/* No extra browser test dependencies: exercise drawer and accordion handlers. */
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../app/static/playlist-studio.js'),'utf8');

class Classes {
  constructor() {this.members=new Set()}
  add(k){this.members.add(k)}
  remove(k){this.members.delete(k)}
  contains(k){return this.members.has(k)}
}
class E {
  constructor() {
    this.events={};this.attributes={};this.dataset={};this.classList=new Classes();
    this.hidden=false;this.inert=false;this.isConnected=true;this.value='';this.defaultValue='';
  }
  addEventListener(name,callback){(this.events[name]??=[]).push(callback)}
  fire(name,options={}){
    const evt={target:this,preventDefault(){this.prevented=true},...options};
    (this.events[name]||[]).forEach(cb=>cb(evt));
    return evt;
  }
  focus(){state.document.activeElement=this}
  setAttribute(name,value){this.attributes[name]=value}
  removeAttribute(name){delete this.attributes[name]}
  getAttribute(name){return this.attributes[name]}
  closest(){return null}
  querySelector(){return null}
  querySelectorAll(){return []}
}
let state;
function setup(){
  state={confirmResponse:true,confirmCount:0};
  const nameOne=new E();nameOne.value='First';nameOne.defaultValue='First';
  const nameTwo=new E();nameTwo.value='Second';nameTwo.defaultValue='Second';
  const secondsOne=new E();secondsOne.value='20';secondsOne.defaultValue='20';
  const secondsTwo=new E();secondsTwo.value='30';secondsTwo.defaultValue='30';
  const editors=[new E(),new E()];
  const buttons=[new E(),new E()];
  const fields=[{name:nameOne,duration:secondsOne},{name:nameTwo,duration:secondsTwo}];
  const cards=[new E(),new E()];
  cards.forEach((card,index)=>{
    const form=new E();
    form.dataset.savedValues=JSON.stringify([fields[index].name.value,fields[index].duration.value]);
    form.querySelector=k=>({'[name="name"]':fields[index].name,'.duration-number':fields[index].duration})[k]??null;
    editors[index].querySelector=k=>k==='input[name="name"]'?fields[index].name:null;
    card.querySelector=k=>({
      '.asset-inline-edit':form,
      '.asset-toolbar':editors[index],
      '.asset-open':buttons[index],
      '.inline-save':new E(),
    })[k]??null;
    card.form=form;
  });
  state.cards=cards;state.buttons=buttons;state.editors=editors;state.fields=fields;
  const backdrop=new E(),drawer=new E(),trigger=new E(),close=new E();
  const studio=new E();studio.dataset.canEdit='yes';
  const input=new E();input.type='text';input.value='';input.defaultValue='';
  drawer.querySelector=k=>k==='[data-close-composer]'?close:null;
  drawer.querySelectorAll=k=>k==='input, textarea, select'?[input]:[];
  studio.querySelector=k=>({'[data-composer-drawer]':drawer,'.composer-backdrop':backdrop})[k]??null;
  studio.querySelectorAll=k=>({
    '.asset[data-asset-id]':cards,
    '[data-open-composer]':[trigger],
    '[data-close-composer]':[close,backdrop],
  })[k]??[];
  const document={body:new E(),activeElement:trigger};
  document.querySelector=k=>k==='.playlist-studio-v2[data-can-edit="yes"]'?studio:null;
  document.addEventListener=function(k,cb){(this.events??={})[k]=cb};
  const window={location:{hash:''},confirm:()=>{state.confirmCount++;return state.confirmResponse}};
  state={...state,document,window,studio,drawer,backdrop,trigger,close,input,cards,buttons,editors,fields,
    sendKey(key,target){const cb=document.events?.keydown;cb?.({key,target,preventDefault(){this.prevented=true}})}
  };
  vm.runInNewContext(source,{window,document,JSON,Number,Math,Array},{filename:'playlist-studio.js'});
  return state;
}

test('Only one card expands; no editor is visible at initial JS load',()=>{
  const s=setup();
  assert.equal(s.studio.classList.contains('js-ready'),true);
  assert.equal(s.editors.every(e=>e.hidden),true);
  s.buttons[0].fire('click');
  assert.equal(s.editors[0].hidden,false);
  assert.equal(s.buttons[0].getAttribute('aria-expanded'),'true');
  s.buttons[1].fire('click');
  assert.equal(s.editors[0].hidden,true);
  assert.equal(s.editors[1].hidden,false);
});
test('Unsaved card edit cannot silently disappear; explicit discard resets fields',()=>{
  const s=setup();
  s.buttons[0].fire('click');
  s.fields[0].name.value='Changed but unsaved';
  s.confirmResponse=false;
  s.buttons[1].fire('click');
  assert.equal(s.editors[0].hidden,false);
  assert.equal(s.editors[1].hidden,true);
  assert.equal(s.confirmCount,1);
  s.confirmResponse=true;
  s.buttons[1].fire('click');
  assert.equal(s.editors[1].hidden,false);
  assert.equal(s.fields[0].name.value,'First');
});
test('Drawer is modal, keyboard Escape closes and focus returns to trigger',()=>{
  const s=setup();
  assert.equal(s.drawer.inert,true);
  const click=s.trigger.fire('click');
  assert.equal(click.prevented,true);
  assert.equal(s.drawer.inert,false);
  assert.equal(s.studio.classList.contains('composer-is-open'),true);
  assert.equal(s.drawer.getAttribute('role'),'dialog');
  assert.equal(s.document.activeElement,s.close);
  s.sendKey('Escape',s.close);
  assert.equal(s.studio.classList.contains('composer-is-open'),false);
  assert.equal(s.drawer.inert,true);
  assert.equal(s.document.activeElement,s.trigger);
});
test('Drawer warns before throwing away typed content',()=>{
  const s=setup();
  s.trigger.fire('click');
  s.input.value='Unsubmitted URL';
  s.confirmResponse=false;
  s.close.fire('click');
  assert.equal(s.studio.classList.contains('composer-is-open'),true);
  s.confirmResponse=true;
  s.close.fire('click');
  assert.equal(s.studio.classList.contains('composer-is-open'),false);
  assert.equal(s.confirmCount,2);
});
