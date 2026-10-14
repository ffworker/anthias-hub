"""Offline regression checks for read-only media previews."""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.anthias import Anthias
from app.library import Library
from app.web import create_app


PNG = b'\x89PNG\r\n\x1a\n' + b'fake-pixels'
MP4 = b'\x00\x00\x00\x18ftypisom' + b'video-payload'


class Upstream:
    def __init__(self, body=PNG, status=200, headers=None):
        self.status_code = status
        self.body = body
        self.headers = headers or {'Content-Type': 'application/octet-stream',
                                   'Content-Length': str(len(body))}
        self.closed = False

    def iter_content(self, chunk_size=65536):
        yield self.body

    def close(self):
        self.closed = True


class Player:
    asset = {'asset_id': 'img1', 'name': 'Speisekarte.png',
             'mimetype': 'image', 'uri': '/data/anthias_assets/123.tmp'}
    upstream = Upstream()
    requests = []

    def __init__(self, device):
        self.url = device['url']
        self.http = self

    def assets(self):
        return [self.asset]

    def call(self, method, path, **kwargs):
        assert method == 'GET' and path.startswith('/api/v2/assets/')
        return dict(self.asset)

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.upstream

    valid_id = staticmethod(Anthias.valid_id)


@pytest.fixture
def env(tmp_path):
    users = tmp_path / 'users.json'
    users.write_text(json.dumps({'users': [
        {'username': 'viewer', 'role': 'viewer',
         'password_hash': generate_password_hash('a-long-safe-password', method='scrypt')},
    ]}), encoding='utf-8')
    devices = tmp_path / 'devices.json'
    devices.write_text(json.dumps({'devices': [
        {'id': 'lab', 'name': 'Test-Pi', 'url': 'http://10.0.0.8', 'location': 'Studio'},
    ]}), encoding='utf-8')
    app = create_app({'TESTING': True, 'SECRET_KEY': 's' * 48,
                      'SESSION_COOKIE_SECURE': False,
                      'USERS_FILE': str(users), 'DEVICES_FILE': str(devices),
                      'AUDIT_FILE': str(tmp_path / 'audit.log'),
                      'LIBRARY_DIR': str(tmp_path / 'library')})
    Player.asset = {'asset_id': 'img1', 'name': 'Speisekarte.png',
                    'mimetype': 'image', 'uri': '/data/anthias_assets/123.tmp'}
    Player.upstream = Upstream()
    Player.requests = []
    with patch('app.web.Anthias', Player):
        yield app, app.test_client()


def login(client):
    client.get('/login')
    with client.session_transaction() as session:
        csrf = session['csrf']
    result = client.post('/login', data={
        'username': 'viewer', 'password': 'a-long-safe-password', 'csrf': csrf})
    assert result.status_code == 302


def test_preview_requires_login(env):
    _, client = env
    assert client.get('/devices/lab/assets/img1/preview').status_code == 302
    assert client.get('/library/fake/items/fake/preview').status_code == 302
    assert not Player.requests


def test_player_image_preview_is_same_origin_and_correct_type(env):
    _, client = env
    login(client)
    page = client.get('/devices/lab')
    assert b'/devices/lab/assets/img1/preview' in page.data
    assert b'asset-media-preview' in page.data
    assert b'media-preview.js' in page.data
    response = client.get('/devices/lab/assets/img1/preview')
    assert response.status_code == 200
    assert response.data == PNG
    assert response.headers['Content-Type'].startswith('image/png')
    assert response.headers['Cache-Control'] == 'no-store'
    assert Player.requests[0][1] == 'http://10.0.0.8/assets/img1/preview/'
    assert Player.requests[0][2]['allow_redirects'] if 'allow_redirects' in Player.requests[0][2] else True
    assert Player.upstream.closed


def test_only_local_media_and_real_ids_can_be_previewed(env):
    _, client = env
    login(client)
    Player.asset = {**Player.asset, 'mimetype': 'webpage'}
    assert client.get('/devices/lab/assets/img1/preview').status_code == 404
    Player.asset = {**Player.asset, 'mimetype': 'image', 'uri': 'https://host.invalid/cat.png'}
    assert client.get('/devices/lab/assets/img1/preview').status_code == 404
    Player.asset = {**Player.asset, 'uri': '/data/anthias_assets/123.tmp'}
    assert client.get('/devices/lab/assets/other/preview').status_code == 404
    assert not Player.requests


def test_redirects_and_large_files_fall_back_without_exposing_data(env):
    _, client = env
    login(client)
    Player.upstream = Upstream(b'', 302, {'Location': 'https://other.invalid/'})
    assert client.get('/devices/lab/assets/img1/preview').status_code == 404
    assert Player.upstream.closed
    Player.upstream = Upstream(PNG, headers={'Content-Type': 'image/png',
                                            'Content-Length': str(9 * 1024 * 1024)})
    assert client.get('/devices/lab/assets/img1/preview').status_code == 404
    assert Player.upstream.closed


def test_video_preview_supports_browser_range_requests(env):
    _, client = env
    login(client)
    Player.asset = {**Player.asset, 'asset_id': 'vid1', 'mimetype': 'video',
                    'name': 'Show.mp4'}
    Player.upstream = Upstream(MP4, 206, {
        'Content-Type': 'video/mp4', 'Content-Length': str(len(MP4)),
        'Content-Range': f'bytes 0-{len(MP4)-1}/500',
        'Accept-Ranges': 'bytes',
    })
    response = client.get('/devices/lab/assets/vid1/preview',
                          headers={'Range': f'bytes=0-{len(MP4)-1}'})
    assert response.status_code == 206
    assert response.data == MP4
    assert response.headers['Content-Type'].startswith('video/mp4')
    assert response.headers['Content-Range'] == f'bytes 0-{len(MP4)-1}/500'
    assert Player.requests[0][2]['headers']['Range'].startswith('bytes=')
    assert Player.upstream.closed
    assert client.get('/devices/lab/assets/vid1/preview',
                      headers={'Range': 'bytes=0-1,3-5'}).status_code == 416


def test_local_library_images_and_videos_use_authenticated_media_paths(env):
    app, client = env
    collection = Library(app.config['LIBRARY_DIR']).create('Speisekarten')
    store = Library(app.config['LIBRARY_DIR'])
    store.add_media(collection['id'], 'Mittag', io.BytesIO(PNG), 'mittag.png', 15)
    store.add_media(collection['id'], 'Abend', io.BytesIO(MP4), 'abend.mp4', 15)
    items = store.get(collection['id'])['items']
    login(client)
    page = client.get('/library/' + collection['id'])
    assert page.status_code == 200
    assert page.data.count(b'asset-preview-content') == 2
    image_response = client.get(f'/library/{collection["id"]}/items/{items[0]["id"]}/preview')
    assert image_response.status_code == 200 and image_response.data == PNG
    assert image_response.headers['Content-Type'].startswith('image/png')
    video_response = client.get(f'/library/{collection["id"]}/items/{items[1]["id"]}/preview',
                                headers={'Range': 'bytes=0-7'})
    assert video_response.status_code == 206
    assert video_response.data == MP4[:8]
    assert client.get(f'/library/{collection["id"]}/items/missing/preview').status_code == 404
