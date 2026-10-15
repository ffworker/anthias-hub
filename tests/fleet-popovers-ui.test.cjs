/* Node-only interaction contract for device side flyouts. No browser/Pi required. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../app/static/fleet-popovers.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '../app/static/workspace.css'), 'utf8');

function harness({width = 1200, height = 800, mobile = false} = {}) {
  const events = {};
  const listeners = (map, name, fn) => {map[name] = fn;};
  const media = {matches:mobile, addEventListener(){}};
  function entry(x, panelHeight = 500) {
    const triggerEvents = {};
    const trigger = {
      getBoundingClientRect(){return {left:x, right:x+124, top:110, bottom:155};},
      focus(){this.focused=true;},
      addEventListener(name, fn){triggerEvents[name]=fn;}
    };
    const classList = {contains(c){return c === 'fleet-remote-body';}};
    const closeEvents = {};
    const closeButton = {addEventListener(name,fn){closeEvents[name]=fn;}};
    const panel = {
      classList, scrollHeight:panelHeight,
      querySelector(selector){return selector==='[data-close-fleet-menu]' ? closeButton : null;},
      style:{
        removeProperty(name){delete this[name];}
      }
    };
    const toggles = {};
    const menu = {
      open:false,children:[trigger,panel],
      querySelector(q){return q === 'summary' ? trigger : null;},
      addEventListener(name,fn){toggles[name]=fn;},
      contains(t){return t===trigger || t===panel;}
    };
    return {menu, trigger, panel, toggle(){toggles.toggle();}, close(){closeEvents.click();}};
  }
  const first=entry(90);
  const last=entry(width-195,900);
  const rootClasses=[];
  const document = {
    querySelectorAll(){return [first.menu,last.menu];},
    documentElement:{classList:{add(x){rootClasses.push(x);}}},
    addEventListener(name,fn){listeners(events,name,fn);}
  };
  const window = {
    innerWidth:width,innerHeight:height,matchMedia(){return media;},
    requestAnimationFrame(fn){fn();},
    addEventListener(name,fn){listeners(events,name,fn);}
  };
  vm.runInNewContext(source, {document,window,console});
  return {first,last,events,window,rootClasses};
}

test('desktop controls open to the right, not as a grid row',()=>{
  const h=harness();
  h.first.menu.open=true;
  h.first.toggle();
  assert.equal(h.first.panel.style.left,'236px');
  assert.equal(h.first.panel.style.width,'312px');
  assert.equal(h.first.panel.style.top,'102px');
  assert.ok(css.includes('.fleet-device-actions>details[open]{grid-column:auto}'));
  assert.ok(css.includes('position:fixed;z-index:1000'));
});

test('rightmost device flips controls to the left and clamps height',()=>{
  const h=harness();
  h.last.menu.open=true;
  h.last.toggle();
  assert.equal(h.last.panel.style.left,'671px');
  assert.equal(h.last.panel.style.top,'12px');
});

test('only one device menu can stay open and clicking outside dismisses it',()=>{
  const h=harness();
  h.first.menu.open=true;h.first.toggle();
  h.last.menu.open=true;h.last.toggle();
  assert.equal(h.first.menu.open,false);
  assert.equal(h.last.menu.open,true);
  h.events.pointerdown({target:{}});
  assert.equal(h.last.menu.open,false);
});

test('Escape closes the menu and restores focus to its trigger',()=>{
  const h=harness();
  h.first.menu.open=true;h.first.toggle();
  let prevented=false;
  h.events.keydown({key:'Escape',preventDefault(){prevented=true;}});
  assert.equal(h.first.menu.open,false);
  assert.equal(h.first.trigger.focused,true);
  assert.equal(prevented,true);
});

test('visible close button closes the flyout and restores focus',()=>{
  const h=harness();
  h.first.menu.open=true;h.first.toggle();
  h.first.close();
  assert.equal(h.first.menu.open,false);
  assert.equal(h.first.trigger.focused,true);
});

test('mobile leaves position to the bottom-sheet CSS',()=>{
  const h=harness({width:390,mobile:true});
  h.first.menu.open=true;h.first.toggle();
  assert.equal(h.first.panel.style.left,undefined);
  assert.equal(h.first.panel.style.top,undefined);
  assert.ok(css.includes('bottom:12px;width:auto!important'));
});

test('library popovers anchor to cards and confirmations stay inside menu',()=>{
  const libraryCss=fs.readFileSync(path.join(__dirname,'../app/static/library.css'),'utf8');
  assert.match(libraryCss,/\.library-item-options-menu\{[\s\S]*?right:12px;left:auto/);
  assert.match(libraryCss,/\.template-options-panel \.template-delete-confirm\{[\s\S]*?position:static/);
});

test('secondary device utilities stay compact and visually subordinate',()=>{
  assert.match(css,/\.fleet-device:has\(\.fleet-device-actions\) \.fleet-open\{[\s\S]*?margin:auto 0 14px!important/);
  assert.match(css,/\.fleet-device-actions>details>summary\{[\s\S]*?min-height:39px/);
  assert.match(css,/\.fleet-device-actions>\.fleet-remote-marketing\{[\s\S]*?width:max-content/);
  assert.match(css,/\.fleet-device-actions>\.fleet-remote-marketing>summary\{[\s\S]*?min-height:36px/);
  assert.match(css,/width:312px;max-width:calc\(100vw - 24px\)/);
  assert.match(source,/const gap = 22;/);
});
