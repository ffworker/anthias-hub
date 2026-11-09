"""Playlist template uses a single progressive composer without losing native routes."""
from pathlib import Path
from jinja2 import Environment
ROOT=Path(__file__).resolve().parents[1]
PAGE=(ROOT/'app/templates/library_detail.html').read_text(encoding='utf-8')
UI=(ROOT/'app/static/ui-system.css').read_text(encoding='utf-8')
SCRIPT=(ROOT/'app/static/library-drawer.js').read_text(encoding='utf-8')

def test_drawer_replaces_old_action_sidebar():
    Environment().parse(PAGE)
    assert 'class="library-grid library-detail-grid"' in PAGE
    assert 'class="library-drawer-backdrop"' in PAGE
    assert 'data-library-drawer' in PAGE
    assert 'class="library-actions"' not in PAGE
    assert 'library-detail-nav' not in PAGE
    assert 'library-action-disclosure' not in PAGE
    assert PAGE.index('id="items-title"') < PAGE.index('id="library-edit-tools"')
    assert PAGE.index('id="items-title"') < PAGE.index('id="playlist-anwenden"')
    assert 'position:fixed;top:0;right:0;bottom:0' in UI
    assert 'grid-template-columns:minmax(0,1fr)' in UI

def test_all_safe_forms_and_role_boundaries_are_present():
    for action in ('library_add_media','library_bulk_media','library_add_url',
                   'append_library_from_template','apply_library_from_template',
                   'library_folder_source','library_auto_devices'):
        assert "url_for('"+action+"'" in PAGE
    for mode in ('add','apply','settings','more'):
        assert 'data-library-drawer-pane="'+mode+'"' in PAGE
    for mode in ('media','bulk','website'):
        assert 'data-library-add-pane="'+mode+'"' in PAGE
    assert PAGE.count('data-template-transfer') == 2
    assert PAGE.count('name="csrf" value="{{ csrf() }}"') >= 7
    assert 'delete_control(template, true)' in PAGE
    assert 'library-backup-export' in PAGE

def test_progressive_drawer_keyboard_and_discard_protection():
    assert 'library-drawer.js' in PAGE
    assert 'drawer.inert=true' in SCRIPT
    assert "drawer.setAttribute('aria-modal','true')" in SCRIPT
    assert "e.key==='Escape'" in SCRIPT
    assert "e.key!=='Tab'" in SCRIPT
    assert 'Nicht gespeicherte Eingaben' in SCRIPT
    assert 'location.hash' in SCRIPT
    assert 'library-drawer-ready' in SCRIPT
    assert '@media(prefers-reduced-motion:reduce)' in UI
