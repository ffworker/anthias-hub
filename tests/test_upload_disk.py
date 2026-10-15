"""Exercise low-space failures and cleanup without filling a real filesystem."""
import errno
import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, request
from werkzeug.test import EnvironBuilder

from app.upload_disk import (DiskRequest, GuardedTemporaryFile, HubStorageFull,
                             HUB_RESERVE_BYTES, guarded_write, validate_temp_directory)
from app.library import Library


def free_bytes(value):
    return patch('app.upload_disk.shutil.disk_usage', return_value=SimpleNamespace(free=value))


def test_guard_never_consumes_reserve_and_closes_stream():
    with GuardedTemporaryFile() as stream:
        with free_bytes(HUB_RESERVE_BYTES + 3):
            with pytest.raises(HubStorageFull):
                stream.write(b'four')
        assert stream.tell() == 0
        with free_bytes(HUB_RESERVE_BYTES + 4):
            assert stream.write(b'four') == 4
    assert stream.closed


def test_unknown_disk_capacity_fails_closed():
    with GuardedTemporaryFile() as stream:
        with patch('app.upload_disk.shutil.disk_usage', side_effect=OSError('unavailable')):
            with pytest.raises(HubStorageFull):
                stream.write(b'test')
        assert stream.tell() == 0


@pytest.mark.parametrize('code', [errno.ENOSPC, errno.EDQUOT])
def test_external_disk_full_or_quota_has_controlled_error(code):
    class FullFile:
        def fileno(self):
            return 1
        def write(self, data):
            raise OSError(code, 'disk full')
    with free_bytes(2 * HUB_RESERVE_BYTES):
        with pytest.raises(HubStorageFull):
            guarded_write(FullFile(), b'data')


def test_failed_multipart_parse_closes_all_opened_files():
    builder = EnvironBuilder(method='POST', data={'media': (io.BytesIO(b'x' * 100000), 'x.mp4')})
    req = DiskRequest(builder.get_environ())
    try:
        with free_bytes(0), pytest.raises(HubStorageFull):
            req.files
        streams = req.__dict__['_upload_streams']
        assert streams
        req.close()
        assert all(stream.closed for stream in streams)
    finally:
        req.close()
        builder.close()


def test_library_full_disk_cleans_partial_and_keeps_manifest(tmp_path):
    library = Library(tmp_path)
    item = library.create('Test')
    with free_bytes(0), pytest.raises(HubStorageFull):
        library.add_media(item['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'photo.png', 10)
    assert library.get(item['id'])['items'] == []
    assert list((tmp_path / item['id'] / 'media').iterdir()) == []


def test_explicit_missing_tmpdir_does_not_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv('TMPDIR', str(tmp_path / 'missing'))
    with pytest.raises(RuntimeError, match='refusing fallback'):
        validate_temp_directory()


def test_multipart_is_disk_backed_even_for_small_files():
    app = Flask(__name__)
    app.request_class = DiskRequest
    @app.post('/')
    def accept():
        stream = request.files['media'].stream
        assert isinstance(stream, GuardedTemporaryFile)
        return stream.read()
    with app.test_client() as client:
        assert client.post('/', data={'media': (io.BytesIO(b'hello'), 'x.mp4')}).data == b'hello'


def test_export_and_restore_disk_failure_cleanup(tmp_path):
    library = Library(tmp_path)
    item = library.create('Test')
    library.add_media(item['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'photo.png', 10)
    with free_bytes(0), pytest.raises(HubStorageFull):
        library.export_file(item['id'])
    archive = library.export(item['id'])
    with free_bytes(0), pytest.raises(HubStorageFull):
        library.import_zip(io.BytesIO(archive))
    assert len(library.list()) == 1
    assert not list(tmp_path.glob('.restore-*'))


def test_export_cannot_create_backup_larger_than_restore_limit(tmp_path, monkeypatch):
    library = Library(tmp_path)
    item = library.create('Test')
    library.add_media(item['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\n'), 'photo.png', 10)
    from app.library import LibraryError
    monkeypatch.setattr('app.library.MAX_ARCHIVE', 1)
    with pytest.raises(LibraryError, match='nicht importierbar'):
        library.export_file(item['id'])


def test_hub_returns_507_json_before_csrf_parse_can_fill_disk():
    from app.web import create_app
    app = create_app({'TESTING': True, 'SECRET_KEY': 's' * 48})
    with app.test_client() as client, free_bytes(0):
        response = client.post('/login', data={'media': (io.BytesIO(b'hi'), 'x.mp4')},
                               headers={'Accept': 'application/json'})
    assert response.status_code == 507
    assert response.json['ok'] is False
    assert 'Hub-Speicher' in response.json['error']


def test_full_disk_while_opening_spool_is_controlled():
    with patch('app.upload_disk.tempfile.TemporaryFile', side_effect=OSError(errno.ENOSPC, 'full')):
        with pytest.raises(HubStorageFull):
            GuardedTemporaryFile()


def test_export_manifest_respects_restore_limit(tmp_path):
    from app.library import LibraryError
    library = Library(tmp_path)
    item = library.create('Long URLs')
    for index in range(50):
        library.add_url(item['id'], f'URL {index}', 'https://example.org/' + 'a' * 2000, 10)
    with pytest.raises(LibraryError, match='100000 Bytes'):
        library.export_file(item['id'])
