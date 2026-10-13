"""Local, portable playlist templates; media lives under the Hub's /data mount."""
import hashlib
import io
import json
import os
import re
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from threading import RLock

from .anthias import validate_duration, validate_website_url

_lock = RLock()
_ID = re.compile(r'^[a-f0-9]{32}$')
_MEDIA = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.mp4': 'video/mp4'}
MAX_MEDIA = 50 * 1024 * 1024
MAX_ARCHIVE = 250 * 1024 * 1024


class LibraryError(ValueError):
    pass


def _title(value):
    name = str(value).strip()
    if not 1 <= len(name) <= 100:
        raise LibraryError('Titel muss 1 bis 100 Zeichen haben')
    return name


def _signature(data, ext):
    return {'.png': data.startswith(b'\x89PNG\r\n\x1a\n'),
            '.jpg': data.startswith(b'\xff\xd8'), '.jpeg': data.startswith(b'\xff\xd8'),
            '.webp': data.startswith(b'RIFF') and data[8:12] == b'WEBP',
            '.mp4': len(data) >= 12 and data[4:8] == b'ftyp'}.get(ext, False)


class Library:
    def __init__(self, root):
        self.root = Path(root)

    def _directory(self, ident):
        if not _ID.fullmatch(str(ident)):
            raise LibraryError('Ungültige Vorlagen-ID')
        return self.root / ident

    def _save(self, item):
        directory = self._directory(item['id'])
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(item, ensure_ascii=False, indent=2).encode('utf-8')
        temp = directory / '.manifest.tmp'
        with temp.open('wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, directory / 'manifest.json')

    def create(self, name):
        item = {'version': 1, 'id': uuid.uuid4().hex, 'name': _title(name), 'items': []}
        with _lock:
            self._save(item)
        return item

    def get(self, ident):
        try:
            return json.loads((self._directory(ident) / 'manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise LibraryError('Vorlage nicht gefunden oder beschädigt') from exc

    def list(self):
        if not self.root.exists():
            return []
        return sorted((self.get(p.name) for p in self.root.iterdir() if p.is_dir() and _ID.fullmatch(p.name)), key=lambda x: x['name'].casefold())

    def add_url(self, ident, name, url, duration):
        try:
            address = validate_website_url(url)
            seconds = validate_duration(duration)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        with _lock:
            collection = self.get(ident)
            if len(collection['items']) >= 100:
                raise LibraryError('Maximal 100 Inhalte je Vorlage')
            collection['items'].append({'id': uuid.uuid4().hex, 'kind': 'url', 'name': _title(name), 'url': address, 'duration': seconds})
            self._save(collection)
        return collection

    def add_media(self, ident, name, stream, filename, duration, max_bytes=MAX_MEDIA):
        ext = Path(str(filename)).suffix.lower()
        if ext not in _MEDIA:
            raise LibraryError('Erlaubt: PNG, JPG, WebP, MP4')
        try:
            seconds = 0 if ext == '.mp4' else validate_duration(duration)
        except ValueError as exc:
            raise LibraryError(str(exc)) from exc
        title = _title(name)
        data = stream.read(max_bytes + 1)
        if len(data) > max_bytes or not _signature(data[:16], ext):
            raise LibraryError('Datei zu groß oder Dateiformat ungültig')
        with _lock:
            collection = self.get(ident)
            if len(collection['items']) >= 100:
                raise LibraryError('Maximal 100 Inhalte je Vorlage')
            relative = 'media/' + hashlib.sha256(data).hexdigest() + ext
            dest = self._directory(ident) / relative
            dest.parent.mkdir(mode=0o700, exist_ok=True)
            if not dest.exists():
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as temp:
                    temp.write(data)
                    temp_name = temp.name
                os.chmod(temp_name, 0o600)
                os.replace(temp_name, dest)
            collection['items'].append({'id': uuid.uuid4().hex, 'kind': 'media', 'name': title, 'file': relative, 'duration': seconds})
            self._save(collection)
        return collection

    def media_path(self, ident, item):
        relative = item.get('file', '')
        if not re.fullmatch(r'media/[a-f0-9]{64}\.(png|jpg|jpeg|webp|mp4)', relative):
            raise LibraryError('Ungültiger Medienpfad')
        return self._directory(ident) / relative

    def verified_media_path(self, ident, item):
        path = self.media_path(ident, item)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise LibraryError('Vorlagenmedium fehlt oder ist nicht lesbar') from exc
        if len(content) > MAX_MEDIA or hashlib.sha256(content).hexdigest() != path.stem or not _signature(content[:16], path.suffix):
            raise LibraryError('Vorlagenmedium beschädigt oder verändert')
        return path

    def move(self, ident, item_id, direction):
        if direction not in ('up', 'down'):
            raise LibraryError('Ungültige Richtung')
        with _lock:
            collection = self.get(ident)
            ids = [item['id'] for item in collection['items']]
            if item_id not in ids:
                raise LibraryError('Inhalt nicht gefunden')
            index = ids.index(item_id)
            other = index + (-1 if direction == 'up' else 1)
            if 0 <= other < len(ids):
                collection['items'][index], collection['items'][other] = collection['items'][other], collection['items'][index]
                self._save(collection)
        return collection

    def remove(self, ident, item_id):
        with _lock:
            collection = self.get(ident)
            previous = len(collection['items'])
            collection['items'] = [item for item in collection['items'] if item['id'] != item_id]
            if len(collection['items']) == previous:
                raise LibraryError('Inhalt nicht gefunden')
            self._save(collection)
        return collection

    def export(self, ident):
        collection = self.get(ident)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json', json.dumps({k: collection[k] for k in ('version', 'name', 'items')}, ensure_ascii=False))
            for filename in {item['file'] for item in collection['items'] if item['kind'] == 'media'}:
                path = self.verified_media_path(ident, {'file': filename})
                z.write(path, filename)
        return output.getvalue()

    def import_zip(self, source):
        try:
            with zipfile.ZipFile(source) as z:
                entries = z.infolist()
                names = [info.filename for info in entries]
                if (len(entries) > 102 or len(set(names)) != len(names) or 'manifest.json' not in names
                        or sum(info.file_size for info in entries) > MAX_ARCHIVE
                        or any(info.is_dir() or info.flag_bits & 0x1 or info.filename.startswith('/')
                               or '..' in PurePosixPath(info.filename).parts for info in entries)):
                    raise LibraryError('Archiv ist zu groß oder enthält ungültige Pfade')
                if z.getinfo('manifest.json').file_size > 100_000:
                    raise LibraryError('Manifest zu groß')
                raw = z.read('manifest.json')
                manifest = json.loads(raw)
                if not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(manifest.get('items'), list) or len(manifest['items']) > 100:
                    raise LibraryError('Nicht unterstütztes Vorlagenformat')
                clean = []
                media = {}
                for item in manifest['items']:
                    name = _title(item['name'])
                    kind = item['kind']
                    if kind == 'url':
                        clean.append({'id': uuid.uuid4().hex, 'kind': 'url', 'name': name,
                                      'url': validate_website_url(item['url']), 'duration': validate_duration(item['duration'])})
                    elif kind == 'media':
                        relative = item['file']
                        # The archive must carry the exact digest-named binary, not a Pi-only URI.
                        self.media_path('0' * 32, {'file': relative})
                        if relative not in names:
                            raise LibraryError('Archiv enthält nicht alle Mediendateien')
                        data = z.read(relative)
                        ext = Path(relative).suffix.lower()
                        if (len(data) > MAX_MEDIA or hashlib.sha256(data).hexdigest() != Path(relative).stem
                                or not _signature(data[:16], ext)):
                            raise LibraryError('Mediendatei beschädigt oder zu groß')
                        media[relative] = data
                        seconds = 0 if ext == '.mp4' else validate_duration(item['duration'])
                        clean.append({'id': uuid.uuid4().hex, 'kind': 'media', 'name': name, 'file': relative, 'duration': seconds})
                    else:
                        raise LibraryError('Unbekannter Inhaltstyp')
                if set(names) != {'manifest.json', *media}:
                    raise LibraryError('Unerwartete Dateien im Archiv')
                title = _title(manifest['name'])
        except (zipfile.BadZipFile, KeyError, TypeError, ValueError, UnicodeError, RuntimeError) as exc:
            raise LibraryError('Ungültiges Playlist-Archiv') from exc
        with _lock:
            result = self.create(title)
            directory = self._directory(result['id'])
            for relative, data in media.items():
                (directory / 'media').mkdir(mode=0o700, exist_ok=True)
                target = directory / relative
                target.write_bytes(data)
                os.chmod(target, 0o600)
            result['items'] = clean
            self._save(result)
        return result
