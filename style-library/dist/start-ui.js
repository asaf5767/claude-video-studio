/* One optional starter, shared by Projects and the guide. Creation stays in the editing chat. */
window.StudioStart=(()=>{
 const key='ai-video-studio-starter-v2',types=['video','carousel','presentation'];
 // Static per-type lookup objects rather than building a key by string concatenation
 // (an I18N dot-t call whose argument is a quoted prefix plus a +variable): the coverage
 // test's key-reference scan is a regex over literal, fully-quoted I18N dot-t calls, so a
 // concatenated key would only ever extract the quoted prefix up to its closing quote as
 // a (nonexistent) key and flag it as missing. Keeping every I18N dot-t call argument a
 // single static string literal here -- looked up through one of these objects -- avoids
 // that false positive.
 const FORMAT_LABEL_KEY={video:'start.format.video',carousel:'start.format.carousel',presentation:'start.format.presentation'};
 const FORMAT_NOUN_KEY={video:'start.chat.formatNoun.video',carousel:'start.chat.formatNoun.carousel',presentation:'start.chat.formatNoun.presentation'};
 const FORMAT_GOAL_PLACEHOLDER_KEY={video:'start.placeholders.goalFormat.video',carousel:'start.placeholders.goalFormat.carousel',presentation:'start.placeholders.goalFormat.presentation'};
 const fields=['goal','footage','script','keep','references','scriptreference'];
 const requestId=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
 let draft={type:'video',start:null,scriptOpen:false,referenceOpen:false,scriptreference:'',goal:'',footage:'',script:'',keep:'',references:'',messages:{},extras:false,preview:false,location:false,inspirationOpen:false,inspiration:[],inspirationDrafts:{},linkDraft:'',editingGoal:null,handoff:null},dialog=null,opener=null,copiedText=null,copying=false,references=null;
 let arrival=null,checking=null;
 const node=id=>dialog.querySelector('#'+id);
 // Fix round 1 (CRITICAL, coordinator review): this file is a `defer`red script, so it
 // runs before I18N.ready resolves (i18n.js's own fetch for the language strings is
 // still in flight) -- a plain `const x=I18N.t(key)` evaluated once here at module-load
 // time would permanently bake in the fallback (the raw key itself, since `strings` is
 // still `{}`) for the rest of the session. `inspirationHeading()` instead calls
 // I18N.t() lazily, every time it's actually needed (after the user interacts, by which
 // point I18N.ready has long since resolved), so it always reflects the current language.
 //
 // Fix round 2 (CRITICAL, coordinator review): round 1's INSPIRATION_SENTINEL was
 // '\u200Binspiration-for-visual-edit\u200B' -- only the two ends were zero-width; the
 // 27 ASCII characters in between were plain visible text that landed, untranslated, in
 // every pasted chat draft that had inspiration attached, in every language.
 //
 // The preferred fix would keep the user's own text and the auto-generated inspiration
 // block as fully separate pieces of draft state, so there's nothing to ever find by
 // content. That's not feasible without a larger redesign here: `project-starter` is
 // NOT readOnly for carousel/presentation projects (see render()'s
 // `node('project-starter').readOnly=idea||edit`), so the user can freely type anywhere
 // in that single textarea, including inside or around the auto-appended inspiration
 // block -- there is no boundary between "the user's words" and "the generated block"
 // once they're merged into one string the user can edit by hand, and the 'input'
 // handler below captures that merged snapshot verbatim into `draft.messages`. (This
 // merged-string-plus-split-marker design predates Task 4 -- the original code did
 // exactly this, using the hardcoded English heading itself as the split key, since
 // there was only one language to worry about.)
 //
 // So instead: INSPIRATION_SENTINEL is now made *entirely* of zero-width characters --
 // no visible text in any language -- and stripSentinel() removes it from the one place
 // it must never reach: the value actually handed to navigator.clipboard (and the
 // clipboard-unavailable manual-copy fallback), in copy() below. It deliberately stays
 // in the live, in-progress textarea value and in `draft.messages`/sessionStorage --
 // invisible there, since it's zero-width -- so a later inspiration-selection change, or
 // a language toggle (via the i18n:change listener below), can still find and replace
 // exactly that block. (Continuing to hand-edit the textarea *after* a failed-clipboard
 // fallback is the one residual edge case where the sentinel could be stripped away by
 // the user's own edit, same as deleting it outright would be -- same accepted
 // characteristic the original heading-text-as-marker design already had.)
 const INSPIRATION_SENTINEL='\u200B\u200C\u200B\u200C\u200B\u200C\u200B\u200C';
 function inspirationHeading(){return INSPIRATION_SENTINEL+I18N.t('start.chat.inspirationMarker');}
 const inspirationText=()=>draft.inspiration.length?inspirationHeading()+window.StartReferences.text(draft.inspiration):'';
 const stripSentinel=text=>text.split(INSPIRATION_SENTINEL).join('');
 // Re-locates and rebuilds the inspiration block in every customized message (skipping
 // 'video-idea', which never gets one -- see set() below) using the *current* language
 // and selection. Used both when the selection changes and -- new in fix round 2-- on
 // every i18n:change, so an already-customized draft's heading doesn't stay frozen in
 // whichever language it was first written in.
 function refreshInspirationInMessages(){
  for(const type of Object.keys(draft.messages))if(type!=='video-idea')draft.messages[type]=draft.messages[type].split(INSPIRATION_SENTINEL)[0]+inspirationText();
 }
 // Drafts saved before this fix (or before fix round 1) spliced in a *visible* marker as
 // the split boundary: the raw i18n key (if fix round 1's module-load-time bug ever
 // fired), fix round 1's half-invisible sentinel above, or -- predating Task 4 entirely
 // -- the hardcoded English heading with no sentinel at all (and, briefly between this
 // group's first commit and fix round 1, its Hebrew translation with no sentinel
 // either). Reloading one of those shapes without migrating would leave the stale
 // heading sitting in the message as unsplittable plain prose, so the next inspiration
 // change would append a second, fresh block right after it instead of replacing it.
 // Finds the earliest of these legacy markers, if any, and rebuilds the message with
 // today's sentinel in its place; returns `text` untouched if none of them are present.
 const LEGACY_INSPIRATION_MARKERS=['start.chat.inspirationMarker','\u200Binspiration-for-visual-edit\u200B','\n\nInspiration for the visual edit (save these exact references with the project):\n','\n\n\u05D4\u05E9\u05E8\u05D0\u05D4 \u05DC\u05E2\u05E8\u05D9\u05DB\u05D4 \u05D4\u05D7\u05D6\u05D5\u05EA\u05D9\u05EA (\u05E9\u05DE\u05E8\u05D5 \u05D0\u05EA \u05D4\u05D4\u05E9\u05E8\u05D0\u05D5\u05EA \u05D4\u05DE\u05D3\u05D5\u05D9\u05E7\u05D5\u05EA \u05D4\u05D0\u05DC\u05D4 \u05E2\u05DD \u05D4\u05E1\u05E8\u05D8\u05D5\u05DF):\n'];
 function migrateLegacyInspirationMarker(text){
  let cut=-1;
  for(const marker of LEGACY_INSPIRATION_MARKERS){const at=text.indexOf(marker);if(at!==-1&&(cut===-1||at<cut))cut=at;}
  return cut===-1?text:text.slice(0,cut)+inspirationText();
 }
 try{
  const saved=JSON.parse(sessionStorage.getItem(key)||'null');
  if(saved&&typeof saved==='object'){
   if(types.includes(saved.type))draft.type=saved.type;
   if(['idea','footage'].includes(saved.start))draft.start=saved.start;
   else if(fields.some(field=>typeof saved[field]==='string'&&saved[field].trim())||saved.inspiration?.length||Object.keys(saved.messages||{}).length)draft.start='footage';
   draft.scriptOpen=saved.scriptOpen===true;draft.referenceOpen=saved.referenceOpen===true;
   if(typeof saved.editingGoal==='string')draft.editingGoal=saved.editingGoal.slice(0,22000);if(typeof saved.linkDraft==='string')draft.linkDraft=saved.linkDraft.slice(0,10000);
   for(const field of fields)if(typeof saved[field]==='string')draft[field]=saved[field].slice(0,field==='script'?50000:10000);
   if(typeof saved.handoff?.id==='string'&&requestId.test(saved.handoff.id))draft.handoff={id:saved.handoff.id,current:saved.handoff.current===true};
   for(const type of [...types,'video-idea'])if(typeof saved.messages?.[type]==='string')draft.messages[type]=saved.messages[type].slice(0,100000);
   draft.extras=saved.extras===true;draft.preview=saved.preview===true;draft.location=saved.location===true||!!draft.footage;draft.inspirationOpen=saved.inspirationOpen===true;draft.inspiration=window.StartReferences.restore(saved.inspiration);draft.inspirationDrafts=Object.fromEntries(window.StartReferences.restore(Object.values(saved.inspirationDrafts||{})).map(r=>[window.StartReferences.targetKey(r),r]));
   for(const type of Object.keys(draft.messages))if(type!=='video-idea')draft.messages[type]=migrateLegacyInspirationMarker(draft.messages[type]);
  }
 }catch{/* Closing still keeps the in-memory draft when browser storage is unavailable. */}
 function persist(){try{sessionStorage.setItem(key,JSON.stringify(draft));}catch{}}
 function messageKey(){return draft.type==='video'&&draft.start==='idea'?'video-idea':draft.type;}
 function writing(){return draft.type==='video'&&draft.start==='idea';}
 function footage(){return draft.type==='video'&&draft.start==='footage';}
 function editingGoal(){return draft.editingGoal??[draft.goal.trim(),draft.keep.trim()?I18N.t('start.chat.detailsToPreserve',{keep:draft.keep.trim()}):''].filter(Boolean).join('\n\n');}
 const writingInputs=()=>JSON.stringify([draft.goal.trim(),draft.script.trim(),draft.scriptreference.trim()]);
 function readFields(){
  const before=draft.handoff?.current?writingInputs():null;
  for(const field of fields){if(field==='goal'&&footage())draft.editingGoal=node('start-goal').value;else draft[field]=node('start-'+field).value;}
  if(before!==null&&before!==writingInputs())draft.handoff.current=false;
 }
 function unchosen(){return draft.type==='video'&&!draft.start;}
 function canCopy(){return !unchosen()&&(!writing()||['goal','script','scriptreference'].some(field=>draft[field].trim()))&&!!node('project-starter').value.trim();}
 function request(){
  if(unchosen())return '';
  if(writing())return [
   I18N.t('start.chat.writeScriptIntro'),
   draft.goal.trim()&&I18N.t('start.chat.ideaAndAudience',{goal:draft.goal.trim()}),
   draft.script.trim()&&I18N.t('start.chat.initialScriptDraft',{script:draft.script.trim()}),
   draft.scriptreference.trim()&&I18N.t('start.chat.scriptReferenceLine',{ref:draft.scriptreference.trim()})
  ].filter(Boolean).join('\n\n');
  if(typeof draft.messages[messageKey()]==='string')return draft.messages[messageKey()];
  const materialNoun=draft.type==='video'?I18N.t('start.chat.footageNoun'):I18N.t('start.chat.sourceMaterialNoun');
  return I18N.t('start.chat.startProject',{format:I18N.t(FORMAT_NOUN_KEY[draft.type])})
   +((footage()?editingGoal():draft.goal).trim()?I18N.t('start.chat.goalAndAudience',{goal:(footage()?editingGoal():draft.goal).trim()}):'')
   +(draft.footage.trim()?I18N.t('start.chat.footageLocation',{materialNoun,location:draft.footage.trim()}):draft.type==='video'?I18N.t('start.chat.attachRawVideo'):'')
   +(draft.type==='video'&&draft.script.trim()?I18N.t('start.chat.scriptRecorded',{script:draft.script.trim()}):'')
   +(!footage()&&draft.keep.trim()?I18N.t('start.chat.requirements',{keep:draft.keep.trim()}):'')
   +(draft.references.trim()?I18N.t('start.chat.referencesLine',{references:draft.references.trim()}):'')
   +'\n'+(draft.type==='video'?I18N.t('start.chat.videoInstructions'):I18N.t('start.chat.otherFormatInstructions'))+I18N.t('start.chat.closing')+inspirationText();
 }
 function guidance(copied=false){
  if(unchosen())return I18N.t('start.guidance.unchosen');
  if(writing()&&!['goal','script','scriptreference'].some(field=>draft[field].trim()))return I18N.t('start.guidance.writingEmpty');
  if(draft.type==='video'&&draft.start==='idea')return copied?I18N.t('start.guidance.ideaCopied'):I18N.t('start.guidance.ideaUncopied');
  if(footage())return copied?I18N.t('start.guidance.footageCopied'):I18N.t('start.guidance.footageUncopied');
  if(draft.footage.trim())return copied?I18N.t('start.guidance.footageLocCopied'):I18N.t('start.guidance.footageLocUncopied');
  if(draft.type==='video')return copied?I18N.t('start.guidance.videoCopied'):I18N.t('start.guidance.videoUncopied');
  return copied?I18N.t('start.guidance.otherCopied'):I18N.t('start.guidance.otherUncopied');
 }
 function copyState(message=null){
  const copied=copiedText===node('project-starter').value,ready=readyForForm();
  node('start-copy').hidden=unchosen();node('start-copy').disabled=copying||references?.busy||(!ready&&!canCopy());node('start-copy').textContent=ready?I18N.t('start.actions.openDraft'):copying?I18N.t('start.actions.preparing'):copied?I18N.t('start.actions.requestCopied'):I18N.t('start.actions.copyRequest');
  node('start-done').textContent=copied?I18N.t('start.actions.done'):I18N.t('start.actions.close');node('start-status').textContent=ready?I18N.t('start.status.scriptReady',{title:arrival.title}):message||guidance(copied);
 }
 function readyForForm(){return !!arrival&&writing()&&draft.handoff?.current&&arrival.request===draft.handoff.id;}
 function renderArrival(){
  const notice=document.querySelector('#starter-arrival');
  if(!notice)return;
  notice.hidden=!arrival||arrival.request!==draft.handoff?.id;
  document.querySelector('#starter-arrival-title').textContent=notice.hidden?'':arrival.title;
 }
 async function checkArrival(projects){
  const id=draft.handoff?.id;
  const candidates=id?projects.filter(p=>p.starter_request_id===id&&p.format==='video'):[];
  const project=candidates.length===1?candidates[0]:null;
  if(arrival&&(!project||arrival.request!==id||arrival.id!==project.id)){
   arrival=null;renderArrival();if(dialog?.open)copyState();
  }
  if(!project){checking=null;return;}
  if(arrival){
   if(arrival.title!==project.title){arrival.title=project.title;renderArrival();if(dialog?.open&&readyForForm())copyState();}
   return;
  }
  if(checking?.request===id&&checking.id===project.id)return;
  const attempt={request:id,id:project.id};
  checking=attempt;
  try{
   const response=await fetch('/project-script?'+new URLSearchParams({project:project.id}),{cache:'no-store'});
   if(!response.ok)return;
   const script=await response.json();
   if(checking!==attempt||draft.handoff?.id!==id||script.project_id!==project.id||!/^[a-f0-9]{64}$/.test(script.version_id||''))return;
   arrival={...attempt,title:project.title};
   renderArrival();if(dialog?.open&&readyForForm())copyState();
  }catch{/* A later refresh can pick up the draft after a transient failure. */}
  finally{if(checking===attempt)checking=null;}
 }
 function openDraft(){
  if(!arrival||arrival.request!==draft.handoff?.id)return;
  const id=arrival.id;
  close();draft.handoff=null;arrival=null;checking=null;persist();renderArrival();
  location.hash=new URLSearchParams({project:id,stage:'script'}).toString();
 }
 function render(){
  for(const field of fields)node('start-'+field).value=draft[field];
  dialog.querySelectorAll('[data-start-type]').forEach(button=>{const on=button.dataset.startType===draft.type;button.setAttribute('aria-checked',String(on));button.tabIndex=on?0:-1;});
  node('start-journeys').hidden=draft.type!=='video';
  dialog.querySelectorAll('[data-start-journey]').forEach(button=>{const on=button.dataset.startJourney===draft.start;button.setAttribute('aria-checked',String(on));button.tabIndex=on||!draft.start&&button.dataset.startJourney==='idea'?0:-1;});
  const idea=writing(),edit=footage();
  node('start-goal').maxLength=edit?22000:10000;if(edit)node('start-goal').value=editingGoal();
  node('start-fields').hidden=unchosen();node('start-footer').hidden=unchosen();dialog.classList.toggle('script-start',idea);dialog.classList.toggle('footage-start',edit);
  node('start-lead').hidden=true;
  node('start-goal-label').textContent=idea?I18N.t('start.labels.goalIdea'):edit?I18N.t('start.labels.goalEdit'):I18N.t('start.labels.goalDefault');
  node('start-extras').hidden=idea||edit;node('start-inspiration').hidden=idea;node('start-preview').hidden=idea||edit&&!draft.preview;node('project-starter').readOnly=idea||edit;node('start-preview-summary').textContent=idea?I18N.t('start.labels.previewSummaryIdea'):edit?I18N.t('start.labels.previewSummaryEdit'):I18N.t('start.labels.previewSummaryDefault');
  node('start-see-message').hidden=!edit;node('start-see-message').setAttribute('aria-expanded',String(draft.preview));node('start-see-message').textContent=draft.preview?I18N.t('start.actions.hideMessage'):I18N.t('start.actions.seeMessage');
  node('start-other-links').hidden=idea||edit&&!draft.references.trim();node('start-other-links-label').textContent=edit?I18N.t('start.labels.otherLinksEdit'):I18N.t('start.labels.otherLinksDefault');
  node('start-draft-note').hidden=idea||edit||unchosen();node('start-material-help').hidden=idea||edit;
  node('start-script-summary').textContent=idea?I18N.t('start.labels.scriptSummaryIdea'):I18N.t('start.labels.scriptSummaryDefault');node('start-script-label').textContent=idea?I18N.t('start.labels.scriptLabelIdea'):I18N.t('start.labels.scriptLabelDefault');
  node('start-script-field').open=draft.scriptOpen||!!draft.script.trim();node('start-script-reference-field').open=draft.referenceOpen||!!draft.scriptreference.trim();
  node('start-location').hidden=idea;node('start-script-reference-field').hidden=!idea;
  node('start-attach-help').hidden=!edit;node('start-location-summary').textContent=edit?I18N.t('start.labels.locationSummaryEdit'):I18N.t('start.labels.locationSummaryDefault');node('start-location-optional').hidden=edit;node('start-location-help').textContent=edit?I18N.t('start.labels.locationHelpEdit'):I18N.t('start.labels.locationHelpDefault');
  node('start-script').placeholder=idea?I18N.t('start.placeholders.scriptIdea'):I18N.t('start.placeholders.scriptDefault');
  node('start-script-field').hidden=draft.type!=='video';node('start-footage-label').textContent=draft.type==='video'?I18N.t('start.labels.footageLabelVideo'):I18N.t('start.labels.footageLabelOther');
  node('start-footage').placeholder=draft.type==='video'?I18N.t('start.placeholders.footageVideo'):I18N.t('start.placeholders.footageOther');
  node('start-material-help').textContent=idea?I18N.t('start.helpers.materialIdea'):draft.type==='video'?I18N.t('start.helpers.materialVideo'):I18N.t('start.helpers.materialOther');
  node('start-goal').placeholder=idea?I18N.t('start.placeholders.goalIdea'):edit?I18N.t('start.placeholders.goalEdit'):I18N.t(FORMAT_GOAL_PLACEHOLDER_KEY[draft.type]);
  node('start-keep-label').textContent=I18N.t('start.labels.keepLabel');
  node('start-extras').open=draft.extras;node('start-preview').open=draft.preview;node('start-location').open=draft.location;node('start-inspiration').open=draft.inspirationOpen||draft.inspiration.length>0||!!draft.references.trim()||!!draft.linkDraft;node('start-inspiration-title').textContent=idea?I18N.t('start.labels.inspirationTitleIdea'):I18N.t('start.labels.inspirationTitleDefault');node('project-starter').value=request();references?.render();copyState();
 }
 function remember(){
  if(!dialog)return;
  readFields();
  draft.scriptOpen=node('start-script-field').open;if(writing())draft.referenceOpen=node('start-script-reference-field').open;draft.extras=node('start-extras').open;draft.preview=node('start-preview').open;draft.location=node('start-location').open;draft.inspirationOpen=node('start-inspiration').open;persist();
 }
 function select(type,focus=false){
  remember();draft.type=type;persist();render();if(focus)dialog.querySelector('[data-start-type="'+type+'"]').focus();
 }
 function close(){if(dialog?.open){remember();references?.hide(false);dialog.close();}}
 async function copy(){
  if(copying||references?.busy||!canCopy())return;const isWriting=writing(),text=node('project-starter').value;if(!text.trim())return;
  copying=true;copiedText=null;copyState();
  try{await window.StartReferences.validate(writing()?[]:draft.inspiration);if(!dialog.open||node('project-starter').value!==text){copying=false;copyState();return;}}catch(error){copying=false;copyState(I18N.t('start.copy.referenceChangedSuffix',{error:error.message}));return;}
  let message=text;
  if(isWriting){
   if(!draft.handoff?.current){draft.handoff={id:crypto.randomUUID(),current:true};arrival=null;checking=null;persist();renderArrival();}
   message=request()+I18N.t('start.chat.starterRequestIdLine',{id:draft.handoff.id});
  }
  // `message` (and `text`) can still carry the invisible INSPIRATION_SENTINEL -- see the
  // fix round 2 comment above `INSPIRATION_SENTINEL`'s declaration. Strip it only right
  // here, at the one place the text actually leaves the app.
  try{await navigator.clipboard.writeText(stripSentinel(message));copiedText=text;}
  catch{
   if(dialog.open&&node('project-starter').value===text){draft.preview=true;node('project-starter').value=stripSentinel(message);node('start-preview').hidden=false;node('start-preview').open=true;persist();node('project-starter').focus();node('project-starter').select();copying=false;copyState(I18N.t('start.copy.automaticCopyFailed'));return;}
  }finally{copying=false;}
  copyState();
 }
 function mount(){
  if(dialog)return dialog;
  dialog=document.createElement('dialog');dialog.id='project-start-dialog';dialog.setAttribute('aria-labelledby','start-project-title');
  dialog.innerHTML=`<div class="project-start-head"><div><h2 id="start-project-title" tabindex="-1">${esc(I18N.t('start.dialog.title'))}</h2><p id="start-lead" hidden></p></div><button class="close-button" id="start-close" aria-label="${esc(I18N.t('start.dialog.closeAria'))}">×</button></div><form id="guided-start"><div class="project-start-body"><fieldset class="start-types"><legend>${esc(I18N.t('start.dialog.whatMaking'))}</legend><div role="radiogroup" aria-label="${esc(I18N.t('start.dialog.formatAria'))}">${types.map(type=>`<button type="button" role="radio" data-start-type="${type}" aria-checked="false">${esc(I18N.t(FORMAT_LABEL_KEY[type]))}</button>`).join('')}</div></fieldset><fieldset id="start-journeys" class="start-journeys"><legend>${esc(I18N.t('start.dialog.whereStarting'))}</legend><div role="radiogroup" aria-label="${esc(I18N.t('start.dialog.journeyAria'))}"><button type="button" role="radio" data-start-journey="idea" aria-checked="false">${esc(I18N.t('start.dialog.journeyIdea'))}<small>${esc(I18N.t('start.dialog.journeyIdeaSub'))}</small></button><button type="button" role="radio" data-start-journey="footage" aria-checked="false">${esc(I18N.t('start.dialog.journeyFootage'))}<small>${esc(I18N.t('start.dialog.journeyFootageSub'))}</small></button></div></fieldset><div id="start-fields"><label id="start-goal-label" for="start-goal">${esc(I18N.t('start.labels.goalDefault'))}</label><textarea id="start-goal" rows="3" maxlength="10000"></textarea><p id="start-material-help" class="start-field-help"></p><details id="start-script-field" class="start-core-extra"><summary><span id="start-script-summary">${esc(I18N.t('start.labels.scriptSummaryDefault'))}</span> <small>${esc(I18N.t('common.optional'))}</small></summary><label for="start-script"><span id="start-script-label">${esc(I18N.t('start.labels.scriptLabelDefault'))}</span></label><textarea id="start-script" rows="3" maxlength="50000" placeholder="${esc(I18N.t('start.placeholders.scriptDefault'))}"></textarea></details><details id="start-script-reference-field" class="start-core-extra" hidden><summary>${esc(I18N.t('start.dialog.useReferenceVideo'))} <small>${esc(I18N.t('common.optional'))}</small></summary><label for="start-scriptreference">${esc(I18N.t('start.dialog.referenceVideoLabel'))}</label><textarea id="start-scriptreference" rows="2" maxlength="10000" placeholder="${esc(I18N.t('start.dialog.referenceVideoPlaceholder'))}"></textarea></details><details id="start-inspiration" class="start-extra start-core-extra start-inspiration"><summary><span id="start-inspiration-title">${esc(I18N.t('start.dialog.inspirationTitleStatic'))}</span> <small>${esc(I18N.t('common.optional'))}</small></summary><div id="start-reference-summary"></div><div id="start-other-links"><label for="start-references"><span id="start-other-links-label">${esc(I18N.t('start.labels.otherLinksDefault'))}</span> <small>${esc(I18N.t('common.optional'))}</small></label><textarea id="start-references" rows="2" maxlength="10000"></textarea></div></details><details id="start-extras" class="start-extra"><summary>${esc(I18N.t('start.dialog.addDetails'))} <small>${esc(I18N.t('common.optional'))}</small></summary><label for="start-keep"><span id="start-keep-label">${esc(I18N.t('start.labels.keepLabel'))}</span> <small>${esc(I18N.t('common.optional'))}</small></label><textarea id="start-keep" rows="2" maxlength="10000"></textarea></details><p id="start-attach-help" class="start-field-help" hidden>${esc(I18N.t('start.dialog.attachHelp'))}</p><details id="start-location" class="start-extra start-location"><summary id="start-location-summary">${esc(I18N.t('start.labels.locationSummaryDefault'))}</summary><label for="start-footage"><span id="start-footage-label">${esc(I18N.t('start.labels.footageLabelVideo'))}</span> <small id="start-location-optional">${esc(I18N.t('common.optional'))}</small></label><input id="start-footage" maxlength="10000"><p id="start-location-help" class="start-field-help">${esc(I18N.t('start.labels.locationHelpDefault'))}</p></details><details id="start-preview" class="start-preview"><summary id="start-preview-summary">${esc(I18N.t('start.labels.previewSummaryDefault'))}</summary><textarea id="project-starter" aria-label="${esc(I18N.t('start.dialog.requestForChatAria'))}" rows="7" maxlength="100000"></textarea></details></div><p id="start-draft-note" class="start-draft-note">${esc(I18N.t('start.dialog.draftNote'))}</p></div><div id="start-footer" class="project-start-foot"><p id="start-status" role="status"></p><div><button type="button" class="text-button" id="start-see-message" aria-controls="start-preview" aria-expanded="false" hidden>${esc(I18N.t('start.actions.seeMessage'))}</button><button type="button" class="secondary" id="start-done">${esc(I18N.t('start.actions.close'))}</button><button type="button" class="primary" id="start-copy">${esc(I18N.t('start.actions.copyRequest'))}</button></div></div></form><section id="start-picker" hidden aria-label="${esc(I18N.t('start.dialog.chooseInspirationTitle'))}"></section>`;
  document.body.append(dialog);
  references=window.StartReferences.create({dialog,state:()=>copyState(),getLinkDraft:()=>draft.linkDraft,setLinkDraft:value=>{draft.linkDraft=value;persist();},getDrafts:()=>draft.inspirationDrafts,setDrafts:rows=>{draft.inspirationDrafts=rows;persist();},level:view=>{const label=view==='reference'?I18N.t('start.dialog.backToReferencesLabel'):view==='library'?I18N.t('start.inspiration.backToProjectShort'):I18N.t('start.dialog.closeAria');node('start-close').setAttribute('aria-label',label);node('start-close').title=label;},get:()=>draft.inspiration,set:rows=>{draft.inspiration=rows;refreshInspirationInMessages();copiedText=null;persist();node('project-starter').value=request();copyState();},showPicker:on=>{
   node('guided-start').hidden=on;node('start-picker').hidden=!on;dialog.classList.toggle('choosing-inspiration',on);node('start-lead').hidden=!on;node('start-project-title').textContent=on?I18N.t('start.dialog.chooseInspirationTitle'):I18N.t('start.dialog.title');node('start-lead').textContent=on?I18N.t('start.dialog.chooseInspirationLead'):I18N.t('start.dialog.defaultLead');
  }});
  node('guided-start').addEventListener('submit',event=>event.preventDefault());
  node('guided-start').addEventListener('input',event=>{
   if(event.target.id==='project-starter'){if(node('project-starter').readOnly)return;draft.messages[messageKey()]=event.target.value;}
   else if(event.target.id==='start-video-link'||event.target.dataset.refNote!==undefined||event.target.dataset.refFocus!==undefined||event.target.dataset.refSummaryNote!==undefined)return;
   else{readFields();if(!writing())delete draft.messages[messageKey()];node('project-starter').value=request();}
   copiedText=null;persist();copyState();
  });
  dialog.querySelectorAll('[data-start-type]').forEach(button=>{
   button.addEventListener('click',()=>select(button.dataset.startType));
   button.addEventListener('keydown',event=>{
    const direction={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[event.key];
    if(direction||event.key==='Home'||event.key==='End'){event.preventDefault();const index=event.key==='Home'?0:event.key==='End'?types.length-1:(types.indexOf(draft.type)+direction+types.length)%types.length;select(types[index],true);}
   });
  });
  dialog.querySelectorAll('[data-start-journey]').forEach(button=>{
   const choose=()=>{remember();draft.start=button.dataset.startJourney;persist();render();};
   button.addEventListener('click',choose);
   button.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    event.preventDefault();remember();draft.start=event.key==='Home'?'idea':event.key==='End'?'footage':button.dataset.startJourney==='idea'?'footage':'idea';persist();render();dialog.querySelector('[data-start-journey="'+draft.start+'"]').focus();
   });
  });
  for(const id of ['start-extras','start-preview','start-location','start-inspiration','start-script-field','start-script-reference-field'])node(id).addEventListener('toggle',()=>{remember();if(id==='start-preview'&&footage()){node('start-preview').hidden=!draft.preview;node('start-see-message').setAttribute('aria-expanded',String(draft.preview));node('start-see-message').textContent=draft.preview?I18N.t('start.actions.hideMessage'):I18N.t('start.actions.seeMessage');}});
  const backOrClose=()=>{if(!references.back())close();};
  node('start-see-message').addEventListener('click',()=>{remember();draft.preview=!draft.preview;persist();node('start-preview').hidden=!draft.preview;node('start-preview').open=draft.preview;node('start-see-message').setAttribute('aria-expanded',String(draft.preview));node('start-see-message').textContent=draft.preview?I18N.t('start.actions.hideMessage'):I18N.t('start.actions.seeMessage');if(draft.preview)node('start-preview').scrollIntoView?.({block:'nearest',behavior:'smooth'});});
  node('start-copy').addEventListener('click',()=>readyForForm()?openDraft():copy());node('start-close').addEventListener('click',backOrClose);node('start-done').addEventListener('click',close);
  dialog.addEventListener('cancel',event=>{event.preventDefault();backOrClose();});
  document.addEventListener('keydown',event=>{
   if(event.key!=='Escape'||!dialog.open||document.fullscreenElement)return;
   event.preventDefault();event.stopPropagation();if(!event.repeat)backOrClose();
  },true);
  let outsideDown=false;
  const outside=event=>{const r=dialog.getBoundingClientRect();return event.target===dialog&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom);};
  dialog.addEventListener('pointerdown',event=>{outsideDown=outside(event);});dialog.addEventListener('click',event=>{if(outsideDown&&outside(event))close();outsideDown=false;});
  dialog.addEventListener('close',()=>{if(!dialog.open){const fallback=document.querySelector((window.Studio?.currentSection==='guide'?'#guide-page':'#projects-page')+' [data-start-project]');(opener?.isConnected?opener:fallback)?.focus();}});
  render();return dialog;
 }
 function open(button=null){mount();references.hide(false);opener=button||document.activeElement;render();if(!dialog.open)dialog.showModal();node('start-project-title').focus();}
 document.addEventListener('click',event=>{
  if(event.target.closest('[data-open-starter-draft]')){event.preventDefault();openDraft();return;}
  const button=event.target.closest('[data-start-project]');if(button){event.preventDefault();open(button);}
 });
 // Fix round 2: without this, an already-customized draft's inspiration heading stayed
 // frozen in whichever language it was first composed in, even after the user toggled
 // the UI language -- refreshInspirationInMessages() re-finds the block via
 // INSPIRATION_SENTINEL (language-independent) and rebuilds it with the now-current
 // I18N.t() text. Runs even if the dialog was never mounted, so the in-memory draft
 // stays correct for whenever it next opens; re-renders it immediately if it's already
 // open.
 document.addEventListener('i18n:change',()=>{refreshInspirationInMessages();persist();if(dialog)render();});
 window.addEventListener('hashchange',close);
 return {mount,open,close,checkArrival,renderArrival};
})();
