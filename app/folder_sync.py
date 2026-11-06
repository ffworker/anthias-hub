"""Read-only folder import for Hub playlist templates.

Network shares are mounted outside the container and exposed beneath
MEDIA_SOURCE_ROOT. This process never mounts shares or handles SMB secrets.
"""
import hashlib
import os
import re
import time
from pathlib import Path

from .library import Library, LibraryError, _MEDIA, MAX_MEDIA

_ALIAS = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')
_CHUNK = 256 * 1024


def source_directory(alias, root=None):
    if not _ALIAS.fullmatch(str(alias)):
        raise LibraryError('Ungültiger Ordnername (nur Buchstaben, Zahlen, _ und -)')
    base = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    if not base.is_dir():
        raise LibraryError('Medienquellen sind nicht eingebunden')
    path = base / alias
    # Do not follow aliases into arbitrary host paths.
    if path.is_symlink() or not path.is_dir() or path.resolve().parent != base.resolve():
        raise LibraryError('Medienordner fehlt oder ist nicht erlaubt')
    return path


def available_sources(root=None):
    """Only return allowed first-level directory aliases; never expose UNC paths."""
    base = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    if not base.is_dir():
        return []
    return sorted(
        (item.name for item in base.iterdir()
         if _ALIAS.fullmatch(item.name) and not item.is_symlink()
         and item.is_dir() and item.resolve().parent == base.resolve()),
        key=str.casefold,
    )


def sync_template(store, template_id, root=None):
    """Import stable files, never delete on an unavailable or empty share.

    Only explicitly folder-managed entries are replaced. Existing manual
    content stays untouched; device playlists are never modified here.
    """
    template = store.get(template_id)
    alias = template.get('folder_source')
    if not alias:
        return {'added': 0, 'updated': 0, 'skipped': 0}
    folder = source_directory(alias, root)
    entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    results = {'added': 0, 'updated': 0, 'skipped': 0}
    for entry in entries:
        if entry.is_symlink() or not entry.is_file() or entry.suffix.lower() not in _MEDIA:
            continue
        stat_before = entry.stat()
        if not 0 < stat_before.st_size <= MAX_MEDIA:
            results['skipped'] += 1
            continue
        current = store.get(template_id)
        previous = next((x for x in current['items'] if x.get('source_file') == entry.name), None)
        # Size and nanosecond mtime are a quick incremental filter.
        fingerprint = f'{stat_before.st_size}:{stat_before.st_mtime_ns}'
        if previous and previous.get('source_fingerprint') == fingerprint:
            results['skipped'] += 1
            continue
        if not previous and len(current['items']) >= 100:
            raise LibraryError('Maximal 100 Inhalte je Vorlage')
        # Refuse changing files; don't publish half-written media.
        with entry.open('rb') as stream:
            import tempfile
            with tempfile.TemporaryFile(dir=store._directory(template_id)) as stage:
                digest = hashlib.sha256()
                while True:
                    chunk = stream.read(_CHUNK)
                    if not chunk:
                        break
                    stage.write(chunk)
                    digest.update(chunk)
                stat_after = entry.stat()
                if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
                    results['skipped'] += 1
                    continue
                stage.seek(0)
                # add_media performs signature checks, bounded copy and disk guards.
                # Existing per-slide timing survives file changes on SMB.
                duration = previous['duration'] if previous else 15
                store.add_media(template_id, entry.stem[:100] or entry.name[:100],
                                stage, entry.name, duration)
        with store_lock(store):
            updated = store.get(template_id)
            created = updated['items'][-1]
            created['source_file'] = entry.name
            created['source_fingerprint'] = fingerprint
            if previous:
                # Preserve the item's identity and position for the Marketing
                # editor, and do not turn every re-import into a slide reorder.
                created['id'] = previous['id']
                current_index = next((i for i, item in enumerate(updated['items'][:-1])
                                      if item['id'] == previous['id']), None)
                if current_index is None:
                    raise LibraryError('Vorlage wurde gleichzeitig verändert; Import prüfen')
                updated['items'].pop()
                updated['items'][current_index] = created
                results['updated'] += 1
            else:
                results['added'] += 1
            store._save(updated)
    return results


def store_lock(store):
    # Use the same lock as all Library mutations.
    from .library import _lock
    return _lock


def sync_all(root=None, library_dir=None):
    store = Library(library_dir or os.environ.get('LIBRARY_DIR', '/data/library'))
    return {t['id']: sync_template(store, t['id'], root)
            for t in store.list() if t.get('folder_source')}


def run_cycle(*, root=None, library_dir=None, devices_file=None, state_root=None,
              schedules_file=None, auto_publish=None, api_factory=None):
    """Independent per-template sync; never publish if its import failed."""
    from .folder_publish import reconcile, Anthias, PublishError
    from .anthias import PlayerError
    from .schedules import ScheduleError
    store = Library(library_dir or os.environ.get('LIBRARY_DIR', '/data/library'))
    devices_file = devices_file or os.environ.get('DEVICES_FILE', '/data/devices.json')
    state_root = state_root or os.environ.get('FOLDER_PUBLICATIONS_DIR', '/data/folder-publications')
    schedules_file = schedules_file or os.environ.get('SCHEDULES_FILE', '/data/schedules.json')
    if auto_publish is None:
        auto_publish = os.environ.get('FOLDER_AUTO_PUBLISH', '0') == '1'
    if api_factory is None:
        api_factory = Anthias
    results = {}
    for template in store.list():
        if not template.get('folder_source'):
            continue
        template_id = template['id']
        try:
            results[template_id] = {'import': sync_template(store, template_id, root),
                                    'devices': {}}
        except (OSError, LibraryError, ValueError) as exc:
            results[template_id] = {'error': str(exc)}
            continue
        # Folder imports remain useful independently; Pi writes are opt-in
        # both per template and via this server-side feature flag.
        if auto_publish:
            # Read fresh template after import; IT may have revoked a mapping.
            for device_id in store.get(template_id).get('auto_devices', []):
                try:
                    results[template_id]['devices'][device_id] = reconcile(
                        store, template_id, device_id, devices_file=devices_file,
                        state_root=state_root, schedules_file=schedules_file,
                        api_factory=api_factory)
                except (PublishError, PlayerError, LibraryError, ScheduleError,
                        OSError, ValueError) as exc:
                    results[template_id]['devices'][device_id] = {'error': str(exc)}
    return results


def worker():
    interval = max(60, int(os.environ.get('FOLDER_SYNC_INTERVAL', '300')))
    while True:
        try:
            reports = run_cycle()
            from .folder_status import write_status
            write_status(reports, enabled=os.environ.get('FOLDER_AUTO_PUBLISH', '0') == '1')
            for template_id, report in reports.items():
                if 'error' in report:
                    print(f'Folder {template_id}: import unavailable: {report["error"]}', flush=True)
                    continue
                changed = report['import']['added'] + report['import']['updated']
                if changed:
                    print(f'Folder {template_id}: imported {report["import"]}', flush=True)
                for device_id, status in report['devices'].items():
                    if 'error' in status:
                        print(f'Folder {template_id}, device {device_id}: {status["error"]}', flush=True)
                    elif status['added'] or status['updated'] or status['disabled']:
                        print(f'Folder {template_id}, device {device_id}: {status}', flush=True)
        except (LibraryError, OSError, ValueError) as exc:
            print(f'Folder cycle failed, keeping existing media: {exc}', flush=True)
        time.sleep(interval)


if __name__ == '__main__':
    worker()
