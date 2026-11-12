"""Small shared heartbeat for read-only folder imports (no credentials or paths)."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def status_path():
    return Path(os.environ.get('FOLDER_STATUS_FILE', '/data/folder-sync-status.json'))


def write_status(reports, enabled, path=None, *, interval_seconds=300, prune_missing=False):
    target = Path(path) if path else status_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    clean = {}
    for ident, report in reports.items():
        if 'error' in report:
            clean[ident] = {'state': 'error', 'added': 0, 'updated': 0,
                            'device_errors': 0}
        else:
            imp = report.get('import', {})
            targets = report.get('devices', {})
            clean[ident] = {
                'state': 'error' if any('error' in value for value in targets.values()) else 'ok',
                'added': int(imp.get('added', 0)),
                'updated': int(imp.get('updated', 0)),
                'retired': int(imp.get('retired', 0)),
                'published': sum(int(v.get('added', 0)) + int(v.get('updated', 0))
                                 for v in targets.values() if isinstance(v, dict)),
                'disabled': sum(int(v.get('disabled', 0))
                                for v in targets.values() if isinstance(v, dict)),
                'device_errors': sum('error' in value for value in targets.values()),
            }
    data = {'checked_at': datetime.now(timezone.utc).isoformat(),
            'auto_publish': bool(enabled), 'prune_missing': bool(prune_missing),
            'interval_seconds': int(interval_seconds), 'templates': clean}
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.folder-status-',
                                         mode='w', encoding='utf-8', delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def read_status(template_id, path=None):
    target = Path(path) if path else status_path()
    fallback = {'state': 'unknown', 'auto_publish': False,
                'checked_at': None, 'interval_seconds': None,
                'prune_missing': False, 'added': 0, 'updated': 0,
                'retired': 0, 'published': 0, 'disabled': 0, 'device_errors': 0}
    try:
        if target.stat().st_size > 65536:
            return fallback
        data = json.loads(target.read_text(encoding='utf-8'))
        checked = datetime.fromisoformat(data['checked_at'])
        if checked.tzinfo is None:
            return fallback
        age = (datetime.now(timezone.utc) - checked).total_seconds()
        row = data.get('templates', {}).get(template_id, {})
        if not isinstance(row, dict) or not isinstance(data.get('auto_publish'), bool):
            return fallback
        interval = data.get('interval_seconds', 300)
        if not isinstance(interval, int) or not 60 <= interval <= 86400:
            return fallback
        if age > max(900, interval * 2.5) or age < -60:
            state = 'stale'
        else:
            state = row.get('state', 'unknown')
        if state not in ('unknown', 'ok', 'error', 'stale'):
            state = 'unknown'
        return {'state': state, 'auto_publish': data['auto_publish'],
                'checked_at': checked.strftime('%d.%m.%Y %H:%M UTC'),
                'interval_seconds': interval,
                'prune_missing': data.get('prune_missing') is True,
                'added': int(row.get('added', 0)),
                'updated': int(row.get('updated', 0)),
                'retired': int(row.get('retired', 0)),
                'published': int(row.get('published', 0)),
                'disabled': int(row.get('disabled', 0)),
                'device_errors': int(row.get('device_errors', 0))}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return fallback
