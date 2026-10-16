"""Named Hub presets backed by Anthias' *native per-asset* v2 time windows.

The names live only in Hub's persistent /data, because Anthias v2 has no
named schedule entity. Playback happens entirely on the Pi using native
play_days/play_time_from/play_time_to, even if the Hub is offline.
"""
import json
import os
import re
import secrets
import threading
from pathlib import Path

from .anthias import PlayerError

_LOCK = threading.Lock()
TIME = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')
DAYS = (1, 2, 3, 4, 5, 6, 7)
MAX_PROFILES = 20


class ScheduleError(ValueError):
    pass


def valid_rule(name, days, start, end):
    name = str(name).strip()
    if (not 1 <= len(name) <= 60 or
            any(ord(ch) < 32 or ord(ch) == 127 for ch in name)):
        raise ScheduleError('Zeitplanname muss 1–60 druckbare Zeichen enthalten.')
    try:
        chosen = sorted({int(d) for d in days})
    except (ValueError, TypeError):
        raise ScheduleError('Ungültige Wochentage.') from None
    if not chosen or any(day not in DAYS for day in chosen):
        raise ScheduleError('Mindestens einen gültigen Wochentag wählen.')
    if not TIME.fullmatch(str(start)) or not TIME.fullmatch(str(end)):
        raise ScheduleError('Zeiten im Format HH:MM eingeben.')
    if start == end:
        raise ScheduleError('Start und Ende dürfen nicht identisch sein.')
    return {'name': name, 'days': chosen, 'start': start, 'end': end}


def _load(path):
    file = Path(path)
    if not file.exists():
        return {}
    try:
        with file.open(encoding='utf-8') as stream:
            content = json.load(stream)
        profiles = content['devices']
        if not isinstance(profiles, dict):
            raise ValueError()
        return profiles
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScheduleError('Zeitplan-Datei nicht lesbar. IT muss Hub-Daten prüfen; nichts überschrieben.') from exc


def profiles_for(path, device_id):
    with _LOCK:
        data = _load(path)
        profiles = data.get(device_id, [])
        if not isinstance(profiles, list):
            raise ScheduleError('Zeitplan-Datei enthält ungültige Gerätedaten.')
        return [dict(profile) for profile in profiles]


def _save(path, data):
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name('.schedules-' + secrets.token_hex(8) + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump({'devices': data}, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, file)
    finally:
        temp.unlink(missing_ok=True)


def add_profile(path, device_id, name, days, start, end):
    profile = valid_rule(name, days, start, end)
    with _LOCK:
        data = _load(path)
        entries = data.get(device_id, [])
        if not isinstance(entries, list):
            raise ScheduleError('Zeitplan-Datei enthält ungültige Gerätedaten.')
        if len(entries) >= MAX_PROFILES:
            raise ScheduleError('Höchstens 20 benannte Zeitpläne pro Gerät.')
        if any(e['name'].casefold() == profile['name'].casefold() for e in entries):
            raise ScheduleError('Der Zeitplanname existiert auf diesem Gerät bereits.')
        profile['id'] = secrets.token_hex(8)
        data[device_id] = entries + [profile]
        _save(path, data)
    return profile


def remove_profile(path, device_id, profile_id):
    with _LOCK:
        data = _load(path)
        entries = data.get(device_id, [])
        remaining = [p for p in entries if p['id'] != profile_id]
        if len(remaining) == len(entries):
            raise ScheduleError('Zeitplan nicht gefunden.')
        data[device_id] = remaining
        _save(path, data)
    # Intentional: never change an Anthias playlist when deleting a Hub preset.


def native_fields(rule=None):
    if rule is None:
        return {'play_days': list(DAYS), 'play_time_from': None, 'play_time_to': None}
    return {'play_days': list(rule['days']),
            'play_time_from': rule['start'] + ':00',
            'play_time_to': rule['end'] + ':00'}


def native_key(fields):
    """Preserve second precision: native rules modified directly on Pi stay custom."""
    days = fields.get('play_days')
    start, end = fields.get('play_time_from'), fields.get('play_time_to')
    if not isinstance(days, list) or not days or any(type(d) is not int or d not in DAYS for d in days):
        raise ScheduleError('Anthias meldet keine unterstützten Wochentagsdaten. Bitte Anthias aktualisieren.')
    if (start is None) != (end is None):
        raise ScheduleError('Anthias meldet unvollständige Zeitfenster.')
    if start is not None:
        if not isinstance(start, str) or not isinstance(end, str):
            raise ScheduleError('Anthias meldet ungültige Zeitangaben.')
        start = start[:8] if len(start) >= 8 else start + ':00'
        end = end[:8] if len(end) >= 8 else end + ':00'
    return (tuple(sorted(set(days))), start, end)


def describe_asset(asset, profiles):
    try:
        rule = native_key(asset)
        if rule == native_key(native_fields()):
            return 'Ohne Zeitplan'
        for profile in profiles:
            if rule == native_key(native_fields(profile)):
                return profile['name']
        return 'Individuell in Anthias'
    except ScheduleError:
        return 'Zeitplan auf Anthias nicht verfügbar'


def apply_to_assets(api, profile, ids):
    """Preflight every chosen ID, patch only native schedule fields, never enable
    or delete an asset. A partial failure is reported, never automatically retried.
    """
    if not ids or len(ids) > 100 or len(ids) != len(set(ids)):
        raise ScheduleError('Bitte 1–100 unterschiedliche Inhalte auswählen.')
    for ident in ids:
        api.valid_id(ident)
    current = {item['asset_id']: item for item in api.assets()}
    if any(ident not in current for ident in ids):
        raise ScheduleError('Playlist hat sich geändert. Bitte neu laden.')
    for ident in ids:
        # Crucial: old Anthias can silently ignore unknown PATCH schedule fields.
        native_key(current[ident])
    changes = native_fields(profile)
    updated = 0
    for ident in ids:
        try:
            result = api.patch(ident, changes)
            if not isinstance(result, dict) or native_key(result) != native_key(changes):
                raise ScheduleError('Anthias hat die Zeitplanung nicht bestätigt. Version prüfen.')
            updated += 1
        except (PlayerError, ScheduleError, OSError) as exc:
            raise ScheduleError(
                f'Übertragung nach {updated}/{len(ids)} Inhalten abgebrochen: {exc}. '
                'Mögliche Teiländerung – im Player prüfen, nicht blind wiederholen.'
            ) from exc
    return updated
