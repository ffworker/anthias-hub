"""Offline Marketing bulk import tests; no physical Anthias player touched."""
import io
import json
import stat
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.anthias import PlayerError
from app.library import Library
from app.web import create_app


PNG = b'\x89PNG\r\n\x1a\n' + b'valid-image'
MP4 = b'\x00\x00\x00\x18ftypisom' + b'valid-video'
JSON = {'Accept': 'application/json'}


class FakePlayer:
    changes = []
    preflight = 0
    fail_name = ''
    current = [{'asset_id': 'already', 'name': 'Keep Me',
                'uri': 'https://example.org/existing', 'mimetype': 'webpage',
                'is_enabled': True, 'duration': 25}]

    def __init__(self, device):
        self.device = device

    def assets(self):
        type(self).preflight += 1
        return list(type(self).current)

    def upload(self, stream, filename, mimetype):
        type(self).changes.append(('upload', filename, mimetype, stream.read()))
        if filename == type(self).fail_name:
            raise PlayerError('Player meldet Upload-Fehler')
        return {'uri': '/data/assets/' + filename, 'ext': Path(filename).suffix}

    def create(self, name, uri, duration, mimetype=None, ext=None):
        type(self).changes.append(('create', name, uri, duration, mimetype, ext))


@pytest.fixture
def env(tmp_path):
    users = tmp_path / 'users.json'
    users.write_text(json.dumps({'users': [
        {'username': name, 'role': name,
         'password_hash': generate_password_hash('password-123-safe', method='scrypt')}
        for name in ('marketing', 'viewer', 'it')
    ]}))
    devices = tmp_path / 'devices.json'
    devices.write_text(json.dumps({'devices': [
        {'id': 'lab', 'name': 'Test Display', 'url': 'http://192.168.1.19',
         'location': 'Test'}]}))
    app = create_app({'TESTING': True, 'SECRET_KEY': 'x' * 48,
                      'SESSION_COOKIE_SECURE': False,
                      'USERS_FILE': str(users),
                      'DEVICES_FILE': str(devices),
                      'AUDIT_FILE': str(tmp_path / 'audit.jsonl'),
                      'LIBRARY_DIR': str(tmp_path / 'library')})
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Marketing')
    FakePlayer.changes = []
    FakePlayer.preflight = 0
    FakePlayer.fail_name = ''
    with patch('app.web.Anthias', FakePlayer):
        yield app, app.test_client(), lib, template


def csrf(client):
    with client.session_transaction() as session:
        return session['csrf']


def login(client, role='marketing'):
    client.get('/login')
    response = client.post('/login', data={
        'csrf': csrf(client), 'username': role, 'password': 'password-123-safe'})
    assert response.status_code == 302


def archive(entries, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as output:
        for name, data in entries:
            output.writestr(name, data)
    return buffer.getvalue()


def submit_zip(client, path, data, **extra):
    return client.post(path, data={
        'csrf': csrf(client), 'duration': '15',
        'media': (io.BytesIO(data), 'photos.zip'), **extra,
    }, content_type='multipart/form-data', headers=JSON)


def test_ordinary_zip_imports_images_and_videos_into_library(env):
    _, client, lib, template = env
    login(client)
    result = submit_zip(client, f"/library/{template['id']}/bulk-media",
                        archive([('Folder/Lunch.png', PNG), ('Folder/Spot.mp4', MP4)]))
    assert result.status_code == 200
    assert result.json['ok'] is True
    assert result.json['imported'] == 2
    assert result.json['failed'] == 0
    assert [row['name'] for row in result.json['results']] == [
        'Folder/Lunch.png', 'Folder/Spot.mp4']
    items = lib.get(template['id'])['items']
    assert [item['name'] for item in items] == ['Lunch', 'Spot']
    assert [item['duration'] for item in items] == [15, 0]
    assert [lib.verified_media_path(template['id'], item).read_bytes() for item in items] == [PNG, MP4]


def test_multi_select_reports_bad_media_without_losing_good_import(env):
    _, client, lib, template = env
    login(client)
    response = client.post(f"/library/{template['id']}/bulk-media",
                           data={'csrf': csrf(client), 'duration': '22',
                                 'media': [(io.BytesIO(PNG), 'good.png'),
                                           (io.BytesIO(b'garbage'), 'bad.jpg'),
                                           (io.BytesIO(MP4), 'promo.mp4')]},
                           content_type='multipart/form-data', headers=JSON)
    assert response.status_code == 200
    assert response.json['partial'] is True
    assert (response.json['imported'], response.json['failed']) == (2, 1)
    assert response.json['results'][1]['status'] == 'failed'
    assert [i['name'] for i in lib.get(template['id'])['items']] == ['good', 'promo']


def test_zip_unsupported_entry_is_reported_and_does_not_abort(env):
    _, client, lib, template = env
    login(client)
    response = submit_zip(client, f"/library/{template['id']}/bulk-media",
                          archive([('notes.txt', b'Hello'), ('picture.png', PNG)]))
    assert response.status_code == 200
    assert response.json['imported'] == 1
    assert response.json['failed'] == 1
    assert len(lib.get(template['id'])['items']) == 1


@pytest.mark.parametrize('bad_path', [
    '../outside.png', '/absolute.png', 'C:/windows.png',
    'folder\\evil.png', 'folder/../../escape.png',
    './relative.png', 'folder//weird.png',
])
def test_rejects_zip_path_traversal_or_ambiguous_separators_before_writes(env, bad_path):
    _, client, lib, template = env
    login(client)
    result = submit_zip(client, f"/library/{template['id']}/bulk-media",
                        archive([('okay.png', PNG), (bad_path, PNG)]))
    assert result.status_code == 422
    assert result.json['results'] == []
    assert not lib.get(template['id'])['items']


def test_rejects_zip_symlinks_and_encrypted_flags(env):
    _, client, lib, template = env
    login(client)
    member = zipfile.ZipInfo('link.png')
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zf:
        zf.writestr('valid.png', PNG)
        zf.writestr(member, '../target')
    result = submit_zip(client, f"/library/{template['id']}/bulk-media", output.getvalue())
    assert result.status_code == 422
    assert not lib.get(template['id'])['items']


def test_rejects_zip_bomb_before_importing_small_legitimate_file(env):
    _, client, lib, template = env
    login(client)
    result = submit_zip(client, f"/library/{template['id']}/bulk-media",
                        archive([('safe.png', PNG), ('bomb.png', b'\0' * 2000000)]))
    assert result.status_code == 422
    assert not lib.get(template['id'])['items']


def test_rejects_duplicate_entries_and_excess_count(env):
    _, client, lib, template = env
    login(client)
    with pytest.warns(UserWarning):
        duplicate = archive([('A.png', PNG), ('A.png', PNG)])
    result = submit_zip(client, f"/library/{template['id']}/bulk-media", duplicate)
    assert result.status_code == 422
    many = archive([(f'{i}.png', PNG) for i in range(21)])
    result = submit_zip(client, f"/library/{template['id']}/bulk-media", many)
    assert result.status_code == 422
    assert not lib.get(template['id'])['items']


def test_rejects_corrupt_zip_and_mixed_zip_selection(env):
    _, client, lib, template = env
    login(client)
    route = f"/library/{template['id']}/bulk-media"
    result = submit_zip(client, route, b'not a real zip')
    assert result.status_code == 422
    result = client.post(route, data={
        'csrf': csrf(client), 'duration': '15',
        'media': [(io.BytesIO(archive([('a.png', PNG)])), 'bundle.zip'),
                  (io.BytesIO(PNG), 'another.png')]},
        content_type='multipart/form-data', headers=JSON)
    assert result.status_code == 422
    assert not lib.get(template['id'])['items']


def test_existing_player_playlist_is_not_replaced_and_failed_item_is_reported(env):
    _, client, _, _ = env
    login(client)
    FakePlayer.fail_name = 'broken.mp4'
    result = client.post('/devices/lab/bulk-media', data={
        'csrf': csrf(client), 'duration': '18',
        'media': [(io.BytesIO(PNG), 'good.png'),
                  (io.BytesIO(MP4), 'broken.mp4'),
                  (io.BytesIO(PNG), 'another.png')]},
        content_type='multipart/form-data', headers=JSON)
    assert result.status_code == 200
    assert (result.json['imported'], result.json['failed']) == (2, 1)
    assert result.json['partial'] is True
    assert [i[0] for i in FakePlayer.changes] == [
        'upload', 'create', 'upload', 'upload', 'create']
    assert [i[1] for i in FakePlayer.changes if i[0] == 'create'] == ['good', 'another']
    assert FakePlayer.preflight >= 1
    assert b'bulk-upload.js' in client.get('/devices/lab').data


def test_non_json_fallback_redirects_and_reports_failure(env):
    _, client, lib, template = env
    login(client)
    route = f"/library/{template['id']}/bulk-media"
    response = client.post(route, data={
        'csrf': csrf(client), 'duration': '15',
        'media': (io.BytesIO(archive([('valid.png', PNG), ('bad.txt', b'x')])), 'media.zip')},
        content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'1 importiert, 1 fehlgeschlagen' in response.data
    assert len(lib.get(template['id'])['items']) == 1


def test_roles_csrf_and_missing_destination_protect_bulk_routes(env):
    _, client, lib, template = env
    route = f"/library/{template['id']}/bulk-media"
    # CSRF is enforced before login checks for all POST requests in this app.
    assert client.post(route, headers=JSON).status_code == 400
    for role in ('viewer', 'it'):
        login(client, role)
        response = submit_zip(client, route, archive([('picture.png', PNG)]))
        assert response.status_code == 403
    login(client, 'marketing')
    assert client.post(route, data={
        'duration': '15', 'media': (io.BytesIO(PNG), 'picture.png')},
        content_type='multipart/form-data').status_code == 400
    response = submit_zip(client, '/library/00000000000000000000000000000000/bulk-media',
                          archive([('picture.png', PNG)]))
    assert response.status_code == 422
    assert not lib.get(template['id'])['items']


def test_ui_shows_both_bulk_targets_and_keeps_single_upload_forms(env):
    _, client, _, template = env
    login(client)
    playlist = client.get('/devices/lab').data
    library = client.get(f"/library/{template['id']}").data
    for page in (playlist, library):
        assert b'data-bulk-upload' in page
        assert b'bulk-upload.js' in page
        assert b'bulk-upload.css' in page
        assert b'multiple required' in page
    assert b'data-upload-form="player"' in playlist
    assert b'data-upload-form="library"' in library
    assert b'/devices/lab/bulk-media' in playlist
    assert f"/library/{template['id']}/bulk-media".encode() in library
