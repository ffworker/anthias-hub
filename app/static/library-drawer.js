/* Progressive template composer: no-JS forms remain available below the list. */
(() => {
 'use strict';
 const root=document.querySelector('[data-library-workspace]');
 const drawer=root?.querySelector('[data-library-drawer]');
 const backdrop=root?.querySelector('.library-drawer-backdrop');
 if(!root||!drawer||!backdrop)return;
 const panes=[...drawer.querySelectorAll('[data-library-drawer-pane]')],tabs=[...drawer.querySelectorAll('[data-library-drawer-tab]')];
 const addPanes=[...drawer.querySelectorAll('[data-library-add-pane]')],addTabs=[...drawer.querySelectorAll('[data-library-add-tab]')];
 const baseline=new Map();let previousFocus=null;
 drawer.querySelectorAll('input,select,textarea').forEach(field=>{
  if(field.type!=='hidden'&&field.type!=='submit')baseline.set(field,
    (field.type==='checkbox'||field.type==='radio')?field.checked:field.value);
 });
 const dirty=()=>[...baseline].some(([field,value])=>field.type==='file'?Boolean(field.files?.length):
   ((field.type==='checkbox'||field.type==='radio')?field.checked:field.value)!==value);
 function selectAdd(mode){
  if(!addPanes.some(x=>x.dataset.libraryAddPane===mode))return;
  addPanes.forEach(x=>x.hidden=x.dataset.libraryAddPane!==mode);
  addTabs.forEach(x=>{let on=x.dataset.libraryAddTab===mode;x.classList.toggle('selected',on);x.setAttribute('aria-pressed',String(on))});
 }
 function selectPane(mode){
  if(!panes.some(x=>x.dataset.libraryDrawerPane===mode))return false;
  panes.forEach(x=>x.hidden=x.dataset.libraryDrawerPane!==mode);
  tabs.forEach(x=>{let on=x.dataset.libraryDrawerTab===mode;x.classList.toggle('selected',on);x.setAttribute('aria-pressed',String(on))});
  const labels={add:['Inhalt hinzufügen','Medien oder Webseiten in die Vorlage speichern.'],apply:['Auf Bildschirm anwenden','Vorlage bewusst auf einen Bildschirm übertragen.'],settings:['Quelle & Zielgeräte','IT-Konfiguration und Netzwerkzuordnung.'],more:['Weitere Optionen','Backup und seltene Verwaltungsaktionen.'],create:['Neue Playlist','Eine neue Hub-Vorlage erstellen, ohne laufende Bildschirme zu verändern.'],backup:['Backup importieren','Nur bereits exportierte Hub-Vorlagenbackups wiederherstellen.']};
  drawer.querySelector('#library-drawer-title').textContent=labels[mode][0];
  drawer.querySelector('[data-library-drawer-description]').textContent=labels[mode][1];
  return true;
 }
 function open(mode,trigger){
  if(!selectPane(mode))return;
  if(!root.classList.contains('library-drawer-open'))previousFocus=trigger||document.activeElement;
  root.classList.add('library-drawer-open');backdrop.hidden=false;drawer.inert=false;
  drawer.removeAttribute('aria-hidden');drawer.setAttribute('role','dialog');drawer.setAttribute('aria-modal','true');
  document.body.classList.add('studio-drawer-open');drawer.querySelector('[data-close-library-drawer]')?.focus();
 }
 function close(){
  if(!root.classList.contains('library-drawer-open'))return;
  if(dirty()&&!window.confirm('Nicht gespeicherte Eingaben oder ausgewählte Dateien verwerfen?'))return;
  root.classList.remove('library-drawer-open');backdrop.hidden=true;drawer.inert=true;drawer.setAttribute('aria-hidden','true');
  drawer.removeAttribute('role');drawer.removeAttribute('aria-modal');document.body.classList.remove('studio-drawer-open');
  if(previousFocus?.isConnected)previousFocus.focus();
 }
 root.querySelectorAll('[data-open-library-drawer]').forEach(el=>el.addEventListener('click',e=>{e.preventDefault();open(el.dataset.openLibraryDrawer,el)}));
 tabs.forEach(el=>el.addEventListener('click',()=>selectPane(el.dataset.libraryDrawerTab)));
 addTabs.forEach(el=>el.addEventListener('click',()=>selectAdd(el.dataset.libraryAddTab)));
 root.querySelectorAll('[data-close-library-drawer]').forEach(el=>el.addEventListener('click',close));
 document.addEventListener('keydown',e=>{
  if(!root.classList.contains('library-drawer-open'))return;
  if(e.key==='Escape'){e.preventDefault();close();return}
  if(e.key!=='Tab')return;
  const focusable=[...drawer.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary')]
    .filter(x=>!x.closest('[hidden]')&&x.getClientRects().length);
  if(!focusable.length){e.preventDefault();drawer.focus();return}
  const first=focusable[0],last=focusable[focusable.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
 });
 function openHash(){
  const mode={'#library-edit-tools':'add','#playlist-anwenden':'apply','#network-settings':'settings','#library-more':'more','#new-playlist':'create','#backup-zip':'backup'}[location.hash];
  if(mode)open(mode,root.querySelector('[data-open-library-drawer="'+mode+'"]'));
 }
 if(addPanes.length)selectAdd(addPanes[0].dataset.libraryAddPane);
 selectPane(panes[0].dataset.libraryDrawerPane);
 drawer.inert=true;drawer.setAttribute('aria-hidden','true');root.classList.add('library-drawer-ready');
 openHash();window.addEventListener('hashchange',openHash);
})();
