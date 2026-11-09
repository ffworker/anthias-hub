"""Dashboard UI smoke tests: screen work first, device utilities second."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = (ROOT / "app/templates/dashboard.html").read_text(encoding="utf-8")
MACRO = (ROOT / "app/templates/_device_controls.html").read_text(encoding="utf-8")
UI = (ROOT / "app/static/ui-system.css").read_text(encoding="utf-8")

def test_dashboard_prioritizes_screen_tasks():
    assert 'class="fleet-device-primary-actions"' in DASH
    assert DASH.index('class="fleet-device-primary-actions"') < DASH.index('class="fleet-device-tools-label"')
    assert "Inhalte bearbeiten" in DASH and "Inhalte ansehen" in DASH
    assert "Zeitpläne</a>" in DASH

def test_role_safe_utilities_are_labeled():
    for token in ("Geräteaktionen", "Einstellungen", "<span>Speicher</span>", "fleet-actions-it", "fleet-actions-marketing"):
        assert token in DASH
    assert "Hilfe &amp; Neustart" in MACRO
    assert 'name="csrf"' in DASH and 'name="csrf"' in MACRO

def test_dashboard_theme_and_mobile_scope():
    for token in ("UI 06:", ".fleet-device-primary-actions", "var(--ui-raised)", "@media(max-width:600px)"):
        assert token in UI
