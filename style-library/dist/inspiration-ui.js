/* Task 13: inspiration by link or file, with style cards.
   - The add-reference dialog gets a drop zone: a dropped video makes the link optional and
     is streamed to PUT /inspiration-file (reference-ui.js calls upload() on submit).
   - The reference dialog gets a STYLE CARD panel: "ללמוד את הסגנון" is the studio's one
     Send-to-Claude card (send-ui.js, task learn-style: progress, cancel, copy details for
     support, copy-to-chat), reloading the card when the run is done; the learned card is
     edited row by row with a "לשמור" pin per field (POST /style-card), and "להשתמש בסגנון
     הזה בסרטון חדש" opens the new-video dialog with this reference as its look.
   Built with document.createElement (like materials-ui.js); SendUI polls inside its own
   node, so a poll never resets what the user is typing. */
window.Inspiration=(()=>{
 const VIDEO_EXT=['.mp4','.mov','.webm','.m4v'],MAX_UPLOAD=1024*1024*1024;
 const IDENTITY=['id','name_he','name_en'];
 let current=null,token=0,dropped=null;

 function el(tag,props={},...children){
  const node=document.createElement(tag);
  for(const [key,value] of Object.entries(props)){
   if(key==='class')node.className=value;else if(key==='attrs')Object.entries(value).forEach(([a,v])=>node.setAttribute(a,v));else node[key]=value;
  }
  node.append(...children.filter(c=>c!==null&&c!==undefined));
  return node;
 }
 const FIELD={captions:'inspiration.field.captions',titles:'inspiration.field.titles',pace:'inspiration.field.pace',transitions:'inspiration.field.transitions',
  graphics:'inspiration.field.graphics',music:'inspiration.field.music',sfx:'inspiration.field.sfx',hook:'inspiration.field.hook',avoid:'inspiration.field.avoid'};
 const label=key=>FIELD[key]?I18N.t(FIELD[key]):key;
 const oneLine=value=>String(value??'').replace(/\s*[\r\n]+\s*/g,' ').trim();
 const extOf=name=>{const text=String(name??''),i=text.lastIndexOf('.');return i<0?'':text.slice(i).toLowerCase();};

 // The card text in the looks/<id>/card.md format: identity keys, the editable keys in
 // order, any extra keys Claude wrote, then the free-text body. Front matter is one line
 // per key, so a value typed over several lines is joined into one.
 function composeCard(card,values,refId,title){
  const fields={...card.fields};
  fields.id=oneLine(fields.id)||refId;fields.name_he=oneLine(fields.name_he)||oneLine(title);fields.name_en=oneLine(fields.name_en)||oneLine(title);
  for(const key of card.keys)fields[key]=oneLine(values[key]);
  const order=[...IDENTITY,...card.keys,...Object.keys(card.fields).filter(k=>!IDENTITY.includes(k)&&!card.keys.includes(k))];
  // A malformed card can come back with its broken --- block still in the body; never write the block twice.
  const body=String(card.body||'').replace(/^---\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/,'').replace(/^\s+|\s+$/g,'');
  return '---\n'+order.map(k=>k+': '+oneLine(fields[k])).join('\n')+'\n---\n'+(body?body+'\n':'');
 }

 function upload(file,params,onProgress){
  return new Promise((resolve,reject)=>{
   const xhr=new XMLHttpRequest();
   xhr.upload.onprogress=event=>{if(event.lengthComputable&&onProgress)onProgress(Math.floor(event.loaded/event.total*100));};
   xhr.onload=()=>{
    let result=null;try{result=JSON.parse(xhr.responseText);}catch{/* the generic message below */}
    if(xhr.status>=200&&xhr.status<300&&result)resolve(result);else reject(Error(I18N.t(result?.error||'inspiration.error.filesystem')));
   };
   xhr.onerror=()=>reject(Error(I18N.t('dialog.reference.networkError')));
   xhr.open('PUT','/inspiration-file?'+new URLSearchParams({name:file.name,...params}));
   xhr.setRequestHeader('X-Studio-Action','inspiration-file');
   xhr.send(file);
  });
 }

 // --- the drop zone in the add-reference dialog ---
 function setDropped(file){
  dropped=file;$('#reference-url').required=!file;
  $('#inspiration-file-chosen').hidden=!file;$('#inspiration-file-name').textContent=file?file.name:'';
 }
 function choose(file){
  if(!file)return;
  if(!VIDEO_EXT.includes(extOf(file.name))){setDropped(null);$('#reference-error').textContent=I18N.t('inspiration.error.unsupportedType');return;}
  if(file.size>MAX_UPLOAD){setDropped(null);$('#reference-error').textContent=I18N.t('inspiration.error.tooLarge');return;}
  $('#reference-error').textContent='';setDropped(file);
 }
 function resetDrop(editing){setDropped(null);$('#inspiration-file').value='';$('#inspiration-drop').hidden=!!editing;}
 $('#inspiration-drop-button').addEventListener('click',()=>$('#inspiration-file').click());
 $('#inspiration-file').addEventListener('change',()=>choose($('#inspiration-file').files?.[0]));
 $('#inspiration-drop').addEventListener('dragover',event=>{event.preventDefault();$('#inspiration-drop').classList.add('drag-over');});
 $('#inspiration-drop').addEventListener('dragleave',()=>$('#inspiration-drop').classList.remove('drag-over'));
 $('#inspiration-drop').addEventListener('drop',event=>{event.preventDefault();$('#inspiration-drop').classList.remove('drag-over');choose(event.dataTransfer?.files?.[0]);});
 $('#inspiration-file-clear').addEventListener('click',()=>{resetDrop(false);});

 // --- the style card panel in the reference dialog ---
 async function json(response){try{return await response.json();}catch{return {};}}
 function message(error){return error instanceof TypeError?I18N.t('dialog.reference.networkError'):error.message;}

 function render(){
  const panel=$('#style-card-panel');if(!current)return;
  const {entry,card}=current,ready=!!card?.exists;
  panel.setAttribute('aria-label',I18N.t('inspiration.card.sectionAria'));
  current.status=el('p',{class:'style-card-status',attrs:{role:'status'},textContent:current.statusText||''});
  const send=el('div',{class:'style-card-send'});
  const parts=[
   el('p',{class:'eyebrow',textContent:I18N.t('inspiration.card.eyebrow')}),
   el('h3',{textContent:I18N.t(ready?'inspiration.card.titleReady':'inspiration.card.titleEmpty')}),
   el('p',{class:'style-card-rule',textContent:I18N.t('inspiration.card.rule')}),
   el('p',{class:'style-card-intro',textContent:card?I18N.t(ready?'inspiration.card.introReady':'inspiration.card.introEmpty'):I18N.t(current.loadFailed?'inspiration.card.loadError':'inspiration.card.loading')}),
   send,current.status,
  ];
  if(ready)parts.push(editor());
  panel.replaceChildren(...parts);
  mountSend(send);
 }

 // The one Send-to-Claude card (send-ui.js) runs learn-style: re-mounting it on every render
 // keeps a running job (SendUI takes it over); when the run is done the card is reloaded.
 function mountSend(node){
  const mine=current;if(!window.SendUI)return;
  mine.send=window.SendUI.mount(node,mine.entry.id,{task:'learn-style',
   sendLabel:()=>I18N.t(mine.card?.exists?'inspiration.learn.again':'inspiration.learn.button'),
   // Re-learning rewrites the card; pinned rows are kept by the server, the rest change.
   beforeSend:()=>!(mine.card?.exists&&typeof confirm==='function'&&!confirm(I18N.t('inspiration.learn.confirmAgain'))),
   onDone:()=>{if(mine===current)load(mine.entry,mine.token);}});
 }

 function editor(){
  const {entry,card}=current,inputs={},pins={};
  const rows=card.keys.map(key=>{
   const fieldId='style-card-'+key;
   inputs[key]=el('textarea',{id:fieldId,rows:2,value:card.fields[key]||''});
   pins[key]=el('input',{type:'checkbox',checked:card.pinned.includes(key),attrs:{'aria-label':I18N.t('inspiration.card.pinAria',{field:label(key)})}});
   return el('div',{class:'style-card-row'+(card.pinned.includes(key)?' is-pinned':'')},
    el('div',{class:'style-card-row-head'},el('label',{textContent:label(key),attrs:{for:fieldId}}),
     el('label',{class:'style-card-pin'},pins[key],el('span',{textContent:I18N.t('inspiration.card.pin')}))),
    inputs[key]);
  });
  rows.forEach((row,i)=>pins[card.keys[i]].addEventListener('change',()=>row.classList.toggle('is-pinned',pins[card.keys[i]].checked)));
  const error=el('p',{class:'style-card-error',attrs:{role:'alert'},textContent:card.missing?.length?I18N.t('inspiration.card.incomplete',{keys:card.missing.filter(k=>card.keys.includes(k)).map(label).join(', ')}):''});
  const save=el('button',{type:'submit',class:'primary',textContent:I18N.t('inspiration.card.save')});
  const reload=el('button',{type:'button',class:'text-button',hidden:true,textContent:I18N.t('inspiration.card.reload')});
  reload.addEventListener('click',()=>load(entry,current.token));
  const use=el('button',{type:'button',class:'secondary',textContent:I18N.t('inspiration.card.useInNewVideo')});
  use.addEventListener('click',()=>{
   const id=entry.id;
   if(typeof closeStyle==='function')closeStyle();else $('#style-dialog').close();
   window.NewVideo?.open(null,{referenceId:id});
  });
  const form=el('form',{class:'style-card-editor',noValidate:true},...rows,error,el('div',{class:'style-card-editor-actions'},save,use,reload));
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(save.disabled)return;
   const values={};card.keys.forEach(k=>values[k]=inputs[k].value);
   const body={reference:entry.id,text:composeCard(card,values,entry.id,entry.title),pinned:card.keys.filter(k=>pins[k].checked),revision:card.revision};
   const mine=current;save.disabled=true;save.textContent=I18N.t('inspiration.card.saving');error.textContent='';reload.hidden=true;
   try{
    const response=await fetch('/style-card',{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Action':'style-card'},body:JSON.stringify(body)});
    const result=await json(response);
    if(!response.ok){
     if(response.status===409)reload.hidden=false;
     throw Error(result.error==='inspiration.error.invalidCard'?I18N.t(result.error,{keys:(result.missing||[]).map(k=>card.keys.includes(k)?label(k):k).join(', ')}):I18N.t(result.error||'inspiration.error.filesystem'));
    }
    if(mine!==current)return;
    Object.assign(card,result);setStatus(I18N.t('inspiration.card.saved'));
   }catch(failure){if(mine===current)error.textContent=message(failure);}
   finally{save.disabled=false;save.textContent=I18N.t('inspiration.card.save');}
  });
  return form;
 }

 function setStatus(text){if(!current)return;current.statusText=text;if(current.status)current.status.textContent=text;}

 async function load(entry,mine){
  try{
   const response=await fetch('/style-card?reference='+encodeURIComponent(entry.id)),result=await json(response);
   if(mine!==token)return;
   if(!response.ok)throw Error(I18N.t(result.error||'inspiration.card.loadError'));
   current.card=result;current.loadFailed=false;
  }catch{if(mine!==token)return;current.loadFailed=true;}
  render();
 }

 function mount(entry){
  const panel=$('#style-card-panel'),mine=++token;
  if(!entry||entry.collection!=='reference'||entry.archived_from){if(current?.send)window.SendUI?.release(current.send);current=null;panel.hidden=true;panel.replaceChildren();return;}
  if(current?.send)window.SendUI?.release(current.send);
  current={entry,token:mine,card:null,statusText:'',loadFailed:false,send:null};
  panel.hidden=false;render();
  load(entry,mine);
 }
 function unmount(){
  ++token;if(current?.send)window.SendUI?.release(current.send);
  current=null;const panel=$('#style-card-panel');panel.hidden=true;panel.replaceChildren();
 }
 $('#style-dialog').addEventListener('close',unmount);
 document.addEventListener('i18n:change',()=>{if(current)render();});

 return {mount,unmount,upload,composeCard,resetDrop,pendingFile:()=>dropped};
})();
