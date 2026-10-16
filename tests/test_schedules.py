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
    def create(self, name, uri, duration, mimetype='webpage', ext=None, *, schedule=None):
        ident = 'new' + str(len(type(self).records) + 1)
        row = asset(ident, name)
        row.update({'uri':uri, 'duration':duration, 'mimetype':mimetype})
        if schedule is not None:
            row.update(native_fields(schedule))
        type(self).records[ident] = row
        return {'asset_id':ident}
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


def test_global_schedule_library_shared_between_all_devices(tmp_path):
    store = tmp_path/'schedules.json'
    weekday = add_profile(store,'pi3','Werktag_Default',['1','2','3','4','5'],'08:00','18:00')
    event = add_profile(store,'pi5','Event',['6'],'10:00','14:00')
    assert profiles_for(store,'pi3') == [weekday, event]
    assert profiles_for(store,'pi5') == [weekday, event]
    assert profiles_for(store,'new-future-device') == [weekday, event]
    assert store.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ScheduleError,match='bereits'):
        add_profile(store,'pi5','WERKTAG_DEFAULT',['1'],'08:00','18:00')
    newer = edit_profile(store,'pi5',weekday['id'],'Werktag neu',['1'],'09:00','17:00')
    assert newer['id'] == weekday['id']
    assert profiles_for(store,'pi3')[0]['start'] == '09:00'
    remove_profile(store,'pi3',weekday['id'])
    assert profiles_for(store,'pi3') == [event]
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
    post(client,base+'/'+rule['id']+'/delete',{'confirm':rule['id'], 'confirm_global':'yes'})
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



def test_default_applies_to_new_web_asset_and_explicit_always_overrides(hub):
    app, client, _ = hub
    sign_in(client,'marketing')
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Werktag_Default','days':['1','2','3','4','5'],
                            'start':'08:00','end':'18:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    response=post(client,base+'/default',{'profile_id':rule['id']})
    assert 'Geräte-Standard gespeichert' in response.get_data(as_text=True)
    assert 'Werktag_Default' in client.get('/devices/lab').get_data(as_text=True)
    assert 'schedule-choice.js' in client.get('/devices/lab').get_data(as_text=True)
    post(client,'/devices/lab/add-url',{'name':'Frühstück','url':'https://example.org/breakfast',
                                       'duration':'15'})
    new=next(v for v in Player.records.values() if v['name']=='Frühstück')
    assert new['play_days']==[1,2,3,4,5]
    assert new['play_time_from']=='08:00:00'
    from app.schedules import assignments_for, default_for
    assert assignments_for(app.config['SCHEDULES_FILE'],'lab')[new['asset_id']]['profile_id']==rule['id']
    assert default_for(app.config['SCHEDULES_FILE'],'lab')==rule['id']
    post(client,'/devices/lab/add-url',{'name':'Logo','url':'https://example.org/logo',
                                       'duration':'15','schedule_choice':'always'})
    logo=next(v for v in Player.records.values() if v['name']=='Logo')
    assert logo['play_time_from'] is None
    assert logo['play_days']==[1,2,3,4,5,6,7]
    post(client,base+'/default',{'profile_id':'always'})
    assert default_for(app.config['SCHEDULES_FILE'],'lab') is None
    assert Player.records[new['asset_id']]['play_time_from']=='08:00:00'


def test_library_transfer_chooses_target_schedule_without_modifying_template(hub):
    app,client,_ = hub
    sign_in(client,'marketing')
    from app.library import Library
    store=Library(app.config['LIBRARY_DIR'])
    template=store.create('Bistro Werbung')
    store.add_url(template['id'],'Werbelink','https://example.org/promo',30)
    initial=store.get(template['id'])
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Samstag Event','days':['6'],
                            'start':'10:00','end':'14:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    post(client,base+'/default',{'profile_id':rule['id']})
    view=client.get('/library/'+template['id']).get_data(as_text=True)
    assert 'data-library-device-schedule' in view
    assert 'data-library-schedule-map' in view
    result=post(client,f'/library/{template["id"]}/append-to-device',{
        'device':'lab','confirm':'append','ack':'yes','schedule_choice':'always'})
    assert result.status_code == 200
    advert=next(v for v in Player.records.values() if v['name']=='Werbelink')
    assert advert['play_time_from'] is None
    assert store.get(template['id'])==initial
    assert all('play_days' not in item and 'schedule' not in item
               for item in store.get(template['id'])['items'])


def test_native_schedule_is_confirmed_before_new_asset_ever_enabled():
    api=Anthias({'url':'http://192.168.1.99'})
    events=[]
    rule=valid_rule('Event',[6],'10:00','14:00')
    def call(method,path,**kwargs):
        events.append(('create',kwargs['payload']['is_enabled']))
        return {'asset_id':'created10'}
    def patch(asset_id, fields):
        events.append(('patch',dict(fields)))
        if 'play_days' in fields:
            return dict(native_fields(rule))
        return {'asset_id':asset_id,**fields}
    from unittest.mock import patch as mock_patch
    with mock_patch.object(api,'call',side_effect=call), mock_patch.object(api,'patch',side_effect=patch):
        api.create('Event','https://example.org/event',30,schedule=rule)
    assert events[0]==('create',False)
    assert events[1][0]=='patch' and events[1][1]['play_days']==[6]
    assert events[2]==('patch',{'is_enabled':True})
    events.clear()
    with mock_patch.object(api,'call',side_effect=call), mock_patch.object(
            api,'patch',return_value={'play_days':[1,2,3,4,5,6,7],
                                       'play_time_from':None,'play_time_to':None}):
        with pytest.raises(PlayerError, match='nicht bestätigt'):
            api.create('Event','https://example.org/event',30,schedule=rule)
    assert events==[('create',False)]


def test_profile_link_drift_does_not_get_silently_overwritten(hub):
    app,client,_=hub
    sign_in(client,'marketing')
    from app.schedules import assignments_for, describe_linked_asset
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Werktag_Default','days':['1','2','3','4','5'],
                            'start':'08:00','end':'18:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    post(client,base+'/apply',{'profile_id':rule['id'],'asset_ids':['a']})
    assert 'a' in assignments_for(app.config['SCHEDULES_FILE'],'lab')
    assert describe_linked_asset(Player.records['a'],[rule],assignments_for(app.config['SCHEDULES_FILE'],'lab'))=='Werktag_Default'
    Player.records['a']['play_time_from']='09:00:00' # external Pi UI edit
    assert 'Abweichend' in describe_linked_asset(
        Player.records['a'],[rule],assignments_for(app.config['SCHEDULES_FILE'],'lab'))
    before=len(Player.patches)
    post(client,base+'/'+rule['id']+'/edit',{'name':'Werktag_Default','days':['1','2','3','4','5'],
                'start':'07:00','end':'19:00','sync_assigned':'yes'})
    assert len(Player.patches)==before
    assert Player.records['a']['play_time_from']=='09:00:00'
    assert 'Abweichend' in client.get('/devices/lab').get_data(as_text=True)


def test_schedule_individual_and_reset_from_existing_playlist_editor(hub):
    app, client, _=hub
    sign_in(client,'marketing')
    page=client.get('/devices/lab').get_data(as_text=True)
    assert 'device-workspace-tabs' in page
    assert 'asset-schedule-details' in page
    assert 'Zeitplanung speichern' in page
    response=post(client,'/devices/lab/assets/a/schedule',{
        'schedule_choice':'custom','schedule_days':['6'],'schedule_from':'10:00','schedule_to':'14:00'})
    assert 'Zeitplanung des Inhalts' in response.get_data(as_text=True)
    assert Player.records['a']['play_days']==[6]
    assert Player.records['a']['play_time_from']=='10:00:00'
    post(client,'/devices/lab/assets/a/schedule',{'schedule_choice':'always'})
    assert Player.records['a']['play_time_from'] is None
    assert Player.records['a']['is_enabled'] is True



def test_default_applies_to_library_append_when_no_explicit_choice(hub):
    app,client,_=hub
    sign_in(client,'marketing')
    from app.library import Library
    store=Library(app.config['LIBRARY_DIR'])
    template=store.create('Bistro Wochenmenü')
    store.add_url(template['id'],'Wochenangebot','https://example.org/weekly',30)
    base='/devices/lab/schedules'
    post(client,base+'/add',{'name':'Werktag_Default','days':['1','2','3','4','5'],
                            'start':'08:00','end':'18:00'})
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    post(client,base+'/default',{'profile_id':rule['id']})
    before=store.get(template['id'])
    result=post(client,f'/library/{template["id"]}/append-to-device', {
        'device':'lab','confirm':'append','ack':'yes'})
    assert 'Inhalte aus der Vorlage hinzugefügt' in result.get_data(as_text=True)
    item=next(v for v in Player.records.values() if v['name']=='Wochenangebot')
    assert item['play_days']==[1,2,3,4,5]
    assert item['play_time_from']=='08:00:00'
    assert store.get(template['id'])==before


def test_defaults_are_per_device_but_rules_are_shared_and_global_delete_cleans_all(tmp_path):
    from app.schedules import default_for, set_default, bind_asset, assignments_for, native_fields
    file=tmp_path/'schedules.json'
    morning=add_profile(file,'pi3','Früh',['1','2'],'07:00','13:00')
    evening=add_profile(file,'pi5','Spät',['6'],'15:00','21:00')
    assert profiles_for(file,'future-pi')==[morning,evening]
    set_default(file,'pi3',morning['id'])
    set_default(file,'pi5',morning['id'])  # same global default is valid on any Pi
    set_default(file,'future-pi',evening['id'])
    bind_asset(file,'pi3','asset-a',morning['id'],native_fields(morning))
    bind_asset(file,'pi5','asset-z',morning['id'],native_fields(morning))
    assert default_for(file,'pi3')==morning['id']
    assert default_for(file,'pi5')==morning['id']
    remove_profile(file,'pi3',morning['id'])
    assert default_for(file,'pi3') is None
    assert default_for(file,'pi5') is None
    assert default_for(file,'future-pi') == evening['id']
    assert assignments_for(file,'pi3') == {}
    assert assignments_for(file,'pi5') == {}
    assert profiles_for(file,'pi5')==[evening]



def test_schedule_gap_warning_is_only_advisory():
    from app.schedules import weekday_warning
    no_schedule=asset('a','Always')
    assert weekday_warning([no_schedule])==''
    scheduled=asset('a','Event',[6],'10:00:00','14:00:00')
    assert 'Mögliche Zeitlücken' in weekday_warning([scheduled])
    assert weekday_warning([{'name':'unknown','is_enabled':True}])==''


def test_legacy_profiles_migrate_without_losing_defaults_or_bindings(tmp_path):
    from app.schedules import default_for, assignments_for, set_default, native_fields
    file=tmp_path/'schedules.json'
    original={'devices': {
        'pi3': [
            {'id':'aa','name':'Werktag_Default','days':[1,2,3,4,5],'start':'08:00','end':'18:00'},
            {'id':'bb','name':'Event','days':[6],'start':'10:00','end':'14:00'}
        ],
        'pi5': [
            {'id':'cc','name':'Werktag_Default','days':[1,2,3,4,5],'start':'08:00','end':'18:00'},
            {'id':'dd','name':'Event','days':[6],'start':'11:00','end':'15:00'},
        ]
    }, 'defaults': {'pi3':'aa','pi5':'cc'}, 'assignments': {
        'pi3': {'media-a': {'profile_id':'aa','native_key': [[1,2,3,4,5],'08:00:00','18:00:00']}},
        'pi5': {'media-b': {'profile_id':'cc','native_key': [[1,2,3,4,5],'08:00:00','18:00:00']},
                'media-c': {'profile_id':'dd','native_key': [[6],'11:00:00','15:00:00']}}
    }}
    file.write_text(json.dumps(original),encoding='utf-8')
    shared=profiles_for(file,'pi3')
    assert profiles_for(file,'pi5')==shared
    assert profiles_for(file,'brand-new-pi')==shared
    assert len(shared)==3
    weekday=next(p for p in shared if p['name']=='Werktag_Default')
    assert len([p for p in shared if p['name'].startswith('Event')])==2
    assert any('pi5' in p['name'] for p in shared)
    assert default_for(file,'pi3')==weekday['id']
    assert default_for(file,'pi5')==weekday['id']
    assert assignments_for(file,'pi3')['media-a']['profile_id']==weekday['id']
    assert assignments_for(file,'pi5')['media-b']['profile_id']==weekday['id']
    assert assignments_for(file,'pi5')['media-c']['profile_id']!=weekday['id']
    # Reading must not mutate the original; the first write migrates atomically.
    assert json.loads(file.read_text(encoding='utf-8'))==original
    set_default(file,'brand-new-pi',weekday['id'])
    saved=json.loads(file.read_text(encoding='utf-8'))
    assert saved['global_profiles']==shared
    assert saved['devices']==original['devices']  # legacy backup retained
    assert saved['assignments']['pi5']['media-c']['profile_id']!=weekday['id']
    assert saved['defaults']['brand-new-pi']==weekday['id']


def test_global_schedule_shared_via_two_device_routes(hub):
    app,client,tmp_path=hub
    sign_in(client,'marketing')
    from app.schedules import default_for
    devices=json.loads(Path(app.config['DEVICES_FILE']).read_text(encoding='utf-8'))
    devices['devices'].append({'id':'lab-two','name':'Pi 2','url':'http://192.168.1.88','location':'Event'})
    Path(app.config['DEVICES_FILE']).write_text(json.dumps(devices),encoding='utf-8')
    post(client,'/devices/lab/schedules/add',{
        'name':'Werktag_Default','days':['1','2','3','4','5'],
        'start':'08:00','end':'18:00'
    })
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    page=client.get('/devices/lab-two/schedules').get_data(as_text=True)
    playlist=client.get('/devices/lab-two').get_data(as_text=True)
    assert 'Werktag_Default' in page
    assert 'Werktag_Default' in playlist
    assert 'Hubweite Zeitplan-Sammlung' in page
    post(client,'/devices/lab-two/schedules/default', {'profile_id':rule['id']})
    assert default_for(app.config['SCHEDULES_FILE'],'lab-two')==rule['id']
    assert default_for(app.config['SCHEDULES_FILE'],'lab') is None
    # Actual native settings can be applied on the second Pi, with no change to first device default.
    response=post(client,'/devices/lab-two/schedules/apply',
                  {'profile_id':rule['id'],'asset_ids':['a']})
    assert '1 Inhalte auf dem Pi' in response.get_data(as_text=True)
    assert Player.records['a']['play_time_from']=='08:00:00'


def test_shared_schedule_global_delete_requires_confirmation(hub):
    app,client,_=hub
    sign_in(client,'marketing')
    base='/devices/lab/schedules'
    post(client,base+'/add',{
        'name':'Event','days':['6'],'start':'10:00','end':'14:00'
    })
    rule=profiles_for(app.config['SCHEDULES_FILE'],'lab')[0]
    with client.session_transaction() as state:
        csrf=state['csrf']
    response=client.post(base+'/'+rule['id']+'/delete',
        data={'csrf':csrf,'confirm':rule['id']})
    assert response.status_code==400
    assert profiles_for(app.config['SCHEDULES_FILE'],'lab')==[rule]
    post(client,base+'/'+rule['id']+'/delete',
         {'confirm':rule['id'],'confirm_global':'yes'})
    assert profiles_for(app.config['SCHEDULES_FILE'],'lab')==[]
