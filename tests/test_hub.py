"""All tests offline: no real Anthias device touched."""
import errno
import io
import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from werkzeug.security import generate_password_hash
from app.web import create_app
from app import anthias
from app.devices import validate_device


class FakeAnthias:
    changes = []
    assets_data = [
        {'asset_id': 'one123', 'name': 'Welcome', 'mimetype':'text/html', 'uri':'https://example.org', 'play_order': 1, 'duration': 30, 'is_enabled': True},
        {'asset_id': 'two123', 'name': 'Lunch menu', 'mimetype':'image/png', 'uri':'file:///menu.png', 'play_order': 2, 'duration': 15, 'is_enabled': True},
    ]
    def __init__(self, device):
        self.device=device
        self.url=device["url"]
    def assets(self):
        return list(self.assets_data)
    def create(self, *args, **kwargs):
        self.changes.append(('create', args, kwargs))
        return {'asset_id':'created'}
    def upload(self, *args, **kwargs):
        self.changes.append(('upload', (), {}))
        return {'uri':'file:///uploaded.png','ext':'png'}
    def patch(self, *args, **kwargs):
        self.changes.append(('patch', args, kwargs))
        return {}
    def remove(self, *args, **kwargs):
        self.changes.append(('remove', args, kwargs))
    def display_power(self, state):
        self.changes.append(('display_power', (state,), {}))
        return {'message': 'CEC command accepted'}
    def system_power(self, action):
        self.changes.append(('system_power', (action,), {}))
        return None
    def order(self, *args, **kwargs):
        self.changes.append(('order', args, kwargs))
    @staticmethod
    def valid_id(asset_id):
        return anthias.Anthias.valid_id(asset_id)


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("ANTHIAS_VERIFIED_STORAGE_URLS", "http://127.0.0.1:9999")
    FakeAnthias.changes=[]
    with tempfile.TemporaryDirectory() as tmp:
        users = Path(tmp) / 'users.json'
        users.write_text(json.dumps({'users':[{'username':x,'role':x,'password_hash':generate_password_hash('safe-password-123',method='scrypt')} for x in ('owner','it','marketing','viewer')]}))
        devices = Path(tmp) / 'devices.json'
        devices.write_text(json.dumps({'devices':[{'id':'lab','name':'Lab Screen','url':'http://127.0.0.1:9999','location':'Lab'}]}))
        app=create_app({'TESTING':True,'SECRET_KEY':'s'*48,'SESSION_COOKIE_SECURE':False,'USERS_FILE':str(users),'DEVICES_FILE':str(devices),'AUDIT_FILE':str(Path(tmp)/'audit.jsonl')})
        with patch('app.web.Anthias',FakeAnthias):
            yield app, app.test_client(), tmp


def token(client):
    with client.session_transaction() as sess:
        return sess.get('csrf')


def login(client, name):
    client.get('/login')
    r=client.post('/login',data={'csrf':token(client),'username':name,'password':'safe-password-123'})
    assert r.status_code==302


def test_fresh_browser_can_log_in_on_its_first_try(env):
    app, _, _ = env
    browser = app.test_client()
    page = browser.get('/login')
    assert page.status_code == 200
    assert 'Set-Cookie' in page.headers
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    response = browser.post('/login', data={
        'csrf': csrf, 'username': 'marketing', 'password': 'safe-password-123',
    })
    assert response.status_code == 302
    assert browser.get('/').status_code == 200


def test_first_login_missing_or_stale_session_never_bypasses_csrf(env):
    app, _, _ = env
    blocked = app.test_client(use_cookies=False)
    page = blocked.get('/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.get_data(as_text=True)).group(1)
    rejected = blocked.post('/login', data={
        'csrf': csrf, 'username': 'marketing', 'password': 'safe-password-123',
    })
    assert rejected.status_code == 400
    assert 'Dein Browser hat die Anmeldesitzung nicht korrekt übermittelt' in rejected.get_data(as_text=True)
    assert rejected.headers['Cache-Control'] == 'no-store'
    assert blocked.get('/').status_code == 302

    stale = app.test_client()
    stale.get('/login')
    mismatch = stale.post('/login', data={
        'csrf': 'stale', 'username': 'marketing', 'password': 'safe-password-123',
    })
    assert mismatch.status_code == 400
    refreshed = mismatch.get_data(as_text=True)
    fresh_csrf = re.search(r'name="csrf" value="([^"]+)"', refreshed).group(1)
    assert stale.post('/login', data={
        'csrf': fresh_csrf, 'username': 'marketing', 'password': 'safe-password-123',
    }).status_code == 302


def test_login_warns_when_secure_cookie_is_used_over_http(env):
    app, _, _ = env
    app.config['SESSION_COOKIE_SECURE'] = True
    client = app.test_client()
    http_page = client.get('/login').get_data(as_text=True)
    assert 'HTTP-Zugriff mit HTTPS-Cookies erkannt.' in http_page
    https_page = client.get('/login', base_url='https://hub.example.test').get_data(as_text=True)
    assert 'HTTP-Zugriff mit HTTPS-Cookies erkannt.' not in https_page


def test_frontend_is_independent_from_other_projects(env):
    _, client, _ = env
    login_page = client.get('/login').data.decode('utf-8')
    assert 'https://github.com/ffworker/anthias-hub' in login_page
    assert 'Nicht von Screenly entwickelt oder unterstützt' in login_page
    assert 'rss2slideshow' not in login_page.lower()
    login(client, 'it')
    dashboard = client.get('/').data.decode('utf-8')
    assert 'rss2slideshow' not in dashboard.lower()


def test_nordlicht_navigation_and_playlist_forms(env):
    _, client, _ = env
    login_page = client.get('/login').data.decode('utf-8')
    assert 'theme-init.js' not in login_page and 'themes.js' not in login_page
    assert login_page.count('data-theme-choice=') == 0
    assert 'icons.svg#mark' in login_page
    for asset in ('ui-system.css', 'icons.svg', 'favicon.svg'):
        assert client.get('/static/' + asset).status_code == 200

    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert page.count('data-theme-choice=') == 0
    assert 'class="site-nav-link site-nav-primary is-active"' in page
    assert 'aria-current="page"' in page
    assert 'data-library-template' not in page
    assert 'data-add-mode="website"' in page and 'data-add-mode="media"' in page
    assert 'name="url"' in page and 'name="media"' in page
    assert 'asset-inline-edit' in page and 'class="quick-toggle-form"' in page
    assert 'class="duration-range" type="range" min="5" max="120"' in page
    assert 'Inhalt bearbeiten' not in page
    assert 'name="direction" value="up"' not in page
    assert 'icons.svg#web' in page and 'icons.svg#image' in page
    assert 'studio-bulk-details' in page
    assert 'add-mode-secondary' not in page
    assert page.count('data-open-composer') == 1  # one consistent add drawer entrypoint
    assert "'unsafe-inline'" not in client.get('/devices/lab').headers['Content-Security-Policy']


def test_ui_refresh_library_and_dashboard_role_safety(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    lib = Library(app.config['LIBRARY_DIR'])
    t = lib.create('Bistro Herbst')
    lib.add_url(t['id'], 'Menue', 'https://example.org/menu', 30)
    login(client, 'marketing')
    library = client.get('/library').data.decode('utf-8')
    assert 'data-bulk-upload' not in library  # imports happen inside templates
    assert 'Neue Playlist erstellen' in library and 'Vorlagen-Backup importieren' in library
    assert 'aria-current="page"' in library
    detail = client.get(f"/library/{t['id']}").data.decode('utf-8')
    assert 'library-item-options' in detail
    assert 'data-library-drawer-pane="more"' in detail
    assert 'data-library-add-pane="bulk"' in detail
    assert 'name="direction" value="up"' in detail
    playlist = client.get('/devices/lab').data.decode('utf-8')
    assert 'data-library-template' in playlist and 'data-library-source' in playlist
    assert 'data-library-source-template' in playlist
    assert 'data-add-mode="website"' in playlist
    assert playlist.count('data-add-mode=') == 4  # Datei, ZIP, Vorlage, Webseite
    dashboard = client.get('/').data.decode('utf-8')
    assert 'Hilfe bei Anzeigeproblemen' in dashboard
    assert 'Gerät verwalten' not in dashboard
    assert 'fleet-device-actions' in dashboard
    assert 'Keine Live-Vorschau verfügbar' not in dashboard


def test_marketing_can_build_export_and_import_local_library(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    login(client, 'marketing')
    t = token(client)
    assert client.post('/library', data={'csrf': t, 'name': 'Launch'}).status_code == 302
    from app.library import Library
    template = Library(app.config['LIBRARY_DIR']).list()[0]
    ident = template['id']
    assert client.post(f'/library/{ident}/url', data={'csrf': t, 'name': 'News', 'url': 'https://example.org/news', 'duration': '30'}).status_code == 302
    png = b'\x89PNG\r\n\x1a\n' + b'image-data'
    assert client.post(f'/library/{ident}/media', data={'csrf': t, 'name': 'Menu', 'duration': '15', 'media': (io.BytesIO(png), 'menu.png')}, content_type='multipart/form-data').status_code == 302
    assert len(Library(app.config['LIBRARY_DIR']).get(ident)['items']) == 2
    archive = client.get(f'/library/{ident}/export')
    assert archive.status_code == 200 and archive.headers['Content-Type'].startswith('application/zip')
    assert client.post('/library/import', data={'csrf': t, 'archive': (io.BytesIO(archive.data), 'launch.zip')}, content_type='multipart/form-data').status_code == 302
    assert len(Library(app.config['LIBRARY_DIR']).list()) == 2
    assert b'Launch' in client.get('/library').data
    assert b'News' in client.get(f'/library/{ident}').data


def test_library_apply_refuses_existing_playlist_then_adds_to_empty_device(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    login(client, 'marketing')
    t = token(client)
    from app.library import Library
    library = Library(app.config['LIBRARY_DIR'])
    template = library.create('Launch')
    library.add_url(template['id'], 'News', 'https://example.org/news', 30)
    data = {'csrf': t, 'template_id': template['id'], 'confirm': 'yes'}
    try:
        response = client.post('/devices/lab/apply-library', data=data)
        assert response.status_code == 302
        assert not FakeAnthias.changes
        FakeAnthias.assets_data = []
        response = client.post('/devices/lab/apply-library', data=data)
        assert response.status_code == 302
        assert [item[0] for item in FakeAnthias.changes] == ['create']
    finally:
        FakeAnthias.assets_data = [
            {'asset_id': 'one123', 'name': 'Welcome', 'mimetype':'text/html', 'uri':'https://example.org', 'play_order': 1, 'duration': 30, 'is_enabled': True},
            {'asset_id': 'two123', 'name': 'Lunch menu', 'mimetype':'image/png', 'uri':'file:///menu.png', 'play_order': 2, 'duration': 15, 'is_enabled': True},
        ]


def test_library_media_apply_and_role_boundary(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    library = Library(app.config['LIBRARY_DIR'])
    template = library.create('Visuals')
    library.add_media(template['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'pic'), 'photo.png', 15)
    login(client, 'it')
    t = token(client)
    assert client.get('/library').status_code == 200
    assert client.post(f"/library/{template['id']}/apply", data={'csrf': t, 'template_id': template['id'], 'device': 'lab', 'confirm': 'yes'}).status_code == 302
    assert client.post('/library', data={'csrf': t, 'name': 'IT can create'}).status_code == 302
    assert not FakeAnthias.changes
    login(client, 'marketing')
    t = token(client)
    try:
        FakeAnthias.assets_data = []
        response = client.post(f"/library/{template['id']}/apply", data={'csrf': t, 'template_id': template['id'], 'device': 'lab', 'confirm': 'yes'})
        assert response.status_code == 302
        assert [item[0] for item in FakeAnthias.changes] == ['upload', 'create']
    finally:
        FakeAnthias.assets_data = [
            {'asset_id': 'one123', 'name': 'Welcome', 'mimetype':'text/html', 'uri':'https://example.org', 'play_order': 1, 'duration': 30, 'is_enabled': True},
            {'asset_id': 'two123', 'name': 'Lunch menu', 'mimetype':'image/png', 'uri':'file:///menu.png', 'play_order': 2, 'duration': 15, 'is_enabled': True},
        ]


def test_library_removal_requires_explicit_ack(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Draft')
    lib.add_url(template['id'], 'Website', 'https://example.org', 30)
    entry = lib.get(template['id'])['items'][0]['id']
    login(client, 'marketing')
    data = {'csrf': token(client), 'confirm': entry}
    uri = f"/library/{template['id']}/remove/{entry}"
    assert client.post(uri, data=data).status_code == 400
    assert len(lib.get(template['id'])['items']) == 1
    assert client.post(uri, data={**data, 'ack': 'yes'}).status_code == 302
    assert not lib.get(template['id'])['items']


def test_library_apply_rejects_corrupt_media_before_any_write(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Visuals')
    lib.add_url(template['id'], 'Website', 'https://example.org', 30)
    lib.add_media(template['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\noriginal'), 'photo.png', 15)
    media = lib.get(template['id'])['items'][1]
    lib.media_path(template['id'], media).write_bytes(b'\x89PNG\r\n\x1a\nchanged')
    login(client, 'marketing')
    try:
        FakeAnthias.assets_data = []
        result = client.post(f"/library/{template['id']}/apply", data={'csrf': token(client), 'template_id': template['id'], 'device': 'lab', 'confirm': 'yes'}, follow_redirects=True)
        assert b'besch\xc3\xa4digt' in result.data
        assert not FakeAnthias.changes
    finally:
        FakeAnthias.assets_data = [
            {'asset_id': 'one123', 'name': 'Welcome', 'mimetype':'text/html', 'uri':'https://example.org', 'play_order': 1, 'duration': 30, 'is_enabled': True},
            {'asset_id': 'two123', 'name': 'Lunch menu', 'mimetype':'image/png', 'uri':'file:///menu.png', 'play_order': 2, 'duration': 15, 'is_enabled': True},
        ]


def test_library_move_updates_order_without_touching_device(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Draft')
    lib.add_url(template['id'], 'A', 'https://example.org/a', 30)
    lib.add_url(template['id'], 'B', 'https://example.org/b', 30)
    second = lib.get(template['id'])['items'][1]['id']
    login(client, 'marketing')
    response = client.post(f"/library/{template['id']}/move/{second}", data={'csrf': token(client), 'direction': 'up'})
    assert response.status_code == 302
    assert [item['name'] for item in lib.get(template['id'])['items']] == ['B', 'A']
    assert not FakeAnthias.changes


def test_requires_auth(env):
    app,client,_=env
    assert client.get('/').status_code==302
    assert client.get('/devices/lab').status_code==302
    assert client.post('/devices',data={}).status_code==400


def test_no_default_passwords_or_secrets(env):
    app,client,_=env
    client.get('/login')
    wrong=client.post('/login',data={'csrf':token(client),'username':'it','password':'wrong'})
    assert wrong.status_code==200
    assert client.get('/').status_code==302
    assert client.get('/healthz').status_code==200


def test_marketing_cannot_modify_devices(env):
    app,client,_=env
    login(client,'marketing')
    assert client.get('/').status_code==200
    response=client.post('/devices',data={'csrf':token(client),'name':'X','id':'x','url':'http://192.168.0.2'})
    assert response.status_code==403
    assert client.post('/devices/lab/remove',data={'csrf':token(client),'confirm':'lab'}).status_code==403
    assert client.post('/devices/lab/edit',data={'csrf':token(client),'name':'Hacked','url':'http://192.168.1.20'}).status_code==403
    page=client.get('/').data
    assert b'Original Anthias' not in page
    assert b'Ger\xc3\xa4t hinzuf\xc3\xbcgen' not in page


def test_it_can_edit_playlists_just_like_marketing(env):
    app,client,_=env
    login(client,'it')
    assert client.get('/devices/lab').status_code==200
    target='/devices/lab/assets/one123/edit'
    assert client.post(target,data={'csrf':token(client),'name':'IT edit','duration':'20'}).status_code==302
    assert client.post('/devices/lab/add-url',data={'csrf':token(client),'url':'https://example.org','name':'IT RSS','duration':'30'}).status_code==302
    assert any(event[0] == 'patch' for event in FakeAnthias.changes)
    assert any(event[0] == 'create' for event in FakeAnthias.changes)
    assert b'data-can-edit="yes"' in client.get('/devices/lab').data


def test_it_can_register_private_device_and_not_public(env):
    app,client,_=env
    login(client,'it')
    t=token(client)
    resp=client.post('/devices',data={'csrf':t,'name':'Bistro','id':'bistro','url':'http://192.168.1.50','location':'Bistro'})
    assert resp.status_code==302
    assert b'Bistro' in client.get('/').data
    client.post('/devices',data={'csrf':t,'name':'Public','id':'public','url':'http://8.8.8.8'})
    assert b'Public' not in client.get('/').data
    assert client.post('/devices/bistro/remove',data={'csrf':t,'confirm':'bistro','ack':'yes'}).status_code==302
    assert b'>Bistro<' not in client.get('/').data


def test_marketing_changes_each_devices_playlist(env):
    app,client,_=env
    login(client,'marketing')
    t=token(client)
    assert client.post('/devices/lab/add-url',data={'csrf':t,'name':'News','url':'https://example.org/news','duration':'45'}).status_code==302
    assert client.post('/devices/lab/assets/one123/edit',data={'csrf':t,'name':'New title','duration':'20','enabled':'on'}).status_code==302
    assert client.post('/devices/lab/assets/one123/move',data={'csrf':t,'direction':'down'}).status_code==302
    assert client.post('/devices/lab/assets/one123/delete',data={'csrf':t,'confirm':'one123','ack':'yes'}).status_code==302
    assert [c[0] for c in FakeAnthias.changes]==['create','patch','order','remove']
    assert FakeAnthias.changes[2][1]==(['two123','one123'],)


def test_viewer_is_read_only(env):
    app,client,_=env
    login(client,'viewer')
    assert client.get('/devices/lab').status_code==200
    assert client.post('/devices/lab/assets/two123/delete',data={'csrf':token(client),'confirm':'two123'}).status_code==403
    assert not FakeAnthias.changes


def test_csrf_required_to_save(env):
    app,client,_=env
    login(client,'marketing')
    assert client.post('/devices/lab/assets/two123/delete',data={'confirm':'two123'}).status_code==400
    assert not FakeAnthias.changes


def test_delete_requires_confirmation(env):
    app,client,_=env
    login(client,'marketing')
    assert client.post('/devices/lab/assets/two123/delete',data={'csrf':token(client),'confirm':'wrong'}).status_code==400
    assert not FakeAnthias.changes


def test_upload_png_and_reject_bad_header(env):
    app,client,_=env
    login(client,'marketing')
    post='/devices/lab/upload'
    resp=client.post(post,data={'csrf':token(client),'media':(io.BytesIO(b'garbage'),'bad.png'),'duration':'15'},content_type='multipart/form-data')
    assert resp.status_code==302
    assert not FakeAnthias.changes
    resp=client.post(post,data={'csrf':token(client),'media':(io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'0'*16),'good.png'),'duration':'15'},content_type='multipart/form-data')
    assert resp.status_code==302
    assert [c[0] for c in FakeAnthias.changes]==['upload','create']


def test_schedule_fields_not_overwritten(env):
    app,client,_=env
    login(client,'marketing')
    client.post('/devices/lab/assets/one123/edit',data={'csrf':token(client),'name':'Edited','duration':'40'})
    data=FakeAnthias.changes[0][1][1]
    assert set(data.keys())=={'name','duration'}


def test_asset_client_does_not_follow_redirects():
    from requests import Session
    def no_redirect(self, method, url, **kwargs):
        assert kwargs['allow_redirects'] is False
        class Response:
            status_code=302
            content=b''
        return Response()
    p=anthias.Anthias({'url':'http://192.168.2.3'})
    with patch.object(Session, 'request', no_redirect):
        with pytest.raises(anthias.PlayerError):
            p.assets()


def test_url_input_rejected(env):
    from app.anthias import validate_website_url
    for value in ('javascript:alert(1)', 'file:///tmp/x', 'http://user:pass@example.org'):
        with pytest.raises(ValueError):
            validate_website_url(value)
    with pytest.raises(ValueError):
        validate_device('bad','bad','http://8.8.8.8')


def test_playlist_editor_keeps_actions_in_hub_and_prioritizes_queue(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert page.index('id="playlist-queue"') < page.index('id="add-content"')
    assert 'id="asset-one123"' in page
    assert 'id="asset-two123"' in page
    assert 'class="drag-handle"' in page
    assert 'name="direction" value="up"' not in page
    assert 'name="direction" value="down"' not in page
    assert 'name="enabled"' in page
    assert 'type="file"' in page
    assert 'href="http://127.0.0.1:9999"' not in page
    assert 'Aktionen am Player bleiben im Hub' in page


def test_playlist_read_only_roles_do_not_get_edit_controls(env):
    _, client, _ = env
    login(client, 'viewer')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'id="playlist-queue"' in page
    assert 'id="add-content"' not in page
    assert 'name="direction"' not in page
    assert 'name="enabled"' not in page


def test_playlist_error_does_not_offer_writes(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'assets', side_effect=anthias.PlayerError('offline')):
        page = client.get('/devices/lab').data.decode('utf-8')
    assert 'offline' in page
    assert 'id="add-content"' not in page
    assert 'name="direction"' not in page


def test_upstream_media_types_show_correct_editor_controls(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'assets_data', [
        {'asset_id': 'web123', 'name': 'Site', 'mimetype': 'webpage', 'uri': 'https://example.org', 'duration': 30, 'is_enabled': True},
        {'asset_id': 'vid123', 'name': 'Film', 'mimetype': 'video', 'uri': '/media/film.mp4', 'duration': 0, 'is_enabled': True},
    ]):
        page = client.get('/devices/lab').data.decode('utf-8')
        assert 'WEBSEITE' in page
        assert 'VIDEO' in page
        video = page.split('id="asset-vid123"', 1)[1].split('</article>', 1)[0]
        assert 'name="duration"' not in video
        result = client.post('/devices/lab/assets/vid123/edit', data={
            'csrf': token(client), 'name': 'Updated film', 'enabled': 'on',
        })
    assert result.status_code == 302
    assert FakeAnthias.changes[-1] == ('patch', ('vid123', {'name': 'Updated film'}), {})

def test_reorder_is_single_call_and_rejects_stale_or_missing_ids(env):
    _, client, _ = env
    login(client, 'marketing')
    route = '/devices/lab/reorder'
    headers = {'Accept': 'application/json'}
    original = [('baseline', 'one123'), ('baseline', 'two123')]
    desired = [('ids', 'two123'), ('ids', 'one123')]
    response = client.post(route, data={'csrf': token(client), 'baseline': ['one123', 'two123'], 'ids': ['two123', 'one123']}, headers=headers)
    assert response.status_code == 200
    assert response.json == {'ok': True, 'ids': ['two123', 'one123']}
    assert FakeAnthias.changes == [('order', (['two123', 'one123'],), {})]
    FakeAnthias.changes.clear()
    bad = client.post(route, data={'csrf': token(client), 'baseline': ['two123', 'one123'], 'ids': ['one123', 'two123']}, headers=headers)
    assert bad.status_code == 409
    assert not FakeAnthias.changes
    missing = client.post(route, data={'csrf': token(client), 'baseline': ['one123', 'two123'], 'ids': ['one123']}, headers=headers)
    assert missing.status_code == 409
    assert not FakeAnthias.changes


def test_toggle_requires_matching_state_and_role(env):
    _, client, _ = env
    login(client, 'marketing')
    path = '/devices/lab/assets/one123/toggle'
    headers = {'Accept': 'application/json'}
    response = client.post(path, data={'csrf': token(client), 'enabled': '0', 'expected': '1'}, headers=headers)
    assert response.status_code == 200
    assert response.json == {'ok': True, 'enabled': False}
    assert FakeAnthias.changes == [('patch', ('one123', {'is_enabled': False}), {})]
    FakeAnthias.changes.clear()
    mismatch = client.post(path, data={'csrf': token(client), 'enabled': '0', 'expected': '0'}, headers=headers)
    assert mismatch.status_code == 409
    assert not FakeAnthias.changes
    no_token = client.post(path, data={'enabled': '0', 'expected': '1'}, headers=headers)
    assert no_token.status_code == 400
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    assert client.post(path, data={'csrf': token(client), 'enabled': '0', 'expected': '1'}, headers=headers).status_code == 403


def test_quick_edit_json_and_safety_confirmation(env):
    _, client, _ = env
    login(client, 'marketing')
    resp = client.post('/devices/lab/assets/one123/edit',
                       data={'csrf': token(client), 'name': 'New headline', 'duration': '22', 'enabled': 'on'},
                       headers={'Accept': 'application/json'})
    assert resp.status_code == 200
    assert resp.json == {'ok': True, 'asset': {'name': 'New headline', 'duration': 22}}
    no_ack = client.post('/devices/lab/assets/one123/delete',
                         data={'csrf': token(client), 'confirm': 'one123'})
    assert no_ack.status_code == 400
    assert not any(entry[0] == 'remove' for entry in FakeAnthias.changes)
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'data-reorder-url=' in page
    assert 'class="quick-toggle-form"' in page
    assert 'name="ack" value="yes" required' in page
    assert 'playlist.js' in page
    assert 'playlist.css' in page
    assert 'onclick=' not in page


def test_studio_visual_language_on_every_user_facing_page(env):
    _, client, _ = env
    login_page = client.get('/login').get_data(as_text=True)
    assert 'workspace.css' in login_page
    assert 'class="auth-layout"' in login_page
    assert 'Deine Ideen.' in login_page
    assert 'name="username"' in login_page
    assert 'name="password"' in login_page
    login(client, 'marketing')
    page = client.get('/').get_data(as_text=True)
    assert 'class="fleet-hero"' in page
    assert 'class="fleet-summary"' in page
    assert 'class="fleet-device card"' in page
    assert 'Inhalte bearbeiten' in page
    assert 'API erreichbar' in page
    assert 'Keine Live-Vorschau' not in page
    assert 'Original Anthias' not in page
    assert 'id="device-setup"' not in page
    # Marketing may acknowledge a support reboot, not IT device removal.
    assert 'Hilfe bei Anzeigeproblemen' in page
    assert 'fleet-danger-zone' not in page
    assert 'name="ack"' in page
    playlist = client.get('/devices/lab').get_data(as_text=True)
    assert 'workspace.css' in playlist
    assert 'playlist.css' in playlist
    assert 'Hauptnavigation' in playlist
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    viewer_page = client.get('/').get_data(as_text=True)
    assert 'Inhalte ansehen' in viewer_page
    assert 'id="device-setup"' not in viewer_page


def test_studio_it_device_management_has_explicit_delete_consent(env):
    _, client, _ = env
    login(client, 'it')
    page = client.get('/').get_data(as_text=True)
    assert 'id="device-setup"' in page
    assert 'Original Anthias' in page
    assert 'name="ack" value="yes" required' in page
    assert 'onclick=' not in page
    route = '/devices/lab/remove'
    res = client.post(route, data={'csrf': token(client), 'confirm': 'lab'})
    assert res.status_code == 400
    assert 'Lab Screen' in client.get('/').get_data(as_text=True)
    res = client.post(route, data={'csrf': token(client), 'confirm': 'lab', 'ack': 'yes'})
    assert res.status_code == 302
    assert 'Lab Screen' not in client.get('/').get_data(as_text=True)


def test_studio_empty_inventory_prompts_it_and_not_marketing(env):
    _, client, _ = env
    login(client, 'it')
    with patch('app.web.load', return_value=[]):
        it_page = client.get('/').get_data(as_text=True)
    assert 'Noch keine Bildschirme' in it_page
    assert 'Ersten Bildschirm verbinden' in it_page
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'marketing')
    with patch('app.web.load', return_value=[]):
        marketing_page = client.get('/').get_data(as_text=True)
    assert 'Noch keine Bildschirme' in marketing_page
    assert 'Ersten Bildschirm verbinden' not in marketing_page


def test_marketing_upload_json_reports_progress_ready_and_validates(env):
    app, client, _ = env
    login(client, 'marketing')
    headers = {'Accept': 'application/json'}
    url = '/devices/lab/upload'
    bad = client.post(url, data={
        'csrf': token(client), 'media': (io.BytesIO(b'not a PNG'), 'wrong.png'),
        'duration': '15'}, content_type='multipart/form-data', headers=headers)
    assert bad.status_code == 422
    assert bad.json['ok'] is False and 'Dateiformat' in bad.json['error']
    assert not FakeAnthias.changes
    good = client.post(url, data={
        'csrf': token(client),
        'media': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'pixels'), 'correct.png'),
        'duration': '15'}, content_type='multipart/form-data', headers=headers)
    assert good.status_code == 200
    assert good.json['ok'] is True
    assert good.json['redirect'] == '/devices/lab'
    assert [event[0] for event in FakeAnthias.changes] == ['upload', 'create']
    page = client.get('/devices/lab')
    assert b'data-upload-form="player"' in page.data
    assert b'upload-feedback.js' in page.data
    assert b'upload-progress' in page.data


def test_library_upload_json_returns_clear_errors_and_success(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    template = Library(app.config['LIBRARY_DIR']).create('Reusable')
    login(client, 'marketing')
    endpoint = f"/library/{template['id']}/media"
    headers = {'Accept': 'application/json'}
    bad = client.post(endpoint, data={
        'csrf': token(client), 'media': (io.BytesIO(b'invalid'), 'bad.png'),
        'duration': '15'}, content_type='multipart/form-data', headers=headers)
    assert bad.status_code == 422 and bad.json['ok'] is False
    good = client.post(endpoint, data={
        'csrf': token(client),
        'media': (io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'pixels'), 'sample.png'),
        'duration': '15'}, content_type='multipart/form-data', headers=headers)
    assert good.status_code == 200 and good.json['ok'] is True
    assert good.json['redirect'] == f"/library/{template['id']}"
    assert len(Library(app.config['LIBRARY_DIR']).get(template['id'])['items']) == 1
    page = client.get(f"/library/{template['id']}")
    assert b'data-upload-form="library"' in page.data


def test_upload_too_large_supports_json_errors(env):
    app, client, _ = env
    login(client, 'marketing')
    app.config['MAX_CONTENT_LENGTH'] = 250
    result = client.post('/devices/lab/upload', data={
        'csrf': token(client), 'media': (io.BytesIO(b'x' * 300), 'x.png')},
        content_type='multipart/form-data', headers={'Accept': 'application/json'})
    assert result.status_code == 413
    assert result.json['ok'] is False
    assert 'zu groß' in result.json['error']
    assert not FakeAnthias.changes


def test_single_library_item_appends_to_existing_player_without_reset(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Office')
    lib.add_url(template['id'], 'New Promo', 'https://example.org/promo', 25)
    saved = lib.get(template['id'])['items'][0]
    login(client, 'marketing')
    page = client.get('/devices/lab')
    assert b'data-add-mode="library"' in page.data
    assert (template['id'] + ':' + saved['id']).encode() in page.data
    before = list(FakeAnthias.assets_data)
    result = client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': template['id'] + ':' + saved['id'],
        'confirm': 'add'}, follow_redirects=True)
    assert result.status_code == 200
    assert [event[0] for event in FakeAnthias.changes] == ['create']
    assert FakeAnthias.changes[0][1] == ('New Promo', 'https://example.org/promo', 25)
    assert FakeAnthias.assets_data == before
    assert b'Bestehende Playlist bleibt erhalten' in result.data


def test_single_library_item_from_detail_uploads_only_selected_media(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Reusable')
    lib.add_media(template['id'], 'Brand', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'image'), 'brand.png', 15)
    lib.add_url(template['id'], 'Website', 'https://example.org', 15)
    items = lib.get(template['id'])['items']
    login(client, 'marketing')
    page = client.get(f"/library/{template['id']}")
    assert b'Zur Playlist hinzuf' in page.data
    uri = f"/library/{template['id']}/items/{items[0]['id']}/add-to-device"
    response = client.post(uri, data={
        'csrf': token(client), 'device': 'lab', 'confirm': 'add'})
    assert response.status_code == 302
    assert [event[0] for event in FakeAnthias.changes] == ['upload', 'create']
    assert len([event for event in FakeAnthias.changes if event[0] == 'create']) == 1


def test_library_item_add_rejects_invalid_confirmation_role_and_corrupt_file(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Photos')
    lib.add_media(template['id'], 'Photo', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'pixels'), 'photo.png', 15)
    item = lib.get(template['id'])['items'][0]
    source = template['id'] + ':' + item['id']
    login(client, 'viewer')
    assert client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': source, 'confirm': 'add'}).status_code == 403
    login(client, 'it')
    assert client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': source, 'confirm': 'wrong'}).status_code == 400
    login(client, 'marketing')
    assert client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': source, 'confirm': 'wrong'}).status_code == 400
    assert client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': '../bad', 'confirm': 'add'}).status_code == 400
    lib.media_path(template['id'], item).write_bytes(b'changed')
    result = client.post('/devices/lab/add-library-item', data={
        'csrf': token(client), 'source': source, 'confirm': 'add'},
        follow_redirects=True)
    assert result.status_code == 200
    assert b'besch\xc3\xa4digt' in result.data
    assert not FakeAnthias.changes


def test_single_library_url_refuses_exact_duplicate(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Duplicate')
    lib.add_url(template['id'], 'Welcome', 'https://example.org', 20)
    item = lib.get(template['id'])['items'][0]
    login(client, 'marketing')
    result = client.post('/devices/lab/add-library-item', data={
        'csrf': token(client),
        'source': template['id'] + ':' + item['id'],
        'confirm': 'add'}, follow_redirects=True)
    assert result.status_code == 200
    assert b'bereits in der Playlist' in result.data
    assert not FakeAnthias.changes


def test_library_landing_keeps_backup_separate_and_uploads_inside_templates(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    sample = lib.create('Bistro Medien')
    login(client, 'marketing')
    page = client.get('/library').data.decode('utf-8')
    assert 'Playlist erstellen' in page
    assert 'manifest.json' in page
    assert 'Vorlagen-Backup importieren' in page
    assert 'data-bulk-upload' not in page
    assert '/library/media-import' not in page
    assert '/library/import' in page
    assert sample['name'] in page
    detail = client.get('/library/' + sample['id']).data.decode('utf-8')
    assert 'data-bulk-upload' in detail
    assert 'data-library-add-pane="bulk"' in detail



def test_plain_zip_sent_to_backup_import_displays_helpful_error(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    lib.create('Vorhanden')
    login(client, 'marketing')
    import zipfile
    zipbytes = io.BytesIO()
    with zipfile.ZipFile(zipbytes, 'w') as writer:
        writer.writestr('medien/bild.png', b'\x89PNG\r\n\x1a\n' + b'sample')
    result = client.post('/library/import', data={
        'csrf': token(client), 'archive': (io.BytesIO(zipbytes.getvalue()), 'bilder.zip'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert result.status_code == 200
    assert b'manifest.json' in result.data
    assert len(lib.list()) == 1


def test_whole_template_can_append_to_nonempty_playlist(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Fruehstueck')
    lib.add_url(template['id'], 'Welcome', 'https://example.org', 30)  # already exists
    lib.add_url(template['id'], 'Aktion', 'https://example.org/promo', 30)
    lib.add_media(template['id'], 'Bild', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'test'), 'bild.png', 20)
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'Bestehende Playlist ergänzen · ganze Vorlage' not in page
    assert 'Eine komplette Vorlage übertragen?' in page
    central = client.get('/library/' + template['id']).get_data(as_text=True)
    assert 'Vorlage zur Playlist hinzufügen' in central
    assert '/append-to-device' in central
    result = client.post('/devices/lab/append-library', data={
        'csrf': token(client), 'confirm': 'append', 'ack': 'yes',
        'template_id': template['id'],
    }, follow_redirects=True)
    assert result.status_code == 200
    assert [event[0] for event in FakeAnthias.changes] == ['create', 'upload', 'create']
    assert FakeAnthias.changes[0][1] == ('Aktion', 'https://example.org/promo', 30)
    assert b'2 Inhalte hinzugef' in result.data
    assert b'1 bereits vorhandene Webseiten' in result.data


def test_whole_template_preflights_all_files_and_preserves_player(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Corrupt')
    lib.add_url(template['id'], 'Aktion', 'https://example.org/promo', 30)
    lib.add_media(template['id'], 'Bild', io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'test'), 'bild.png', 20)
    media = lib.get(template['id'])['items'][1]
    lib.media_path(template['id'], media).write_bytes(b'broken content')
    login(client, 'marketing')
    result = client.post('/devices/lab/append-library', data={
        'csrf': token(client), 'confirm': 'append', 'ack': 'yes',
        'template_id': template['id'],
    }, follow_redirects=True)
    assert result.status_code == 200
    assert not FakeAnthias.changes
    assert b'besch\xc3\xa4digt' in result.data


def test_whole_template_marketing_only_and_requires_ack(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    template = Library(app.config['LIBRARY_DIR']).create('Bistro')
    login(client, 'viewer')
    assert client.post('/devices/lab/append-library', data={
        'csrf': token(client), 'confirm': 'append', 'ack': 'yes',
        'template_id': template['id'],
    }).status_code == 403
    login(client, 'marketing')
    assert client.post('/devices/lab/append-library', data={
        'csrf': token(client), 'confirm': 'append',
        'template_id': template['id'],
    }).status_code == 400
    assert not FakeAnthias.changes


def test_whole_template_can_be_sent_from_library_detail(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Bistro')
    lib.add_url(template['id'], 'Promo', 'https://example.org/promo', 20)
    login(client, 'marketing')
    page = client.get('/library/' + template['id']).data.decode('utf-8')
    assert 'Vorlage zur Playlist hinzufügen' in page
    assert '/append-to-device' in page
    assert 'Backup-ZIP exportieren' in page
    result = client.post('/library/' + template['id'] + '/append-to-device', data={
        'csrf': token(client), 'confirm': 'append', 'ack': 'yes', 'device': 'lab',
    })
    assert result.status_code == 302
    assert [event[0] for event in FakeAnthias.changes] == ['create']


def test_inline_playlist_fields_preserve_pause_state_without_js(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'asset-inline-edit' in page
    assert 'class="duration-range" type="range" min="5" max="120"' in page
    assert 'name="enabled" value="on"' not in page
    assert 'Inhalt bearbeiten' not in page
    resp = client.post('/devices/lab/assets/one123/edit', data={
        'csrf': token(client), 'name': 'Renamed', 'duration': '41',
    }, headers={'Accept': 'application/json'})
    assert resp.status_code == 200
    assert 'is_enabled' not in resp.json['asset']
    assert resp.json['asset']['duration'] == 41
    assert 'is_enabled' not in FakeAnthias.changes[-1][1][1]


def test_library_publish_action_is_above_media_list_and_not_hidden_in_sidebar(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Frühstück im Bistro')
    lib.add_url(template['id'], 'Werbung', 'https://example.org/promo', 20)
    login(client, 'marketing')
    page = client.get(f"/library/{template['id']}").data.decode('utf-8')
    assert 'library-publish-hero' in page
    assert 'data-library-drawer-pane="apply"' in page
    assert 'data-open-library-drawer="apply"' in page
    assert 'id="library-publish-heading"' in page
    assert page.index('id="items-title"') < page.index('id="library-publish-heading"')
    assert page.index('Inhalte und Wiedergabereihenfolge') < page.index('Vorlage zur Playlist hinzufügen')
    assert page.count(f'/library/{template["id"]}/append-to-device') == 1
    assert 'name="device" required' in page
    assert 'name="ack" value="yes" required' in page
    assert 'bestehende Einträge bleiben unverändert' in page
    assert 'Backup-ZIP exportieren' in page


def test_library_publish_action_is_disabled_for_empty_templates_or_no_players(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    template = Library(app.config['LIBRARY_DIR']).create('Empty')
    login(client, 'marketing')
    page = client.get(f"/library/{template['id']}").data.decode('utf-8')
    assert 'Diese Vorlage ist noch leer' in page
    assert 'library-publish-button" disabled' in page
    from unittest.mock import patch
    with patch('app.web.load', return_value=[]):
        page = client.get(f"/library/{template['id']}").data.decode('utf-8')
    assert 'Noch kein Bildschirm registriert' not in page  # Empty takes priority.
    assert 'name="device" required disabled' in page


def test_read_only_viewer_does_not_receive_publish_controls(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    template = Library(app.config['LIBRARY_DIR']).create('Viewer')
    login(client, 'viewer')
    page = client.get(f"/library/{template['id']}").data.decode('utf-8')
    assert template['name'] in page
    assert 'library-publish-hero' not in page
    assert '/append-to-device' not in page


def test_playlist_edit_toolbar_contains_all_controls_in_one_compact_container(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    first = page.split('id="asset-one123"', 1)[1].split('</article>', 1)[0]
    toolbar = first.split('<div class="asset-toolbar"', 1)[1]
    assert 'move-controls' not in toolbar
    assert 'asset-inline-edit' in toolbar
    assert 'name="name"' in toolbar
    assert 'class="duration-range" type="range" min="5" max="120"' in toolbar
    assert 'inline-save' in toolbar
    assert 'delete-panel' in toolbar
    assert toolbar.index('asset-inline-edit') < toolbar.index('delete-panel')
    assert first.count('asset-inline-edit') == 1
    from pathlib import Path
    sheet = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'playlist.css').read_text()
    assert 'grid-template-columns:minmax(0,1fr) auto' in sheet
    assert 'flex:1 0 100%' not in sheet



def test_playlist_save_delete_are_grouped_and_save_button_targets_own_edit_form(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    for asset_id in ('one123', 'two123'):
        card = page.split(f'id="asset-{asset_id}"', 1)[1].split('</article>', 1)[0]
        toolbar = card.split('<div class="asset-toolbar"', 1)[1]
        edit_form = f'id="asset-edit-{asset_id}"'
        button_target = f'form="asset-edit-{asset_id}"'
        assert toolbar.count(edit_form) == 1
        assert toolbar.count(button_target) == 1
        assert 'class="asset-toolbar-actions"' in toolbar
        assert 'class="primary inline-save" data-save-ready="false">Speichern</button>' in toolbar
        assert '<summary aria-label=' in toolbar
        assert '<svg class="delete-icon"' in toolbar
        assert 'title="Inhalt löschen"' in toolbar
        assert 'class="delete-confirmation"' in toolbar
        assert 'move-controls' not in toolbar
        assert toolbar.index('asset-inline-edit') < toolbar.index('asset-toolbar-actions')
        assert toolbar.index(edit_form) < toolbar.index('class="asset-toolbar-actions"')
        assert toolbar.index('class="asset-toolbar-actions"') < toolbar.index(button_target)
        assert 'name="ack" value="yes" required' in toolbar
    # Same edit endpoint; HTML's form= association works without JS, too.
    result = client.post('/devices/lab/assets/one123/edit', data={
        'csrf': token(client), 'name': 'New compact title',
        'duration': '45', 'enabled': 'on',
    }, headers={'Accept': 'application/json'})
    assert result.status_code == 200
    assert result.json['asset']['name'] == 'New compact title'
    assert FakeAnthias.changes[-1][0] == 'patch'


def test_playlist_action_group_alignment_styles_and_script():
    root = Path(__file__).resolve().parents[1] / 'app' / 'static'
    css = (root / 'playlist.css').read_text(encoding='utf-8')
    js = (root / 'playlist.js').read_text(encoding='utf-8')
    assert '.playlist-workspace .asset-toolbar-actions{' in css
    assert 'justify-content:flex-end;' in css
    assert '.playlist-workspace .asset-toolbar-actions .inline-save{' in css
    assert '.playlist-workspace .asset-toolbar-actions .delete-panel>summary{' in css
    assert '.asset:has(.asset-toolbar-actions .delete-panel[open])' in css
    assert 'grid-column:1;grid-row:2' in css  # mobile: actions after fields
    assert "card.querySelector('.asset-toolbar-actions .inline-save')" in js
    assert "const result = await postForm(form.action, new FormData(form));" in js


def test_precise_duration_editor_shows_slider_and_direct_number_input(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'assets_data', [
        {'asset_id': 'precise123', 'name': 'Extended menu',
         'mimetype': 'image/png', 'uri': 'file:///menu.png',
         'duration': 900, 'is_enabled': True},
    ]):
        page = client.get('/devices/lab').data.decode('utf-8')
        card = page.split('id="asset-precise123"', 1)[1].split('</article>', 1)[0]
        # The slider is for typical short durations; a longer saved duration
        # remains exact in the submitted number field, never reduced to 120.
        assert 'class="duration-range" type="range" min="5" max="120"' in card
        assert 'value="120"' in card
        assert 'class="duration-number" type="number"' in card
        assert 'name="duration" min="5" max="3600" step="1" required' in card
        assert 'value="900"' in card
        assert card.count('name="duration"') == 1
        result = client.post('/devices/lab/assets/precise123/edit', data={
            'csrf': token(client), 'name': 'Extended menu',
            'duration': '900', 'enabled': 'on',
        }, headers={'Accept': 'application/json'})
    assert result.status_code == 200
    assert result.json['asset']['duration'] == 900
    assert FakeAnthias.changes[-1][1][1]['duration'] == 900


def test_duration_manual_input_still_validates_server_side(env):
    _, client, _ = env
    login(client, 'marketing')
    for value in ('4', '3601', 'abc'):
        response = client.post('/devices/lab/assets/one123/edit', data={
            'csrf': token(client), 'name': 'Welcome',
            'duration': value, 'enabled': 'on',
        }, headers={'Accept': 'application/json'})
        assert response.status_code == 422
        assert response.json['ok'] is False
    assert not FakeAnthias.changes


def test_duration_js_sync_preserves_long_manually_entered_values():
    source = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'playlist.js').read_text(encoding='utf-8')
    assert "number.value = slider.value" in source
    assert "slider.value = String(Math.max(5, Math.min(120, seconds)))" in source
    assert "number.value = String(Math.max(" not in source


def test_marketing_playlist_has_one_accessible_drag_grip_per_asset(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'Tastatur: Griff fokussieren' in page
    assert 'id="playlist-sort-status"' in page
    assert 'role="status" aria-live="polite"' in page
    assert page.count('class="drag-handle"') == 2
    assert page.count('aria-describedby="queue-help" aria-pressed="false"') == 2
    assert 'name="direction"' not in page
    assert 'class="move-controls"' not in page
    assert 'move-label' not in page
    assert 'data-reorder-url=' in page
    assert 'grid-template-columns' not in page  # styling stays in CSS


def test_nonmarketing_does_not_get_drag_or_sort_controls(env):
    _, client, _ = env
    login(client, 'viewer')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'class="drag-handle"' not in page
    assert 'id="playlist-sort-status"' not in page
    assert 'data-reorder-url=' not in page
    assert 'name="direction"' not in page
    login(client, 'it')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'class="drag-handle"' in page
    assert 'data-can-edit="yes"' in page


def test_drag_reorder_contract_has_rollback_and_touch_keyboard_support():
    static = Path(__file__).resolve().parents[1] / 'app' / 'static'
    js = (static / 'playlist.js').read_text(encoding='utf-8')
    css = (static / 'playlist.css').read_text(encoding='utf-8')
    for required in ("'baseline'", "'ids'", "restoreOrder(before)",
                     "pointercancel", "setPointerCapture", "ArrowUp", "ArrowDown",
                     "Escape", "focusout", "aria-pressed", "announceSort"):
        assert required in js
    assert 'touch-action:none' in css
    assert '.asset.is-keyboard-grabbed' in css
    assert '.asset.drop-before' in css and '.asset.drop-after' in css
    assert 'move-controls' not in js
    assert '.playlist-workspace .asset-toolbar .move-controls' not in css


def test_save_is_dirty_only_with_javascript_and_still_works_without_it(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'data-save-ready="false"' in page
    js = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'playlist.js').read_text()
    assert 'form.dataset.savedValues = editValue(form)' in js
    assert 'button.disabled = !dirty' in js
    assert 'form.dataset.savedValues = submitted' in js
    assert 'refreshSave(card)' in js
    # Without JS, a normal edit still reaches the same authenticated endpoint.
    result = client.post('/devices/lab/assets/one123/edit', data={
        'csrf': token(client), 'name': 'Neue Karte',
        'duration': '24', 'enabled': 'on',
    }, headers={'Accept': 'application/json'})
    assert result.status_code == 200
    assert result.json['asset']['duration'] == 24


def test_stale_edit_never_restores_old_enabled_state(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'class="asset-edit asset-inline-edit ' in page
    assert '<input type="hidden" name="enabled" value="on">' not in page
    with patch.object(FakeAnthias, 'assets_data', [dict(FakeAnthias.assets_data[0], is_enabled=False)]):
        result = client.post('/devices/lab/assets/one123/edit', data={
            'csrf': token(client), 'name': 'New heading', 'duration': '22',
            'enabled': 'on',  # An old/stale browser may still send this field.
        }, headers={'Accept': 'application/json'})
        assert result.status_code == 200
        assert result.json['asset'] == {'name': 'New heading', 'duration': 22}
        assert FakeAnthias.changes[-1] == ('patch', ('one123', {'name': 'New heading', 'duration': 22}), {})



def test_playlist_media_and_library_are_prominent_before_optional_website(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert page.index('data-add-mode="media"') < page.index('data-add-mode="library"')
    assert page.index('data-add-mode="library"') < page.index('data-add-mode="website"')
    assert 'class="add-mode selected" data-add-mode="media" aria-pressed="true"' in page
    assert 'class="add-mode" data-add-mode="website" aria-pressed="false"' in page
    assert '>Webseite</button>' in page
    assert page.index('data-add-pane="website"') < page.index('data-add-pane="media"')  # legacy form remains
    assert 'RSS2Slideshow-Anzeige' in page
    static = Path(__file__).resolve().parents[1] / 'app' / 'static'
    javascript = (static / 'playlist.js').read_text(encoding='utf-8')
    stylesheet = (static / 'playlist.css').read_text(encoding='utf-8')
    assert "if (modeButtons.length) selectMode('media')" in javascript
    assert "selectMode('website')" not in javascript
    assert '.add-type-switch .add-mode' in stylesheet
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in stylesheet


def test_library_template_shows_media_first_and_website_only_on_request(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    library = Library(app.config['LIBRARY_DIR'])
    collection = library.create('Bistro-Archiv')
    login(client, 'marketing')
    page = client.get('/library/' + collection['id']).data.decode('utf-8')
    assert page.index('Einzeldatei hinzufügen') < page.index('ZIP / mehrere Dateien importieren')
    assert page.index('ZIP / mehrere Dateien importieren') < page.index('Webseite / RSS hinzufügen')
    assert 'data-library-add-tab="website"' in page
    assert 'data-library-add-pane="website"' in page
    assert 'library-website-details library-action-disclosure' not in page
    assert 'library_add_url' not in page  # internal endpoint name is not exposed
    assert '/url' in page  # existing URL submission stays available
    assert 'RSS2Slideshow-Anzeige' in page
    assert 'data-upload-form="library"' in page
    assert 'data-bulk-upload' in page
    assert page.index('Inhalte und Wiedergabereihenfolge') < page.index('Vorlage zur Playlist hinzufügen')


def test_library_optional_website_submission_and_role_guards_are_unchanged(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    store = Library(app.config['LIBRARY_DIR'])
    collection = store.create('Bistro-Web')
    endpoint = '/library/' + collection['id'] + '/url'
    login(client, 'viewer')
    assert client.post(endpoint, data={
        'csrf': token(client), 'name': 'Kiosk', 'url': 'https://example.org',
        'duration': '20'}).status_code == 403
    login(client, 'marketing')
    response = client.post(endpoint, data={
        'csrf': token(client), 'name': 'Kiosk',
        'url': 'https://example.org', 'duration': '20'})
    assert response.status_code == 302
    assert [item['name'] for item in store.get(collection['id'])['items']] == ['Kiosk']


def test_pilot_pause_state_protection_is_still_present_after_ui_reordering(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    edit_form = page.split('id="asset-edit-one123"', 1)[1].split('</form>', 1)[0]
    assert 'name="enabled"' not in edit_form  # Toggle owns this state, not edit.
    assert 'class="quick-toggle-form"' in page  # Existing pause form still works.
    result = client.post('/devices/lab/assets/one123/edit', data={
        'csrf': token(client), 'name': 'Bistro-News', 'duration': '30',
        'enabled': 'on',  # stale client must not overwrite pause state
    }, headers={'Accept': 'application/json'})
    assert result.status_code == 200
    assert result.json['asset'] == {'name': 'Bistro-News', 'duration': 30}
    assert 'is_enabled' not in FakeAnthias.changes[-1][1][1]


def test_studio_v2_cards_are_editable_on_demand_and_drawer_is_reachable(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'class="playlist-workspace playlist-studio-v2"' in page
    assert 'class="editor-layout studio-full-layout"' in page
    assert 'data-open-composer' in page
    assert 'class="composer-backdrop" data-close-composer hidden' in page
    assert 'data-composer-drawer' in page
    assert 'playlist-studio.js' in page
    assert page.count('class="asset-body asset-open" aria-expanded="false"') == 2
    assert 'aria-controls="asset-editor-one123"' in page
    assert 'role="region"' in page
    assert 'id="asset-editor-one123"' in page
    # The image preview stays independent from the card editor click target.
    assert 'data-media-lightbox' in page
    assert 'class="drag-handle"' in page
    assert 'class="quick-toggle-form"' in page
    assert 'name="duration" min="5" max="3600"' in page
    edit_form = page.split('id="asset-edit-one123"', 1)[1].split('</form>', 1)[0]
    assert 'name="enabled"' not in edit_form  # Pause is owned by its own form


def test_studio_v2_keeps_viewers_read_only_and_has_no_drawer(env):
    _, client, _ = env
    login(client, 'viewer')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert 'class="playlist-workspace playlist-studio-v2"' in page
    assert 'class="asset-body asset-open"' not in page
    assert 'data-composer-drawer' not in page
    assert 'data-open-composer' not in page
    assert 'role="region"' not in page
    assert 'class="drag-handle"' not in page


def test_studio_v2_progressive_enhancement_and_unsaved_confirmation():
    root = Path(__file__).resolve().parents[1] / 'app' / 'static'
    js = (root / 'playlist-studio.js').read_text(encoding='utf-8')
    css = (root / 'playlist.css').read_text(encoding='utf-8')
    assert "studio.classList.add('js-ready')" in js
    assert "if (isUnsaved(card))" in js
    assert "Ungespeicherte Änderungen verwerfen?" in js
    assert "hasUnsubmittedContent()" in js
    assert "event.key === 'Escape'" in js
    assert "event.key !== 'Tab'" in js
    assert "closeCard(expanded)" in js
    assert "drawer.inert = true" in js
    assert ".playlist-studio-v2 .asset-toolbar[hidden]{display:none!important}" in css
    assert "grid-template-columns:minmax(0,1fr)!important" in css
    assert "width:100vw" in css  # mobile sheet
    assert "prefers-reduced-motion:reduce" in css


def test_library_marketing_can_delete_whole_template_without_touching_pi(env):
    app, client, tmp = env
    from app.library import Library, LibraryError
    root = Path(tmp) / 'library'
    app.config['LIBRARY_DIR'] = str(root)
    library = Library(root)
    collection = library.create('Bistro Herbst')
    unchanged = library.create('Andere Vorlage')
    png = b'\x89PNG\r\n\x1a\n' + b'data'
    library.add_media(collection['id'], 'Aktion', io.BytesIO(png), 'aktion.png', 20)
    library.add_url(collection['id'], 'Kiosk', 'https://example.org/kiosk', 30)
    login(client, 'marketing')
    t = token(client)
    detail = client.get('/library/' + collection['id']).data.decode('utf-8')
    overview = client.get('/library').data.decode('utf-8')
    assert 'template-delete-control template-delete-detail' in detail
    assert 'template-delete-control template-delete-list' not in overview
    assert 'data-library-drawer-pane="create"' in overview
    assert 'data-library-drawer-pane="backup"' in overview
    assert 'name="name_confirmation"' in detail
    assert 'name="ack" value="yes"' in detail
    assert 'template-delete.js' in detail
    route = '/library/' + collection['id'] + '/delete'
    assert client.post(route, data={'csrf': t, 'confirm': collection['id'],
                                    'ack': 'yes', 'name_confirmation': 'Falsch'}).status_code == 302
    assert root.joinpath(collection['id']).is_dir()
    assert not FakeAnthias.changes
    response = client.post(route, data={
        'csrf': t, 'confirm': collection['id'],
        'ack': 'yes', 'name_confirmation': collection['name'],
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'gel\xc3\xb6scht' in response.data
    assert not (root / collection['id']).exists()
    assert library.get(unchanged['id'])['name'] == 'Andere Vorlage'
    with pytest.raises(LibraryError):
        library.get(collection['id'])
    assert not FakeAnthias.changes
    assert b'Andere Vorlage' in response.data


def test_library_template_delete_csrf_roles_confirm_and_symlink_protection(env):
    app, client, tmp = env
    from app.library import Library, LibraryError
    root = Path(tmp) / 'library'
    app.config['LIBRARY_DIR'] = str(root)
    lib = Library(root)
    collection = lib.create('Sicher')
    route = '/library/' + collection['id'] + '/delete'
    login(client, 'viewer')
    assert client.post(route, data={'csrf': token(client), 'confirm': collection['id'],
                                    'ack': 'yes', 'name_confirmation': 'Sicher'}).status_code == 403
    login(client, 'it')
    assert client.post(route, data={'csrf': token(client), 'confirm': 'wrong',
                                    'ack': 'yes', 'name_confirmation': 'Sicher'}).status_code == 400
    login(client, 'marketing')
    t = token(client)
    assert client.post(route, data={'csrf': t, 'confirm': 'wrong',
                                    'ack': 'yes', 'name_confirmation': 'Sicher'}).status_code == 400
    assert client.post(route, data={'csrf': t, 'confirm': collection['id'],
                                    'name_confirmation': 'Sicher'}).status_code == 400
    assert client.post(route, data={'confirm': collection['id'], 'ack': 'yes',
                                    'name_confirmation': 'Sicher'}).status_code == 400
    assert (root / collection['id']).exists()
    # A compromised directory symlink must not allow deleting external content.
    external = Path(tmp) / 'external'
    external.mkdir()
    (external / 'important.txt').write_text('keep')
    link = root / ('a' * 32)
    link.symlink_to(external, target_is_directory=True)
    # Even a seemingly valid manifest at the linked location must not cause
    # rmtree() to traverse and remove another directory.
    (external / 'manifest.json').write_text(json.dumps({
        'version': 1, 'id': 'a' * 32, 'name': 'Link target', 'items': [],
    }))
    with pytest.raises(LibraryError, match='verzeichnis'):
        lib.delete_template('a' * 32, 'Link target')
    assert (external / 'important.txt').read_text() == 'keep'


def test_library_overview_uses_one_action_drawer_and_deletion_only_in_detail(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Aktionsvorlage')
    login(client, 'marketing')
    page = client.get('/library').get_data(as_text=True)
    detail = client.get('/library/' + template['id']).get_data(as_text=True)

    assert '<div class="card library-entry-shell">' in page
    entry = page.split('<div class="card library-entry-shell">', 1)[1]
    assert '<a class="library-entry" href=' in entry
    assert 'class="template-delete-control template-delete-list"' not in entry
    assert 'class="library-actions"' not in page
    assert 'library-action-disclosure' not in page
    assert page.index('id="library-list-title"') < page.index('id="new-playlist"')
    assert 'data-open-library-drawer="create"' in page
    assert 'data-open-library-drawer="backup"' in page
    assert 'data-library-drawer-pane="create"' in page
    assert 'data-library-drawer-pane="backup"' in page
    assert 'name="csrf"' in page and 'name="archive"' in page
    assert 'template-delete-control template-delete-detail' in detail
    style = (Path(__file__).resolve().parents[1] / 'app' / 'static' /
             'ui-system.css').read_text(encoding='utf-8')
    assert '.site-main .library-index-workspace .library-list{' in style
    assert '.site-main .library-index-workspace .library-index-grid{' in style
    assert 'width:min(485px,100vw)' in style
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    viewer = client.get('/library').get_data(as_text=True)
    assert '<div class="card library-entry-shell">' in viewer
    assert 'data-library-drawer' not in viewer
    assert 'template-delete-control' not in viewer
    assert 'library_create' not in viewer


def test_screen_card_ctas_have_equal_insets_for_marketing_it_and_viewer(env):
    _, client, _ = env
    style = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'ui-system.css').read_text()
    assert '.fleet-device-primary-actions' in style
    assert 'grid-template-columns:minmax(0,1.25fr) minmax(0,1fr)' in style
    assert '.fleet-device-tools-label' in style
    assert '.fleet-actions-it:has(>.fleet-storage-menu)' in style
    for role, label in [('marketing', 'Inhalte bearbeiten'),
                        ('viewer', 'Inhalte ansehen'), ('it', 'Inhalte bearbeiten')]:
        login(client, role)
        page = client.get('/').get_data(as_text=True)
        assert 'class="button primary fleet-open"' in page
        assert 'class="fleet-device-primary-actions"' in page
        assert label in page
        if role == 'it':
            assert 'fleet-settings' in page
            assert 'fleet-add-button' in page and 'href="#device-setup"' in page
        else:
            assert 'fleet-settings' not in page
        client.post('/logout', data={'csrf': token(client)})


def test_device_playlist_one_add_drawer_bulk_selection_stays_in_context(env):
    _, client, _ = env
    for role in ('marketing', 'it'):
        login(client, role)
        page = client.get('/devices/lab').get_data(as_text=True)
        assert page.count('data-open-composer') == 1
        assert 'playlist-bottom-actions' not in page
        assert 'Weiteren Inhalt hinzufügen' not in page
        assert 'data-bulk-management' in page
        assert page.index('id="playlist-items"') < page.index('data-bulk-management')
        assert 'name="selected" value="one123" form="playlist-bulk-form"' in page
        assert 'name="baseline" value="one123"' in page
        assert 'name="mode" value="selected"' in page
        assert 'name="mode" value="all"' in page
        assert 'name="name_confirmation"' in page
        assert 'playlist-bulk.js' in page
        assert 'data-add-mode="library"' in page
        assert 'Noch keine gespeicherten Inhalte vorhanden.' in page
        assert 'Eine komplette Vorlage übertragen?' not in page  # no template exists yet
        assert 'append_library_from_player' not in page
        assert 'attach_folder_playlist_to_device' not in page
        assert 'data-add-mode="library"' in page
        client.post('/logout', data={'csrf': token(client)})

    login(client, 'viewer')
    read_only = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-open-composer' not in read_only
    assert 'playlist-bulk-form' not in read_only


def test_playlist_empty_has_first_add_but_no_bulk_or_bottom_add(env):
    _, client, _ = env
    login(client, 'marketing')
    original = FakeAnthias.assets_data
    try:
        FakeAnthias.assets_data = []
        page = client.get('/devices/lab').get_data(as_text=True)
        assert page.count('data-open-composer') == 1
        assert 'Öffne oben „Inhalt hinzufügen“' in page
        assert 'Weiteren Inhalt hinzufügen' not in page
        assert 'playlist-bulk-form' not in page
    finally:
        FakeAnthias.assets_data = original


def test_player_bulk_delete_selected_only_and_audits_actual_writes(env):
    app, client, tmp = env
    login(client, 'marketing')
    snapshot = ['one123', 'two123']
    result = client.post('/devices/lab/bulk-delete', data={
        'csrf': token(client), 'mode': 'selected', 'baseline': snapshot,
        'selected': ['two123'], 'ack': 'yes',
    }, follow_redirects=True)
    assert result.status_code == 200
    assert b'1 ausgew' in result.data
    assert FakeAnthias.changes == [('remove', ('two123',), {})]
    entries = [json.loads(line) for line in (Path(tmp) / 'audit.jsonl').read_text().splitlines()]
    assert [(e['action'], e['asset']) for e in entries if e['action'] == 'asset.bulk-delete'] == [
        ('asset.bulk-delete', 'two123')]
    # No device unregister, library mutation or unselected player asset deletion.
    assert client.get('/devices/lab').status_code == 200


def test_player_clear_entire_playlist_requires_exact_name_and_ack(env):
    _, client, _ = env
    login(client, 'marketing')
    snapshot = ['one123', 'two123']
    url = '/devices/lab/bulk-delete'
    base = {'csrf': token(client), 'mode': 'all', 'baseline': snapshot, 'ack': 'yes'}
    assert client.post(url, data={**base, 'name_confirmation': 'Other Screen'}).status_code == 400
    assert not FakeAnthias.changes
    assert client.post(url, data={**base, 'ack': 'no', 'name_confirmation': 'Lab Screen'}).status_code == 400
    assert not FakeAnthias.changes
    done = client.post(url, data={**base, 'name_confirmation': 'Lab Screen'}, follow_redirects=True)
    assert done.status_code == 200
    assert [e[1][0] for e in FakeAnthias.changes] == ['one123', 'two123']
    assert b'2 Inhalte vom Player entfernt' in done.data
    assert b'Bibliotheksvorlagen bleiben erhalten' in done.data


def test_player_bulk_rejects_bad_selection_stale_snapshot_and_csrf(env):
    _, client, _ = env
    url = '/devices/lab/bulk-delete'
    login(client, 'viewer')
    assert client.post(url, data={
        'csrf': token(client), 'baseline': ['one123', 'two123'],
        'selected': ['one123'], 'ack': 'yes', 'mode': 'selected'}).status_code == 403
    login(client, 'marketing')
    base = {'csrf': token(client), 'baseline': ['one123', 'two123'],
            'selected': ['one123'], 'ack': 'yes', 'mode': 'selected'}
    assert client.post(url, data={**base, 'csrf': 'invalid'}).status_code == 400
    assert client.post(url, data={**base, 'ack': ''}).status_code == 400
    assert client.post(url, data={**base, 'selected': ['one123', 'one123']}).status_code == 400
    assert client.post(url, data={**base, 'selected': ['unknown']}).status_code == 400
    assert client.post(url, data={**base, 'selected': []}).status_code == 400
    assert client.post(url, data={**base, 'selected': ['one123', 'two123']}).status_code == 400
    assert client.post(url, data={**base, 'baseline': ['one123', '../../bad']}).status_code == 400
    assert client.post(url, data={**base, 'baseline': ['two123', 'one123']}).status_code == 409
    assert client.post(url, data={**base, 'baseline': ['one123', 'two123', 'extra123']}).status_code == 409
    assert client.post(url, data={
        **base, 'mode': 'all', 'baseline': ['one123'], 'name_confirmation': 'Lab Screen'
    }).status_code == 409
    assert not FakeAnthias.changes


def test_player_bulk_partial_failure_stops_and_explains_uncertainty(env):
    _, client, _ = env
    login(client, 'marketing')
    original = FakeAnthias.remove
    def fail_second(self, asset_id):
        if asset_id == 'two123':
            raise anthias.PlayerError('simulierte Pi-Störung')
        self.changes.append(('remove', (asset_id,), {}))
    FakeAnthias.remove = fail_second
    try:
        response = client.post('/devices/lab/bulk-delete', data={
            'csrf': token(client), 'mode': 'all', 'baseline': ['one123', 'two123'],
            'name_confirmation': 'Lab Screen', 'ack': 'yes',
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b'1 von 2' in response.data
        assert b'nicht blind erneut l' in response.data
        assert FakeAnthias.changes == [('remove', ('one123',), {})]
    finally:
        FakeAnthias.remove = original


def test_device_remote_control_renders_only_allowed_roles(env):
    _, client, _ = env
    login(client, 'it')
    it = client.get('/').get_data(as_text=True)
    assert 'Gerätesteuerung' in it
    assert 'Original Anthias' in it
    assert 'value="hdmi-on"' in it and 'value="hdmi-off"' in it
    assert 'value="reboot"' in it and 'value="shutdown"' in it
    assert 'name="name_confirmation"' in it
    assert 'id="device-lab"' in it
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'marketing')
    marketing = client.get('/').get_data(as_text=True)
    assert 'Hilfe bei Anzeigeproblemen' in marketing
    assert 'Pi neu starten' in marketing
    assert 'value="reboot"' in marketing
    assert 'value="hdmi-off"' not in marketing
    assert 'value="hdmi-on"' not in marketing
    assert 'value="shutdown"' not in marketing
    assert 'Original Anthias' not in marketing
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    viewer = client.get('/').get_data(as_text=True)
    assert 'Gerätesteuerung' not in viewer
    assert 'Hilfe bei Anzeigeproblemen' not in viewer
    assert '/devices/lab/control' not in viewer


def test_it_can_send_explicit_hdmi_reboot_and_shutdown_commands(env):
    _, client, _ = env
    login(client, 'it')
    uri = '/devices/lab/control'
    base = {'csrf': token(client), 'confirm': 'lab', 'ack': 'yes'}
    for action in ('hdmi-on', 'hdmi-off', 'reboot', 'shutdown'):
        data = {**base, 'action': action}
        if action == 'shutdown':
            data['name_confirmation'] = 'Lab Screen'
        response = client.post(uri, data=data, follow_redirects=True)
        assert response.status_code == 200
        assert response.request.path == '/'
    assert FakeAnthias.changes == [
        ('display_power', ('on',), {}),
        ('display_power', ('off',), {}),
        ('system_power', ('reboot',), {}),
        ('system_power', ('shutdown',), {}),
    ]


def test_marketing_only_reboot_with_ack_and_csrf(env):
    _, client, _ = env
    uri = '/devices/lab/control'
    login(client, 'marketing')
    base = {'csrf': token(client), 'confirm': 'lab', 'ack': 'yes'}
    for action in ('hdmi-on', 'hdmi-off', 'shutdown', 'unknown', ''):
        assert client.post(uri, data={**base, 'action': action,
                                     'name_confirmation': 'Lab Screen'}).status_code == 403
    assert not FakeAnthias.changes
    assert client.post(uri, data={**base, 'action': 'reboot',
                                  'csrf': 'bad'}).status_code == 400
    assert client.post(uri, data={**base, 'action': 'reboot',
                                  'ack': 'no'}).status_code == 400
    assert client.post(uri, data={**base, 'action': 'reboot',
                                  'confirm': 'other'}).status_code == 400
    assert not FakeAnthias.changes
    result = client.post(uri, data={**base, 'action': 'reboot'}, follow_redirects=True)
    assert result.status_code == 200
    assert b'Neustart angefordert' in result.data
    assert FakeAnthias.changes == [('system_power', ('reboot',), {})]


def test_viewer_cannot_post_any_remote_control(env):
    _, client, _ = env
    login(client, 'viewer')
    for action in ('hdmi-on', 'hdmi-off', 'reboot', 'shutdown'):
        r = client.post('/devices/lab/control', data={
            'csrf': token(client), 'confirm': 'lab', 'ack': 'yes',
            'action': action, 'name_confirmation': 'Lab Screen'})
        assert r.status_code == 403
    assert not FakeAnthias.changes


def test_shutdown_requires_exact_screen_name_and_registered_device(env):
    _, client, _ = env
    login(client, 'it')
    base = {'csrf': token(client), 'confirm': 'lab', 'ack': 'yes', 'action': 'shutdown'}
    for name in ('', 'lab', 'Lab Screen ', 'another'):
        assert client.post('/devices/lab/control', data={
            **base, 'name_confirmation': name}).status_code == 400
    assert client.post('/devices/missing/control', data=base).status_code == 404
    assert not FakeAnthias.changes


def test_device_control_errors_do_not_retry_or_claim_reboot_succeeded(env):
    _, client, _ = env
    login(client, 'it')
    original = FakeAnthias.system_power
    calls = []
    def disconnected(self, action):
        calls.append(action)
        raise anthias.PlayerError('Anthias nicht erreichbar')
    FakeAnthias.system_power = disconnected
    try:
        response = client.post('/devices/lab/control', data={
            'csrf': token(client), 'confirm': 'lab',
            'ack': 'yes', 'action': 'reboot'}, follow_redirects=True)
        assert response.status_code == 200
        assert 'Gerätebefehl nicht bestätigt'.encode() in response.data
        assert b'nicht blind erneut senden' in response.data
        assert calls == ['reboot']
        assert not FakeAnthias.changes
    finally:
        FakeAnthias.system_power = original


def test_anthias_remote_wrappers_use_only_static_v2_api_paths():
    p = anthias.Anthias({'url': 'http://192.168.1.25'})
    calls = []
    def fake_call(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return None
    p.call = fake_call
    p.display_power('on')
    p.display_power('off')
    p.system_power('reboot')
    p.system_power('shutdown')
    assert [(method, path) for method, path, _ in calls] == [
        ('POST', '/api/v2/display/on'),
        ('POST', '/api/v2/display/off'),
        ('POST', '/api/v2/reboot'),
        ('POST', '/api/v2/shutdown'),
    ]
    for cmd in ('../backup', 'reboot?redirect=bad', 'status'):
        with pytest.raises(anthias.PlayerError):
            p.system_power(cmd)
            # No arbitrary proxy path accepted.
    for state in ('../', 'toggle', 'off/../../shutdown'):
        with pytest.raises(anthias.PlayerError):
            p.display_power(state)
    assert len(calls) == 4

def test_ui_refresh_pages_have_well_nested_rendered_markup(env):
    """Catch misplaced closing tags in nested library options and the drawer."""
    from html.parser import HTMLParser
    from app.library import Library

    class Structure(HTMLParser):
        void = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img',
                          'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))
        def __init__(self):
            super().__init__()
            self.stack = []
            self.errors = []
        def handle_starttag(self, tag, attrs):
            if tag not in self.void:
                if tag == 'form' and tag in self.stack:
                    self.errors.append('nested form')
                self.stack.append(tag)
        def handle_endtag(self, tag):
            if tag in self.void:
                return
            if not self.stack or self.stack[-1] != tag:
                self.errors.append(f'closing {tag}, expected {self.stack[-1] if self.stack else "none"}')
                if tag in self.stack:
                    self.stack = self.stack[:self.stack.index(tag)]
            else:
                self.stack.pop()

    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    library = Library(app.config['LIBRARY_DIR'])
    template = library.create('Template')
    library.add_url(template['id'], 'Website', 'https://example.org', 15)
    urls = ('/login', '/', '/devices/lab', '/library', f"/library/{template['id']}")
    for role in ('marketing', 'it', 'viewer'):
        login(client, role)
        for url in urls:
            page = client.get(url)
            assert page.status_code == 200
            checker = Structure()
            checker.feed(page.get_data(as_text=True))
            assert not checker.errors, f'{role} {url}: {checker.errors[:5]}'
            assert not checker.stack, f'{role} {url}: unclosed {checker.stack[-5:]}'
        client.post('/logout', data={'csrf': token(client)})


def test_floating_device_menus_are_role_scoped_and_safe(env):
    _, client, _ = env
    login(client, 'it')
    dashboard = client.get('/').get_data(as_text=True)
    assert 'fleet-popovers.js' in dashboard
    assert 'Gerätesteuerung schließen' in dashboard
    assert 'Geräteverwaltung schließen' in dashboard
    assert 'data-close-fleet-menu' in dashboard
    assert 'name="name_confirmation"' in dashboard
    assert 'name="action" value="shutdown"' in dashboard

    client.post('/logout', data={'csrf': token(client)})
    login(client, 'marketing')
    dashboard = client.get('/').get_data(as_text=True)
    assert 'fleet-popovers.js' in dashboard
    assert 'Hilfe-Menü schließen' in dashboard
    assert 'Geräteverwaltung schließen' not in dashboard
    assert 'name="action" value="shutdown"' not in dashboard

    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    dashboard = client.get('/').get_data(as_text=True)
    assert 'fleet-popovers.js' not in dashboard
    assert 'data-close-fleet-menu' not in dashboard


def test_owner_has_both_roles_without_expanding_existing_role_grants(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    login(client, 'owner')
    assert b'OWNER' in client.get('/').data
    assert b'Ger\xc3\xa4testeuerung' in client.get('/').data
    assert b'data-can-edit="yes"' in client.get('/devices/lab').data
    assert client.post('/library', data={'csrf': token(client), 'name': 'Owner content'}).status_code == 302
    assert client.post('/devices/lab/control', data={
        'csrf': token(client), 'action': 'hdmi-on', 'confirm': 'lab', 'ack': 'yes'
    }).status_code == 302
    assert any(change[0] == 'display_power' for change in FakeAnthias.changes)
    assert client.post('/devices/lab/edit', data={
        'csrf': token(client), 'name': 'Lab Screen', 'url': 'http://192.168.1.55', 'location': 'Lab'
    }).status_code == 302

    login(client, 'marketing')
    assert client.post('/devices/lab/edit', data={'csrf': token(client)}).status_code == 403
    assert client.post('/devices/lab/control', data={
        'csrf': token(client), 'action': 'shutdown', 'confirm': 'lab', 'ack': 'yes'
    }).status_code == 403
    login(client, 'it')
    assert client.post('/library', data={'csrf': token(client), 'name': 'IT collection'}).status_code == 302
    login(client, 'viewer')
    assert client.post('/devices/lab/control', data={
        'csrf': token(client), 'action': 'reboot', 'confirm': 'lab', 'ack': 'yes'
    }).status_code == 403


# Large-media boundaries and device capacity are exercised by test_device_storage.py.


def test_fleet_renders_without_any_player_calls_and_storage_is_deferred(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'assets', side_effect=AssertionError('slow player call')) as assets, \
         patch.object(FakeAnthias, 'info', side_effect=AssertionError('slow info call'), create=True) as info:
        dashboard = client.get('/')
    assert dashboard.status_code == 200
    assert 'fleet-status.js' in dashboard.get_data(as_text=True)
    assert 'data-overview-state="pending"' in dashboard.get_data(as_text=True)
    assert 'Wird geprüft' in dashboard.get_data(as_text=True)
    assert 'data-fleet-online' in dashboard.get_data(as_text=True)
    assert 'data-storage-url=' in dashboard.get_data(as_text=True)
    assets.assert_not_called()
    info.assert_not_called()


def test_player_capacity_is_fetched_after_playlist_renders(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'info', side_effect=AssertionError('info must be lazy'), create=True) as info:
        playlist = client.get('/devices/lab').data.decode('utf-8')
    info.assert_not_called()
    assert 'Speicher wird geprüft' in playlist
    assert 'data-storage-loading="1"' in playlist
    assert 'data-player-available="0"' in playlist
    assert 'template-transfer.js' in playlist

    with patch.object(FakeAnthias, 'info', return_value={'free_space':'6.0 GB'}, create=True):
        disk = client.get('/devices/lab/storage')
    assert disk.status_code == 200 and disk.json['ok']
    assert disk.json['reported'] == '6.0 GB'
    assert disk.json['usable_bytes'] > 0


def test_device_overview_reports_actual_count_without_info_or_credentials(env):
    _, client, _ = env
    assert client.get('/devices/lab/overview').status_code in (302, 401, 403)
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'info', side_effect=AssertionError('unexpected info'), create=True) as info:
        response = client.get('/devices/lab/overview')
    info.assert_not_called()
    assert response.status_code == 200
    assert response.json == {'ok':True, 'count':len(FakeAnthias.assets_data)}
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/devices/does-not-exist/overview').status_code == 404
    with patch.object(FakeAnthias, 'assets', side_effect=anthias.PlayerError('device offline')):
        down = client.get('/devices/lab/overview')
    assert down.status_code == 200
    assert down.json == {'ok':False, 'count':None}


def test_storage_menu_is_small_and_only_shows_detail_on_demand(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'info', return_value={'free_space':'6.0 GB'}, create=True):
        board = client.get('/').data.decode('utf-8')
        player = client.get('/devices/lab').data.decode('utf-8')
        disk = client.get('/devices/lab/storage')
    assert 'fleet-storage-menu' in board
    assert 'Gerätespeicher von Lab Screen anzeigen' in board
    assert 'fleet-storage-panel' in board
    assert 'fleet-storage' not in board.split('<a class="button primary fleet-open"')[0]
    assert 'data-storage-status' in player
    assert 'data-storage-refresh' in player
    assert 'data-player-available="' in player
    assert 'storage-note' not in player
    assert '6.0 GB' not in player.split('<header class="playlist-hero device-page-hero">')[1].split('</header>')[0]
    assert disk.status_code == 200 and disk.json['ok']
    assert disk.json['usable_bytes'] > 0
    assert disk.headers['Cache-Control'] == 'no-store'


def test_storage_endpoint_unknown_does_not_unblock_uploads(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'info', return_value={}, create=True):
        response = client.get('/devices/lab/storage')
    assert response.status_code == 200
    assert not response.json['ok']
    assert response.json['usable_bytes'] == 0
    assert 'prüfen' in response.json['message']


def test_storage_endpoint_requires_auth_and_registered_player(env):
    _, client, _ = env
    assert client.get('/devices/lab/storage').status_code in (302, 401, 403)
    login(client, 'viewer')
    assert client.get('/devices/missing/storage').status_code == 404
    board = client.get('/').data.decode('utf-8')
    # No IT controls leaked to view-only users.
    assert 'fleet-settings-content' not in board


def test_storage_reason_and_override_only_for_unknown(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'info', side_effect=anthias.PlayerError('Anthias antwortete mit HTTP 404'), create=True):
        page = client.get('/devices/lab').data.decode('utf-8')
        disk = client.get('/devices/lab/storage')
    assert 'Speicher wird geprüft' in page
    assert 'data-storage-loading="1"' in page
    assert 'name="ignore_storage_check"' in page
    assert 'value="manual-confirmed"' in page
    assert disk.json['status'] == 'unknown'
    assert 'HTTP 404' in disk.json['message']
    with patch.object(FakeAnthias, 'info', return_value={'free_space': '2.0 GB'}, create=True):
        full_data = client.get('/devices/lab/storage')
    assert full_data.json['status'] == 'full'
    assert full_data.json['ok']
    # Browser only offers overrides after a genuinely unknown API response;
    # valid but insufficient capacity cannot be bypassed.
    assert 'data-storage-loading="1"' in page


def test_single_upload_forwards_manual_acknowledgement(env):
    _, client, _ = env
    login(client, 'marketing')
    media = b'\x89PNG\r\n\x1a\n' + b'bytes'
    calls = []
    original = FakeAnthias.upload
    def recording(self, *args, **kwargs):
        calls.append(kwargs.get('allow_unknown_space'))
        return original(self, *args, **kwargs)
    with patch.object(FakeAnthias, 'upload', recording):
        no_ack = client.post('/devices/lab/upload', data={
            'csrf':token(client),'media':(io.BytesIO(media),'x.png'),
            'duration':'15'},content_type='multipart/form-data')
        ack = client.post('/devices/lab/upload', data={
            'csrf':token(client),'media':(io.BytesIO(media),'x.png'),
            'duration':'15','ignore_storage_check':'manual-confirmed'},
            content_type='multipart/form-data')
    assert no_ack.status_code == 302 and ack.status_code == 302
    assert calls == [None, True]


def test_api_storage_reading_enables_upload_without_attestation(env, monkeypatch):
    _, client, _ = env
    login(client, 'marketing')
    monkeypatch.delenv('ANTHIAS_VERIFIED_STORAGE_URLS', raising=False)
    with patch.object(FakeAnthias, 'info', return_value={'free_space': '20.0 GB'}, create=True):
        response = client.get('/devices/lab/storage')
        page = client.get('/devices/lab').data.decode()
    assert response.json['status'] == 'ready'
    assert response.json['ok']
    assert response.json['reported'] == '20.0 GB'
    assert response.json['usable_bytes'] > 0
    assert 'Speicher wird geprüft' in page
    assert 'data-storage-loading="1"' in page
    assert 'data-player-available="0"' in page
    assert 'name="ignore_storage_check" value="manual-confirmed"' in page
    # Browser disables manual override while initial storage lookup is pending.


@pytest.mark.parametrize('code', [errno.ENOSPC, errno.EDQUOT])
def test_storage_creation_failure_has_controlled_response(env, code):
    _, client, _ = env
    login(client, 'marketing')
    with patch('app.web.Library.create', side_effect=OSError(code, 'storage failure')):
        response = client.post('/library', data={'csrf': token(client), 'name': 'Test'},
                               headers={'Accept': 'application/json'})
    assert response.status_code == 507
    assert response.json['ok'] is False
    assert 'Hub-Speicher' in response.json['error']


def test_dashboard_storage_popover_fetches_only_when_opened(env):
    _, client, _ = env
    login(client, 'marketing')
    dashboard = client.get('/').get_data(as_text=True)
    assert 'data-storage-url="/devices/lab/storage"' in dashboard
    assert 'fleet-status.js' in dashboard
    assert 'Anthias meldet frei' in dashboard
    assert 'data-storage-values hidden' in dashboard
    assert 'Wird beim Öffnen abgefragt' in dashboard
    assert 'data-storage-warning hidden' in dashboard


def test_folder_auto_targets_require_it_and_csrf(env, monkeypatch):
    app, marketing_client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    root = Path(tmp) / 'sources'
    (root / 'bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(app.config['LIBRARY_DIR'])
    ident = store.create('Auto Bistro')['id']

    login(marketing_client, 'marketing')
    assert marketing_client.post(f'/library/{ident}/folder-source',
                                 data={'csrf': token(marketing_client),
                                       'folder_source': 'bistro'}).status_code == 403
    assert marketing_client.post(f'/library/{ident}/auto-devices',
                                 data={'csrf': token(marketing_client),
                                       'devices': 'lab'}).status_code == 403
    assert 'Netzwerkquelle &amp; Zielbildschirme' not in (
        marketing_client.get(f'/library/{ident}').get_data(as_text=True))

    it_client = app.test_client()
    login(it_client, 'it')
    detail = it_client.get(f'/library/{ident}').get_data(as_text=True)
    assert 'Netzwerkquelle &amp; Zielbildschirme' in detail
    assert 'name="devices"' in detail
    assert it_client.post(f'/library/{ident}/folder-source',
                          data={'folder_source': 'bistro'}).status_code == 400
    assert not store.get(ident).get('folder_source')
    assert it_client.post(f'/library/{ident}/folder-source',
                          data={'csrf': token(it_client),
                                'folder_source': 'bistro'}).status_code == 302
    assert store.get(ident)['folder_source'] == 'bistro'
    assert it_client.post(f'/library/{ident}/auto-devices',
                          data={'csrf': token(it_client),
                                'devices': ['lab']}).status_code == 302
    assert store.get(ident)['auto_devices'] == ['lab']
    assert it_client.post(f'/library/{ident}/auto-devices',
                          data={'csrf': token(it_client),
                                'devices': ['unregistered']}).status_code == 302
    assert store.get(ident)['auto_devices'] == ['lab']

    # Revoking the source stops publication and clears the device opt-in.
    assert it_client.post(f'/library/{ident}/folder-source',
                          data={'csrf': token(it_client),
                                'folder_source': ''}).status_code == 302
    assert store.get(ident)['auto_devices'] == []


def test_folder_backed_marketing_view_is_duration_first_and_it_has_setup(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    from app.folder_sync import sync_template
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    root = Path(tmp) / 'sources'
    source = root / 'bistro'
    source.mkdir(parents=True)
    (root / 'empfang').mkdir()
    (source / 'banner.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'picture')
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    lib = Library(app.config['LIBRARY_DIR'])
    ident = lib.create('Bistro Screens')['id']
    lib.set_folder_source(ident, 'bistro')
    sync_template(lib, ident)
    lib.add_url(ident, 'Bistro custom RSS', 'http://192.0.2.55/feed', 30)
    item = next(x for x in lib.get(ident)['items'] if x.get('source_file'))

    login(client, 'marketing')
    marketing = client.get(f'/library/{ident}').get_data(as_text=True)
    assert 'Automatisch aus dem Netzwerkordner' in marketing
    assert 'name="duration"' in marketing
    assert 'name="folder_source"' not in marketing
    assert 'RSS2Slideshow / Web-Feed hinzufügen (IT)' not in marketing
    assert 'Bild oder Video speichern' not in marketing
    assert 'name="devices"' not in marketing
    assert 'Aus Netzwerkordner' in marketing
    assert client.post(f'/library/{ident}/items/{item["id"]}/duration',
                       data={'csrf': token(client), 'duration': '44'}).status_code == 302
    assert lib.get(ident)['items'][0]['duration'] == 44
    assert client.post(f'/library/{ident}/folder-source',
                       data={'csrf': token(client), 'folder_source': 'empfang'}).status_code == 403
    client.post('/logout', data={'csrf': token(client)})

    login(client, 'it')
    it = client.get(f'/library/{ident}').get_data(as_text=True)
    assert 'Webseite / RSS hinzufügen' in it
    assert 'name="folder_source"' in it
    assert 'value="bistro" selected' in it
    assert 'value="empfang"' in it
    assert 'name="devices"' in it
    assert 'name="duration"' in it
    assert 'Noch kein Importlauf gemeldet' in it
    client.post('/logout', data={'csrf': token(client)})

    login(client, 'viewer')
    viewer = client.get(f'/library/{ident}').get_data(as_text=True)
    assert 'class="library-duration-form"' not in viewer
    assert client.post(f'/library/{ident}/items/{item["id"]}/duration',
                       data={'csrf': token(client), 'duration': '23'}).status_code == 403


def test_it_can_add_and_edit_smb_sources_without_exposing_passwords(env, monkeypatch):
    app, client, tmp = env
    from app.media_sources import load_sources
    registry = Path(tmp) / 'media-sources.json'
    app.config['MEDIA_SOURCES_FILE'] = str(registry)
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'mount-status.json')
    mountroot = Path(tmp) / 'sources'
    (mountroot / 'bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(mountroot))
    login(client, 'it')
    page = client.get('/media-sources').get_data(as_text=True)
    assert '<h1 id="media-page-title">Ordner &amp; Quellen</h1>' in page
    assert 'bistro' in page
    assert 'root@' not in page
    assert 'name="unc"' in page
    assert 'Ordner &amp; Quellen' in client.get('/library').get_data(as_text=True)

    response = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'bistro',
        'unc': '//10.11.0.5/files$/Marketing/Bistro'})
    assert response.status_code == 302
    assert load_sources(registry)[0]['unc'] == '//10.11.0.5/files$/Marketing/Bistro'
    page = client.get('/media-sources').get_data(as_text=True)
    assert 'value="//10.11.0.5/files$/Marketing/Bistro"' in page
    assert 'Host-Mount noch ausstehend' in page
    assert 'files$' in page

    response = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'bistro',
        'unc': '//10.11.0.5/files$/Marketing/Updated'})
    assert response.status_code == 302
    assert load_sources(registry)[0]['unc'].endswith('/Updated')

    response = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'hack',
        'unc': '//8.8.8.8/public/content'})
    assert response.status_code == 302
    assert len(load_sources(registry)) == 1
    assert client.post('/media-sources',
                       data={'alias': 'test', 'unc': '//10.11.0.5/test'}).status_code == 400


def test_only_it_or_owner_can_change_smb_sources(env):
    app, client, tmp = env
    app.config['MEDIA_SOURCES_FILE'] = str(Path(tmp) / 'sources.json')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'status.json')
    for role in ('viewer', 'marketing'):
        login(client, role)
        assert client.get('/media-sources').status_code == 403
        assert client.post('/media-sources', data={
            'csrf': token(client), 'alias': 'screen',
            'unc': '//10.11.0.5/files$/Screen'}).status_code == 403
        assert 'href="/media-sources"' not in client.get('/').get_data(as_text=True)

    login(client, 'owner')
    assert client.get('/media-sources').status_code == 200
    assert client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'screen',
        'unc': '//10.11.0.5/files$/Screen'}).status_code == 302



def test_it_can_retire_unused_smb_source_but_never_mounted_files(env, monkeypatch):
    app, client, tmp = env
    from app.media_sources import load_sources, retired_aliases, save_source
    from app.folder_sync import available_sources, source_directory
    from app.library import Library, LibraryError
    reg = Path(tmp) / 'sources.json'
    root = Path(tmp) / 'sources'
    folder = root / 'default' / 'Bistro'
    folder.mkdir(parents=True)
    marker = folder / 'content.txt'
    marker.write_text('unchanged')
    libroot = Path(tmp) / 'library'
    app.config['LIBRARY_DIR'] = str(libroot)
    app.config['MEDIA_SOURCES_FILE'] = str(reg)
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'status.json')
    monkeypatch.setenv('MEDIA_SOURCES_FILE', str(reg))
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    save_source('default', '//10.11.0.5/files$/Screens', path=reg)
    assert available_sources() == ['default/Bistro']

    store = Library(libroot)
    template = store.create('Bistro')
    store.set_folder_source(template['id'], 'default/Bistro')
    login(client, 'it')
    page = client.get('/media-sources').get_data(as_text=True)
    assert 'Quelle aus dem Hub entfernen' in page
    assert 'Entfernen gesperrt' in page
    assert '/library/' + template['id'] in page

    # Protection is server-side even if the user bypasses the disabled UI.
    data = {'csrf': token(client), 'alias': 'default',
            'confirm': 'default', 'ack': 'yes'}
    assert client.post('/media-sources/remove', data=data).status_code == 302
    assert load_sources(reg)[0]['alias'] == 'default'
    assert marker.read_text() == 'unchanged'

    store.set_folder_source(template['id'], '')
    assert client.post('/media-sources/remove', data={
        'csrf': token(client), 'alias': 'default', 'confirm': 'other',
        'ack': 'yes',
    }).status_code == 302
    assert len(load_sources(reg)) == 1
    assert client.post('/media-sources/remove', data=data).status_code == 302
    assert load_sources(reg) == []
    assert retired_aliases(reg) == ['default']
    assert available_sources() == []
    with pytest.raises(LibraryError, match='ausgetragen'):
        source_directory('default/Bistro')
    assert marker.read_text() == 'unchanged'
    assert 'Ausgetragene Quellen' in client.get('/media-sources').get_data(as_text=True)

    # Re-registration is deliberate; the physical contents were never altered.
    assert client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'default',
        'unc': '//10.11.0.5/files$/Screens',
    }).status_code == 302
    assert retired_aliases(reg) == []
    assert available_sources() == ['default/Bistro']



def test_legacy_unmanaged_mount_can_be_hidden_without_unmounting(env, monkeypatch):
    app, client, tmp = env
    from app.folder_sync import available_sources, source_directory
    from app.media_sources import retired_aliases, load_sources
    from app.library import Library, LibraryError
    root = Path(tmp) / 'sources'
    folder = root / 'oldscreen'
    folder.mkdir(parents=True)
    marker = folder / 'keep.txt'
    marker.write_text('present')
    reg = Path(tmp) / 'sources.json'
    app.config['MEDIA_SOURCES_FILE'] = str(reg)
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'status.json')
    monkeypatch.setenv('MEDIA_SOURCES_FILE', str(reg))
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    assert available_sources() == ['oldscreen']
    assert load_sources(reg) == []
    store = Library(app.config['LIBRARY_DIR'])
    bound = store.create('Legacy')
    store.set_folder_source(bound['id'], 'oldscreen')
    login(client, 'it')
    page = client.get('/media-sources').get_data(as_text=True)
    assert 'Bereits am Host eingebundene Ordner' in page
    assert 'Entfernen gesperrt' in page
    action = {'csrf': token(client), 'alias': 'oldscreen',
              'confirm': 'oldscreen', 'ack': 'yes'}
    client.post('/media-sources/remove', data=action)
    assert retired_aliases(reg) == []

    store.set_folder_source(bound['id'], '')
    assert client.post('/media-sources/remove', data=action).status_code == 302
    assert retired_aliases(reg) == ['oldscreen']
    assert available_sources() == []
    with pytest.raises(LibraryError, match='ausgetragen'):
        source_directory('oldscreen')
    assert marker.read_text() == 'present'

    # Unknown aliases must not be accepted as arbitrary tombstones.
    client.post('/media-sources/remove', data={
        **action, 'alias': 'invisible', 'confirm': 'invisible'})
    assert retired_aliases(reg) == ['oldscreen']



def test_only_it_owner_may_retire_source_and_csrf_is_required(env):
    app, client, tmp = env
    from app.media_sources import load_sources, save_source
    registry = Path(tmp) / 'sources.json'
    app.config['MEDIA_SOURCES_FILE'] = str(registry)
    save_source('extra', '//10.11.0.5/files$/Extra', path=registry)
    data = {'alias': 'extra', 'confirm': 'extra', 'ack': 'yes'}
    for role in ('viewer', 'marketing'):
        login(client, role)
        assert client.post('/media-sources/remove', data={
            **data, 'csrf': token(client),
        }).status_code == 403
    login(client, 'it')
    assert client.post('/media-sources/remove', data=data).status_code == 400
    assert load_sources(registry)[0]['alias'] == 'extra'
    assert client.post('/media-sources/remove', data={
        **data, 'csrf': token(client),
    }).status_code == 302
    assert load_sources(registry) == []


def test_default_library_first_class_ui_and_one_click_folder_playlist(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    root = Path(tmp) / 'sources'
    bistro = root / 'default' / 'Demo-Screen-A'
    bistro.mkdir(parents=True)
    (bistro / 'banner.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'pic')
    (root / 'oldbistro').mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    app.config['MEDIA_SOURCES_FILE'] = str(Path(tmp) / 'media-sources.json')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'status.json')

    login(client, 'it')
    dash = client.get('/').get_data(as_text=True)
    assert 'id="fleet-devices"' in dash
    assert 'Ordner &amp; Quellen verwalten' in dash
    assert 'Ordner &amp; Quellen' in dash
    assert 'ui-system.css' in dash
    assert 'data-product-theme-toggle' in dash
    page = client.get('/media-sources')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Ein Netzwerkordner. Alle Bildschirme.' in html
    assert 'Demo-Screen-A' not in html  # selection moves to library
    assert '1 Unterordner im Hub sichtbar' in html
    assert 'Playlist-Bibliothek öffnen' in html
    assert 'value="default/Demo-Screen-A"' in client.get('/library').get_data(as_text=True)
    assert 'Als Playlist verwenden' not in html
    assert 'id="new-playlist"' in client.get('/library').get_data(as_text=True)
    assert 'name="alias" value="default"' in html
    assert 'Stammverzeichnis speichern' in html

    target = '/media-sources/folders/use'
    bad = client.post(target, data={'csrf': token(client), 'folder': '../escape'})
    assert bad.status_code == 302
    assert Library(app.config['LIBRARY_DIR']).list() == []

    result = client.post(target, data={'csrf': token(client),
                                       'folder': 'Demo-Screen-A'})
    assert result.status_code == 302
    store = Library(app.config['LIBRARY_DIR'])
    templates = store.list()
    assert len(templates) == 1
    assert templates[0]['folder_source'] == 'default/Demo-Screen-A'
    assert result.location.endswith('/library/' + templates[0]['id'])

    same = client.post(target, data={'csrf': token(client),
                                     'folder': 'Demo-Screen-A'})
    assert same.status_code == 302
    assert len(store.list()) == 1
    html = client.get(result.location).get_data(as_text=True)
    assert 'Standardbibliothek' in html
    assert 'Demo-Screen-A' in html

    login(client, 'marketing')
    assert client.post(target, data={'csrf': token(client),
                                     'folder': 'Demo-Screen-A'}).status_code == 403
    assert 'Ordner &amp; Quellen' not in client.get('/').get_data(as_text=True)
    assert 'Playlists verwalten' in client.get('/').get_data(as_text=True)


def test_it_legacy_network_bind_route_stays_safe_after_centralization(env, monkeypatch):
    """Legacy IT binding remains guarded, although its UI action moved to Playlists."""
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    root = Path(tmp) / 'sources'
    (root / 'default' / 'Bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(app.config['LIBRARY_DIR'])

    login(client, 'marketing')
    marketing_page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-add-mode="folder"' not in marketing_page
    assert 'data-add-pane="folder"' not in marketing_page
    assert client.post('/devices/lab/folder-playlist', data={
        'csrf': token(client), 'folder_source': 'default/Bistro'
    }).status_code == 403
    client.post('/logout', data={'csrf': token(client)})

    login(client, 'it')
    it_page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-add-mode="folder"' in it_page
    assert 'data-add-pane="folder"' in it_page
    assert 'value="default/Bistro"' in it_page
    assert 'Ordnerinhalt einmalig hinzufügen' in it_page
    assert 'Ordner-Playlists öffnen' in it_page
    assert '/devices/lab/folder-playlist' not in it_page

    invalid = client.post('/devices/lab/folder-playlist', data={
        'csrf': token(client), 'folder_source': 'default/../not-allowed'
    })
    assert invalid.status_code == 302
    assert store.list() == []

    first = client.post('/devices/lab/folder-playlist', data={
        'csrf': token(client), 'folder_source': 'default/Bistro'
    })
    assert first.status_code == 302
    templates = store.list()
    assert len(templates) == 1
    assert templates[0]['folder_source'] == 'default/Bistro'
    assert templates[0]['auto_devices'] == ['lab']
    assert first.location.endswith('/library/' + templates[0]['id'])

    second = client.post('/devices/lab/folder-playlist', data={
        'csrf': token(client), 'folder_source': 'default/Bistro'
    })
    assert second.status_code == 302
    assert len(store.list()) == 1
    assert FakeAnthias.changes == []  # Binding cannot mutate a live Pi playlist.
    linked_page = client.get('/devices/lab').get_data(as_text=True)
    assert 'Dieser Bildschirm wird über einen Netzwerkordner verwaltet' in linked_page
    assert 'Playlist verwalten' in linked_page
    assert 'Einzelne Pi-Inhalte anzeigen' in linked_page


def test_manual_network_folder_import_is_guarded_and_append_only(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    root = Path(tmp) / 'sources'
    media = root / 'default' / 'Bistro'
    media.mkdir(parents=True)
    (media / 'poster.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'poster')
    (media / 'screen.jpg').write_bytes(b'\xff\xd8' + b'photo')
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    url = '/devices/lab/import-network-folder'

    login(client, 'marketing')
    marketing = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-add-pane="folder"' not in marketing
    assert client.post(url, data={
        'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
        'folder_source': 'default/Bistro', 'duration': '30'
    }).status_code == 403
    assert not FakeAnthias.changes
    client.post('/logout', data={'csrf': token(client)})

    login(client, 'it')
    it = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-add-pane="folder"' in it
    assert 'name="folder_source"' in it
    assert '/import-network-folder' in it
    assert client.post(url, data={
        'csrf': token(client), 'confirm': 'once', 'folder_source': 'default/Bistro'
    }).status_code == 400  # explicit acknowledgement required

    assert client.post(url, data={
        'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
        'folder_source': 'default/../bad', 'duration': '30'
    }).status_code == 302
    assert not FakeAnthias.changes

    response = client.post(url, data={
        'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
        'folder_source': 'default/Bistro', 'duration': '30'
    })
    assert response.status_code == 302
    assert [event[0] for event in FakeAnthias.changes] == [
        'upload', 'create', 'upload', 'create'
    ]
    assert Library(app.config['LIBRARY_DIR']).list() == []
    assert all(event[0] != 'remove' for event in FakeAnthias.changes)


def test_manual_network_folder_preflight_rejects_bad_media_and_excess(env, monkeypatch):
    _, client, tmp = env
    root = Path(tmp) / 'sources'
    media = root / 'default' / 'Bistro'
    media.mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    login(client, 'it')
    url = '/devices/lab/import-network-folder'
    payload = {'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
               'folder_source': 'default/Bistro', 'duration': '15'}
    (media / 'bad.jpg').write_bytes(b'not a jpeg')
    response = client.post(url, data=payload, follow_redirects=True)
    assert response.status_code == 200
    assert 'Dateiformat' in response.get_data(as_text=True)
    assert not FakeAnthias.changes

    (media / 'bad.jpg').unlink()
    for i in range(21):
        (media / f'{i:02d}.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'x')
    response = client.post(url, data=payload, follow_redirects=True)
    assert 'Mehr als 20 Medien' in response.get_data(as_text=True)
    assert not FakeAnthias.changes


def test_player_composer_workflows_are_explicit_and_marketing_does_not_administer_folders(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').get_data(as_text=True)
    for mode in ('media', 'zip', 'library', 'website'):
        assert f'data-add-mode="{mode}"' in page
        assert f'data-add-pane="{mode}"' in page
    assert 'data-add-mode="folder"' not in page
    assert 'Medien-ZIP importieren' in page
    assert 'Noch keine gespeicherten Inhalte vorhanden.' in page
    assert 'Bestehende Playlist' in page or 'bestehende Playlist' in page


def test_template_apply_uses_central_ui_while_legacy_empty_route_is_guarded(env):
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    from app.library import Library
    library = Library(app.config['LIBRARY_DIR'])
    template = library.create('Bistro')
    library.add_url(template['id'], 'News', 'https://example.org/news', 30)
    login(client, 'marketing')
    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'Bestehende Playlist ergänzen · ganze Vorlage' not in page
    assert 'Leere Playlist initialisieren' not in page
    assert '/devices/lab/append-library' not in page
    assert '/devices/lab/apply-library' not in page
    central = client.get('/library/' + template['id']).get_data(as_text=True)
    assert 'data-library-drawer-pane="apply"' in central
    assert 'Alternative: nur leeren Pi initialisieren' in central
    assert '/append-to-device' in central
    refused = client.post('/devices/lab/apply-library', data={
        'csrf': token(client), 'template_id': template['id'], 'confirm': 'yes'
    }, follow_redirects=True)
    assert refused.status_code == 200
    assert 'nicht leer' in refused.get_data(as_text=True)
    assert FakeAnthias.changes == []


def test_every_user_facing_page_uses_same_ui_revision_and_single_stylesheet(env):
    """All roles and routes share one final, cache-distinct UI skin."""
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    sample = Library(app.config['LIBRARY_DIR']).create('Smoke UI')
    pages = ['/login']
    response = client.get('/login')
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'content="ui-20261113-03"' in text
    assert 'ui-system.css' in text
    assert 'data-hub-build-sha="dev"' in text
    assert 'UI <code>ui-20261113-03</code>' in text
    assert all(f"filename='{name}'" not in text for name in (
        'product-ui.css', 'ui-refinements.css', 'workflow-ui.css'))

    login(client, 'it')
    pages = ['/', '/library', f"/library/{sample['id']}",
             '/devices/lab', '/devices/lab/schedules', '/media-sources']
    for path in pages:
        result = client.get(path)
        assert result.status_code == 200, path
        text = result.get_data(as_text=True)
        assert 'content="ui-20261113-03"' in text, path
        assert text.count('ui-system.css') == 1, path
        assert 'data-product-theme-toggle' in text, path
        assert 'class="site-main"' not in text or 'id="hauptinhalt"' in text
    assert client.get('/static/ui-system.css').status_code == 200


def test_footer_build_metadata_tracks_the_running_image_not_the_requested_tag(env):
    app, client, _ = env
    sha = 'a19b53c47c8b9a1c6317dc34e884760db06aeeaf'
    # Simulates the exact immutable commit written at Docker build time.
    app.config['HUB_BUILD_SHA'] = sha
    page = client.get('/login').get_data(as_text=True)
    assert f'content="{sha}"' in page
    assert f'data-hub-build-sha="{sha}"' in page
    assert f'/ffworker/anthias-hub/commit/{sha}' in page
    assert sha[:12] in page
    assert 'lokal/dev' not in page


def test_screens_are_the_real_landing_and_playlists_have_consistent_actions(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    tpl = Library(app.config['LIBRARY_DIR']).create('Testvorlage')

    first = client.get('/login')
    assert first.status_code == 200
    logged = client.post('/login', data={
        'csrf': token(client), 'username': 'it', 'password': 'safe-password-123'
    })
    assert logged.status_code == 302
    assert logged.location == '/'  # dashboard/screens, never SMB admin

    page = client.get('/').get_data(as_text=True)
    assert page.index('Bildschirme</a>') < page.index('Playlists</a>') < page.index('Ordner &amp; Quellen</a>')
    assert page.index('id="fleet-devices"') < page.index('class="hub-next-steps"')
    assert 'Playlists verwalten' in page
    assert 'Ordner &amp; Quellen' in page
    assert 'ui-system.css?v=ui-20261113-03' in page

    libpage = client.get('/library').get_data(as_text=True)
    assert libpage.index('id="library-page-title"') < libpage.index('class="library-grid library-index-grid"')
    assert 'library-action-disclosure' not in libpage
    assert 'id="new-playlist" data-library-drawer-pane="create"' in libpage
    assert 'id="backup-zip" data-library-drawer-pane="backup"' in libpage
    assert 'class="library-actions"' not in libpage
    assert libpage.index('id="library-list-title"') < libpage.index('id="new-playlist"')

    detail = client.get('/library/' + tpl['id']).get_data(as_text=True)
    order = ['id="items-title"', 'Einzeldatei hinzufügen',
             'ZIP / mehrere Dateien importieren', 'Webseite / RSS hinzufügen',
             'id="playlist-anwenden"', 'Netzwerkquelle &amp; Zielbildschirme']
    indices = [detail.index(x) for x in order]
    assert indices == sorted(indices)
    assert 'data-library-drawer-pane="settings"' in detail
    assert 'class="library-drawer-backdrop"' in detail
    assert 'data-library-drawer-pane="settings"' in detail
    assert 'library-action-disclosure' not in detail
    assert FakeAnthias.changes == []

    client.post('/logout', data={'csrf': token(client)})
    login(client, 'marketing')
    marketing = client.get('/library/' + tpl['id']).get_data(as_text=True)
    assert 'id="network-settings"' not in marketing
    assert 'Einzeldatei hinzufügen' in marketing
    assert 'ZIP / mehrere Dateien importieren' in marketing
    assert 'Vorlage zur Playlist hinzufügen' in marketing


def test_zero_state_discovers_single_smb_parent_without_individual_mounts(env, monkeypatch):
    """Fresh state: one root mount exposes direct child folders as playlist sources."""
    app, client, tmp = env
    from app.folder_sync import available_sources, default_library_folders, sync_template
    from app.library import Library
    root = Path(tmp) / 'sources'
    root.mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.delenv('FOLDER_REQUIRE_MOUNT', raising=False)
    monkeypatch.delenv('FOLDER_REQUIRE_VERIFIED', raising=False)
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'fresh-library')
    app.config['MEDIA_SOURCES_FILE'] = str(Path(tmp) / 'fresh-sources.json')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'fresh-status.json')
    assert not Path(app.config['MEDIA_SOURCES_FILE']).exists()
    assert Library(app.config['LIBRARY_DIR']).list() == []

    login(client, 'it')
    first = client.get('/media-sources').get_data(as_text=True)
    assert '0 Unterordner im Hub sichtbar' in first
    assert 'Stammverzeichnis speichern' in first
    assert client.get('/library').status_code == 200
    assert client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'default',
        'unc': '//10.20.30.40/media$/DigitalSignage'
    }).status_code == 302
    # Saving only registers a UNC; the host must still mount it.
    assert not (root / 'default').exists()
    assert available_sources() == []

    shared = root / 'default'
    (shared / 'Entrance').mkdir(parents=True)
    (shared / 'Bistro').mkdir()
    (shared / '.hidden').mkdir()
    (shared / 'Entrance' / 'nested').mkdir()
    (shared / 'Bistro' / 'image.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'picture')
    outside = Path(tmp) / 'outside'
    outside.mkdir()
    (shared / 'escaping').symlink_to(outside, target_is_directory=True)
    assert default_library_folders() == ['Bistro', 'Entrance']
    assert available_sources() == ['default/Bistro', 'default/Entrance']

    page = client.get('/library').get_data(as_text=True)
    assert 'value="default/Bistro"' in page
    assert 'value="default/Entrance"' in page
    assert 'value="default/.hidden"' not in page
    created = client.post('/library', data={
        'csrf': token(client), 'name': 'Demo Signage',
        'folder_source': 'default/Bistro'
    })
    assert created.status_code == 302
    templates = Library(app.config['LIBRARY_DIR']).list()
    assert len(templates) == 1
    assert templates[0]['folder_source'] == 'default/Bistro'
    assert templates[0].get('auto_devices', []) == []
    assert FakeAnthias.changes == []

    result = sync_template(Library(app.config['LIBRARY_DIR']), templates[0]['id'])
    assert result['added'] == 1
    assert FakeAnthias.changes == []


def test_existing_imported_playlist_refuses_unsafe_folder_alias_rebind(env, monkeypatch):
    """Never silently lose imported durations and IDs when old mounts are removed."""
    app, _, tmp = env
    from app.folder_sync import sync_template
    from app.library import Library, LibraryError
    root = Path(tmp) / 'sources'
    old = root / 'legacy'
    target = root / 'default' / 'Bistro'
    old.mkdir(parents=True)
    target.mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.delenv('FOLDER_REQUIRE_MOUNT', raising=False)
    monkeypatch.delenv('FOLDER_REQUIRE_VERIFIED', raising=False)
    media = b'\x89PNG\r\n\x1a\n' + b'picture'
    (old / 'image.png').write_bytes(media)
    (target / 'image.png').write_bytes(media)
    store = Library(str(Path(tmp) / 'library'))
    ident = store.create('Existing Bistro')['id']
    store.set_folder_source(ident, 'legacy')
    assert sync_template(store, ident)['added'] == 1
    before = store.get(ident)
    assert before['items'][0]['source_file'] == 'image.png'
    with pytest.raises(LibraryError, match='bereits importierte Medien'):
        store.set_folder_source(ident, 'default/Bistro')
    after = store.get(ident)
    assert after['folder_source'] == before['folder_source'] == 'legacy'
    assert after['items'] == before['items']
    assert FakeAnthias.changes == []


def test_smb_ui_reports_verified_mount_only_for_fresh_matching_host_status(env, monkeypatch):
    """Saving an SMB path is not proof of a mounted share, also on the dashboard."""
    import hashlib
    import json
    import time

    app, client, tmp = env
    from app.media_sources import save_source
    reg = Path(tmp) / 'new-ui-media-sources.json'
    status_file = Path(tmp) / 'new-ui-mount-status.json'
    root = Path(tmp) / 'sources'
    (root / 'default' / 'Screen-A').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['MEDIA_SOURCES_FILE'] = str(reg)
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(status_file)
    smb = '//10.12.0.4/files$/Marketing'
    save_source('default', smb, path=reg)
    login(client, 'it')

    unconfirmed = client.get('/media-sources').get_data(as_text=True)
    assert 'Mount unbestätigt' in unconfirmed
    assert 'Host-Mount noch ausstehend' in unconfirmed
    assert 'Eingehängt · Host bestätigt' not in unconfirmed
    assert 'Gespeicherter SMB-Pfad' in unconfirmed
    assert '/srv/anthias-sources/default' in unconfirmed
    assert 'Stammverzeichnis aktualisieren' in unconfirmed
    assert 'Erkannte Unterordner ansehen' not in unconfirmed
    assert 'Ordner im Container sichtbar, aber der Host-Mount ist nicht bestätigt' in unconfirmed
    assert 'Stammordner: Host-Mount nicht bestätigt' in client.get('/').get_data(as_text=True)

    status_file.write_text(json.dumps({'checked_at': time.time(), 'sources': {
        'default': {'state': 'mounted',
                    'fingerprint': hashlib.sha256(smb.encode()).hexdigest()}
    }}))
    confirmed = client.get('/media-sources').get_data(as_text=True)
    assert 'Eingehängt · Host bestätigt' in confirmed
    assert '1 Unterordner im Hub sichtbar' in confirmed
    assert 'Erkannte Bildschirmordner' in confirmed
    assert 'Screen-A' in confirmed
    assert 'Playlist mit Netzwerkordner erstellen' in confirmed
    assert 'Stammordner: Host-Mount bestätigt' in client.get('/').get_data(as_text=True)

    # Staleness cannot impersonate proof of a live/recent host check.
    status_file.write_text(json.dumps({'checked_at': time.time() - 3600, 'sources': {
        'default': {'state': 'mounted',
                    'fingerprint': hashlib.sha256(smb.encode()).hexdigest()}
    }}))
    stale = client.get('/media-sources').get_data(as_text=True)
    assert 'Mount unbestätigt' in stale
    assert 'Eingehängt · Host bestätigt' not in stale

    # A successful status from the previous UNC is not valid after a path edit.
    status_file.write_text(json.dumps({'checked_at': time.time(), 'sources': {
        'default': {'state': 'mounted', 'fingerprint': 'older-unc'}
    }}))
    mismatch = client.get('/media-sources').get_data(as_text=True)
    assert 'Mount unbestätigt' in mismatch
    assert 'Eingehängt · Host bestätigt' not in mismatch


def test_smb_ui_displays_existing_and_legacy_sources_before_extra_setup(env, monkeypatch):
    from app.media_sources import save_source
    app, client, tmp = env
    reg = Path(tmp) / 'ui-source-registry.json'
    app.config['MEDIA_SOURCES_FILE'] = str(reg)
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'empty-state.json')
    source_root = Path(tmp) / 'sources'
    (source_root / 'legacy-pi').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(source_root))
    save_source('other', '//10.12.0.4/files$/Reception', path=reg)
    login(client, 'it')
    page = client.get('/media-sources').get_data(as_text=True)
    assert 'Weitere Quellen' in page
    assert 'legacy-pi' in page
    assert 'CIFS-Mount nicht bestätigt' in page
    assert 'Host-Mount noch ausstehend' in page
    assert page.index('REGISTRIERTE EINZELQUELLE') < page.index('Weitere SMB-Quelle hinzufügen')
    assert page.index('ALTER HOST-MOUNT / NICHT REGISTRIERT') < page.index('Weitere SMB-Quelle hinzufügen')
    assert 'Quelle aus dem Hub entfernen' in page

    # The mountinfo inspector, not the mere presence of a folder, upgrades
    # the legacy badge to "CIFS-Mount erkannt".
    with patch('app.media_sources.observed_mount_source', return_value='//10.12.0.4/files$'):
        observed = client.get('/media-sources').get_data(as_text=True)
    assert 'CIFS-Mount erkannt' in observed


def _manual_folder_events(response):
    assert response.mimetype == 'text/event-stream'
    return [json.loads(line[6:]) for line in response.get_data(as_text=True).splitlines()
            if line.startswith('data: ')]


def test_manual_folder_stream_reports_confirmed_file_counts(env, monkeypatch):
    app, client, tmp = env
    root = Path(tmp) / 'sources'
    folder = root / 'bistro'
    folder.mkdir(parents=True)
    png = b'\x89PNG\r\n\x1a\n' + b'test image'
    (folder / 'alpha.png').write_bytes(png)
    (folder / 'beta.png').write_bytes(png)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['SCHEDULES_FILE'] = str(Path(tmp) / 'schedules.json')
    login(client, 'it')
    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-network-import-form' in page
    assert 'data-network-import-counter' in page
    assert 'network-folder-import.js' in page
    # A checkbox inside a flex label used to consume 100% of the row and
    # squeeze the confirmation text into a one-letter-wide column.
    assert 'class="network-import-ack"' in page
    assert 'id="network-folder-ack-lab"' in page
    assert 'for="network-folder-ack-lab"' in page
    assert 'class="append-confirm"' not in page
    skin = (Path(__file__).resolve().parents[1] / 'app/static/ui-system.css').read_text(encoding='utf-8')
    assert '>.network-import-ack>input[type="checkbox"]' in skin
    assert '>.network-import-ack>label' in skin

    response = client.post('/devices/lab/import-network-folder', data={
        'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
        'folder_source': 'bistro', 'duration': '15', 'progress_stream': '1',
    })
    assert response.status_code == 200
    assert response.headers['X-Accel-Buffering'] == 'no'
    events = _manual_folder_events(response)
    assert [event['type'] for event in events] == [
        'preparing', 'start', 'active', 'progress', 'active', 'progress', 'complete'
    ]
    assert [(event['done'], event['total']) for event in events
            if event['type'] == 'progress'] == [(1, 2), (2, 2)]
    assert events[-1]['done'] == events[-1]['total'] == 2
    assert sum(action[0] == 'upload' for action in FakeAnthias.changes) == 2
    assert sum(action[0] == 'create' for action in FakeAnthias.changes) == 2


def test_manual_folder_stream_preserves_partial_failure_warning(env, monkeypatch):
    app, client, tmp = env
    root = Path(tmp) / 'sources'
    folder = root / 'bistro'
    folder.mkdir(parents=True)
    png = b'\x89PNG\r\n\x1a\n' + b'image'
    (folder / 'a.png').write_bytes(png)
    (folder / 'b.png').write_bytes(png)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['SCHEDULES_FILE'] = str(Path(tmp) / 'schedules.json')
    original_upload = FakeAnthias.upload

    def second_upload_fails(self, stream, filename, mime):
        if filename == 'b.png':
            raise anthias.PlayerError('Geräteübertragung fehlgeschlagen')
        return original_upload(self, stream, filename, mime)

    monkeypatch.setattr(FakeAnthias, 'upload', second_upload_fails)
    login(client, 'it')
    response = client.post('/devices/lab/import-network-folder', data={
        'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
        'folder_source': 'bistro', 'duration': '15', 'progress_stream': '1',
    })
    events = _manual_folder_events(response)
    assert events[-1]['type'] == 'error'
    assert events[-1]['done'] == 1 and events[-1]['total'] == 2
    assert 'nicht blind wiederholen' in events[-1]['message']
    assert sum(action[0] == 'create' for action in FakeAnthias.changes) == 1


def test_manual_folder_stream_preflight_and_native_fallback(env, monkeypatch):
    app, client, tmp = env
    root = Path(tmp) / 'sources'
    folder = root / 'bistro'
    folder.mkdir(parents=True)
    (folder / 'invalid.png').write_bytes(b'not a PNG')
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['SCHEDULES_FILE'] = str(Path(tmp) / 'schedules.json')
    login(client, 'it')
    data = {'csrf': token(client), 'confirm': 'once', 'ack': 'yes',
            'folder_source': 'bistro', 'duration': '15'}
    response = client.post('/devices/lab/import-network-folder',
                           data={**data, 'progress_stream': '1'})
    events = _manual_folder_events(response)
    assert events[-1]['type'] == 'error'
    assert events[-1]['done'] == 0
    assert 'Dateiformat' in events[-1]['message']
    assert not FakeAnthias.changes
    # JavaScript-free form must still be a normal redirect + flash.
    native = client.post('/devices/lab/import-network-folder', data=data, follow_redirects=False)
    assert native.status_code == 302
    assert native.location.endswith('/devices/lab')
    assert not FakeAnthias.changes


def test_bound_folder_playlist_is_visible_and_player_content_is_read_only(env, monkeypatch):
    """One permanent folder assignment owns screen media even when publisher is off."""
    app, client, tmp = env
    from app.library import Library, LibraryError
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    source = Path(tmp) / 'sources'
    (source / 'bistro').mkdir(parents=True)
    (source / 'empfang').mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(source))
    store = Library(app.config['LIBRARY_DIR'])
    template = store.create('Bistro Wochenplan')
    store.set_folder_source(template['id'], 'bistro')
    store.set_auto_devices(template['id'], ['lab'],
                           [{'id': 'lab'}])

    login(client, 'it')
    home = client.get('/').get_data(as_text=True)
    assert 'Playlist fest zugeordnet · Direktbearbeitung gesperrt' in home
    assert 'Bistro Wochenplan' in home
    assert f'/library/{template["id"]}' in home
    assert 'Playlist ansehen' in home
    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-managed-playlist' in page
    assert 'Bistro Wochenplan' in page
    assert '<code>bistro</code>' in page
    assert 'Übertragung auf den Pi:' in page and 'Noch deaktiviert' in page
    assert 'data-managed-player-assets' in page
    assert '<details class="managed-player-assets" data-managed-player-assets>' in page
    assert page.index('data-managed-playlist') < page.index('data-managed-player-assets')
    assert page.index('data-managed-player-assets') < page.index('id="playlist-items"')
    assert 'Einzelne Pi-Inhalte anzeigen' in page
    assert 'data-can-edit="no"' in page
    assert 'data-open-composer' not in page
    assert 'data-reorder-url=' not in page
    assert 'asset-inline-edit' not in page
    assert 'data-bulk-management' not in page
    assert 'data-bulk-check' not in page
    assert 'data-media-lightbox' in page  # Read-only preview remains available.

    # A stale form or an external call must not bypass the read-only page.
    blocked = [
        ('/devices/lab/add-url', {}),
        ('/devices/lab/upload', {}),
        ('/devices/lab/bulk-media', {}),
        ('/devices/lab/import-network-folder', {}),
        ('/devices/lab/add-library-item', {}),
        ('/devices/lab/append-library', {}),
        ('/devices/lab/apply-library', {}),
        ('/devices/lab/assets/one123/edit', {}),
        ('/devices/lab/assets/one123/move', {}),
        ('/devices/lab/reorder', {}),
        ('/devices/lab/assets/one123/toggle', {}),
        ('/devices/lab/assets/one123/schedule', {}),
        ('/devices/lab/assets/one123/delete', {}),
        ('/devices/lab/bulk-delete', {}),
        (f'/library/{template["id"]}/apply', {'device': 'lab'}),
        (f'/library/{template["id"]}/append-to-device', {'device': 'lab'}),
        (f'/library/{template["id"]}/items/placeholder/add-to-device',
         {'device': 'lab'}),
    ]
    for path, payload in blocked:
        response = client.post(path, data={'csrf': token(client), **payload})
        assert response.status_code == 409, path
        assert 'Ordner-Playlist zugeordnet' in response.get_data(as_text=True)
    assert not FakeAnthias.changes

    # Direct content controls return only after unassigning this screen.
    store.set_auto_devices(template['id'], [], [{'id': 'lab'}])
    unbound = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-managed-playlist' not in unbound
    assert 'data-managed-player-assets' not in unbound
    assert 'data-can-edit="yes"' in unbound
    assert 'data-open-composer' in unbound
    assert client.post('/devices/lab/add-url', data={
        'csrf': token(client), 'name': 'Wieder manuell',
        'url': 'https://example.org/info', 'duration': '30',
    }).status_code == 302
    assert any(event[0] == 'create' for event in FakeAnthias.changes)


def test_screen_cannot_have_two_conflicting_folder_playlist_owners(env, monkeypatch):
    from app.library import Library, LibraryError
    app, client, tmp = env
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    source = Path(tmp) / 'sources'
    (source / 'first').mkdir(parents=True)
    (source / 'second').mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(source))
    store = Library(app.config['LIBRARY_DIR'])
    first = store.create('Bistro')
    second = store.create('Empfang')
    store.set_folder_source(first['id'], 'first')
    store.set_folder_source(second['id'], 'second')
    known = [{'id': 'lab'}]
    store.set_auto_devices(first['id'], ['lab'], known)
    with pytest.raises(LibraryError, match='bereits der Playlist'):
        store.set_auto_devices(second['id'], ['lab'], known)
    assert store.get(second['id']).get('auto_devices') in (None, [])
    login(client, 'it')
    refused = client.post(f"/library/{first['id']}/delete", data={
        'csrf': token(client), 'confirm': first['id'],
        'ack': 'yes', 'name_confirmation': 'Bistro',
    }, follow_redirects=True)
    assert refused.status_code == 200
    assert 'Erst Zielbildschirme' in refused.get_data(as_text=True)
    assert store.get(first['id'])['auto_devices'] == ['lab']


def test_managed_screens_announce_same_source_on_dashboard_schedule_and_library(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    from app.folder_status import write_status
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    source = Path(tmp) / 'sources'
    (source / 'bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(source))
    store = Library(app.config['LIBRARY_DIR'])
    t = store.create('Bistro Hauptplaylist')
    store.set_folder_source(t['id'], 'bistro')
    store.set_auto_devices(t['id'], ['lab'], [{'id': 'lab'}])
    heartbeat = Path(tmp) / 'folder-sync.json'
    monkeypatch.setenv('FOLDER_STATUS_FILE', str(heartbeat))
    write_status({t['id']: {'import': {'added': 1, 'updated': 0},
                            'devices': {'lab': {'added': 1, 'updated': 0, 'disabled': 0}}}},
                 True, heartbeat, interval_seconds=1800)
    login(client, 'it')
    dashboard = client.get('/').get_data(as_text=True)
    player = client.get('/devices/lab').get_data(as_text=True)
    schedules = client.get('/devices/lab/schedules').get_data(as_text=True)
    index = client.get('/library').get_data(as_text=True)
    detail = client.get(f"/library/{t['id']}").get_data(as_text=True)
    for page in (dashboard, player, schedules, index, detail):
        assert 'Bistro Hauptplaylist' in page
        assert f"/library/{t['id']}" in page or page == detail
    assert '30 Min.' in dashboard
    assert 'Alle 30 Minuten' in player
    assert '30 Min.' in index
    assert '30 Minuten' in detail
    assert 'Pi-Abgleich: aktiv' in dashboard
    assert 'Pi-Veröffentlichung: aktiv' in index
    assert 'Zugeordnete Playlist' in player
    assert 'Playlist-gesteuerter Bildschirm' in schedules
    assert 'data-schedule-assign' not in schedules  # Read-only.
    assert client.post('/devices/lab/schedules/apply',
                       data={'csrf': token(client)}).status_code == 409
    assert client.post('/devices/lab/schedules/demo/edit',
                       data={'csrf': token(client),
                             'sync_assigned': 'yes'}).status_code == 409
    assert client.post('/schedules/demo/edit',
                       data={'csrf': token(client),
                             'sync_device': 'lab'}).status_code == 409
    assert not FakeAnthias.changes


def test_explicit_development_mode_unlocks_managed_player_without_changing_default(env, monkeypatch):
    """On a separate test installation management remains visible but not a blocker."""
    app, client, tmp = env
    from app.library import Library
    root = Path(tmp) / 'sources'
    (root / 'demo').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    lib = Library(app.config['LIBRARY_DIR'])
    template = lib.create('Demo-Ordner')
    lib.set_folder_source(template['id'], 'demo')
    lib.set_auto_devices(template['id'], ['lab'], [{'id':'lab'}])
    app.config['HUB_DEVELOPMENT_MODE'] = True
    login(client, 'it')
    screen = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-managed-playlist' in screen
    assert 'data-can-edit="yes"' in screen
    assert 'TESTSYSTEM · Bearbeiten erlaubt' in screen
    assert 'data-open-composer' in screen
    assert 'data-managed-player-assets open' in screen
    dash = client.get('/').get_data(as_text=True)
    assert 'Playlist zugeordnet · Testmodus: bearbeiten erlaubt' in dash
    assert 'Inhalte testen' in dash
    schedule = client.get('/devices/lab/schedules').get_data(as_text=True)
    assert 'TESTMODUS: Zeitpläne bearbeiten erlaubt' in schedule
    assert 'data-schedule-assign' in schedule
    response = client.post('/devices/lab/add-url', data={
        'csrf': token(client), 'name': 'Testquelle',
        'url': 'https://example.org', 'duration': '30',
    })
    assert response.status_code == 302
    edit = client.post('/devices/lab/assets/one123/edit', data={
        'csrf': token(client), 'name': 'Experiment', 'duration': '25',
    })
    assert edit.status_code == 302
    assert any(event[0] == 'create' for event in FakeAnthias.changes)
    assert any(event[0] == 'patch' for event in FakeAnthias.changes)
    assert lib.get(template['id'])['auto_devices'] == ['lab']


def test_development_mode_reassigns_already_managed_screen_without_touching_pi(env, monkeypatch):
    """Move target between folder playlists with one save; normal mode still refuses."""
    app, client, tmp = env
    from app.library import Library
    root = Path(tmp) / 'sources'
    (root / 'alpha').mkdir(parents=True)
    (root / 'beta').mkdir()
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    store = Library(app.config['LIBRARY_DIR'])
    first = store.create('Alpha')
    second = store.create('Beta')
    store.set_folder_source(first['id'], 'alpha')
    store.set_folder_source(second['id'], 'beta')
    store.set_auto_devices(first['id'], ['lab'], [{'id':'lab'}])
    login(client, 'it')
    t = token(client)
    refused = client.post(f"/library/{second['id']}/auto-devices",
                          data={'csrf': t, 'devices': ['lab']}, follow_redirects=True)
    assert refused.status_code == 200
    assert 'bereits der Playlist' in refused.get_data(as_text=True)
    assert store.get(first['id'])['auto_devices'] == ['lab']
    app.config['HUB_DEVELOPMENT_MODE'] = True
    changed = client.post(f"/library/{second['id']}/auto-devices",
                          data={'csrf': t, 'devices': ['lab']}, follow_redirects=True)
    assert changed.status_code == 200
    assert 'Testmodus: Zielzuordnung gespeichert' in changed.get_data(as_text=True)
    assert store.get(first['id'])['auto_devices'] == []
    assert store.get(second['id'])['auto_devices'] == ['lab']
    assert FakeAnthias.changes == []


def test_v2_single_owner_disables_duplicate_device_editing_even_in_dev(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    app.config['HUB_DEVELOPMENT_MODE'] = True
    app.config['HUB_WORKFLOW_V2'] = True
    store = Library(app.config['LIBRARY_DIR'])
    one = store.create('Zentrale Playlist')
    store.set_auto_devices(one['id'], ['lab'], [{'id':'lab'}],
                           replace_existing=True, allow_manual=True)
    login(client, 'it')
    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-screen-mode="playlist"' in page
    assert 'Zentrale Playlist' in page
    assert 'data-open-composer' not in page
    assert 'Einzelne Pi-Inhalte anzeigen' not in page

    guessed = client.get('/devices/lab?editor=1').get_data(as_text=True)
    assert 'data-screen-mode="playlist"' in guessed
    assert 'data-open-composer' not in guessed
    assert 'add-content' not in guessed

    for path, params in [
        ('/devices/lab/add-url', {'name': 'Verboten', 'url': 'https://example.org',
                                  'duration': '30'}),
        ('/devices/lab/schedules/apply', {'profile_id': 'always'}),
        ('/devices/lab/schedules/default', {'profile_id': 'always'}),
        ('/devices/lab/reorder', {}),
        (f"/library/{one['id']}/append-to-device",
         {'device': 'lab', 'confirm': 'append', 'ack': 'yes'}),
    ]:
        assert client.post(path, data={'csrf': token(client), **params}).status_code == 409, path
    assert not FakeAnthias.changes

    index = client.get('/library').get_data(as_text=True)
    detail = client.get(f"/library/{one['id']}").get_data(as_text=True)
    assert 'ZENTRALE INHALTE' in index
    assert 'Playlist zuordnen' in detail
    assert 'Einmalige Übertragung' not in detail
    assert f"/library/{one['id']}/auto-devices" in detail


def test_v2_manual_empty_network_have_different_only_one_editor(env, monkeypatch):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    app.config['HUB_WORKFLOW_V2'] = True
    app.config['HUB_DEVELOPMENT_MODE'] = True
    login(client, 'it')

    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-screen-mode="manual"' in page
    assert 'Manuelle Inhalte bearbeiten' in page
    assert 'Netzwerkordner-Anzeige' not in page
    assert client.get('/devices/lab?editor=1').status_code == 200

    monkeypatch.setattr(FakeAnthias, 'assets_data', [])
    empty = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-screen-mode="empty"' in empty
    assert 'Manuellen Inhalt hinzufügen' in empty

    root = Path(tmp) / 'sources'
    (root / 'bistro').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    store = Library(app.config['LIBRARY_DIR'])
    folder = store.create('Bistro Ordner')
    store.set_folder_source(folder['id'], 'bistro')
    store.set_auto_devices(folder['id'], ['lab'], [{'id': 'lab'}],
                           allow_manual=True)
    network = client.get('/devices/lab').get_data(as_text=True)
    assert 'data-screen-mode="network"' in network
    assert '<code>bistro</code>' in network
    assert 'Manuellen Inhalt hinzufügen' not in network
    assert 'data-open-composer' not in network
    assert 'data-screen-mode="network"' in client.get('/devices/lab?editor=1').get_data(as_text=True)


def test_v2_source_live_status_endpoint_shows_no_fake_scan(env, monkeypatch):
    app, client, tmp = env
    app.config['HUB_WORKFLOW_V2'] = True
    app.config['MEDIA_SOURCES_FILE'] = str(Path(tmp) / 'media-sources.json')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'mount-status.json')
    login(client, 'it')
    unconfigured = client.get('/media-sources').get_data(as_text=True)
    assert 'Was passiert gerade?' in unconfigured
    assert 'data-source-monitor' in unconfigured
    assert 'source-progress.js' in unconfigured
    result = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'default',
        'unc': '//10.12.13.14/media$/Bildschirme',
    }, follow_redirects=True)
    assert result.status_code == 200
    assert 'Speichern allein' in result.get_data(as_text=True)
    status = client.get('/media-sources/status')
    assert status.status_code == 200
    source = status.json['sources'][0]
    assert source['stages'][0]['state'] == 'done'
    assert source['stages'][1]['state'] == 'waiting'
    assert source['discovered'] == 0


def test_dev_smb_can_be_connected_and_rechecked_entirely_from_it_ui(env, tmp_path, monkeypatch):
    import app.smb_ui as smb_ui
    from contextlib import contextmanager

    app, client, tmp = env
    app.config['HUB_WORKFLOW_V2'] = True
    app.config['MEDIA_SOURCES_FILE'] = str(Path(tmp) / 'dev-media-sources.json')
    app.config['MEDIA_MOUNT_STATUS_FILE'] = str(Path(tmp) / 'dev-smb-report.json')
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'dev-library')
    monkeypatch.setenv('MEDIA_SOURCES_FILE', app.config['MEDIA_SOURCES_FILE'])
    monkeypatch.setenv('MEDIA_MOUNT_STATUS_FILE', app.config['MEDIA_MOUNT_STATUS_FILE'])
    monkeypatch.setenv('DEV_SMB_UI', '1')
    monkeypatch.setenv('APP_SECRET_KEY', 'S' * 48)
    monkeypatch.setenv('DEV_SMB_CREDENTIALS_FILE', str(Path(tmp) / 'dev-credentials.bin'))
    monkeypatch.setenv('DEV_SMB_TRIGGER_FILE', str(Path(tmp) / 'dev-trigger'))
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(Path(tmp) / 'dev-sources'))
    (Path(tmp) / 'dev-sources').mkdir()

    class Screen:
        name = 'Bistro'
        def is_dir(self): return True
        def is_symlink(self): return False

    class SMB:
        @contextmanager
        def scandir(self, path, **kwargs):
            if kwargs['password'] != 'testsecret':
                raise PermissionError('STATUS_LOGON_FAILURE')
            yield iter([Screen()])
        def reset_connection_cache(self): pass

    monkeypatch.setattr(smb_ui, '_smb', lambda: SMB())
    login(client, 'it')
    page = client.get('/media-sources')
    assert page.status_code == 200
    assert b'name="password"' in page.data
    assert b'Verbinden &amp; pr' in page.data

    response = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'default',
        'unc': '//10.11.12.13/media$/Bildschirme',
        'username': 'reader', 'password': 'testsecret', 'domain': 'DOMAIN',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert 'SMB verbunden:' in response.get_data(as_text=True)
    assert b'testsecret' not in response.data
    assert b'testsecret' not in (Path(tmp) / 'dev-credentials.bin').read_bytes()
    assert (Path(tmp) / 'dev-trigger').exists()

    state = client.get('/media-sources/status')
    assert state.status_code == 200
    assert state.json['sources'][0]['stages'][1]['state'] == 'done'
    assert state.json['sources'][0]['copy_progress']['state'] == 'tested'
    assert 'testsecret' not in json.dumps(state.json)

    refreshed = client.post('/media-sources/sync-now', data={'csrf': token(client)})
    assert refreshed.status_code == 302

    denied = client.post('/media-sources', data={
        'csrf': token(client), 'alias': 'default',
        'unc': '//10.11.12.13/media$/Other',
        'username': 'reader', 'password': 'wrong', 'domain': '',
    }, follow_redirects=True)
    assert denied.status_code == 200
    assert 'Anmeldung/Berechtigung fehlgeschlagen' in denied.get_data(as_text=True)
    from app.media_sources import load_sources
    assert load_sources(app.config['MEDIA_SOURCES_FILE'])[0]['unc'].endswith('/Bildschirme')

    login(client, 'viewer')
    assert client.get('/media-sources/status').status_code == 403
    assert client.post('/media-sources/sync-now',
                       data={'csrf': token(client)}).status_code == 403


def test_v2_network_folder_playlist_creation_form_supplies_csrf_and_submits(env, monkeypatch):
    """Reproduce the exact browser failure: POST /library without hidden csrf."""
    app, client, tmp = env
    from app.library import Library
    app.config['HUB_WORKFLOW_V2'] = True
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'v2-library')
    root = Path(tmp) / 'dev-sources'
    (root / 'default' / 'demo-screen-01').mkdir(parents=True)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('FOLDER_REQUIRE_MOUNT', '0')
    monkeypatch.setenv('FOLDER_REQUIRE_VERIFIED', '0')
    login(client, 'it')

    html = client.get('/library').get_data(as_text=True)
    form = re.search(r'<form[^>]+action="/library"[^>]*>(.*?)</form>', html, re.S)
    assert form, 'Playlist-create form missing'
    csrf = re.search(r'<input[^>]+name="csrf"[^>]+value="([^"]+)"', form.group(1))
    assert csrf, 'Playlist-create form did not include csrf: would return HTTP 400'
    assert csrf.group(1) == token(client)
    assert 'default/demo-screen-01' in form.group(1)

    # Still reject forged or omitted tokens; never weaken the global CSRF check.
    assert client.post('/library', data={
        'name': 'Bad Submission', 'folder_source': 'default/demo-screen-01',
    }).status_code == 400

    created = client.post('/library', data={
        'csrf': csrf.group(1), 'name': 'Service-Center',
        'folder_source': 'default/demo-screen-01',
    })
    assert created.status_code == 302
    playlists = Library(app.config['LIBRARY_DIR']).list()
    assert len(playlists) == 1
    assert playlists[0]['name'] == 'Service-Center'
    assert playlists[0]['folder_source'] == 'default/demo-screen-01'
    assert client.get(created.headers['Location']).status_code == 200
