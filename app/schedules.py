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
MAX_PROFILES = 100


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


def _migrate_legacy(doc):
    """In-memory, lossless promotion of per-device rules into one global library.

    Identical name+window on different Pis becomes ONE shared preset. A same
    name with different windows is renamed with the originating device ID,
    never silently overwritten. Old device-scoped records are retained for
    recovery; the new global key is saved atomically on the next mutation.
    """
    if 'global_profiles' in doc:
        if not isinstance(doc['global_profiles'], list):
            raise ValueError('invalid global schedule list')
        return doc

    shared = []
    defaults = dict(doc['defaults'])
    assignments = {d: dict(records) for d, records in doc['assignments'].items()}
    for device_id, entries in doc['devices'].items():
        if not isinstance(entries, list):
            raise ValueError('invalid device schedule list')
        remap = {}
        for item in entries:
            profile = dict(item)
            if not isinstance(profile.get('id'), str):
                raise ValueError('invalid schedule ID')
            existing = next((p for p in shared if
                             p['name'].casefold() == profile['name'].casefold() and
                             p['days'] == profile['days'] and
                             p['start'] == profile['start'] and
                             p['end'] == profile['end']), None)
            if existing:
                remap[profile['id']] = existing['id']
                continue
            if any(p['name'].casefold() == profile['name'].casefold() for p in shared):
                # Explicit conflict marker preserves the original Pi's distinct rule.
                base = profile['name'][:max(1, 56 - len(device_id))]
                profile['name'] = (base + ' (' + device_id[:12] + ')')[:60]
                index = 2
                while any(p['name'].casefold() == profile['name'].casefold() for p in shared):
                    suffix = ' (' + str(index) + ')'
                    profile['name'] = (base[:60 - len(suffix)] + suffix)
                    index += 1
            if any(p['id'] == profile['id'] for p in shared):
                profile['id'] = secrets.token_hex(8)
            remap[item['id']] = profile['id']
            shared.append(profile)
        if defaults.get(device_id) in remap:
            defaults[device_id] = remap[defaults[device_id]]
        for record in assignments.get(device_id, {}).values():
            if record.get('profile_id') in remap:
                record['profile_id'] = remap[record['profile_id']]
    doc['global_profiles'] = shared
    doc['defaults'] = defaults
    doc['assignments'] = assignments
    return doc


def _document(path):
    file = Path(path)
    if not file.exists():
        return {'devices': {}, 'global_profiles': [], 'defaults': {}, 'assignments': {}}
    try:
        with file.open(encoding='utf-8') as stream:
            content = json.load(stream)
        if not isinstance(content, dict) or not isinstance(content.get('devices'), dict):
            raise ValueError()
        if not isinstance(content.get('defaults', {}), dict) or not isinstance(content.get('assignments', {}), dict):
            raise ValueError()
        content.setdefault('defaults', {})
        content.setdefault('assignments', {})
        return _migrate_legacy(content)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ScheduleError('Zeitplan-Datei nicht lesbar. IT muss Hub-Daten prüfen; nichts überschrieben.') from exc


def profiles_for(path, device_id=None):
    """The whole Hub has one common preset collection. Device is optional."""
    with _LOCK:
        return [dict(item) for item in _document(path)['global_profiles']]


def _save(path, data):
    doc = _document(path)
    doc['global_profiles'] = data
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
    """Add to the shared library, regardless of the currently open Pi."""
    profile = valid_rule(name, days, start, end)
    with _LOCK:
        doc = _document(path)
        entries = doc['global_profiles']
        if len(entries) >= MAX_PROFILES:
            raise ScheduleError('Höchstens 100 gemeinsame Zeitpläne im Hub.')
        if any(e['name'].casefold() == profile['name'].casefold() for e in entries):
            raise ScheduleError('Dieser Zeitplanname existiert bereits in der gemeinsamen Sammlung.')
        profile['id'] = secrets.token_hex(8)
        doc['global_profiles'] = entries + [profile]
        _save_document(path, doc)
    return profile


def edit_profile(path, device_id, profile_id, name, days, start, end):
    profile = valid_rule(name, days, start, end)
    with _LOCK:
        doc = _document(path)
        entries = doc['global_profiles']
        index = next((i for i, item in enumerate(entries)
                      if item['id'] == profile_id), None)
        if index is None:
            raise ScheduleError('Zeitplan nicht gefunden.')
        if any(item['id'] != profile_id and
               item['name'].casefold() == profile['name'].casefold()
               for item in entries):
            raise ScheduleError('Dieser Name existiert bereits in der gemeinsamen Sammlung.')
        profile['id'] = profile_id
        entries[index] = profile
        _save_document(path, doc)
    # Updates never silently push to other Pis.
    return profile


def remove_profile(path, device_id, profile_id):
    with _LOCK:
        doc = _document(path)
        entries = doc['global_profiles']
        remaining = [p for p in entries if p['id'] != profile_id]
        if len(remaining) == len(entries):
            raise ScheduleError('Zeitplan nicht gefunden.')
        doc['global_profiles'] = remaining
        # A global deletion must clear the default and binding on EVERY device.
        # The actual native Pi times remain unchanged.
        for ident, default_id in list(doc['defaults'].items()):
            if default_id == profile_id:
                doc['defaults'].pop(ident, None)
        for ident, records in doc['assignments'].items():
            doc['assignments'][ident] = {
                asset_id: record for asset_id, record in records.items()
                if record.get('profile_id') != profile_id
            }
        _save_document(path, doc)


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


def apply_to_assets(api, profile, ids, on_applied=None):
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
            if on_applied is not None:
                on_applied(ident, changes)
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
                entry['id'] == profile_id for entry in doc['global_profiles']):
            raise ScheduleError('Dieser Zeitplan existiert nicht in der gemeinsamen Sammlung.')
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


def linked_native_key(record):
    """Last rules actually confirmed by the Pi, not today's global template."""
    snapshot = record.get('native_key')
    if not (isinstance(snapshot, list) and len(snapshot) == 3 and
            isinstance(snapshot[0], list)):
        return None
    return (tuple(snapshot[0]), snapshot[1], snapshot[2])


def describe_linked_asset(asset, profiles, bindings):
    """Keep shared template updates distinct from external Pi changes."""
    record = bindings.get(str(asset.get('asset_id')))
    if record:
        profile = next((p for p in profiles if p['id'] == record.get('profile_id')), None)
        if profile:
            try:
                actual = native_key(asset)
                if actual == native_key(native_fields(profile)):
                    return profile['name']
                if actual == linked_native_key(record):
                    return profile['name'] + ' · Aktualisierung ausstehend'
                return profile['name'] + ' · Abweichend in Anthias'
            except ScheduleError:
                return 'Zeitplan auf Anthias nicht verfügbar'
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
