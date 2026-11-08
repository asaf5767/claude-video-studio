/* Task 21: the optional "add-ons" dialog (voice: ElevenLabs; image: OpenAI Images or
   Azure AI Foundry). Off by default, never required -- enabling one means paying its
   provider on the user's own account, not the studio. Loads/saves through GET/POST
   /addons (serve.py / addons.py, the same trusted-write pattern as /ui-language and
   /ui-motion), which never echoes a saved API key back out of the browser -- only
   has_key: bool. The password fields here are therefore never prefilled: leaving one
   empty on Save leaves any already-saved key untouched, and the only way to blank a
   saved key is the explicit "Clear key" button next to it. Any failure (network or
   server) shows one generic translated message, the same way motion-setting.js does
   for /ui-motion -- never the server's raw response text. */
window.Addons=(()=>{
 const dialog=$('#addons-dialog'),form=$('#addons-form'),error=$('#addons-error');
 const field={
  voice:{enabled:$('#addons-voice-enabled'),key:$('#addons-voice-key'),status:$('#addons-voice-status'),clear:$('#addons-voice-clear')},
  image:{enabled:$('#addons-image-enabled'),provider:$('#addons-image-provider'),key:$('#addons-image-key'),status:$('#addons-image-status'),clear:$('#addons-image-clear')},
 };
 let busy=false,opener=null;

 function setStatus(kind,entry){
  const f=field[kind];
  f.status.textContent=entry.has_key?I18N.t('dialog.addons.connected'):'';
  if(f.status.classList)f.status.classList.toggle('connected',!!entry.has_key);
  f.clear.hidden=!entry.has_key;
 }

 function apply(data){
  field.voice.enabled.checked=data.voice.enabled;
  field.voice.key.value='';
  setStatus('voice',data.voice);
  field.image.enabled.checked=data.image.enabled;
  if(data.image.provider)field.image.provider.value=data.image.provider;
  field.image.key.value='';
  setStatus('image',data.image);
 }

 // What this add-on would be saved as right now, from the form's own fields -- the
 // key is layered on separately by the caller, never read from here.
 function currentPatch(kind){
  const f=field[kind],enabled=f.enabled.checked;
  return {enabled,provider:enabled?(kind==='voice'?'elevenlabs':f.provider.value):null};
 }

 function setBusy(next){
  busy=next;
  form.querySelectorAll('input,select,button').forEach(el=>el.disabled=next);
 }

 async function load(){
  try{
   const response=await fetch('/addons',{cache:'no-store'});
   if(response.ok)apply(await response.json());
  }catch{ /* keep whatever is on screen (both add-ons default to disabled) */ }
 }

 async function save(body){
  try{
   const response=await fetch('/addons',{method:'POST',
    headers:{'Content-Type':'application/json','X-Studio-Action':'addons'},body:JSON.stringify(body)});
   if(!response.ok)throw Error();
   return await response.json();
  }catch{
   throw Error(I18N.t('dialog.addons.error'));
  }
 }

 function open(button=null){
  opener=button||document.activeElement;
  error.textContent='';
  setBusy(false);
  if(!dialog.open)dialog.showModal();
  load();
 }

 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  setBusy(true);error.textContent='';
  try{
   const body={voice:currentPatch('voice'),image:currentPatch('image')};
   if(field.voice.key.value.trim())body.voice.key=field.voice.key.value;
   if(field.image.key.value.trim())body.image.key=field.image.key.value;
   apply(await save(body));
   dialog.close();
  }catch(err){
   error.textContent=err.message;
  }finally{
   setBusy(false);
  }
 });

 async function clearKey(kind){
  if(busy)return;
  setBusy(true);error.textContent='';
  try{
   apply(await save({[kind]:{...currentPatch(kind),key:''}}));
  }catch(err){
   error.textContent=err.message;
  }finally{
   setBusy(false);
  }
 }
 field.voice.clear.addEventListener('click',()=>clearKey('voice'));
 field.image.clear.addEventListener('click',()=>clearKey('image'));

 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-addons]');
  if(button){event.preventDefault();open(button);}
 });
 dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
 dialog.addEventListener('close',()=>{if(opener?.isConnected)opener.focus();});
 return {open};
})();
