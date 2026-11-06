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
