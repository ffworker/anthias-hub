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


def test_marketing_changes_published_image_duration_without_reupload(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    first = env['store'].get(env['template'])['items'][0]
    env['store'].update_item_duration(env['template'], first['id'], '37')
    assert perform(env)['added'] == 1
    assert env['player'].entries['asset1']['duration'] == 37
    assert perform(env)['unchanged'] == 1
    env['store'].update_item_duration(env['template'], first['id'], '52')
    assert perform(env)['updated'] == 1
    assert env['player'].entries['asset1']['duration'] == 52
    assert sum(event[0] == 'upload' for event in env['player'].events) == 1

    # Replacing the SMB file must retain the Marketing-selected timing and
    # stable template item identity; only its media hash changes.
    (env['folder'] / 'banner.png').write_bytes(PNG + b'updated file')
    assert sync_template(env['store'], env['template'])['updated'] == 1
    new_item = env['store'].get(env['template'])['items'][0]
    assert new_item['id'] == first['id']
    assert new_item['duration'] == 52
    assert perform(env)['updated'] == 1
    assert env['player'].entries['asset2']['duration'] == 52


def test_rss_web_feed_auto_publishes_with_folder_and_updates_duration(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    template = env['store'].add_url(env['template'], 'Bistro RSS2Slideshow',
                                    'http://192.0.2.55/feed', 30)
    web = next(item for item in template['items'] if item['kind'] == 'url')
    assert perform(env)['added'] == 2
    assert len(env['player'].entries) == 3
    rss = next(entry for entry in env['player'].entries.values()
               if entry.get('uri') == 'http://192.0.2.55/feed')
    assert rss['mimetype'] == 'webpage'
    assert rss['duration'] == 30
    assert '[HubWeb:' in rss['name']
    assert perform(env)['unchanged'] == 2
    env['store'].update_item_duration(env['template'], web['id'], '75')
    assert perform(env)['updated'] == 1
    rss = next(entry for entry in env['player'].entries.values()
               if entry.get('uri') == 'http://192.0.2.55/feed')
    assert rss['duration'] == 75
    assert len(env['player'].entries) == 3


def test_invalid_duration_never_changes_imported_file(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    item = env['store'].get(env['template'])['items'][0]
    for seconds in ('0', '3601', 'banana', ''):
        with pytest.raises(LibraryError):
            env['store'].update_item_duration(env['template'], item['id'], seconds)
    assert env['store'].get(env['template'])['items'][0]['duration'] == 15


def test_video_duration_remains_automatic(tmp_path):
    store = Library(tmp_path / 'library')
    ident = store.create('Clips')['id']
    store.add_media(ident, 'Clip', io.BytesIO(b'\x00\x00\x00\x18ftyp' + b'video'),
                    'clip.mp4', 15)
    item = store.get(ident)['items'][0]
    assert item['duration'] == 0
    with pytest.raises(LibraryError, match='voller Länge'):
        store.update_item_duration(ident, item['id'], '30')


class OrderedPlayer(FakePlayer):
    """Anthias-like ordered assets for a dedicated, Hub-managed display."""
    def assets(self):
        return sorted(self.entries.values(),
                      key=lambda asset: (asset.get('play_order', 0), asset['asset_id']))

    def order(self, ids):
        assert set(ids) == set(self.entries)
        self.events.append(('order', tuple(ids)))
        for index, ident in enumerate(ids, 1):
            self.entries[ident]['play_order'] = index
        return {'success': True}


def test_folder_playlist_reordering_matches_template_on_dedicated_player(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    env['store'].add_url(env['template'], 'Bistro RSS',
                         'http://192.0.2.44/feed', 45)
    env['player'] = OrderedPlayer()  # New Anthias Pi: no unrelated manual items.
    assert perform(env)['added'] == 2
    template = env['store'].get(env['template'])
    web = next(item for item in template['items'] if item['kind'] == 'url')
    assert env['player'].assets()[0]['asset_id'] == 'asset1'

    # Marketing changes the template order. Subsequent sync must reorder
    # exactly once and never duplicate or re-upload the existing media.
    env['store'].move(env['template'], web['id'], 'up')
    assert perform(env)['unchanged'] == 2
    assert [item['asset_id'] for item in env['player'].assets()] == ['asset2', 'asset1']
    assert sum(e[0] == 'order' for e in env['player'].events) == 1
    assert perform(env)['unchanged'] == 2
    assert sum(e[0] == 'order' for e in env['player'].events) == 1

    # New version disables old asset. New slide retains its library position;
    # obsolete files stay at the end, disabled, never deleted.
    (env['folder'] / 'banner.png').write_bytes(PNG + b'new revision')
    assert sync_template(env['store'], env['template'])['updated'] == 1
    assert perform(env)['updated'] == 1
    assert [item['asset_id'] for item in env['player'].assets()] == ['asset2', 'asset3', 'asset1']
    assert env['player'].entries['asset1']['is_enabled'] is False
    assert env['player'].entries['asset3']['is_enabled'] is True


def test_reconcile_never_reorders_existing_mixed_manual_playlist(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    env['store'].add_url(env['template'], 'RSS',
                         'http://192.0.2.44/feed', 45)
    player = OrderedPlayer()
    player.entries['manual'] = {
        'asset_id': 'manual', 'name': 'Manually managed announcement',
        'uri': 'https://example.org/other', 'play_order': 1,
        'is_enabled': True
    }
    env['player'] = player
    perform(env)
    assert not any(event[0] == 'order' for event in player.events)
    web = next(i for i in env['store'].get(env['template'])['items']
               if i['kind'] == 'url')
    env['store'].move(env['template'], web['id'], 'up')
    perform(env)
    assert not any(event[0] == 'order' for event in player.events)
    assert player.entries['manual']['is_enabled'] is True


def test_missing_remote_managed_media_is_restored_from_folder_without_duplicates(setup):
    """Missing Pi media should be recreated from the cached verified source."""
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'])
    assert perform(env)['added'] == 1
    env['player'].entries.pop('asset1')  # Simulate removed/corrupt Pi asset.
    restored = perform(env)
    assert restored['updated'] == 1
    assert 'asset2' in env['player'].entries
    assert env['player'].entries['asset2']['is_enabled'] is True
    assert perform(env)['unchanged'] == 1
    assert sum(x[0] == 'upload' for x in env['player'].events) == 2
    assert 'manual' in env['player'].entries  # Unrelated data is never cleared.


def test_missing_source_needs_two_nonempty_scans_then_only_owned_asset_disabled(setup):
    """Source cleanup is opt-in, never DELETEs a Pi medium, and preserves manual."""
    env = setup
    from app.folder_sync import sync_template
    (env['folder'] / 'second.png').write_bytes(PNG + b'second')
    sync_template(env['store'], env['template'], prune_missing=True)
    assert perform(env)['added'] == 2
    (env['folder'] / 'banner.png').unlink()
    first = sync_template(env['store'], env['template'], prune_missing=True)
    assert first['retired'] == 0
    assert len(env['store'].get(env['template'])['items']) == 2
    assert perform(env, retire_missing=True)['disabled'] == 0
    second = sync_template(env['store'], env['template'], prune_missing=True)
    assert second['retired'] == 1
    template = env['store'].get(env['template'])
    assert [row['source_file'] for row in template['items']] == ['second.png']
    result = perform(env, retire_missing=True)
    assert result['disabled'] == 1
    assert env['player'].entries['asset1']['is_enabled'] is False
    assert env['player'].entries['asset2']['is_enabled'] is True
    assert env['player'].entries['manual']['is_enabled'] is True
    assert perform(env, retire_missing=True)['disabled'] == 0
    assert not any(ev[0] == 'remove' for ev in env['player'].events)
    # Reappearing identical bytes are reactivated, not duplicated or deleted.
    (env['folder'] / 'banner.png').write_bytes(PNG)
    assert sync_template(env['store'], env['template'], prune_missing=True)['added'] == 1
    assert perform(env, retire_missing=True)['added'] == 1
    assert env['player'].entries['asset1']['is_enabled'] is True
    assert perform(env, retire_missing=True)['unchanged'] == 2


def test_empty_source_never_prunes_even_with_opt_in(setup):
    env = setup
    from app.folder_sync import sync_template
    sync_template(env['store'], env['template'], prune_missing=True)
    perform(env)
    (env['folder'] / 'banner.png').unlink()
    for _ in range(3):
        result = sync_template(env['store'], env['template'], prune_missing=True)
        assert result['retired'] == 0
    assert len(env['store'].get(env['template'])['items']) == 1
    assert perform(env, retire_missing=True)['disabled'] == 0
    assert env['player'].entries['asset1']['is_enabled'] is True


def test_v2_manual_playlist_publishes_only_owned_media_when_explicitly_enabled(
        tmp_path, monkeypatch):
    """A fixed manual playlist is a real publisher, not just an info badge."""
    monkeypatch.setenv('HUB_WORKFLOW_V2', '1')
    store = Library(tmp_path / 'library')
    template = store.create('Zentrale Playlist')
    media = store.add_media(template['id'], 'Logo',
                            io.BytesIO(PNG), 'logo.png', 15)
    devices = tmp_path / 'devices.json'
    devices.write_text(json.dumps({'devices': [
        {'id': 'lab', 'name': 'Test Pi', 'url': 'http://10.10.0.21', 'location': ''}
    ]}))
    store.set_auto_devices(template['id'], ['lab'],
                           json.loads(devices.read_text())['devices'],
                           allow_manual=True)
    player = FakePlayer()
    player.entries['outside'] = {
        'asset_id': 'outside', 'name': 'Manually added Pi content',
        'uri': 'https://example.org', 'is_enabled': True,
    }
    options = dict(library_dir=str(tmp_path / 'library'),
                   devices_file=str(devices), state_root=str(tmp_path / 'publications'),
                   schedules_file=str(tmp_path / 'schedules.json'),
                   api_factory=lambda d: player)
    off = run_cycle(auto_publish=False, **options)
    assert off[template['id']]['devices'] == {}
    assert not player.events

    on = run_cycle(auto_publish=True, **options)
    assert on[template['id']]['devices']['lab']['added'] == 1
    assert player.entries['outside']['is_enabled'] is True
    assert len([event for event in player.events if event[0] == 'upload']) == 1
    repeat = run_cycle(auto_publish=True, **options)
    assert repeat[template['id']]['devices']['lab']['unchanged'] == 1

    store.remove(template['id'], media['id'])
    clean = run_cycle(auto_publish=True, **options)
    assert clean[template['id']]['devices']['lab']['disabled'] == 1
    assert player.entries['outside']['is_enabled'] is True
    assert not any(event[0] == 'remove' for event in player.events)
