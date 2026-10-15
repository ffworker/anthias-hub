const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../app/static/playlist-bulk.js'),'utf8');

class El {
  constructor() {
    this.handlers={};this.attributes={};this.dataset={};this.checked=false;
    this.disabled=false;this.hidden=false;this.value='';this.textContent='';
    const tokens=new Set();
    this.classList={
      contains:k=>tokens.has(k),add:k=>tokens.add(k),remove:k=>tokens.delete(k),
      toggle:(k,on)=>{if(on)tokens.add(k);else tokens.delete(k)}
    };
  }
  addEventListener(event,fn){(this.handlers[event]??=[]).push(fn)}
  fire(event,extra={}){
    const e={submitter:undefined,prevented:false,preventDefault(){this.prevented=true},...extra};
    for(const fn of this.handlers[event]||[]) fn(e);
    return e;
  }
  getAttribute(name){return this.attributes[name]}
  setAttribute(name,value){this.attributes[name]=value}
}
function start(){
  const choices=[new El(),new El()];
  const toggle=new El(),all=new El(),count=new El(),ack=new El();
  const selected=new El(),clear=new El(),name=new El();
  selected.value='selected';clear.value='all';
  name.attributes.placeholder='Lab Screen';
  const fields={
    '[data-bulk-toggle]':toggle, '[data-bulk-all]':all,
    '[data-bulk-count]':count, '[data-bulk-ack]':ack,
    '[data-bulk-delete-selected]':selected,'[data-bulk-clear-all]':clear,
    '[data-bulk-device-name]':name
  };
  const form=new El();form.querySelector=k=>fields[k];
  const panel=new El(),studio=new El();
  studio.querySelector=k=>({'[data-bulk-management]':panel,'#playlist-bulk-form':form})[k];
  studio.querySelectorAll=k=>k==='[data-bulk-check]'?choices:[];
  const document={querySelector:k=>k==='.playlist-studio-v2[data-can-edit="yes"]'?studio:null};
  let answer=true,asked=[];
  const window={confirm:message=>{asked.push(message);return answer}};
  vm.runInNewContext(source,{document,window,Array},{filename:'playlist-bulk.js'});
  return {choices,toggle,all,count,ack,selected,clear,name,form,studio,asked,
    setConfirm:v=>{answer=v}};
}

test('only explicitly selected items are counted and can be submitted',()=>{
  const s=start();
  assert.equal(s.selected.disabled,true);
  assert.equal(s.clear.disabled,true);
  assert.equal(s.studio.classList.contains('bulk-select-mode'),false);
  s.toggle.fire('click');
  assert.equal(s.studio.classList.contains('bulk-select-mode'),true);
  assert.equal(s.all.hidden,false);
  s.choices[1].checked=true;s.choices[1].fire('change');
  assert.equal(s.count.textContent,'1 ausgewählt');
  assert.equal(s.selected.disabled,true);
  s.ack.checked=true;s.ack.fire('change');
  assert.equal(s.selected.disabled,false);
  s.setConfirm(false);
  assert.equal(s.form.fire('submit',{submitter:s.selected}).prevented,true);
  s.setConfirm(true);
  assert.equal(s.form.fire('submit',{submitter:s.selected}).prevented,false);
  assert.equal(s.asked.some(x=>x.includes('1 ausgewählte Inhalte')),true);
});

test('select all / clear selection and closing select mode',()=>{
  const s=start();s.toggle.fire('click');s.all.fire('click');
  assert.equal(s.count.textContent,'2 ausgewählt – für alle bitte „Ganze Playlist leeren“ verwenden');
  s.ack.checked=true;s.ack.fire('change');
  assert.equal(s.selected.disabled,true); // full clear always requires typed device name
  s.all.fire('click');assert.equal(s.count.textContent,'0 ausgewählt');
  s.toggle.fire('click');
  assert.equal(s.studio.classList.contains('bulk-select-mode'),false);
  assert.equal(s.choices.every(x=>!x.checked),true);
});

test('clearing all requires both acknowledgement and exact device name',()=>{
  const s=start();
  s.name.value='Lab Screen';s.name.fire('input');
  assert.equal(s.clear.disabled,true);
  s.ack.checked=true;s.ack.fire('change');
  assert.equal(s.clear.disabled,false);
  s.name.value='wrong';s.name.fire('input');
  assert.equal(s.clear.disabled,true);
  assert.equal(s.form.fire('submit',{submitter:s.clear}).prevented,true);
  s.name.value='Lab Screen';s.name.fire('input');
  s.setConfirm(false);
  assert.equal(s.form.fire('submit',{submitter:s.clear}).prevented,true);
  s.setConfirm(true);
  assert.equal(s.form.fire('submit',{submitter:s.clear}).prevented,false);
  assert.equal(s.asked.some(x=>x.includes('Alle 2 Inhalte')),true);
});
