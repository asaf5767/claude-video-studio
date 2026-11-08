/* Reversible library visibility. Source records and exact handoffs are retained. */
window.LibraryVisibility=(()=>{
 let busy=false,undo=null,noticeId=null;
 const dialog=$('#removed-references-dialog');
 function details(e){
  noticeId=e.archived_from||e.id;const removed=isRemoved(e);
  $('#removed-reference-notice').hidden=!removed;
  $('.library-removal-action').hidden=removed;
  $('#library-removal-help').textContent=e.collection==='mine'?I18N.t('library.removal.helpMine'):I18N.t('dialog.style.removalHelp');
  $('#library-removal-error').textContent='';
 }
 function hideDetails(){noticeId=null;$('.library-removal-action').hidden=true;$('#removed-reference-notice').hidden=true;}
 function techniqueNotice(e){noticeId=e.archived_from||e.id;$('#removed-reference-notice').hidden=!isRemoved(e);}
 function refresh(){
  const removed=entries.filter(e=>!e.archived_from&&isRemoved(e));$('#open-removed-references').hidden=!removed.length;
  $('#open-removed-references').textContent=I18N.t('library.removedButton.count',{n:removed.length});
  if(dialog.open)renderRemoved();
 }
 function renderRemoved(){
  const removed=entries.filter(e=>!e.archived_from&&isRemoved(e));
  $('#removed-references-list').innerHTML=removed.length?removed.map(e=>'<article class="removed-reference-row"><div><h3>'+esc(e.title)+'</h3><p>'+esc(e.creator)+' · '+esc(e.collection==='mine'?I18N.t('library.collection.mine'):I18N.t('library.collection.reference'))+'</p></div><div><button class="text-button" data-view-removed="'+esc(e.id)+'">'+esc(I18N.t('library.removed.view'))+'</button><button class="secondary" data-restore-reference="'+esc(e.id)+'"'+(busy?' disabled':'')+'>'+esc(I18N.t('feedback.actions.restore'))+'</button></div></article>').join(''):'<p class="removed-empty">'+esc(I18N.t('library.removed.empty'))+'</p>';
 }
 function setBusy(value){busy=value;document.querySelectorAll('#remove-library-reference,#restore-library-reference,#undo-library-remove,[data-restore-reference]').forEach(b=>b.disabled=value);}
 async function reply(response){
  if(!response.headers.get('Content-Type')?.includes('application/json'))throw Error(I18N.t('library.removal.error.generic'));
  const data=await response.json();if(!response.ok)throw Error(data.error||I18N.t('library.removal.error.genericShort'));return data;
 }
 async function refreshBrowse(){
  const category=$('#technique').value,creator=$('#creator').value;
  await window.refreshReferenceCatalog();updateControls();
  if([...$('#technique').options].some(o=>o.value===category))$('#technique').value=category;
  if([...$('#creator').options].some(o=>o.value===creator))$('#creator').value=creator;
  render();
 }
 async function change(id,remove,status){
  if(busy)return;id=source(id)?.archived_from||id;const e=source(id);if(!e)return;
  const expected=isRemoved(e);setBusy(true);status.textContent='';
  let saved=false;
  try{
   const state=await reply(await fetch('/reference-visibility?id='+encodeURIComponent(id),{cache:'no-store'}));
   if(state.removed!==expected)throw Error(I18N.t('library.removal.error.conflict'));
   await reply(await fetch('/reference-visibility',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'reference-visibility'},body:JSON.stringify({id,action:remove?'remove':'restore',revision:state.revision})}));saved=true;
   await refreshBrowse();
   if(remove){
    undo=id;$('#library-undo span').textContent=I18N.t('library.removal.removedToast',{title:e.title});$('#library-undo').hidden=false;
    if(active?.id===id&&!isTech(active))closeStyle();
   }else{
    if(undo===id){undo=null;$('#library-undo').hidden=true;}
    if(active&&!isTech(active)&&active.id===id)details(source(id));
    if(noticeId===id)$('#removed-reference-notice').hidden=true;
    notify(I18N.t('library.removal.restoredToast',{title:e.title}));
   }
  }catch(error){status.textContent=saved?I18N.t('library.removal.error.savedButRefresh'):error instanceof TypeError?I18N.t('library.removal.error.network'):error.message;}
  finally{setBusy(false);if(saved&&remove&&!$('#library-undo').hidden&&window.Studio?.currentSection==='library'&&!document.querySelector('dialog[open]'))$('#undo-library-remove').focus();}
 }
 $('#remove-library-reference').addEventListener('click',()=>{if(active&&!isTech(active))change(active.id,true,$('#library-removal-error'));});
 $('#restore-library-reference').addEventListener('click',()=>{if(noticeId)change(noticeId,false,$('#detail-quick-status'));});
 $('#undo-library-remove').addEventListener('click',()=>{if(undo)change(undo,false,$('#library-undo span'));});
 $('#dismiss-library-undo').addEventListener('click',()=>{$('#library-undo').hidden=true;});
 $('#open-removed-references').addEventListener('click',async()=>{
  $('#removed-references-status').textContent='';renderRemoved();dialog.showModal();
  try{await refreshBrowse();}catch{$('#removed-references-status').textContent=I18N.t('library.removed.refreshFailed');}
 });
 dialog.addEventListener('click',event=>{
  const restore=event.target.closest('[data-restore-reference]');if(restore)return change(restore.dataset.restoreReference,false,$('#removed-references-status'));
  const view=event.target.closest('[data-view-removed]');if(view){dialog.close();showStyle(view.dataset.viewRemoved);}
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
 return {details,hideDetails,techniqueNotice,refresh};
})();
