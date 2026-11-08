/* Navigation and previews only. The editing chat and existing project files drive production. */
window.Studio=(()=>{
 let projects=[],loaded=false,failed=false,filter='all',query='',activeProject=null,activeArtifact=null,frameIndex=0,request=0;
 let currentSection='projects';
 let savingReview=false, routeRequest=0, indexPending=null, lastRefresh=0, pendingUpdate=false;
 const stageChoices=new Map();
 async function loadProjects(){
  if(indexPending)return indexPending;
  indexPending=(async()=>{const r=await fetch('/projects.json',{cache:'no-store'});if(!r.ok)throw Error(I18N.t('projects.loadError'));const result=await r.json();projects=result.projects;loaded=true;failed=false;lastRefresh=Date.now();void window.StudioStart?.checkArrival?.(projects);return projects;})();
  try{return await indexPending;}finally{indexPending=null;}
 }
 async function checkUpdates(force=false){
  if(document.hidden||force!==true&&Date.now()-lastRefresh<4000)return;
  const before=JSON.stringify(projects);
  try{await loadProjects();if(before===JSON.stringify(projects))return;
   if(currentSection==='projects')home();
   else if(currentSection==='project'&&activeProject){
    const updated=projects.find(p=>p.id===activeProject.id);
    if(updated&&JSON.stringify(updated)===JSON.stringify(activeProject))return;
    const params=new URLSearchParams(location.hash.slice(1)),video=$('#project-artifact video');
    if(updated&&!params.has('artifact')&&!window.ProjectFeedback?.hasDraft()&&!window.ProjectScript?.hasDraft()&&!window.ProjectScript?.isEditing()&&!window.ProjectScript?.hasPendingFeedback()&&(!video||video.paused)){
     projectPage(updated,null,0);return;
    }
    pendingUpdate=true;$('#project-update').hidden=false;
    const controls=$('#review-controls');if(controls)controls.innerHTML='<p class="review-save-note">'+I18N.t('project.newInfoAvailable')+'</p>';
   }
  }catch{if(currentSection==='project'&&$('#project-update')){$('#project-update').hidden=false;$('#project-update-status').textContent=I18N.t('project.couldNotCheckUpdates');}}
 }
 window.addEventListener('focus',()=>checkUpdates(true));
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkUpdates(true);});
 setInterval(checkUpdates,20000);
 const h=esc,updateRequestBase=$('#studio-update-request').value;
 const stateLabel=p=>p.stale?I18N.t('project.state.notesUpdated'):p.review_action==='reopened'?I18N.t('project.state.changesRequested'):p.state==='in_progress'&&p.review_decision?.action==='approve'?(p.review_decision.kind==='spoken_cut'?I18N.t('project.state.spokenCutApproved'):I18N.t('project.state.storyboardApproved')):({review:I18N.t('project.state.readyForReview'),approved:I18N.t('project.state.approvedEdit'),final:I18N.t('project.state.finalAssetsReady'),draft:I18N.t('project.state.draft')}[p.state]||I18N.t('project.state.inProgress'));
 const decisionLabel=(d,p)=>d.action==='reopen'?I18N.t('review.decision.reopen'):d.kind==='spoken_cut'?I18N.t('review.decision.approveSpokenCut'):d.kind==='storyboard'?I18N.t('review.decision.approveStoryboard'):d.kind==='final'?(p.format==='presentation'?I18N.t('review.decision.approveSectionFinal'):I18N.t('review.decision.approveFinal')):I18N.t('review.decision.approveCheckpoint');
 const projectHash=(p,a=null,f=null)=>{const params=new URLSearchParams({project:p.id});if(a){if(a.type==='script')params.set('stage','script');else params.set('artifact',a.id);}if(f!==null)params.set('frame',String(f+1));return '#'+params;};
 function pause(){document.querySelectorAll('#project-page video').forEach(v=>v.pause());}
 function section(next){
  if(next!=='project')window.ProjectFeedback?.retain();
  if(next!=='effects')window.EffectsBoard?.leave();
  currentSection=next;pause();
  for(const id of ['projects','project','guide','library','updates','effects'])$('#'+id+'-page').hidden=id!==next;
  document.querySelectorAll('[data-section]').forEach(a=>{const on=a.dataset.section===(next==='project'?'projects':next);if(on)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  const label=next==='project'?(activeProject?.title||I18N.t('project.openingProject')):next==='library'?$('#library-nav-label').textContent:next==='guide'?I18N.t('app.nav.guide'):next==='updates'?I18N.t('app.nav.updates'):next==='effects'?I18N.t('app.nav.effects'):I18N.t('app.nav.projects');
  document.title=(window.studioName||I18N.t('app.brand.name'))+' · '+label;
  $('#studio-footer-note').textContent=next==='library'?I18N.t('footer.note.library'):I18N.t('footer.note.default');
  updateSelection();
 }
 function card(p){
  const counts=p.artifacts.length;
  return '<article class="project-card"><a class="project-cover" href="'+projectHash(p)+'" aria-label="'+I18N.t('projects.card.openAria',{title:h(p.title)})+'">'+(p.cover?'<img src="'+h(p.cover)+'" alt="'+h(p.title)+' — '+I18N.t('library.alt.projectArtwork')+'" loading="lazy">':'<span class="project-placeholder">↗</span>')+'<span class="project-format">'+({presentation:I18N.t('projects.format.presentation'),carousel:I18N.t('projects.format.carousel'),video:I18N.t('projects.format.video')}[p.format]||I18N.t('projects.format.project'))+'</span><span class="project-state '+h(p.stale?'stale':p.state)+'">'+h(stateLabel(p))+'</span></a><div class="project-card-copy"><p class="project-subtitle">'+h(p.subtitle)+'</p><a class="project-title" href="'+projectHash(p)+'"><h2><bdi>'+h(p.title)+'</bdi></h2><span>↗</span></a><p>'+h(p.stale?I18N.t('projects.card.staleNotice'):p.summary)+'</p><div class="project-card-foot"><span>'+I18N.t('projects.card.savedVersions',{count:counts})+'</span><a href="'+projectHash(p)+'">'+I18N.t('library.detail.openProject')+'</a></div></div></article>';
 }
 function renderCards(){
  const matches=p=>filter==='all'||(filter==='review'?(p.state==='review'||p.stale):filter==='approved'?['approved','final'].includes(p.state)&&!p.stale:p.format===filter);
  const list=projects.filter(p=>matches(p)&&[p.title,p.subtitle,p.summary].join(' ').toLowerCase().includes(query.toLowerCase().trim()));
  $('#project-grid').innerHTML=list.map(card).join('');$('#project-empty').hidden=!!list.length;
  $('#project-results').textContent=list.length===1?I18N.t('projects.resultsOne'):I18N.t('projects.resultsMany',{n:list.length});
 }
 function home(){
  activeProject=null;activeArtifact=null;section('projects');
  const attention=projects.filter(p=>p.stale||p.state==='review'||p.review_action==='reopened');
  const resume=attention[0]||projects[0];
  $('#projects-page').innerHTML=`<section class="home-heading"><div><p class="eyebrow">${I18N.t('projects.page.aria')}</p><h1>${projects.length?I18N.t('projects.home.welcomeBack'):I18N.t('projects.home.firstVideo')}</h1><p>${projects.length?I18N.t('projects.home.yourWork'):I18N.t('projects.home.createInChat')}</p></div><button class="primary" data-new-video>${I18N.t('projects.home.newVideo')}</button></section>
   <aside class="starter-arrival" id="starter-arrival" hidden><p aria-live="polite"><strong>${I18N.t('projects.home.scriptReady')}</strong><span id="starter-arrival-title"></span></p><button class="primary" data-open-starter-draft>${I18N.t('projects.home.openDraft')}</button></aside>
   ${resume?`<a class="resume-project" href="${projectHash(resume)}"><div>${resume.cover?`<img src="${h(resume.cover)}" alt="">`:''}</div><section><p class="eyebrow">${attention.length?I18N.t('projects.home.readyForAttention'):I18N.t('projects.home.pickUpWhereLeft')}</p><h2><bdi>${h(resume.title)}</bdi></h2><p>${h(resume.next_step||resume.summary)}</p><strong>${attention.length?I18N.t('projects.home.reviewProject'):I18N.t('projects.home.openProjectArrow')} <span class="arrow">→</span></strong></section><span class="project-state ${h(resume.state)}">${h(stateLabel(resume))}</span></a>`:`<div class="first-project"><h2>${I18N.t('projects.home.bringIdea')}</h2><p>${I18N.t('projects.home.startWithFootage')}</p><button class="plain-link" data-new-video>${I18N.t('projects.home.newVideoArrow')}</button><a href="#videos" class="plain-link">${I18N.t('projects.home.findInspiration')}</a></div>`}
   <section class="project-list"><div class="project-list-head"><h2>${I18N.t('projects.home.yourProjects')}</h2><p id="project-results" aria-live="polite"></p></div><div class="project-toolbar"><div class="project-filters" role="group" aria-label="${I18N.t('app.nav.aria')}"><button data-project-filter="all" aria-pressed="${filter==='all'}">${I18N.t('projects.filter.all')}</button><button data-project-filter="review" aria-pressed="${filter==='review'}">${I18N.t('projects.filter.review')}</button><button data-project-filter="approved" aria-pressed="${filter==='approved'}">${I18N.t('projects.filter.approved')}</button><button data-project-filter="presentation" aria-pressed="${filter==='presentation'}">${I18N.t('projects.filter.presentations')}</button></div><input id="project-search" type="search" placeholder="${I18N.t('projects.search.placeholder')}" aria-label="${I18N.t('projects.search.aria')}" value="${h(query)}"></div>${failed?'<p class="project-notice" role="alert">'+I18N.t('projects.loadFailedNotice')+'</p>':''}<div id="project-grid" class="project-grid"></div><div id="project-empty" class="empty" hidden><em>${!projects.length?I18N.t('projects.empty.readyTitle'):I18N.t('projects.empty.noMatchTitle')}</em><p>${!projects.length?I18N.t('projects.empty.readyBody'):I18N.t('projects.empty.noMatchBody')}</p></div></section>`;
  window.StudioStart?.renderArrival?.();
  window.WelcomeCard?.render?.();
  if(!loaded&&!failed)$('#project-results').textContent=I18N.t('projects.loadingShort');else renderCards();
 }
 function guide(){
  activeProject=null;section('guide');
  const steps=[
   [I18N.t('guide.step1.title'),I18N.t('guide.step1.body'),I18N.t('guide.step1.small')],
   [I18N.t('guide.step2.title'),I18N.t('guide.step2.body'),I18N.t('guide.step2.small')],
   [I18N.t('guide.step3.title'),I18N.t('guide.step3.body'),I18N.t('guide.step3.small')],
   [I18N.t('guide.step4.title'),I18N.t('guide.step4.body'),I18N.t('guide.step4.small')],
   [I18N.t('guide.step5.title'),I18N.t('guide.step5.body'),I18N.t('guide.step5.small')],
   [I18N.t('guide.step6.title'),I18N.t('guide.step6.body'),I18N.t('guide.step6.small')]
  ];
  $('#guide-page').innerHTML='<section class="studio-hero guide-hero"><div><p class="eyebrow">'+I18N.t('guide.hero.eyebrow')+'</p><h1>'+I18N.t('guide.hero.titleLine1')+'<br><em>'+I18N.t('guide.hero.titleLine2')+'</em></h1><p class="lede">'+I18N.t('guide.hero.lede')+'</p></div><svg class="guide-loop" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width=".9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 12a9 9 0 0 1 15.357-6.364L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.357 6.364L3 16M8 16H3v5"/></svg></section><div class="workflow-grid">'+steps.map((s,i)=>'<article class="workflow-step"><span class="step-number">0'+(i+1)+'</span><div><h2>'+s[0]+'</h2><p>'+s[1]+'</p><small>'+s[2]+'</small></div></article>').join('')+'</div><section class="guide-start guide-start-callout"><div><p class="eyebrow">'+I18N.t('guide.callout.eyebrow')+'</p><h2>'+I18N.t('guide.callout.titleLine1')+'<br><em>'+I18N.t('guide.callout.titleLine2')+'</em></h2><p>'+I18N.t('guide.callout.body1')+'</p></div><div><p>'+I18N.t('guide.callout.body2')+'</p><button class="primary" data-new-video>'+I18N.t('projects.home.newVideo')+'</button></div></section><section class="guide-reference"><p class="eyebrow">'+I18N.t('guide.reference.eyebrow')+'</p><h2>'+I18N.t('guide.reference.title')+'</h2><div class="guide-reference-columns"><div><h3>'+I18N.t('guide.reference.one.title')+'</h3><p>'+I18N.t('guide.reference.one.body')+'</p></div><div><h3>'+I18N.t('guide.reference.mix.title')+'</h3><p>'+I18N.t('guide.reference.mix.body')+'</p></div><div><h3>'+I18N.t('guide.reference.collection.title')+'</h3><p>'+I18N.t('guide.reference.collection.body')+'</p></div></div><p class="guide-boundary">'+I18N.t('guide.reference.boundary')+'</p><a class="plain-link" href="#videos">'+I18N.t('guide.browseLibrary')+'</a> <a class="plain-link" href="quickstart.html">'+I18N.t('guide.seeExamples')+'</a></section><div class="guide-footnote"><strong>'+I18N.t('guide.footnote.lead')+'</strong> '+I18N.t('guide.footnote.rest')+'</div>';
 }
 function downloads(a){return (a.downloads||[]).map(d=>d.available?'<a href="'+h(d.url)+'" download="'+h(d.path.split('/').pop())+'">'+h(d.label)+' ↓</a>':'<span class="unavailable">'+h(d.label)+' · unavailable</span>').join('');}
 function downloadLink(a,label){return a.available&&a.url?'<a href="'+h(a.url)+'" download="'+h(a.path.split('/').pop())+'">'+label+' ↓</a>':'';}
 function projectPage(p,artifactId,wantedFrame){
  window.ProjectScript?.retain();
  window.ProjectFeedback?.retain();pendingUpdate=false;activeProject=p;section('project');
  const primary=p.artifacts.find(a=>a.id===p.primary_artifact),a=artifactId==='@script'&&p.format==='video'?ReviewLayout.script(p):artifactId?p.artifacts.find(a=>a.id===artifactId):p.stage==='script'&&p.format==='video'?ReviewLayout.script(p):primary;
  $('#project-page').innerHTML=`<a class="project-back" href="#projects">${I18N.t('project.backToAll')}</a><section class="project-heading compact-heading"><div><p class="eyebrow">${h(p.subtitle||'')}</p><h1><bdi>${h(p.title)}</bdi></h1><div class="project-status-line"><span class="project-state ${h(p.stale?'stale':p.state)}">${h(stateLabel(p))}</span><span>${h(p.next_step||'')}</span></div></div><button class="secondary" data-copy-project>${I18N.t('project.copyLink')}</button></section><div id="project-update" class="project-update" hidden><p id="project-update-status">${I18N.t('project.newWorkAvailable')}</p><button class="secondary" data-load-update>${I18N.t('project.loadUpdates')}</button></div>${p.stale?'<p class="project-notice">'+I18N.t('project.staleReconcile')+'</p>':''}<div id="review-navigation"></div><section id="project-script-panel" hidden></section><section id="project-artifact" aria-label="${I18N.t('project.versionPreviewAria')}"></section><div id="project-materials"></div><div id="project-choices"></div><div id="project-send"></div>${ReviewLayout.details(p)}`;
  window.MaterialsUI?.mount($('#project-materials'),p.id);
  window.ChoicesUI?.mount($('#project-choices'),p.id);
  if(p.format==='video')window.SendUI?.mount($('#project-send'),p.id);
  if(!a){activeArtifact=null;$('#project-artifact').innerHTML='<h2>'+I18N.t('project.versionUnavailable.title')+'</h2><p>'+I18N.t('project.versionUnavailable.body')+'</p><button class="secondary" data-back-current>'+I18N.t('project.viewLatestVersion')+'</button>';return;}
  showArtifact(a,Number.isInteger(wantedFrame)?wantedFrame:0,false);
  const requestedTime=Number(new URLSearchParams(location.hash.slice(1)).get('time'));
  const v=$('#project-artifact video');if(v&&Number.isFinite(requestedTime)&&requestedTime>=0){const seek=()=>{if(requestedTime<=v.duration)v.currentTime=requestedTime;};if(v.readyState>=1)seek();else v.addEventListener('loadedmetadata',seek,{once:true});}
 }
 function reviewControls(){
  const box=$('#review-controls'),p=activeProject;if(!box||!p)return;
  const decision=p.review;
  if(activeArtifact?.type==='document'){box.innerHTML='<p class="review-save-note">'+I18N.t('project.planningDocNote')+'</p>';return;}
  if(!decision){box.innerHTML='<p class="review-save-note">'+I18N.t('project.reloadToLoadActions')+'</p>';return;}
  if(activeArtifact?.id!==p.primary_artifact){box.innerHTML='';return;}
  const help=decision.action==='reopen'?I18N.t('project.help.reopen'):decision.kind==='final'?I18N.t('project.help.final'):I18N.t('project.help.checkpoint');
  box.innerHTML='<p class="review-target">'+h(decision.checkpoint)+' <strong>'+h(decision.version)+'</strong></p><button class="primary review-action" data-review-action="'+h(decision.action)+'" '+(!decision.enabled||savingReview?'disabled':'')+'>'+h(savingReview?I18N.t('project.saving'):decisionLabel(decision,p))+'</button><p class="review-save-note">'+h(p.stale?I18N.t('project.help.staleRefresh'):!decision.enabled?I18N.t('project.help.missingFile'):help)+'</p>'+(decision.decided_at?'<p class="review-saved-date">'+I18N.t('project.decisionSavedOn')+h(new Date(decision.decided_at).toLocaleDateString(I18N.lang()))+'</p>':'')+'<p id="review-save-status" class="review-save-status" role="status"></p>';
 }
 async function saveReview(action){
  if(pendingUpdate||savingReview||!activeProject?.review?.enabled||activeArtifact?.id!==activeProject.primary_artifact)return;
  const p=activeProject,decision=p.review;
  if(action!==decision.action)return;
  const body={project_id:p.id,artifact_id:decision.artifact_id,action,revision:decision.revision,request_id:crypto.randomUUID()};
  savingReview=true;reviewControls();
  try{
   const response=await fetch('/review-action',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'review'},body:JSON.stringify(body)});
   const result=await response.json().catch(()=>({error:I18N.t('project.decisionSaveFailedRefresh')}));
   if(!response.ok)throw Error(I18N.server(result.error)||I18N.t('project.decisionSaveFailed'));
   projects=result.projects;loaded=true;
   let libraryError=false;
   if(result.library_changed)try{await window.refreshReferenceCatalog();}catch{libraryError=true;}
   savingReview=false;
   if(currentSection==='project'&&activeProject?.id===p.id){const updated=projects.find(v=>v.id===p.id);projectPage(updated,decision.artifact_id,0);}
   else if(currentSection==='project')reviewControls();
   else if(currentSection==='projects')home();
   notify(libraryError?I18N.t('project.notify.decisionSavedReload'):action==='reopen'?I18N.t('project.notify.reopened'):decision.kind==='final'?I18N.t('project.notify.approvedFinal'):I18N.t('project.notify.checkpointApproved'));
  }catch(error){
   savingReview=false;
   if(currentSection==='project'&&activeProject?.id===p.id){reviewControls();const status=$('#review-save-status');if(status){status.textContent=error.message;const button=document.createElement('button');button.className='text-button';button.dataset.refreshProject='';button.textContent=I18N.t('project.refreshProjectLink');status.append(document.createElement('br'),button);}}
   else{if(currentSection==='project')reviewControls();notify(error.message);}
  }
 }
 function showArtifact(a,index=0,update=true){
  const sameStoryboard=activeArtifact?.id===a.id&&!!a.frames;
  window.ProjectFeedback?.retain();window.ProjectScript?.retain();pause();request++;activeArtifact=a;
  frameIndex=Math.max(0,Math.min((a.frames||[]).length-1,index));
  const container=$('#project-artifact');
  container.hidden=a.type==='script';
  $('#project-page').classList.toggle('script-view',a.type==='script');
  if(sameStoryboard&&ReviewLayout.updateFrame(container,a,frameIndex)){
   window.ProjectFeedback?.render(activeProject,a,frameIndex);
   if(update)history.replaceState(null,'',projectHash(activeProject,a,frameIndex));
   return;
  }
  stageChoices.set(activeProject.id+'/'+ReviewLayout.stage(activeProject,a),a.id);
  $('#review-navigation').innerHTML=ReviewLayout.navigation(activeProject,a);
  container.innerHTML=ReviewLayout.content(activeProject,a,frameIndex);
  if(a.frames)ReviewLayout.revealFrame(container);
  reviewControls();window.ProjectFeedback?.render(activeProject,a,frameIndex);window.ProjectTools?.mount(activeProject,a);window.ProjectScript?.mount(activeProject,a);
  if(a.available&&a.type==='document'){
   const token=request;fetch(a.url,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.text();}).then(t=>{if(token===request)container.querySelector('.project-document').innerHTML=ReviewLayout.readable(t);}).catch(()=>{if(token===request)container.querySelector('.project-document').textContent=I18N.t('project.notesLoadFailed');});
  }
  const video=container.querySelector('video');
  if(video){
   let settled=false;
   const showUnplayable=()=>{if(settled)return;settled=true;video.parentElement.after(videoUnplayableNotice(a));};
   video.addEventListener('error',showUnplayable);
   // Some HEVC failures never fire `error` -- the browser reports metadata but decoded
   // nothing (videoWidth stays 0). Give it a beat after loadedmetadata before deciding
   // that's what happened, rather than reacting to a frame that just hasn't painted yet.
   video.addEventListener('loadedmetadata',()=>{setTimeout(()=>{if(!settled&&video.videoWidth===0)showUnplayable();},1500);});
  }
  if(update){history.replaceState(null,'',projectHash(activeProject,a,a.frames?frameIndex:null));(ReviewLayout.stage(activeProject,a)==='spoken'?$('#review-navigation'):container).scrollIntoView({block:'start',behavior:'auto'});}
 }
 // T9b: the message shown in the player area when a browser can't decode a version's
 // video at all -- in practice, Chrome on Windows failing on HEVC/HLG footage shot on an
 // iPhone. A real `error` event on the <video> fires this directly; showArtifact() also
 // fires it after a short loadedmetadata timeout if the browser reports metadata but never
 // actually decoded a frame (videoWidth stays 0), since some HEVC failures show up that way
 // instead of a clean `error` event. download uses the artifact's own URL/filename -- the
 // exact same bytes the <video> couldn't play, not a re-encode -- so the link always works.
 function videoUnplayableNotice(a){
  const notice=document.createElement('div');notice.className='project-video-unplayable';
  const message=document.createElement('p');message.className='project-notice';message.textContent=I18N.t('project.videoUnplayable.message');
  const link=document.createElement('a');link.href=a.url;link.download=(a.path||'').split('/').pop()||'';link.textContent=I18N.t('project.videoUnplayable.download');
  notice.append(message,link);return notice;
 }
 function enlargeFrame(){
  const f=activeArtifact?.frames?.[frameIndex];if(!f?.available)return;
  const dialog=$('#frame-dialog');dialog.querySelector('.frame-lightbox-media').innerHTML=f.media_type==='video'?`<video controls muted playsinline src="${h(f.url)}"></video>`:`<img src="${h(f.url)}" alt="${h(f.title)}">`;
  dialog.querySelector('#frame-dialog-title').textContent=`${frameIndex+1} / ${activeArtifact.frames.length} · ${f.title}`;
  dialog.querySelector('[data-lightbox-step="-1"]').disabled=frameIndex===0;dialog.querySelector('[data-lightbox-step="1"]').disabled=frameIndex===activeArtifact.frames.length-1;
  if(!dialog.open)dialog.showModal();
 }
 async function copy(text,button){
  try{await navigator.clipboard.writeText(text);const old=button.textContent;button.textContent=I18N.t('dialog.style.copiedCheck');setTimeout(()=>{if(button.isConnected)button.textContent=old;},2000);notify(I18N.t('project.copiedPasteChat'));}
  catch{$('#link-text').value=text;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}
 }
 $('#projects-page').addEventListener('click',e=>{const b=e.target.closest('[data-project-filter]');if(!b)return;filter=b.dataset.projectFilter;document.querySelectorAll('[data-project-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));renderCards();});
 $('#projects-page').addEventListener('input',e=>{if(e.target.id==='project-search'){query=e.target.value;renderCards();}});
 $('#project-page').addEventListener('click',e=>{
  const stage=e.target.closest('[data-stage]');if(stage){const rows=ReviewLayout.versions(activeProject,stage.dataset.stage),chosen=stageChoices.get(activeProject.id+'/'+stage.dataset.stage);return showArtifact(rows.find(a=>a.id===chosen)||rows[0]);}
  if(e.target.closest('[data-load-update]')){if(window.ProjectFeedback?.hasDraft()||window.ProjectScript?.hasDraft()){notify(I18N.t('project.saveDraftFirst'));return;}return route();}
  if(e.target.closest('[data-use-version]'))return copy(I18N.t('project.continueFromVersion',{title:activeProject.title,url:new URL(projectHash(activeProject,activeArtifact),location.href)}),e.target.closest('[data-use-version]'));
  if(e.target.closest('[data-enlarge-frame]'))return enlargeFrame();
  if(e.target.closest('[data-overview]')){const grid=$('.project-thumbs');grid.classList.toggle('is-overview');e.target.closest('[data-overview]').textContent=grid.classList.contains('is-overview')?I18N.t('project.backToFilmstrip'):I18N.t(activeArtifact.type==='carousel'?'project.seeAllSlides':'project.seeAllScenes',{n:activeArtifact.frames.length});if(!grid.classList.contains('is-overview'))ReviewLayout.revealFrame($('#project-artifact'));return;}
  const note=e.target.closest('[data-project-note]');if(note){const box=$('#readable-project-note'),p=activeProject;box.hidden=false;box.textContent=I18N.t('projects.loadingShort');fetch(p.source_notes[Number(note.dataset.projectNote)].url,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error();return r.text();}).then(t=>{if(activeProject===p)box.innerHTML=ReviewLayout.readable(t);}).catch(()=>box.textContent=I18N.t('project.noteLoadFailed'));return;}

  const review=e.target.closest('[data-review-action]');if(review)return saveReview(review.dataset.reviewAction);
  if(e.target.closest('[data-back-current]')){const a=activeProject.artifacts.find(a=>a.id===activeProject.primary_artifact);return showArtifact(a);}
  if(e.target.closest('[data-refresh-project]')){fetch('/projects.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{projects=data.projects;route();}).catch(()=>notify(I18N.t('project.refreshFailedRestart')));return;}
  const copyButton=e.target.closest('[data-copy-project]');if(copyButton){
   const url=new URL(projectHash(activeProject,activeArtifact,activeArtifact?.frames?frameIndex:null),location.href),video=$('#project-artifact video');
   if(video&&activeArtifact?.type==='video'&&video.currentTime>0){const params=new URLSearchParams(url.hash.slice(1));params.set('time',String(Math.round(video.currentTime*1000)/1000));url.hash=params.toString();}
   return copy(url.href,copyButton);
  }
  const artifact=e.target.closest('[data-artifact]');if(artifact){const a=activeProject.artifacts.find(a=>a.id===artifact.dataset.artifact);if(a)showArtifact(a);return;}
  const frame=e.target.closest('[data-project-frame]'),step=e.target.closest('[data-frame-step]');
  if(frame)showArtifact(activeArtifact,Number(frame.dataset.projectFrame));else if(step)showArtifact(activeArtifact,frameIndex+Number(step.dataset.frameStep));
 });
 $('#header-version').textContent=document.querySelector('meta[name=studio-version]').content;
 $('#updates-page').addEventListener('click',async event=>{const button=event.target.closest('[data-copy-update]');if(!button)return;const field=$('#studio-update-request');try{await navigator.clipboard.writeText(field.value);button.textContent=I18N.t('updates.requestCopied');$('.update-copy-status').textContent=I18N.t('updates.pasteFromFolder');}catch{field.focus();field.select();$('.update-copy-status').textContent=I18N.t('updates.selectAndCopy');}});
 function route(){
  const hash=location.hash.slice(1),params=new URLSearchParams(hash),id=params.get('project');
  const token=++routeRequest;
  if(id||!hash||hash==='projects'||hash.startsWith('how-it-works'))window.scrollTo(0,0);
  if(hash==='updates'){section('updates');const version=document.querySelector('meta[name=studio-version]').content;$('#installed-version').textContent=version;$('#studio-update-request').value=updateRequestBase+I18N.t('updates.installedVersionSuffix',{version});window.scrollTo(0,0);return true;}
  if(hash==='how-it-works-start'){history.replaceState(null,'','#projects');home();if(!loaded)loadProjects().then(()=>{if(token===routeRequest)home();}).catch(()=>{if(token===routeRequest){failed=true;home();}});requestAnimationFrame(()=>{if(token===routeRequest&&location.hash==='#projects')window.NewVideo?.open();});return true;}
  if(hash==='how-it-works'){guide();return true;}
  if(hash==='effects'||hash.startsWith('effects?')){activeProject=null;section('effects');const fx=new URLSearchParams(hash.slice('effects'.length));window.EffectsBoard?.mount($('#effects-page'),fx.get('project'),fx.get('tab'));window.scrollTo(0,0);return true;}
  if(id){
   if(activeProject?.id!==id){window.ProjectFeedback?.retain();window.ProjectScript?.retain();section('project');$('#project-page').innerHTML='<p class="studio-loading">'+I18N.t('project.openingLatest')+'</p>';}
   loadProjects().then(()=>{if(token!==routeRequest||location.hash.slice(1)!==hash)return;const p=projects.find(p=>p.id===id);if(p)projectPage(p,params.get('stage')==='script'||params.has('script')?'@script':params.get('artifact'),params.has('frame')?Number(params.get('frame'))-1:0);else{$('#project-page').innerHTML='<a href="#projects">'+I18N.t('project.backToAll')+'</a><div class="empty"><h2>'+I18N.t('project.notFound.title')+'</h2><p>'+I18N.t('project.notFound.body')+'</p></div>';}}).catch(()=>{if(token===routeRequest)$('#project-page').innerHTML='<p class="project-notice">'+I18N.t('project.refreshFailedCheck')+'</p>';});
   return true;
  }
  if(!hash||hash==='projects'){home();if(!loaded)loadProjects().then(()=>{if(token===routeRequest)home();}).catch(()=>{failed=true;home();});return true;}
  section('library');window.scrollTo(0,0);return false;
 }
 document.addEventListener('click',event=>{
  const link=event.target.closest('a[href]');
  if(link){const url=new URL(link.href,location.href);if(url.origin===location.origin&&url.pathname===location.pathname&&url.hash===location.hash&&url.hash.startsWith('#project=')){event.preventDefault();route();return;}}
  const step=event.target.closest('[data-lightbox-step]');if(step){showArtifact(activeArtifact,frameIndex+Number(step.dataset.lightboxStep),true);enlargeFrame();}
 });
 $('#frame-dialog').addEventListener('close',()=>{$('#frame-dialog video')?.pause();});
 document.addEventListener('i18n:change',()=>{
  if(currentSection==='projects')home();
  else if(currentSection==='project'&&activeProject)projectPage(activeProject,activeArtifact?.id,activeArtifact?.frames?frameIndex:null);
  else if(currentSection==='guide')guide();
  else section(currentSection);
 });
 return {route,refresh:checkUpdates,get currentSection(){return currentSection;}};
})();
