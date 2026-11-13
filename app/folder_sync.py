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


DEFAULT_LIBRARY_ALIAS = 'default'
# The one approved parent mount contains independent folders for each screen.
# Names come from the real SMB directory and may include spaces or umlauts.
_CHILD_MAX = 180


def valid_child_name(value):
    return (isinstance(value, str) and 0 < len(value) <= _CHILD_MAX
            and value not in ('.', '..') and not value.startswith('.')
            and '/' not in value and '\\' not in value
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
            and value == value.strip() and value[-1] not in ('.', ' '))


def _source_parts(value):
    if not isinstance(value, str):
        raise LibraryError('Ungültige Ordnerquelle')
    parts = value.split('/')
    if len(parts) == 1 and _ALIAS.fullmatch(parts[0]):
        return parts[0], None
    if (len(parts) == 2 and parts[0] == DEFAULT_LIBRARY_ALIAS
            and valid_child_name(parts[1])):
        return parts[0], parts[1]
    raise LibraryError('Ungültige Ordnerquelle; nur ein registrierter Ordner oder ein Unterordner der Standardbibliothek')


def _base(root):
    base = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    if base.is_symlink() or not base.is_dir():
        raise LibraryError('Medienquellen sind nicht eingebunden')
    return base


def source_directory(alias, root=None):
    parent_alias, child = _source_parts(alias)
    # A retired entry must not remain usable just because CIFS is still mounted.
    from .media_sources import SourceError, retired_aliases
    try:
        if parent_alias in retired_aliases():
            raise LibraryError('Netzwerkquelle wurde im Hub ausgetragen; Host-Mount separat bereinigen')
    except SourceError as exc:
        raise LibraryError(str(exc)) from exc
    base = _base(root)
    mount = base / parent_alias
    if mount.is_symlink() or not mount.is_dir() or mount.resolve().parent != base.resolve():
        raise LibraryError('Medienordner fehlt oder ist nicht erlaubt')
    # The parent is the mountpoint; children beneath the default media library
    # are deliberately not separate network mounts.
    if os.environ.get('FOLDER_REQUIRE_MOUNT', '0') == '1' and not os.path.ismount(mount):
        raise LibraryError('Netzwerkquelle nicht eingehängt; vorhandene Medien bleiben erhalten')
    if os.environ.get('FOLDER_REQUIRE_VERIFIED', '0') == '1':
        from .media_sources import SourceError, load_sources, mount_statuses
        try:
            registry = {entry['alias'] for entry in load_sources()}
            if parent_alias in registry and mount_statuses().get(parent_alias) not in ('mounted', 'already-mounted', 'connected'):
                raise LibraryError('SMB-Pfad noch nicht durch den Host bestätigt; Import gestoppt')
        except SourceError as exc:
            raise LibraryError(str(exc)) from exc
    if child is None:
        return mount
    path = mount / child
    if path.is_symlink() or not path.is_dir() or path.resolve().parent != mount.resolve():
        raise LibraryError('Unterordner der Standardbibliothek ist nicht erreichbar oder nicht erlaubt')
    return path


def default_library_folders(root=None):
    """Browse only direct child directories of the approved default SMB mount."""
    try:
        parent = source_directory(DEFAULT_LIBRARY_ALIAS, root)
    except LibraryError:
        return []
    try:
        return sorted(
            [entry.name for entry in parent.iterdir()
             if valid_child_name(entry.name) and not entry.is_symlink()
             and entry.is_dir() and entry.resolve().parent == parent.resolve()],
            key=str.casefold,
        )
    except OSError:
        return []


def available_sources(root=None):
    """Only show approved top-level aliases or direct default library folders."""
    base = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    if base.is_symlink() or not base.is_dir():
        return []
    from .media_sources import SourceError, retired_aliases
    try:
        retired = set(retired_aliases())
    except SourceError:
        return []  # A damaged registry must not expose retired mounts.
    standalone = sorted(
        (entry.name for entry in base.iterdir()
         if entry.name != DEFAULT_LIBRARY_ALIAS and entry.name not in retired and _ALIAS.fullmatch(entry.name)
         and not entry.is_symlink() and entry.is_dir()
         and entry.resolve().parent == base.resolve()),
        key=str.casefold,
    )
    return standalone + [f'{DEFAULT_LIBRARY_ALIAS}/{folder}'
                         for folder in default_library_folders(base)]

def sync_template(store, template_id, root=None, prune_missing=None):
    """Import stable files; optionally retire missing media only after two scans.

    The source must be reachable and nonempty in both successful scans.
    Never treat an empty/unmounted share as an instruction to erase a screen.
    Manual template media and webpages are never removed.
    """
    template = store.get(template_id)
    alias = template.get('folder_source')
    if not alias:
        return {'added': 0, 'updated': 0, 'skipped': 0}
    folder = source_directory(alias, root)
    entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    if prune_missing is None:
        prune_missing = os.environ.get('FOLDER_PRUNE_MISSING', '0') == '1'
    # All present supported filenames count, including files that are still
    # being written or rejected by the signature checker. Those must never be
    # mistaken for a deletion.
    present = {entry.name for entry in entries
               if entry.suffix.lower() in _MEDIA and not entry.is_symlink()
               and entry.is_file()}
    results = {'added': 0, 'updated': 0, 'skipped': 0, 'retired': 0}
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
    # Deliberate opt-in only. Two consecutive nonempty, verified successful
    # scans are required before removing a missing file from the Hub manifest.
    # Only *source_file* entries qualify. Cached blobs are retained on disk
    # for recovery; Pi retirement happens in folder_publish and is reversible.
    if prune_missing and present:
        with store_lock(store):
            current = store.get(template_id)
            stale = []
            changed = False
            for item in current['items']:
                name = item.get('source_file')
                if not name:
                    continue
                if name in present:
                    if item.pop('source_missing_checks', None) is not None:
                        changed = True
                    continue
                checks = min(2, int(item.get('source_missing_checks', 0)) + 1)
                if checks >= 2:
                    stale.append(item['id'])
                else:
                    item['source_missing_checks'] = checks
                    changed = True
            if stale:
                current['items'] = [item for item in current['items']
                                    if item['id'] not in stale]
                results['retired'] = len(stale)
                changed = True
            if changed:
                store._save(current)
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
    v2 = os.environ.get('HUB_WORKFLOW_V2', '0') == '1'
    results = {}
    for template in store.list():
        folder = bool(template.get('folder_source'))
        # A manual template is only part of the synchronization loop when
        # source-of-truth v2 is enabled AND a device is explicitly assigned.
        if not folder and not (v2 and template.get('auto_devices')):
            continue
        template_id = template['id']
        try:
            imported = sync_template(store, template_id, root) if folder else {
                'added': 0, 'updated': 0, 'retired': 0, 'skipped': 0}
            results[template_id] = {'import': imported, 'devices': {}}
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
                        api_factory=api_factory,
                        retire_missing=os.environ.get('FOLDER_PRUNE_MISSING', '0') == '1',
                        allow_manual=v2 and not folder)
                except (PublishError, PlayerError, LibraryError, ScheduleError,
                        OSError, ValueError) as exc:
                    results[template_id]['devices'][device_id] = {'error': str(exc)}
    return results


def worker():
    interval = max(60, int(os.environ.get('FOLDER_SYNC_INTERVAL', '1800')))
    trigger = Path(os.environ.get('DEV_SMB_TRIGGER_FILE', '/data/dev-smb-trigger'))
    while True:
        # Capture before work: a new UI request arriving during a scan must
        # trigger another scan instead of being swallowed by the sleep timer.
        try:
            at_start = trigger.stat().st_mtime_ns
        except OSError:
            at_start = 0
        try:
            if os.environ.get('DEV_SMB_UI', '0') == '1':
                from .smb_ui import mirror_cycle
                mirror_cycle()
            reports = run_cycle()
            from .folder_status import write_status
            write_status(reports, enabled=os.environ.get('FOLDER_AUTO_PUBLISH', '0') == '1',
                         interval_seconds=interval,
                         prune_missing=os.environ.get('FOLDER_PRUNE_MISSING', '0') == '1')
            for template_id, report in reports.items():
                if 'error' in report:
                    print(f'Folder {template_id}: import unavailable: {report["error"]}', flush=True)
                    continue
                changed = (report['import']['added'] + report['import']['updated']
                           + report['import'].get('retired', 0))
                if changed:
                    print(f'Folder {template_id}: imported {report["import"]}', flush=True)
                for device_id, status in report['devices'].items():
                    if 'error' in status:
                        print(f'Folder {template_id}, device {device_id}: {status["error"]}', flush=True)
                    elif status['added'] or status['updated'] or status['disabled']:
                        print(f'Folder {template_id}, device {device_id}: {status}', flush=True)
        except (LibraryError, OSError, ValueError) as exc:
            print(f'Folder cycle failed, keeping existing media: {exc}', flush=True)
        if os.environ.get('DEV_SMB_UI', '0') == '1':
            # The UI queues a sync through the shared /data directory. Wake up
            # quickly rather than making the operator wait a full 60 seconds.
            for _ in range(interval):
                time.sleep(1)
                try:
                    changed = trigger.stat().st_mtime_ns
                except OSError:
                    changed = 0
                if changed != at_start:
                    break
        else:
            time.sleep(interval)


if __name__ == '__main__':
    worker()
