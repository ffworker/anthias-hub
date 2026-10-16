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


def _document(path):
    file = Path(path)
    if not file.exists():
        return {'devices': {}, 'defaults': {}, 'assignments': {}}
    try:
        with file.open(encoding='utf-8') as stream:
            content = json.load(stream)
        if not isinstance(content, dict) or not isinstance(content.get('devices'), dict):
            raise ValueError()
        if not isinstance(content.get('defaults', {}), dict) or not isinstance(content.get('assignments', {}), dict):
            raise ValueError()
        content.setdefault('defaults', {})
        content.setdefault('assignments', {})
        return content
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScheduleError('Zeitplan-Datei nicht lesbar. IT muss Hub-Daten prüfen; nichts überschrieben.') from exc


def _load(path):
    return _document(path)['devices']


def profiles_for(path, device_id):
    with _LOCK:
        data = _load(path)
        profiles = data.get(device_id, [])
        if not isinstance(profiles, list):
            raise ScheduleError('Zeitplan-Datei enthält ungültige Gerätedaten.')
        return [dict(profile) for profile in profiles]


def _save(path, data):
    doc = _document(path)
    doc['devices'] = data
    _save_document(path, doc)


def _save_document(path, data):
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name('.schedules-' + secrets.token_hex(8) + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
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



def edit_profile(path, device_id, profile_id, name, days, start, end):
    profile = valid_rule(name, days, start, end)
    with _LOCK:
        data = _load(path)
        entries = data.get(device_id, [])
        index = next((i for i, e in enumerate(entries) if e['id'] == profile_id), None)
        if index is None:
            raise ScheduleError('Zeitplan nicht gefunden.')
        if any(e['id'] != profile_id and
               e['name'].casefold() == profile['name'].casefold() for e in entries):
            raise ScheduleError('Der Zeitplanname existiert bereits.')
        profile['id'] = profile_id
        entries[index] = profile
        data[device_id] = entries
        _save(path, data)
    # Existing assets keep their *native* rules until explicitly reassigned.
    return profile


def remove_profile(path, device_id, profile_id):
    with _LOCK:
        data = _load(path)
        entries = data.get(device_id, [])
        remaining = [p for p in entries if p['id'] != profile_id]
        if len(remaining) == len(entries):
            raise ScheduleError('Zeitplan nicht gefunden.')
        data[device_id] = remaining
        doc = _document(path)
        doc['devices'] = data
        if doc['defaults'].get(device_id) == profile_id:
            doc['defaults'].pop(device_id, None)
        # Keep the original Pi fields; obsolete bindings are only local labels.
        doc['assignments'].setdefault(device_id, {})
        doc['assignments'][device_id] = {
            ident: record for ident, record in doc['assignments'][device_id].items()
            if record.get('profile_id') != profile_id
        }
        _save_document(path, doc)
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


def default_for(path, device_id):
    with _LOCK:
        return _document(path)['defaults'].get(device_id)


def set_default(path, device_id, profile_id):
    """None removes the default; never alters existing player assets."""
    with _LOCK:
        doc = _document(path)
        if profile_id is not None and not any(
                entry['id'] == profile_id for entry in doc['devices'].get(device_id, [])):
            raise ScheduleError('Dieser Zeitplan gehört nicht zum ausgewählten Gerät.')
        if profile_id is None:
            doc['defaults'].pop(device_id, None)
        else:
            doc['defaults'][device_id] = profile_id
        _save_document(path, doc)


def assignments_for(path, device_id):
    with _LOCK:
        records = _document(path)['assignments'].get(device_id, {})
        if not isinstance(records, dict):
            raise ScheduleError('Ungültige Zeitplan-Zuordnungen.')
        return {ident: dict(entry) for ident, entry in records.items()}


def bind_asset(path, device_id, asset_id, profile_id, fields):
    """Record a binding ONLY after the Pi has acknowledged its native fields."""
    with _LOCK:
        doc = _document(path)
        entries = doc['assignments'].setdefault(device_id, {})
        if profile_id is None:
            entries.pop(asset_id, None)
        else:
            entries[asset_id] = {
                'profile_id': profile_id,
                'native_key': list(native_key(fields)[0:1]) +
                    [native_key(fields)[1], native_key(fields)[2]],
            }
        _save_document(path, doc)


def choice_for(path, device_id, choice, days=None, start=None, end=None):
    """Resolve a submitted choice at the moment of the write (never trust UI)."""
    profiles = profiles_for(path, device_id)
    if choice in ('', 'default', None):
        choice = default_for(path, device_id) or 'always'
    if choice == 'always':
        return None, None
    if choice == 'custom':
        return valid_rule('Individuell', days or [], start or '', end or ''), None
    profile = next((p for p in profiles if p['id'] == choice), None)
    if profile is None:
        raise ScheduleError('Zeitplan existiert nicht mehr. Bitte neu laden.')
    return profile, profile['id']


def describe_linked_asset(asset, profiles, bindings):
    """Stored identity wins over accidental identical-time matches.

    If the Pi is modified outside Hub, show drift instead of falsely claiming
    the preset still applies.
    """
    record = bindings.get(str(asset.get('asset_id')))
    if record:
        profile = next((p for p in profiles if p['id'] == record.get('profile_id')), None)
        if profile:
            try:
                if native_key(asset) != native_key(native_fields(profile)):
                    return profile['name'] + ' · Abweichend in Anthias'
            except ScheduleError:
                return 'Zeitplan auf Anthias nicht verfügbar'
            return profile['name']
    return describe_asset(asset, profiles)


def uncovered_weekdays(assets):
    """Conservative warning only: never change playback or pretend certainty.

    A 24-hour asset guarantees coverage for its active weekdays. Other time
    windows may leave gaps; we do not declare exact hours without full calendar
    evaluation. Date-bounded or malformed native data makes results unknown.
    """
    if not assets:
        return []
    from .anthias import DEFAULT_FROM, DEFAULT_TO
    for asset in assets:
        if (asset.get('start_date') not in (None, DEFAULT_FROM) or
                asset.get('end_date') not in (None, DEFAULT_TO)):
            return []
    try:
        unrestricted = set()
        for item in assets:
            if not item.get('is_enabled'):
                continue
            days, start, end = native_key(item)
            if start is None and end is None:
                unrestricted.update(days)
        return [day for day in DAYS if day not in unrestricted]
    except ScheduleError:
        return []


def weekday_warning(assets):
    """Never falsely claim no playback. Warn only about potential gaps."""
    if not assets:
        return 'Keine Inhalte in der Playlist. Anthias bestimmt die Anzeige.'
    if uncovered_weekdays(assets):
        return 'Mögliche Zeitlücken: Nicht an allen Tagen ist ein dauerhaft verfügbares Medium aktiv. Bitte Wochenzeiten prüfen.'
    return ''
