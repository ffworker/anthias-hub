"""All tests offline: no real Anthias device touched."""
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
    def order(self, *args, **kwargs):
        self.changes.append(('order', args, kwargs))
    @staticmethod
    def valid_id(asset_id):
        return anthias.Anthias.valid_id(asset_id)


@pytest.fixture()
def env():
    FakeAnthias.changes=[]
    with tempfile.TemporaryDirectory() as tmp:
        users = Path(tmp) / 'users.json'
        users.write_text(json.dumps({'users':[{'username':x,'role':x,'password_hash':generate_password_hash('safe-password-123',method='scrypt')} for x in ('it','marketing','viewer')]}))
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
    assert set(data.keys())=={'name','is_enabled','duration'}


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
    assert 'name="direction" value="up"' in page
    assert 'name="direction" value="down"' in page
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
    assert FakeAnthias.changes[-1] == ('patch', ('vid123', {'name': 'Updated film', 'is_enabled': True}), {})

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
    assert resp.json == {'ok': True, 'asset': {'name': 'New headline', 'duration': 22, 'is_enabled': True}}
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
    assert 'Keine Live-Vorschau' in page
    assert 'Original Anthias' not in page
    assert 'id="device-setup"' not in page
    assert 'name="ack"' not in page
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
