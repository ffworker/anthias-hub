/* Dependency-free browser interaction simulation for playlist.js.
 * Run with: node --test tests/playlist-ui.test.cjs */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '../app/static/playlist.js'), 'utf8');

class Classes {
  constructor() { this.items = new Set(); }
  add(...names) { names.forEach(n => this.items.add(n)); }
  remove(...names) { names.forEach(n => this.items.delete(n)); }
  contains(n) { return this.items.has(n); }
  toggle(name, force) {
    if (force === undefined) force = !this.items.has(name);
    if (force) this.items.add(name); else this.items.delete(name);
    return force;
  }
}
class Element {
  constructor() {
    this.dataset = {};
    this.attributes = new Map();
    this.classList = new Classes();
    this.listeners = new Map();
    this.textContent = '';
    this.disabled = false;
  }
  addEventListener(type, cb) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(cb);
  }
  fire(type, props = {}) {
    const event = { target: this, preventDefault() { this.prevented = true; }, ...props };
    for (const cb of (this.listeners.get(type) || [])) cb(event);
    return event;
  }
  setAttribute(k,v) { this.attributes.set(k,String(v)); }
  getAttribute(k) { return this.attributes.get(k); }
  matches() { return false; }
  closest() { return null; }
}
class Input extends Element {
  constructor(value, kind) { super(); this.value=value; this.kind=kind; }
  matches(selector) {
    return this.kind === 'name' && selector === '.asset-inline-edit input[name="name"]';
  }
  closest(selector) {
    return selector === '.asset' ? this.card : null;
  }
}
class Form extends Element {
  constructor(card) {
    super(); this.card=card; this.action='/edit';
    this.nameInput = new Input(card.name.textContent,'name');
    this.durationInput = new Input('15','duration');
    this.stateInput = new Input('on','state');
    this.nameInput.card=card;
    this.durationInput.card=card;
    this.stateInput.card=card;
  }
  querySelector(selector) {
    return selector === '[name="name"]' ? this.nameInput :
      selector === '.duration-number' ? this.durationInput :
      selector === '[name="enabled"]' ? this.stateInput : null;
  }
  matches(selector) { return selector === '.asset-edit'; }
  closest(selector) { return selector === '.asset' ? this.card : null; }
}
class Grip extends Element {
  constructor(card) { super(); this.card=card; this.draggable=true; this.captured=false; }
  closest(selector) { return selector === '.drag-handle' ? this : selector === '.asset' ? this.card : null; }
  focus() { this.card.env.document.activeElement=this; }
  setPointerCapture() { this.captured=true; }
  hasPointerCapture() { return this.captured; }
  releasePointerCapture() { this.captured=false; }
}
class Card extends Element {
  constructor(id, env) {
    super();
    this.env=env; this.dataset.assetId=id; this.dataset.enabled='1';
    this.name = new Element(); this.name.textContent=id;
    this.index = new Element();
    this.duration = new Element();
    this.status = new Element();
    this.handle = new Grip(this);
    this.form = new Form(this);
    this.save = new Element();
    this.saved = new Element();
    this.preview = null;
  }
  closest(sel) { return sel === '.asset' ? this : null; }
  get nextSibling() {
    const index=this.env.stack.children.indexOf(this);
    return this.env.stack.children[index+1] || null;
  }
  getBoundingClientRect() {
    const index=this.env.stack.children.indexOf(this);
    return { top:100+index*110, height:95, bottom:195+index*110 };
  }
  querySelector(s) {
    return ({
      '.asset-name':this.name,
      '.asset-index':this.index,
      '.drag-handle':this.handle,
      '.asset-inline-edit':this.form,
      '.asset-toolbar-actions .inline-save':this.save,
      '.save-indicator':this.saved,
      '.asset-duration':this.duration,
      '.asset-status':this.status,
      '.asset-inline-edit [name="enabled"]':this.form.stateInput,
      '.quick-toggle-form':null,
      '[data-media-lightbox]':this.preview,
    })[s] ?? null;
  }
}
class Stack extends Element {
  constructor(env) { super(); this.env=env; this.children=[]; }
  querySelectorAll(selector) {
    if (selector === '.asset[data-asset-id]') return this.children.slice();
    if (selector === '.drag-handle') return this.children.map(c=>c.handle);
    if (selector === '.delete-panel form') return [];
    return [];
  }
  insertBefore(card, after) {
    this.children=this.children.filter(c=>c!==card);
    const i=after ? this.children.indexOf(after) : -1;
    if(i<0)this.children.push(card);else this.children.splice(i,0,card);
  }
  appendChild(card) { this.insertBefore(card,null); }
  getBoundingClientRect() {
    return {top:90,bottom:100+this.children.length*110,height:this.children.length*110};
  }
}
class FormDataStub {
  constructor(form) {
    this.rows=[];
    if(form instanceof Form) {
      this.append('name', form.nameInput.value);
      this.append('duration', form.durationInput.value);
      this.append('enabled', form.stateInput.value);
    }
  }
  append(name,value) { this.rows.push([name,value]); }
  getAll(name){return this.rows.filter(x=>x[0]===name).map(x=>x[1]);}
}
const settle = () => new Promise(resolve=>setImmediate(resolve));

function setup(ids=['a','b','c']) {
  const env={};
  const document={activeElement:null};
  env.document=document;
  env.stack=new Stack(env);
  env.cards=ids.map(id=>new Card(id,env));
  env.stack.children=env.cards.slice();
  env.queue=new Element();
  env.queue.dataset.csrf='testcsrf';
  env.queue.dataset.reorderUrl='/reorder';
  env.workspace=new Element();
  env.feedback=new Element();env.feedback.hidden=true;
  env.active=new Element();env.status=new Element();
  env.requests=[];
  env.nextReorderError=false;
  const byId={'playlist-queue':env.queue,'playlist-items':env.stack,
    'playlist-feedback':env.feedback,'active-count':env.active,
    'playlist-sort-status':env.status};
  document.querySelector=s=>s==='.playlist-workspace[data-can-edit="yes"]'?env.workspace:null;
  document.getElementById=id=>byId[id]??null;
  document.querySelectorAll=()=>[];
  const window={innerHeight:760,setTimeout:()=>11,clearTimeout:()=>{},
    scrollBy:()=>{},confirm:()=>true};
  const fetch=async (url, opts) => {
    env.requests.push({url,payload:opts.body});
    if(url==='/reorder') {
      if(env.nextReorderError) {
        env.nextReorderError=false;
        return {ok:false,json:async()=>({ok:false,error:'Reihenfolge veraltet'})};
      }
      return {ok:true,json:async()=>({ok:true,ids:opts.body.getAll('ids')})};
    }
    if(url==='/edit') {
      return {ok:true,json:async()=>({ok:true,asset:{
        name:opts.body.getAll('name')[0],
        duration:Number(opts.body.getAll('duration')[0]),
        is_enabled:true}})};
    }
    throw Error('Unexpected request '+url);
  };
  vm.runInNewContext(source,{
    document,window,fetch,
    HTMLInputElement:Input,HTMLFormElement:Form,
    FormData:FormDataStub, Math, Promise,
  },{filename:'playlist.js'});
  env.order=()=>env.stack.children.map(c=>c.dataset.assetId);
  env.key=(grip,key)=>env.stack.fire('keydown',{target:grip,key});
  env.pointer=(type,grip,y)=>env.stack.fire(type,{target:grip,
    pointerType:'touch',isPrimary:true,pointerId:1,clientX:10,clientY:y});
  return env;
}

test('keyboard Space, arrows and Enter commit one optimistic reorder',async()=>{
  const e=setup();
  const grip=e.cards[0].handle;
  e.key(grip,' ');
  assert.equal(grip.getAttribute('aria-pressed'),'true');
  e.key(grip,'ArrowDown');
  assert.deepEqual(e.order(),['b','a','c']);
  assert.equal(e.document.activeElement,grip);
  e.key(grip,'Enter');
  await settle();
  assert.equal(grip.getAttribute('aria-pressed'),'false');
  assert.equal(e.requests.length,1);
  assert.deepEqual(e.requests[0].payload.getAll('baseline'),['a','b','c']);
  assert.deepEqual(e.requests[0].payload.getAll('ids'),['b','a','c']);
  assert.match(e.status.textContent,/gespeichert/);
});
test('Escape restores keyboard preview and never writes to player',async()=>{
  const e=setup(),grip=e.cards[2].handle;
  e.key(grip,' ');
  e.key(grip,'ArrowUp');
  assert.deepEqual(e.order(),['a','c','b']);
  e.key(grip,'Escape');
  await settle();
  assert.deepEqual(e.order(),['a','b','c']);
  assert.equal(e.requests.length,0);
  assert.equal(grip.getAttribute('aria-pressed'),'false');
});
test('touch drag moves only after threshold and saves once',async()=>{
  const e=setup(),grip=e.cards[2].handle;
  e.pointer('pointerdown',grip,330);
  assert.equal(grip.draggable,false);
  e.pointer('pointermove',grip,325);
  e.pointer('pointerup',grip,325);
  await settle();
  assert.equal(e.requests.length,0);
  e.pointer('pointerdown',grip,330);
  e.pointer('pointermove',grip,118);
  e.pointer('pointerup',grip,118);
  await settle();
  assert.equal(grip.draggable,true);
  assert.deepEqual(e.order(),['c','a','b']);
  assert.deepEqual(e.requests[0].payload.getAll('ids'),['c','a','b']);
});
test('pointercancel aborts without any POST',async()=>{
  const e=setup(),grip=e.cards[1].handle;
  e.pointer('pointerdown',grip,225);
  e.pointer('pointermove',grip,120);
  e.pointer('pointercancel',grip,120);
  await settle();
  assert.deepEqual(e.order(),['a','b','c']);
  assert.equal(e.requests.length,0);
});
test('stale server baseline restores original DOM and announces failure',async()=>{
  const e=setup(),grip=e.cards[0].handle;
  e.nextReorderError=true;
  e.key(grip,' ');e.key(grip,'ArrowDown');e.key(grip,'Enter');
  await settle();
  assert.deepEqual(e.order(),['a','b','c']);
  assert.equal(e.requests.length,1);
  assert.match(e.status.textContent,/wiederhergestellt/);
});
test('native mouse drag uses same commit and baseline',async()=>{
  const e=setup(),handle=e.cards[2].handle;
  const dataTransfer={effectAllowed:'',setData(){},dropEffect:''};
  handle.fire('dragstart',{dataTransfer});
  e.stack.fire('dragover',{target:e.cards[0],clientY:112,dataTransfer});
  e.stack.fire('drop',{target:e.cards[0],clientY:110,dataTransfer});
  await settle();
  assert.deepEqual(e.order(),['c','a','b']);
  assert.equal(e.requests.length,1);
});
test('Save only enabled on changed title, and disabled after save',async()=>{
  const e=setup(),card=e.cards[0];
  assert.equal(card.save.disabled,true);
  card.form.nameInput.value='New item title';
  e.stack.fire('input',{target:card.form.nameInput});
  assert.equal(card.save.disabled,false);
  e.stack.fire('submit',{target:card.form});
  await settle();
  assert.equal(card.save.disabled,true);
  assert.equal(card.name.textContent,'New item title');
  assert.match(card.saved.textContent,/Gespeichert/);
});
