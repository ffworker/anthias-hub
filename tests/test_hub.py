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
    assert client.post('/devices/bistro/remove',data={'csrf':t,'confirm':'bistro'}).status_code==302
    assert b'>Bistro<' not in client.get('/').data


def test_marketing_changes_each_devices_playlist(env):
    app,client,_=env
    login(client,'marketing')
    t=token(client)
    assert client.post('/devices/lab/add-url',data={'csrf':t,'name':'News','url':'https://example.org/news','duration':'45'}).status_code==302
    assert client.post('/devices/lab/assets/one123/edit',data={'csrf':t,'name':'New title','duration':'20','enabled':'on'}).status_code==302
    assert client.post('/devices/lab/assets/one123/move',data={'csrf':t,'direction':'down'}).status_code==302
    assert client.post('/devices/lab/assets/one123/delete',data={'csrf':t,'confirm':'one123'}).status_code==302
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
