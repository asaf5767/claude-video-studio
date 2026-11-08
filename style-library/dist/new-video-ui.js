/* Task 7: create a draft video directly from the studio, no chat round-trip. Title,
   kind and video language only; on success the new project's own page opens. */
window.NewVideo=(()=>{
 const dialog=$('#new-video-dialog'),form=$('#new-video-form'),titleField=$('#new-video-title-input');
 let state={kind:'talking-head',language:'he',referenceId:null},busy=false,opener=null;
 function setChecked(selector,attr,value){
  dialog.querySelectorAll(selector).forEach(b=>b.setAttribute('aria-checked',String(b.dataset[attr]===value)));
 }
 function setBusy(next){
  busy=next;dialog.querySelectorAll('input,button').forEach(el=>el.disabled=next);
  $('#new-video-save').textContent=next?I18N.t('project.saving'):I18N.t('dialog.newVideo.create');
 }
 // This is the studio's one "new video" flow (fix round 1, controller ruling R23):
 // every entry point -- the home hero, the guide-page callout, the empty-state link,
 // #how-it-works-start, and (when `options.referenceId` is passed) a future "use this
 // reference in a new video" button -- opens this dialog rather than the old
 // copy-to-chat wizard in start-ui.js. That file stays for Task 15's in-project
 // "copy to chat" fallback, but nothing currently routes a "new video" click into it.
 function open(button=null,options={}){
  opener=button||document.activeElement;form.reset();
  state={kind:'talking-head',language:I18N.lang(),referenceId:options.referenceId||null};
  setChecked('[data-new-video-kind]','newVideoKind',state.kind);
  setChecked('[data-new-video-language]','newVideoLanguage',state.language);
  $('#new-video-error').textContent='';setBusy(false);
  if(!dialog.open)dialog.showModal();
  titleField.focus();
 }
 dialog.addEventListener('click',event=>{
  const kind=event.target.closest('[data-new-video-kind]');
  if(kind){state.kind=kind.dataset.newVideoKind;setChecked('[data-new-video-kind]','newVideoKind',state.kind);return;}
  const language=event.target.closest('[data-new-video-language]');
  if(language){state.language=language.dataset.newVideoLanguage;setChecked('[data-new-video-language]','newVideoLanguage',state.language);}
 });
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy||!form.reportValidity())return;
  setBusy(true);$('#new-video-error').textContent='';
  try{
   const body={title:titleField.value,kind:state.kind,video_language:state.language};
   if(state.referenceId)body.reference_id=state.referenceId;
   const response=await fetch('/new-video',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'new-video'},
    body:JSON.stringify(body)});
   let result;
   try{result=await response.json();}catch{throw Error(I18N.t('dialog.newVideo.saveFailed'));}
   if(!response.ok)throw Error(I18N.t(result.error));
   dialog.close();
   location.hash='#project='+encodeURIComponent(result.id);
  }catch(error){
   setBusy(false);
   $('#new-video-error').textContent=error instanceof TypeError?I18N.t('dialog.reference.networkError'):error.message;
  }
 });
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-new-video]');
  if(button){event.preventDefault();open(button,{referenceId:button.dataset.referenceId||null});}
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
 dialog.addEventListener('close',()=>{if(opener?.isConnected)opener.focus();});
 return {open};
})();
