/* Verify multiple 500 MiB browser Files are submitted as individual requests,
 * without allocating gigabytes or weakening the server's Pi-space guard.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname,'../app/static/bulk-upload.js'),'utf8');

function harness(failAt=0) {
  const sent=[];
  const createElement=()=>({
    textContent:'',className:'',hidden:false,dataset:{},
    children:[],append(...nodes){this.children.push(...nodes)},
    appendChild(node){this.children.push(node);return node},
    replaceChildren(){this.children=[]},addEventListener(){},
    style:{width:'0%'}
  });
  const parts={};
  const map={'input[type="file"][name="media"]':'input','button[type="submit"]':'submit',
    '[data-bulk-cancel]':'cancel','[data-bulk-selected]':'selected',
    '[data-bulk-progress]':'progress','[data-bulk-progress-bar]':'bar',
    '[data-bulk-progress-text]':'progressText','[data-bulk-report]':'report'};
  for(const name of Object.values(map))parts[name]=createElement();
  parts.input.files=Array.from({length:5},(_,i)=>({name:'movie-'+i+'.mp4',size:500*1024*1024}));
  parts.submit.textContent='Import starten';
  const listeners={};
  const form={action:'http://hub.local/devices/lab/bulk-media',reportValidity:()=>true,
    querySelector(selector){return parts[map[selector]]||null},
    addEventListener(name,callback){listeners[name]=callback}};
  class FakeFormData{
    constructor(){this.entries=[]}
    delete(name){this.entries=this.entries.filter(e=>e[0]!==name)}
    append(name,value){this.entries.push([name,value])}
  }
  class FakeXHR{
    constructor(){this.upload={addEventListener(){}};this.timeout=0}
    open(method,url){this.method=method;this.url=url}
    setRequestHeader(){}
    send(data){
      const entries=data.entries.filter(e=>e[0]==='media');
      sent.push(entries);
      const file=entries[0][1];
      this.status=200;
      const failed=failAt===sent.length;
      this.responseText=JSON.stringify({ok:!failed,results:[{
        name:file.name,status:failed?'failed':'imported',
        message:failed?'No room on Pi':'Done'}],redirect:'/devices/lab'});
      this.onload();
    }
    abort(){this.onabort?.()}
  }
  const context={window:{XMLHttpRequest:FakeXHR,AnthiasStorage:{refresh:async()=>({usable_bytes:5*1024**3})}},
    XMLHttpRequest:FakeXHR,FormData:FakeFormData,
    document:{querySelectorAll:()=>[form],createElement,createTextNode:text=>({textContent:text})}};
  vm.runInNewContext(script,context);
  return {sent,parts,listeners};
}
test('five 500-MiB videos result in five distinct bounded requests',async()=>{
  const h=harness();
  await h.listeners.submit({preventDefault(){}});
  assert.equal(h.sent.length,5);
  for (const sent of h.sent) {
    assert.equal(sent.length,1);
    assert.equal(sent[0][1].size,500*1024*1024);
  }
  assert.equal(h.parts.submit.disabled,false);
  assert.equal(h.parts.cancel.hidden,true);
  assert.equal(h.parts.report.dataset.state,'success');
});
test('failed second video stops queue and frees UI without resending',async()=>{
  const h=harness(2);
  await h.listeners.submit({preventDefault(){}});
  assert.equal(h.sent.length,2);
  assert.equal(h.parts.submit.disabled,false);
  assert.equal(h.parts.cancel.hidden,true);
  assert.equal(h.parts.report.dataset.state,'partial');
  assert.match(h.parts.report.children[0].textContent,/3 nicht versucht/);
});
