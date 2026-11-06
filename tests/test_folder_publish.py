"""Offline safety contract for opt-in folder->Pi publication."""
import io
import json

import pytest

from app.folder_publish import PublishError, _name, reconcile
from app.folder_sync import run_cycle
from app.library import Library, LibraryError


PNG = b'\x89PNG\r\n\x1a\n' + b'first version'


class FakePlayer:
    def __init__(self):
        self.entries = {}
        self.events = []
        self.seq = 0

    def assets(self):
        return list(self.entries.values())

    def upload(self, stream, filename, mime):
        self.events.append(('upload', filename))
        return {'uri': '/data/anthias_assets/' + str(len(self.events)) + '.png', 'ext': '.png'}

    def create(self, name, uri, duration, mimetype='webpage', ext=None, *, enabled=True, schedule=None):
        self.seq += 1
        ident = 'asset' + str(self.seq)
        self.entries[ident] = {'asset_id': ident, 'name': name, 'uri': uri,
                               'duration': duration, 'mimetype': mimetype, 'ext': ext,
                               'is_enabled': enabled, 'play_order': self.seq,
                               'play_days': [1, 2, 3, 4, 5, 6, 7],
                               'play_time_from': None, 'play_time_to': None}
        self.events.append(('create', ident, enabled))
        return {'asset_id': ident}

    def patch(self, ident, changes):
        self.events.append(('patch', ident, dict(changes)))
        self.entries[ident].update(changes)
        return dict(self.entries[ident])

    def remove(self, ident):
        raise AssertionError('No remote DELETE allowed in automatic sync')

    def order(self, ids):
        raise AssertionError('No automatic playlist reordering allowed')


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    source = tmp_path / 'sources'
    folder = source / 'bistro'
    folder.mkdir(parents=True)
    (folder / 'banner.png').write_bytes(PNG)
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(source))
    store = Library(tmp_path / 'library')
    template = store.create('Bistro')
    store.set_folder_source(template['id'], 'bistro')
    devices = tmp_path / 'devices.json'
    devices.write_text(json.dumps({'devices': [
        {'id': 'lab', 'name': 'Test Pi', 'url': 'http://10.10.0.21', 'location': ''},
        {'id': 'other', 'name': 'Other Pi', 'url': 'http://10.10.0.22', 'location': ''},
    ]}))
    store.set_auto_devices(template['id'], ['lab'],
                           json.loads(devices.read_text())['devices'])
    player = FakePlayer()
    player.entries['manual'] = {'asset_id': 'manual', 'name': 'My manual item',
        'uri': 'https://example.org', 'is_enabled': True,
        'play_days': [1,2,3,4,5,6,7], 'play_time_from': None, 'play_time_to': None}
    return {'folder': folder, 'store': store, 'template': template['id'],
            'devices': str(devices), 'player': player,
            'state': str(tmp_path / 'publications'), 'schedules': str(tmp_path / 'schedules.json')}


def perform(env, **overrides):
    args = dict(devices_file=env['devices'], state_root=env['state'],
                schedules_file=env['schedules'], api_factory=lambda device: env['player'])
    args.update(overrides)
    return reconcile(env['store'], env['template'], 'lab', **args)


def test_first_publish_idempotency_and_no_manual_changes(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    assert perform(env)['added'] == 1
    assert 'manual' in env['player'].entries
    assert len(env['player'].entries) == 2
    assert perform(env)['unchanged'] == 1
    assert sum(1 for evt in env['player'].events if evt[0] == 'upload') == 1
    assert env['player'].entries['manual']['is_enabled'] is True
    assert env['player'].entries['asset1']['is_enabled'] is True


def test_changed_file_stages_new_version_and_disables_only_old(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    perform(env)
    env['player'].patch('asset1', {'play_days': [1, 2, 3],
                                   'play_time_from': '09:00:00',
                                   'play_time_to': '17:00:00'})
    (env['folder'] / 'banner.png').write_bytes(PNG + b'new')
    assert sync_template(env['store'], env['template'])['updated'] == 1
    result = perform(env)
    assert result['updated'] == 1
    assert env['player'].entries['asset1']['is_enabled'] is False
    assert env['player'].entries['asset2']['is_enabled'] is True
    assert env['player'].entries['asset2']['play_days'] == [1, 2, 3]
    assert env['player'].entries['asset2']['play_time_from'] == '09:00:00'
    assert env['player'].entries['asset2']['play_time_to'] == '17:00:00'
    assert env['player'].entries['manual']['is_enabled'] is True
    assert perform(env)['unchanged'] == 1


def test_manual_disable_on_existing_asset_is_respected(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    perform(env)
    env['player'].patch('asset1', {'is_enabled': False})
    (env['folder'] / 'banner.png').write_bytes(PNG + b'edited')
    sync_template(env['store'], env['template'])
    perform(env)
    assert env['player'].entries['asset1']['is_enabled'] is False
    assert env['player'].entries['asset2']['is_enabled'] is False


def test_out_of_band_rename_blocks_mutation(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    perform(env)
    env['player'].entries['asset1']['name'] = 'Renamed in player'
    (env['folder'] / 'banner.png').write_bytes(PNG + b'v2')
    sync_template(env['store'], env['template'])
    previous_events = list(env['player'].events)
    with pytest.raises(PublishError, match='umbenannt'):
        perform(env)
    assert env['player'].events == previous_events


def test_adopts_existing_exact_version_after_interrupted_commit(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    item = env['store'].get(env['template'])['items'][0]
    name = _name(env['template'], item['source_file'], item)
    env['player'].create(name, '/data/anthias_assets/staged.png', 15, enabled=False)
    assert perform(env)['added'] == 1
    assert len(env['player'].entries) == 2
    assert sum(e[0] == 'upload' for e in env['player'].events) == 0
    assert env['player'].entries['asset1']['is_enabled'] is True


def test_run_cycle_off_by_default_and_opt_in_target_only(setup):
    env = setup
    settings = dict(library_dir=str(env['store'].root), devices_file=env['devices'],
                    state_root=env['state'], schedules_file=env['schedules'],
                    api_factory=lambda device: env['player'])
    run_cycle(auto_publish=False, **settings)
    assert len(env['player'].entries) == 1
    out = run_cycle(auto_publish=True, **settings)
    assert out[env['template']]['devices']['lab']['added'] == 1
    assert len(env['player'].entries) == 2
    assert set(out[env['template']]['devices']) == {'lab'}


def test_revoked_device_mapping_never_writes(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    env['store'].set_auto_devices(env['template'], [],
                                  json.loads(open(env['devices']).read())['devices'])
    assert perform(env) == {'added': 0, 'updated': 0, 'disabled': 0, 'unchanged': 0}
    assert not env['player'].events


def test_failed_import_never_publishes(setup):
    env = setup
    (env['folder'] / 'banner.png').write_bytes(b'invalid media')
    out = run_cycle(auto_publish=True,
                    library_dir=str(env['store'].root), devices_file=env['devices'],
                    state_root=env['state'], schedules_file=env['schedules'],
                    api_factory=lambda device: env['player'])
    assert 'error' in out[env['template']]
    assert len(env['player'].entries) == 1


def test_library_rejects_unregistered_device_and_requires_folder(tmp_path, monkeypatch):
    store = Library(tmp_path / 'library')
    ident = store.create('No folder')['id']
    with pytest.raises(LibraryError):
        store.set_auto_devices(ident, ['lab'], [{'id': 'lab'}])
    with pytest.raises(LibraryError):
        store.set_auto_devices(ident, ['missing'], [{'id': 'lab'}])


def test_switching_imported_source_does_not_mix_old_files(setup, tmp_path, monkeypatch):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    source_root = env['folder'].parent
    (source_root / 'empfang').mkdir()
    with pytest.raises(LibraryError, match='neue Vorlage'):
        env['store'].set_folder_source(env['template'], 'empfang')
    assert env['store'].get(env['template'])['folder_source'] == 'bistro'
    env['store'].set_folder_source(env['template'], '')
    assert env['store'].get(env['template'])['auto_devices'] == []
    env['store'].set_folder_source(env['template'], 'bistro')
    assert env['store'].get(env['template'])['folder_source'] == 'bistro'
