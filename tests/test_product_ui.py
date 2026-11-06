"""Contract tests for the shared Signaturee-inspired UI without external services."""
from pathlib import Path
from jinja2 import Environment


STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'
TEMPLATES = Path(__file__).resolve().parents[1] / 'app' / 'templates'


def test_product_theme_loads_last_and_controls_are_real():
    base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    assert "filename='ui-system.css'" in base
    assert "filename='product-ui.css'" not in base
    assert "filename='workflow-ui.css'" not in base
    assert "filename='ui-refinements.css'" not in base
    assert 'name="anthias-hub-ui" content="ui-20261106-06"' in base
    assert base.index('{% block extra_head %}') < base.index("filename='ui-system.css'")
    assert 'product-theme.js' in base
    assert 'data-product-theme-toggle' in base
    assert 'aria-pressed="false"' in base
    assert 'class="skip-link"' in base
    assert base.index('Bildschirme</a>') < base.index('Playlists</a>') < base.index('Ordner &amp; Quellen</a>')
    assert 'logged_user.role in (\'it\', \'owner\')' in base
    sheet = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
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
    assert 'library-source-feature' not in library  # no network hero before the playlists
    assert library.index('library-workflow-nav') < library.index('library-grid')
    assert folders.index('media-default-panel') < folders.index('media-sources-admin')
    assert 'media-folder-notice' in folders
    assert 'library_index' in folders
    assert 'media-default-folders' not in folders
    assert 'id="new-playlist"' in library
    assert 'source.startswith(\'default/\')' in detail


def test_templates_parse_without_jinja_syntax_errors():
    env = Environment()
    for path in TEMPLATES.glob('*.html'):
        env.parse(path.read_text(encoding='utf-8'))


def test_playlist_workflows_have_explicit_categories_and_theme_aware_contrast():
    base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    library = (TEMPLATES / 'library.html').read_text(encoding='utf-8')
    detail = (TEMPLATES / 'library_detail.html').read_text(encoding='utf-8')
    player = (TEMPLATES / 'playlist.html').read_text(encoding='utf-8')
    sheet = (STATIC / 'ui-system.css').read_text(encoding='utf-8')

    assert base.index('{% block extra_head %}') < base.index('ui-system.css')
    for title in ('Vorlagen ansehen', 'Neue Playlist', 'ZIP-Backup'):
        assert title in library
    assert 'id="backup-zip"' in library
    assert 'Backup-ZIP exportieren' in detail
    assert 'Vorlage zur Playlist hinzufügen' in detail
    assert 'library-folder-settings' in detail
    assert 'data-add-mode="zip"' in player
    assert 'data-add-mode="library"' in player
    assert 'import_network_folder_once' in player
    assert 'attach_folder_playlist_to_device' in player
    assert "color:var(--ui-fg)!important" in sheet
    assert '.library-item' in sheet and 'grid-template-columns:' in sheet
    assert '@media(max-width:1170px)' in sheet
    assert 'html[data-theme="dark"]' in sheet
    assert 'html[data-theme="light"]' in sheet


def test_dashboard_links_to_actual_screen_list_and_new_device_form_is_optional():
    page = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    script = (STATIC / 'fleet-setup.js').read_text(encoding='utf-8')
    assert 'href="#fleet-devices"' in page
    assert 'id="fleet-devices"' in page
    assert 'href="#fleet-title">Bildschirme ansehen' not in page
    assert '<details id="device-setup"' in page
    assert 'fleet-setup-toggle' in page and 'fleet-setup-body' in page
    assert '{% if not devices %} open{% endif %}' in page
    assert 'fleet-setup.js' in page
    assert "window.location.hash === '#device-setup'" in script
    assert 'setup.open = true' in script
    assert '.fleet-grid-single' in css
    assert '.hub-workflow-card>a.button:not(.primary)' in css
    assert 'var(--ui-fg)!important' in css
    assert 'fleet-setup-collapsible' in css


def test_scheduling_and_fleet_popovers_follow_shared_light_dark_tokens():
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    schedule = (TEMPLATES / 'schedules.html').read_text(encoding='utf-8')
    dashboard = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    assert '.schedule-secondary-panel' in css
    assert '.schedule-assigned' in css
    assert '.schedule-global-confirm' in css
    assert '.schedule-global-delete .schedule-remove' in css
    assert 'html[data-theme="dark"] .schedule-workspace input[type=time]' in css
    assert 'var(--ui-error-bg)' in css
    assert '.fleet-storage-panel' in css
    assert 'class="schedule-workspace"' in schedule
    assert 'fleet-storage-menu' in dashboard


def test_smb_design_levels_and_statuses_are_textual_in_both_themes():
    base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    sources = (TEMPLATES / 'media_sources.html').read_text(encoding='utf-8')
    dashboard = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    detail = (TEMPLATES / 'library_detail.html').read_text(encoding='utf-8')
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')

    assert 'site-nav-utility' in base  # IT administration is secondary navigation.
    assert 'hub-admin-mount-hint' in dashboard
    assert sources.index('media-overview-strip') < sources.index('media-default-panel')
    assert sources.index('media-default-panel') < sources.index('media-existing-sources')
    assert sources.index('media-existing-sources') < sources.index('media-advanced-sources')
    assert sources.index('media-source-facts') < sources.index('media-source-manage')
    for message in (
        'Eingehängt · Host bestätigt', 'Mount unbestätigt',
        'Mount fehlgeschlagen', 'Freigabe blockiert',
        'CIFS-Mount erkannt', 'CIFS-Mount nicht bestätigt',
        'Quelle aus dem Hub entfernen',
    ):
        # Shared removal macro is imported, the rest are template labels.
        assert message in sources or message == 'Quelle aus dem Hub entfernen'
    assert 'Zugeordnet: {{ template.folder_source }}' in detail
    for selector in ('.media-mount-badge.is-confirmed',
                     '.media-mount-badge.is-pending',
                     '.media-mount-badge.is-error',
                     '.media-existing-sources',
                     '.media-source-facts',
                     '@media(max-width:600px)'):
        assert selector in css
    assert 'var(--ui-good-bg)' in css
    assert 'var(--ui-warn-bg)' in css
    assert 'var(--ui-error-bg)' in css
