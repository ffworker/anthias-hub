"""IT SMB source registry, security boundaries, mount health contract."""
import hashlib
import json
import time

import pytest

from app.media_sources import (
    SourceError, load_sources, save_source, remove_source, retired_aliases,
    validate_alias, validate_unc, split_unc, mount_statuses,
)


def test_smb_unc_parsing_and_aliases():
    unc = r'\\10.12.0.4\files$\Marketing\Screens\Bistro'
    canonical = '//10.12.0.4/files$/Marketing/Screens/Bistro'
    assert validate_unc(unc) == canonical
    assert split_unc(unc) == ('10.12.0.4', 'files$', 'Marketing/Screens/Bistro')
    assert validate_alias('empfang') == 'empfang'
    for alias in ('../escape', '/etc', 'x/y', 'x.y', ''):
        with pytest.raises(SourceError):
            validate_alias(alias)
    for invalid in (
        '', 'https://10.12.0.4/files$', '//127.0.0.1/share',
        '//8.8.8.8/share', '//10.12.0.4/share/../../etc',
        '//10.12.0.4/share//another', '//10.12.0.4/share/dir?key=bad',
        '//10.12.0.4/share/dir:bad', '//10.12.0.4/share/',
        '//10.12.0.4/share/dir ', '//10.12.0.4/share/dir/..',
        '//10.12.0.4/share/dir\\',
    ):
        with pytest.raises(SourceError):
            validate_unc(invalid)


def test_source_registry_is_atomic_and_never_stores_credentials(tmp_path):
    registry = tmp_path / 'media-sources.json'
    assert load_sources(registry) == []
    assert save_source('bistro', '//10.12.0.4/files$/News', path=registry) == 'created'
    assert (registry.stat().st_mode & 0o777) == 0o600
    assert save_source('bistro', '//10.12.0.4/files$/News', path=registry) == 'unchanged'
    assert save_source('bistro', '//10.12.0.4/files$/Current', path=registry) == 'updated'
    assert save_source('empfang', '//10.12.0.4/files$/Reception', path=registry) == 'created'
    assert load_sources(registry) == [
        {'alias': 'bistro', 'unc': '//10.12.0.4/files$/Current'},
        {'alias': 'empfang', 'unc': '//10.12.0.4/files$/Reception'},
    ]
    assert 'password' not in registry.read_text().lower()
    registry.write_text('not json')
    with pytest.raises(SourceError, match='beschädigt'):
        load_sources(registry)


def test_mount_status_must_match_current_saved_path(tmp_path):
    registry = tmp_path / 'sources.json'
    status = tmp_path / 'mounts.json'
    unc = '//10.12.0.4/files$/Current'
    save_source('bistro', unc, path=registry)
    status.write_text(json.dumps({'checked_at': time.time(), 'sources': {
        'bistro': {'state': 'already-mounted',
                   'fingerprint': hashlib.sha256(unc.encode()).hexdigest()}
    }}))
    assert mount_statuses(status, registry) == {'bistro': 'already-mounted'}
    save_source('bistro', '//10.12.0.4/files$/Next', path=registry)
    assert mount_statuses(status, registry) == {'bistro': 'pending'}
    status.write_text(json.dumps({'checked_at': time.time(), 'sources': {
        'bistro': {'state': 'already-mounted', 'fingerprint': 'invalid'}
    }}))
    assert mount_statuses(status, registry) == {'bistro': 'pending'}


def test_folder_guard_denies_edited_but_unverified_smb_path(tmp_path, monkeypatch):
    from app.folder_sync import source_directory
    from app.library import LibraryError
    root = tmp_path / 'sources'
    (root / 'bistro').mkdir(parents=True)
    reg = tmp_path / 'registry.json'
    state = tmp_path / 'state.json'
    save_source('bistro', '//10.12.0.4/files$/One', path=reg)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('MEDIA_SOURCES_FILE', str(reg))
    monkeypatch.setenv('MEDIA_MOUNT_STATUS_FILE', str(state))
    monkeypatch.setenv('FOLDER_REQUIRE_VERIFIED', '1')
    with pytest.raises(LibraryError, match='Host bestätigt'):
        source_directory('bistro')
    state.write_text(json.dumps({'checked_at': time.time(), 'sources': {
        'bistro': {'state': 'mounted',
                   'fingerprint': hashlib.sha256('//10.12.0.4/files$/One'.encode()).hexdigest()}
    }}))
    assert source_directory('bistro') == root / 'bistro'
    save_source('bistro', '//10.12.0.4/files$/Two', path=reg)
    with pytest.raises(LibraryError, match='Host bestätigt'):
        source_directory('bistro')


def test_retiring_alias_is_atomic_hides_it_and_does_not_touch_host(tmp_path):
    registry = tmp_path / 'sources.json'
    mount = tmp_path / 'sources' / 'bistro'
    mount.mkdir(parents=True)
    (mount / 'still-on-host.txt').write_text('preserve me')
    unc = '//10.12.0.4/files$/Marketing/Bistro'
    save_source('bistro', unc, path=registry)

    assert remove_source('bistro', path=registry) == 'retired'
    assert load_sources(registry) == []
    assert retired_aliases(registry) == ['bistro']
    assert (registry.stat().st_mode & 0o777) == 0o600
    assert (mount / 'still-on-host.txt').read_text() == 'preserve me'
    with pytest.raises(SourceError, match='nicht'):
        remove_source('bistro', path=registry)

    # Re-registering a retired alias is an explicit operator action.
    assert save_source('bistro', unc, path=registry) == 'created'
    assert retired_aliases(registry) == []
    assert load_sources(registry)[0]['alias'] == 'bistro'


def test_retired_alias_persists_across_other_source_updates(tmp_path):
    registry = tmp_path / 'sources.json'
    save_source('old', '//10.12.0.4/files$/Old', path=registry)
    save_source('other', '//10.12.0.4/files$/Other', path=registry)
    remove_source('old', path=registry)
    save_source('other', '//10.12.0.4/files$/New', path=registry)
    save_source('new', '//10.12.0.4/files$/New2', path=registry)
    assert retired_aliases(registry) == ['old']
    assert [s['alias'] for s in load_sources(registry)] == ['new', 'other']

    bad = json.loads(registry.read_text())
    bad['retired'] = ['../escape']
    registry.write_text(json.dumps(bad))
    with pytest.raises(SourceError, match='beschädigt'):
        retired_aliases(registry)
