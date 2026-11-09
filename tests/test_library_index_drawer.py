"""Library index and detail reuse the same composer and keep the player safe."""
from pathlib import Path
from jinja2 import Environment
ROOT=Path(__file__).resolve().parents[1]
INDEX=(ROOT/'app/templates/library.html').read_text(encoding='utf-8')
DETAIL=(ROOT/'app/templates/library_detail.html').read_text(encoding='utf-8')
JS=(ROOT/'app/static/library-drawer.js').read_text(encoding='utf-8')
CSS=(ROOT/'app/static/ui-system.css').read_text(encoding='utf-8')

def test_library_index_is_content_first_and_has_one_drawer():
    Environment().parse(INDEX)
    assert INDEX.index('class="library-list"') < INDEX.index('class="library-detail-drawer"')
    assert INDEX.count('data-library-drawer-pane="create"') == 1
    assert INDEX.count('data-library-drawer-pane="backup"') == 1
    assert 'class="library-actions"' not in INDEX
    assert 'library-action-disclosure' not in INDEX
    assert 'template-delete-control template-delete-list' not in INDEX
    assert 'delete_control(template)' not in INDEX
    assert 'data-library-drawer' in DETAIL
    assert 'data-library-drawer' in INDEX
    assert "filename='library-drawer.js'" in INDEX
    assert "filename='library-drawer.js'" in DETAIL

def test_server_forms_and_access_control_are_preserved():
    assert "url_for('library_create')" in INDEX
    assert "url_for('library_import')" in INDEX
    assert 'name="folder_source"' in INDEX
    assert "logged_user.role in ('owner', 'it')" in INDEX
    assert "logged_user.role in ('marketing', 'owner', 'it')" in INDEX
    assert 'name="archive" accept=".zip" required' in INDEX
    assert INDEX.count('name="csrf" value="{{ csrf() }}"') == 2
    assert 'manifest.json' in INDEX

def test_single_drawer_script_supports_both_pages_and_keyboard():
    assert "'#new-playlist':'create'" in JS
    assert "'#backup-zip':'backup'" in JS
    assert "create:['Neue Playlist'" in JS
    assert "backup:['Backup importieren'" in JS
    assert "e.key==='Escape'" in JS
    assert 'drawer.inert=true' in JS
    assert '.library-index-workspace .library-list{' in CSS
    assert '@media(prefers-reduced-motion:reduce)' in CSS
