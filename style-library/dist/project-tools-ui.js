/* Local editor working copies and sound direction. Saved review exports stay unchanged. */
window.ProjectTools=(()=>{
 let current=null,run=0,busy=false;
 const dialog=document.createElement('dialog');dialog.id='editor-dialog';dialog.setAttribute('aria-labelledby','editor-title');
 // This dialog is built once, here, before I18N.ready resolves — data-i18n* attributes
 // (rather than I18N.t() calls baked into this one-time string) let i18n.js's own
 // render() fill these in once strings load, and keep them in sync on i18n:change,
 // the same way index.html's static dialogs work. Left empty rather than defaulting to
 // English fallback text: app.js's init() always awaits I18N.ready before the first
 // route runs, so nothing shows this dialog before render() has filled it in once.
 dialog.innerHTML='<div class="brief-head"><h2 id="editor-title" data-i18n="tools.editor.title"></h2><button class="close-button" aria-label="" data-i18n-aria="tools.editor.closeAria">×</button></div><p id="editor-version"></p><p id="editor-explanation" data-i18n="tools.editor.explanationNew"></p><p data-i18n="tools.editor.returnNote"></p><p id="editor-launch-status" role="status"></p><div class="editor-actions"><button class="primary" id="editor-launch" data-i18n="tools.editor.launchCreate"></button><button class="secondary" id="editor-cancel" data-i18n="tools.editor.cancel"></button></div><div id="editor-result" hidden><a id="editor-link" target="_blank" rel="noopener" data-i18n="tools.editor.openLink"></a><p id="editor-copy-path" class="editor-copy-path"></p></div>';
 document.body.append(dialog);window.addEventListener('hashchange',()=>{if(dialog.open&&!busy)dialog.close();});
 const close=()=>{if(!busy)dialog.close();};dialog.querySelector('.close-button').onclick=close;$('#editor-cancel').onclick=close;dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
 function open(){
  if(!current?.data.editor)return;
  $('#editor-version').textContent=I18N.t('tools.editor.versionLabel',{project:current.project.title,version:current.artifact.version||current.artifact.label});
  $('#editor-explanation').textContent=I18N.t(current.data.editor.working_copy?'tools.editor.explanationExisting':'tools.editor.explanationNew');$('#editor-launch').textContent=I18N.t(current.data.editor.working_copy?'tools.editor.launchOpenExisting':'tools.editor.launchCreate');
  $('#editor-launch-status').textContent='';$('#editor-result').hidden=true;$('#editor-launch').hidden=false;$('#editor-launch').disabled=false;$('#editor-cancel').textContent=I18N.t('tools.editor.cancel');dialog.showModal();
 }
 $('#editor-launch').onclick=async()=>{
  if(busy||!current?.data.editor)return;const target=current;busy=true;$('#editor-launch').disabled=true;$('#editor-cancel').disabled=true;dialog.querySelector('.close-button').disabled=true;$('#editor-launch-status').textContent=I18N.t(target.data.editor.working_copy?'tools.editor.statusOpeningExisting':'tools.editor.statusCreating');
  try{
   const response=await fetch('/open-editor',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'open-editor'},body:JSON.stringify({project_id:target.project.id,artifact_id:target.artifact.id,revision:target.data.editor.revision})});
   const data=await response.json();if(!response.ok)throw Error(data.error||I18N.t('tools.editor.errorGeneric'));
   target.data.editor.working_copy=true;$('#editor-launch-status').textContent=I18N.t('tools.editor.readyStatus');$('#editor-link').href=data.url;$('#editor-copy-path').textContent=I18N.t('tools.editor.savedIn',{path:data.working_copy});$('#editor-result').hidden=false;$('#editor-launch').hidden=true;$('#editor-cancel').textContent=I18N.t('tools.editor.done');
  }catch(error){$('#editor-launch-status').textContent=error instanceof TypeError?I18N.t('tools.editor.errorNetwork'):error.message;}
  finally{busy=false;$('#editor-launch').disabled=false;$('#editor-cancel').disabled=false;dialog.querySelector('.close-button').disabled=false;}
 };
 async function copySound(project,artifact,button){
  const url=new URL('./',location.href);url.hash=new URLSearchParams({project:project.id,artifact:artifact.id}).toString();
  const text=I18N.t('tools.sound.requestMessage',{project:project.title,version:artifact.version||artifact.label,url:url.href});
  try{await navigator.clipboard.writeText(text);button.textContent=I18N.t('tools.sound.copiedButton');setTimeout(()=>{if(button.isConnected)button.textContent=I18N.t('tools.sound.copyRequestButton');},2200);}
  catch{$('#link-text').value=text;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}
 }
 async function mount(project,artifact){
  const token=++run;current=null;if(artifact.type!=='video'||!artifact.available)return;
  const container=$('#project-artifact'),notes=container?.querySelector('.artifact-notes');if(!notes)return;
  try{
   const response=await fetch('/project-tools?'+new URLSearchParams({project:project.id,artifact:artifact.id}),{cache:'no-store'});const data=await response.json();if(!response.ok||token!==run||!notes.isConnected)return;
   current={project,artifact,data};
   if(data.editor?.ready){const button=document.createElement('button');button.className='secondary editor-open';button.textContent=I18N.t('tools.editor.title');button.onclick=open;container.querySelector('.review-downloads')?.prepend(button);}
   const sound=data.sound||{},box=document.createElement('details');box.className='project-sound';
   box.innerHTML='<summary>'+esc(I18N.t('tools.sound.summary'))+'</summary>'+(sound.recorded?'<dl class="sound-facts"><div><dt>'+esc(I18N.t('tools.sound.music'))+'</dt><dd>'+esc(sound.music||I18N.t('tools.sound.notRecorded'))+'</dd></div><div><dt>'+esc(I18N.t('tools.sound.effects'))+'</dt><dd>'+esc(sound.effects||I18N.t('tools.sound.notRecorded'))+'</dd></div></dl>'+(sound.direction?'<p class="sound-help">'+esc(sound.direction)+'</p>':''):'<p class="sound-help">'+esc(I18N.t('tools.sound.notRecordedYet'))+'</p>')+'<p class="sound-help">'+esc(I18N.t('tools.sound.helpListen'))+'</p><button class="text-button" data-copy-sound>'+esc(I18N.t('tools.sound.copyRequestButton'))+'</button>';
   box.querySelector('[data-copy-sound]').onclick=e=>copySound(project,artifact,e.currentTarget);notes.insertBefore(box,notes.querySelector('#review-controls'));
  }catch{if(token===run&&notes.isConnected){const message=document.createElement('p');message.className='sound-help';message.textContent=I18N.t('tools.loadError');notes.append(message);}}
 }
 return {mount};
})();
