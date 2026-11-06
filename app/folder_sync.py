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
                new = store.add_media(template_id, entry.stem[:100] or entry.name[:100],
                                      stage, entry.name, 15)
        with store_lock(store):
            updated = store.get(template_id)
            created = updated['items'][-1]
            created['source_file'] = entry.name
            created['source_fingerprint'] = fingerprint
            if previous:
                updated['items'] = [x for x in updated['items'] if x['id'] != previous['id']]
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


def worker():
    interval = max(60, int(os.environ.get('FOLDER_SYNC_INTERVAL', '300')))
    while True:
        try:
            sync_all()
        except (LibraryError, OSError, ValueError) as exc:
            print(f'Folder import failed, keeping existing media: {exc}', flush=True)
        time.sleep(interval)


if __name__ == '__main__':
    worker()
