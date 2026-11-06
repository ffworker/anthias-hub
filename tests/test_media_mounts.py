"""Offline root mount helper tests. Never issue actual mount/unmount commands."""
from pathlib import Path
from types import SimpleNamespace

from scripts import sync_media_mounts as coordinator


def test_new_approved_source_is_mounted_read_only_without_shell(monkeypatch, tmp_path):
    target = tmp_path / 'bistro'
    target.mkdir()
    unc = '//10.12.0.4/files$/Marketing/Bistro'
    source = {'alias': 'bistro', 'unc': unc}
    allowlist = {('10.12.0.4', 'files$'): Path('/etc/anthias-hub/secrets/marketing.smb')}
    monkeypatch.setattr(coordinator, 'ensure_directory', lambda root, alias: target)
    calls = []
    times = iter([None, (unc, 'cifs')])
    monkeypatch.setattr(coordinator, 'source_at', lambda _: next(times))
    def run(args, timeout=30):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(coordinator, 'run', run)
    assert coordinator.reconcile_one(source, allowlist, tmp_path, allow_write=True) == 'mounted'
    assert len(calls) == 1
    assert calls[0][:5] == ['mount', '-t', 'cifs', unc, str(target)]
    assert 'ro,nosuid,nodev,noexec' in calls[0][-1]
    assert 'credentials=/etc/anthias-hub/secrets/marketing.smb' in calls[0][-1]


def test_unapproved_source_never_calls_mount(monkeypatch, tmp_path):
    monkeypatch.setattr(coordinator, 'run', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('mount called')))
    source = {'alias': 'bistro', 'unc': '//10.12.0.5/files$/Marketing/Bistro'}
    assert coordinator.reconcile_one(source, {}, tmp_path, allow_write=True) == 'blocked'


def test_existing_different_mount_never_unmounted_or_replaced(monkeypatch, tmp_path):
    target = tmp_path / 'bistro'
    target.mkdir()
    monkeypatch.setattr(coordinator, 'ensure_directory', lambda root, alias: target)
    monkeypatch.setattr(coordinator, 'source_at', lambda _: ('//10.12.0.4/files$/OLD', 'cifs'))
    monkeypatch.setattr(coordinator, 'run', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('mount called')))
    source = {'alias': 'bistro', 'unc': '//10.12.0.4/files$/NEW'}
    allowed = {('10.12.0.4', 'files$'): Path('/etc/anthias-hub/secrets/marketing.smb')}
    assert coordinator.reconcile_one(source, allowed, tmp_path, allow_write=True) == 'conflict'


def test_mount_status_is_root_side_and_expires(tmp_path, monkeypatch):
    import time
    from app.media_sources import save_source, mount_statuses
    registry = tmp_path / 'reg.json'
    status = tmp_path / '.mount-status.json'
    unc = '//10.12.0.4/files$/Bistro'
    save_source('bistro', unc, path=registry)
    coordinator.write_status(status, {
        'bistro': {'state': 'already-mounted',
                   'fingerprint': __import__('hashlib').sha256(unc.encode()).hexdigest()}
    })
    assert mount_statuses(status, registry)['bistro'] == 'already-mounted'
    instant = time.time()
    monkeypatch.setattr('app.media_sources.time.time', lambda: instant + 600)
    assert mount_statuses(status, registry) == {}
