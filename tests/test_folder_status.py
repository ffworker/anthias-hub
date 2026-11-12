"""Worker heartbeat is a safe, bounded, non-secret UI status indicator."""
from datetime import datetime, timedelta, timezone
import json
from app.folder_status import read_status, write_status


def test_folder_status_reports_health_and_server_side_publish_lock(tmp_path):
    status = tmp_path / 'folder-status.json'
    template_id = 'a' * 32
    write_status({
        template_id: {'import': {'added': 11, 'updated': 0}, 'devices': {}}
    }, False, status)
    result = read_status(template_id, status)
    assert result['state'] == 'ok'
    assert result['auto_publish'] is False
    assert result['added'] == 11
    assert 'checked_at' in result

    write_status({
        template_id: {'import': {'added': 0, 'updated': 1},
                      'devices': {'test-pi': {'error': 'private details'}}}
    }, True, status)
    contents = status.read_text(encoding='utf-8')
    assert 'private details' not in contents
    assert read_status(template_id, status)['state'] == 'error'


def test_missing_corrupt_and_stale_status_fail_closed(tmp_path):
    status = tmp_path / 'folder-status.json'
    assert read_status('a' * 32, status)['state'] == 'unknown'
    status.write_text('{broken')
    assert read_status('a' * 32, status)['state'] == 'unknown'
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    status.write_text(json.dumps({'checked_at': old.isoformat(), 'auto_publish': True,
                                  'templates': {'a' * 32: {'state': 'ok'}}}))
    assert read_status('a' * 32, status)['state'] == 'stale'
    status.write_text('x' * 70000)
    assert read_status('a' * 32, status)['state'] == 'unknown'


def test_half_hour_heartbeat_reports_correct_timing_and_retire_counts(tmp_path):
    status = tmp_path / 'status.json'
    ident = 'f' * 32
    write_status({ident: {'import': {'added': 1, 'updated': 2, 'retired': 3},
                          'devices': {'lab': {'added': 1, 'updated': 2, 'disabled': 3}}}},
                 True, status, interval_seconds=1800, prune_missing=True)
    report = read_status(ident, status)
    assert report['state'] == 'ok'
    assert report['interval_seconds'] == 1800
    assert report['prune_missing'] is True
    assert report['published'] == 3
    assert report['disabled'] == 3
    assert report['retired'] == 3

    # A 30-minute worker must not show as stale after 16 minutes.
    data = json.loads(status.read_text(encoding='utf-8'))
    data['checked_at'] = (datetime.now(timezone.utc) -
                          timedelta(minutes=16)).isoformat()
    status.write_text(json.dumps(data), encoding='utf-8')
    assert read_status(ident, status)['state'] == 'ok'
    data['checked_at'] = (datetime.now(timezone.utc) -
                          timedelta(minutes=80)).isoformat()
    status.write_text(json.dumps(data), encoding='utf-8')
    assert read_status(ident, status)['state'] == 'stale'
