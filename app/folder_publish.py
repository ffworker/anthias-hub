"""Opt-in folder -> Anthias player reconciliation.

Only the assets created by this feature are touched. Every asset carries a
deterministic versioned marker, allowing safe adoption after a crash between
the remote create and local journal commit. Manual playlist entries stay intact.
"""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .anthias import Anthias, PlayerError, ASSET_ID
from .devices import ID as DEVICE_ID, get
from .library import LibraryError, _ID as TEMPLATE_ID, _MEDIA
from .schedules import ScheduleError, default_for, native_fields, native_key, profiles_for


class PublishError(RuntimeError):
    pass


def _name(template_id, source_file, item):
    digest = item['file'].split('/')[-1].split('.')[0]
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        raise PublishError('Ungültiger Medienhash in Hub-Vorlage')
    key = hashlib.sha256((template_id + ':' + source_file).encode('utf-8')).hexdigest()[:12]
    suffix = f' [Hub:{key}-{digest[:12]}]'
    return item['name'][:100 - len(suffix)] + suffix


def _state_path(root, template_id, device_id):
    if not TEMPLATE_ID.fullmatch(template_id) or not DEVICE_ID.fullmatch(device_id):
        raise PublishError('Ungültige Vorlagen- oder Geräte-ID')
    return Path(root) / template_id / (device_id + '.json')


def _load(path):
    if not path.exists():
        return {'version': 1, 'assets': {}}
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(doc, dict) or doc.get('version') != 1 or
                not isinstance(doc.get('assets'), dict)):
            raise ValueError('format')
        return doc
    except (OSError, ValueError) as exc:
        raise PublishError('Synchronisationsstatus beschädigt; keine Änderungen am Pi') from exc


def _save(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.pub-', delete=False,
                                         mode='w', encoding='utf-8') as handle:
            tmp = Path(handle.name)
            json.dump(doc, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _remote_assets(api):
    assets = api.assets()
    if not isinstance(assets, list) or any(
            not isinstance(x, dict) or not ASSET_ID.fullmatch(str(x.get('asset_id', '')))
            for x in assets):
        raise PublishError('Anthias liefert keine gültigen Asset-IDs')
    return assets


def _owned(existing, record):
    """Never modify a remote asset whose name has changed outside the Hub."""
    if not record:
        return None
    ident, name = record.get('asset_id'), record.get('name')
    if not isinstance(ident, str) or not ASSET_ID.fullmatch(ident) or not isinstance(name, str):
        raise PublishError('Ungültiger gespeicherter Asset-Verweis')
    match = next((x for x in existing if x['asset_id'] == ident), None)
    if match and match.get('name') != name:
        raise PublishError('Verwaltetes Asset wurde extern umbenannt; keine Änderung am Pi')
    return match


def _matching(existing, name):
    found = [x for x in existing if x.get('name') == name]
    if len(found) > 1:
        raise PublishError('Mehrere gleichnamige Hub-Assets; IT muss Playlist prüfen')
    return found[0] if found else None


def _schedule_fields(existing_asset, schedules_file, device_id):
    """Carry forward current native per-asset schedule, not a stale Hub preset."""
    if existing_asset is not None:
        try:
            native_key(existing_asset)  # reject partial/unsupported schedule API
        except ScheduleError as exc:
            raise PublishError('Alter Zeitplan nicht lesbar; alte Playlist bleibt aktiv') from exc
        return {key: existing_asset[key] for key in
                ('play_days', 'play_time_from', 'play_time_to')}
    profile_id = default_for(schedules_file, device_id)
    if not profile_id:
        return None
    profile = next((p for p in profiles_for(schedules_file, device_id)
                    if p['id'] == profile_id), None)
    if profile is None:
        raise PublishError('Geräte-Standardzeitplan fehlt; keine automatische Veröffentlichung')
    return native_fields(profile)


def _confirm_schedule(api, asset_id, fields):
    if fields is None:
        return
    result = api.patch(asset_id, fields)
    try:
        if not isinstance(result, dict) or native_key(result) != native_key(fields):
            raise PublishError('Anthias hat neuen Zeitplan nicht bestätigt')
    except ScheduleError as exc:
        raise PublishError('Anthias-Zeitplan-API inkompatibel') from exc


def reconcile(store, template_id, device_id, *,
              devices_file='/data/devices.json', state_root='/data/folder-publications',
              schedules_file='/data/schedules.json', api_factory=Anthias):
    """Reconcile one explicitly opted-in pair; raises and leaves other devices alone.

    No remote DELETE calls, no global reordering, and no automatic retries of
    uncertain partial writes in a single pass. Superseded assets are disabled
    but retained for manual recovery.
    """
    template = store.get(template_id)
    if not template.get('folder_source') or device_id not in template.get('auto_devices', []):
        return {'added': 0, 'updated': 0, 'disabled': 0, 'unchanged': 0}
    device = get(devices_file, device_id)
    if device is None:
        raise PublishError('Zielbildschirm nicht mehr registriert')
    path = _state_path(state_root, template_id, device_id)
    doc = _load(path)
    api = api_factory(device)
    existing = _remote_assets(api)
    stats = {'added': 0, 'updated': 0, 'disabled': 0, 'unchanged': 0}

    # Import-only entries from a folder source; manual Hub media/URLs are
    # never implicitly sent or changed by this worker.
    for item in template['items']:
        if item.get('kind') != 'media' or not item.get('source_file'):
            continue
        source = item['source_file']
        if not isinstance(source, str) or '/' in source or '\\' in source or not source:
            raise PublishError('Ungültiger Quelldateiname')
        record = doc['assets'].get(source)
        if record is not None and not isinstance(record, dict):
            raise PublishError('Ungültiger Medienstatus; keine Änderungen')
        old = _owned(existing, record)
        name = _name(template_id, source, item)
        revision = item['file'].split('/')[-1].split('.')[0]
        target = _matching(existing, name)

        # Do not hash huge video files every 5 minutes when the managed
        # revision already exists. Fresh/changed imports are fully verified.
        if record and record.get('revision') == revision and old and old['asset_id'] == record['asset_id']:
            stats['unchanged'] += 1
            continue
        media_path = store.verified_media_path(template_id, item)
        media_type = _MEDIA.get(media_path.suffix.lower())
        if not media_type:
            raise PublishError('Ungültiger Medientyp')

        # A previous run may have created the asset but crashed before saving
        # the journal. Adopt by its exact versioned name instead of duplicating.
        fields = _schedule_fields(old, schedules_file, device_id)
        if target is None:
            with media_path.open('rb') as stream:
                uploaded = api.upload(stream, media_path.name, media_type)
            result = api.create(name, uploaded['uri'],
                                item['duration'], mimetype=media_type,
                                ext=uploaded.get('ext'), enabled=False)
            if not isinstance(result, dict) or not ASSET_ID.fullmatch(str(result.get('asset_id', ''))):
                raise PublishError('Unbekannte Anthias-Asset-ID; Playlist vor Wiederholung prüfen')
            existing = _remote_assets(api)
            target = _matching(existing, name)
            if target is None or target['asset_id'] != result['asset_id']:
                raise PublishError('Neues Asset auf Anthias nicht bestätigt; Playlist prüfen')
            _confirm_schedule(api, target['asset_id'], fields)
        else:
            # Adopted asset is not trusted for modifying existing content
            # other than its own exact deterministic name.
            if target.get('uri') in ('', None):
                raise PublishError('Vorhandenes Hub-Asset ohne Medienadresse')
            if fields:
                _confirm_schedule(api, target['asset_id'], fields)

        enable = old is None or bool(old.get('is_enabled'))
        if enable and not target.get('is_enabled'):
            api.patch(target['asset_id'], {'is_enabled': True})
        existing = _remote_assets(api)
        target = _matching(existing, name)
        if target is None or (enable and not target.get('is_enabled')):
            raise PublishError('Aktivierung nicht bestätigt; altes Asset bleibt unangetastet')

        if old and old['asset_id'] != target['asset_id'] and old.get('is_enabled'):
            api.patch(old['asset_id'], {'is_enabled': False})
            existing = _remote_assets(api)
            prior = _owned(existing, record)
            if prior and prior.get('is_enabled') is not False:
                raise PublishError('Alte Version blieb aktiv; IT muss Playlist prüfen')

        doc['assets'][source] = {'asset_id': target['asset_id'], 'name': name,
                                 'revision': revision, 'status': 'active'}
        _save(path, doc)
        stats['updated' if record else 'added'] += 1
        existing = _remote_assets(api)
    return stats


def reconcile_all(store, devices_file='/data/devices.json',
                  state_root='/data/folder-publications',
                  schedules_file='/data/schedules.json', api_factory=Anthias):
    results = {}
    for template in store.list():
        if not template.get('folder_source'):
            continue
        for device_id in template.get('auto_devices', []):
            try:
                results[(template['id'], device_id)] = reconcile(
                    store, template['id'], device_id, devices_file=devices_file,
                    state_root=state_root, schedules_file=schedules_file,
                    api_factory=api_factory)
            except (PublishError, PlayerError, LibraryError, ScheduleError, OSError, ValueError) as exc:
                results[(template['id'], device_id)] = {'error': str(exc)}
    return results
