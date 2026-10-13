"""Simple, static file-based accounts. Passwords are only stored as slow hashes."""
import json
import os
import secrets
import threading
import time
from functools import wraps
from pathlib import Path
from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash

_attempts = {}
_attempts_lock = threading.Lock()


def accounts():
    with Path(current_app.config['USERS_FILE']).open(encoding='utf-8') as f:
        data = json.load(f)
    users = data.get('users', [])
    if not isinstance(users, list):
        raise ValueError('Invalid users file')
    return {u['username']: u for u in users if u.get('role') in ('it', 'marketing', 'viewer') and u.get('password_hash')}


def authenticate(username, password):
    # In-memory lockout; for internal deployment behind TLS, not internet-exposed auth.
    key = (request.remote_addr, username.lower())
    now = time.monotonic()
    with _attempts_lock:
        hits = [t for t in _attempts.get(key, []) if now - t < 900]
        if len(hits) >= 7:
            return False
    user = accounts().get(username)
    ok = bool(user and check_password_hash(user['password_hash'], password))
    with _attempts_lock:
        if ok:
            _attempts.pop(key, None)
        else:
            _attempts[key] = hits + [now]
    return ok


def current_user():
    username = session.get('user')
    if not username:
        return None
    return accounts().get(username)


def login_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for('login'))
            if roles and u['role'] not in roles:
                abort(403)
            g.user = u
            return fn(*args, **kwargs)
        return inner
    return decorator


def csrf_token():
    if not session.get('csrf'):
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def require_csrf():
    expected = session.get('csrf')
    supplied = request.form.get('csrf')
    if not expected or not supplied or not secrets.compare_digest(str(expected), str(supplied)):
        abort(400, 'Invalid CSRF token')
