"""Folder-backed template import: safe, additive, independent of Pi playlists."""
import io
import pytest
from app.library import Library, LibraryError
from app.folder_sync import source_directory, sync_template, sync_all


PNG = b'\x89PNG\r\n\x1a\n' + b'valid image bytes'


def test_folder_binding_and_incremental_import(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    folder = root / 'bistro'
    folder.mkdir(parents=True)
    (folder / 'a.png').write_bytes(PNG)
    store = Library(tmp_path / 'library')
    template = store.create('Bistro')
    store.add_url(template['id'], 'Manual', 'https://example.org', 20)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store.set_folder_source(template['id'], 'bistro')
    assert sync_template(store, template['id'])['added'] == 1
    assert sync_template(store, template['id'])['skipped'] == 1
    entries = store.get(template['id'])['items']
    assert len(entries) == 2 and entries[0]['kind'] == 'url'
    assert store.verified_media_path(template['id'], entries[1]).read_bytes() == PNG

    (folder / 'a.png').write_bytes(PNG + b'new')
    assert sync_template(store, template['id'])['updated'] == 1
    items = store.get(template['id'])['items']
    assert len(items) == 2 and items[0]['name'] == 'Manual'
    assert store.verified_media_path(template['id'], items[1]).read_bytes() == PNG + b'new'

    (folder / 'a.png').unlink()
    assert sync_template(store, template['id'])['added'] == 0
    assert len(store.get(template['id'])['items']) == 2  # no automatic deletion


def test_reject_path_traversal_and_symlinks(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    root.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(tmp_path / 'library')
    ident = store.create('Template')['id']
    for alias in ('../outside', '/etc', 'nested/name', 'escape'):
        with pytest.raises(LibraryError):
            store.set_folder_source(ident, alias)
    assert 'folder_source' not in store.get(ident)


def test_invalid_media_and_missing_mount_do_not_remove_existing(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    folder = root / 'bistro'
    folder.mkdir(parents=True)
    (folder / 'bad.png').write_bytes(b'not a png')
    store = Library(tmp_path / 'library')
    ident = store.create('Template')['id']
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store.set_folder_source(ident, 'bistro')
    with pytest.raises(LibraryError):
        sync_template(store, ident)
    assert store.get(ident)['items'] == []
    store.add_media(ident, 'Manual', io.BytesIO(PNG), 'manual.png', 15)
    folder.rename(root / 'offline')
    with pytest.raises(LibraryError):
        sync_template(store, ident)
    assert len(store.get(ident)['items']) == 1


def test_sync_all_scopes_only_bound_templates(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    (root / 'bistro').mkdir(parents=True)
    (root / 'bistro' / 'banner.png').write_bytes(PNG)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(tmp_path / 'library')
    a = store.create('Bound')
    b = store.create('Manual')
    store.set_folder_source(a['id'], 'bistro')
    assert list(sync_all(library_dir=str(store.root))) == [a['id']]
    assert len(store.get(b['id'])['items']) == 0


def test_mount_guard_prevents_empty_unmounted_folder_being_seen_as_healthy(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    (root / 'bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('FOLDER_REQUIRE_MOUNT', '1')
    with pytest.raises(LibraryError, match='nicht eingehängt'):
        source_directory('bistro')
    monkeypatch.setattr('app.folder_sync.os.path.ismount', lambda path: True)
    assert source_directory('bistro') == root / 'bistro'


def test_default_library_discovers_only_safe_direct_children(tmp_path, monkeypatch):
    from app.folder_sync import available_sources, default_library_folders
    root = tmp_path / 'sources'
    default = root / 'default'
    default.mkdir(parents=True)
    (default / 'Demo-Screen-A').mkdir()
    (default / 'Empfang Nord').mkdir()
    (default / '.private').mkdir()
    (default / 'hidden.txt').write_text('not a directory')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (default / 'linked').symlink_to(outside, target_is_directory=True)
    (root / 'oldbistro').mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))

    assert default_library_folders() == ['Demo-Screen-A', 'Empfang Nord']
    assert available_sources() == [
        'oldbistro', 'default/Demo-Screen-A', 'default/Empfang Nord'
    ]
    assert source_directory('default/Empfang Nord') == default / 'Empfang Nord'
    for bad in ('default/../outside', 'default/link', 'default/.private',
                'default/linked', 'default/Empfang Nord/secret',
                'default/../../etc', 'default//etc', 'default/'):
        with pytest.raises(LibraryError):
            source_directory(bad)


def test_default_library_parent_mount_check_not_each_child(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    base = root / 'default'
    (base / 'Bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('FOLDER_REQUIRE_MOUNT', '1')
    seen = []
    def ismount(path):
        seen.append(str(path))
        return Path(path) == base
    from pathlib import Path
    monkeypatch.setattr('app.folder_sync.os.path.ismount', ismount)
    assert source_directory('default/Bistro') == base / 'Bistro'
    assert seen == [str(base)]


def test_default_library_child_import_and_retain_duration(tmp_path, monkeypatch):
    root = tmp_path / 'sources'
    bistro = root / 'default' / 'Demo-Screen-A'
    bistro.mkdir(parents=True)
    (bistro / 'banner.png').write_bytes(PNG)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(tmp_path / 'library')
    ident = store.create('Bistro')['id']
    store.set_folder_source(ident, 'default/Demo-Screen-A')
    assert sync_template(store, ident)['added'] == 1
    item = store.get(ident)['items'][0]
    store.update_item_duration(ident, item['id'], '38')
    (bistro / 'banner.png').write_bytes(PNG + b'new')
    assert sync_template(store, ident)['updated'] == 1
    modified = store.get(ident)['items'][0]
    assert modified['id'] == item['id']
    assert modified['duration'] == 38
    assert store.get(ident)['folder_source'] == 'default/Demo-Screen-A'
