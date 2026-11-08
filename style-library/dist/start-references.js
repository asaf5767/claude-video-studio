/* Project-only inspiration. Browsing/copying never edits the library or its selection. */
window.StartReferences=(()=>{
 const isLink=r=>r?.kind==='link';
 const targetKey=t=>isLink(t)?JSON.stringify(['link',t.url]):JSON.stringify([t.reference_id,t.example_id||null,t.slide||null]);
 function link(value,note=''){
  let url;try{url=new URL(value.trim());}catch{throw Error(I18N.t('start.inspiration.error.invalidLink'));}
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.href.length>10000)throw Error(I18N.t('start.inspiration.error.unsafeLink'));
  return {kind:'link',url:url.href,note:String(note).slice(0,2000),details:{title:url.hostname.replace(/^www\./,''),label:'',kind:'link'}};
 }
 const noteValue=r=>({note:typeof r?.note==='string'?r.note.slice(0,2000):'',time:typeof r?.time==='number'&&Number.isFinite(r.time)&&r.time>=0?Math.round(r.time*100)/100:null,focus:typeof r?.focus==='string'?r.focus.slice(0,1000):''});
 const hasNote=r=>{const n=noteValue(r);return !!(n.note.trim()||n.time!==null||n.focus.trim());};
 const target=t=>({reference_id:t.reference_id,example_id:t.example_id||null,slide:t.slide||null});
 function resolve(t){
  const e=item(t.reference_id);if(!e)throw Error(I18N.t('start.inspiration.error.referenceGone'));
  const x=isTech(e)?e.examples.find(x=>x.id===t.example_id):null;
  if(isTech(e)&&!x)throw Error(I18N.t('start.inspiration.error.chooseExampleAgain'));
  if(!isTech(e)&&t.example_id)throw Error(I18N.t('start.inspiration.error.referenceChanged'));
  const s=x?source(x.style_id):e;if(!s)throw Error(I18N.t('start.inspiration.error.sourceUnavailable'));
  if(t.slide&&(!isCarousel(e)||t.slide>e.slides.length))throw Error(I18N.t('start.inspiration.error.chooseSlideAgain'));
  return {title:e.title,label:x?.label||'',creator:s.creator,poster:x?.poster||e.poster,kind:x?'technique':isCarousel(e)?'carousel':'video',
   url:referenceUrl(e.id,x?.id||null,t.slide?t.slide-1:null),media:s.media_path?'/media/'+encodeURIComponent(s.id):null,
   start:x?.start||0,end:x?.end??s.duration??null,status:s.analysis_status,description:e.summary||'',removed:isRemoved(s)};
 }
 async function json(response){const data=await response.json();if(!response.ok)throw Error(data.error||I18N.t('start.inspiration.error.loadFailed'));return data;}
 async function handoff(rows){return json(await fetch('/reference-handoff',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference-handoff'},body:JSON.stringify({references:rows.map(r=>({...target(r),context_revision:r.context_revision,note_ids:r.note_ids}))})}));}
 async function capture(t){
  const details=resolve(t),params=new URLSearchParams({id:t.reference_id});if(t.example_id)params.set('example',t.example_id);
  const data=await json(await fetch('/reference-notes?'+params,{cache:'no-store'}));
  const notes=(data.notes||[]).filter(n=>n.slide===null||n.slide===(t.slide||null));
  const row={...target(t),context_revision:data.context_revision,note_ids:notes.map(n=>n.id),note:'',details};
  const result=await handoff([row]);row.message=result.text.split('\n').slice(2).join('\n').trim();return row;
 }
 function text(rows){
  if(!rows.length)return '';
  let value=(rows.length===1?I18N.t('start.inspiration.text.useOneReference'):I18N.t('start.inspiration.text.useManyReferences'))+'\n\n'+rows.map(r=>isLink(r)?r.url:r.message).join('\n\n');
  const notes=rows.filter(hasNote);if(notes.length)value+=I18N.t('start.inspiration.text.notesHeading')+notes.map(r=>{const n=noteValue(r),position=n.time!==null?I18N.t('referenceNotes.position.at',{time:exact(n.time)}):n.focus.trim()?I18N.t('start.inspiration.text.momentOrRange',{focus:n.focus.trim()}):'';return (isLink(r)?r.url:r.details.label||r.details.title)+(position?' — '+position:'')+(n.note.trim()?': '+n.note.trim():'');}).join('\n');
  return value;
 }
 async function validate(rows){
  if(!rows.length)return;
  rows.filter(isLink).forEach(r=>link(r.url));rows=rows.filter(r=>!isLink(r));if(!rows.length)return;
  rows.forEach(r=>{const d=resolve(r),n=noteValue(r);if(n.time!==null&&(n.time<d.start||d.end!==null&&n.time>d.end))throw Error(I18N.t('start.inspiration.error.timestampOutsideExample'));});const result=await handoff(rows),
   // This integrity check compares the backend's echoed handoff text against the same
   // header `reference_notes.py` builds server-side ('Use this reference:'/'Use these
   // references:', hardcoded English there). It is never shown to the user -- only used
   // to detect "the server's text doesn't match what we expect" -- so it must stay
   // byte-identical to the untranslated Python string rather than go through I18N.t().
   expected=(rows.length===1?'Use this reference:':'Use these references:')+'\n\n'+rows.map(r=>r.message).join('\n\n');
  if(result.text.trim()!==expected.trim())throw Error(I18N.t('start.inspiration.error.changedBeforeHandoff'));
 }
 function restore(rows){
  if(!Array.isArray(rows))return [];
  const seen=new Set();return rows.slice(0,60).filter(r=>{
   if(isLink(r)){let normalized;try{normalized=link(r.url);}catch{return false;}const key=targetKey(normalized);if(seen.has(key))return false;seen.add(key);return true;}
   if(!r||typeof r.reference_id!=='string'||typeof r.context_revision!=='string'||!Array.isArray(r.note_ids)||!r.note_ids.every(n=>typeof n==='string')||typeof r.message!=='string'||!r.details||typeof r.details.title!=='string')return false;
   if(r.example_id!==null&&typeof r.example_id!=='string'||r.slide!==null&&(!Number.isInteger(r.slide)||r.slide<1))return false;
   const key=targetKey(r);if(seen.has(key))return false;seen.add(key);return true;
  }).map(r=>isLink(r)?link(r.url,r.note):({...r,...noteValue(r)}));
 }
 function selectedTargets(){
  let slides={};try{slides=JSON.parse(localStorage.getItem('ai-video-studio-reference-slides-v1')||'{}');}catch{}
  return [...selected].map(id=>{const e=item(id);return e?{reference_id:id,example_id:isTech(e)?example(e,false).id:null,slide:isCarousel(e)&&Number.isInteger(slides?.[id])?slides[id]:null}:null;}).filter(Boolean);
 }
 function create({dialog,get,set,showPicker,state=()=>{},level=()=>{},getDrafts=()=>({}),setDrafts=()=>{},getLinkDraft=()=>'',setLinkDraft=()=>{}}){
  const summary=dialog.querySelector('#start-reference-summary'),host=dialog.querySelector('#start-picker');
  let kind='videos',collection='all',query='',family=null,preview=null,loading=false,busy=false,run=0,visible=false,message='',browseScroll=0,browseFocus=null,noteRun=0,noteLoading=false,noteError='';
  const fresh=new Map();
  host.innerHTML='<div class="start-picker-body"><button type="button" class="text-button" data-ref-back>'+esc(I18N.t('start.inspiration.backToProject'))+'</button><p>'+esc(I18N.t('start.inspiration.intro'))+'</p><div class="start-picker-tools"><div class="start-picker-tabs" role="group" aria-label="'+esc(I18N.t('start.inspiration.typeAria'))+'"><button type="button" data-ref-kind="videos">'+esc(I18N.t('library.view.videos'))+'</button><button type="button" data-ref-kind="techniques">'+esc(I18N.t('library.view.techniques'))+'</button></div><label class="sr-only" for="start-reference-search">'+esc(I18N.t('start.inspiration.searchPlaceholder'))+'</label><input id="start-reference-search" type="search" placeholder="'+esc(I18N.t('start.inspiration.searchPlaceholder'))+'"><div class="start-picker-sources" role="group" aria-label="'+esc(I18N.t('start.inspiration.sourceAria'))+'"><button type="button" data-ref-source="all">'+esc(I18N.t('library.collection.all'))+'</button><button type="button" data-ref-source="mine">'+esc(I18N.t('library.collection.mine'))+'</button><button type="button" data-ref-source="reference">'+esc(I18N.t('library.collection.reference'))+'</button></div></div><div id="start-reference-results"></div><p class="start-picker-status" role="status"></p></div><div class="project-start-foot"><p>'+esc(I18N.t('start.inspiration.footNote'))+'</p><div><button type="button" class="primary" data-ref-done>'+esc(I18N.t('start.inspiration.useSelected'))+'</button></div></div>';
  const body=host.querySelector('.start-picker-body'),results=host.querySelector('#start-reference-results'),status=host.querySelector('.start-picker-status');
  const matches=s=>collection==='all'||s.collection===collection;
  const choose=t=>get().some(r=>targetKey(r)===targetKey(t));
  const rowFor=t=>get().find(r=>targetKey(r)===targetKey(t))||getDrafts()[targetKey(t)]||fresh.get(targetKey(t));
  const stale=t=>{const old=rowFor(t),now=fresh.get(targetKey(t));return !!(old&&now&&hasNote(old)&&old.context_revision!==now.context_revision);};
  function stash(row){setDrafts({...getDrafts(),[targetKey(row)]:row});}
  function update(t,delta){
   const row=rowFor(t);if(!row)return;
   const next={...row,...noteValue({...row,...delta})};
   if(choose(t))set(get().map(r=>targetKey(r)===targetKey(t)?next:r));else stash(next);
  }
  function composer(t,id,inPreview=false){
   let d;try{d=resolve(t);}catch{d=rowFor(t)?.details||{};}
   const row=rowFor(t),n=noteValue(row),disabled=!row||inPreview&&noteLoading||stale(t),position=n.time!==null?I18N.t('referenceNotes.scope.noteTime',{time:exact(n.time)}):d.kind==='technique'?I18N.t('start.inspiration.scope.thisExample',{start:exact(d.start),end:exact(d.end)}):I18N.t('referenceNotes.scope.wholeReference');
   return '<section class="start-project-note" data-project-note="'+esc(encodeURIComponent(targetKey(t)))+'">'+(stale(t)?'<div class="start-note-warning"><p>'+esc(I18N.t('start.inspiration.stale.message'))+'</p><button type="button" class="secondary" data-ref-rebase>'+esc(I18N.t('start.inspiration.stale.rebaseButton'))+'</button><small>'+esc(I18N.t('start.inspiration.stale.clearsTimestamp'))+'</small></div>':'')+'<label for="start-borrow-'+id+'">'+esc(I18N.t('start.inspiration.borrowLabel'))+' <small>'+esc(I18N.t('common.optional'))+'</small></label><textarea id="start-borrow-'+id+'" data-ref-note rows="2" maxlength="2000" placeholder="'+esc(I18N.t('start.inspiration.borrowPlaceholder'))+'"'+(disabled?' disabled':'')+'>'+esc(n.note)+'</textarea><div class="start-note-time'+(n.time!==null?' is-attached':'')+'"><span>'+esc(position)+'</span>'+(n.time!==null?'<button type="button" class="text-button" data-ref-remove-time>'+esc(I18N.t('referenceNotes.actions.removeTimestamp'))+'</button>':'')+'</div>'+(d.media?'<button type="button" class="secondary start-note-timestamp" data-ref-timestamp'+(disabled||inPreview&&!(host.querySelector('video')?.readyState>=1)?' disabled':'')+'>'+esc(I18N.t('feedback.actions.addTimestamp'))+'</button>':'<label class="start-note-focus" for="start-focus-'+id+'">'+esc(I18N.t('start.inspiration.focusLabel'))+' <small>'+esc(I18N.t('common.optional'))+'</small><input id="start-focus-'+id+'" data-ref-focus maxlength="1000" value="'+esc(n.focus)+'" placeholder="'+esc(I18N.t('start.inspiration.focusPlaceholder'))+'"'+(disabled?' disabled':'')+'></label>')+'<p class="start-note-helper">'+esc(inPreview&&noteLoading?I18N.t('start.inspiration.helper.loading'):inPreview&&noteError?noteError:stale(t)?I18N.t('start.inspiration.helper.stale'):choose(t)?I18N.t('start.inspiration.helper.chosen'):I18N.t('start.inspiration.helper.default'))+'</p>'+(inPreview&&noteError?'<button type="button" class="text-button" data-ref-note-retry>'+esc(I18N.t('start.inspiration.helper.retry'))+'</button>':'')+'</section>';
  }
  function summaryNote(r,i){
   const n=noteValue(r),position=n.time!==null?I18N.t('referenceNotes.position.at',{time:exact(n.time)}):n.focus.trim();
   return '<label for="start-summary-note-'+i+'">'+esc(I18N.t('referenceNotes.borrow.label'))+'</label><textarea id="start-summary-note-'+i+'" data-ref-summary-note="'+i+'" rows="2" maxlength="2000" placeholder="'+esc(I18N.t('start.inspiration.summaryNotePlaceholder'))+'">'+esc(n.note)+'</textarea>'+(position?'<small class="start-summary-position">'+esc(position)+'</small>':'')+(!isLink(r)?'<details class="start-source-options"><summary>'+esc(I18N.t('start.inspiration.referenceDetailsSummary'))+'</summary>'+composer(r,'summary-'+i)+(r.message.split('\n').length>2?'<p>'+esc(r.message.split('\n').slice(2).join('\n'))+'</p>':'')+'</details>':'');
  }
  function summaryRender(){
   const rows=get(),selection=selectedTargets();
   summary.innerHTML='<div class="start-reference-actions"><button type="button" class="secondary" data-ref-browse>'+esc(I18N.t('start.inspiration.browseLibrary'))+'</button><button type="button" class="secondary" data-ref-paste aria-expanded="'+linkOpen+'" aria-controls="start-link-entry">'+esc(I18N.t('start.inspiration.pasteLink'))+'</button>'+(selection.length?'<button type="button" class="text-button" data-ref-import>'+esc(selection.length===1?I18N.t('start.inspiration.useSelectedOne'):I18N.t('start.inspiration.useSelectedMany',{n:selection.length}))+'</button>':'')+'</div><div id="start-link-entry"'+(linkOpen?'':' hidden')+'><label for="start-video-link">'+esc(I18N.t('start.inspiration.videoLinkLabel'))+'</label><div class="start-link-input"><input id="start-video-link" type="url" inputmode="url" maxlength="10000" placeholder="https://…" value="'+esc(getLinkDraft())+'"><button type="button" class="secondary" data-ref-add-link>'+esc(I18N.t('start.inspiration.addLinkButton'))+'</button></div><p class="start-field-help">'+esc(I18N.t('start.inspiration.linkHelp'))+'</p></div><div class="start-chosen-references">'+rows.map((r,i)=>'<article class="start-chosen-reference"><div>'+(isLink(r)?'<span class="start-link-icon" aria-hidden="true">↗</span>':'<button type="button" class="start-chosen-preview" data-ref-watch="'+esc(r.reference_id)+'"'+(r.example_id?' data-example-id="'+esc(r.example_id)+'"':'')+' aria-label="'+esc(I18N.t('start.inspiration.viewAria',{title:r.details.label||r.details.title}))+'"><img src="'+esc(r.details.poster)+'" alt=""></button>')+'<div><strong>'+esc(r.details.title)+'</strong>'+(isLink(r)?'<a href="'+esc(r.url)+'" target="_blank" rel="noopener noreferrer">'+esc(r.url)+'</a>':'<span>'+esc([r.details.label,r.details.creator,r.slide?I18N.t('referenceNotes.scope.slide',{n:r.slide}):''].filter(Boolean).join(' · '))+'</span>')+'</div><button type="button" class="text-button" data-ref-remove="'+i+'" aria-label="'+esc(I18N.t('start.inspiration.removeFromProjectAria',{title:r.details.label||r.details.title}))+'">'+esc(I18N.t('start.inspiration.removeButton'))+'</button></div>'+summaryNote(r,i)+'</article>').join('')+'</div><p class="start-reference-status" role="status">'+esc(message)+'</p>';
   summary.querySelectorAll('[data-ref-import],[data-ref-browse]').forEach(b=>b.disabled=busy);state();
  }
  let linkOpen=!!getLinkDraft();
  function addLink(){
   const input=summary.querySelector('#start-video-link');
   try{const row=link(input.value),index=get().findIndex(r=>targetKey(r)===targetKey(row));
    if(index<0){if(get().length>=60)throw Error(I18N.t('start.inspiration.error.maxReferences'));set([...get(),row]);}
    setLinkDraft('');linkOpen=false;message='';summaryRender();summary.querySelector('#start-summary-note-'+(index<0?get().length-1:index))?.focus();
   }catch(error){message=error.message;summary.querySelector('.start-reference-status').textContent=message;input.focus();}
  }
  function pause(){const video=host.querySelector('video');if(video)video.pause();}
  function media(t){const d=resolve(t);return '<div class="start-reference-preview">'+(d.media?'<video controls muted playsinline preload="metadata" poster="'+esc(d.poster)+'" src="'+esc(d.media)+'" aria-label="'+esc(I18N.t('start.inspiration.previewAria',{label:d.label||d.title}))+'"></video>':'<img src="'+esc(d.poster)+'" alt="'+esc(d.title)+'">')+'<div><strong>'+esc(d.label||d.title)+'</strong><p>'+esc(d.creator)+(d.kind==='technique'?' · '+exact(d.start)+'–'+exact(d.end):'')+'</p><p>'+esc(d.description)+'</p>'+(!d.media?'<small>'+esc(d.status==='not_analyzed'?I18N.t('start.inspiration.awaitingAnalysis'):I18N.t('start.inspiration.coverOnlyNote'))+'</small>':'')+'</div></div>';}
  const previewNote=t=>'<div id="start-preview-note">'+composer(t,'preview',true)+'</div>';
  function footer(){
   const pending=preview&&!choose(preview);
   host.querySelector('.project-start-foot>div').innerHTML=(pending?'<button type="button" class="primary" data-ref-pick="'+esc(preview.reference_id)+'"'+(preview.example_id?' data-example-id="'+esc(preview.example_id)+'"':'')+(busy||noteLoading||noteError||stale(preview)?' disabled':'')+'>'+esc(preview.example_id?I18N.t('start.inspiration.addThisExample'):I18N.t('start.inspiration.addThisReference'))+'</button>':'')+'<button type="button" class="'+(pending?'secondary':'primary')+'" data-ref-done>'+esc(get().length?I18N.t('start.inspiration.useSelectedCount',{n:get().length}):I18N.t('start.inspiration.backToProjectShort'))+'</button>';
  }
  function render(){
   pause();status.textContent=message;footer();level(visible?(family||preview?'reference':'library'):'project');
   host.querySelector('[data-ref-back]').textContent=family||preview?I18N.t('start.inspiration.backToReferences'):I18N.t('start.inspiration.backToProject');
   host.querySelector('.start-picker-tools').hidden=!!family||!!preview;
   host.querySelectorAll('[data-ref-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.refKind===kind)));
   host.querySelectorAll('[data-ref-source]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.refSource===collection)));
   if(loading){results.innerHTML='<p class="start-picker-empty">'+esc(I18N.t('start.inspiration.loadingLibrary'))+'</p>';return;}
   if(family){
    const t=item(family);if(!t||!isTech(t)){family=null;preview=null;return render();}
    const examples=browseExamples(t).filter(x=>matches(source(x.style_id))),chosen=preview?.example_id||examples[0]?.id;
    preview={reference_id:t.id,example_id:chosen,slide:null};
    if(!chosen){family=null;preview=null;return render();}
    results.innerHTML='<h3>'+esc(t.title)+'</h3>'+media(preview)+'<div class="start-example-list" role="radiogroup" aria-label="'+esc(I18N.t('start.inspiration.chooseExampleAria'))+'">'+examples.map(x=>'<button type="button" class="start-example" data-ref-example="'+esc(x.id)+'" role="radio" aria-checked="'+(x.id===chosen)+'" tabindex="'+(x.id===chosen?'0':'-1')+'"><img src="'+esc(x.poster)+'" alt=""><span><strong>'+esc(x.label)+'</strong><small>'+esc(source(x.style_id).creator)+' · '+exact(x.start)+'–'+exact(x.end)+'</small></span><span class="choice-check" aria-hidden="true"></span></button>').join('')+'</div>'+previewNote(preview);
   }else if(preview){results.innerHTML=media(preview)+previewNote(preview);}
   else{
    const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let list=kind==='videos'?browseEntries().filter(e=>!isCarousel(e)&&matches(e)):browseTechniques().filter(t=>browseExamples(t).some(x=>matches(source(x.style_id))));
    list=list.filter(e=>terms.every(q=>[e.title,e.summary,e.creator,...(e.tags||[]),...(e.examples||[]).flatMap(x=>[x.label,source(x.style_id)?.creator])].join(' ').toLowerCase().includes(q)));
    results.innerHTML=list.length?'<div class="start-reference-grid">'+list.map(e=>{const x=isTech(e)?browseExamples(e).find(x=>matches(source(x.style_id))):null,s=x?source(x.style_id):e,t={reference_id:e.id,example_id:x?.id||null,slide:null},on=isTech(e)?get().some(r=>r.reference_id===e.id):choose(t),exampleCount=browseExamples(e).filter(x=>matches(source(x.style_id))).length;return '<article class="start-reference-card"><button type="button" class="start-reference-art" data-ref-watch="'+esc(e.id)+'" aria-label="'+esc(I18N.t(isTech(e)?'start.inspiration.ariaChooseExample':'start.inspiration.ariaPreview',{title:e.title}))+'"><img loading="lazy" src="'+esc(x?.poster||e.poster)+'" alt=""><span>'+esc(isTech(e)?I18N.t('start.inspiration.chooseExampleLabel'):I18N.t('start.inspiration.previewLabel'))+'</span></button><div><strong>'+esc(e.title)+'</strong><small>'+esc(isTech(e)?I18N.t(exampleCount===1?'start.inspiration.categoryExampleCountOne':'start.inspiration.categoryExampleCountMany',{category:e.category,count:exampleCount}):s.creator)+'</small><button type="button" class="'+(on?'secondary':'text-button')+'" '+(isTech(e)?'data-ref-watch':'data-ref-pick')+'="'+esc(e.id)+'">'+esc(isTech(e)?on?I18N.t('start.inspiration.chooseExampleSelected'):I18N.t('start.inspiration.chooseExampleLabel'):on?I18N.t('start.inspiration.selectedCheck'):I18N.t('start.inspiration.addReferencePlus'))+'</button></div></article>';}).join('')+'</div>':'<p class="start-picker-empty">'+esc(query?I18N.t('start.inspiration.noMatches'):I18N.t('start.inspiration.emptyLibrary'))+'</p>';
   }
   footer();const video=host.querySelector('video');if(video){const d=resolve(preview),n=noteValue(rowFor(preview));video.addEventListener('loadedmetadata',()=>{video.currentTime=n.time!==null&&n.time>=d.start&&(!d.end||n.time<d.end)?n.time:d.start;const button=host.querySelector('[data-ref-timestamp]');if(button)button.disabled=noteLoading||!rowFor(preview)||stale(preview);});if(d.end)video.addEventListener('timeupdate',()=>{if(video.currentTime>=d.end||video.currentTime<d.start){video.pause();video.currentTime=d.start;}});}
   host.querySelectorAll('[data-ref-pick]').forEach(b=>b.disabled=busy||!!preview&&(noteLoading||!!noteError||stale(preview)));
  }
  function paintPreviewNote(){const el=host.querySelector('#start-preview-note');if(el&&preview)el.innerHTML=composer(preview,'preview',true);footer();}
  async function ensure(t){
   const token=++noteRun;noteLoading=true;noteError='';paintPreviewNote();
   try{const current=await capture(t);if(token!==noteRun||!visible||!preview||targetKey(preview)!==targetKey(t))return;fresh.set(targetKey(t),current);if(!rowFor(t))stash(current);}
   catch(error){if(token===noteRun)noteError=error.message;}
   finally{if(token===noteRun){noteLoading=false;summaryRender();paintPreviewNote();}}
  }
  function hide(focus=true){++run;++noteRun;visible=false;pause();showPicker(false);level('project');if(focus)summary.querySelector('[data-ref-browse]')?.focus();}
  function back(){
   if(!visible)return false;
   if(family||preview){++noteRun;family=null;preview=null;noteLoading=false;noteError='';message='';render();body.scrollTop=browseScroll;host.querySelectorAll('[data-ref-watch]').forEach(b=>{if(b.dataset.refWatch===browseFocus)b.focus({preventScroll:true});});}
   else hide();return true;
  }
  async function open(){visible=true;family=null;preview=null;loading=true;message='';showPicker(true);render();const token=++run;
   try{await window.refreshReferenceCatalog();if(token!==run)return;loading=false;render();body.scrollTop=browseScroll;host.querySelector('#start-reference-search').focus({preventScroll:true});}
   catch{if(token!==run)return;loading=false;results.innerHTML='<p class="start-picker-empty">'+esc(I18N.t('start.inspiration.error.libraryLoadFailed'))+'</p><button type="button" class="secondary" data-ref-retry>'+esc(I18N.t('start.inspiration.helper.retry'))+'</button>';}
  }
  function watch(t){
   if(!family&&!preview){browseScroll=body.scrollTop;browseFocus=t.reference_id;}
   const e=item(t.reference_id);if(!e)return;
   visible=true;loading=false;family=isTech(e)?e.id:null;preview=isTech(e)?{...target(t),example_id:t.example_id||browseExamples(e).find(x=>matches(source(x.style_id)))?.id}:target(t);
   if(!preview.example_id&&family){preview=null;family=null;return;}
   noteLoading=true;noteError='';message='';showPicker(true);render();body.scrollTop=0;ensure(preview);
  }
  async function add(targets){if(busy)return;busy=true;message=I18N.t('start.inspiration.loadingReferencesAndNotes');summaryRender();if(visible)render();const token=++run;
   try{const captured=[];for(const t of targets){if(get().some(r=>targetKey(r)===targetKey(t)))continue;if(get().length+captured.length>=60)throw Error(I18N.t('start.inspiration.error.maxReferences'));const base=fresh.get(targetKey(t))||await capture(t),old=rowFor(t);if(old&&hasNote(old)&&old.context_revision!==base.context_revision)throw Error(I18N.t('start.inspiration.error.sourceChangedReview'));const row={...base,...noteValue(old)};await validate([row]);captured.push(row);}if(token!==run)return;const next=get().slice();for(const row of captured)if(!next.some(r=>targetKey(r)===targetKey(row)))next.push(row);set(next);message='';summaryRender();if(visible)render();}
   catch(error){if(token===run){message=error.message;summaryRender();if(visible)render();}}
   finally{busy=false;if(token===run){summaryRender();if(visible)render();}}
  }
  function noteTarget(button){const el=button.closest('[data-project-note]');if(!el)return null;try{const [reference_id,example_id,slide]=JSON.parse(decodeURIComponent(el.dataset.projectNote));return {reference_id,example_id,slide};}catch{return null;}}
  function noteClick(b){
   const t=noteTarget(b);if(!t)return false;
   if(b.hasAttribute('data-ref-timestamp')){
    if(!visible||!preview||targetKey(t)!==targetKey(preview)){watch(t);return true;}
    const video=host.querySelector('video'),d=resolve(t);if(!video||!Number.isFinite(video.currentTime))return true;
    video.pause();const time=video.currentTime;if(time<d.start||d.end&&time>d.end){noteError=I18N.t('start.inspiration.error.momentOutsideExample');paintPreviewNote();return true;}
    update(t,{time,focus:''});summaryRender();paintPreviewNote();return true;
   }
   if(b.hasAttribute('data-ref-remove-time')){update(t,{time:null});if(visible)paintPreviewNote();summaryRender();return true;}
   if(b.hasAttribute('data-ref-note-retry')){ensure(t);return true;}
   if(b.hasAttribute('data-ref-rebase')){const now=fresh.get(targetKey(t)),old=rowFor(t);if(now&&old){const next={...now,...noteValue(old),time:null,focus:''};if(choose(t))set(get().map(r=>targetKey(r)===targetKey(t)?next:r));else stash(next);summaryRender();paintPreviewNote();}return true;}
   return false;
  }
  function noteInput(event){
   if(event.target.id==='start-video-link'){setLinkDraft(event.target.value);return;}
   if(event.target.dataset.refSummaryNote!==undefined){const index=Number(event.target.dataset.refSummaryNote);set(get().map((r,i)=>i===index?{...r,note:event.target.value.slice(0,2000)}:r));return;}
   if(event.target.dataset.refNote===undefined&&event.target.dataset.refFocus===undefined)return;
   const t=noteTarget(event.target);if(!t||stale(t))return;
   update(t,event.target.dataset.refNote!==undefined?{note:event.target.value}:{focus:event.target.value,time:null});if(visible)summaryRender();
  }
  host.addEventListener('click',event=>{
   const b=event.target.closest('button');if(!b)return;if(noteClick(b))return;
   if(b.hasAttribute('data-ref-done'))return hide();
   if(b.hasAttribute('data-ref-back'))return back();
   if(b.hasAttribute('data-ref-retry'))return open();
   if(b.dataset.refKind){kind=b.dataset.refKind;message='';browseScroll=0;return render();}
   if(b.dataset.refSource){collection=b.dataset.refSource;message='';browseScroll=0;return render();}
   if(b.dataset.refWatch)return watch({reference_id:b.dataset.refWatch,example_id:b.dataset.exampleId||null,slide:null});
   if(b.dataset.refExample){const id=b.dataset.refExample;watch({reference_id:family,example_id:id,slide:null});host.querySelectorAll('[data-ref-example]').forEach(b=>{if(b.dataset.refExample===id)b.focus();});return;}
   if(b.dataset.refPick){const t={reference_id:b.dataset.refPick,example_id:b.dataset.exampleId||null,slide:null};if(choose(t)){stash(rowFor(t));set(get().filter(r=>targetKey(r)!==targetKey(t)));summaryRender();render();}else add([t]);}
  });
  host.addEventListener('keydown',event=>{
   const button=event.target.closest('[data-ref-example]');if(!button)return;
   const buttons=[...host.querySelectorAll('[data-ref-example]')],direction={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[event.key];
   if(direction||event.key==='Home'||event.key==='End'){event.preventDefault();const index=event.key==='Home'?0:event.key==='End'?buttons.length-1:(buttons.indexOf(button)+direction+buttons.length)%buttons.length;buttons[index].click();}
  });
  host.querySelector('#start-reference-search').addEventListener('input',event=>{query=event.target.value;browseScroll=0;render();});
  host.addEventListener('input',noteInput);summary.addEventListener('input',noteInput);
  summary.addEventListener('keydown',event=>{if(event.target.id==='start-video-link'&&event.key==='Enter'){event.preventDefault();addLink();}});
  summary.addEventListener('click',event=>{const b=event.target.closest('button');if(!b)return;if(noteClick(b))return;if(b.hasAttribute('data-ref-paste')){linkOpen=!linkOpen;summaryRender();summary.querySelector(linkOpen?'#start-video-link':'[data-ref-paste]')?.focus();return;}if(b.hasAttribute('data-ref-add-link'))return addLink();if(b.dataset.refWatch)return watch({reference_id:b.dataset.refWatch,example_id:b.dataset.exampleId||null,slide:null});if(b.hasAttribute('data-ref-browse'))open();if(b.hasAttribute('data-ref-import'))add(selectedTargets());if(b.dataset.refRemove!==undefined){const row=get()[Number(b.dataset.refRemove)];if(row&&!isLink(row))stash(row);set(get().filter((_,i)=>i!==Number(b.dataset.refRemove)));summaryRender();}});
  return {render:summaryRender,open,hide,back,watch,get visible(){return visible;},get busy(){return busy;}};
 }
 return {create,restore,text,validate,capture,resolve,targetKey,noteValue,link};
})();
