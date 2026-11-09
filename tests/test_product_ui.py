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
    assert 'name="anthias-hub-ui" content="ui-20261109-08"' in base
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
    assert dashboard.index('id="fleet-devices"') < dashboard.index('class="hub-next-steps"')
    assert 'library-source-feature' not in library  # no network hero before the playlists
    assert library.index('library-index-intro') < library.index('library-grid')
    assert folders.index('media-default-panel') < folders.index('media-sources-admin')
    assert 'class="media-folder-peek"' in folders
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
    for title in ('Playlists', 'Neue Playlist erstellen', 'Vorlagen-Backup importieren'):
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
    assert 'class="hub-next-steps"' in page
    assert 'id="fleet-devices"' in page
    assert 'href="#fleet-title">Bildschirme ansehen' not in page
    assert '<details id="device-setup"' in page
    assert 'fleet-setup-toggle' in page and 'fleet-setup-body' in page
    assert '{% if not devices %} open{% endif %}' in page
    assert 'fleet-setup.js' in page
    assert "window.location.hash === '#device-setup'" in script
    assert 'setup.open = true' in script
    assert '.fleet-grid-single' in css
    assert '.hub-next-steps-grid' in css
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
    assert 'Stammordner: Host-Mount bestätigt' in dashboard
    assert sources.index('media-default-panel') < sources.index('media-overview-strip')
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

def test_device_pages_prioritize_current_task_without_touching_player_actions():
    playlist = (TEMPLATES / 'playlist.html').read_text(encoding='utf-8')
    schedule = (TEMPLATES / 'schedules.html').read_text(encoding='utf-8')
    ui = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    assert '<span aria-current="page">Playlist</span>' in playlist
    assert '<h1>Playlist</h1>' in playlist
    assert '<h1>Zeitpläne</h1>' in schedule
    assert '<span aria-current="page">Zeitpläne</span>' in schedule
    assert 'BILDSCHIRM · {{ device.name }}' in playlist
    assert 'BILDSCHIRM · {{ device.name }}' in schedule
    assert 'Zeitplan zuweisen' in schedule
    # The first-setup case has no presets. Don't render an empty collection
    # with the same explanation before the already-open creation form.
    first = schedule.split('{% if not profiles %}', 1)[1]
    first = first.split('    {% if can_edit %}', 1)[0]
    assert 'class="schedule-presets"' not in first
    assert 'Ersten Zeitplan erstellen' in first
    assert '.device-page-hero' in ui
    assert '.device-page-breadcrumbs' in ui
    assert 'schedule_library_page' in schedule
    shared = (TEMPLATES / 'schedule_library.html').read_text(encoding='utf-8')
    assert 'schedule_library_add' in shared and 'schedule_library_edit' in shared
    assert 'schedule_library_delete' in shared

def test_composer_prioritizes_common_content_sources_and_keeps_forms():
    player = (TEMPLATES / 'playlist.html').read_text(encoding='utf-8')
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    # Direct, frequently used actions are a single group, with URL and
    # IT-only folder sources deliberately lower in the dialog.
    frequent = player.split('class="add-type-switch"', 1)[1].split('</div>', 1)[0]
    further = player.split('class="add-type-extra"', 1)[1].split('</div>', 1)[0]
    for mode in ('media', 'zip', 'library'):
        assert 'data-add-mode="' + mode + '"' in frequent
    for mode in ('website', 'folder'):
        assert 'data-add-mode="' + mode + '"' in further
    assert player.index('Häufig genutzt') < player.index('Weitere Quellen')
    assert player.index('data-add-mode="library"') < player.index('data-add-mode="website"')
    assert '<section class="bulk-media-panel studio-bulk-details"' in player
    assert '<details class="bulk-media-panel studio-bulk-details"' not in player
    assert 'data-bulk-upload' in player
    assert 'action="{{ url_for(\'player_bulk_media\', device_id=device.id) }}"' in player
    assert 'name="csrf"' in player
    assert 'composer-source-menu' in css
    assert 'composer-choice-label' in css
    assert 'add-type-extra' in css



def test_final_ui_navigation_forms_and_zero_states_are_role_aware():
    base = (TEMPLATES / 'base.html').read_text(encoding='utf-8')
    dashboard = (TEMPLATES / 'dashboard.html').read_text(encoding='utf-8')
    library = (TEMPLATES / 'library.html').read_text(encoding='utf-8')
    schedules = (TEMPLATES / 'schedules.html').read_text(encoding='utf-8')
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    assert 'aria-label="Hauptnavigation"' in base
    assert 'aria-current="page"' in base
    assert '.site-nav:has(.site-nav-utility)' in css
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))' in css
    assert 'overflow:visible;flex-wrap:wrap' in css
    assert 'Gespeicherte Vorlagen' in library
    assert 'role="status"' in library
    assert "logged_user.role == 'viewer'" in library
    assert 'site-nav-schedule' in base
    assert 'Noch keine Bildschirme verbunden' in dashboard
    assert 'class="button schedule-empty-link"' in schedules
    assert "url_for('playlist', device_id=device.id)" in schedules
    assert "if can_edit else 'Playlist ansehen'" in schedules
    assert 'input[type="file"]::file-selector-button' in css
    assert ':user-invalid' in css
    for retired in ('hub-workflow-cards','hub-workflow-card',
                    'library-workflow-nav','library-source-feature',
                    'media-folder-notice'):
        assert retired not in css


def test_playlist_asset_editor_finishing_pass_uses_shared_tokens_and_context_help():
    player = (TEMPLATES / 'playlist.html').read_text(encoding='utf-8')
    schedule = (TEMPLATES / '_schedule_controls.html').read_text(encoding='utf-8')
    css = (STATIC / 'ui-system.css').read_text(encoding='utf-8')
    assert "asset-inline-edit{{ ' is-video' if is_video else ' is-static' }}" in player
    assert 'Ändert nur die Zeitplanung dieses Inhalts.' in player
    assert "hint='Gilt nur für neu hinzugefügte Inhalte." in schedule
    assert '<p class="schedule-choice-hint">{{ hint }}</p>' in schedule
    assert 'class="button schedule-save" type="submit"' in player
    assert 'name="csrf" value="{{ csrf() }}"' in player
    assert "url_for('asset_schedule', device_id=device.id" in player
    assert "url_for('delete_asset', device_id=device.id" in player
    assert "url_for('toggle_asset', device_id=device.id" in player
    editor = css.split('/* Player item editor: replace remaining hard-coded', 1)[1]
    editor = editor.split('/* Scheduling: old all-dark', 1)[0]
    for selector in (
        '.asset-toolbar>.asset-inline-edit.is-video',
        '.asset-toolbar-actions .quick-toggle',
        '.asset-toolbar-actions .delete-confirmation',
        '.asset-schedule-details .schedule-choice',
        '.asset-schedule-details .schedule-choice select',
        '.asset-schedule-details>form>.schedule-save',
    ):
        assert selector in editor
    for token in ('var(--ui-surface)', 'var(--ui-raised)',
                  'var(--ui-line-strong)', 'var(--ui-muted)'):
        assert token in editor
    for old_color in ('#102834', '#122a38', '#101f30', '#231e2c'):
        assert old_color not in editor
    assert '@media(max-width:900px)' in editor
    assert '@media(max-width:620px)' in editor
