/* Shared reference/technique note, selection and explicit-copy experience. */
window.ReferenceNotes=(()=>{
 const panels=new Map(),drafts=new Map(),requests=new Map();let detail=null,selectionPanels=[],selectionRun=0,copyBusy=false,slides={};
 try{const raw=JSON.parse(localStorage.getItem('ai-video-studio-reference-drafts-v2')||'{}');for(const [k,v] of Object.entries(raw))if(v&&typeof v.text==='string')drafts.set(k,{...v,time:typeof v.time==='number'&&Number.isFinite(v.time)?v.time:null,focus:typeof v.focus==='string'?v.focus:''});}catch{}
 try{slides=JSON.parse(localStorage.getItem('ai-video-studio-reference-slides-v1')||'{}');}catch{}
 if(!slides||typeof slides!=='object'||Array.isArray(slides))slides={};
 const key=t=>JSON.stringify([t.reference_id,t.example_id,t.slide]);
 const token=t=>t.reference_id+(t.example_id?'@'+t.example_id:'');
 const draft=p=>drafts.get(key(p.target))||{text:'',time:null,focus:''};
 const hasDraft=p=>!!(draft(p).text?.trim()||draft(p).focus?.trim()||draft(p).time!==null);
 const applicable=p=>(p.data?.notes||[]).filter(n=>n.slide===null||n.slide===p.target.slide);
 function remember(){try{localStorage.setItem('ai-video-studio-reference-drafts-v2',JSON.stringify(Object.fromEntries(drafts)));}catch{}}
 function retain(){for(const [el,p] of panels){if(!el.isConnected){panels.delete(el);continue;}if(p.combined?!$('#brief-dialog').open:!$('#style-dialog').open||$('#brief-dialog').open)continue;const text=p.el.querySelector('[data-borrow-note]'),focus=p.el.querySelector('[data-borrow-focus]');if(text){const d={...draft(p),text:text.value,contextRevision:draft(p).contextRevision||p.data?.context_revision};if(focus)d.focus=focus.value;drafts.set(key(p.target),d);}}remember();}
 function currentTarget(){
  if(!active)return null;
  const x=isTech(active)?example(active,false):null;
  const slide=isCarousel(active)?Number($('#detail-media').dataset.slideIndex)+1:null;
  return {reference_id:active.id,example_id:x?.id||null,slide};
 }
 function targetFor(id,exampleId=null){
  const e=item(id);return {reference_id:id,example_id:isTech(e)?exampleId||example(e,false).id:null,
   slide:isCarousel(e)&&Number.isInteger(slides[id])?slides[id]:null};
 }
 async function reply(response){
  if(!response.headers.get('Content-Type')?.includes('application/json'))throw Error(I18N.t('referenceNotes.error.network'));
  const value=await response.json();if(!response.ok)throw Error(I18N.server(value.error)||I18N.t('referenceNotes.error.unavailable'));return value;
 }
 async function load(t){const params=new URLSearchParams({id:t.reference_id});if(t.example_id)params.set('example',t.example_id);return reply(await fetch('/reference-notes?'+params,{cache:'no-store'}));}
 function scope(p){const d=draft(p);return d.time!==null?I18N.t('referenceNotes.scope.noteTime',{time:exact(d.time)}):p.target.slide?I18N.t('referenceNotes.scope.slide',{n:p.target.slide}):p.data?.example_id?I18N.t('referenceNotes.scope.selectedExample',{start:exact(p.data.start),end:exact(p.data.end)}):I18N.t('referenceNotes.scope.wholeReference');}
 function notePosition(n){return n.time!==null?I18N.t('referenceNotes.position.at',{time:exact(n.time)}):n.slide?I18N.t('referenceNotes.scope.slide',{n:n.slide}):I18N.t('referenceNotes.scope.wholeReference');}
 function cards(notes,p){return notes.map(n=>'<article class="reference-saved-note"><span>'+esc(notePosition(n))+(n.focus?' · '+esc(n.focus):'')+'</span><p>'+esc(n.text)+'</p>'+(n.time!==null&&!p.combined?'<button class="text-button" data-note-seek="'+n.time+'">'+esc(I18N.t('referenceNotes.actions.viewMoment'))+'</button>':'')+'</article>').join('');}
 async function legacyFor(t){
  const old=referenceNotes?.[token(t)];if(!old||typeof old!=='object')return null;
  const value={focus:typeof old.focus==='string'?old.focus:'',borrow:typeof old.borrow==='string'?old.borrow:''};if(!value.focus.trim()&&!value.borrow.trim())return null;
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));
  return {...value,key:[...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('')};
 }
 function paint(p){
  if(panels.get(p.el)!==p)return;
  const wasOpen=p.el.querySelector('.reference-note-composer')?.open,d=draft(p),notes=applicable(p),saved=notes.length;
  const open=p.forceOpen??wasOpen??(hasDraft(p)||!!saved),disabled=p.loading||p.busy,stale=hasDraft(p)&&d.contextRevision&&p.data&&d.contextRevision!==p.data.context_revision;p.forceOpen=undefined;
  p.el.innerHTML='<details class="reference-note-composer"'+(open?' open':'')+'><summary>'+esc(saved?I18N.t('referenceNotes.summary.yourNotes',{n:saved}):I18N.t('referenceNotes.summary.addNote'))+'</summary><div class="reference-note-body">'+(stale?'<div class="reference-stale-draft"><p>'+esc(I18N.t('referenceNotes.stale.message'))+'</p><button class="secondary" data-note-rebase>'+esc(I18N.t('referenceNotes.stale.rebaseButton'))+'</button><small>'+esc(I18N.t('referenceNotes.stale.clearsTimestamp'))+'</small></div>':'')+'<div class="reference-note-context'+(d.time!==null?' is-attached':'')+'"><span>'+esc(scope(p))+'</span>'+(d.time!==null?'<button class="text-button" data-note-remove-time>'+esc(I18N.t('referenceNotes.actions.removeTimestamp'))+'</button>':'')+'</div><label class="sr-only" for="borrow-'+p.id+'">'+esc(I18N.t('referenceNotes.borrow.label'))+'</label><textarea id="borrow-'+p.id+'" data-borrow-note rows="3" maxlength="2000" placeholder="'+esc(I18N.t('referenceNotes.borrow.label'))+'"'+(disabled?' disabled':'')+'>'+esc(d.text)+'</textarea>'+(p.combined?'<label class="reference-focus-label">'+esc(I18N.t('referenceNotes.focus.label'))+' <span>'+esc(I18N.t('common.optional'))+'</span><input data-borrow-focus maxlength="1000" value="'+esc(d.focus||'')+'" placeholder="'+esc(I18N.t('referenceNotes.focus.placeholder'))+'"'+(disabled?' disabled':'')+'></label>':d.focus?'<p class="reference-focus-existing">'+esc(I18N.t('referenceNotes.focus.existing',{focus:d.focus}))+'</p>':'')+'<div class="feedback-actions">'+(p.data?.has_video&&!p.combined?'<button class="secondary" data-note-timestamp'+(disabled?' disabled':'')+'>'+esc(I18N.t('feedback.actions.addTimestamp'))+'</button>':'')+'<button class="primary" data-note-save'+(disabled||stale?' disabled':'')+'>'+esc(p.busy?I18N.t('project.saving'):I18N.t('referenceNotes.actions.saveNote'))+'</button><button class="text-button" data-note-clear'+(!hasDraft(p)?' hidden':'')+(disabled?' disabled':'')+'>'+esc(I18N.t('referenceNotes.actions.clearDraft'))+'</button></div><p class="reference-note-status" role="status">'+esc(p.message|| (p.loading?I18N.t('referenceNotes.status.loadingNotes'):I18N.t('referenceNotes.status.readyHint')))+'</p>'+(saved?'<div class="reference-saved-notes"><h4>'+esc(I18N.t('referenceNotes.saved.heading',{n:saved}))+'</h4>'+cards(notes,p)+'</div>':'')+'</div></details>';
  if(p.error)p.el.insertAdjacentHTML('beforeend','<p class="reference-note-error" role="alert">'+esc(p.error)+' <button class="text-button" data-note-retry>'+esc(I18N.t('referenceNotes.actions.retry'))+'</button></p>');
  if(p.legacy&&!p.data?.notes.some(n=>n.legacy_key===p.legacy.key))p.el.insertAdjacentHTML('beforeend','<details class="reference-legacy-note"><summary>'+esc(I18N.t('referenceNotes.legacy.heading'))+'</summary><p>'+esc(I18N.t('referenceNotes.legacy.body'))+'</p>'+(p.legacy.focus?'<p>'+I18N.t('referenceNotes.legacy.momentPrefix',{focus:esc(p.legacy.focus)})+'</p>':'')+'<p>'+esc(p.legacy.borrow||p.legacy.focus)+'</p><button class="secondary" data-note-import'+(disabled?' disabled':'')+'>'+esc(I18N.t('referenceNotes.legacy.saveButton'))+'</button></details>');
  if(p.data?.earlier_notes.length)p.el.insertAdjacentHTML('beforeend','<details class="reference-earlier-notes"><summary>'+esc(I18N.t('referenceNotes.earlier.heading',{n:p.data.earlier_notes.length}))+'</summary><p>'+esc(I18N.t('referenceNotes.earlier.body'))+'</p>'+cards(p.data.earlier_notes,{combined:true})+'</details>');
  if(!p.combined){$('#detail-quick-copy').disabled=disabled||!p.data;$('#detail-quick-copy').textContent=I18N.t('dialog.style.copyForChat');const context=p.data?.example_label||(p.target.slide?I18N.t('referenceNotes.scope.slide',{n:p.target.slide}):I18N.t('referenceNotes.scope.thisReference'));$('#detail-quick-hint').textContent=saved?I18N.t('referenceNotes.quickHint.withContext',{count:saved===1?I18N.t('referenceNotes.quickHint.noteCountOne'):I18N.t('referenceNotes.quickHint.noteCountMany',{n:saved}),context}):I18N.t('referenceNotes.quickHint.default');}
 }
 let panelCount=0;
 async function mount(el,t,combined=false){
  const p={el,target:t,combined,id:++panelCount,data:null,loading:true,busy:false,message:'',error:null,legacy:null};panels.set(el,p);paint(p);
  try{const [data,legacy]=await Promise.all([load(t),legacyFor(t)]);if(panels.get(el)!==p)return p;p.data=data;p.legacy=legacy;}
  catch(error){p.error=error.message;}
  finally{p.loading=false;paint(p);}
  return p;
 }
 function mountCurrent(){
  const t=currentTarget();if(!t)return;retain();
  if(t.slide){slides[t.reference_id]=t.slide;try{localStorage.setItem('ai-video-studio-reference-slides-v1',JSON.stringify(slides));}catch{}}
  const el=$('#reference-note-panel');mount(el,t).then(p=>{if(panels.get(el)===p)detail=p;});detail=panels.get(el);
 }
 async function save(p,legacy=false){
  if(p.loading||p.busy||!p.data)return;retain();
  const d=draft(p),text=legacy?p.legacy?.borrow||p.legacy?.focus:d.text;
  if(!legacy&&d.contextRevision&&d.contextRevision!==p.data.context_revision){p.message=I18N.t('referenceNotes.save.staleWarning');paint(p);return;}
  if(!text?.trim()){p.message=I18N.t('feedback.save.writeNoteFirst');paint(p);p.el.querySelector('[data-borrow-note]')?.focus();return;}
  const body={...p.target,slide:legacy?null:p.target.slide,context_revision:p.data.context_revision,text,time:legacy?null:d.time,focus:legacy?(p.legacy.borrow?p.legacy.focus:''):d.focus||'',legacy_key:legacy?p.legacy.key:null};
  const signature=JSON.stringify(body);let request=requests.get(signature);if(!request){request={...body,request_id:crypto.randomUUID()};requests.set(signature,request);}
  p.busy=true;p.message='';p.error=null;paint(p);
  try{
   const result=await reply(await fetch('/reference-notes',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference-note'},body:JSON.stringify(request)}));
   if(!legacy){const latest=draft(p);if(latest.text===d.text&&latest.time===d.time&&latest.focus===d.focus)drafts.delete(key(p.target));remember();}
   requests.delete(signature);if(legacy)p.forceOpen=true;p.message=I18N.t('referenceNotes.save.successMessage');
   for(const other of panels.values())if(other.target.reference_id===p.target.reference_id&&other.target.example_id===p.target.example_id){other.data=result;paint(other);}
  }catch(error){p.message=/draft.*kept/i.test(error.message)?error.message:I18N.t('referenceNotes.save.errorWithDraftKept',{error:error.message});}
  finally{p.busy=false;paint(p);}
 }
 function timestamp(p){
  const video=$('#detail-media video');if(!video||p.combined||!Number.isFinite(video.currentTime))return;
  video.pause();retain();const time=Math.round(video.currentTime*1000)/1000;
  if(time<p.data.start||time>(p.data.end??86400)){p.message=I18N.t('referenceNotes.timestamp.chooseInside');paint(p);return;}
  drafts.set(key(p.target),{...draft(p),time,contextRevision:p.data.context_revision});remember();p.message=I18N.t('referenceNotes.timestamp.set',{time:exact(time)});paint(p);p.el.querySelector('[data-borrow-note]')?.focus();
 }
 document.addEventListener('input',event=>{
  if(!event.target.matches('[data-borrow-note],[data-borrow-focus]'))return;retain();const p=[...panels.values()].find(p=>p.el.contains(event.target));if(p)p.el.querySelector('[data-note-clear]').hidden=!hasDraft(p);
 });
 document.addEventListener('click',event=>{
  const node=event.target.closest('[data-note-rebase],[data-note-save],[data-note-import],[data-note-timestamp],[data-note-remove-time],[data-note-clear],[data-note-seek],[data-note-retry]');if(!node)return;
  const p=[...panels.values()].find(p=>p.el.contains(node));if(!p)return;
  if(node.hasAttribute('data-note-retry')){retain();mount(p.el,p.target,p.combined).then(next=>{if(detail===p)detail=next;selectionPanels=selectionPanels.map(v=>v===p?next:v);});return;}
  if(node.hasAttribute('data-note-rebase')){retain();drafts.set(key(p.target),{...draft(p),time:null,contextRevision:p.data.context_revision});p.message=I18N.t('referenceNotes.rebase.message');remember();paint(p);return;}
  if(node.hasAttribute('data-note-save'))return save(p);
  if(node.hasAttribute('data-note-import'))return save(p,true);
  if(node.hasAttribute('data-note-timestamp'))return timestamp(p);
  if(node.hasAttribute('data-note-remove-time')){retain();drafts.set(key(p.target),{...draft(p),time:null});p.message=I18N.t('referenceNotes.removeTime.message');remember();paint(p);return;}
  if(node.hasAttribute('data-note-clear')){drafts.delete(key(p.target));p.message=I18N.t('referenceNotes.clearDraft.message');remember();paint(p);return;}
  const video=$('#detail-media video');if(video&&node.dataset.noteSeek!==undefined){video.pause();video.currentTime=Number(node.dataset.noteSeek);}
 });
 function row(p){
  if(p.loading||p.busy||!p.data)throw Error(I18N.t('referenceNotes.row.waitForLoad'));
  if(hasDraft(p))throw Error(I18N.t('referenceNotes.row.saveOrClearFirst'));
  return {...p.target,context_revision:p.data.context_revision,note_ids:applicable(p).map(n=>n.id)};
 }
 async function prepare(list){
  retain();const rows=list.map(row),signature=JSON.stringify(rows);
  const result=await reply(await fetch('/reference-handoff',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference-handoff'},body:JSON.stringify({references:rows})}));
  retain();if(JSON.stringify(list.map(row))!==signature)throw Error(I18N.t('referenceNotes.prepare.changed'));return result.text;
 }
 function fallback(text){$('#link-title').textContent=I18N.t('referenceNotes.fallback.title');$('#link-text').value=text;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}
 async function copy(list,status,button,valid=()=>true){
  if(copyBusy)return;copyBusy=true;button.disabled=true;status.textContent=I18N.t('referenceNotes.copy.preparing');
  try{
   const text=await prepare(list);if(!valid())return;
   try{await navigator.clipboard.writeText(text);if(valid()){button.textContent=button.classList.contains('copy-card')?'✓':I18N.t('dialog.style.copiedCheck');status.textContent=I18N.t('referenceNotes.copy.pasteHint');}}
   catch{if(valid()){status.textContent=I18N.t('referenceNotes.copy.manualFallback');fallback(text);}}
  }catch(error){if(valid())status.textContent=error.message;}
  finally{copyBusy=false;if(valid())button.disabled=false;}
 }
 function copyCurrent(){const p=detail;if(p)return copy([p],$('#detail-quick-status'),$('#detail-quick-copy'),()=>detail===p&&$('#style-dialog').open);}
 async function copyCard(id,exampleId,button){
  const t=targetFor(id,exampleId);if(!exampleId&&isCarousel(item(id)))t.slide=null;
  const status=$('#toast');status.hidden=false;
  try{const data=await load(t),p={target:t,data,loading:false,busy:false};await copy([p],status,button,()=>button.isConnected);if(button.isConnected){setTimeout(()=>{button.innerHTML=copyIcon;status.hidden=true;},2400);}}
  catch(error){notify(error.message);}
 }
 async function openSelection(ids){
  retain();pausePreview();const run=++selectionRun;briefIds=ids.filter(id=>item(id));selectionPanels=[];$('#copy-status').textContent=I18N.t('referenceNotes.status.loadingNotes');$('#copy-again').disabled=true;$('#copy-again').textContent=I18N.t('dialog.style.copyForChat');$('#reference-message-preview').open=false;$('#brief-text').value='';
  $('#handoff-items').innerHTML=briefIds.map((id,i)=>{const t=targetFor(id),e=item(id),x=t.example_id?example(e,false):null;return '<section class="handoff-item"><div class="handoff-item-head"><img src="'+esc(x?.poster||e.poster)+'" alt=""><div><h3>'+esc(e.title)+'</h3><p>'+esc(x?x.label+' · '+source(x.style_id).creator+' · '+exact(x.start)+'–'+exact(x.end):e.creator)+'</p></div><button class="remove-reference" data-selection-remove="'+esc(id)+'">'+esc(I18N.t('referenceNotes.actions.removeFromSelection'))+'</button></div><div data-selection-notes="'+i+'"></div></section>';}).join('');
  $('#brief-dialog').showModal();
  const loaded=await Promise.all(briefIds.map((id,i)=>mount($('#handoff-items [data-selection-notes="'+i+'"]'),targetFor(id),true)));
  if(run!==selectionRun)return;selectionPanels=loaded;$('#copy-again').disabled=false;$('#copy-status').textContent=I18N.t('referenceNotes.status.readyToCopy');
 }
 $('#handoff-items').addEventListener('click',event=>{const button=event.target.closest('[data-selection-remove]');if(!button)return;retain();const id=button.dataset.selectionRemove;selected.delete(id);saveSelection();const next=briefIds.filter(v=>v!==id);if(next.length)openSelection(next);else{$('#brief-dialog').close();++selectionRun;}});
 $('#brief-dialog').addEventListener('close',()=>{retain();++selectionRun;});
 $('#copy-again').addEventListener('click',()=>{const run=selectionRun;copy(selectionPanels,$('#copy-status'),$('#copy-again'),()=>selectionRun===run&&$('#brief-dialog').open);});
 $('#reference-message-preview').addEventListener('toggle',async()=>{
  if(!$('#reference-message-preview').open)return;const run=selectionRun;$('#brief-text').value=I18N.t('referenceNotes.preview.preparingMessage');
  try{const text=await prepare(selectionPanels);if(run===selectionRun)$('#brief-text').value=text;}
  catch(error){if(run===selectionRun)$('#brief-text').value=error.message;}
 });
 if(active)mountCurrent();
 return {mountCurrent,retain,copyCurrent,copyCard,openSelection};
})();
