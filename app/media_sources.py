"""IT-editable SMB source registry. No passwords or mount privileges in Flask."""
import ipaddress
import hashlib
import json
import os
import re
import tempfile
import threading
import time
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
    raw = str(value or '')
    if raw != raw.strip():
        raise SourceError('SMB-Pfad darf keine führenden oder nachgestellten Leerzeichen enthalten')
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


def retired_aliases(path=None):
    """Explicitly retired aliases stay hidden even while their host mount exists.

    The registry is not a privileged unmount queue. Keeping tombstones prevents
    a still-present legacy mount from silently reappearing as a selectable source.
    """
    target = registry_file(path)
    if not target.exists():
        return []
    try:
        if target.stat().st_size > 131072:
            raise ValueError('oversized registry')
        data = json.loads(target.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('sources'), list):
            raise ValueError('invalid registry')
        values = data.get('retired', [])
        if not isinstance(values, list) or len(values) > 50:
            raise ValueError('invalid retired aliases')
        aliases = [validate_alias(value) for value in values]
        if len(set(aliases)) != len(aliases):
            raise ValueError('duplicate retired alias')
        active = {entry['alias'] for entry in load_sources(target)}
        if active.intersection(aliases):
            raise ValueError('active alias is retired')
        return sorted(aliases)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise SourceError('Gespeicherte Medienquellen beschädigt oder unlesbar') from exc


def _write_registry(target, entries, retired):
    """Atomic local registry update; no SMB files or host mounts are touched."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.media-sources-',
                                         mode='w', encoding='utf-8', delete=False) as f:
            tmp = Path(f.name)
            json.dump({'version': 1, 'sources': entries, 'retired': sorted(retired)},
                      f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def save_source(alias, unc, *, path=None):
    alias, unc = validate_alias(alias), validate_unc(unc)
    target = registry_file(path)
    with LOCK:
        entries = load_sources(target)
        retired = retired_aliases(target)
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
        # A deliberate re-registration un-retires the alias.
        _write_registry(target, entries, [a for a in retired if a != alias])
    return result


def remove_source(alias, *, path=None):
    """Retire a registry entry; never unmount or remove underlying data.

    Callers must check active playlist dependencies under the library lock.
    """
    alias = validate_alias(alias)
    target = registry_file(path)
    with LOCK:
        entries = load_sources(target)
        retired = retired_aliases(target)
        if not any(entry['alias'] == alias for entry in entries):
            raise SourceError('Diese Medienquelle ist nicht (mehr) registriert')
        if len(retired) >= 50:
            raise SourceError('Zu viele ausgetragene Quellen; Host-Bereinigung prüfen')
        _write_registry(target, [entry for entry in entries if entry['alias'] != alias],
                        retired + [alias])
    return 'retired'


def retire_unmanaged_source(alias, *, path=None):
    """Hide a visible legacy host mount without first registering its UNC.

    The caller is responsible for verifying that the alias really exists in
    the trusted mount source directory and that no playlist depends on it.
    """
    alias = validate_alias(alias)
    target = registry_file(path)
    with LOCK:
        entries = load_sources(target)
        retired = retired_aliases(target)
        if any(entry['alias'] == alias for entry in entries):
            raise SourceError('Quelle ist bereits registriert; reguläres Austragen verwenden')
        if alias in retired:
            raise SourceError('Quelle wurde bereits ausgetragen')
        if len(retired) >= 50:
            raise SourceError('Zu viele ausgetragene Quellen; Host-Bereinigung prüfen')
        _write_registry(target, entries, retired + [alias])
    return 'retired'


def mount_statuses(path=None, registry_path=None):
    """Host helper writes only non-sensitive per-alias states, never passwords."""
    target = Path(path or os.environ.get('MEDIA_MOUNT_STATUS_FILE', '/sources/.mount-status.json'))
    try:
        if not target.is_file() or target.stat().st_size > 32768:
            return {}
        doc = json.loads(target.read_text(encoding='utf-8'))
        statuses = doc.get('sources')
        if not isinstance(statuses, dict):
            return {}
        # Only a recently running root-controlled mount coordinator may
        # authorize publishing. A stale status is never an approval.
        checked_at = doc.get('checked_at')
        if not isinstance(checked_at, (float, int)) or not 0 <= time.time() - checked_at < 300:
            return {}
        sources = {row['alias']: row['unc'] for row in load_sources(registry_path)}
        result = {}
        for key, value in statuses.items():
            if not ALIAS.fullmatch(str(key)) or key not in sources or not isinstance(value, dict):
                continue
            expected = hashlib.sha256(sources[key].encode('utf-8')).hexdigest()
            state = value.get('state', 'pending')
            if value.get('fingerprint') != expected:
                state = 'pending'
            if state in ('mounted', 'already-mounted', 'blocked', 'pending', 'conflict', 'error',
                         'tested', 'syncing', 'connected'):
                result[key] = state
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def observed_mount_source(alias, *, mountinfo='/proc/self/mountinfo'):
    """Best-effort display of pre-existing mounts; may expose only the share root.

    Not used for authorization or mounting. Never assume mountinfo includes the
    complete prefix path when CIFS was mounted with a prefixpath option.
    """
    validate_alias(alias)
    try:
        for row in Path(mountinfo).read_text(encoding='utf-8').splitlines():
            left, separator, right = row.partition(' - ')
            if not separator:
                continue
            columns, fs = left.split(), right.split()
            if len(columns) < 5 or len(fs) < 2:
                continue
            mountpoint = columns[4].replace(r'\040', ' ')
            if mountpoint == '/sources/' + alias and fs[0] == 'cifs':
                return fs[1].replace(r'\040', ' ')
    except OSError:
        pass
    return None
