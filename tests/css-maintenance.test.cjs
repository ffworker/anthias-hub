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

test('Nordlicht refinement sheet is last after optional page CSS', () => {
  const styles = ['style.css','modern.css','workspace.css','ui-refinements.css'];
  for (const name of styles) {
    assert.ok(template.includes("filename='" + name + "'"), 'missing ' + name);
  }
  const positions = styles.map(name => template.indexOf("filename='" + name + "'"));
  assert.deepEqual([...positions].sort((a,b) => a-b), positions);
  assert.ok(template.indexOf('{% block extra_head %}') < positions[3],
    'page styles must load before final shared refinements');
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
