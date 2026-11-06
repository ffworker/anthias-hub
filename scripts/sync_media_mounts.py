#!/usr/bin/env python3
"""Root-owned host side SMB mount coordinator.

The web container never gets CAP_SYS_ADMIN, host paths or SMB passwords.
Only explicitly allowed SMB server/share pairs are eligible to mount.
The helper will NOT unmount or replace an existing mount automatically.
"""
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from app.media_sources import load_sources, split_unc, SourceError

ROOT = Path('/srv/anthias-sources')
DEFAULT_ALLOWLIST = Path('/etc/anthias-hub/smb-allowlist.json')


class MountError(RuntimeError):
    pass


def run(args, timeout=30):
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)


def allowed_shares(path=DEFAULT_ALLOWLIST):
    """The allowlist and credential references must be maintained by root."""
    if path.is_symlink() or not path.is_file():
        raise MountError('Root-Freigabeliste fehlt oder ist ein Symlink')
    st = path.stat()
    if st.st_uid != 0 or st.st_mode & 0o022:
        raise MountError('Root-Freigabeliste ist nicht geschützt')
    content = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(content.get('allowed_shares'), list):
        raise MountError('Ungültige Root-Freigabeliste')
    out = {}
    for rule in content['allowed_shares']:
        server, share, remainder = split_unc(f"//{rule['server']}/{rule['share']}")
        if remainder or (server, share) in out:
            raise MountError('Doppelte oder ungültige SMB-Freigabe')
        credential = Path(rule['credentials'])
        if (not credential.is_absolute() or credential.is_symlink()
                or not credential.is_file() or
                not credential.is_relative_to('/etc/anthias-hub/secrets/')):
            raise MountError('Ungültiger Credentials-Dateipfad')
        meta = credential.stat()
        if meta.st_uid != 0 or meta.st_mode & 0o077:
            raise MountError('SMB-Credentials müssen Root gehören und Modus 0600 haben')
        out[(server, share)] = credential
    return out


def ensure_directory(root, alias):
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid != 0:
        raise MountError('Quellen-Stammverzeichnis muss Root gehören und darf kein Symlink sein')
    target = root / alias
    if target.is_symlink():
        raise MountError('Quellen-Mountpoint darf kein Symlink sein')
    if not target.exists():
        target.mkdir(mode=0o755)
    if not target.is_dir() or target.stat().st_uid != 0:
        raise MountError('Quellen-Mountpoint muss ein Root-Verzeichnis sein')
    return target


def source_at(target):
    result = run(['findmnt', '-M', str(target), '-rn', '-o', 'SOURCE,FSTYPE'])
    if result.returncode:
        return None
    value = result.stdout.strip().split()
    if len(value) != 2:
        raise MountError('Mountpoint konnte nicht eindeutig geprüft werden')
    return value[0], value[1]


def reconcile_one(source, allowlist, root, *, allow_write=False):
    alias, unc = source['alias'], source['unc']
    server, share, _ = split_unc(unc)
    if (server, share) not in allowlist:
        return 'blocked'
    target = ensure_directory(root, alias)
    mounted = source_at(target)
    if mounted:
        found, fstype = mounted
        if fstype != 'cifs' or found.casefold() != unc.casefold():
            # Explicit manual intervention required: never automatically unmount
            # production network filesystems or switch them mid-playback.
            return 'conflict'
        return 'already-mounted'
    if any(target.iterdir()):
        return 'conflict'
    if not allow_write:
        return 'pending'
    credentials = allowlist[(server, share)]
    result = run([
        'mount', '-t', 'cifs', unc, str(target),
        '-o', f'credentials={credentials},ro,nosuid,nodev,noexec,vers=3.0,iocharset=utf8',
    ], timeout=60)
    if result.returncode:
        return 'error'
    return 'mounted' if source_at(target) == (unc, 'cifs') else 'error'


def write_status(path, states):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix='.media-mount-status-', mode='w',
            encoding='utf-8', delete=False,
        ) as f:
            temporary = Path(f.name)
            json.dump({'version': 1, 'sources': states}, f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, 0o644)  # Non-secret states readable by Hub UID
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', default='/root/apps/anthias-hub/data/media-sources.json')
    parser.add_argument('--status', default='/root/apps/anthias-hub/data/media-mount-status.json')
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--allowlist', default=str(DEFAULT_ALLOWLIST))
    parser.add_argument('--check', action='store_true', help='Validate only; do not mount')
    args = parser.parse_args()
    if os.geteuid() != 0:
        print('Dieser Dienst muss als Root laufen', file=sys.stderr)
        return 2
    try:
        allowlist = allowed_shares(Path(args.allowlist))
        sources = load_sources(Path(args.registry))
        results = {src['alias']: reconcile_one(src, allowlist, Path(args.root),
                                               allow_write=not args.check)
                   for src in sources}
        if not args.check:
            mapping = {src['alias']: src['unc'] for src in sources}
            write_status(Path(args.status), {
                alias: {'state': state,
                        'fingerprint': hashlib.sha256(mapping[alias].encode('utf-8')).hexdigest()}
                for alias, state in results.items()
            })
        for alias, state in results.items():
            print(f'{alias}: {state}')
        return 0 if all(state in ('already-mounted', 'mounted', 'pending') for state in results.values()) else 1
    except (OSError, ValueError, TypeError, MountError, SourceError, subprocess.TimeoutExpired) as exc:
        print('Medienquellen-Abgleich fehlgeschlagen:', str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
