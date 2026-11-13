"""Offline DEV SMB UI tests: no external SMB server or production mounts."""
import io
import json
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import smb_ui
from app.media_sources import save_source, mount_statuses
from app.folder_sync import default_library_folders, source_directory


PNG = b'\x89PNG\r\n\x1a\n' + b'dev image bytes'


class Entry:
    def __init__(self, name, *, directory=False, content=b''):
        self.name = name
        self.directory = directory
        self.content = content

    def is_dir(self):
        return self.directory

    def is_file(self):
        return not self.directory

    def is_symlink(self):
        return False

    def stat(self):
        return SimpleNamespace(st_size=len(self.content),
                               st_mtime=1700000000,
                               st_mtime_ns=1700000000 * 1000000000)


class FakeSMB:
    def __init__(self):
        self.rejected = False
        self.variant = 1
        self.sessions = 0
        self.bytes = PNG

    @contextmanager
    def scandir(self, path, **options):
        assert options['encrypt'] is True
        assert options['username'] == 'DOMAIN' + chr(92) + 'reader'
        assert options['password'] == 'example-password'
        if self.rejected:
            raise PermissionError('STATUS_LOGON_FAILURE')
        self.sessions += 1
        part = path.split(chr(92))[-1]
        if part == 'Bistro':
            yield iter([Entry('banner.png', content=self.bytes),
                        Entry('ignored.txt', content=b'junk')])
        elif part == 'Andere':
            yield iter([Entry('second.png', content=self.bytes)])
        else:
            yield iter([Entry('Bistro' if self.variant == 1 else 'Andere',
                              directory=True)])

    def open_file(self, path, mode='rb', **options):
        assert mode == 'rb'
        assert options['encrypt'] is True
        return io.BytesIO(self.bytes)

    def reset_connection_cache(self):
        pass


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv('DEV_SMB_UI', '1')
    monkeypatch.setenv('APP_SECRET_KEY', 'X' * 48)
    monkeypatch.setenv('MEDIA_SOURCES_FILE', str(tmp_path / 'sources.json'))
    monkeypatch.setenv('MEDIA_MOUNT_STATUS_FILE', str(tmp_path / 'smb-status.json'))
    monkeypatch.setenv('DEV_SMB_CREDENTIALS_FILE', str(tmp_path / 'credentials.bin'))
    monkeypatch.setenv('DEV_SMB_TRIGGER_FILE', str(tmp_path / 'trigger.txt'))
    monkeypatch.setenv('DEV_SMB_MIRROR_INDEX', str(tmp_path / 'mirror-index.json'))
    root = tmp_path / 'cache'
    root.mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('FOLDER_REQUIRE_MOUNT', '0')
    monkeypatch.setenv('FOLDER_REQUIRE_VERIFIED', '1')
    smb = FakeSMB()
    monkeypatch.setattr(smb_ui, '_smb', lambda: smb)
    return root, smb, tmp_path


def connect(path):
    record, folders = smb_ui.test_connection(
        path, 'reader', 'example-password', 'DOMAIN')
    save_source('default', record['unc'])
    smb_ui.store_credentials(record)
    smb_ui.write_status('tested', record['unc'], record['revision'],
                        folders=len(folders))
    smb_ui.request_sync()
    return record, folders


def test_web_credentials_are_encrypted_and_mirror_produces_verified_sources(sandbox):
    root, smb, temporary = sandbox
    unc = '//10.10.0.4/files$/Marketing/Screens'
    record, folders = connect(unc)
    assert folders == ['Bistro']
    raw = (temporary / 'credentials.bin').read_bytes()
    assert b'example-password' not in raw
    assert b'reader' not in raw
    assert (temporary / 'credentials.bin').stat().st_mode & 0o777 == 0o600
    assert (temporary / 'trigger.txt').exists()
    assert mount_statuses().get('default') == 'tested'
    with pytest.raises(Exception):
        source_directory('default/Bistro')  # not copied yet
    assert smb_ui.mirror_cycle()['copied'] == 1
    assert (root / 'default' / 'Bistro' / 'banner.png').read_bytes() == PNG
    assert mount_statuses().get('default') == 'connected'
    assert default_library_folders() == ['Bistro']
    assert source_directory('default/Bistro') == root / 'default' / 'Bistro'
    assert smb_ui.safe_status()['sources']['default']['done'] == 1
    assert 'password' not in json.dumps(smb_ui.safe_status()).lower()
    assert smb_ui.mirror_cycle()['copied'] == 0
    assert smb_ui.safe_status()['sources']['default']['files'] == 1


def test_failed_login_does_not_replace_saved_credentials_or_trust_old_cache(sandbox):
    _, smb, temporary = sandbox
    old, _ = connect('//10.10.0.4/files$/Old')
    token = (temporary / 'credentials.bin').read_bytes()
    smb.rejected = True
    with pytest.raises(smb_ui.SMBSetupError, match='Anmeldung'):
        smb_ui.test_connection('//10.10.0.4/files$/Wrong',
                               'reader', 'example-password', 'DOMAIN')
    assert (temporary / 'credentials.bin').read_bytes() == token
    assert smb_ui._get_credentials()['revision'] == old['revision']


def test_source_switch_never_leaves_old_source_files_visible(sandbox):
    root, smb, _ = sandbox
    connect('//10.10.0.4/files$/Old')
    assert smb_ui.mirror_cycle()['copied'] == 1
    smb.variant = 2
    connect('//10.10.0.4/files$/Different')
    assert smb_ui.mirror_cycle()['copied'] == 1
    assert (root / 'default' / 'Andere' / 'second.png').exists()
    assert not (root / 'default' / 'Bistro').exists()
    assert default_library_folders() == ['Andere']


def test_share_outage_preserves_last_good_files_and_blocks_new_publication(sandbox):
    root, smb, _ = sandbox
    connect('//10.10.0.4/files$/Old')
    smb_ui.mirror_cycle()
    smb.rejected = True
    assert 'error' in smb_ui.mirror_cycle()
    assert (root / 'default' / 'Bistro' / 'banner.png').exists()
    assert mount_statuses().get('default') == 'error'
    with pytest.raises(Exception):
        source_directory('default/Bistro')


def test_large_share_moves_in_multiple_automatic_batches_without_redownloading(
        sandbox, monkeypatch):
    """A share larger than the 4GiB *batch budget* must not fail."""
    from app.source_progress import describe_sources
    root, smb, work = sandbox
    budget = len(PNG) * 2
    monkeypatch.setattr(smb_ui, 'MAX_BYTES_PER_CYCLE', budget)

    @contextmanager
    def many_scandir(path, **options):
        assert options['encrypt'] is True
        if path.endswith(chr(92) + 'Bistro'):
            yield iter([Entry('a.png', content=PNG),
                        Entry('b.png', content=PNG),
                        Entry('c.png', content=PNG)])
        else:
            yield iter([Entry('Bistro', directory=True)])

    smb.scandir = many_scandir
    unc = '//10.10.0.4/files$/Marketing/Large'
    record, _ = connect(unc)

    first = smb_ui.mirror_cycle()
    assert first['copied'] == 2
    assert first['pending'] == 1
    state = smb_ui.safe_status()['sources']['default']
    assert state['state'] == 'syncing'
    assert state['files'] == 3
    assert state['done'] == 2
    assert state['total_bytes'] == len(PNG) * 3
    assert not (root / 'default' / 'Bistro' / 'a.png').exists()
    assert (root / ('.default-stage-' + record['revision']) /
            'Bistro' / 'a.png').exists()
    assert not (work / 'mirror-index.json').exists()
    assert (work / 'mirror-index.json.pending').exists()
    assert mount_statuses().get('default') == 'syncing'
    display = describe_sources(
        work / 'sources.json', work / 'smb-status.json', [], root)[0]
    assert '2 von 3 Medien' in display['stages'][2]['detail']
    assert display['stages'][2]['state'] == 'waiting'
    assert display['stages'][3]['state'] == 'waiting'
    assert '10000' not in display['stages'][2]['detail']

    # Fresh function invocation uses only persisted state, emulating a
    # container restart. Already downloaded media are not transferred again.
    second = smb_ui.mirror_cycle()
    assert second['copied'] == 1
    assert second['pending'] == 0
    assert (root / 'default' / 'Bistro' / 'a.png').read_bytes() == PNG
    assert (root / 'default' / 'Bistro' / 'b.png').read_bytes() == PNG
    assert (root / 'default' / 'Bistro' / 'c.png').read_bytes() == PNG
    assert not (work / 'mirror-index.json.pending').exists()
    assert smb_ui.safe_status()['sources']['default']['state'] == 'connected'
    assert smb_ui.mirror_cycle()['copied'] == 0

    # Re-entering valid credentials for the *same UNC* does not trigger a
    # full 4GiB re-download or duplicate the mirror.
    connect(unc)
    assert smb_ui.mirror_cycle()['copied'] == 0


def test_source_switch_preserves_previous_active_share_until_full_batch_sync(
        sandbox, monkeypatch):
    root, smb, _ = sandbox
    connect('//10.10.0.4/files$/Original')
    assert smb_ui.mirror_cycle()['pending'] == 0
    assert (root / 'default' / 'Bistro' / 'banner.png').exists()
    monkeypatch.setattr(smb_ui, 'MAX_BYTES_PER_CYCLE', len(PNG))
    @contextmanager
    def many_scandir(path, **options):
        if path.endswith(chr(92) + 'Andere'):
            yield iter([Entry('a.png', content=PNG), Entry('b.png', content=PNG)])
        else:
            yield iter([Entry('Andere', directory=True)])
    smb.scandir = many_scandir
    record, _ = connect('//10.10.0.4/files$/Changed')
    first = smb_ui.mirror_cycle()
    assert first['pending'] == 1
    assert (root / 'default' / 'Bistro' / 'banner.png').exists()
    assert not (root / 'default' / 'Andere').exists()
    assert (root / ('.default-stage-' + record['revision']) / 'Andere' / 'a.png').exists()
    assert smb_ui.mirror_cycle()['pending'] == 0
    assert (root / 'default' / 'Andere' / 'b.png').exists()
    assert not (root / 'default' / 'Bistro').exists()
