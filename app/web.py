"""Anthias Hub: IT owns devices; Marketing owns playlists."""
import errno
import json
import io
import os
import re
import secrets
import threading

import requests
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, session, stream_with_context, url_for)
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .upload_disk import DiskRequest, HubStorageFull, validate_temp_directory
from .version import UI_REVISION, read_build_sha

from .auth import authenticate, current_user, csrf_token, login_required, require_csrf
from .anthias import ASSET_ID, Anthias, PlayerError, validate_duration, validate_website_url
from .bulk_media import BatchError, execute_batch
from .devices import load, save, get, validate_device
from .library import Library, LibraryError
from .storage import MAX_MEDIA_BYTES, MAX_REQUEST_BYTES, upload_capacity
from .schedules import (
    ScheduleError, profiles_for, add_profile, edit_profile, remove_profile,
    describe_asset, apply_to_assets, default_for, set_default, assignments_for,
    bind_asset, choice_for, describe_linked_asset, linked_native_key, native_key,
    weekday_warning, valid_rule, native_fields,
)

_audit_lock = threading.Lock()
_apply_lock = threading.Lock()
MEDIA = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.mp4':'video/mp4'}


def create_app(config=None):
    validate_temp_directory()
    app = Flask(__name__)
    app.request_class = DiskRequest
    app.config.update(
        SECRET_KEY=os.environ.get('APP_SECRET_KEY', ''),
        USERS_FILE=os.environ.get('USERS_FILE', '/config/users.json'),
        DEVICES_FILE=os.environ.get('DEVICES_FILE', '/data/devices.json'),
        AUDIT_FILE=os.environ.get('AUDIT_FILE', '/data/audit.jsonl'),
        LIBRARY_DIR=os.environ.get('LIBRARY_DIR', '/data/library'),
        SCHEDULES_FILE=os.environ.get('SCHEDULES_FILE', '/data/schedules.json'),
        MEDIA_SOURCES_FILE=os.environ.get('MEDIA_SOURCES_FILE', '/data/media-sources.json'),
        MEDIA_MOUNT_STATUS_FILE=os.environ.get('MEDIA_MOUNT_STATUS_FILE', '/sources/.mount-status.json'),
        UI_REVISION=UI_REVISION,
        HUB_BUILD_SHA=read_build_sha(),
        # Explicit opt-in for isolated fresh-device testing. Never copy into production.
        HUB_DEVELOPMENT_MODE=os.environ.get('HUB_DEVELOPMENT_MODE', '0') == '1',
        HUB_WORKFLOW_V2=os.environ.get('HUB_WORKFLOW_V2', '0') == '1',
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1') == '1',
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,  # template backups can contain large media
    )
    if config:
        app.config.update(config)
    # Trust forwarded scheme/client IP only when a single trusted proxy is the sole entry point.
    proxy_count = os.environ.get('TRUSTED_PROXY_COUNT', '0')
    if proxy_count not in ('0', '1'):
        raise RuntimeError('TRUSTED_PROXY_COUNT must be 0 or 1')
    if proxy_count == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1,
                                x_host=0, x_port=0, x_prefix=0)
    if len(app.config['SECRET_KEY']) < 32 or 'REPLACE' in app.config['SECRET_KEY'].upper() or 'CHANGE_ME' in app.config['SECRET_KEY'].upper():
        raise RuntimeError('APP_SECRET_KEY must contain at least 32 random characters')

    @app.before_request
    def protect_post():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            try:
                require_csrf()
            except BadRequest:
                if request.endpoint != 'login':
                    raise
                # Keep login protected: a missing/mismatched cookie must never
                # turn into a CSRF bypass. Render a fresh, actionable form.
                # Log only the failure category, never credentials or tokens.
                reason = 'missing_session_token' if not session.get('csrf') else 'token_mismatch'
                app.logger.warning(
                    'Login CSRF rejected: %s; https=%s; secure_cookie=%s',
                    reason, request.is_secure, app.config['SESSION_COOKIE_SECURE'],
                )
                return render_template('login.html', login_csrf_error=True), 400

    @app.after_request
    def headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.context_processor
    def context():
        return {'csrf': csrf_token, 'logged_user': current_user(),
                'ui_revision': app.config['UI_REVISION'],
                'hub_build_sha': app.config['HUB_BUILD_SHA'],
                'development_mode': app.config['HUB_DEVELOPMENT_MODE'],
                'workflow_v2': app.config['HUB_WORKFLOW_V2'],
                'dev_smb_ui': app.config['HUB_WORKFLOW_V2'] and
                              os.environ.get('DEV_SMB_UI', '0') == '1'}

    def audit(action, device_id='', asset_id=''):
        Path(app.config['AUDIT_FILE']).parent.mkdir(parents=True, exist_ok=True)
        record = {'at': datetime.now(timezone.utc).isoformat(), 'user': session.get('user'),
                  'action': action, 'device': device_id, 'asset': asset_id}
        with _audit_lock, open(app.config['AUDIT_FILE'], 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')

    def player_or_404(device_id):
        device = get(app.config['DEVICES_FILE'], device_id)
        if device is None:
            abort(404)
        return device, Anthias(device)

    def library():
        return Library(app.config['LIBRARY_DIR'])

    def managed_playlists_for_device(device_id, templates=None):
        """Persisted folder-template assignment is the editing source of truth.

        A one-off 'apply template' is a copy, not a lasting assignment.
        Do not infer management from asset names or the publisher toggle.
        """
        collections = templates if templates is not None else library().list()
        return [item for item in collections
                if (app.config['HUB_WORKFLOW_V2'] or item.get('folder_source'))
                and device_id in item.get('auto_devices', [])]

    @app.before_request
    def protect_managed_player_content():
        """Guard real player writes, including stale forms and library-origin POSTs.

        The background folder publisher calls the Anthias API independently,
        so these UI endpoint checks cannot disrupt an approved sync.
        """
        # Keep role authentication, CSRF, ID/path validation and explicit
        # confirmations. In a separate test installation, however, a folder
        # assignment must not hide/forbid all experiment actions on the Pi.
        if app.config['HUB_DEVELOPMENT_MODE'] and not app.config['HUB_WORKFLOW_V2']:
            return
        user = current_user()
        if request.method != 'POST' or not user or user['role'] == 'viewer':
            return
        if request.endpoint == 'import_network_folder_once' and user['role'] == 'marketing':
            return  # Existing IT-only role check still returns HTTP 403.
        device_routes = {
            'player_bulk_media', 'import_network_folder_once',
            'add_library_item_from_player', 'append_library_from_player',
            'apply_library', 'add_url', 'upload',
            'edit_asset', 'move_asset', 'reorder_assets',
            'toggle_asset', 'bulk_delete_assets', 'delete_asset',
            'asset_schedule', 'device_schedule_apply', 'device_schedule_default',
            'device_schedule_add', 'device_schedule_delete',
        }
        if app.config['HUB_WORKFLOW_V2']:
            device_routes.add('attach_folder_playlist_to_device')
        library_routes = {
            'apply_library_from_template', 'append_library_from_template',
            'add_library_item_from_template',
        }
        if request.endpoint == 'schedule_library_edit':
            device_id = request.form.get('sync_device', '')
            if device_id and managed_playlists_for_device(device_id):
                abort(409, description='Zugeordnete Ordner-Playlist: Zeitpläne einzelner '
                      'Pi-Inhalte nicht direkt überschreiben.')
            return
        if request.endpoint == 'device_schedule_edit':
            # In the v2 single-owner model, legacy forms may not opt out of
            # the protection by omitting their old sync_assigned flag.
            if request.form.get('sync_assigned') != 'yes' and not app.config['HUB_WORKFLOW_V2']:
                return
            device_id = (request.view_args or {}).get('device_id', '')
            if device_id and managed_playlists_for_device(device_id):
                abort(409, description='Zugeordnete Ordner-Playlist: Zeitpläne einzelner '
                      'Pi-Inhalte nicht direkt überschreiben.')
            return
        if request.endpoint not in device_routes | library_routes:
            return
        if request.endpoint in library_routes:
            device_id = request.form.get('device', '')
        else:
            device_id = (request.view_args or {}).get('device_id', '')
        if device_id and managed_playlists_for_device(device_id):
            abort(409, description='Bildschirm ist einer Ordner-Playlist zugeordnet. '
                  'Inhalte ausschließlich unter Playlists oder im Netzwerkordner '
                  'verwalten; keine direkte Änderung am Pi.')

    def read_player_storage(api):
        """Return (API-based upload capacity, failure reason).

        Do not leak the upstream device URL or response body to the UI.
        """
        try:
            info = api.info()
        except (PlayerError, AttributeError) as exc:
            reason = str(exc)
            if isinstance(exc, AttributeError):
                reason = 'Anthias-Version meldet keine Info-API'
            if 'HTTP ' in reason:
                reason = 'Anthias-Info-API: ' + reason
            else:
                reason = 'Info-API nicht erreichbar oder Zeitüberschreitung'
            app.logger.warning('Anthias storage lookup failed: %s', reason)
            return None, reason
        disk = upload_capacity(info)
        if disk is None:
            app.logger.warning('Anthias free_space missing or unsupported')
            return None, 'Anthias meldet keinen auswertbaren freien Speicher – Pi prüfen'
        return disk, None

    def chosen_schedule(device_id):
        return choice_for(
            app.config['SCHEDULES_FILE'], device_id,
            request.form.get('schedule_choice', 'default'),
            request.form.getlist('schedule_days'),
            request.form.get('schedule_from'),
            request.form.get('schedule_to'),
        )

    def create_scheduled(api, device_id, name, uri, duration, **kwargs):
        """Resolve before writing. Persist an explicit link after confirmed Pi creation."""
        rule, profile_id = chosen_schedule(device_id)
        if rule is not None:
            result = api.create(name, uri, duration, schedule=rule, **kwargs)
        else:
            result = api.create(name, uri, duration, **kwargs)
        if profile_id and isinstance(result, dict) and result.get('asset_id'):
            try:
                bind_asset(app.config['SCHEDULES_FILE'], device_id,
                           result['asset_id'], profile_id, native_fields(rule))
            except ScheduleError as exc:
                raise ScheduleError('Inhalt auf dem Pi erstellt, aber Zuordnung im Hub nicht speicherbar: '
                                    + str(exc) + '. Nicht blind erneut übertragen.') from exc
        return result

    def schedule_options(device_id):
        try:
            return profiles_for(app.config['SCHEDULES_FILE'], device_id), default_for(
                app.config['SCHEDULES_FILE'], device_id)
        except ScheduleError:
            raise  # Never silently fall back to unscheduled if the store is corrupted.

    def requested_storage_override():
        """A conscious per-request acknowledgement, never a persistent bypass."""
        return request.form.get('ignore_storage_check') == 'manual-confirmed'


    @app.get('/media-sources/status')
    @login_required('it')
    def media_sources_status():
        """Status-only refresh. Never mounts SMB or handles credentials."""
        from .source_progress import describe_sources
        from .media_sources import SourceError
        try:
            return jsonify(ok=True, sources=describe_sources(
                app.config['MEDIA_SOURCES_FILE'],
                app.config['MEDIA_MOUNT_STATUS_FILE'], library().list()))
        except (SourceError, OSError, ValueError) as exc:
            return jsonify(ok=False, message=str(exc)), 503

    @app.get('/media-sources')
    @login_required('it')
    def media_sources_page():
        from .folder_sync import available_sources, default_library_folders
        from .media_sources import (
            SourceError, load_sources, mount_statuses, observed_mount_source, retired_aliases,
        )
        try:
            registered = load_sources(app.config['MEDIA_SOURCES_FILE'])
            retired = retired_aliases(app.config['MEDIA_SOURCES_FILE'])
            states = mount_statuses(app.config['MEDIA_MOUNT_STATUS_FILE'], app.config['MEDIA_SOURCES_FILE'])
            aliases = available_sources()
            templates = library().list()
            for source in registered:
                source['status'] = states.get(source['alias'], 'pending')
                source['dependents'] = [
                    {'id': t['id'], 'name': t['name']}
                    for t in templates
                    if t.get('folder_source') == source['alias']
                    or (source['alias'] == 'default'
                        and str(t.get('folder_source') or '').startswith('default/'))
                ]
            # Child folder options are NOT standalone mount aliases. Only
            # top-level aliases may be passed to mountinfo inspection.
            standalone_aliases = {alias for alias in aliases if '/' not in alias}
            unmanaged = [
                {'alias': alias, 'observed': observed_mount_source(alias),
                 'dependents': [
                     {'id': t['id'], 'name': t['name']} for t in templates
                     if t.get('folder_source') == alias
                 ]}
                for alias in sorted(standalone_aliases - {entry['alias'] for entry in registered})
            ]
            assigned = {t.get('folder_source'): t for t in library().list()
                        if t.get('folder_source')}
            default_folders = [
                {'name': name, 'source': 'default/' + name,
                 'template': assigned.get('default/' + name)}
                for name in default_library_folders()
            ]
            default_source = next((entry for entry in registered if entry['alias'] == 'default'), None)
            mounted_count = sum(s['status'] in ('mounted', 'already-mounted') for s in registered)
            attention_count = len(registered) - mounted_count
            return render_template('media_sources.html', sources=registered,
                                   unmanaged=unmanaged, default_folders=default_folders,
                                   default_source=default_source, retired=retired,
                                   mounted_count=mounted_count, attention_count=attention_count)
        except SourceError as exc:
            flash(str(exc), 'error')
            return render_template('media_sources.html', sources=[], unmanaged=[],
                                   default_folders=[], default_source=None, retired=[],
                                   mounted_count=0, attention_count=0)

    @app.post('/media-sources/sync-now')
    @login_required('it')
    def media_sources_sync_now():
        """Queue a DEV-only rescan. The isolated worker performs the network IO."""
        from .smb_ui import enabled, _get_credentials, request_sync, SMBSetupError
        if not enabled() or not app.config['HUB_WORKFLOW_V2']:
            abort(404)
        try:
            if not _get_credentials():
                raise SMBSetupError('Bitte zuerst über „Verbinden & prüfen“ anmelden')
            request_sync()
            audit('dev-smb.sync-requested')
            flash('SMB-Abgleich angefordert. Fortschritt erscheint im Statusbereich.', 'success')
        except (SMBSetupError, OSError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('media_sources_page'))

    @app.post('/media-sources')
    @login_required('it')
    def media_sources_save():
        from .media_sources import SourceError, save_source
        try:
            alias = request.form.get('alias', '')
            unc = request.form.get('unc', '')
            if app.config['HUB_WORKFLOW_V2'] and os.environ.get('DEV_SMB_UI', '0') == '1':
                # Test BEFORE persistence. SMB secrets never appear in the
                # source registry, URL, audit or status endpoint.
                if alias != 'default':
                    raise SourceError('Im vereinfachten DEV-Workflow gibt es eine Stammquelle')
                from .smb_ui import (
                    SMBSetupError, test_connection, store_credentials,
                    write_status, request_sync,
                )
                record, folders = test_connection(
                    unc, request.form.get('username', ''),
                    request.form.get('password', ''),
                    request.form.get('domain', ''))
                result = save_source(alias, record['unc'],
                                     path=app.config['MEDIA_SOURCES_FILE'])
                store_credentials(record)
                write_status('tested', record['unc'], record['revision'],
                             detail='Anmeldung und Ordnerliste erfolgreich geprüft',
                             folders=len(folders))
                request_sync()
                audit('dev-smb.connected', asset_id='default')
                flash(f'SMB verbunden: {len(folders)} Unterordner erkannt. '
                      'Der DEV-Importer übernimmt jetzt die Medien.', 'success')
                return redirect(url_for('media_sources_page'))
            result = save_source(alias, unc, path=app.config['MEDIA_SOURCES_FILE'])
            audit('media-source.' + result, asset_id=alias.strip().lower())
            flash(('SMB-Pfad gespeichert. Die Anzeige „Verbindungsstatus“ zeigt, '
                   'ob ein Host-Mountdienst tatsächlich läuft. Speichern allein '
                   'startet noch keinen SMB-Mount.' if app.config['HUB_WORKFLOW_V2']
                   else 'SMB-Quelle gespeichert. Der Root-Mountdienst prüft die Freigabe '
                        'und bindet neue Ordner automatisch ein; bei einem geänderten '
                        'bereits eingebundenen Pfad ist ein kontrollierter Host-Wechsel nötig.'),
                  'success')
        except (SourceError, OSError, ValueError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('media_sources_page'))

    @app.post('/media-sources/remove')
    @login_required('it')
    def media_sources_remove():
        """Unregister only an unused alias; host mount and Pi files stay intact."""
        from .media_sources import (
            SourceError, validate_alias, remove_source, retire_unmanaged_source, load_sources,
        )
        from .folder_sync import available_sources
        from .library import _lock as library_lock
        try:
            alias = validate_alias(request.form.get('alias', ''))
            if request.form.get('confirm') != alias or request.form.get('ack') != 'yes':
                raise SourceError('Entfernen der Quelle ausdrücklich bestätigen')
            # One critical section with set_folder_source: never retire a source
            # between checking playlist references and accepting a new binding.
            with library_lock:
                dependent = [
                    t['name'] for t in library().list()
                    if t.get('folder_source') == alias
                    or (alias == 'default'
                        and str(t.get('folder_source') or '').startswith('default/'))
                ]
                if dependent:
                    raise SourceError(
                        'Quelle wird noch von ' + str(len(dependent)) +
                        ' Playlist(s) genutzt: ' + ', '.join(dependent[:3]) +
                        '. Zuerst die Zuordnung in den Playlists lösen.'
                    )
                registered = {item['alias'] for item in load_sources(app.config['MEDIA_SOURCES_FILE'])}
                if alias in registered:
                    remove_source(alias, path=app.config['MEDIA_SOURCES_FILE'])
                    if (alias == 'default' and app.config['HUB_WORKFLOW_V2']
                            and os.environ.get('DEV_SMB_UI', '0') == '1'):
                        # Never leave a password behind when the browser-only
                        # source is intentionally unregistered. The importer
                        # will fail closed on the missing registry/credentials.
                        from .smb_ui import credentials_file
                        credentials_file().unlink(missing_ok=True)
                elif alias in {a for a in available_sources() if '/' not in a}:
                    # Only a genuinely visible, non-registered legacy directory
                    # may be hidden. Never accept arbitrary tombstone requests.
                    retire_unmanaged_source(alias, path=app.config['MEDIA_SOURCES_FILE'])
                else:
                    raise SourceError('Keine registrierte oder bekannte alte Quelle mit diesem Alias')
            audit('media-source.retired', asset_id=alias)
            flash(('Quelle „' + alias + '“ im DEV-Hub ausgetragen. '
                   'Gespeicherte SMB-Zugangsdaten entfernt. Kopierte Medien bleiben erhalten.'
                   if app.config['HUB_WORKFLOW_V2'] and os.environ.get('DEV_SMB_UI') == '1'
                      and alias == 'default'
                   else 'Quelle „' + alias + '“ im Hub ausgetragen. Kein SMB-Mount wurde '
                        'ausgehängt und keine Dateien wurden gelöscht. Den alten Host-Mount '
                        'nach Prüfung separat kontrolliert entfernen.'), 'success')
        except (SourceError, LibraryError, OSError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('media_sources_page'))

    @app.post('/media-sources/folders/use')
    @login_required('it')
    def media_sources_use_folder():
        """Make one real child of the default SMB root its own Hub playlist."""
        from .folder_sync import default_library_folders
        name = request.form.get('folder', '')
        if name not in default_library_folders():
            flash('Unterordner fehlt oder ist nicht freigegeben.', 'error')
            return redirect(url_for('media_sources_page'))
        selected = 'default/' + name
        store = library()
        for template in store.list():
            if template.get('folder_source') == selected:
                return redirect(url_for('library_detail', template_id=template['id']))
        try:
            template = store.create(name[:100])
            store.set_folder_source(template['id'], selected)
            audit('library.default-folder-created', asset_id=template['id'])
            flash('Playlist für diesen Netzwerkordner angelegt. Jetzt die Ziel-Pis wählen.', 'success')
            return redirect(url_for('library_detail', template_id=template['id']))
        except LibraryError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('media_sources_page'))

    @app.get('/control')
    @login_required('marketing')
    def control_center():
        """Single DEV-only workspace for changing Hub settings.

        The device, playlist, source and schedule APIs remain the authoritative
        POST handlers. Switching tabs never writes to a Pi or SMB share.
        """
        if not app.config['HUB_WORKFLOW_V2']:
            abort(404)
        tab = request.args.get('tab', 'overview')
        if tab not in ('overview', 'screens', 'playlists', 'sources', 'schedules'):
            abort(404)
        role = current_user()['role']
        devices = load(app.config['DEVICES_FILE'])
        templates = library().list()
        profiles = []
        sources = []
        folder_sources = []
        try:
            if tab in ('overview', 'schedules'):
                profiles = profiles_for(app.config['SCHEDULES_FILE'])
            if role in ('it', 'owner') and tab in ('overview', 'sources', 'playlists'):
                from .folder_sync import available_sources
                folder_sources = available_sources()
                from .media_sources import load_sources
                sources = load_sources(app.config['MEDIA_SOURCES_FILE'])
        except (ScheduleError, LibraryError, OSError, ValueError) as exc:
            flash(str(exc), 'error')
        source_dependents = {}
        for source in sources:
            source['dependents'] = [
                {'id': row['id'], 'name': row['name']} for row in templates
                if row.get('folder_source') == source['alias'] or
                (source['alias'] == 'default' and
                 str(row.get('folder_source') or '').startswith('default/'))
            ]
        return render_template(
            'control_center.html', control_tab=tab,
            templates=templates, devices=devices, profiles=profiles,
            sources=sources, folder_sources=folder_sources,
            default_source=next((row for row in sources if row['alias'] == 'default'), None),
            can_manage_sources=role in ('owner', 'it'),
        )

    @app.after_request
    def stay_in_control_center(response):
        """Form submissions from DEV control return to the same tab.

        This changes the destination of a successful redirect, never the
        permission checks, CSRF validation or the underlying POST operation.
        """
        allowed = {
            'library_create': 'playlists', 'library_import': 'playlists',
            'library_delete_template': 'playlists', 'library_auto_devices': 'playlists',
            'library_folder_source': 'playlists', 'library_add_url': 'playlists',
            'library_add_media': 'playlists', 'library_bulk_media': 'playlists',
            'add_device': 'screens', 'edit_device': 'screens',
            'remove_device': 'screens', 'control_device': 'screens',
            'media_sources_save': 'sources', 'media_sources_remove': 'sources',
            'media_sources_sync_now': 'sources',
            'schedule_library_add': 'schedules',
            'schedule_library_edit': 'schedules',
            'schedule_library_delete': 'schedules',
        }
        tab = allowed.get(request.endpoint)
        if (app.config['HUB_WORKFLOW_V2'] and tab and
                request.method == 'POST' and response.status_code in (302, 303)
                and request.form.get('control_tab') == tab):
            return redirect(url_for('control_center', tab=tab))
        return response

    @app.get('/library')
    @login_required()
    def library_index():
        from .folder_sync import available_sources
        templates = library().list()
        from .folder_status import read_status
        return render_template('library_index_v2.html' if app.config['HUB_WORKFLOW_V2'] else 'library.html',
                               templates=templates,
                               folder_sync_by_template={
                                   t['id']: read_status(t['id']) for t in templates if t.get('folder_source')},
                               device_names={d['id']: d['name'] for d in load(app.config['DEVICES_FILE'])},
                               folder_sources=available_sources())

    @app.post('/library')
    @login_required('marketing')
    def library_create():
        try:
            source = request.form.get('folder_source', '').strip()
            if source:
                if current_user()['role'] not in ('it', 'owner'):
                    abort(403)
                from .folder_sync import source_directory
                source_directory(source)  # Validate before the new template is created.
            item = library().create(request.form.get('name', ''))
            if source:
                library().set_folder_source(item['id'], source)
            audit('library.create', asset_id=item['id'])
            return redirect(url_for('library_detail', template_id=item['id']))
        except LibraryError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('library_index'))

    @app.post('/library/import')
    @login_required('marketing')
    def library_import():
        try:
            file = request.files.get('archive')
            if not file or not file.filename or not file.filename.lower().endswith('.zip'):
                raise LibraryError('Hier nur ein zuvor aus Anthias Hub exportiertes Vorlagen-Backup (.zip) auswählen. Für Bilder/Videos bitte „Medien-ZIP importieren“ nutzen.')
            item = library().import_zip(file.stream)
            audit('library.import', asset_id=item['id'])
            return redirect(url_for('library_detail', template_id=item['id']))
        except LibraryError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('library_index'))

    @app.post('/library/<template_id>/delete')
    @login_required('marketing')
    def library_delete_template(template_id):
        """Delete only Hub-local template media, never player playlist assets."""
        if request.form.get('confirm') != template_id or request.form.get('ack') != 'yes':
            abort(400, 'Löschung ausdrücklich bestätigen')
        try:
            chosen = library().get(template_id)
            if chosen.get('auto_devices'):
                raise LibraryError('Playlist ist Bildschirmen zugeordnet. Erst Zielbildschirme '
                                   'in „Quelle & IT“ entfernen, danach Vorlage löschen.')
            deleted = library().delete_template(template_id, request.form.get('name_confirmation', ''))
            audit('library.delete-template', asset_id=template_id)
            flash(f'Vorlage „{deleted["name"]}“ mit {len(deleted["items"])} Inhalten gelöscht. '
                  'Bereits übertragene Bildschirm-Inhalte bleiben erhalten.', 'success')
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_index'))

    @app.get('/library/<template_id>')
    @login_required()
    def library_detail(template_id):
        try:
            item = library().get(template_id)
        except LibraryError:
            abort(404)
        from .folder_sync import available_sources
        from .folder_status import read_status
        return render_template(
            'library_detail_v2.html' if app.config['HUB_WORKFLOW_V2'] else 'library_detail.html',
            template=item,
            folder_sources=available_sources(),
            folder_sync_status=read_status(template_id),
            devices=load(app.config['DEVICES_FILE']),
            schedules_by_device={
                d['id']: {'profiles': profiles_for(app.config['SCHEDULES_FILE'], d['id']),
                          'default': default_for(app.config['SCHEDULES_FILE'], d['id'])}
                for d in load(app.config['DEVICES_FILE'])
            })

    @app.post('/library/<template_id>/folder-source')
    @login_required('it')
    def library_folder_source(template_id):
        """IT only: bind to a pre-mounted alias, never arbitrary paths."""
        try:
            alias = request.form.get('folder_source', '').strip()
            library().set_folder_source(template_id, alias)
            audit('library.folder-source', asset_id=template_id)
            flash('Ordnerquelle gespeichert. Automatischer Import bei aktivem Importdienst.'
                  if alias else 'Ordnerquelle entfernt. Medien bleiben erhalten.', 'success')
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    @app.post('/library/<template_id>/auto-devices')
    @login_required('it')
    def library_auto_devices(template_id):
        """Explicit IT opt-in for auto-publishing folder-managed media."""
        try:
            selected = request.form.getlist('devices')
            library().set_auto_devices(
                template_id, selected, load(app.config['DEVICES_FILE']),
                replace_existing=app.config['HUB_DEVELOPMENT_MODE'],
                allow_manual=app.config['HUB_WORKFLOW_V2'])
            audit('library.auto-devices', asset_id=template_id)
            flash(('Testmodus: Zielzuordnung gespeichert. Bereits anders zugeordnete Geräte '
                   'wurden automatisch hierher übernommen. ' if app.config['HUB_DEVELOPMENT_MODE']
                   else 'Automatische Bildschirmzuordnung gespeichert. ')
                  + 'Der Pi-Publisher bleibt bis zur ausdrücklichen Freigabe ausgeschaltet.', 'success')
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    @app.get('/library/<template_id>/items/<item_id>/preview')
    @login_required()
    def library_item_preview(template_id, item_id):
        """Read-only preview of one allowed local library file; never an arbitrary path."""
        try:
            store = library()
            collection = store.get(template_id)
            item = next((entry for entry in collection['items']
                         if entry['id'] == item_id and entry['kind'] == 'media'), None)
            if item is None:
                abort(404)
            media_path = store.verified_media_path(template_id, item)
            mime = MEDIA.get(media_path.suffix.lower())
            if not mime:
                abort(404)
        except LibraryError:
            abort(404)
        return send_file(media_path, mimetype=mime, as_attachment=False, conditional=True)

    @app.get('/library/<template_id>/export')
    @login_required()
    def library_export(template_id):
        try:
            archive = library().export_file(template_id)
        except LibraryError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('library_index'))
        return send_file(archive, mimetype='application/zip', as_attachment=True,
                         download_name='anthias-playlist-' + template_id + '.zip')

    @app.post('/library/<template_id>/url')
    @login_required('marketing')
    def library_add_url(template_id):
        try:
            library().add_url(template_id, request.form.get('name'), request.form.get('url'), request.form.get('duration'))
            audit('library.add-url', asset_id=template_id)
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    @app.post('/library/<template_id>/media')
    @login_required('marketing')
    def library_add_media(template_id):
        destination = url_for('library_detail', template_id=template_id)
        try:
            file = request.files.get('media')
            if file is None or not file.filename:
                raise LibraryError('Bitte eine Datei auswählen')
            library().add_media(template_id, request.form.get('name') or file.filename,
                                file.stream, file.filename, request.form.get('duration'))
            audit('library.add-media', asset_id=template_id)
            if request.accept_mimetypes.best == 'application/json':
                return jsonify(ok=True, message='Medium in der Bibliothek gespeichert.', redirect=destination)
            flash('Medium in der Bibliothek gespeichert.', 'success')
        except LibraryError as exc:
            if request.accept_mimetypes.best == 'application/json':
                return jsonify(ok=False, error=str(exc)), 422
            flash(str(exc), 'error')
        return redirect(destination)


    def finish_bulk(report, destination_url):
        """JSON result for progress UI; concise server-rendered fallback."""
        report['redirect'] = destination_url
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(report)
        category = 'success' if report['ok'] else 'error'
        errors = [f"{row['name']}: {row['message']}"
                  for row in report['results'] if row['status'] == 'failed']
        note = (' Bitte Ziel-Playlist prüfen, vor erneutem Hochladen; '
                'Teilerfolge werden nicht automatisch zurückgerollt.'
                if not report['ok'] else '')
        flash(report['message'] + (' ' + '; '.join(errors[:3]) if errors else '') + note, category)
        return redirect(destination_url)

    def reject_bulk(exc, destination_url):
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, error=str(exc), results=[], imported=0, failed=0), 422
        flash(str(exc), 'error')
        return redirect(destination_url)

    @app.post('/library/media-import')
    @login_required('marketing')
    def library_media_import_from_index():
        """Accept a plain media ZIP directly from the library landing page.

        The destination template is explicit; never create a new template
        implicitly or route uploaded files to the special backup importer.
        """
        template_id = request.form.get('template_id', '')
        try:
            library().get(template_id)
        except LibraryError as exc:
            return reject_bulk(exc, url_for('library_index'))
        return library_bulk_media(template_id)

    @app.post('/library/<template_id>/bulk-media')
    @login_required('marketing')
    def library_bulk_media(template_id):
        destination_url = url_for('library_detail', template_id=template_id)
        try:
            store = library()
            store.get(template_id)  # Reject unknown target before reading/processing files.
            def add_one(title, filename, ext, stream, duration):
                store.add_media(template_id, title, stream, filename, duration)
                audit('library.bulk-add-media', asset_id=template_id)
            report = execute_batch(request.files.getlist('media'),
                                   duration=request.form.get('duration'),
                                   destination='library', on_media=add_one)
            return finish_bulk(report, destination_url)
        except (BatchError, LibraryError) as exc:
            return reject_bulk(exc, destination_url)

    @app.post('/devices/<device_id>/bulk-media')
    @login_required('marketing')
    def player_bulk_media(device_id):
        destination_url = url_for('playlist', device_id=device_id)
        _, api = player_or_404(device_id)
        try:
            chosen_schedule(device_id)  # Validate before first bulk media transfer.
            # No automatic overwrite/reorder: every file is appended individually.
            # One user-visible failure might still have reached the Pi.
            api.assets()  # Make sure target is reachable before the first transfer.
            def add_one(title, filename, ext, stream, duration):
                if requested_storage_override():
                    uploaded = api.upload(stream, filename, MEDIA[ext],
                                          allow_unknown_space=True)
                else:
                    uploaded = api.upload(stream, filename, MEDIA[ext])
                create_scheduled(api, device_id, title, uploaded['uri'], duration,
                                 mimetype=MEDIA[ext], ext=uploaded.get('ext'))
                audit('asset.bulk-upload', device_id)
            if requested_storage_override():
                audit('storage.override-request', device_id)
            report = execute_batch(request.files.getlist('media'),
                                   duration=request.form.get('duration'),
                                   destination='player', on_media=add_one)
            if report['failed']:
                report['message'] += ' Player-Playlist prüfen; kein automatischer Rollback oder Retry.'
            return finish_bulk(report, destination_url)
        except (BatchError, PlayerError, ScheduleError) as exc:
            return reject_bulk(exc, destination_url)

    @app.post('/library/<template_id>/items/<item_id>/duration')
    @login_required('marketing')
    def library_item_duration(template_id, item_id):
        """Simple Marketing control, independent of network folder writes."""
        try:
            item = library().update_item_duration(
                template_id, item_id, request.form.get('duration'))
            audit('library.duration', asset_id=item_id)
            flash(f'Anzeigedauer für „{item["name"]}“ gespeichert. '
                  'Auf zugeordneten Test-Pis übernimmt der automatische Publisher '
                  'die Änderung beim nächsten Abgleich, sofern aktiviert.', 'success')
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    @app.post('/library/<template_id>/move/<item_id>')
    @login_required('marketing')
    def library_move_item(template_id, item_id):
        try:
            library().move(template_id, item_id, request.form.get('direction'))
            audit('library.move-item', asset_id=template_id)
        except LibraryError as exc:
            flash(str(exc), 'error')
        # Return directly to the ordered items, not to the page heading.
        # This is a visible, navigation-only v2 improvement; data handling,
        # CSRF and legacy behavior are unchanged.
        return redirect(url_for('library_detail', template_id=template_id,
                                _anchor='inhalte' if app.config['HUB_WORKFLOW_V2'] else None))

    @app.post('/library/<template_id>/remove/<item_id>')
    @login_required('marketing')
    def library_remove_item(template_id, item_id):
        if request.form.get('confirm') != item_id or request.form.get('ack') != 'yes':
            abort(400)
        try:
            library().remove(template_id, item_id)
            audit('library.remove-item', asset_id=template_id)
        except LibraryError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    @app.post('/devices/<device_id>/apply-library')
    @login_required('marketing')
    def apply_library(device_id):
        if request.form.get('confirm') != 'yes':
            abort(400)
        device, api = player_or_404(device_id)
        try:
            chosen_schedule(device_id)
            template = library().get(request.form.get('template_id', ''))
            if not template['items']:
                raise LibraryError('Leere Vorlage wird nicht übertragen')
            # Preflight every local file before any player write. Serialize the empty-list
            # check and transfer against parallel requests in this single-worker process.
            media_paths = {item['id']: library().verified_media_path(template['id'], item)
                           for item in template['items'] if item['kind'] == 'media'}
            with _apply_lock:
                if api.assets():
                    raise LibraryError('Player-Playlist ist nicht leer. Nichts übertragen; vorhandene Inhalte bleiben unverändert.')
                for item in template['items']:
                    if item['kind'] == 'url':
                        create_scheduled(api, device_id, item['name'], item['url'], item['duration'])
                    else:
                        path = media_paths[item['id']]
                        ext = path.suffix.lower()
                        with path.open('rb') as stream:
                            uploaded = api.upload(stream, path.name, MEDIA[ext])
                        create_scheduled(api, device_id, item['name'], uploaded['uri'], item['duration'],
                                         mimetype=MEDIA[ext], ext=uploaded.get('ext'))
            audit('library.apply', device_id, template['id'])
            flash('Vorlage übertragen. Playlist und Ausgabe am TV prüfen.', 'success')
        except (LibraryError, PlayerError, ScheduleError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Playlist am Player prüfen (Teilübertragung möglich).', 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/library/<template_id>/apply')
    @login_required('marketing')
    def apply_library_from_template(template_id):
        if request.form.get('template_id') != template_id:
            abort(400)
        return apply_library(request.form.get('device', ''))

    def append_library_template(device_id, template_id):
        """Append an entire saved template in order, without clearing the player.

        Preflight every stored media item before any player operation. A stopped
        transfer is not atomic; do not retry automatically after partial writes.
        """
        _, api = player_or_404(device_id)
        chosen_schedule(device_id)
        store = library()
        collection = store.get(template_id)
        items = collection.get('items', [])
        if not items:
            raise LibraryError('Die Vorlage ist leer. Bitte zuerst Inhalte hinzufügen.')
        if len(items) > 100:
            raise LibraryError('Vorlage enthält mehr als 100 Inhalte.')
        # Fail on missing/corrupt files before uploading *any* of the template.
        files = {}
        for item in items:
            if item.get('kind') == 'media':
                files[item['id']] = store.verified_media_path(template_id, item)
            elif item.get('kind') != 'url':
                raise LibraryError('Unbekannter Inhaltstyp in Vorlage.')

        added, skipped = 0, 0
        with _apply_lock:
            existing = api.assets()  # Preflight target reachability under lock.
            known_urls = {(asset.get('name'), asset.get('uri'))
                          for asset in existing}
            for item in items:
                try:
                    if item['kind'] == 'url':
                        # Do not duplicate identical URLs already on the device
                        # or repeated in the source template.
                        identity = item['name'], item['url']
                        if identity in known_urls:
                            skipped += 1
                            continue
                        create_scheduled(api, device_id, item['name'], item['url'], item['duration'])
                        known_urls.add(identity)
                    else:
                        path = files[item['id']]
                        ext = path.suffix.lower()
                        with path.open('rb') as stream:
                            uploaded = api.upload(stream, path.name, MEDIA[ext])
                        create_scheduled(api, device_id, item['name'], uploaded['uri'], item['duration'],
                                           mimetype=MEDIA[ext], ext=uploaded.get('ext'))
                    added += 1
                    audit('library.append-item', device_id, item['id'])
                except (PlayerError, OSError, ValueError) as exc:
                    # A failed upload/create may already have modified the Pi.
                    raise LibraryError(
                        f'Abbruch nach {added} hinzugefügten und {skipped} übersprungenen '
                        f'Inhalten bei „{item["name"]}“: {exc}. '
                        'Mögliche Teilübertragung! Playlist prüfen und nicht blind erneut starten.'
                    ) from exc
        audit('library.append-template', device_id, template_id)
        return added, skipped

    @app.post('/devices/<device_id>/append-library')
    @login_required('marketing')
    def append_library_from_player(device_id):
        if request.form.get('confirm') != 'append' or request.form.get('ack') != 'yes':
            abort(400)
        try:
            added, skipped = append_library_template(device_id, request.form.get('template_id', ''))
            flash(f'{added} Inhalte hinzugefügt, {skipped} bereits vorhandene Webseiten übersprungen. '
                  'Bestehende Playlist wurde nicht gelöscht. Ausgabe am TV prüfen.', 'success')
        except (LibraryError, PlayerError, ScheduleError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Playlist auf dem Player prüfen.', 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/library/<template_id>/append-to-device')
    @login_required('marketing')
    def append_library_from_template(template_id):
        if request.form.get('confirm') != 'append' or request.form.get('ack') != 'yes':
            abort(400)
        device_id = request.form.get('device', '')
        try:
            added, skipped = append_library_template(device_id, template_id)
            flash(f'{added} Inhalte aus der Vorlage hinzugefügt, {skipped} vorhandene Webseiten übersprungen. '
                  'Der Bildschirm wurde nicht geleert.', 'success')
        except (LibraryError, PlayerError, ScheduleError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Ziel-Playlist prüfen.', 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    def append_library_item(device_id, template_id, item_id):
        """Append exactly one item to a possibly nonempty player playlist.

        Never delete, reorder, overwrite, or transfer a whole template. Verify
        the library file before touching the player. A partial media transfer
        cannot be rolled back safely by this endpoint.
        """
        _, api = player_or_404(device_id)
        chosen_schedule(device_id)
        store = library()
        collection = store.get(template_id)
        item = next((entry for entry in collection['items'] if entry.get('id') == item_id), None)
        if item is None:
            raise LibraryError('Inhalt nicht in dieser Bibliotheksvorlage gefunden')
        if item.get('kind') not in ('url', 'media'):
            raise LibraryError('Unbekannter Inhaltstyp')
        path = store.verified_media_path(template_id, item) if item['kind'] == 'media' else None
        with _apply_lock:
            current = api.assets()  # preflight: confirm target is reachable before any write
            if item['kind'] == 'url':
                if any(asset.get('uri') == item['url'] and asset.get('name') == item['name']
                       for asset in current):
                    raise LibraryError('Diese Webseite ist bereits in der Playlist vorhanden')
                create_scheduled(api, device_id, item['name'], item['url'], item['duration'])
            else:
                ext = path.suffix.lower()
                with path.open('rb') as stream:
                    uploaded = api.upload(stream, path.name, MEDIA[ext])
                create_scheduled(api, device_id, item['name'], uploaded['uri'], item['duration'],
                                   mimetype=MEDIA[ext], ext=uploaded.get('ext'))
        audit('library.add-item', device_id, item_id)

    @app.post('/devices/<device_id>/import-network-folder')
    @login_required('it')
    def import_network_folder_once(device_id):
        """Append approved SMB media once, with optional per-file SSE progress.

        Both the native-form fallback and streaming UI use the same guarded
        preflight and upload iterator. A failed run must never be retried
        automatically: earlier files may already exist on the player.
        """
        from .folder_sync import available_sources, source_directory
        import stat

        if request.form.get('confirm') != 'once' or request.form.get('ack') != 'yes':
            abort(400)
        destination = url_for('playlist', device_id=device_id)
        streamed = request.form.get('progress_stream') == '1'
        alias = request.form.get('folder_source', '')

        def import_events():
            added = 0
            total = 0
            yield {'type': 'preparing', 'done': 0, 'total': 0,
                   'message': 'Netzwerkordner und Dateien werden geprüft …'}
            try:
                if alias not in available_sources():
                    raise LibraryError('Netzwerkordner nicht verfügbar oder nicht freigegeben.')
                folder = source_directory(alias)
                chosen_schedule(device_id)  # Invalid schedules fail before first upload.
                duration = validate_duration(request.form.get('duration', 15))
                candidates = sorted(
                    (p for p in folder.iterdir() if p.suffix.lower() in MEDIA
                     and not p.is_symlink() and p.is_file()),
                    key=lambda p: p.name.casefold())
                total = len(candidates)
                if not candidates:
                    raise LibraryError('Der Ordner enthält keine unterstützten Bilder oder Videos.')
                if total > 20:
                    raise LibraryError('Mehr als 20 Medien im Ordner. Bitte in kleinere freigegebene Unterordner aufteilen; es wurde nichts übertragen.')
                # Validate *every* candidate before making the first Pi-side write.
                signatures = {
                    '.png': lambda h: h.startswith(b'\x89PNG\r\n\x1a\n'),
                    '.jpg': lambda h: h.startswith(b'\xff\xd8'),
                    '.jpeg': lambda h: h.startswith(b'\xff\xd8'),
                    '.webp': lambda h: h.startswith(b'RIFF') and h[8:12] == b'WEBP',
                    '.mp4': lambda h: len(h) >= 12 and h[4:8] == b'ftyp',
                }
                for p in candidates:
                    if p.resolve().parent != folder.resolve():
                        raise LibraryError('Nicht freigegebener Medienpfad erkannt.')
                    fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                    with os.fdopen(fd, 'rb') as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MEDIA_BYTES:
                            raise LibraryError('Mediengröße unzulässig (0 bis 4 GiB): ' + p.name)
                        if not signatures[p.suffix.lower()](stream.read(16)):
                            raise LibraryError('Dateiformat stimmt nicht mit Endung überein: ' + p.name)

                _, api = player_or_404(device_id)
                with _apply_lock:
                    api.assets()  # Check reachability before the first transfer.
                    yield {'type': 'start', 'done': 0, 'total': total,
                           'message': f'0 / {total} Dateien übertragen'}
                    for index, p in enumerate(candidates, 1):
                        yield {'type': 'active', 'done': added, 'total': total,
                               'index': index, 'name': p.name}
                        try:
                            fd = os.open(p, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                            with os.fdopen(fd, 'rb') as stream:
                                info = os.fstat(stream.fileno())
                                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_MEDIA_BYTES:
                                    raise LibraryError('Quelldatei vor Upload verändert: ' + p.name)
                                head = stream.read(16)
                                stream.seek(0)
                                if not signatures[p.suffix.lower()](head):
                                    raise LibraryError('Quelldatei vor Upload verändert: ' + p.name)
                                uploaded = api.upload(stream, p.name, MEDIA[p.suffix.lower()])
                            seconds = 0 if p.suffix.lower() == '.mp4' else duration
                            create_scheduled(api, device_id, p.name[:100], uploaded['uri'], seconds,
                                             mimetype=MEDIA[p.suffix.lower()], ext=uploaded.get('ext'))
                            added += 1
                            audit('folder.manual-append-file', device_id)
                            yield {'type': 'progress', 'done': added, 'total': total,
                                   'index': index, 'name': p.name}
                        except (PlayerError, LibraryError, ScheduleError, OSError) as exc:
                            raise LibraryError(f'Abbruch nach {added} Medien bei „{p.name}“: {exc}. '
                                               'Mögliche Teilübertragung; Playlist prüfen, nicht blind wiederholen.') from exc
                audit('folder.manual-append', device_id)
                yield {'type': 'complete', 'done': added, 'total': total,
                       'message': f'{added} Medien aus „{alias}“ einmalig hinzugefügt. '
                                  'Keine automatische Verbindung eingerichtet. Wiedergabe am TV prüfen.',
                       'redirect': destination}
            except (LibraryError, PlayerError, ScheduleError, OSError, ValueError) as exc:
                yield {'type': 'error', 'done': added, 'total': total,
                       'message': str(exc) + ' Vorhandene Playlist wurde nicht absichtlich verändert oder geleert.',
                       'redirect': destination}

        if streamed:
            def event_stream():
                for event in import_events():
                    yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'

            return Response(stream_with_context(event_stream()),
                            content_type='text/event-stream; charset=utf-8',
                            headers={'X-Accel-Buffering': 'no'})

        # Standard HTML POST remains usable when JavaScript is unavailable.
        result = None
        for result in import_events():
            pass
        flash(result['message'], 'success' if result['type'] == 'complete' else 'error')
        return redirect(destination)

    @app.post('/devices/<device_id>/folder-playlist')
    @login_required('it')
    def attach_folder_playlist_to_device(device_id):
        """One-click IT binding, starting from a screen instead of the library."""
        from .folder_sync import source_directory, available_sources
        device_ids = {d['id'] for d in load(app.config['DEVICES_FILE'])}
        if device_id not in device_ids:
            abort(404)
        alias = request.form.get('folder_source', '')
        if alias not in available_sources():
            flash('Netzwerkordner nicht verfügbar. SMB-Mount im Hub prüfen.', 'error')
            return redirect(url_for('playlist', device_id=device_id))
        try:
            source_directory(alias)  # fail closed on unplugged/out-of-scope sources
            store = library()
            template = next((t for t in store.list()
                             if t.get('folder_source') == alias), None)
            if template is None:
                template = store.create(alias.split('/')[-1][:100])
                store.set_folder_source(template['id'], alias)
            current = list(template.get('auto_devices', []))
            if device_id not in current:
                store.set_auto_devices(template['id'],
                                       current + [device_id],
                                       load(app.config['DEVICES_FILE']))
            audit('library.folder-attach-device', device_id, asset_id=template['id'])
            flash('Netzwerkordner ist dem Bildschirm zugewiesen. Die Medien '
                  'erscheinen erst, wenn der Ordnerimport läuft und der '
                  'automatische Publisher von IT serverseitig freigegeben wird.', 'success')
            return redirect(url_for('library_detail', template_id=template['id']))
        except (LibraryError, OSError) as exc:
            flash(str(exc), 'error')
            return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/add-library-item')
    @login_required('marketing')
    def add_library_item_from_player(device_id):
        if request.form.get('confirm') != 'add':
            abort(400)
        source = request.form.get('source', '')
        if not re.fullmatch(r'[a-f0-9]{32}:[a-f0-9]{32}', source):
            abort(400)
        template_id, item_id = source.split(':', 1)
        try:
            append_library_item(device_id, template_id, item_id)
            flash('Ein Bibliotheksinhalt hinzugefügt. Bestehende Playlist bleibt erhalten; Ausgabe am TV prüfen.', 'success')
        except (LibraryError, PlayerError, ScheduleError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Playlist prüfen (Teilübertragung möglich).', 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/library/<template_id>/items/<item_id>/add-to-device')
    @login_required('marketing')
    def add_library_item_from_template(template_id, item_id):
        if request.form.get('confirm') != 'add':
            abort(400)
        device_id = request.form.get('device', '')
        try:
            append_library_item(device_id, template_id, item_id)
            flash('Ein Inhalt zur ausgewählten Playlist hinzugefügt; bestehende Inhalte bleiben erhalten.', 'success')
        except (LibraryError, PlayerError, ScheduleError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Ziel-Playlist prüfen (Teilübertragung möglich).', 'error')
        return redirect(url_for('library_detail', template_id=template_id))

    def chosen_asset(api, asset_id):
        Anthias.valid_id(asset_id)
        items = api.assets()
        return next((item for item in items if item.get('asset_id') == asset_id), None), items

    @app.get('/healthz')
    def healthz():
        return 'ok\n'

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            name = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            if authenticate(name, password):
                session.clear()
                session['user'] = name
                session['csrf'] = secrets.token_urlsafe(32)
                session.permanent = True
                return redirect(url_for('dashboard'))
            flash('Anmeldung fehlgeschlagen.', 'error')
        return render_template('login.html')

    @app.post('/logout')
    @login_required()
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    @login_required()
    def dashboard():
        # Do not block Hub navigation on serial Pi API calls or slow info.
        devices = load(app.config['DEVICES_FILE'])
        default_mount_state = None
        if current_user()['role'] in ('it', 'owner'):
            # Small, IT-only readiness hint; do not treat an absent/stale host
            # report as a mounted SMB share or block the screen overview.
            from .media_sources import SourceError, load_sources, mount_statuses
            try:
                registry = load_sources(app.config['MEDIA_SOURCES_FILE'])
                if any(row['alias'] == 'default' for row in registry):
                    states = mount_statuses(app.config['MEDIA_MOUNT_STATUS_FILE'],
                                             app.config['MEDIA_SOURCES_FILE'])
                    default_mount_state = states.get('default', 'pending')
                else:
                    default_mount_state = 'unconfigured'
            except SourceError:
                default_mount_state = 'pending'
        templates = library().list()
        managed_by_device = {d['id']: managed_playlists_for_device(d['id'], templates)
                             for d in devices}
        from .folder_status import read_status
        sync_status_by_template = {t['id']: read_status(t['id'])
                                   for t in templates if t.get('folder_source')}
        return render_template('dashboard.html', devices=devices,
                               managed_by_device=managed_by_device,
                               sync_status_by_template=sync_status_by_template,
                               default_mount_state=default_mount_state)

    @app.get('/devices/<device_id>/overview')
    @login_required()
    def device_overview(device_id):
        """Small, authenticated player count; no expensive system-info call."""
        _, api = player_or_404(device_id)
        try:
            items = api.assets()
        except PlayerError:
            return jsonify(ok=False, count=None)
        return jsonify(ok=True, count=len(items))

    @app.post('/devices')
    @login_required('it')
    def add_device():
        try:
            d = validate_device(request.form.get('name', ''), request.form.get('id', ''),
                                request.form.get('url', ''), request.form.get('location', ''))
            devices = load(app.config['DEVICES_FILE'])
            if any(old['id'] == d['id'] for old in devices):
                raise ValueError('Diese Geräte-ID existiert bereits')
            devices.append(d)
            save(app.config['DEVICES_FILE'], devices)
            audit('device.add', d['id'])
            flash('Gerät hinzugefügt.', 'success')
        except (ValueError, OSError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('dashboard'))

    @app.post('/devices/<device_id>/edit')
    @login_required('it')
    def edit_device(device_id):
        items = load(app.config['DEVICES_FILE'])
        if not any(d['id'] == device_id for d in items):
            abort(404)
        try:
            updated = validate_device(request.form.get('name', ''), device_id,
                                      request.form.get('url', ''), request.form.get('location', ''))
            save(app.config['DEVICES_FILE'], [updated if d['id'] == device_id else d for d in items])
            audit('device.edit', device_id)
            flash('Geräteverbindung aktualisiert.', 'success')
        except (ValueError, OSError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('dashboard'))

    @app.post('/devices/<device_id>/control')
    @login_required('it', 'marketing')
    def control_device(device_id):
        """Explicitly confirmed operations on a registered Anthias Pi only.

        Marketing may request a reboot for recovery, never shutdown or HDMI.
        Only fixed API v2 endpoints are used; no arbitrary command or proxy.
        """
        device, api = player_or_404(device_id)
        action = request.form.get('action')
        role = current_user()['role']
        permitted = {'it': {'hdmi-on', 'hdmi-off', 'reboot', 'shutdown'},
                     'owner': {'hdmi-on', 'hdmi-off', 'reboot', 'shutdown'},
                     'marketing': {'reboot'}}
        if action not in permitted[role]:
            abort(403)
        if request.form.get('confirm') != device_id or request.form.get('ack') != 'yes':
            abort(400, 'Geräteaktion ausdrücklich bestätigen')
        if action == 'shutdown' and request.form.get('name_confirmation') != device['name']:
            abort(400, 'Bildschirmname muss für das Herunterfahren exakt übereinstimmen')

        try:
            if action.startswith('hdmi-'):
                result = api.display_power(action.removeprefix('hdmi-'))
                # Anthias returns a message on CEC success, but not a
                # verifiable report that the physical TV switched state.
                if isinstance(result, dict) and 'message' in result:
                    message = str(result['message'])[:220]
                else:
                    message = 'HDMI-CEC-Befehl gesendet.'
                audit('device.' + action, device_id)
                flash(message + ' Anzeige am TV prüfen (HDMI-CEC experimentell).', 'success')
            else:
                # Reboot/shutdown may drop the network connection immediately
                # after accepting the request: no automatic retry.
                api.system_power(action)
                audit('device.' + action, device_id)
                if action == 'reboot':
                    flash('Neustart angefordert. Der Pi kann für einige Minuten nicht erreichbar sein. '
                          'Bitte warten und Status prüfen.', 'success')
                else:
                    flash('Herunterfahren angefordert. Der Pi kann anschließend ausgeschaltet bleiben '
                          'und muss ggf. vor Ort wieder gestartet werden.', 'success')
        except PlayerError as exc:
            flash('Gerätebefehl nicht bestätigt: ' + str(exc) +
                  '. Bei Neustart/Shutdown kann der Pi bereits reagieren. '
                  'Bitte Gerätestatus prüfen, nicht blind erneut senden.', 'error')
        return redirect(url_for('dashboard', _anchor='device-' + device_id))

    @app.post('/devices/<device_id>/remove')
    @login_required('it')
    def remove_device(device_id):
        if request.form.get('confirm') != device_id or request.form.get('ack') != 'yes':
            abort(400, 'Entfernen des Geräts ausdrücklich bestätigen')
        devices = load(app.config['DEVICES_FILE'])
        if not any(d['id'] == device_id for d in devices):
            abort(404)
        save(app.config['DEVICES_FILE'], [d for d in devices if d['id'] != device_id])
        audit('device.remove', device_id)
        flash('Gerät aus Hub entfernt. Pi/Playlist bleiben unverändert.', 'success')
        return redirect(url_for('dashboard'))

    @app.get('/devices/<device_id>')
    @login_required()
    def playlist(device_id):
        device, api = player_or_404(device_id)
        assets, error = [], None
        try:
            assets = api.assets()
        except PlayerError as exc:
            error = str(exc)
        # Fetch slow Anthias system info asynchronously after rendering.
        # Server-side upload preflight still rechecks actual Pi capacity.
        storage = None
        storage_reason = 'Speicher wird geprüft …' if not error else None
        templates = []
        library_unavailable = False
        try:
            templates = library().list()
        except LibraryError:
            library_unavailable = True
            flash('Bibliothek konnte nicht geladen werden. Inhaltsänderungen am Bildschirm '
                  'bleiben vorsorglich gesperrt.', 'error')
        schedule_profiles, schedule_default = schedule_options(device_id)
        bindings = assignments_for(app.config['SCHEDULES_FILE'], device_id)
        for asset in assets:
            asset['schedule_label'] = describe_linked_asset(asset, schedule_profiles, bindings)
            matched = next((p['id'] for p in schedule_profiles
                            if asset['schedule_label'] == p['name']), None)
            asset['schedule_choice'] = (
                matched if matched else
                'always' if asset['schedule_label'] == 'Ohne Zeitplan' else
                'custom' if asset['schedule_label'] == 'Individuell in Anthias'
                    and isinstance(asset.get('play_time_from'), str)
                    and isinstance(asset.get('play_time_to'), str)
                    and asset['play_time_from'].endswith(':00')
                    and asset['play_time_to'].endswith(':00') else 'choose'
            )
        folder_templates = managed_playlists_for_device(device_id, templates)
        can_edit_player = (current_user()['role'] in ('marketing', 'owner', 'it')
                           and not error and
                           (not folder_templates or
                            (app.config['HUB_DEVELOPMENT_MODE'] and not app.config['HUB_WORKFLOW_V2']))
                           and not library_unavailable)
        from .folder_status import read_status
        folder_sync_by_template = {t['id']: read_status(t['id']) for t in folder_templates}
        publish_enabled = bool(folder_templates) and all(
            row['auto_publish'] and row['state'] == 'ok'
            for row in folder_sync_by_template.values())
        from .folder_sync import available_sources
        if app.config['HUB_WORKFLOW_V2']:
            from .screen_modes import resolve_mode
            mode = resolve_mode(device_id, templates, assets=assets, error=error)
            # A guessed editor URL may never expose duplicate managed controls.
            if request.args.get('editor') != '1' or mode['key'] not in ('manual', 'empty'):
                return render_template(
                'screen_v2.html', device=device, mode=mode, assets=assets,
                folder_sync_by_template=folder_sync_by_template,
                publisher_ready=publish_enabled,
                templates=templates, error=error)
        return render_template('playlist.html', device=device, assets=assets,
                               available_folder_sources=available_sources() if current_user()['role'] in ('owner', 'it') else [],
                               folder_templates=folder_templates,
                               folder_managed=bool(folder_templates),
                               folder_publish_enabled=publish_enabled,
                               folder_sync_by_template=folder_sync_by_template,
                               can_edit_player=can_edit_player,
                               library_templates=templates,
                               library_items_available=any(t.get('items') for t in templates),
                               schedule_profiles=schedule_profiles,
                               schedule_default=schedule_default,
                               can_schedule=current_user()['role'] in ('owner', 'it', 'marketing'),
                               error=error, storage=storage, storage_reason=storage_reason)

    @app.get('/schedules')
    @login_required()
    def schedule_library_page():
        """Shared presets live here; viewing them never calls a player API."""
        try:
            profiles = profiles_for(app.config['SCHEDULES_FILE'])
        except ScheduleError as exc:
            profiles = []
            flash(str(exc), 'error')
        return render_template(
            'schedule_library.html', profiles=profiles,
            devices=load(app.config['DEVICES_FILE']),
            can_edit=current_user()['role'] in ('owner', 'it', 'marketing'),
        )

    @app.post('/schedules/add')
    @login_required('it', 'marketing')
    def schedule_library_add():
        try:
            saved = add_profile(
                app.config['SCHEDULES_FILE'], 'hub',
                request.form.get('name', ''), request.form.getlist('days'),
                request.form.get('start', ''), request.form.get('end', ''),
            )
            audit('schedule.add', 'hub', saved['id'])
            flash('Gemeinsamer Zeitplan erstellt. Bestehende Pi-Inhalte bleiben unverändert.', 'success')
        except ScheduleError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('schedule_library_page'))

    @app.post('/schedules/<profile_id>/edit')
    @login_required('it', 'marketing')
    def schedule_library_edit(profile_id):
        sync_device = request.form.get('sync_device', '').strip()
        if sync_device:
            # The explicit target must still be a registered player.
            player_or_404(sync_device)
        try:
            saved = edit_profile(
                app.config['SCHEDULES_FILE'], 'hub', profile_id,
                request.form.get('name', ''), request.form.getlist('days'),
                request.form.get('start', ''), request.form.get('end', ''),
            )
            audit('schedule.edit', 'hub', saved['id'])
            if sync_device:
                _, api = player_or_404(sync_device)
                linked = assignments_for(app.config['SCHEDULES_FILE'], sync_device)
                originals = {item['asset_id']: item for item in api.assets()}
                to_sync = []
                for ident, record in linked.items():
                    if record.get('profile_id') != profile_id or ident not in originals:
                        continue
                    try:
                        # Only change values last acknowledged on this Pi.
                        if native_key(originals[ident]) == linked_native_key(record):
                            to_sync.append(ident)
                    except ScheduleError:
                        continue
                if to_sync:
                    apply_to_assets(
                        api, saved, to_sync,
                        on_applied=lambda ident, values: bind_asset(
                            app.config['SCHEDULES_FILE'], sync_device, ident, profile_id, values))
                flash(f'Vorlage gespeichert. {len(to_sync)} bestätigte Inhalte auf '
                      f'{sync_device} aktualisiert; andere Pis unverändert.', 'success')
            else:
                flash('Gemeinsame Vorlage aktualisiert. Zeitfenster auf allen Pis bleiben '
                      'unverändert, bis sie ausdrücklich zugewiesen werden.', 'success')
        except (ScheduleError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('schedule_library_page'))

    @app.post('/schedules/<profile_id>/delete')
    @login_required('it', 'marketing')
    def schedule_library_delete(profile_id):
        if (request.form.get('confirm') != profile_id or
                request.form.get('confirm_global') != 'yes'):
            abort(400, 'Hubweites Entfernen des Zeitplans ausdrücklich bestätigen')
        try:
            remove_profile(app.config['SCHEDULES_FILE'], 'hub', profile_id)
            audit('schedule.delete', 'hub', profile_id)
            flash('Zeitplan hubweit entfernt. Vorhandene Pi-Zeitfenster bleiben erhalten.', 'success')
        except ScheduleError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('schedule_library_page'))

    @app.get('/devices/<device_id>/schedules')
    @login_required()
    def device_schedules(device_id):
        device, api = player_or_404(device_id)
        try:
            profiles = profiles_for(app.config['SCHEDULES_FILE'], device_id)
        except ScheduleError as exc:
            profiles = []
            flash(str(exc), 'error')
        assets, problem = [], None
        try:
            assets = api.assets()
        except PlayerError as exc:
            problem = str(exc)
        bindings = assignments_for(app.config['SCHEDULES_FILE'], device_id)
        for asset in assets:
            asset['schedule_label'] = describe_linked_asset(asset, profiles, bindings)
        folder_templates = managed_playlists_for_device(device_id)
        return render_template('schedules.html', device=device,
                               folder_templates=folder_templates,
                               profiles=profiles, assets=assets,
                               schedule_default=default_for(app.config['SCHEDULES_FILE'], device_id),
                               schedule_bindings=bindings,
                               gap_warning=weekday_warning(assets) if not problem else '',
                               problem=problem,
                               can_edit=current_user()['role'] in ('owner', 'it', 'marketing')
                                        and (not folder_templates or
                                             (app.config['HUB_DEVELOPMENT_MODE'] and
                                              not app.config['HUB_WORKFLOW_V2'])))

    @app.post('/devices/<device_id>/schedules/default')
    @login_required('it', 'marketing')
    def device_schedule_default(device_id):
        player_or_404(device_id)
        try:
            selected = request.form.get('profile_id', '')
            if selected == 'always':
                selected = None
            if selected is None or selected:
                set_default(app.config['SCHEDULES_FILE'], device_id, selected)
                audit('schedule.default', device_id, selected or 'always')
                flash('Geräte-Standard gespeichert. Bestehende Inhalte bleiben unverändert.', 'success')
            else:
                raise ScheduleError('Bitte einen Geräte-Standard auswählen.')
        except ScheduleError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('device_schedules', device_id=device_id))

    @app.post('/devices/<device_id>/assets/<asset_id>/schedule')
    @login_required('it', 'marketing')
    def asset_schedule(device_id, asset_id):
        _, api = player_or_404(device_id)
        try:
            rule, pid = chosen_schedule(device_id)
            apply_to_assets(api, rule, [asset_id], on_applied=lambda ident, values: bind_asset(
                app.config['SCHEDULES_FILE'], device_id, ident, pid, values))
            audit('schedule.asset', device_id, asset_id)
            flash('Zeitplanung des Inhalts auf Anthias gespeichert.', 'success')
        except (ScheduleError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('playlist', device_id=device_id) + '#asset-' + asset_id)

    @app.post('/devices/<device_id>/schedules/add')
    @login_required('it', 'marketing')
    def device_schedule_add(device_id):
        player_or_404(device_id)  # Registered devices only.
        try:
            saved = add_profile(
                app.config['SCHEDULES_FILE'], device_id,
                request.form.get('name', ''), request.form.getlist('days'),
                request.form.get('start', ''), request.form.get('end', ''),
            )
            audit('schedule.add', device_id, saved['id'])
            flash('Gemeinsamer Zeitplan gespeichert – jetzt auf allen Geräten verfügbar.', 'success')
        except ScheduleError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('device_schedules', device_id=device_id))

    @app.post('/devices/<device_id>/schedules/<profile_id>/edit')
    @login_required('it', 'marketing')
    def device_schedule_edit(device_id, profile_id):
        player_or_404(device_id)
        try:
            saved = edit_profile(
                app.config['SCHEDULES_FILE'], device_id, profile_id,
                request.form.get('name', ''), request.form.getlist('days'),
                request.form.get('start', ''), request.form.get('end', ''),
            )
            audit('schedule.edit', device_id, saved['id'])
            if request.form.get('sync_assigned') == 'yes':
                # Sync only explicitly linked and still-unmodified native values;
                # an externally edited Pi rule is never overwritten.
                _, api = player_or_404(device_id)
                linked = assignments_for(app.config['SCHEDULES_FILE'], device_id)
                originals = {x['asset_id']: x for x in api.assets()}
                to_sync = []
                for ident, record in linked.items():
                    if record.get('profile_id') != profile_id or ident not in originals:
                        continue
                    try:
                        # Compare with the LAST Pi-acknowledged assignment,
                        # not the current hub-wide template. This still works
                        # if another device edited the global rule meanwhile.
                        if native_key(originals[ident]) == linked_native_key(record):
                            to_sync.append(ident)
                    except ScheduleError:
                        pass
                if to_sync:
                    apply_to_assets(
                        api, saved, to_sync,
                        on_applied=lambda ident, values: bind_asset(
                            app.config['SCHEDULES_FILE'], device_id,
                            ident, profile_id, values))
                flash(f'Gemeinsame Vorlage gespeichert. {len(to_sync)} bestätigte Inhalte auf '
                      f'{device_id} aktualisiert. Andere Geräte behalten ihre '
                      'bisherigen Pi-Zeitfenster bis zur ausdrücklichen Übernahme; '
                      'extern angepasste Inhalte wurden ausgespart.', 'success')
            else:
                flash('Gemeinsame Vorlage aktualisiert. Vorhandene Pi-Zeitfenster bleiben '
                      'unverändert, bis sie auf dem jeweiligen Gerät erneut zugewiesen werden.', 'success')
        except (ScheduleError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('device_schedules', device_id=device_id))

    @app.post('/devices/<device_id>/schedules/<profile_id>/delete')
    @login_required('it', 'marketing')
    def device_schedule_delete(device_id, profile_id):
        player_or_404(device_id)
        if (request.form.get('confirm') != profile_id or
                request.form.get('confirm_global') != 'yes'):
            abort(400, 'Hubweites Entfernen des Zeitplans ausdrücklich bestätigen')
        try:
            remove_profile(app.config['SCHEDULES_FILE'], device_id, profile_id)
            audit('schedule.delete', device_id, profile_id)
            flash('Zeitplan aus der gemeinsamen Sammlung entfernt. Geräte-Standards und '
                  'Hub-Zuordnungen wurden bereinigt. Wiedergabezeiten auf den Pis '
                  'wurden nicht verändert.', 'success')
        except ScheduleError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('device_schedules', device_id=device_id))

    @app.post('/devices/<device_id>/schedules/apply')
    @login_required('it', 'marketing')
    def device_schedule_apply(device_id):
        _, api = player_or_404(device_id)
        try:
            choice = request.form.get('profile_id', '')
            profiles = profiles_for(app.config['SCHEDULES_FILE'], device_id)
            profile = None if choice == 'always' else next(
                (p for p in profiles if p['id'] == choice), None)
            if not choice or (choice != 'always' and profile is None):
                raise ScheduleError('Bitte einen vorhandenen Zeitplan wählen.')
            count = apply_to_assets(
                api, profile, request.form.getlist('asset_ids'),
                on_applied=lambda ident, values: bind_asset(
                    app.config['SCHEDULES_FILE'], device_id, ident,
                    profile['id'] if profile else None, values))
            audit('schedule.apply', device_id, choice)
            flash(f'{count} Inhalte auf dem Pi zeitlich aktualisiert. '
                  'Der Pi entscheidet anhand seiner lokalen Zeitzone, wann sie laufen.', 'success')
        except (ScheduleError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('device_schedules', device_id=device_id))

    @app.get('/devices/<device_id>/storage')
    @login_required()
    def device_storage(device_id):
        """Fresh, read-only status with explicit unknown/full/ready distinction."""
        _, api = player_or_404(device_id)
        disk, reason = read_player_storage(api)
        if disk is None:
            return jsonify(ok=False, status='unknown', usable_bytes=0,
                           message=reason or 'Speicherprüfung fehlgeschlagen')
        return jsonify(ok=True, status='ready' if disk['usable_bytes'] else 'full',
                       **disk)


    @app.get('/devices/<device_id>/assets/<asset_id>/preview')
    @login_required()
    def player_asset_preview(device_id, asset_id):
        """Read-only, authenticated, same-player media preview (never URL proxy).

        The native Anthias media-preview URL serves local files directly; remote
        URL assets redirect elsewhere, which we intentionally do not follow.
        This endpoint is restricted to registered device + asset IDs and
        image/video asset types. Range requests keep video previews lightweight.
        """
        Anthias.valid_id(asset_id)
        _, api = player_or_404(device_id)
        try:
            asset = api.call('GET', '/api/v2/assets/' + asset_id, timeout=4)
        except PlayerError:
            abort(404)
        if not isinstance(asset, dict) or str(asset.get('asset_id')) != asset_id:
            abort(404)
        mime_type = str(asset.get('mimetype') or '')
        is_image = mime_type == 'image' or mime_type.startswith('image/')
        is_video = mime_type == 'video' or mime_type.startswith('video/')
        if not is_image and not is_video:
            abort(404)
        uri = str(asset.get('uri') or '')
        # Never fetch off-player URLs, even when Anthias would redirect there.
        if not uri or uri.startswith(('http://', 'https://', '//')):
            abort(404)

        incoming_range = request.headers.get('Range', '')
        if incoming_range and not re.fullmatch(r'bytes=\d+-\d*', incoming_range):
            abort(416)
        upstream_headers = {'Accept': '*/*'}
        if incoming_range:
            upstream_headers['Range'] = incoming_range
        upstream = None
        try:
            upstream = api.http.request(
                'GET', api.url + '/assets/' + asset_id + '/preview/',
                headers={**upstream_headers, 'Accept-Encoding': 'identity'}, stream=True, timeout=(3, 12),
            )
            if upstream.status_code not in (200, 206):
                upstream.close()
                abort(404)
            claimed_type = upstream.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            # Keep malformed remote replies out of a same-origin media route.
            if claimed_type and claimed_type not in (
                'application/octet-stream', 'image/png', 'image/jpeg',
                'image/webp', 'video/mp4', 'video/quicktime',
            ):
                upstream.close()
                abort(404)
            cap = 8 * 1024 * 1024 if is_image else 55 * 1024 * 1024
            content_length = upstream.headers.get('Content-Length')
            if content_length and (not content_length.isdigit() or int(content_length) > cap):
                upstream.close()
                abort(404)
            chunks = upstream.iter_content(chunk_size=65536)
            first = next(chunks, b'')
            if not first:
                upstream.close()
                abort(404)
            # Uploaded images often have .tmp filenames and octet-stream MIME.
            if is_image:
                if first.startswith(b'\x89PNG\r\n\x1a\n'):
                    content_type = 'image/png'
                elif first.startswith(b'\xff\xd8\xff'):
                    content_type = 'image/jpeg'
                elif first.startswith(b'RIFF') and first[8:12] == b'WEBP':
                    content_type = 'image/webp'
                else:
                    upstream.close()
                    abort(404)
            else:
                content_type = 'video/mp4'
                if upstream.status_code == 200 and first[4:8] != b'ftyp':
                    upstream.close()
                    abort(404)
                if claimed_type.startswith('image/'):
                    upstream.close()
                    abort(404)

            def media_stream():
                size = 0
                try:
                    size += len(first)
                    yield first
                    for chunk in chunks:
                        size += len(chunk)
                        if size > cap:
                            break
                        yield chunk
                finally:
                    upstream.close()

            response = Response(
                stream_with_context(media_stream()), status=upstream.status_code,
                content_type=content_type,
            )
            if content_length:
                response.headers['Content-Length'] = content_length
            if upstream.status_code == 206:
                range_header = upstream.headers.get('Content-Range', '')
                if re.fullmatch(r'bytes \d+-\d+/\d+', range_header):
                    response.headers['Content-Range'] = range_header
            if upstream.headers.get('Accept-Ranges') == 'bytes':
                response.headers['Accept-Ranges'] = 'bytes'
            return response
        except requests.RequestException:
            if upstream is not None:
                upstream.close()
            abort(404)

    @app.post('/devices/<device_id>/add-url')
    @login_required('marketing')
    def add_url(device_id):
        _, api = player_or_404(device_id)
        try:
            name = request.form.get('name', '').strip()
            if not 1 <= len(name) <= 100:
                raise ValueError('Bitte einen Titel (max. 100 Zeichen) angeben')
            uri = validate_website_url(request.form.get('url'))
            duration = validate_duration(request.form.get('duration'))
            create_scheduled(api, device_id, name, uri, duration)
            audit('asset.add-url', device_id)
            flash('Webseite zur Playlist hinzugefügt.', 'success')
        except (ValueError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/upload')
    @login_required('marketing')
    def upload(device_id):
        _, api = player_or_404(device_id)
        destination = url_for('playlist', device_id=device_id)
        transferred = False
        try:
            file = request.files.get('media')
            if file is None or not file.filename:
                raise ValueError('Bitte eine Datei auswählen')
            filename = secure_filename(file.filename)
            ext = Path(filename).suffix.lower()
            if ext not in MEDIA:
                raise ValueError('Erlaubt: PNG, JPG, WebP, MP4')
            file.stream.seek(0, os.SEEK_END)
            size = file.stream.tell()
            file.stream.seek(0)
            if size > MAX_MEDIA_BYTES:
                raise ValueError('Datei zu groß (max. 4 GiB)')
            head = file.stream.read(16)
            file.stream.seek(0)
            signatures = {
                '.png': head.startswith(b'\x89PNG\r\n\x1a\n'),
                '.jpg': head.startswith(b'\xff\xd8'),
                '.jpeg': head.startswith(b'\xff\xd8'),
                '.webp': head.startswith(b'RIFF') and head[8:12] == b'WEBP',
                '.mp4': len(head) >= 12 and head[4:8] == b'ftyp',
            }
            if not signatures[ext]:
                raise ValueError('Dateiformat passt nicht zur Dateiendung')
            title = request.form.get('name', '').strip() or filename
            if len(title) > 100:
                raise ValueError('Titel zu lang')
            length = 0 if ext == '.mp4' else validate_duration(request.form.get('duration', 15))
            # Reject a missing/invalid selected schedule BEFORE uploading bytes.
            # Pi media should not be orphaned by a simple form-selection error.
            chosen_schedule(device_id)
            # Once the transfer starts, an error may leave a file on Anthias.
            # Never promise that retrying is safe without reviewing the playlist.
            transferred = True
            if requested_storage_override():
                audit('storage.override-request', device_id)
            if requested_storage_override():
                result = api.upload(file.stream, filename, MEDIA[ext], allow_unknown_space=True)
            else:
                result = api.upload(file.stream, filename, MEDIA[ext])
            create_scheduled(api, device_id, title, result['uri'], length, mimetype=MEDIA[ext], ext=result.get('ext'))
            audit('asset.upload', device_id)
            if request.accept_mimetypes.best == 'application/json':
                return jsonify(ok=True, message='Medium zur Playlist hinzugefügt.', redirect=destination)
            flash('Medium zur Playlist hinzugefügt.', 'success')
        except (ValueError, PlayerError) as exc:
            message = str(exc)
            if transferred:
                message += ' Übertragung möglicherweise teilweise erfolgt. Playlist am Player prüfen, nicht blind erneut hochladen.'
            if request.accept_mimetypes.best == 'application/json':
                return jsonify(ok=False, error=message), 422
            flash(message, 'error')
        return redirect(destination)

    @app.post('/devices/<device_id>/assets/<asset_id>/edit')
    @login_required('marketing')
    def edit_asset(device_id, asset_id):
        _, api = player_or_404(device_id)
        asset, _ = chosen_asset(api, asset_id)
        if asset is None:
            abort(404)
        try:
            name = request.form.get('name', '').strip()
            if not 1 <= len(name) <= 100:
                raise ValueError('Ungültiger Titel')
            # Enabled state is owned by /toggle. An edit form left open before
            # another user's pause/resume must not silently revert that change.
            changes = {'name': name}
            if asset.get('mimetype') != 'video' and not str(asset.get('mimetype') or '').startswith('video/'):
                changes['duration'] = validate_duration(request.form.get('duration'))
            # Keep device-specific date schedules unchanged unless editing is intentionally added later.
            api.patch(asset_id, changes)
            audit('asset.edit', device_id, asset_id)
            if request.accept_mimetypes.best == 'application/json':
                return jsonify({'ok': True, 'asset': changes})
            flash('Playlist-Element aktualisiert.', 'success')
        except (ValueError, PlayerError) as exc:
            if request.accept_mimetypes.best == 'application/json':
                return jsonify({'ok': False, 'error': str(exc)}), 422
            flash(str(exc), 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/assets/<asset_id>/move')
    @login_required('marketing')
    def move_asset(device_id, asset_id):
        _, api = player_or_404(device_id)
        _, assets = chosen_asset(api, asset_id)
        ids = [str(a['asset_id']) for a in assets]
        if len(set(ids)) != len(ids) or asset_id not in ids:
            abort(409, 'Playlist hat sich verändert')
        direction = request.form.get('direction')
        if direction not in ('up', 'down'):
            abort(400)
        i = ids.index(asset_id)
        j = i + (-1 if direction == 'up' else 1)
        if 0 <= j < len(ids):
            ids[i], ids[j] = ids[j], ids[i]
            api.order(ids)
            audit('asset.move', device_id, asset_id)
            flash('Reihenfolge aktualisiert.', 'success')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/reorder')
    @login_required('marketing')
    def reorder_assets(device_id):
        """One atomic order call; reject stale editors instead of overwriting another user."""
        _, api = player_or_404(device_id)
        wanted = request.form.getlist('ids')
        baseline = request.form.getlist('baseline')
        current = [str(a['asset_id']) for a in api.assets()]
        if (not current or len(current) != len(set(current))
                or len(wanted) != len(current) or len(wanted) != len(set(wanted))
                or set(wanted) != set(current)):
            return jsonify({'ok': False, 'error': 'Playlist geändert. Bitte neu laden.'}), 409
        if baseline != current:
            return jsonify({'ok': False, 'error': 'Playlist wurde inzwischen geändert. Bitte neu laden.'}), 409
        if wanted != current:
            api.order(wanted)
            audit('asset.reorder', device_id)
        return jsonify({'ok': True, 'ids': wanted})

    @app.post('/devices/<device_id>/assets/<asset_id>/toggle')
    @login_required('marketing')
    def toggle_asset(device_id, asset_id):
        """Explicit desired state, with a stale-state check to avoid surprise writes."""
        _, api = player_or_404(device_id)
        desired, expected = request.form.get('enabled'), request.form.get('expected')
        if desired not in ('0', '1') or expected not in ('0', '1'):
            abort(400, 'Status ungültig')
        asset, _ = chosen_asset(api, asset_id)
        if asset is None:
            abort(404)
        before = bool(asset.get('is_enabled'))
        if before != (expected == '1'):
            if request.accept_mimetypes.best == 'application/json':
                return jsonify({'ok': False, 'error': 'Status wurde geändert. Bitte neu laden.'}), 409
            flash('Status wurde geändert. Bitte Seite neu laden.', 'error')
            return redirect(url_for('playlist', device_id=device_id))
        after = desired == '1'
        if before != after:
            api.patch(asset_id, {'is_enabled': after})
            audit('asset.toggle', device_id, asset_id)
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({'ok': True, 'enabled': after})
        flash('Inhalt aktiviert.' if after else 'Inhalt pausiert.', 'success')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/bulk-delete')
    @login_required('marketing')
    def bulk_delete_assets(device_id):
        """Delete confirmed player assets, never devices or local library templates.

        Anthias v2 deletes one asset per call, not transactionally. A complete
        ordered snapshot check rejects stale page selections before any write.
        """
        device, api = player_or_404(device_id)
        mode = request.form.get('mode')
        if mode not in ('selected', 'all') or request.form.get('ack') != 'yes':
            abort(400, 'Löschung ausdrücklich bestätigen')
        baseline = request.form.getlist('baseline')
        selected = request.form.getlist('selected')
        if (not baseline or len(baseline) > 500 or len(set(baseline)) != len(baseline)
                or any(not ASSET_ID.fullmatch(item_id) for item_id in baseline)):
            abort(400, 'Ungültige Playlist-Auswahl')
        try:
            if len(selected) != len(set(selected)) or any(item_id not in baseline for item_id in selected):
                abort(400, 'Ungültige Playlist-Auswahl')
            if mode == 'selected' and not selected:
                abort(400, 'Bitte mindestens einen Inhalt auswählen')
            if mode == 'selected' and len(selected) == len(baseline):
                abort(400, 'Für das vollständige Leeren bitte die gesonderte Bestätigung mit Bildschirmnamen verwenden')
            if mode == 'all' and request.form.get('name_confirmation') != device['name']:
                abort(400, 'Bildschirmname stimmt nicht überein')
            with _apply_lock:
                current = [str(a['asset_id']) for a in api.assets()]
                if current != baseline or len(current) != len(set(current)):
                    abort(409, 'Die Playlist hat sich verändert. Bitte neu laden und erneut auswählen. Nichts gelöscht.')
                targets = selected if mode == 'selected' else baseline
                # Delete only snapshot-confirmed IDs. No unscoped wipe call.
                removed = 0
                try:
                    for item_id in targets:
                        api.remove(item_id)
                        removed += 1
                        audit('asset.bulk-delete' if mode == 'selected' else 'asset.clear', device_id, item_id)
                except (PlayerError, OSError) as exc:
                    flash(f'{removed} von {len(targets)} Löschungen bestätigt. '
                          'Beim nächsten Inhalt trat ein Fehler auf: ' + str(exc) +
                          '. Player-Playlist jetzt prüfen, nicht blind erneut löschen.', 'error')
                    return redirect(url_for('playlist', device_id=device_id))
        except PlayerError as exc:
            flash(str(exc) + '. Nichts gelöscht.', 'error')
            return redirect(url_for('playlist', device_id=device_id))
        if mode == 'all':
            flash(f'{removed} Inhalte vom Player entfernt. Playlist am TV prüfen; '
                  'Gerät und Bibliotheksvorlagen bleiben erhalten.', 'success')
        else:
            flash(f'{removed} ausgewählte Inhalte entfernt. Playlist am TV prüfen.', 'success')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/assets/<asset_id>/delete')
    @login_required('marketing')
    def delete_asset(device_id, asset_id):
        _, api = player_or_404(device_id)
        if request.form.get('confirm') != asset_id or request.form.get('ack') != 'yes':
            abort(400, 'Löschung ausdrücklich bestätigen')
        asset, _ = chosen_asset(api, asset_id)
        if asset is None:
            abort(404)
        api.remove(asset_id)
        audit('asset.delete', device_id, asset_id)
        flash('Playlist-Element gelöscht.', 'success')
        return redirect(url_for('playlist', device_id=device_id))

    @app.errorhandler(HubStorageFull)
    def storage_full(exc):
        message = str(exc)
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, error=message), 507
        return message, 507

    @app.errorhandler(OSError)
    def disk_os_error(exc):
        # External writers/quota changes can fail directory creation or fsync,
        # before/after a guarded chunk write. Preserve a controlled response.
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            return storage_full(HubStorageFull())
        raise exc

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        if request.accept_mimetypes.best == 'application/json':
            return jsonify(ok=False, error='Datei zu groß (max. 4 GiB pro Medium plus Formular-Overhead)'), 413
        return ('Datei zu groß (max. 4 GiB pro Medium plus Formular-Overhead)', 413)

    @app.errorhandler(PlayerError)
    def api_error(exc):
        return render_template('error.html', message=str(exc)), 502

    return app
