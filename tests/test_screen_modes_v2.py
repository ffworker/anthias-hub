"""Offline regression: one source of truth and honest SMB progress."""
import hashlib
import json
import time
from pathlib import Path

from app.screen_modes import resolve_mode
from app.media_sources import save_source
from app.source_progress import describe_sources


def test_four_modes_are_exclusive_and_offline_is_not_empty():
    network = {'id': 'f' * 32, 'folder_source': 'default/demo',
               'auto_devices': ['lab'], 'name': 'Netz'}
    manual_playlist = {'id': 'a' * 32, 'auto_devices': ['lab'],
                       'name': 'Sommer'}
    assert resolve_mode('lab', [network], assets=[{'id': 1}])['key'] == 'network'
    assert resolve_mode('lab', [manual_playlist], assets=[])['key'] == 'playlist'
    assert resolve_mode('lab', [], assets=[{'id': 1}])['key'] == 'manual'
    assert resolve_mode('lab', [], assets=[])['key'] == 'empty'
    assert resolve_mode('lab', [], assets=[], error='API down')['key'] == 'offline'
    assert resolve_mode('lab', [network, manual_playlist], assets=[])['key'] == 'conflict'


def test_source_progress_refuses_to_claim_mount_without_host_report(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    (root / 'default' / 'Bistro').mkdir(parents=True)
    registry = tmp_path / 'sources.json'
    status = tmp_path / 'status.json'
    monkeypatch.setenv('MEDIA_SOURCE_ROOT', str(root))
    monkeypatch.setenv('MEDIA_SOURCES_FILE', str(registry))
    save_source('default', '//10.11.12.13/files$/Marketing/Bildschirme', path=registry)
    waiting = describe_sources(registry, status, [], root)[0]
    assert waiting['state'] == 'pending'
    assert waiting['discovered'] == 0  # Local directory alone is NOT a mounted SMB source.
    assert waiting['stages'][1]['state'] == 'waiting'
    assert 'kein host-mountdienst' in waiting['stages'][1]['detail'].lower()
    assert waiting['last_host_check'] is None

    from app.media_sources import mount_statuses
    unc = '//10.11.12.13/files$/Marketing/Bildschirme'
    status.write_text(json.dumps({
        'checked_at': time.time(), 'sources': {
            'default': {'state': 'mounted',
                        'fingerprint': hashlib.sha256(unc.encode()).hexdigest()}
        }
    }))
    assert mount_statuses(status, registry)['default'] == 'mounted'
    confirmed = describe_sources(registry, status, [], root)[0]
    assert confirmed['stages'][1]['state'] == 'done'
    assert confirmed['stages'][2]['state'] == 'done'
    assert confirmed['discovered'] == 1
    assert confirmed['folders'][0]['name'] == 'Bistro'

    status.write_text(json.dumps({
        'checked_at': time.time() - 900,
        'sources': {'default': {'state': 'mounted',
                                'fingerprint': hashlib.sha256(unc.encode()).hexdigest()}}
    }))
    stale = describe_sources(registry, status, [], root)[0]
    assert stale['stages'][1]['state'] == 'waiting'
    assert stale['report_stale'] is True
    assert stale['discovered'] == 0
