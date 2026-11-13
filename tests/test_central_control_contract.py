"""Central control must reuse the Hub's protected routes and keep view pages focused."""
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / 'app' / 'templates'
CONTROL = (HTML / 'control_center.html').read_text(encoding='utf-8')
CSS = (ROOT / 'app' / 'static' / 'ui-system.css').read_text(encoding='utf-8')
WEB = (ROOT / 'app' / 'web.py').read_text(encoding='utf-8')


def test_central_control_contains_every_existing_management_action():
    Environment().parse(CONTROL)
    for endpoint in (
        'add_device', 'edit_device', 'remove_device', 'control_device',
        'device_storage', 'library_create', 'library_import', 'library_export',
        'library_auto_devices', 'library_folder_source',
        'media_sources_save', 'media_sources_remove', 'media_sources_sync_now',
        'schedule_library_add', 'schedule_library_edit',
        'schedule_library_delete',
    ):
        assert endpoint in CONTROL or endpoint in (
            'control_device', 'media_sources_remove',
        ), 'missing management action: ' + endpoint
    assert "delete_control(item, return_to_control=true)" in CONTROL
    assert "retire_control(source, return_to_control=true)" in CONTROL
    assert "device_control(device, logged_user.role, return_to_control=true)" in CONTROL
    assert 'data-control-storage' in CONTROL
    assert 'source-v2-item-more' not in CONTROL  # content-level actions stay in content


def test_focused_pages_have_only_view_or_content_actions():
    playlists = (HTML / 'library_index_v2.html').read_text(encoding='utf-8')
    detail = (HTML / 'library_detail_v2.html').read_text(encoding='utf-8')
    sources = (HTML / 'media_sources_v2.html').read_text(encoding='utf-8')
    schedules = (HTML / 'schedule_library_v2.html').read_text(encoding='utf-8')
    for page in (playlists, detail, sources, schedules):
        assert "url_for('control_center'" in page
        Environment().parse(page)
    assert "url_for('library_delete_template'" not in playlists
    assert 'name="devices"' not in detail
    assert "url_for('media_sources_save'" not in sources
    assert "url_for('schedule_library_add'" not in schedules
    assert 'data-progress-stages' in sources and 'data-source-folders' in sources
    assert 'source-v2-sequence-move' in detail
    assert 'source-v2-add-media' in detail


def test_no_control_center_in_unchanged_production_mode():
    assert "if not app.config['HUB_WORKFLOW_V2']:" in WEB
    assert "def control_center():" in WEB
    assert "abort(404)" in WEB
    assert "'control_tab'" in WEB
    assert "app.config['HUB_WORKFLOW_V2'] and tab" in WEB
    assert "if tab == 'sources' and role not in ('it', 'owner'):" in WEB
    base = (HTML / 'base.html').read_text(encoding='utf-8')
    assert "if workflow_v2 and logged_user.role in" in base
    assert 'hub-control-menu' in base
    assert 'site-nav-utility' in base
    assert '.site-nav .hub-control-menu' in CSS
