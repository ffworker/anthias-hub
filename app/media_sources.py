"""IT-editable SMB source registry. No passwords or mount privileges in Flask."""
import ipaddress
import hashlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path

LOCK = threading.RLock()
ALIAS = re.compile(r'^[a-z0-9][a-z0-9_-]{0,39}$')
SHARE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.$ -]{0,79}$')
PART = re.compile(r'^[^<>:"|?*\\/\x00-\x1f]{1,180}$')


class SourceError(ValueError):
    pass


def validate_alias(value):
    alias = str(value or '').strip().lower()
    if not ALIAS.fullmatch(alias):
        raise SourceError('Ordnerkennung: 1–40 Zeichen, Kleinbuchstaben, Ziffern, - oder _')
    return alias


def validate_unc(value):
    """Require a literal private IPv4 server and a normalized SMB subdirectory."""
    raw = str(value or '').strip()
    if len(raw) > 650 or '\x00' in raw:
        raise SourceError('SMB-Pfad zu lang oder ungültig')
    normalized = raw.replace('\\', '/')
    if not normalized.startswith('//') or normalized.startswith('///'):
        raise SourceError('SMB-Pfad muss //SERVER/FREIGABE/ORDNER sein')
    parts = normalized[2:].split('/')
    if len(parts) < 2 or any(not p for p in parts):
        raise SourceError('SMB-Pfad ohne leere oder doppelte Verzeichnisse angeben')
    server, share, *folders = parts
    try:
        ip = ipaddress.ip_address(server)
    except ValueError:
        raise SourceError('Bitte die feste private IPv4-Adresse des SMB-Servers verwenden') from None
    if ip.version != 4 or not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise SourceError('Nur private IPv4-Adressen für SMB-Server erlaubt')
    if not SHARE.fullmatch(share) or share in ('.', '..'):
        raise SourceError('Ungültiger Freigabename')
    if any(not PART.fullmatch(p) or p in ('.', '..') or p.endswith(('.', ' ')) for p in folders):
        raise SourceError('Ungültiger SMB-Unterordner')
    return f'//{server}/{share}' + ''.join('/' + part for part in folders)


def split_unc(unc):
    parts = validate_unc(unc)[2:].split('/')
    return parts[0], parts[1], '/'.join(parts[2:])


def registry_file(path=None):
    return Path(path or os.environ.get('MEDIA_SOURCES_FILE', '/data/media-sources.json'))


def load_sources(path=None):
    target = registry_file(path)
    try:
        if not target.exists():
            return []
        if target.stat().st_size > 131072:
            raise SourceError('Medienquellen-Datei zu groß')
        record = json.loads(target.read_text(encoding='utf-8'))
        if record.get('version') != 1 or not isinstance(record.get('sources'), list):
            raise ValueError('invalid registry')
        entries = record['sources']
        if len(entries) > 50:
            raise ValueError('too many entries')
        ids = set()
        cleaned = []
        for src in entries:
            if not isinstance(src, dict):
                raise ValueError('invalid entry')
            alias, unc = validate_alias(src.get('alias')), validate_unc(src.get('unc'))
            if alias in ids:
                raise ValueError('duplicate alias')
            ids.add(alias)
            cleaned.append({'alias': alias, 'unc': unc})
        return sorted(cleaned, key=lambda item: item['alias'])
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise SourceError('Gespeicherte Medienquellen beschädigt oder unlesbar') from exc


def save_source(alias, unc, *, path=None):
    alias, unc = validate_alias(alias), validate_unc(unc)
    target = registry_file(path)
    with LOCK:
        entries = load_sources(target)
        old = next((x for x in entries if x['alias'] == alias), None)
        if old and old['unc'] == unc:
            return 'unchanged'
        if old:
            old['unc'] = unc
            result = 'updated'
        else:
            if len(entries) >= 50:
                raise SourceError('Maximal 50 Medienquellen')
            entries.append({'alias': alias, 'unc': unc})
            result = 'created'
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.media-sources-',
                                             mode='w', encoding='utf-8', delete=False) as f:
                tmp = Path(f.name)
                json.dump({'version': 1, 'sources': entries}, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
    return result


def mount_statuses(path=None):
    """Host helper writes only non-sensitive per-alias states, never passwords."""
    target = Path(path or os.environ.get('MEDIA_MOUNT_STATUS_FILE', '/data/media-mount-status.json'))
    try:
        if not target.is_file() or target.stat().st_size > 32768:
            return {}
        doc = json.loads(target.read_text(encoding='utf-8'))
        statuses = doc.get('sources')
        if not isinstance(statuses, dict):
            return {}
        sources = {row['alias']: row['unc'] for row in load_sources()}
        result = {}
        for key, value in statuses.items():
            if not ALIAS.fullmatch(str(key)) or key not in sources or not isinstance(value, dict):
                continue
            expected = hashlib.sha256(sources[key].encode('utf-8')).hexdigest()
            state = value.get('state', 'pending')
            if value.get('fingerprint') != expected:
                state = 'pending'
            if state in ('mounted', 'already-mounted', 'blocked', 'pending', 'conflict', 'error'):
                result[key] = state
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
