"""DEV playlist overview shows honest, actionable import states without extra controls."""
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/templates/library_index_v2.html").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/ui-system.css").read_text(encoding="utf-8")


def test_dev_playlist_overview_distinguishes_pending_failed_and_stale_imports():
    Environment().parse(INDEX)
    assert 'data-import-state="{{ sync.state|default(\'pending\') }}"' in INDEX
    for state, label in (
        ("ok", "Import OK"),
        ("error", "Importfehler"),
        ("stale", "Import veraltet"),
        ("pending", "Import offen"),
    ):
        assert label in INDEX
        if state != "pending":
            assert "sync.state == '" + state + "'" in INDEX
    assert "{% if source.folder_source %}" in INDEX
    assert "url_for('library_detail', template_id=source.id)" in INDEX


def test_failed_and_stale_statuses_stand_out_but_normal_status_is_quiet():
    assert ".source-v2-import-state{white-space:nowrap;color:var(--ui-muted)}" in CSS
    assert '.source-v2-import-state[data-import-state="error"]' in CSS
    assert '.source-v2-import-state[data-import-state="stale"]' in CSS
    assert "color:var(--ui-error)" in CSS
    assert "color:var(--ui-warn)" in CSS
