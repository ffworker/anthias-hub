"""Static contracts for navigation affordances, themes and reduced-motion safety."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'app/static/ui-system.css').read_text(encoding='utf-8')
BASE = (ROOT / 'app/templates/base.html').read_text(encoding='utf-8')
DETAIL = (ROOT / 'app/templates/library_detail.html').read_text(encoding='utf-8')
DEVICE_TABS = (ROOT / 'app/templates/_device_tabs.html').read_text(encoding='utf-8')

def test_main_navigation_has_visible_active_state_without_script():
    assert '.site-nav .site-nav-link.is-active{' in UI
    assert 'border-bottom-color:#ff795c' in UI
    assert 'site-nav-schedule' in BASE
    assert 'aria-current="page"' in BASE

def test_navigation_polish_is_role_safe_and_targeted():
    assert '.site-main .device-workspace-tabs a[aria-current="page"]' in UI
    assert 'box-shadow:inset 0 -3px 0 var(--ui-coral)' in UI
    assert 'id="items-title"' in DETAIL
    for target in ('library-edit-tools','playlist-anwenden','library-more'):
        assert f'href="#{target}"' in DETAIL
    assert 'data-library-workspace' in DETAIL
    assert 'data-library-drawer' in DETAIL
    assert '.site-main .library-template-workspace.library-drawer-ready' in UI
    assert 'url_for(\'playlist\'' in DEVICE_TABS

def test_hover_has_no_persistent_motion_or_hidden_ui():
    assert '@media(hover:hover) and (prefers-reduced-motion:no-preference)' in UI
    assert '@media(prefers-reduced-motion:reduce)' in UI
    assert '.site-nav .site-nav-link,.site-nav .site-nav-link .icon{' in UI
    assert 'transition:none!important;transform:none!important' in UI
    assert 'animation:infinite' not in UI
