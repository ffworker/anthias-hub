"""Device playlist has one place for each action and no duplicate template forms."""
from pathlib import Path
from jinja2 import Environment
ROOT=Path(__file__).resolve().parents[1]
PLAYER=(ROOT/'app/templates/playlist.html').read_text(encoding='utf-8')
DETAIL=(ROOT/'app/templates/library_detail.html').read_text(encoding='utf-8')
INDEX=(ROOT/'app/templates/library.html').read_text(encoding='utf-8')
CSS=(ROOT/'app/static/playlist.css').read_text(encoding='utf-8')
UI=(ROOT/'app/static/ui-system.css').read_text(encoding='utf-8')


def test_device_add_only_once_and_single_item_library():
    Environment().parse(PLAYER)
    assert PLAYER.count('data-open-composer') == 1
    assert 'id="add-content"' in PLAYER
    assert 'data-add-mode="library"' in PLAYER
    assert '>Bibliothek</button>' in PLAYER
    assert 'add_library_item_from_player' in PLAYER
    assert 'data-library-source' in PLAYER
    assert 'Weiteren Inhalt hinzufügen' not in PLAYER
    assert 'library-template-append' not in PLAYER
    assert 'append_library_from_player' not in PLAYER
    assert 'attach_folder_playlist_to_device' not in PLAYER
    assert 'import_network_folder_once' in PLAYER


def test_whole_template_and_folder_automation_remain_centrally_available():
    assert 'append_library_from_template' in DETAIL
    assert 'apply_library_from_template' in DETAIL
    assert 'library_auto_devices' in DETAIL
    assert 'library_folder_source' in DETAIL
    assert "url_for('library_index')" in PLAYER
    assert 'data-open-library-drawer="apply"' in DETAIL
    assert 'id="library-index-drawer"' in INDEX


def test_no_stale_css_or_hidden_duplicate_actions():
    assert '.library-template-append' not in CSS
    assert '.playlist-bottom-actions' not in CSS
    assert '.library-template-append' not in UI
    assert '.playlist-bottom-actions' not in UI
    assert 'data-bulk-check' in PLAYER
    assert 'data-bulk-management' in PLAYER
    assert 'id="playlist-bulk-form"' in PLAYER
    assert 'csrf()' in PLAYER
