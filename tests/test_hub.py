"""All tests offline: no real Anthias device touched."""
import errno
import io
import json
import os
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
    for asset in ('ui-refinements.css', 'icons.svg', 'favicon.svg'):
        assert client.get('/static/' + asset).status_code == 200

    login(client, 'marketing')
    page = client.get('/devices/lab').data.decode('utf-8')
    assert page.count('data-theme-choice=') == 0
    assert 'class="site-nav-link is-active"' in page
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
    assert 'Weiteren Inhalt hinzufügen' in page  # populated playlist keeps bottom CTA
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
    assert 'Vorlage erstellen' in library and 'Vorlagenbackup wiederherstellen' in library
    assert 'aria-current="page"' in library
    detail = client.get(f"/library/{t['id']}").data.decode('utf-8')
    assert 'library-item-options' in detail
    assert 'template-options' in detail
    assert 'library-bulk-compact' in detail
    assert 'name="direction" value="up"' in detail
    playlist = client.get('/devices/lab').data.decode('utf-8')
    assert 'data-library-template' in playlist and 'data-library-source' in playlist
    assert 'data-library-source-template' in playlist
    assert 'data-add-mode="website"' in playlist
    assert playlist.count('data-add-mode=') == 3
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
    assert client.post(f"/library/{template['id']}/apply", data={'csrf': t, 'template_id': template['id'], 'device': 'lab', 'confirm': 'yes'}).status_code == 403
    assert client.post('/library', data={'csrf': t, 'name': 'No'}).status_code == 403
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


def test_it_cannot_change_playlist(env):
    app,client,_=env
    login(client,'it')
    assert client.get('/devices/lab').status_code==200
    target='/devices/lab/assets/one123/edit'
    assert client.post(target,data={'csrf':token(client),'name':'Tamper','duration':'20'}).status_code==403
    assert client.post('/devices/lab/add-url',data={'csrf':token(client),'url':'https://example.org','name':'X','duration':'30'}).status_code==403
    assert not FakeAnthias.changes


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
    assert 'class="fleet-device card ' in page
    assert 'Playlist bearbeiten' in page
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
    assert 'Playlist ansehen' in viewer_page
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
        'csrf': token(client), 'source': source, 'confirm': 'add'}).status_code == 403
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
    assert 'Neue Vorlage erstellen' in page
    assert 'manifest.json' in page
    assert 'Vorlagenbackup wiederherstellen' in page
    assert 'data-bulk-upload' not in page
    assert '/library/media-import' not in page
    assert '/library/import' in page
    assert sample['name'] in page
    detail = client.get('/library/' + sample['id']).data.decode('utf-8')
    assert 'data-bulk-upload' in detail
    assert 'library-bulk-compact' in detail



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
    assert 'Gesamte Vorlage hinzufügen' in page
    assert 'Inhalt hinzufügen' in page
    assert 'Vorlage auswählen' in page or 'Vorlage' in page
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
    assert 'Backup exportieren' in page
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
    assert 'id="library-publish-heading"' in page
    assert page.index('id="library-publish-heading"') < page.index('id="items-title"')
    assert page.index('Vorlage zur Playlist hinzufügen') < page.index('Bild oder Video speichern')
    assert page.count(f'/library/{template["id"]}/append-to-device') == 1
    assert 'name="device" required' in page
    assert 'name="ack" value="yes" required' in page
    assert 'bestehende Inhalte bleiben erhalten' in page
    assert 'Backup exportieren' in page


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
    assert 'class="drag-handle"' not in page


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
    assert 'class="asset-edit asset-inline-edit"' in page
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
    assert '> Webseite</button>' in page
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
    assert page.index('Bild oder Video speichern') < page.index('Medien-Sammelimport')
    assert page.index('Medien-Sammelimport') < page.index('Optional: Webseite verlinken')
    assert '<details class="library-website-details">' in page
    assert 'library-website-details" open' not in page
    assert 'library_add_url' not in page  # internal endpoint name is not exposed
    assert '/url' in page  # existing URL submission stays available
    assert 'RSS2Slideshow-Anzeige' in page
    assert 'data-upload-form="library"' in page
    assert 'data-bulk-upload' in page
    assert page.index('Vorlage zur Playlist hinzufügen') < page.index('Bild oder Video speichern')


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
    assert 'template-delete-control template-delete-list' in overview
    assert 'name="name_confirmation"' in detail
    assert 'name="ack" value="yes"' in detail
    assert 'template-delete.js' in overview
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
    assert client.post(route, data={'csrf': token(client), 'confirm': collection['id'],
                                    'ack': 'yes', 'name_confirmation': 'Sicher'}).status_code == 403
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


def test_library_overview_actions_share_aligned_card_without_overlay_offsets(env):
    app, client, tmp = env
    from app.library import Library
    app.config['LIBRARY_DIR'] = str(Path(tmp) / 'library')
    Library(app.config['LIBRARY_DIR']).create('Aktionsvorlage')
    login(client, 'marketing')
    page = client.get('/library').get_data(as_text=True)
    # The clickable template title and separate delete menu are flex siblings
    # within the SAME card. No nested links/buttons or absolute-centering hacks.
    assert '<div class="card library-entry-shell">' in page
    entry = page.split('<div class="card library-entry-shell">', 1)[1]
    assert '<a class="library-entry" href=' in entry
    assert 'class="template-delete-control template-delete-list"' in entry
    assert entry.index('<a class="library-entry"') < entry.index('template-delete-control')
    sheet = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'library.css').read_text()
    assert '.library-entry-shell.card{' in sheet
    assert 'display:flex;align-items:center;gap:10px' in sheet
    assert '.template-delete-control{' in sheet
    assert 'color:var(--ink);margin:0;padding:0;border:0' in sheet
    assert 'top:50%;transform:translateY(-50%)' not in sheet
    assert '.library-actions .library-panel form>button.primary' in sheet
    client.post('/logout', data={'csrf': token(client)})
    login(client, 'viewer')
    viewer = client.get('/library').get_data(as_text=True)
    assert '<div class="card library-entry-shell">' in viewer
    assert 'template-delete-control' not in viewer


def test_screen_card_ctas_have_equal_insets_for_marketing_it_and_viewer(env):
    _, client, _ = env
    style = (Path(__file__).resolve().parents[1] / 'app' / 'static' / 'workspace.css').read_text()
    assert '.fleet-open{' in style
    assert 'width:100%;align-self:stretch;' in style
    assert 'margin:auto 0 20px!important' in style
    assert '.fleet-settings{border:0;border-top:1px solid #2e4453;margin:0 -23px 0' in style
    assert '.fleet-hero .fleet-add-button{align-self:flex-start}' in style
    for role, label in [('marketing', 'Playlist bearbeiten'),
                        ('viewer', 'Playlist ansehen'), ('it', 'Playlist ansehen')]:
        login(client, role)
        page = client.get('/').get_data(as_text=True)
        assert 'class="button primary fleet-open"' in page
        assert label in page
        if role == 'it':
            assert 'fleet-settings' in page
            assert 'class="button primary fleet-add-button"' in page
        else:
            assert 'fleet-settings' not in page
        client.post('/logout', data={'csrf': token(client)})


def test_playlist_bottom_add_and_bulk_controls_are_marketing_only(env):
    _, client, _ = env
    login(client, 'marketing')
    page = client.get('/devices/lab').get_data(as_text=True)
    assert 'Weiteren Inhalt hinzufügen' in page
    assert 'playlist-bottom-actions' in page
    assert page.index('id="playlist-items"') < page.index('playlist-bottom-actions')
    assert 'data-open-composer' in page.split('playlist-bottom-actions', 1)[1]
    assert 'data-bulk-management' in page
    assert 'name="selected" value="one123" form="playlist-bulk-form"' in page
    assert 'name="baseline" value="one123"' in page
    assert 'name="mode" value="selected"' in page
    assert 'name="mode" value="all"' in page
    assert 'name="name_confirmation"' in page
    assert 'playlist-bulk.js' in page
    for role in ('it', 'viewer'):
        client.post('/logout', data={'csrf': token(client)})
        login(client, role)
        read_only = client.get('/devices/lab').get_data(as_text=True)
        assert 'Weiteren Inhalt hinzufügen' not in read_only
        assert 'playlist-bottom-actions' not in read_only
        assert 'playlist-bulk-form' not in read_only


def test_playlist_empty_has_first_add_but_no_bulk_or_bottom_add(env):
    _, client, _ = env
    login(client, 'marketing')
    original = FakeAnthias.assets_data
    try:
        FakeAnthias.assets_data = []
        page = client.get('/devices/lab').get_data(as_text=True)
        assert 'Ersten Inhalt hinzufügen' in page
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
    for role in ('it', 'viewer'):
        login(client, role)
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
    assert client.post('/library', data={'csrf': token(client), 'name': 'Denied'}).status_code == 403
    login(client, 'viewer')
    assert client.post('/devices/lab/control', data={
        'csrf': token(client), 'action': 'reboot', 'confirm': 'lab', 'ack': 'yes'
    }).status_code == 403


# Large-media boundaries and device capacity are exercised by test_device_storage.py.


def test_fleet_renders_without_any_player_calls_and_storage_is_deferred(env):
    _, client, _ = env
    login(client, 'marketing')
    with patch.object(FakeAnthias, 'assets', side_effect=AssertionError('slow player call')) as assets, \
         patch.object(FakeAnthias, 'info', side_effect=AssertionError('slow info call')) as info:
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
    with patch.object(FakeAnthias, 'info', side_effect=AssertionError('info must be lazy')) as info:
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
    with patch.object(FakeAnthias, 'info', side_effect=AssertionError('unexpected info')) as info:
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
    assert '6.0 GB' not in player.split('<header class="playlist-hero">')[1].split('</header>')[0]
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
    assert 'name="ignore_storage_check" value="manual-confirmed" disabled' in page


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
