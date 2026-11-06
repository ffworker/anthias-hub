"""Small shared heartbeat for read-only folder imports (no credentials or paths)."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def status_path():
    return Path(os.environ.get('FOLDER_STATUS_FILE', '/data/folder-sync-status.json'))


def write_status(reports, enabled, path=None):
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
                'device_errors': sum('error' in value for value in targets.values()),
            }
    data = {'checked_at': datetime.now(timezone.utc).isoformat(),
            'auto_publish': bool(enabled), 'templates': clean}
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
    fallback = {'state': 'unknown', 'auto_publish': False, 'checked_at': None}
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
        if age > 900 or age < -60:
            state = 'stale'
        else:
            state = row.get('state', 'unknown')
        if state not in ('unknown', 'ok', 'error', 'stale'):
            state = 'unknown'
        return {'state': state, 'auto_publish': data['auto_publish'],
                'checked_at': checked.strftime('%d.%m.%Y %H:%M UTC'),
                'added': int(row.get('added', 0)),
                'updated': int(row.get('updated', 0))}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return fallback
