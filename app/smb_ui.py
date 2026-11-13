"""DEV-only SMB2/3 mirror: no privileged mount, no SMB passwords in the UI status.

Only read operations are sent to a private IPv4 SMB endpoint. Network files
are copied into the isolated DEV mirror, never into production. The worker owns
the mirror, the web process only probes and stores encrypted credentials.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .media_sources import split_unc, validate_unc, load_sources, SourceError
from .folder_sync import valid_child_name
from .library import _MEDIA, MAX_MEDIA

MAX_FOLDERS = 150
MAX_FILES = 1500
# Safety boundary for EACH batch, not for the entire network library.
MAX_BYTES_PER_CYCLE = 4 * 1024 ** 3
CHUNK = 256 * 1024


class SMBSetupError(ValueError):
    pass


def enabled():
    return os.environ.get('DEV_SMB_UI', '0') == '1'


def credentials_file():
    return Path(os.environ.get('DEV_SMB_CREDENTIALS_FILE',
                               '/data/dev-smb-credentials.bin'))


def _status_path():
    return Path(os.environ.get('MEDIA_MOUNT_STATUS_FILE',
                               '/data/smb-sync-status.json'))


def _secret_cipher():
    secret = os.environ.get('APP_SECRET_KEY', '')
    if len(secret) < 32:
        raise SMBSetupError('DEV-Schlüssel fehlt oder ist ungültig')
    key = base64.urlsafe_b64encode(hashlib.sha256(
        b'anthias-dev-smb-v1:' + secret.encode('utf-8')).digest())
    return Fernet(key)


def _atomic_write(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.dev-smb-',
                                         mode='wb', delete=False) as target:
            filename = Path(target.name)
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(filename, mode)
        os.replace(filename, path)
    finally:
        if filename:
            filename.unlink(missing_ok=True)


def _fingerprint(unc):
    return hashlib.sha256(validate_unc(unc).encode('utf-8')).hexdigest()


def _public_status(state, unc, revision, *, detail='', folders=0, files=0,
                   done=0, bytes_copied=0, pending=0):
    return {
        'checked_at': time.time(),
        'provider': 'python-smb',
        'sources': {
            'default': {
                'state': state,
                'fingerprint': _fingerprint(unc),
                'revision': revision,
                'detail': detail[:160],
                'folders': folders,
                'files': files,
                'done': done,
                'pending': pending,
                'bytes': bytes_copied,
            }
        },
    }


def write_status(state, unc, revision, **info):
    doc = _public_status(state, unc, revision, **info)
    _atomic_write(_status_path(), json.dumps(doc, ensure_ascii=False).encode())


def safe_status():
    try:
        path = _status_path()
        if not path.exists() or path.stat().st_size > 32768:
            return {}
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}


def _get_credentials():
    path = credentials_file()
    if not path.exists():
        return None
    try:
        if path.stat().st_size > 32768:
            raise SMBSetupError('SMB-Anmeldedaten beschädigt')
        plain = _secret_cipher().decrypt(path.read_bytes())
        data = json.loads(plain)
        if data.get('version') != 1 or data.get('alias') != 'default':
            raise ValueError('bad document')
        validate_unc(data['unc'])
        if not all(isinstance(data.get(key), str)
                   for key in ('username', 'password', 'domain', 'revision')):
            raise ValueError('bad fields')
        return data
    except (InvalidToken, ValueError, KeyError, OSError, TypeError):
        raise SMBSetupError('SMB-Anmeldedaten können nicht gelesen werden; bitte erneut im DEV-UI verbinden') from None


def credential_is_current(record):
    current = _get_credentials()
    if not current or current['revision'] != record['revision']:
        return False
    sources = {row['alias']: row['unc'] for row in load_sources()}
    return sources.get('default') == record['unc']


def _unc_path(unc):
    server, share, folders = split_unc(unc)
    slash = chr(92)
    return slash * 2 + server + slash + share + (
        slash + folders.replace('/', slash) if folders else ''), server


def _options(record):
    name = record['username']
    if record['domain']:
        name = record['domain'] + chr(92) + name
    return {'username': name, 'password': record['password'],
            'encrypt': True, 'connection_timeout': 8}


def _smb():
    import smbclient
    return smbclient


def _scan_directories(record):
    smbclient = _smb()
    root, _ = _unc_path(record['unc'])
    names = []
    with smbclient.scandir(root, **_options(record)) as entries:
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink() and valid_child_name(entry.name):
                names.append(entry.name)
                if len(names) > MAX_FOLDERS:
                    raise SMBSetupError('Mehr als 150 Bildschirmordner: Quelle zu groß')
    return sorted(names, key=str.casefold)


def _error_description(exc):
    # Never show exception text: some SMB libraries include UNC and usernames.
    name = type(exc).__name__.lower()
    hint = str(exc).upper()
    if 'LOGON_FAILURE' in hint or 'ACCESS_DENIED' in hint or 'INVALID_CREDENTIAL' in hint:
        return 'Anmeldung/Berechtigung fehlgeschlagen. Benutzer, Kennwort und SMB-Freigabe prüfen.'
    if 'timeout' in name or 'TIMED_OUT' in hint:
        return 'SMB-Server antwortet nicht rechtzeitig (Port 445 oder Netzwerk prüfen).'
    if 'BAD_NETWORK_NAME' in hint or 'OBJECT_PATH_NOT_FOUND' in hint:
        return 'Freigabe oder Unterordner existiert nicht.'
    return 'SMB-Verbindung/Lesen fehlgeschlagen. Pfad, SMB3-Verschlüsselung und Berechtigungen prüfen.'


def test_connection(unc, username, password, domain=''):
    if not enabled():
        raise SMBSetupError('Der UI-SMB-Connector ist nur in DEV verfügbar')
    unc = validate_unc(unc)
    username = str(username or '').strip()
    domain = str(domain or '').strip()
    password = str(password or '')
    if not 1 <= len(username) <= 128 or len(password) > 512 or not password:
        raise SMBSetupError('SMB-Benutzername und Kennwort sind erforderlich')
    if len(domain) > 128 or any(x in domain for x in '/\\\r\n\x00'):
        raise SMBSetupError('Ungültige SMB-Domäne')
    record = {'version': 1, 'alias': 'default', 'unc': unc, 'username': username,
              'password': password, 'domain': domain, 'revision': secrets.token_hex(16)}
    try:
        folders = _scan_directories(record)
        return record, folders
    except Exception as exc:
        raise SMBSetupError(_error_description(exc)) from None
    finally:
        try:
            _smb().reset_connection_cache()
        except Exception:
            pass


def store_credentials(record):
    encoded = json.dumps(record, ensure_ascii=False).encode('utf-8')
    _atomic_write(credentials_file(), _secret_cipher().encrypt(encoded))


def request_sync():
    trigger = Path(os.environ.get('DEV_SMB_TRIGGER_FILE', '/data/dev-smb-trigger'))
    _atomic_write(trigger, secrets.token_hex(12).encode('ascii'))


def _safe_local_dir(base, name):
    target = base / name
    if not valid_child_name(name) and not re.fullmatch(r'\.default-stage-[a-f0-9]{32}', name):
        raise SMBSetupError('Ungültiger Medienordnername')
    if base.is_symlink() or target.is_symlink() or base.resolve() == target.resolve():
        raise SMBSetupError('Unsicherer lokaler Medienpfad')
    target.mkdir(parents=True, exist_ok=True)
    if target.resolve().parent != base.resolve():
        raise SMBSetupError('Unsicherer lokaler Medienpfad')
    return target


def _copy_file(smbclient, source, dest, record, expected, progress=None):
    fd = None
    written = 0
    last_heartbeat = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix='.download-',
                                         delete=False) as temp:
            fd = Path(temp.name)
            with smbclient.open_file(source, mode='rb', **_options(record)) as remote:
                while True:
                    chunk = remote.read(CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_MEDIA or written > expected:
                        raise SMBSetupError('SMB-Mediendatei überschreitet die erwartete Größe')
                    temp.write(chunk)
                    if progress is not None and time.monotonic() - last_heartbeat >= 3:
                        progress(written)
                        last_heartbeat = time.monotonic()
            temp.flush()
            os.fsync(temp.fileno())
        if written != expected:
            raise SMBSetupError('Datei auf SMB wurde während des Kopierens verändert')
        os.chmod(fd, 0o600)
        os.replace(fd, dest)
        fd = None
        return written
    finally:
        if fd:
            fd.unlink(missing_ok=True)


def _read_manifest(path):
    try:
        if path.stat().st_size > 262144:
            return {}
        result = json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def mirror_cycle(root=None):
    """Probe, stage and copy recognized media; never delete the last good mirror.

    Only the worker writes to /sources. Local removed-media cleanup is not
    performed: DEV_PRUNE_MISSING remains a separate, explicit policy.
    """
    if not enabled():
        return None
    record = _get_credentials()
    if not record:
        return None
    if not credential_is_current(record):
        return None
    root = Path(root or os.environ.get('MEDIA_SOURCE_ROOT', '/sources'))
    mirror = root / 'default'
    manifest_path = Path(os.environ.get('DEV_SMB_MIRROR_INDEX', '/data/dev-smb-mirror-index.json'))
    old = _read_manifest(manifest_path)
    new_revision = old.get('revision') != record['revision'] or old.get('unc') != record['unc']
    if new_revision:
        old = {}
    # On source/credential replacement, download into a new hidden cache.
    # Do not mix old UNC media with a new source or take down a good mirror
    # before the new source has been fully checked.
    stage = root / ('.default-stage-' + record['revision'])
    if new_revision and stage.is_symlink():
        raise SMBSetupError('Unsicherer DEV-Zwischenspeicher')
    target_root = stage if new_revision else mirror
    current = {}
    copied = 0
    files = 0
    transferred = 0
    folders = []
    try:
        folders = _scan_directories(record)
        if new_revision:
            _safe_local_dir(root, stage.name)
        else:
            _safe_local_dir(root, 'default')
        write_status('syncing', record['unc'], record['revision'],
                     detail='Ordner entdeckt, Dateien werden geprüft', folders=len(folders))
        smbclient = _smb()
        remote_root, _ = _unc_path(record['unc'])
        for name in folders:
            local = _safe_local_dir(target_root, name)
            with smbclient.scandir(remote_root + chr(92) + name,
                                   **_options(record)) as directory:
                for entry in directory:
                    filename = entry.name
                    if (not valid_child_name(filename) or
                            Path(filename).suffix.lower() not in _MEDIA or
                            not entry.is_file() or entry.is_symlink()):
                        continue
                    info = entry.stat()
                    size = int(info.st_size)
                    if size <= 0 or size > MAX_MEDIA:
                        continue
                    files += 1
                    if files > MAX_FILES:
                        raise SMBSetupError('Zu viele Medien in einem Abgleich (max. 1500)')
                    revision = str(size) + ':' + str(getattr(info, 'st_mtime_ns', int(info.st_mtime * 1e9)))
                    key = name + '/' + filename
                    destination = local / filename
                    if destination.is_symlink():
                        raise SMBSetupError('Unsicherer lokaler Medienpfad')
                    if (old.get('files', {}).get(key) == revision and destination.is_file()
                            and destination.stat().st_size == size):
                        current[key] = revision
                        continue
                    if transferred + size > MAX_BYTES_PER_CYCLE:
                        raise SMBSetupError('Transfer-Limit dieses Abgleichs erreicht (4 GiB)')
                    copied_bytes = _copy_file(smbclient, remote_root + chr(92) + name +
                                              chr(92) + filename, destination, record, size)
                    transferred += copied_bytes
                    copied += 1
                    current[key] = revision
                    if not credential_is_current(record):
                        raise SMBSetupError('SMB-Zuordnung wurde geändert; alten Abgleich gestoppt')
                    write_status('syncing', record['unc'], record['revision'],
                                 detail='Medien werden heruntergeladen', folders=len(folders),
                                 files=files, done=copied, bytes_copied=transferred)
        if not credential_is_current(record):
            raise SMBSetupError('SMB-Zuordnung geändert; Ergebnis nicht übernommen')
        if new_revision:
            previous = root / ('.default-previous-' + record['revision'])
            if previous.exists() or previous.is_symlink():
                raise SMBSetupError('Alter DEV-Zwischenspeicher muss geprüft werden')
            renamed = False
            try:
                if mirror.exists():
                    if mirror.is_symlink():
                        raise SMBSetupError('Unsicherer DEV-Medienspiegel')
                    mirror.rename(previous)
                    renamed = True
                stage.rename(mirror)
            except Exception:
                if renamed and not mirror.exists():
                    previous.rename(mirror)
                raise
        manifest = {'unc': record['unc'], 'revision': record['revision'],
                    'files': current, 'checked_at': time.time()}
        _atomic_write(manifest_path, json.dumps(manifest).encode('utf-8'))
        write_status('connected', record['unc'], record['revision'],
                     detail='SMB-Ordner geprüft, lokaler DEV-Spiegel aktualisiert',
                     folders=len(folders), files=files, done=copied,
                     bytes_copied=transferred)
        return {'folders': len(folders), 'files': files, 'copied': copied,
                'bytes': transferred}
    except Exception as exc:
        if credential_is_current(record):
            write_status('error', record['unc'], record['revision'],
                         detail=(str(exc)[:160] if isinstance(exc, SMBSetupError)
                                 else _error_description(exc)),
                         folders=len(folders), files=files,
                         done=copied, bytes_copied=transferred)
        return {'error': 'SMB-Ordner konnte nicht vollständig eingelesen werden'}
    finally:
        try:
            _smb().reset_connection_cache()
        except Exception:
            pass
