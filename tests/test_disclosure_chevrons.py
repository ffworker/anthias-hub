"""Regression guard for a single, accessible disclosure-chevron language.

No browser-generated Unicode glyphs, duplicated SVG arrows, or native
<summary> markers should reappear on schedule/playlist/SMB/device controls.
The controls themselves remain real <details>/<summary> elements.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'app/templates'
UI_CSS = ROOT / 'app/static/ui-system.css'
OLD_GLYPHS = re.compile(r'[⌄⌃▾▿▼▲⌵]')


def test_schedule_new_and_edit_have_the_same_real_disclosure_chevron():
    page = (TEMPLATES / 'schedule_library.html').read_text(encoding='utf-8')
    assert 'Neuen gemeinsamen Zeitplan erstellen <span class="ui-chevron" aria-hidden="true"></span>' in page
    assert 'Zeitfenster bearbeiten <span class="ui-chevron" aria-hidden="true"></span>' in page
    assert '<details class="card schedule-new' in page
    assert '<details class="schedule-rule-edit">' in page
    assert OLD_GLYPHS.search(page) is None


def test_other_pages_do_not_reintroduce_font_dependent_dropdown_arrows():
    pages = [
        'schedules.html', 'dashboard.html', 'media_sources.html',
        'playlist.html', '_device_controls.html', '_media_source_retire.html',
        'library_index_v2.html', 'library_detail_v2.html'
    ]
    for name in pages:
        content = (TEMPLATES / name).read_text(encoding='utf-8')
        assert OLD_GLYPHS.search(content) is None, name
        assert '#chevron-down' not in content, name
    device = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    assert 'settings-chevron ui-chevron' in device
    assert 'class="ui-chevron" aria-hidden="true"' in device
    sources = (TEMPLATES / 'media_sources.html').read_text(encoding='utf-8')
    assert 'media-disclosure-chevron ui-chevron' in sources
    assert 'library-action-chevron ui-chevron' in sources
    schedule = (TEMPLATES / 'schedules.html').read_text(encoding='utf-8')
    assert 'schedule-secondary-chevron ui-chevron' in schedule
    retire = (TEMPLATES / '_media_source_retire.html').read_text(encoding='utf-8')
    assert 'media-retire-chevron ui-chevron' in retire


def test_uniform_chevron_has_accessible_states_without_extra_javascript():
    css = UI_CSS.read_text(encoding='utf-8')
    assert '.site-main .ui-chevron {' in css
    assert 'border-right:1.7px solid currentColor!important' in css
    assert 'border-bottom:1.7px solid currentColor!important' in css
    assert '.site-main details[open] > summary .ui-chevron' in css
    assert 'rotate(225deg)' in css
    assert ':not(:has(.ui-chevron))' in css
    assert 'summary:not([aria-label])' in css
    assert 'prefers-reduced-motion:reduce' in css
    assert "content:'⌄'" not in css
    assert "content:'⌃'" not in css
    assert 'details.source-v2-expand > summary::after' in css


def test_icon_only_more_menus_are_not_forced_to_show_a_second_arrow():
    css = UI_CSS.read_text(encoding='utf-8')
    assert 'summary:not([aria-label]):not(:has(.ui-chevron))' in css
    detail = (TEMPLATES / 'library_detail_v2.html').read_text(encoding='utf-8')
    assert 'summary aria-label="Einstellungen für' in detail
    assert 'class="source-v2-item-more source-v2-sequence-more"' in detail
