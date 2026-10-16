"""Native Anthias weekly asset schedules: persisted presets, roles and safe Pi updates."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.anthias import Anthias, PlayerError
from app.schedules import (
    ScheduleError, add_profile, edit_profile, remove_profile, profiles_for,
    valid_rule, native_fields, native_key, describe_asset, apply_to_assets,
)
from app.web import create_app


def asset(ident, name, days=None, start=None, end=None):
    return {
        'asset_id': ident, 'name': name, 'is_enabled': True,
        'play_order': 1, 'uri': 'https://example.org/' + ident,
        'mimetype': 'webpage', 'duration': 30,
        'play_days': days if days is not None else [1,2,3,4,5,6,7],
        'play_time_from': start, 'play_time_to': end,
    }


class Player:
    records = {}
    patches = []
    fails_on = None
    def __init__(self, device):
        self.url = device['url']
    def assets(self):
        return [dict(row) for row in type(self).records.values()]
    def patch(self, ident, changes):
        if ident == type(self).fails_on:
            raise PlayerError('Test-Pi offline')
        type(self).patches.append((ident, changes.copy()))
        type(self).records[ident].update(changes)
        return dict(type(self).records[ident])
    valid_id = staticmethod(Anthias.valid_id)


@pytest.fixture
def hub(tmp_path):
    users = tmp_path/'users.json'
    users.write_text(json.dumps({'users': [
        {'username':role, 'role':role,
         'password_hash':generate_password_hash('local-safe-password', method='scrypt')}
        for role in ('owner','marketing','it','viewer')]}))
    devices = tmp_path/'devices.json'
    devices.write_text(json.dumps({'devices':[{
        'id':'lab', 'name':'Pi im Bistro', 'url':'http://192.168.1.77',
        'location':'Bistro'}]}))
    app = create_app({'TESTING':True,'SECRET_KEY':'x'*48,
                      'SESSION_COOKIE_SECURE':False,
                      'USERS_FILE':str(users), 'DEVICES_FILE':str(devices),
                      'LIBRARY_DIR':str(tmp_path/'library'),
                      'SCHEDULES_FILE':str(tmp_path/'schedules.json'),
                      'AUDIT_FILE':str(tmp_path/'audit.jsonl')})
    Player.records = {
        'a':asset('a','Werktagsmenü'),
        'b':asset('b','Eventanzeige'),
    }
    Player.patches = []
    Player.fails_on = None
    with patch('app.web.Anthias',Player):
        yield app, app.test_client(), tmp_path


def sign_in(client, role):
    client.get('/login')
    with client.session_transaction() as state:
        csrf = state['csrf']
    resp = client.post('/login',data={
        'csrf':csrf,'username':role,'password':'local-safe-password'})
    assert resp.status_code == 302


def post(client, url, payload):
    with client.session_transaction() as state:
        csrf = state['csrf']
    return client.post(url, data={'csrf':csrf,**payload}, follow_redirects=True)


def test_weekday_validation_and_native_fields_match_anthias():
    weekday = valid_rule('Werktag_Default',['5','1','2','3','4'],'08:00','18:00')
    assert weekday == {'name':'Werktag_Default','days':[1,2,3,4,5],
                       'start':'08:00','end':'18:00'}
    assert native_fields(weekday) == {
        'play_days':[1,2,3,4,5],
        'play_time_from':'08:00:00',
        'play_time_to':'18:00:00',
    }
    assert native_fields() == {
        'play_days':[1,2,3,4,5,6,7],
        'play_time_from':None,'play_time_to':None,
    }
    assert native_key(native_fields(weekday)) == ((1,2,3,4,5),'08:00:00','18:00:00')
    assert describe_asset(asset('a','A',[1,2,3,4,5],'08:00:01','18:00:00'),
                          [weekday]) == 'Individuell in Anthias'
    for days, start, end in (([], '08:00','18:00'),(['8'],'08:00','18:00'),
                             (['1'],'18:00','18:00'),(['1'],'25:00','17:00'),
                             (['1'],'08:00','')):
        with pytest.raises(ScheduleError):
            valid_rule('Test',days,start,end)


def test_presets_persist_per_device_and_deleting_preset_never_touches_pi(tmp_path):
    store = tmp_path/'schedules.json'
    weekday = add_profile(store,'pi3','Werktag_Default',['1','2','3','4','5'],'08:00','18:00')
    event = add_profile(store,'pi5','Event',['6'],'10:00','14:00')
    assert [p['name'] for p in profiles_for(store,'pi3')] == ['Werktag_Default']
    assert profiles_for(store,'pi5') == [event]
    assert store.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ScheduleError,match='bereits'):
        add_profile(store,'pi3','WERKTAG_DEFAULT',['1'],'08:00','18:00')
    newer = edit_profile(store,'pi3',weekday['id'],'Werktag neu',['1'],'09:00','17:00')
    assert newer['id'] == weekday['id']
    assert profiles_for(store,'pi3')[0]['start'] == '09:00'
    remove_profile(store,'pi3',weekday['id'])
    assert profiles_for(store,'pi3') == []
    assert profiles_for(store,'pi5') == [event]


def test_schedule_ui_is_per_device_and_has_examples(hub):
    _, client, _ = hub
    sign_in(client,'marketing')
    page = client.get('/devices/lab/schedules')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'Pi im Bistro' in html
    assert 'Werktag_Default' in html
    assert 'data-schedule-example="weekday"' in html
    assert 'data-schedule-example="event"' in html
    assert 'Ohne Zeitplan' in html
    assert 'Individuell in Anthias' in html  # explanation in footer
    assert 'schedules.js' in html
    assert 'Zeitpläne' in client.get('/').get_data(as_text=True)
    assert 'Zeitplanung' in client.get('/devices/lab').get_data(as_text=True)
    assert client.get('/devices/unknown/schedules').status_code == 404


def test_marketing_creates_weekday_and_event_and_assigns_different_assets(hub):
    app, client, _ = hub
    sign_in(client,'marketing')
    base='/devices/lab/schedules'
    for name,days,start,end in (
        ('Werktag_Default',['1','2','3','4','5'],'08:00','18:00'),
        ('Event',['6'],'10:00','14:00'),
    ):
        res=post(client,base+'/add',{'name':name,'days':days,'start':start,'end':end})
        assert res.status_code == 200
        assert 'Zeitplan gespeichert' in res.get_data(as_text=True)
    rules=profiles_for(app.config['SCHEDULES_FILE'],'lab')
    assert len(rules)==2
    for rule,ident in zip(rules,('a','b')):
        res=post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':[ident]})
        assert res.status_code == 200
        assert '1 Inhalte auf dem Pi' in res.get_data(as_text=True)
    assert Player.records['a']['play_days']==[1,2,3,4,5]
    assert Player.records['a']['play_time_from']=='08:00:00'
    assert Player.records['b']['play_days']==[6]
    assert Player.records['b']['play_time_from']=='10:00:00'
    assert len(Player.patches)==2
    # Existing metadata, dates and paused state are never touched.
    assert all(set(fields)=={'play_days','play_time_from','play_time_to'}
               for _,fields in Player.patches)
    page=client.get(base).get_data(as_text=True)
    assert 'Werktag_Default' in page and 'Event' in page
    # Reset only b to Anthias default 'no schedule'.
    res=post(client,base+'/apply',{'profile_id':'always','asset_ids':['b']})
    assert res.status_code==200
    assert Player.records['b']['play_time_from'] is None
    assert Player.records['b']['play_days']==[1,2,3,4,5,6,7]
    assert Player.records['a']['play_time_from']=='08:00:00'


def test_it_can_edit_and_apply_but_viewer_cannot_write(hub):
    app,client,_=hub
    sign_in(client,'it')
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Event','days':['6'],
                            'start':'10:00','end':'14:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':['a']})
    assert Player.records['a']['play_time_from']=='10:00:00'
    post(client,base+'/'+rule['id']+'/edit',{'name':'Event 2026',
                    'days':['6'],'start':'11:00','end':'15:00'})
    assert profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]['name']=='Event 2026'
    assert Player.records['a']['play_time_from']=='10:00:00'
    post(client,base+'/'+rule['id']+'/delete',{'confirm':rule['id']})
    assert profiles_for(app.config['SCHEDULES_FILE'],'lab')==[]
    assert Player.records['a']['play_time_from']=='10:00:00'
    post(client,base+'/apply',{'profile_id':'always','asset_ids':['a']})
    assert Player.records['a']['play_time_from'] is None
    post(client,'/logout',{})
    sign_in(client,'viewer')
    assert client.get(base).status_code==200
    assert 'data-schedule-form' not in client.get(base).get_data(as_text=True)
    assert client.post(base+'/apply').status_code==400  # No CSRF, before role.
    with client.session_transaction() as state:
        csrf=state['csrf']
    assert client.post(base+'/apply',data={'csrf':csrf}).status_code==403


def test_invalid_schedule_never_mutates_pi_and_old_api_is_rejected(hub):
    app,client,_=hub
    sign_in(client,'marketing')
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Bad','days':['9'],'start':'08:00','end':'18:00'})
    assert profiles_for(app.config['SCHEDULES_FILE'],'lab')==[]
    post(client,base+'/add',{'name':'Event','days':['6'],'start':'10:00','end':'14:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':['a','nonexistent']})
    assert Player.patches==[]
    del Player.records['b']['play_days']
    response=post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':['a','b']})
    assert 'Anthias meldet keine unterstützten Wochentagsdaten' in response.get_data(as_text=True)
    assert Player.patches==[]


def test_partial_failure_stops_and_warns_without_auto_retries(hub):
    app,client,_=hub
    sign_in(client,'marketing')
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Event','days':['6'],'start':'10:00','end':'14:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    Player.fails_on='b'
    response=post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':['a','b']})
    assert response.status_code==200
    assert 'Mögliche Teiländerung' in response.get_data(as_text=True)
    assert Player.records['a']['play_time_from']=='10:00:00'
    assert Player.records['b']['play_time_from'] is None
    assert [i for i,_ in Player.patches]==['a']
