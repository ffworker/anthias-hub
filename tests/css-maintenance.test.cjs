/* Guard the stylesheet handoff contract without a browser or CSS dependencies.
 * This is a static sanity check, not a substitute for visual review. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const staticDir = path.join(__dirname, '../app/static');
const template = fs.readFileSync(path.join(__dirname, '../app/templates/base.html'), 'utf8');
const cssFiles = fs.readdirSync(staticDir).filter(name => name.endsWith('.css'));

// Scan braces outside CSS comments and quoted content to catch truncated edits.
// This deliberately does not claim to validate all CSS syntax or browser layout.
function assertBalancedCss(name, css) {
  let depth = 0;
  let quote = '';
  let comment = false;
  for (let i = 0; i < css.length; i++) {
    const c = css[i], next = css[i + 1];
    if (comment) {
      if (c === '*' && next === '/') { comment = false; i++; }
      continue;
    }
    if (quote) {
      if (c === '\\') { i++; continue; }
      if (c === quote) quote = '';
      continue;
    }
    if (c === '/' && next === '*') { comment = true; i++; continue; }
    if (c === '"' || c === "'") { quote = c; continue; }
    if (c === '{') depth++;
    if (c === '}') {
      depth--;
      assert.ok(depth >= 0, name + ': unexpected closing brace');
    }
  }
  assert.equal(depth, 0, name + ': unclosed block');
  assert.equal(quote, '', name + ': unclosed CSS quote');
  assert.equal(comment, false, name + ': unclosed CSS comment');
}

test('every CSS file has balanced rule delimiters', () => {
  for (const name of cssFiles) {
    assertBalancedCss(name, fs.readFileSync(path.join(staticDir, name), 'utf8'));
  }
});

test('single unified UI sheet is last after optional page CSS', () => {
  const styles = ['style.css','modern.css','workspace.css','ui-system.css'];
  for (const name of styles) {
    assert.ok(template.includes("filename='" + name + "'"), 'missing ' + name);
  }
  const positions = styles.map(name => template.indexOf("filename='" + name + "'"));
  assert.deepEqual([...positions].sort((a,b) => a-b), positions);
  assert.ok(template.indexOf('{% block extra_head %}') < positions[3],
    'page styles must load before unified UI');
});

test('removed theme switching and obsolete website tab styles stay gone', () => {
  assert.ok(!cssFiles.includes('themes.css'), 'retired themes.css should not return');
  assert.ok(!fs.existsSync(path.join(staticDir,'theme-init.js')));
  assert.ok(!fs.existsSync(path.join(staticDir,'themes.js')));
  assert.doesNotMatch(template, /theme-picker|data-theme-choice|themes\.css/);
  const all = cssFiles.map(name => fs.readFileSync(path.join(staticDir,name),'utf8')).join('\n');
  assert.doesNotMatch(all, /\.theme-options\b|\.add-mode-secondary\b/);
});

test('device and library actions retain guarded responsive positioning', () => {
  const device = fs.readFileSync(path.join(staticDir,'workspace.css'),'utf8');
  const library = fs.readFileSync(path.join(staticDir,'library.css'),'utf8');
  assert.match(device, /\.fleet-device-actions>details\[open\]\{grid-column:auto\}/);
  assert.match(device, /\.fleet-device-actions>\.fleet-remote-marketing\{[\s\S]*?width:max-content/);
  assert.match(device, /\.fleet-device-actions>details>summary\{[\s\S]*?min-height:39px/);
  assert.match(library, /\.library-item-options-menu\{[\s\S]*?right:12px;left:auto/);
  assert.match(library, /\.template-options-panel \.template-delete-confirm\{[\s\S]*?position:static/);
});

test('template publishing keeps target, schedule and actions together at narrow widths', () => {
  const detail = fs.readFileSync(path.join(__dirname,'../app/templates/library_detail.html'),'utf8');
  const library = fs.readFileSync(path.join(staticDir,'library.css'),'utf8');
  const refinements = fs.readFileSync(path.join(staticDir,'ui-system.css'),'utf8');
  assert.match(detail, /class="library-publish-fields"/);
  assert.match(detail, /class="library-publish-target schedule-choice"/);
  assert.match(detail, /class="library-publish-actions"/);
  assert.match(library, /\.library-publish-fields\{[\s\S]*?grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(library, /@media\(max-width:640px\)\{[\s\S]*?\.library-publish-fields\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(library, /\.library-publish-form\{\s*display:grid;\s*grid-template-columns:minmax\(0,1fr\)/);
  assert.match(refinements, /\.library-publish-target select/);
  assert.doesNotMatch(library, /\.library-publish-form\{\s*display:grid;\s*grid-template-columns:minmax\(0,1fr\) auto/);
});

test('only canonical UI sheet is loaded; no redundant layered themes', () => {
  assert.match(template, /filename='ui-system\.css'/);
  for (const retired of ['ui-refinements.css', 'product-ui.css', 'workflow-ui.css']) {
    assert.ok(!template.includes("filename='" + retired + "'"), 'still loading ' + retired);
  }
  assert.ok(template.includes('name="anthias-hub-ui" content="{{ ui_revision }}"'));
  assert.ok(template.includes('name="anthias-hub-build" content="{{ hub_build_sha or'));
  assert.ok(template.includes("filename='ui-system.css', v=ui_revision"));
  const release = fs.readFileSync(path.join(__dirname, '../app/version.py'), 'utf8');
  assert.match(release, /UI_REVISION = "ui-20261112-06"/);
});

test('primary page content precedes secondary administration and disclosures', () => {
  const root = path.join(__dirname, '../app/templates');
  const dashboard = fs.readFileSync(path.join(root, 'dashboard.html'), 'utf8');
  const library = fs.readFileSync(path.join(root, 'library.html'), 'utf8');
  const detail = fs.readFileSync(path.join(root, 'library_detail.html'), 'utf8');
  const sources = fs.readFileSync(path.join(root, 'media_sources.html'), 'utf8');
  const ui = fs.readFileSync(path.join(staticDir, 'ui-system.css'), 'utf8');
  assert.ok(dashboard.indexOf('id="fleet-devices"') < dashboard.indexOf('class="hub-next-steps"'),
    'device cards must appear before secondary tasks');
  assert.doesNotMatch(dashboard, /hub-workflow-cards/, 'do not block devices with onboarding cards');
  assert.match(library, /class="library-intro library-index-intro"/);
  assert.match(library, /id="new-playlist" data-library-drawer-pane="create"/);
  assert.match(library, /id="backup-zip" data-library-drawer-pane="backup"/);
  assert.doesNotMatch(library, /library-action-disclosure/);
  assert.ok(detail.indexOf('class="library-intro library-template-intro"') <
            detail.indexOf('class="folder-workflow"'),
    'template identity precedes folder importer details');
  assert.ok(detail.indexOf('id="library-edit-tools"') <
            detail.indexOf('id="network-settings"'),
    'content tools precede IT source controls');
  assert.ok(sources.indexOf('class="card library-panel media-default-panel') <
            sources.indexOf('class="media-overview-strip"'),
    'primary SMB library precedes auxiliary counters');
  assert.match(sources, /class="media-folder-peek" aria-labelledby="media-folders-heading"/);
  assert.match(ui, /\.hub-next-steps-grid/);
  assert.match(template, /filename='ui-navigation\.js'/);
});


test('mobile header navigation has visible touch-friendly tabs', () => {
  const css = fs.readFileSync(path.join(staticDir, 'ui-system.css'), 'utf8');
  const required = [
    '.site-nav:has(.site-nav-utility)',
    'grid-template-columns:repeat(2,minmax(0,1fr))',
    'overflow:visible;flex-wrap:wrap',
    '.site-nav-link',
    'min-height:44px',
  ];
  for (const token of required) assert.ok(css.includes(token), 'missing '+token);
  const retired = ['hub-workflow-card', 'library-workflow-nav',
                   'library-source-feature', 'media-folder-notice'];
  for (const token of retired) {
    assert.ok(!css.includes(token), 'dead stylesheet selector '+token);
  }
});


test('inline asset editor uses shared theme variables and separate schedule action', () => {
  const css = fs.readFileSync(path.join(staticDir, 'ui-system.css'), 'utf8');
  const player = fs.readFileSync(path.join(__dirname, '../app/templates/playlist.html'), 'utf8');
  assert.match(css, /\.asset-toolbar>\.asset-inline-edit\.is-video/);
  assert.match(css, /\.asset-schedule-details \.schedule-choice\{/);
  assert.match(css, /\.asset-schedule-details>form>\.schedule-save/);
  assert.match(css, /html\[data-theme="light"\][^\n]*input\[type="time"\]/);
  assert.match(css, /html\[data-theme="dark"\][^\n]*input\[type="time"\]/);
  assert.match(player, /class="button schedule-save" type="submit"/);
});
