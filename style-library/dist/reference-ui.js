/* Link or file capture (Task 13: a dropped video needs no link) with optional public cover retrieval.
   The style card itself lives in inspiration-ui.js; details() mounts it for creator references. */
window.ReferenceIntake=(()=>{
 let editing=null,revision=null,busy=false,opening=0,justSaved=null,analysisCopying=null,lastAnalysisCopy=null;
 const dialog=$('#reference-dialog'),form=$('#reference-form');
 const fields={url:$('#reference-url'),title:$('#reference-title'),creator:$('#reference-creator'),note:$('#reference-note')};
 function setBusy(value){busy=value;dialog.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=value);$('#reference-save').textContent=value?I18N.t('project.saving'):editing?I18N.t('dialog.reference.saveDetails'):I18N.t('dialog.reference.save');}
 function detailHierarchy(pending,partial=false){
  $('#reference-analysis-next').hidden=!(pending||partial);$('#reference-analyze').autofocus=pending;$('#detail-summary').hidden=pending;$('#reference-more').open=false;
  $('#reference-use').classList.toggle('awaiting-analysis',pending);$('#pending-link-heading').hidden=!pending;
  $('.detail-copy').insertBefore($('#reference-use'),pending?$('.reference-deep-details'):$('#reference-user-note'));
  $('#detail-quick-copy').classList.toggle('primary',!pending);$('#detail-quick-copy').classList.toggle('secondary',pending);
 }
 function details(e){
  const pending=e.analysis_status==='not_analyzed',partial=e.analysis_status==='partial',fresh=pending&&justSaved===e.id;if(justSaved!==e.id)justSaved=null;
  detailHierarchy(pending,partial);$('#reference-more').hidden=false;
  $('#reference-analysis-state').textContent=partial?I18N.t('dialog.style.partlyAnalyzed'):I18N.t('dialog.style.awaitingAnalysis');renderAnalysisCopy(e);
  $('.analysis-next-description').textContent=partial?I18N.t('dialog.style.analyzeNextBodyPartial'):I18N.t('dialog.style.analyzeNextBody');
  $('#reference-analysis-title').textContent=partial?I18N.t('dialog.style.continueAnalyzing'):fresh?I18N.t('dialog.style.savedNextAnalyze'):I18N.t('dialog.style.analyzeNext');
  $('#detail-analyze').hidden=pending||partial;$('#detail-analyze').textContent=I18N.t('dialog.style.analyzeAgain');$('#detail-edit-reference').hidden=!(e.collection==='reference'&&(e.source_url||e.source_file));
  $('#reference-user-note').hidden=!e.reference_note;$('#reference-user-note-text').textContent=e.reference_note||'';
  $('.taste').hidden=!(e.keep.length||e.avoid.length);
  if(e.asset_type==='link'&&!e.media_path){const poster=$('#detail-media img');if(poster)poster.alt=e.poster==='assets/link-reference.svg'?I18N.t('dialog.style.posterVideoUnavailableAlt'):I18N.t('dialog.style.posterCoverAlt',{title:e.title});}
  // Task 13 fix round 1: for a creator reference the style card is the one next step; Matt's
  // analysis request moves into the reference options menu instead of a second primary box.
  if(window.Inspiration&&e.collection==='reference'&&!e.archived_from){
   $('#reference-analysis-next').hidden=true;$('#detail-analyze').hidden=false;if(!e.source_url)$('#pending-link-heading').hidden=true;
   $('#detail-analyze').textContent=pending||partial?I18N.t('dialog.style.copyAnalysisRequest'):I18N.t('dialog.style.analyzeAgain');
  }
  window.Inspiration?.mount(e);
 }
 function hideDetails(){window.Inspiration?.unmount();detailHierarchy(false);$('#reference-more').hidden=true;$('#detail-analyze').hidden=true;$('#detail-edit-reference').hidden=true;$('#reference-user-note').hidden=true;$('.taste').hidden=false;}
 async function reply(response,fallback){
  if(!response.headers.get('Content-Type')?.includes('application/json'))throw Error(fallback);
  try{return await response.json();}catch{throw Error(fallback);}
 }
 async function open(id=null){
  pausePreview();$('#reference-more').open=false;const token=++opening;editing=id;revision=null;form.reset();setBusy(false);
  fields.url.readOnly=!!id;fields.url.required=true;window.Inspiration?.resetDrop(!!id);$('#reference-form-title').textContent=id?I18N.t('dialog.reference.editTitle'):I18N.t('dialog.reference.title');
  $('#reference-intro').textContent=id?I18N.t('dialog.reference.introEdit'):I18N.t('dialog.reference.introNew');
  $('#reference-error').textContent='';$('#reference-save').disabled=!!id;
  $('#reference-creators').innerHTML=[...new Set(entries.map(e=>e.creator).filter(c=>c&&c!=='Creator not added'))].sort().map(c=>'<option value="'+esc(c)+'"></option>').join('');
  $('.reference-helper').textContent=id?I18N.t('dialog.reference.helperEdit'):I18N.t('dialog.reference.helper');
  dialog.showModal();if(!id){fields.url.focus();return;}
  Object.values(fields).forEach(field=>field.disabled=true);
  try{
   const response=await fetch('/reference-state?id='+encodeURIComponent(id)),data=await reply(response,I18N.t('dialog.reference.loadFailed'));
   if(token!==opening||!dialog.open)return;if(!response.ok)throw Error(data.error||I18N.t('dialog.reference.loadFailedShort'));
   revision=data.revision;for(const key of Object.keys(fields)){fields[key].value=data[key]||'';fields[key].disabled=false;}
   if(data.creator==='Creator not added')fields.creator.value='';$('#reference-save').disabled=false;fields.title.focus();
  }catch(error){if(token===opening&&dialog.open)$('#reference-error').textContent=error instanceof TypeError?I18N.t('dialog.reference.networkError'):error.message;}
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!form.reportValidity())return;
  const body={action:editing?'edit':'create',title:fields.title.value,creator:fields.creator.value,note:fields.note.value};
  if(editing){body.id=editing;body.revision=revision;}else body.url=fields.url.value;
  const file=editing?null:window.Inspiration?.pendingFile()||null,progress=percent=>{$('#reference-save').textContent=I18N.t('inspiration.drop.uploading',{percent});};
  setBusy(true);$('#reference-error').textContent='';let result;
  try{
   if(file&&!body.url.trim())result=await window.Inspiration.upload(file,{title:body.title,creator:body.creator,note:body.note},progress);
   else{
    const response=await fetch('/references',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference'},body:JSON.stringify(body)});
    result=await reply(response,I18N.t('dialog.reference.saveFailed'));if(!response.ok)throw Error(result.error||I18N.t('dialog.reference.saveFailedShort'));
    if(file){
     try{await window.Inspiration.upload(file,{reference:result.id},progress);}
     catch{
      setBusy(false);$('#reference-error').textContent=I18N.t('inspiration.error.linkSavedFileFailed');
      try{await window.refreshReferenceCatalog();}catch{/* the link is saved either way */}
      return;
     }
    }
   }
  }catch(error){setBusy(false);$('#reference-error').textContent=error instanceof TypeError?I18N.t('dialog.reference.networkError'):error.message;return;}
  try{await window.refreshReferenceCatalog();}
  catch{setBusy(false);$('#reference-error').textContent=I18N.t('dialog.reference.savedRefreshNeeded');return;}
  setBusy(false);dialog.close();justSaved=body.action==='create'&&!result.duplicate?result.id:null;
  if(location.hash===referenceHash(result.id))applyRoute();else location.hash=referenceHash(result.id);
  if(body.action==='create'&&!result.duplicate&&(!file||body.url.trim()))getPreview(result.id);
  notify(result.duplicate?I18N.t('dialog.reference.notifyDuplicate'):editing?I18N.t('dialog.reference.notifyDetailsSaved'):file?I18N.t('inspiration.notify.saved'):I18N.t('dialog.reference.notifySavedNextAnalyze'));
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();else ++opening;});
 dialog.addEventListener('close',()=>++opening);
 $('#add-reference').addEventListener('click',()=>open());
 $('#detail-edit-reference').addEventListener('click',()=>{if(active&&!isTech(active))open(active.id);});
 const fetching=new Set();
 async function getPreview(id){
  if(fetching.has(id))return;fetching.add(id);
  try{
   const response=await fetch('/reference-preview',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference-preview'},body:JSON.stringify({id})});
   const result=await reply(response,'');
   if(response.ok&&result.changed){
    await window.refreshReferenceCatalog();
    if(window.Studio?.currentSection==='library')render();
    if(active?.id===id&&!isTech(active)&&$('#style-dialog').open)showStyle(id);
   }
  }catch{/* A missing public cover never blocks the saved reference or its analysis step. */}
  finally{fetching.delete(id);}
 }
 function analysisRequest(e){
  const verb=e.analysis_status==='not_analyzed'?I18N.t('dialog.style.analysisRequest.notAnalyzed'):e.analysis_status==='partial'?I18N.t('dialog.style.analysisRequest.partial'):I18N.t('dialog.style.analysisRequest.reviewExisting');
  const originalLine=e.source_url?I18N.t('dialog.style.analysisRequest.originalLine',{url:e.source_url}):'',noteLine=e.reference_note?I18N.t('dialog.style.analysisRequest.noteLine',{note:e.reference_note}):'';
  return I18N.t('dialog.style.analysisRequest.body',{verb,url:referenceUrl(e.id),originalLine,noteLine});
 }
 function renderAnalysisCopy(e){
  const button=$('#reference-analyze'),copied=lastAnalysisCopy?.id===e.id&&lastAnalysisCopy.text===analysisRequest(e);
  button.disabled=analysisCopying===e.id;button.textContent=button.disabled?I18N.t('dialog.analysis.copying'):copied?I18N.t('dialog.style.copiedCheck'):I18N.t('dialog.style.copyAnalysisRequest');
  $('.analysis-next-helper').textContent=copied?I18N.t('dialog.style.analysisCopiedHelper'):I18N.t('dialog.style.analysisHelper');
 }
 async function copyPrimaryAnalysis(){
  if(!active||isTech(active)||analysisCopying)return;
  const e=active,text=analysisRequest(e),isCurrent=()=>active?.id===e.id&&!isTech(active)&&$('#style-dialog').open;
  analysisCopying=e.id;renderAnalysisCopy(e);pausePreview();
  try{await navigator.clipboard.writeText(text);lastAnalysisCopy={id:e.id,text};}
  catch{if(isCurrent()){openAnalysis();$('#analysis-status').textContent=I18N.t('dialog.style.copyManuallyBelow');$('#analysis-text').focus();$('#analysis-text').select();}}
  finally{analysisCopying=null;if(isCurrent())renderAnalysisCopy(active);}
 }
 async function copyAnalysis(){
  try{await navigator.clipboard.writeText($('#analysis-text').value);if(active&&!isTech(active)&&analysisRequest(active)===$('#analysis-text').value){lastAnalysisCopy={id:active.id,text:$('#analysis-text').value};renderAnalysisCopy(active);}$('#analysis-status').textContent=I18N.t('dialog.analysis.copiedPasteStudio');$('#analysis-copy').textContent=I18N.t('dialog.style.copiedCheck');}
  catch{$('#analysis-status').textContent=I18N.t('dialog.analysis.selectAndCopy');$('#analysis-text').focus();$('#analysis-text').select();}
 }
 function openAnalysis(){
  if(!active||isTech(active))return;pausePreview();$('#analysis-text').value=analysisRequest(active);$('#analysis-status').textContent='';$('#analysis-copy').textContent=I18N.t('dialog.style.copyAnalysisRequest');$('#analysis-dialog').showModal();$('#reference-more').open=false;
 }
 $('#reference-analyze').addEventListener('click',copyPrimaryAnalysis);
 $('#detail-analyze').addEventListener('click',openAnalysis);
 $('#reference-keep-browsing').addEventListener('click',()=>closeStyle());
 $('#analysis-copy').addEventListener('click',copyAnalysis);
 document.addEventListener('click',event=>{if(!event.target.closest('#reference-more'))$('#reference-more').open=false;});
 $('#reference-more').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();$('#reference-more').open=false;$('#reference-more summary').focus();event.stopPropagation();}});
 return {details,hideDetails};
})();
