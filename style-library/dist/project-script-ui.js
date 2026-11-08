/* Scripts stay with the project; only explicit Copy prepares a request for the editing chat. */
window.ProjectScript=(()=>{
 const drafts=new Map(),key='ai-video-studio-script-drafts-v1',feedbackDrafts=new Map(),feedbackKey='ai-video-studio-script-feedback-v1';let current=null,run=0;
 try{for(const [id,value] of Object.entries(JSON.parse(sessionStorage.getItem(feedbackKey)||'{}')))if(value&&typeof value.feedback==='string'&&value.feedback.length<=10000&&typeof value.references==='string'&&value.references.length<=10000)feedbackDrafts.set(id,value);}catch{}
 try{for(const [id,value] of Object.entries(JSON.parse(sessionStorage.getItem(key)||'{}')))if(value&&typeof value.text==='string'&&value.text.length<=50000)drafts.set(id,value);}catch{}
 const requestReply=async response=>{const value=await response.json();if(!response.ok){const error=Error(value.error||'Your script could not load.');error.status=response.status;throw error;}return value;};
 const get=url=>fetch(url,{cache:'no-store'}).then(requestReply);
 function persist(){try{sessionStorage.setItem(key,JSON.stringify(Object.fromEntries(drafts)));}catch{}}
 function retain(){
  if(!current?.panel.isConnected)return;
  if(current.renderedVersion!==undefined&&current.renderedVersion!==current.data.version_id)return;
  const field=current.panel.querySelector('[data-script-text]');if(!field)return;
  // Keep earlier tab-only context drafts recoverable, even though context is now read-only here.
  const d={...drafts.get(current.project.id),text:field.value,dirty:dirty(current),editing:current.editing,open:current.panel.querySelector('details')?.open??true,base:current.data.version_id};
  drafts.set(current.project.id,d);persist();retainFeedback(current);
 }
 function dirty(target){
  const field=target.panel.querySelector('[data-script-text]');
  return !!field&&(field.value.trim()!==target.data.text.trim());
 }
 function grow(target){
  const field=target?.panel.querySelector('[data-script-text]');if(!target?.full||!field)return;
  field.style.height='auto';field.style.height=(field.scrollHeight+2)+'px';
 }
 function readyStage(target){return target.full&&target.project.stage==='script';}
 function approved(target){
  return readyStage(target)&&!!target.data.version_id&&target.data.version_id===target.data.current_version_id&&target.brief?.ready_script===target.data.version_id;
 }
 function canSetReady(target){
  return readyStage(target)&&!!target.data.version_id&&target.data.version_id===target.data.current_version_id&&!target.editing&&!dirty(target)&&!target.needsCompare&&!target.busy&&!target.feedbackBusy;
 }
 function controls(target){
  const field=target.panel.querySelector('[data-script-text]');if(!field)return;
  const earlier=target.data.version_id!==target.data.current_version_id,changed=dirty(target),hasSaved=!!target.data.version_id;
  if(target.full&&changed)target.editing=true;
  const locked=target.busy||target.feedbackBusy;
  field.readOnly=!!locked;
  if(target.full){
   const isApproved=approved(target),decision=target.panel.querySelector('[data-script-decision]'),approve=target.panel.querySelector('[data-approve-script]'),record=target.panel.querySelector('[data-record-script]');
   if(decision){
    decision.hidden=!hasSaved||earlier||target.editing;
    target.panel.querySelector('[data-approve-row]').hidden=isApproved;approve.disabled=!canSetReady(target);
    record.hidden=!isApproved;
    for(const selector of ['[data-copy-recording]','[data-reopen-script]'])target.panel.querySelector(selector).disabled=!canSetReady(target);
   }
   target.panel.querySelector('[data-script-refinement]').hidden=isApproved&&!target.editing;
   field.hidden=!target.editing;
   target.panel.querySelector('[data-script-document]').hidden=!!target.editing;
   target.panel.querySelector('[data-edit-script]').hidden=!!target.editing||isApproved;
   target.panel.querySelector('[data-edit-script]').disabled=!!locked;
   target.panel.querySelector('[data-script-edit-bar]').hidden=!target.editing&&!earlier;
   const cancel=target.panel.querySelector('[data-cancel-script]');cancel.hidden=!target.editing;cancel.disabled=!!locked;
   target.panel.querySelector('[data-script-edit-state]').textContent=changed?'Unsaved changes':earlier?'Earlier version':'Editing script';
   const undo=target.panel.querySelector('[data-undo-opening]');
   if(undo){undo.hidden=!target.openingUndo||target.openingUndo.after!==target.data.version_id;undo.disabled=!!locked||changed||earlier||target.needsCompare;}
  }
  const save=target.panel.querySelector('[data-save-script]'),copy=target.panel.querySelector('[data-copy-script]');
  save.hidden=target.full&&!target.editing&&!earlier;
  save.textContent=target.full?(earlier&&!changed?'Make current':'Save changes'):'Save script';
  save.disabled=locked||target.needsCompare||!field.value.trim()||hasSaved&&!changed&&!earlier;
  copy.hidden=approved(target);
  copy.disabled=locked||!target.full&&(!hasSaved||changed||target.needsCompare);
  const menu=target.panel.querySelector('[data-script-history]');if(menu)menu.disabled=locked||target.full&&target.editing;
  target.panel.querySelectorAll('[data-use-hook]').forEach(button=>button.disabled=!!locked||approved(target)||target.editing||changed||target.needsCompare||earlier);
  for(const selector of ['[data-script-feedback]','[data-script-reference]']){const input=target.panel.querySelector(selector);if(input)input.readOnly=!!locked;}
  const feedbackCopy=target.panel.querySelector('[data-copy-script-feedback]');if(feedbackCopy){
   feedbackCopy.disabled=!!locked||!field.value.trim()||target.needsCompare||!hasFeedback(target);
   feedbackCopy.textContent=changed?'Save & copy feedback':target.copiedFeedback===feedbackSignature(target)?'Copied ✓':'Copy feedback for chat';
  }
  const feedbackHint=target.panel.querySelector('[data-feedback-hint]');if(feedbackHint)feedbackHint.textContent=changed?'Saves your changes, then copies feedback for that version.':earlier?'This feedback uses the earlier version shown above. Paste into your editing chat.':'Paste into your editing chat to revise this script.';
  copy.className=target.full&&!changed?'primary':'secondary';
  target.panel.querySelector('[data-script-state]').textContent=changed?'Unsaved changes':earlier?'Earlier version':approved(target)?'Script approved ✓':hasSaved?'Saved':'Draft';
  const count=field.value.trim()?field.value.trim().split(/\s+/).length:0;
  target.panel.querySelector('[data-script-count]').textContent=count+' word'+(count===1?'':'s');
  const compare=target.panel.querySelector('[data-reload-script]');
  compare.hidden=target.full&&!earlier&&!target.needsCompare;
 }
 function status(target,message){
  if(current!==target)return;
  const node=target.panel.querySelector('[data-script-status]');node.textContent=message;node.hidden=!message;
 }
 function contextText(value){
  return value.split(/(https?:\/\/[^\s<>"']+)/g).map(part=>/^https?:\/\//.test(part)?'<a href="'+esc(part)+'" target="_blank" rel="noopener noreferrer">'+esc(part)+'</a>':esc(part)).join('');
 }
 function paragraphs(text){return text.split(/\n\s*\n/).filter(Boolean).map(line=>'<p>'+esc(line)+'</p>').join('');}
 function documentText(target,text){
  const selected=target.hooks?.options?.find(option=>option.id===target.hooks.selected_id),opening=selected?.opening;
  return '<div data-script-document class="script-document">'+(opening&&text.startsWith(opening)?'<div data-opening-text class="script-opening-text'+(target.highlightOpening?' opening-changed':'')+'">'+paragraphs(opening)+'</div>'+paragraphs(text.slice(opening.length).trim()):paragraphs(text))+'</div>';
 }
 function details(target){
  const box=$('#project-script-context');if(!box)return;
  const {brief,data}=target;
  const notes=target.full?Object.entries({idea:brief.idea,references:brief.references}).filter(([,value])=>value.trim()):[];
  const later=[...new Set((target.feedback?.requests||[]).map(row=>row.references).filter(value=>value.trim()&&value.trim()!==brief?.references?.trim()))];
  const wrapper=box.closest('.script-idea-details');if(wrapper)wrapper.hidden=!target.full||!notes.length&&!later.length;
  box.hidden=!target.full||!notes.length&&!later.length;
  box.innerHTML=notes.map(([name,value])=>'<section><h3>'+(name==='idea'?'Your idea':'References')+'</h3><p>'+contextText(value)+'</p></section>').join('')+(target.full&&later.length?'<section><h3>References added during revisions</h3>'+later.map(value=>'<p>'+contextText(value)+'</p>').join('')+'</section>':'');
 }
 function draw(target,message=''){
  target.renderedVersion=target.data.version_id;
  const {panel,data,project,full}=target,draft=drafts.get(project.id);
  const conflict=draft&&draft.base!==data.version_id&&draft.text.trim()!==data.text.trim();
  target.needsCompare=!!conflict;
  const text=draft?.text??data.text;
  const history=data.versions.length?'<label class="script-history"><span'+(full?' class="sr-only"':'')+'>Versions</span><select data-script-history aria-label="Saved script versions">'+data.versions.map((v,i)=>'<option value="'+esc(v.id)+'" '+(v.id===data.version_id?'selected':'')+'>'+'Version '+(data.version_count-i)+(v.id===data.current_version_id?' · Current':'')+'</option>').join('')+'</select></label>':'';
  const writing='<label class="sr-only" for="project-script-text">Your script</label><textarea id="project-script-text" data-script-text rows="'+(full?1:7)+'" maxlength="50000" placeholder="'+(full?'Develop your script in chat, or start writing here…':'Paste the script you recorded…')+'">'+esc(text)+'</textarea>';
  const actions='<div class="script-actions">'+(full?'<button class="secondary script-edit-trigger" data-edit-script><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m16 3 5 5M4 15 16.5 2.5a2.1 2.1 0 0 1 3 3L7 18l-5 1zM3 22h18"/></svg>Edit script</button>':'<button class="primary" data-save-script>Save script</button>')+'<button class="'+(full?'primary':'secondary')+'" data-copy-script>'+(full?'Refine in chat':'Copy request for chat')+'</button></div>';
  const editBar=full?'<div class="script-edit-bar" data-script-edit-bar hidden><span data-script-edit-state>Editing script</span><div><button class="secondary" data-cancel-script>Cancel</button><button class="primary" data-save-script>Save changes</button></div></div>':'';
  const savedSpeech=!full&&data.assembled?'<details class="assembled-script"><summary>Selected spoken script · '+esc(data.assembled.version)+'</summary><p>The words selected from your recording are kept separately.</p><pre>'+esc(data.assembled.text)+'</pre></details>':'';
  const toolbar='<div class="script-editor-head"><span data-script-state></span><span data-script-count></span>'+history+(full?actions:'')+'</div>';
  const notice='<p data-script-status role="status" '+(message?'':'hidden')+'>'+esc(message)+'</p>';
  const body=(conflict?'<p class="project-notice">A newer script is saved. Your draft is kept below. Compare before saving.</p>':'')+toolbar+(full?notice+openings(target)+documentText(target,text):'')+writing+editBar+(full?'':'<div class="script-action-row">'+actions+'</div><p class="script-help">Your assistant uses this script to choose takes and flag missing lines. Saving doesn’t start an edit.</p>')+
   (full?'':notice)+'<button class="text-button" data-reload-script>Compare with saved script</button><div data-saved-comparison hidden></div>'+savedSpeech;
  panel.className=full?'scripting-workspace':'';
  panel.innerHTML=full?body+decisionCard(target)+refinement(target):'<details class="project-script" '+(draft?.open?'open':'')+'><summary>Your script <span>optional</span></summary><div class="project-script-body">'+body+'</div></details>';
  panel.querySelector('[data-script-text]').addEventListener('input',()=>{retain();target.request=null;target.panel.querySelector('[data-copy-script]').textContent=full?'Refine in chat':'Copy request for chat';status(target,'');grow(target);controls(target);});
  panel.querySelector('[data-save-script]').onclick=()=>save(target);
  panel.querySelector('[data-copy-script]').onclick=()=>full?refine(target):copy(target);
  panel.querySelector('[data-reload-script]').onclick=()=>compare(target);
  const menu=panel.querySelector('[data-script-history]');if(menu)menu.onchange=()=>loadVersion(target,menu.value);
  if(full){
   panel.querySelectorAll('[data-use-hook]').forEach(button=>button.onclick=()=>useHook(target,button.dataset.useHook));
   for(const selector of ['[data-script-feedback]','[data-script-reference]'])panel.querySelector(selector).addEventListener('input',()=>{retainFeedback(target);target.copiedFeedback=null;panel.querySelector('[data-copy-script-feedback]').textContent='Copy feedback for chat';feedbackStatus(target,'');controls(target);});
   panel.querySelector('[data-feedback-reference]').addEventListener('toggle',()=>retainFeedback(target));
   panel.querySelector('[data-copy-script-feedback]').onclick=()=>copyFeedback(target);
   panel.querySelector('[data-edit-script]').onclick=()=>{target.editing=true;controls(target);grow(target);const field=panel.querySelector('[data-script-text]');field.focus({preventScroll:true});field.scrollIntoView?.({block:'start',behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});retain();};
   panel.querySelector('[data-cancel-script]').onclick=()=>cancelEdit(target);
   if(readyStage(target)){
    panel.querySelector('[data-approve-script]').onclick=()=>setReady(target,true);
    panel.querySelector('[data-reopen-script]').onclick=()=>setReady(target,false);
    panel.querySelector('[data-copy-recording]').onclick=()=>copyRecording(target);
   }
   const undo=panel.querySelector('[data-undo-opening]');if(undo)undo.onclick=()=>undoOpening(target);
  }
  controls(target);grow(target);details(target);target.highlightOpening=false;
 }
 function cancelEdit(target){
  if(target.busy||target.feedbackBusy)return;retainFeedback(target);
  const d=drafts.get(target.project.id)||{};drafts.set(target.project.id,{...d,text:target.data.text,base:target.data.version_id,editing:false,dirty:false});persist();target.editing=false;target.request=null;draw(target);
  target.panel.querySelector(approved(target)?'[data-copy-recording]':'[data-edit-script]').focus({preventScroll:true});
 }
 async function save(target,feedback=null){
  if(target.busy||target.needsCompare||current!==target)return false;retain();
  const text=target.panel.querySelector('[data-script-text]').value;
  target.request??={project_id:target.project.id,revision:target.data.revision,request_id:crypto.randomUUID(),text};
  target.busy=true;controls(target);status(target,'Saving script…');
  try{
   const data=await fetch('/project-script',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'project-script'},body:JSON.stringify(target.request)}).then(requestReply);
   const draft=drafts.get(target.project.id);
   if(draft?.text===text){draft.text=data.text;draft.base=data.version_id;persist();}
   target.data=data;target.request=null;target.editing=false;target.openingUndo=null;target.openingNotice='';
   if(draft?.text===data.text){draft.editing=false;draft.dirty=false;}persist();
   let feedbackConflict=false;
   if(feedback){
    const existing=feedbackDrafts.get(feedbackId(target));
    feedbackConflict=!!existing&&!existing.copied&&(existing.feedback.trim()||existing.references.trim())&&(existing.feedback!==feedback.feedback||existing.references!==feedback.references);
    if(!feedbackConflict){feedbackDrafts.set(feedbackId(target),{feedback:feedback.feedback,references:feedback.references,referenceOpen:feedback.referenceOpen});persistFeedback();}
   }
   const route=new URLSearchParams(location.hash.slice(1));if(route.get('project')===target.project.id&&route.has('script')){if(target.full){target.pinned=false;route.delete('script');route.set('stage','script');}else route.set('script',data.version_id);route.delete('script-feedback');route.delete('feedback-revision');history.replaceState(null,'','#'+route);}
   await loadExtras(target);if(current===target)draw(target,feedbackConflict?'Changes saved. This version already has feedback; your other feedback stays with the previous version.':'Changes saved. Previous versions are kept.');
   if(current===target&&typeof notify==='function')notify(feedbackConflict?'Script saved. Your earlier feedback is kept.':'Script saved. Previous versions are kept.');
   return !feedbackConflict;
  }catch(error){if(error.status===409)target.needsCompare=true;status(target,error.message||'Couldn’t save. Your draft is kept.');return false;}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 async function compare(target){
  if(target.busy)return;
  try{
   const data=await get('/project-script?'+new URLSearchParams({project:target.project.id}));if(current!==target)return;
   const box=target.panel.querySelector('[data-saved-comparison]');box.hidden=false;
   box.innerHTML='<h3>Current saved script</h3><pre>'+esc(data.text||'No script saved yet.')+'</pre><button class="secondary" data-use-saved>Use saved script</button><p>Your draft stays in the editor until you choose to replace it.</p>';
   box.querySelector('[data-use-saved]').onclick=async()=>{retain();target.busy=true;controls(target);try{const draft=drafts.get(target.project.id);draft.text=data.text;draft.base=data.version_id;draft.dirty=false;persist();target.data=data;await loadExtras(target);if(current===target)draw(target);}finally{target.busy=false;if(current===target)controls(target);}};
   // Rebase only the revision after showing both versions; saving the kept draft remains explicit.
   target.data={...target.data,revision:data.revision,current_version_id:data.current_version_id,versions:data.versions};target.request=null;target.needsCompare=false;controls(target);
  }catch(error){status(target,error.message);}
 }
 async function loadVersion(target,id){
  if(target.busy)return;retainFeedback(target);
  if(dirty(target)){status(target,'Save your draft before switching versions.');target.panel.querySelector('[data-script-history]').value=target.data.version_id;return;}
  target.busy=true;controls(target);
  try{
   const data=await get('/project-script?'+new URLSearchParams({project:target.project.id,version:id}));if(current!==target)return;
   const draft=drafts.get(target.project.id)||{};draft.text=data.text;draft.base=data.version_id;draft.dirty=false;drafts.set(target.project.id,draft);persist();target.data=data;
   target.pinned=id!==data.current_version_id;const route=new URLSearchParams(location.hash.slice(1));if(target.pinned)route.set('script',id);else{route.delete('script');route.set('stage','script');}route.delete('script-feedback');route.delete('feedback-revision');history.replaceState(null,'','#'+route);
   await loadExtras(target);if(current===target)draw(target,id===data.current_version_id?'':'Viewing an earlier script. Choose Make current to restore it; all versions are kept.');
  }catch(error){status(target,error.message);}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 async function copy(target){
  if(target.busy||current!==target||dirty(target)||target.needsCompare)return;
  try{
   const data=await get('/project-script?'+new URLSearchParams(target.data.version_id?{project:target.project.id,version:target.data.version_id}:{project:target.project.id}));if(current!==target)return;
   if(dirty(target))throw Error('Save your changes before copying.');
   if(data.text!==target.data.text){target.needsCompare=true;controls(target);throw Error('The saved script changed. Compare it before copying.');}
   const url=new URL('./',location.href);url.hash=new URLSearchParams(data.version_id?{project:target.project.id,script:data.version_id}:{project:target.project.id,stage:'script'}).toString();
   const intro=!target.full?'Use my saved script for '+target.project.title+' to build or refine the spoken cut. I’ll attach my recorded footage or provide its location. Choose the strongest complete takes, preserve natural delivery, and flag missing or changed lines. Keep existing reviews and source footage.':
    'Help me develop or refine the script for '+target.project.title+'. Read docs/SCRIPTING.md, docs/SCRIPTING-BASELINE.md, my local writing preferences and this project’s script brief. Follow my reference intent, preserve accepted direction and save the revised script as a new version. Offer a few distinct hook options when we are choosing the opening; keep an accepted hook during targeted revisions. Remember useful general feedback with its source; keep project-only choices local.';
   const value=intro+'\n'+url.href;
   try{await navigator.clipboard.writeText(value);if(current===target){target.panel.querySelector('[data-copy-script]').textContent='Copied ✓';status(target,'Copied—paste into your editing chat.');}}
   catch{if(current===target){$('#link-text').value=value;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}}
  }catch(error){status(target,error.message);}
 }

 function feedbackId(target){return target.project.id+'/'+(target.data.version_id||'draft');}
 function feedbackDraft(target){return feedbackDrafts.get(feedbackId(target))||{feedback:'',references:'',referenceOpen:false};}
 function persistFeedback(){try{sessionStorage.setItem(feedbackKey,JSON.stringify(Object.fromEntries(feedbackDrafts)));}catch{}}
 function retainFeedback(target){
  if(!target?.full||!target.panel.isConnected)return;
  if(target.renderedVersion!==undefined&&target.renderedVersion!==target.data.version_id)return;
  const field=target.panel.querySelector('[data-script-feedback]'),reference=target.panel.querySelector('[data-script-reference]');if(!field||!reference)return;
  const old=feedbackDraft(target),next={...old,feedback:field.value,references:reference.value,referenceOpen:target.panel.querySelector('[data-feedback-reference]').open};
  if(old.feedback!==next.feedback||old.references!==next.references){delete next.request;delete next.copied;}
  feedbackDrafts.set(feedbackId(target),next);persistFeedback();
 }
 function hasFeedback(target){const d=feedbackDraft(target);return !!(d.feedback.trim()||d.references.trim());}
 function pendingFeedback(target){return hasFeedback(target)&&feedbackDraft(target).copied!==true;}
 function feedbackStatus(target,message){const field=target.panel.querySelector('[data-script-feedback-status]');if(current===target&&field){field.textContent=message;field.hidden=!message;}}
 async function loadExtras(target){
  if(!target.full)return;
  const query=new URLSearchParams({project:target.project.id});if(target.data.version_id)query.set('version',target.data.version_id);
  const results=await Promise.allSettled([get('/script-hooks?'+query),get('/script-feedback?'+new URLSearchParams({project:target.project.id}))]);
  target.hooks=results[0].status==='fulfilled'?results[0].value:{options:[],selected_id:null};
  target.feedback=results[1].status==='fulfilled'?results[1].value:{requests:[]};
  target.extraError=results.some(r=>r.status==='rejected')?'Your script is loaded, but some saved context couldn’t load. Reopen Script to try again.':'';
  const params=new URLSearchParams(location.hash.slice(1)),id=params.get('script-feedback');
  if(params.get('project')===target.project.id&&id){
   const row=(target.feedback.requests||[]).find(r=>r.id===id);
   if(!row||row.script_version!==target.data.version_id||params.has('feedback-revision')&&params.get('feedback-revision')!==row.content_revision)target.extraError='This copied feedback is unavailable for the selected script. Your saved script and draft are kept.';
   else if(!feedbackDrafts.has(feedbackId(target))){feedbackDrafts.set(feedbackId(target),{feedback:row.feedback,references:row.references,referenceOpen:!!row.references,request:{project_id:target.project.id,script_version:row.script_version,request_id:row.id,feedback:row.feedback,references:row.references}});persistFeedback();}
  }
 }
 function openings(target){
  const options=target.hooks?.options||[];
  if(!options.length)return '';
  const isApproved=approved(target);
  const cards='<div class="script-opening-options">'+options.map((option,i)=>{
   const [hook,...bridge]=option.opening.split(/\n\s*\n/),selected=option.id===target.hooks.selected_id;
   const label='<span class="script-opening-label">Hook '+(i+1)+'<span>'+(selected?'✓ In script':isApproved?'':'Use this hook')+'</span></span><span class="script-opening-copy">'+esc(hook)+'</span>';
   const choice=isApproved?'<div class="script-hook-reference">'+label+'</div>':'<button data-use-hook="'+esc(option.id)+'" aria-pressed="'+selected+'">'+label+'</button>';
   return '<article class="script-opening-option'+(selected?' is-selected':'')+'">'+choice+(bridge.length?'<details class="script-hook-lead"><summary>Preview lead-in</summary><p>'+esc(bridge.join('\n\n'))+'</p></details>':'')+'</article>';
  }).join('')+'</div>';
  return isApproved?'<details class="script-openings script-hooks-approved"><summary>Hook options <span>'+options.length+' saved</span></summary>'+cards+'</details>':
   '<section class="script-openings" aria-labelledby="script-openings-title"><div class="script-openings-head"><h3 id="script-openings-title">Hook options</h3><div class="script-opening-notice"><span role="status">'+esc(target.openingNotice||'')+'</span><button class="text-button" data-undo-opening hidden>Undo</button></div></div>'+cards+'</section>';
 }
 function decisionCard(target){
  if(!readyStage(target))return '';
  return '<section class="script-decision" data-script-decision><div class="script-approve-row" data-approve-row><p>Next: record your video</p><button class="primary" data-approve-script>Approve script</button></div><div class="script-record" data-record-script hidden><h3>Ready to record</h3><p>Record your video outside the studio. When you’re done, click <strong>Copy prompt for chat</strong>, paste it into your editing chat, and attach your raw footage.</p><div class="script-record-actions"><button class="primary" data-copy-recording>Copy prompt for chat</button><button class="text-button" data-reopen-script>Make changes</button></div></div><p data-ready-status role="status" hidden></p></section>';
 }
 function readyStatus(target,message){
  if(current!==target)return;
  const node=target.panel.querySelector('[data-ready-status]');node.textContent=message;node.hidden=!message;
 }
 async function setReady(target,ready){
  if(current!==target||!canSetReady(target)||ready===approved(target))return;
  retain();
  const body={project_id:target.project.id,revision:target.brief.revision,script_version:target.data.version_id,script_revision:target.data.revision,ready};
  const signature=JSON.stringify(body);
  if(target.readyRequest?.signature!==signature)target.readyRequest={signature,body:{...body,request_id:crypto.randomUUID()}};
  target.busy=true;controls(target);readyStatus(target,ready?'Approving script…':'Reopening script…');
  try{
   const brief=await fetch('/script-ready',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'script-ready'},body:JSON.stringify(target.readyRequest.body)}).then(requestReply);
   if(current!==target)return;
   target.brief=brief;target.readyRequest=null;target.openingUndo=null;target.openingNotice='';
   draw(target);
   target.busy=false;controls(target);
   readyStatus(target,approved(target)?'Script approved.':'Script reopened. Your saved versions are kept.');
   const next=target.panel.querySelector(approved(target)?'[data-copy-recording]':'[data-approve-script]');
   next.focus({preventScroll:true});next.scrollIntoView?.({block:'nearest'});
  }catch(error){if(error.status===409)target.readyRequest=null;readyStatus(target,error.message||'Couldn’t save the decision. Your script is kept.');}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 async function copyRecording(target){
  if(current!==target||!canSetReady(target)||!approved(target))return;
  target.busy=true;controls(target);readyStatus(target,'');
  try{
   const brief=await get('/script-brief?'+new URLSearchParams({project:target.project.id}));
   if(current!==target)return;
   if(!brief.ready||brief.ready_script!==target.data.version_id)throw Error('The script approval changed. Reopen Script before copying a recording request.');
   const url=new URL('./',location.href);url.hash=new URLSearchParams({project:target.project.id,script:target.data.version_id,handoff:'spoken-cut'}).toString();
   const message='Use my approved script to turn this footage into a spoken cut. Share it with me for review before storyboarding.\n\n'+url.href;
   try{await navigator.clipboard.writeText(message);if(current===target)readyStatus(target,'Copied. Paste into your editing chat and attach your raw footage.');}
   catch{if(current===target){$('#link-text').value=message;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}}
  }catch(error){readyStatus(target,error.message||'Couldn’t prepare the recording request.');}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 function refinement(target){
  const d=feedbackDraft(target),copied=target.copiedFeedback===feedbackSignature(target);
  return '<section class="script-refinement" data-script-refinement aria-labelledby="script-feedback-label"><label id="script-feedback-label" for="script-feedback-text">What would you like to change?</label><textarea id="script-feedback-text" data-script-feedback rows="3" maxlength="10000" placeholder="Give me a stronger hook, make it shorter, or make it sound more like me…">'+esc(d.feedback)+'</textarea><details class="script-feedback-reference" data-feedback-reference '+(d.referenceOpen||d.references?'open':'')+'><summary>Add a reference <small>optional</small></summary><label for="script-feedback-reference">Reference video and what you like</label><textarea id="script-feedback-reference" data-script-reference rows="2" maxlength="10000" placeholder="Paste a link and describe what you’d like to borrow—its opening question, storytelling approach, pacing…">'+esc(d.references)+'</textarea></details><div class="script-refinement-actions"><p data-feedback-hint></p><button class="primary" data-copy-script-feedback>'+(copied?'Copied ✓':'Copy feedback for chat')+'</button></div><p data-script-feedback-status role="status" '+(copied?'':'hidden')+'>'+(copied?'Copied—paste into your editing chat.':'')+'</p></section>';
 }
 function refine(target){
  const field=target.panel.querySelector('[data-script-feedback]');field.scrollIntoView?.({block:'center',behavior:'smooth'});field.focus({preventScroll:true});
 }
 async function useHook(target,id){
  if(current!==target||approved(target)||target.busy||target.feedbackBusy||target.editing||dirty(target)||target.needsCompare||target.data.version_id!==target.data.current_version_id||id===target.hooks.selected_id)return;
  retain();const oldVersion=target.data.version_id,oldText=target.data.text;
  if(target.hookRequest?.option_id!==id)target.hookRequest={project_id:target.project.id,revision:target.data.revision,request_id:crypto.randomUUID(),script_version:oldVersion,hook_revision:target.hooks.revision,option_id:id};
  target.busy=true;controls(target);status(target,'Saving the new opening…');
  try{
   const data=await fetch('/script-hook',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'script-hook'},body:JSON.stringify(target.hookRequest)}).then(requestReply);
   if(current!==target)return;
   target.hookRequest=null;target.data=data;target.hooks=data.hooks;target.openingUndo={text:oldText,version_id:oldVersion,after:data.version_id};target.openingNotice='Opening updated.';target.highlightOpening=true;
   const d=drafts.get(target.project.id)||{};drafts.set(target.project.id,{...d,text:data.text,base:data.version_id,dirty:false});persist();
   target.pinned=false;const route=new URLSearchParams(location.hash.slice(1));route.delete('script');route.set('stage','script');route.delete('script-feedback');route.delete('feedback-revision');history.replaceState(null,'','#'+route);
   draw(target,hasFeedback({...target,data:{...target.data,version_id:oldVersion}})?'Your feedback draft stays with the previous version.':'');
   target.panel.querySelector('[data-use-hook="'+id+'"]')?.focus({preventScroll:true});
  }catch(error){status(target,error.message);if(error.status===409){target.hookRequest=null;target.needsCompare=true;}}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 async function undoOpening(target){
  const undo=target.openingUndo;
  if(current!==target||approved(target)||!undo||undo.after!==target.data.version_id||target.busy||target.feedbackBusy||dirty(target)||target.needsCompare||target.data.version_id!==target.data.current_version_id)return;
  retain();undo.request??={project_id:target.project.id,revision:target.data.revision,request_id:crypto.randomUUID(),text:undo.text};
  target.busy=true;controls(target);status(target,'Restoring the previous opening…');
  try{
   const data=await fetch('/project-script',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'project-script'},body:JSON.stringify(undo.request)}).then(requestReply);
   if(current!==target)return;
   target.data=data;target.openingUndo=null;target.openingNotice='Previous opening restored.';target.highlightOpening=true;
   const d=drafts.get(target.project.id)||{};drafts.set(target.project.id,{...d,text:data.text,base:data.version_id,editing:false,dirty:false});persist();target.editing=false;
   await loadExtras(target);if(current===target){draw(target);target.panel.querySelector('[data-use-hook="'+target.hooks.selected_id+'"]')?.focus({preventScroll:true});}
  }catch(error){status(target,error.message||'Couldn’t restore the opening. Your script is kept.');if(error.status===409){undo.request=null;target.needsCompare=true;}}
  finally{target.busy=false;if(current===target)controls(target);}
 }
 function feedbackSignature(target){const d=feedbackDraft(target);return JSON.stringify([target.data.version_id,d.feedback.trim(),d.references.trim()]);}
 async function copyFeedback(target){
  if(current!==target||approved(target)&&!dirty(target)||target.feedbackBusy||target.busy||target.needsCompare)return;
  if(dirty(target)){
   retainFeedback(target);const feedback={...feedbackDraft(target)};if(!hasFeedback(target))return;
   target.feedbackBusy=true;controls(target);const saved=await save(target,feedback);target.feedbackBusy=false;if(current===target)controls(target);
   if(!saved||current!==target)return;
  }
  if(!target.data.version_id)return;
  retainFeedback(target);if(!hasFeedback(target))return;
  const draft=feedbackDraft(target),signature=feedbackSignature(target);
  if(!draft.request||draft.request.project_id!==target.project.id||draft.request.script_version!==target.data.version_id||draft.request.feedback!==draft.feedback.trim()||draft.request.references!==draft.references.trim())draft.request={project_id:target.project.id,script_version:target.data.version_id,request_id:crypto.randomUUID(),feedback:draft.feedback.trim(),references:draft.references.trim()};persistFeedback();
  const request={...draft.request};target.feedbackBusy=true;controls(target);feedbackStatus(target,'Preparing feedback…');
  try{
   const record=await fetch('/script-feedback',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'script-feedback'},body:JSON.stringify(request)}).then(requestReply);
   if(current!==target||dirty(target)||signature!==feedbackSignature(target))return;
   if(record.project_id!==request.project_id||record.script_version!==request.script_version||record.feedback!==request.feedback||record.references!==request.references)throw Error('The feedback response did not match this script. Your draft is kept.');
   const url=new URL('./',location.href);url.hash=new URLSearchParams({project:target.project.id,script:record.script_version,'script-feedback':record.id,'feedback-revision':record.content_revision}).toString();
   const text='Help me revise the script for '+target.project.title+'.\n'+url.href+(record.feedback?'\n\nMy feedback:\n'+record.feedback:'')+(record.references?'\n\nReference video and what I’d like to borrow:\n'+record.references:'')+'\n\nRead docs/SCRIPTING.md, docs/SCRIPTING-BASELINE.md and my local writing preferences. Load this exact script and scripting.feedback_current(project_id, request_id, content_revision) for the copied feedback. Inspect supplied references and follow my borrowing intent. Current feedback takes priority; preserve direction I’ve already accepted. Save the revised script as a new immutable version. When choosing the opening, save a few distinct, compatible opening options with scripting.hooks_save so I can compare them in the studio. Keep useful reference intent with this project and remember general writing feedback with its source. Preserve existing scripts, footage and reviews.';
   if(!target.feedback.requests.some(row=>row.id===record.id))target.feedback.requests.push(Object.fromEntries(Object.entries(record).filter(([key])=>key!=='project_id')));details(target);
   try{await navigator.clipboard.writeText(text);if(current===target&&signature===feedbackSignature(target)){feedbackDraft(target).copied=true;target.copiedFeedback=signature;persistFeedback();target.panel.querySelector('[data-copy-script-feedback]').textContent='Copied ✓';feedbackStatus(target,'Copied—paste into your editing chat.');}}
   catch{if(current===target&&signature===feedbackSignature(target)){$('#link-text').value=text;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();feedbackStatus(target,'Feedback saved. Copy the request, then paste into your editing chat.');}}
  }catch(error){feedbackStatus(target,error.message||'Couldn’t prepare feedback. Your draft is kept.');}
  finally{target.feedbackBusy=false;if(current===target)controls(target);}
 }
 async function mount(project,artifact){
  const token=++run;current=null;const panel=$('#project-script-panel');if(!panel)return;
  const context=$('#project-script-context');if(context){context.hidden=true;context.innerHTML='';const wrapper=context.closest('.script-idea-details');if(wrapper)wrapper.hidden=true;}
  const full=artifact.type==='script';
  panel.hidden=project.format!=='video'||!full&&ReviewLayout.stage(project,artifact)!=='spoken';if(panel.hidden)return;
  panel.className='';panel.innerHTML='<p class="script-help">Opening your script…</p>';
  try{
   const params=new URLSearchParams(location.hash.slice(1)),query=new URLSearchParams({project:project.id});if(params.get('project')===project.id&&params.has('script'))query.set('version',params.get('script'));
   const [data,brief]=await Promise.all([get('/project-script?'+query),full?get('/script-brief?'+new URLSearchParams({project:project.id})):Promise.resolve(null)]);
   if(token!==run||!panel.isConnected)return;
   let draft=drafts.get(project.id);
   if(draft?.dirty===false&&draft.base!==data.version_id){
    draft={...draft,text:data.text,base:data.version_id,editing:false};drafts.set(project.id,draft);persist();
   }
   const target={project,panel,data,brief,full,editing:full&&(!data.version_id||draft?.editing||!!draft&&draft.text.trim()!==data.text.trim()),pinned:params.has('script'),busy:false,request:null};await loadExtras(target);if(token!==run||!panel.isConnected)return;current=target;draw(target,target.extraError||'');
  }catch(error){if(token===run&&panel.isConnected)panel.innerHTML='<p class="script-help">'+esc(error.message)+' Reopen Script to try again. Your draft is kept.</p>';}
 }
 async function refresh(){
  const target=current;if(!target?.panel.isConnected||target.panel.hidden||target.panel.closest('#project-page')?.hidden||document.hidden||target.busy||target.feedbackBusy||target.editing||dirty(target)||target.data.version_id!==target.data.current_version_id)return;
  const visibleVersion=target.data.version_id;let ownsLock=false;
  try{
   const data=await get('/project-script?'+new URLSearchParams({project:target.project.id}));
   const brief=target.full?await get('/script-brief?'+new URLSearchParams({project:target.project.id})):null;
   if(current!==target||target.busy||target.feedbackBusy||target.editing||dirty(target)||target.data.version_id!==visibleVersion)return;
   if(data.revision===target.data.revision&&brief?.revision===target.brief?.revision){
    const oldHooks=target.hooks?.revision,oldFeedback=JSON.stringify(target.feedback);await loadExtras(target);
    if(current===target&&!target.busy&&!target.editing&&target.data.version_id===visibleVersion&&!dirty(target)&&(oldHooks!==target.hooks?.revision||oldFeedback!==JSON.stringify(target.feedback))){retainFeedback(target);draw(target);}return;
   }
   retainFeedback(target);
   if(data.version_id!==target.data.version_id&&(target.pinned||pendingFeedback(target))){
    target.data={...target.data,revision:data.revision,current_version_id:data.current_version_id,versions:data.versions,version_count:data.version_count};await loadExtras(target);if(current===target)draw(target,target.pinned?'A newer script is saved. You’re viewing this exact saved version; choose the latest from Versions to continue.':'A newer script is saved. Your feedback stays with this version; choose the latest from Versions when you’re ready.');return;
   }
   target.busy=true;ownsLock=true;controls(target);
   const draft=drafts.get(target.project.id);if(draft)drafts.set(target.project.id,{...draft,text:data.text,base:data.version_id,dirty:false});persist();target.data=data;target.brief=brief;await loadExtras(target);if(current===target)draw(target);
  }catch{/* Kept draft and explicit comparison remain available. */}
  finally{if(ownsLock){target.busy=false;if(current===target)controls(target);}}
 }
 window.addEventListener('beforeunload',retain);window.addEventListener('focus',refresh);window.addEventListener('resize',()=>grow(current));setInterval(refresh,8000);
 return {mount,retain,hasDraft:()=>!!current&&dirty(current),isEditing:()=>!!current&&current.full&&!!current.editing,hasPendingFeedback:()=>!!current&&current.full&&pendingFeedback(current)};
})();
