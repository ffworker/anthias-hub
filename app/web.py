"""Anthias Hub: IT owns devices; Marketing owns playlists."""
import json
import io
import os
import re
import secrets
import threading

import requests
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, session, stream_with_context, url_for)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .auth import authenticate, current_user, csrf_token, login_required, require_csrf
from .anthias import Anthias, PlayerError, validate_duration, validate_website_url
from .devices import load, save, get, validate_device
from .library import Library, LibraryError

_audit_lock = threading.Lock()
_apply_lock = threading.Lock()
MEDIA = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.mp4':'video/mp4'}


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('APP_SECRET_KEY', ''),
        USERS_FILE=os.environ.get('USERS_FILE', '/config/users.json'),
        DEVICES_FILE=os.environ.get('DEVICES_FILE', '/data/devices.json'),
        AUDIT_FILE=os.environ.get('AUDIT_FILE', '/data/audit.jsonl'),
        LIBRARY_DIR=os.environ.get('LIBRARY_DIR', '/data/library'),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1') == '1',
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    if len(app.config['SECRET_KEY']) < 32 or 'REPLACE' in app.config['SECRET_KEY'].upper() or 'CHANGE_ME' in app.config['SECRET_KEY'].upper():
        raise RuntimeError('APP_SECRET_KEY must contain at least 32 random characters')

    @app.before_request
    def protect_post():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            require_csrf()

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
        return {'csrf': csrf_token, 'logged_user': current_user()}

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

    @app.get('/library')
    @login_required()
    def library_index():
        return render_template('library.html', templates=library().list())

    @app.post('/library')
    @login_required('marketing')
    def library_create():
        try:
            item = library().create(request.form.get('name', ''))
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
                raise LibraryError('Bitte ein Playlist-ZIP auswählen')
            item = library().import_zip(file.stream)
            audit('library.import', asset_id=item['id'])
            return redirect(url_for('library_detail', template_id=item['id']))
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
        return render_template('library_detail.html', template=item, devices=load(app.config['DEVICES_FILE']))

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
            archive = library().export(template_id)
        except LibraryError:
            abort(404)
        return send_file(io.BytesIO(archive), mimetype='application/zip', as_attachment=True,
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
        try:
            file = request.files.get('media')
            if file is None or not file.filename:
                raise LibraryError('Bitte eine Datei auswählen')
            library().add_media(template_id, request.form.get('name') or file.filename,
                                file.stream, file.filename, request.form.get('duration'))
            audit('library.add-media', asset_id=template_id)
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
        return redirect(url_for('library_detail', template_id=template_id))

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
                        api.create(item['name'], item['url'], item['duration'])
                    else:
                        path = media_paths[item['id']]
                        ext = path.suffix.lower()
                        with path.open('rb') as stream:
                            uploaded = api.upload(stream, path.name, MEDIA[ext])
                        api.create(item['name'], uploaded['uri'], item['duration'], mimetype=MEDIA[ext], ext=uploaded.get('ext'))
            audit('library.apply', device_id, template['id'])
            flash('Vorlage übertragen. Playlist und Ausgabe am TV prüfen.', 'success')
        except (LibraryError, PlayerError, OSError) as exc:
            flash(str(exc) + ' Keine automatische Wiederholung: Playlist am Player prüfen (Teilübertragung möglich).', 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/library/<template_id>/apply')
    @login_required('marketing')
    def apply_library_from_template(template_id):
        if request.form.get('template_id') != template_id:
            abort(400)
        return apply_library(request.form.get('device', ''))

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
        devices = load(app.config['DEVICES_FILE'])
        statuses = {}
        for device in devices:
            try:
                statuses[device['id']] = {'ok': True, 'count': len(Anthias(device).assets())}
            except PlayerError:
                statuses[device['id']] = {'ok': False, 'count': None}
        return render_template('dashboard.html', devices=devices, statuses=statuses)

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
        return render_template('playlist.html', device=device, assets=assets, error=error)

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
            api.create(name, uri, duration)
            audit('asset.add-url', device_id)
            flash('Webseite zur Playlist hinzugefügt.', 'success')
        except (ValueError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('playlist', device_id=device_id))

    @app.post('/devices/<device_id>/upload')
    @login_required('marketing')
    def upload(device_id):
        _, api = player_or_404(device_id)
        try:
            file = request.files.get('media')
            if file is None or not file.filename:
                raise ValueError('Bitte eine Datei auswählen')
            filename = secure_filename(file.filename)
            ext = Path(filename).suffix.lower()
            if ext not in MEDIA:
                raise ValueError('Erlaubt: PNG, JPG, WebP, MP4')
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
            result = api.upload(file.stream, filename, MEDIA[ext])
            api.create(title, result['uri'], length, mimetype=MEDIA[ext], ext=result.get('ext'))
            audit('asset.upload', device_id)
            flash('Datei zur Playlist hinzugefügt.', 'success')
        except (ValueError, PlayerError) as exc:
            flash(str(exc), 'error')
        return redirect(url_for('playlist', device_id=device_id))

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
            changes = {'name': name, 'is_enabled': request.form.get('enabled') == 'on'}
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

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        return ('Datei zu groß (max. 50 MB)', 413)

    @app.errorhandler(PlayerError)
    def api_error(exc):
        return render_template('error.html', message=str(exc)), 502

    return app
