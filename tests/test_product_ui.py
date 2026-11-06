"""Contract tests for the shared Signaturee-inspired UI without external services."""
from pathlib import Path
from jinja2 import Environment


STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'
TEMPLATES = Path(__file__).resolve().parents[1] / 'app' / 'templates'


def test_product_theme_loads_last_and_controls_are_real():
    base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    assert base.index('ui-refinements.css') < base.index('product-ui.css')
    assert 'product-theme.js' in base
    assert 'data-product-theme-toggle' in base
    assert 'aria-pressed="false"' in base
    assert 'class="skip-link"' in base
    assert base.index('Ordner &amp; Quellen') < base.index('Playlists') < base.index('Bildschirme</a>')
    assert 'logged_user.role in (\'it\', \'owner\')' in base
    sheet = (STATIC / 'product-ui.css').read_text(encoding='utf-8')
    assert 'html[data-theme="dark"]' in sheet
    assert '--ui-bg:#eeece2' in sheet
    assert '#ff795c' in sheet
    assert 'prefers-reduced-motion' in sheet
    assert 'width:min(100% - 40px' not in sheet
    behavior = (STATIC / 'product-theme.js').read_text(encoding='utf-8')
    assert 'localStorage.setItem' in behavior
    assert 'aria-pressed' in behavior
    assert 'data-product-theme-toggle' in behavior


def test_default_library_is_primary_in_all_three_core_views():
    dashboard = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    library = (TEMPLATES / 'library.html').read_text(encoding='utf-8')
    folders = (TEMPLATES / 'media_sources.html').read_text(encoding='utf-8')
    detail = (TEMPLATES / 'library_detail.html').read_text(encoding='utf-8')
    assert dashboard.index('hub-workflow-cards') < dashboard.index('fleet-summary')
    assert library.index('library-source-feature') < library.index('library-grid')
    assert folders.index('media-default-panel') < folders.index('media-sources-admin">\n  <h2>Neue Medienquelle')
    assert 'media-default-folders' in folders
    assert 'media_sources_use_folder' in folders
    assert 'source.startswith(\'default/\')' in detail


def test_templates_parse_without_jinja_syntax_errors():
    env = Environment()
    for path in TEMPLATES.glob('*.html'):
        env.parse(path.read_text(encoding='utf-8'))
