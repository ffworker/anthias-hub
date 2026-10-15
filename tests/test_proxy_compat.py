"""Explicit proxy trust and secure-cookie defaults."""
import pytest
from werkzeug.middleware.proxy_fix import ProxyFix
from app.web import create_app


def test_proxy_headers_not_trusted_by_default(monkeypatch):
    monkeypatch.setenv('APP_SECRET_KEY', 'x' * 48)
    monkeypatch.delenv('TRUSTED_PROXY_COUNT', raising=False)
    app = create_app({'TESTING': True})
    assert not isinstance(app.wsgi_app, ProxyFix)
    assert app.config['SESSION_COOKIE_SECURE']


def test_single_proxy_requires_opt_in(monkeypatch):
    monkeypatch.setenv('APP_SECRET_KEY', 'x' * 48)
    monkeypatch.setenv('TRUSTED_PROXY_COUNT', '1')
    app = create_app({'TESTING': True})
    assert isinstance(app.wsgi_app, ProxyFix)
    assert app.wsgi_app.x_for == 1
    assert app.wsgi_app.x_proto == 1
    assert app.wsgi_app.x_host == 0


def test_invalid_proxy_count_fails_closed(monkeypatch):
    monkeypatch.setenv('APP_SECRET_KEY', 'x' * 48)
    monkeypatch.setenv('TRUSTED_PROXY_COUNT', '2')
    with pytest.raises(RuntimeError, match='TRUSTED_PROXY_COUNT'):
        create_app({'TESTING': True})
