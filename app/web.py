"""Anthias Hub: IT owns devices; Marketing owns playlists."""
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .auth import authenticate, current_user, csrf_token, login_required, require_csrf
from .anthias import Anthias, PlayerError, validate_duration, validate_website_url
from .devices import load, save, get, validate_device

_audit_lock = threading.Lock()
MEDIA = {'.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.mp4':'video/mp4'}


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('APP_SECRET_KEY', ''),
        USERS_FILE=os.environ.get('USERS_FILE', '/config/users.json'),
        DEVICES_FILE=os.environ.get('DEVICES_FILE', '/data/devices.json'),
        AUDIT_FILE=os.environ.get('AUDIT_FILE', '/data/audit.jsonl'),
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
        if request.form.get('confirm') != device_id:
            abort(400, 'Geräte-ID bestätigen')
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
            if not str(asset.get('mimetype') or '').startswith('video/'):
                changes['duration'] = validate_duration(request.form.get('duration'))
            # Keep device-specific date schedules unchanged unless editing is intentionally added later.
            api.patch(asset_id, changes)
            audit('asset.edit', device_id, asset_id)
            flash('Playlist-Element aktualisiert.', 'success')
        except (ValueError, PlayerError) as exc:
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

    @app.post('/devices/<device_id>/assets/<asset_id>/delete')
    @login_required('marketing')
    def delete_asset(device_id, asset_id):
        _, api = player_or_404(device_id)
        if request.form.get('confirm') != asset_id:
            abort(400, 'Element-ID bestätigen')
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
