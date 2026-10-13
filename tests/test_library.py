import io
import json
import zipfile
from pathlib import Path
import pytest
from app.library import Library, LibraryError


def test_create_url_and_portable_roundtrip(tmp_path):
    store = Library(tmp_path / 'source')
    collection = store.create('Bistro Start')
    store.add_url(collection['id'], 'News', 'https://example.org/news', 30)
    archive = store.export(collection['id'])
    target = Library(tmp_path / 'target')
    restored = target.import_zip(io.BytesIO(archive))
    assert restored['name'] == 'Bistro Start'
    assert restored['items'][0]['url'] == 'https://example.org/news'
    assert restored['items'][0]['duration'] == 30
    assert restored['id'] != collection['id']


def test_uploaded_media_are_persisted_and_included_in_export(tmp_path):
    store = Library(tmp_path / 'source')
    collection = store.create('Visuals')
    png = b'\x89PNG\r\n\x1a\n' + b'picture data'
    store.add_media(collection['id'], 'Menu', io.BytesIO(png), 'menu.png', 15)
    assert store.media_path(collection['id'], store.get(collection['id'])['items'][0]).read_bytes() == png
    archive = store.export(collection['id'])
    restored_store = Library(tmp_path / 'target')
    restored = restored_store.import_zip(io.BytesIO(archive))
    assert restored_store.media_path(restored['id'], restored['items'][0]).read_bytes() == png


def test_rejects_untrusted_zip_and_missing_media(tmp_path):
    store = Library(tmp_path / 'library')
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('../escape', 'no')
        z.writestr('manifest.json', json.dumps({'version': 1, 'name': 'X', 'items': []}))
    with pytest.raises(LibraryError):
        store.import_zip(io.BytesIO(data.getvalue()))
    assert not (tmp_path / 'escape').exists()

    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        z.writestr('manifest.json', json.dumps({'version': 1, 'name': 'X', 'items': [{'kind': 'media', 'name': 'X', 'duration': 15, 'file': 'media/missing.png'}]}))
    with pytest.raises(LibraryError):
        store.import_zip(io.BytesIO(data.getvalue()))
    assert store.list() == []


def test_rejects_oversize_and_unsupported_media(tmp_path):
    store = Library(tmp_path / 'library')
    item = store.create('X')
    with pytest.raises(LibraryError):
        store.add_media(item['id'], 'bad', io.BytesIO(b'garbage'), 'no.png', 15)
    with pytest.raises(LibraryError):
        store.add_media(item['id'], 'bad', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'a' * 101), 'no.png', 15, max_bytes=100)
    assert store.get(item['id'])['items'] == []
    with pytest.raises(LibraryError):
        store.add_media(item['id'], 'bad', io.BytesIO(b'\x89PNG\r\n\x1a\nvalid'), 'valid.png', 'not-a-number')


def test_template_items_can_be_reordered_without_changing_contents(tmp_path):
    store = Library(tmp_path / 'library')
    template = store.create('Sequence')
    store.add_url(template['id'], 'First', 'https://example.org/one', 15)
    store.add_url(template['id'], 'Second', 'https://example.org/two', 20)
    second = store.get(template['id'])['items'][1]['id']
    store.move(template['id'], second, 'up')
    assert [x['name'] for x in store.get(template['id'])['items']] == ['Second', 'First']


def test_export_refuses_tampered_media(tmp_path):
    store = Library(tmp_path / 'library')
    template = store.create('Photos')
    store.add_media(template['id'], 'Banner', io.BytesIO(b'\x89PNG\r\n\x1a\noriginal'), 'banner.png', 15)
    media = store.get(template['id'])['items'][0]
    store.media_path(template['id'], media).write_bytes(b'\x89PNG\r\n\x1a\nchanged')
    with pytest.raises(LibraryError):
        store.export(template['id'])


def test_import_rejects_non_object_manifest_without_crashing(tmp_path):
    store = Library(tmp_path / 'library')
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('manifest.json', '[]')
    with pytest.raises(LibraryError):
        store.import_zip(io.BytesIO(payload.getvalue()))
