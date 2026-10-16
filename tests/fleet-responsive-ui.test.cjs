/* Browser feedback contracts for async dashboard + native long-form transfer. */
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const source = name => fs.readFileSync(
  path.join(__dirname, '..', 'app', 'static', name), 'utf8'
);
const tick = async() => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};

test('dashboard reports each real Pi count separately and fetches storage only on open', async () => {
  const calls = [];
  const handlers = {};
  const elems = {};
  for (const name of ['online', 'offline']) elems[name] = {textContent:'–'};
  const createCard = (slug, count) => {
    const badge = {textContent:'Wird geprüft', classList:{
      current:new Set(['off']), add(x){this.current.add(x)}, remove(...xs){xs.forEach(x=>this.current.delete(x))}
    }};
    const label = {textContent:'–'};
    const menuFields = {};
    for (const key of ['message','values','warning','reported','budget','reserve']) {
      menuFields[key] = {textContent:'',hidden:key==='values'||key==='warning'};
    }
    const menu = {
      dataset:{storageUrl:'/devices/'+slug+'/storage'},
      open:false,
      addEventListener(name, fn){this[name]=fn},
      querySelector(key){return ({
        '[data-storage-message]':menuFields.message,
        '[data-storage-values]':menuFields.values,
        '[data-storage-warning]':menuFields.warning,
        '[data-storage-reported]':menuFields.reported,
        '[data-storage-budget]':menuFields.budget,
        '[data-storage-reserve]':menuFields.reserve
      })[key]}
    };
    const card = {
      dataset:{overviewUrl:'/devices/'+slug+'/overview',overviewState:'pending'},
      classList:{add(){},remove(){}},
      querySelector(key){return ({
        '[data-device-state]':badge, '[data-device-count]':label,
        '.fleet-storage-menu[data-storage-url]':menu
      })[key]}
    };
    return {card,badge,label,menu,menuFields};
  };
  const a=createCard('pi3',4),b=createCard('pi5',9);
  const document = {
    querySelectorAll(){return [a.card,b.card]},
    querySelector(key){return ({
      '[data-fleet-online]':elems.online,
      '[data-fleet-offline]':elems.offline
    })[key]}
  };
  const fetch = async url => {
    calls.push(url);
    if (url.includes('/overview')) return {
      ok:true,json:async()=>url.includes('pi3')
        ? {ok:true,count:4}:{ok:true,count:9}
    };
    return {ok:true,json:async()=>({
      ok:true,reported:'19.4 GB',usable_bytes:8*1024**3,
      usable_gib:'8.0',reserve_gib:'3.0'
    })};
  };
  vm.runInNewContext(source('fleet-status.js'),{document,fetch});
  await tick();
  assert.deepEqual(calls,['/devices/pi3/overview','/devices/pi5/overview']);
  assert.equal(elems.online.textContent,'2');
  assert.equal(elems.offline.textContent,'0');
  assert.equal(a.label.textContent,'4');
  assert.equal(b.label.textContent,'9');
  b.menu.open=true;b.menu.toggle();
  await tick();
  assert.equal(calls.length,3);
  assert.equal(b.menuFields.reported.textContent,'19.4 GB');
  assert.equal(b.menuFields.values.hidden,false);
});

test('template transfer keeps native POST and shows observed player count, not fake percent',async()=>{
  let submit;
  const button={disabled:false,dataset:{},textContent:'Übertragen'};
  const box={hidden:true};
  const msg={textContent:''};
  const live={textContent:''};
  const form = {
    dataset:{transferDeviceId:'pi3',transferOverviewPath:'/devices/__DEVICE__/overview'},
    querySelector(key){return ({
      '[data-transfer-feedback]':box,
      '[data-transfer-message]':msg,
      '[data-transfer-live]':live,
      'button[type="submit"], button.primary':button
    })[key]},
    reportValidity(){return true},
    addEventListener(type,cb){if(type==='submit')submit=cb}
  };
  const intervals=[];
  const window={
    addEventListener(){},
    setInterval(fn){intervals.push(fn);return 1},
    clearInterval(){}
  };
  const urls=[];
  const fetch=async url=>{
    urls.push(url);
    return {ok:true,json:async()=>({ok:true,count:7})};
  };
  const document={querySelectorAll(){return [form]}};
  vm.runInNewContext(source('template-transfer.js'),{document,window,fetch});
  const event={prevented:false,preventDefault(){this.prevented=true}};
  submit(event);
  assert.equal(event.prevented,false); // Preserve original POST/redirect/flash.
  assert.equal(button.disabled,true);
  assert.equal(box.hidden,false);
  assert.match(msg.textContent,/übertragen/i);
  await tick();
  assert.deepEqual(urls,['/devices/pi3/overview']);
  assert.match(live.textContent,/7 Playlist-Inhalte/);
  assert.doesNotMatch(live.textContent,/%/);
  const duplicate={prevented:false,preventDefault(){this.prevented=true}};
  submit(duplicate);
  assert.equal(duplicate.prevented,true);
  assert.equal(urls.length,1);
  assert.equal(intervals.length,1);
});
