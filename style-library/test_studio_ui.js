const {test}=require('node:test'),assert=require('node:assert/strict'),{readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm');
// Task 4: app.js/studio.js now call I18N.t(key, vars) for UI copy. These sandboxed
// contexts don't load the real i18n.js, so they get a stub that looks up the same
// strings a Hebrew-first page would show in English (en.json), with the same
// `{name}` interpolation i18n.js itself implements.
function i18nStub(){
 const en=JSON.parse(readFileSync(join(__dirname,'dist/i18n/en.json'),'utf8'));
 return {ready:Promise.resolve(),lang:()=>'en',server:message=>message,t(key,vars){const value=en[key]??key;if(!vars)return value;return Object.keys(vars).reduce((text,name)=>text.split('{'+name+'}').join(vars[name]),value);}};
}
test('library sorting uses original added dates, with stable undated entries and independent approval times',()=>{
 const app=readFileSync(join(__dirname,'dist/app.js'),'utf8'),start=app.indexOf('function render(){'),end=app.indexOf('\nfunction setView(',start);
 assert.ok(start>=0&&end>start);
 const entries=[
  {id:'older',title:'Alpha',created_at:'2026-11-01T10:00:00Z',approval:{at:'2026-11-05T10:00:00Z'}},
  {id:'undated-one',title:'Delta'},
  {id:'newer',title:'Beta',created_at:'2026-11-04T10:00:00Z'},
  {id:'undated-two',title:'Gamma'}
 ].map(e=>({subtitle:'',creator:'Owner',summary:'',tags:[],traits:{},...e}));
 const nodes=new Map(),node=key=>{if(!nodes.has(key))nodes.set(key,{value:'all'});return nodes.get(key);};
 node('#search').value='';node('#library-sort').value='newest';
 const context={$:node,view:'videos',collection:'mine',entries,techniques:[],viewEntries:()=>entries,matchesSource:()=>true,
  renderActiveFilters(){},updateSelection(){},videoCard:e=>'['+e.id+']',I18N:i18nStub()};
 runInNewContext(app.slice(start,end),context);context.render();
 assert.equal(node('#gallery').innerHTML,'[newer][older][undated-one][undated-two]');
 node('#library-sort').value='oldest';context.render();
 assert.equal(node('#gallery').innerHTML,'[older][newer][undated-one][undated-two]');
 node('#library-sort').value='name';context.render();
 assert.equal(node('#gallery').innerHTML,'[older][newer][undated-one][undated-two]');
});
function menu(){
 const handlers={},summary={focused:false,focus(){this.focused=true;}},inside={},outside={};
 const picker={open:true,contains:target=>target===inside,querySelector:()=>summary};
 const document={addEventListener:(name,fn)=>handlers[name]=fn,querySelectorAll:()=>picker.open?[picker]:[],querySelector:()=>picker.open?picker:null};
 runInNewContext(readFileSync(join(__dirname,'dist/review-layout.js'),'utf8'),{window:{},document,esc:String});return {handlers,picker,summary,inside,outside};
}
test('version menu stays open inside and dismisses on an outside click',()=>{const h=menu();h.handlers.click({target:h.inside});assert.equal(h.picker.open,true);h.handlers.click({target:h.outside});assert.equal(h.picker.open,false);});
test('Escape closes the version menu and returns focus to its summary',()=>{const h=menu();let prevented=false;h.handlers.keydown({key:'Escape',preventDefault(){prevented=true;},stopPropagation(){}});assert.equal(h.picker.open,false);assert.equal(h.summary.focused,true);assert.equal(prevented,true);});

// T9b: the message+download link shown when a browser can't decode a version's video at
// all (in practice, Chrome on Windows failing on HEVC/HLG footage shot on an iPhone).
// Sliced out of studio.js the same way menu() above slices review-layout.js: the function
// only touches document.createElement/I18N.t, so it runs standalone without the rest of
// studio.js's module-load-time DOM wiring.
function videoUnplayableNotice(){
 const studio=readFileSync(join(__dirname,'dist/studio.js'),'utf8');
 const start=studio.indexOf(' function videoUnplayableNotice('),end=studio.indexOf('\n function enlargeFrame(',start);
 assert.ok(start>=0&&end>start,'videoUnplayableNotice() moved or was renamed in studio.js');
 const made=[];
 const document={createElement:tag=>{const node={tag,_className:'',get className(){return this._className;},set className(v){this._className=v;},textContent:'',append(...kids){node.children=kids;}};made.push(node);return node;}};
 const context={document,I18N:i18nStub()};
 runInNewContext(studio.slice(start,end),context);
 return {fn:context.videoUnplayableNotice,made};
}
test('videoUnplayableNotice shows the translated HEVC message and a download link to the exact artifact file',()=>{
 const {fn}=videoUnplayableNotice();
 const notice=fn({url:'/project-assets/demo/abc123',path:'projects/demo/review-v3.mp4'});
 assert.equal(notice.className,'project-video-unplayable');
 const [message,link]=notice.children;
 assert.equal(message.className,'project-notice');
 assert.match(message.textContent,/HEVC/);
 assert.equal(link.href,'/project-assets/demo/abc123');
 assert.equal(link.download,'review-v3.mp4');
 assert.ok(link.textContent.length>0);
});
function starter(options={}){
 const nodes=new Map(),storage=options.storage||new Map(),copies=[],requests=[],documentHandlers={},windowHandlers={};
 const node=key=>{
  if(!nodes.has(key))nodes.set(key,{value:'',textContent:'',hidden:false,disabled:false,open:false,isConnected:true,listeners:{},attributes:{},dataset:{},classList:{toggle(){}},
   addEventListener(type,fn){this.listeners[type]=fn;},setAttribute(name,value){this.attributes[name]=value;},focus(){this.focused=true;},select(){this.selected=true;},
   showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();},getBoundingClientRect(){return {left:100,right:760,top:50,bottom:650};},
   querySelector(selector){const match=selector.match(/^\[data-start-type="(.+)"\]$/);const journey=selector.match(/^\[data-start-journey="(.+)"\]$/);return node(match?'type-'+match[1]:journey?'journey-'+journey[1]:selector);},querySelectorAll(selector){return selector==='[data-start-journey]'?journeys:radios;}});
  return nodes.get(key);
 };
 const radios=['video','carousel','presentation'].map(type=>{const button=node('type-'+type);button.dataset.startType=type;return button;});
 const journeys=['idea','footage'].map(start=>{const button=node('journey-'+start);button.dataset.startJourney=start;return button;});
 const document={body:{append(){}},activeElement:node('opener'),createElement:()=>node('dialog'),querySelector:node,addEventListener:(type,fn)=>documentHandlers[type]=fn};
 let referenceConfig,depth=0;const referenceAPI={restore:rows=>Array.isArray(rows)?rows:[],targetKey:r=>JSON.stringify([r.reference_id,r.example_id||null,r.slide||null]),text:rows=>rows.map(r=>r.message).join('\n'),validate:async rows=>{if(options.validationWait)await options.validationWait;if(options.referenceError&&rows.length)throw Error(options.referenceError);},create:config=>{referenceConfig=config;return {busy:false,hide(){depth=0;config.showPicker(false);},back(){if(!depth)return false;depth--;config.level(depth?'library':'project');return true;},render(){}};}};
 const context={document,URLSearchParams,location:{hash:'#projects'},crypto:{randomUUID:require('node:crypto').randomUUID},esc:String,fetch:async url=>{requests.push(url);return {ok:true,json:async()=>options.scriptState||{}};},window:{StartReferences:referenceAPI,Studio:{currentSection:'projects'},addEventListener:(type,fn)=>windowHandlers[type]=fn},sessionStorage:{getItem:key=>{if(options.blocked)throw Error();return storage.get(key)||null;},setItem:(key,value)=>{if(options.blocked)throw Error();storage.set(key,value);}},navigator:{clipboard:{writeText:async text=>{if(options.wait)await options.wait;if(options.fail)throw Error('No clipboard');copies.push(text);}}},I18N:options.i18n||i18nStub()};
 runInNewContext(readFileSync(join(__dirname,'dist/start-ui.js'),'utf8'),context);
 const api=context.window.StudioStart,dialog=api.mount();api.open();
 if(!options.unselected&&!journeys.some(button=>button.attributes['aria-checked']==='true'))node('journey-footage').listeners.click();
 return {node,api,dialog,copies,requests,location:context.location,storage,windowHandlers,documentHandlers,inspire:rows=>referenceConfig.set(rows),enter:layer=>{depth=layer==='reference'?2:1;referenceConfig.level(layer);},input(id,value){node('#'+id).value=value;return node('#guided-start').listeners.input({target:{id,value,dataset:{}}});},type:type=>node('type-'+type).listeners.click(),copy:()=>node('#start-copy').listeners.click()};
}
function copiedStarterId(message){
 return /Studio starter request ID: ([0-9a-f-]{36})/.exec(message)?.[1];
}
test('only the matched project with a saved script completes the starter; Open draft is explicit',async()=>{
 const options={},h=starter(options);h.node('journey-idea').listeners.click();h.input('start-goal','A real idea.');
 await h.copy();const id=copiedStarterId(h.copies[0]);assert.ok(id);
 await h.copy();assert.equal(copiedStarterId(h.copies[1]),id);
 const match={id:'right-draft',format:'video',title:'The right draft',starter_request_id:id};
 await h.api.checkArrival([{...match,id:'wrong-draft',starter_request_id:'unrelated'}]);
 assert.equal(h.requests.length,0);
 await h.api.checkArrival([match,{...match,id:'duplicate'}]);
 assert.equal(h.requests.length,0);
 options.scriptState={project_id:match.id,version_id:null};
 await h.api.checkArrival([match]);
 assert.equal(h.node('#start-copy').textContent,'Request copied ✓');
 options.scriptState={...options.scriptState,version_id:'a'.repeat(64)};
 await h.api.checkArrival([match]);
 assert.equal(h.node('#start-copy').textContent,'Open draft');
 assert.equal(h.node('#start-status').textContent,'Your script is ready: The right draft');
 assert.equal(h.location.hash,'#projects');assert.equal(h.dialog.open,true);
 await h.copy();
 assert.equal(h.dialog.open,false);
 assert.equal(h.location.hash,'project=right-draft&stage=script');
 assert.equal(h.node('#starter-arrival').hidden,true);
});
test('a ready script waits on Projects without replacing edits to the starter, including after reload',async()=>{
 const h=starter();h.node('journey-idea').listeners.click();h.input('start-goal','First idea.');await h.copy();
 const id=copiedStarterId(h.copies[0]);assert.ok(id);
 h.input('start-goal','A different idea I am still writing.');h.api.close();
 const reloaded=starter({storage:h.storage,scriptState:{project_id:'saved-first',version_id:'b'.repeat(64)}});
 await reloaded.api.checkArrival([{id:'saved-first',format:'video',title:'First idea',starter_request_id:id}]);
 assert.equal(reloaded.node('#start-copy').textContent,'Copy request');
 assert.equal(reloaded.node('#start-goal').value,'A different idea I am still writing.');
 assert.equal(reloaded.node('#starter-arrival').hidden,false);
 reloaded.api.close();
 reloaded.documentHandlers.click({target:{closest:selector=>selector==='[data-open-starter-draft]'?{}:null},preventDefault(){}});
 assert.equal(reloaded.location.hash,'project=saved-first&stage=script');
 reloaded.api.open();assert.equal(reloaded.node('#start-goal').value,'A different idea I am still writing.');
 await reloaded.copy();assert.notEqual(copiedStarterId(reloaded.copies[0]),id);
});
test('the manual clipboard fallback carries the same exact starter ID',async()=>{
 const h=starter({fail:true});h.node('journey-idea').listeners.click();h.input('start-goal','An idea to copy manually.');
 await h.copy();const message=h.node('#project-starter').value,id=copiedStarterId(message);
 assert.ok(id);assert.equal(h.node('#start-preview').hidden,false);assert.equal(h.node('#project-starter').selected,true);
 await h.copy();assert.equal(h.node('#project-starter').value,message);
});
test('starter formats retain input and show a format-specific material handoff',()=>{
 const h=starter();h.input('start-goal','Explain my idea.');h.input('start-script','The script I recorded.');
 assert.match(h.node('#project-starter').value,/Script I recorded.*\nThe script I recorded/);assert.equal(h.node('#start-status').textContent,'Paste into your editing chat.');
 h.type('carousel');assert.equal(h.node('#start-script-field').hidden,true);assert.doesNotMatch(h.node('#project-starter').value,/The script I recorded/);assert.match(h.node('#start-status').textContent,/source material or outline/);assert.match(h.node('#start-goal').placeholder,/carousel/);
 h.type('video');assert.equal(h.node('#start-script').value,'The script I recorded.');assert.equal(h.node('#start-goal').value,'Explain my idea.');
});
test('closing and reloading keep fields, expanded details and an edited request',()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({start:'footage',goal:'A useful video',footage:'Documents/raw.mov',preview:true,messages:{video:'My custom request.'}})]]),h=starter({storage});h.api.close();assert.equal(h.dialog.open,false);h.api.open();assert.equal(h.node('#project-starter').value,'My custom request.');
 const reloaded=starter({storage:h.storage});assert.equal(reloaded.node('#start-goal').value,'A useful video');assert.equal(reloaded.node('#start-footage').value,'Documents/raw.mov');assert.equal(reloaded.node('#start-preview').open,true);assert.equal(reloaded.node('#project-starter').value,'My custom request.');
});
test('backdrop and Escape close the starter without losing its draft',()=>{
 const h=starter(),outside={target:h.dialog,clientX:10,clientY:10};h.input('start-goal','Keep my goal');
 h.dialog.listeners.pointerdown({target:h.dialog,clientX:200,clientY:100});h.dialog.listeners.click(outside);assert.equal(h.dialog.open,true);
 h.dialog.listeners.pointerdown(outside);h.dialog.listeners.click(outside);assert.equal(h.dialog.open,false);h.api.open();assert.equal(h.node('#start-goal').value,'Keep my goal');
 let prevented=false;h.dialog.listeners.cancel({preventDefault(){prevented=true;}});assert.equal(h.dialog.open,false);assert.equal(prevented,true);h.api.open();assert.equal(h.node('#start-goal').value,'Keep my goal');
});
test('explicit copy keeps the starter open and gives the correct next step',async()=>{
 const h=starter();assert.equal(h.copies.length,0);h.input('start-goal','My video goal.');const expected=h.node('#project-starter').value;await h.copy();assert.deepEqual(h.copies,[expected]);assert.equal(h.dialog.open,true);assert.equal(h.node('#start-done').textContent,'Done');assert.match(h.node('#start-status').textContent,/Request copied.*Paste into your editing chat/);
 h.input('start-footage','Documents/raw.mov');await h.copy();assert.match(h.copies[1],/Documents\/raw.mov/);assert.equal(h.node('#start-status').textContent,'Request copied. Paste into your editing chat.');
});
test('clipboard failure reveals the same request for manual copying',async()=>{
 const h=starter({fail:true}),text=h.node('#project-starter').value;await h.copy();assert.equal(h.dialog.open,true);assert.equal(h.node('#start-preview').open,true);assert.equal(h.node('#project-starter').value,text);assert.equal(h.node('#project-starter').selected,true);assert.match(h.node('#start-status').textContent,/Select and copy/);assert.equal(h.copies.length,0);
});
test('a late clipboard result does not claim that a changed request was copied',async()=>{
 let finish;const wait=new Promise(resolve=>finish=resolve),h=starter({wait});h.input('start-goal','First request');const expected=h.node('#project-starter').value,pending=h.copy();await new Promise(resolve=>setImmediate(resolve));h.input('start-goal','Second request');finish();await pending;assert.deepEqual(h.copies,[expected]);assert.equal(h.node('#start-copy').textContent,'Copy request');
});
test('keyboard format changes work and blocked storage still keeps an in-memory draft',()=>{
 const h=starter({blocked:true});h.input('start-goal','Keep this without storage');let prevented=false;h.node('type-video').listeners.keydown({key:'ArrowRight',preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(h.node('type-carousel').attributes['aria-checked'],'true');assert.equal(h.node('type-carousel').focused,true);h.type('video');h.api.close();h.api.open();assert.equal(h.node('#start-goal').value,'Keep this without storage');
});

test('file-location disclosure is optional, remembered, and uses plain chat instructions',()=>{
 const h=starter();assert.equal(h.node('#start-location').open,false);assert.match(h.node('#start-material-help').textContent,/Attach your raw video in chat after copying/);assert.equal(h.node('#start-copy').textContent,'Copy request');assert.equal(h.node('#start-status').textContent,'Paste into your editing chat.');assert.equal(h.node('#start-material-help').hidden,true);
 h.node('#start-location').open=true;h.input('start-footage','Footage/raw.mov');h.api.close();const next=starter({storage:h.storage});assert.equal(next.node('#start-location').open,true);assert.match(next.node('#project-starter').value,/Footage\/raw.mov/);
});
test('inspiration travels with the script and stays after the spoken-cut instructions',()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({inspiration:[{message:'Exact technique: http://localhost/#technique=type&example=chosen'}]})]]),h=starter({storage});h.input('start-script','The supplied script');const message=h.node('#project-starter').value;
 assert.match(message,/The supplied script/);assert.match(message,/spoken cut first/);assert.match(message,/If speech is already edited, preserve its words and timing/);assert.match(message,/Keep any selected inspiration for the visual-edit stage/);assert.match(message,/#technique=type&example=chosen/);h.type('presentation');assert.match(h.node('#project-starter').value,/#technique=type&example=chosen/);assert.doesNotMatch(h.node('#project-starter').value,/The supplied script/);
});
// Fix round 1 (CRITICAL, coordinator review): start-ui.js is a `defer`red script, so its
// module-top-level code runs before I18N.ready resolves in the real app (i18n.js's own
// fetch for the language strings is still in flight at that point). This stub models that
// exact timing: `t()` returns the raw key -- the same fallback i18n.js itself uses for a
// key with no value in `strings` yet -- until `becomeReady()` flips it over, which this
// test calls only *after* `starter()` (and therefore any module-load-time code) has
// already run, mirroring I18N.ready resolving sometime after the deferred script executed
// but before the user interacts with it.
function notReadyThenReadyI18N(){
 const en=JSON.parse(readFileSync(join(__dirname,'dist/i18n/en.json'),'utf8'));
 let ready=false;
 return {becomeReady(){ready=true;},stub:{ready:new Promise(()=>{}),lang:()=>'en',t(key,vars){if(!ready)return key;const value=en[key]??key;if(!vars)return value;return Object.keys(vars).reduce((text,name)=>text.split('{'+name+'}').join(vars[name]),value);}}};
}
test('a deferred module-load-time I18N.t() call never bakes a raw key into the inspiration heading',()=>{
 const {becomeReady,stub}=notReadyThenReadyI18N();
 const h=starter({i18n:stub}); // start-ui.js's module body -- including any top-level I18N.t() call -- has already run here, with I18N not yet "ready".
 becomeReady(); // mirrors I18N.ready resolving before the user actually interacts.
 h.inspire([{message:'Exact reference'}]);
 const message=h.node('#project-starter').value;
 assert.doesNotMatch(message,/start\.chat\.inspirationMarker/);
 assert.match(message,/Inspiration for the visual edit/);
});
// Fix round 2 (CRITICAL, coordinator review): round 1's INSPIRATION_SENTINEL was
// '​inspiration-for-visual-edit​' -- only the two ends were zero-width; the
// 27 ASCII characters in the middle were plain visible text that landed, untranslated,
// in every pasted chat draft that had inspiration attached. A stub whose `t()` always
// returns real text (unlike notReadyThenReadyI18N above) is enough to catch this --
// the bug was in the sentinel's own shape, not in when I18N.t() got called.
function toggleableI18N(){
 const en=JSON.parse(readFileSync(join(__dirname,'dist/i18n/en.json'),'utf8')),he=JSON.parse(readFileSync(join(__dirname,'dist/i18n/he.json'),'utf8'));
 let lang='en';
 return {setLang(l){lang=l;},stub:{ready:Promise.resolve(),lang:()=>lang,t(key,vars){const value=(lang==='he'?he:en)[key]??key;if(!vars)return value;return Object.keys(vars).reduce((text,name)=>text.split('{'+name+'}').join(vars[name]),value);}}};
}
test('the copied value never leaks the visible sentinel text or raw zero-width characters',async()=>{
 const {stub}=toggleableI18N(),h=starter({i18n:stub});
 h.inspire([{message:'Exact reference'}]);
 await h.copy();
 const copied=h.copies[0];
 assert.doesNotMatch(copied,/inspiration-for-visual-edit/);
 assert.equal(/[​‌]/.test(copied),false,'the copied text must not contain any zero-width sentinel characters');
 assert.match(copied,/Inspiration for the visual edit/); // the real, translated heading is still there -- only the sentinel is stripped
});
test('toggling the UI language re-renders an existing inspiration heading without duplicating it',()=>{
 const {setLang,stub}=toggleableI18N(),h=starter({i18n:stub});
 h.inspire([{message:'Exact reference'}]);
 assert.match(h.node('#project-starter').value,/Inspiration for the visual edit/);
 setLang('he');
 h.documentHandlers['i18n:change']();
 const message=h.node('#project-starter').value;
 assert.doesNotMatch(message,/Inspiration for the visual edit/);
 assert.equal((message.match(/השראה לעריכה החזותית/g)||[]).length,1);
 assert.match(message,/Exact reference/);
});
test('an old-format draft (saved before the sentinel existed) migrates its inspiration block without duplicating it',()=>{
 const legacyHeading='\n\nInspiration for the visual edit (save these exact references with the project):\n';
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({messages:{video:'My custom message.'+legacyHeading+'Old reference text'},inspiration:[{message:'Fresh reference text'}]})]]);
 const h=starter({storage});
 const message=h.node('#project-starter').value;
 assert.equal((message.match(/Inspiration for the visual edit/g)||[]).length,1);
 assert.match(message,/^My custom message\./);
 assert.match(message,/Fresh reference text/);
 assert.doesNotMatch(message,/Old reference text/);
});
test('a stale reference blocks copying while preserving the whole draft',async()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({goal:'Keep my idea',inspiration:[{message:'old exact reference'}]})]]),h=starter({storage,referenceError:'The selected source changed.'});await h.copy();assert.equal(h.copies.length,0);assert.match(h.node('#start-status').textContent,/source changed/);assert.equal(h.node('#start-goal').value,'Keep my idea');assert.equal(h.dialog.open,true);
});

test('choosing inspiration preserves an edited project request and replaces only its generated reference section',()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({start:'footage',messages:{video:'My carefully edited goal.'}})]]),h=starter({storage});h.inspire([{message:'Exact first reference'}]);assert.match(h.node('#project-starter').value,/^My carefully edited goal/);assert.match(h.node('#project-starter').value,/Exact first reference/);h.inspire([{message:'Exact second reference'}]);assert.match(h.node('#project-starter').value,/^My carefully edited goal/);assert.match(h.node('#project-starter').value,/Exact second reference/);assert.doesNotMatch(h.node('#project-starter').value,/Exact first reference/);
});

test('a failed reference recheck clears an earlier copied confirmation',async()=>{
 const options={storage:new Map([['ai-video-studio-starter-v2',JSON.stringify({inspiration:[{message:'Exact reference'}]})]])},h=starter(options);await h.copy();assert.equal(h.node('#start-copy').textContent,'Request copied ✓');options.referenceError='Source changed.';await h.copy();assert.equal(h.copies.length,1);assert.equal(h.node('#start-copy').textContent,'Copy request');assert.match(h.node('#start-status').textContent,/Remove the affected reference/);
});

test('closing during reference validation never copies and leaves the starter usable',async()=>{
 let finish;const validationWait=new Promise(resolve=>finish=resolve),h=starter({validationWait});h.input('start-goal','Keep my pending draft');const pending=h.copy();h.api.close();finish();await pending;assert.equal(h.copies.length,0);h.api.open();assert.equal(h.node('#start-copy').disabled,false);assert.equal(h.node('#start-goal').value,'Keep my pending draft');await h.copy();assert.equal(h.copies.length,1);
});

test('X and Escape return through nested reference views before closing the project starter',()=>{
 const h=starter();h.input('start-goal','Preserve my project');h.enter('reference');assert.equal(h.node('#start-close').attributes['aria-label'],'Back to references');h.node('#start-close').listeners.click();assert.equal(h.dialog.open,true);assert.equal(h.node('#start-close').attributes['aria-label'],'Back to project');h.dialog.listeners.cancel({preventDefault(){}});assert.equal(h.dialog.open,true);assert.equal(h.node('#start-close').attributes['aria-label'],'Close project starter');h.node('#start-close').listeners.click();assert.equal(h.dialog.open,false);h.api.open();assert.equal(h.node('#start-goal').value,'Preserve my project');
});
test('additional details and other links have explicit optional labels',()=>{
 const h=starter();assert.match(h.dialog.innerHTML,/Details to preserve<\/span> <small>optional/);assert.match(h.dialog.innerHTML,/Other links and what you like<\/span> <small>optional/);assert.doesNotMatch(h.dialog.innerHTML,/required/);assert.equal(h.node('#start-keep-label').textContent,'Details to preserve');
});

test('captured Escape handles one level once even when focus has left a replaced video control',()=>{
 const h=starter();h.enter('reference');let prevented=0,stopped=0;const event={key:'Escape',repeat:false,preventDefault(){prevented++;},stopPropagation(){stopped++;}};h.documentHandlers.keydown(event);assert.equal(h.dialog.open,true);assert.equal(h.node('#start-close').attributes['aria-label'],'Back to project');h.documentHandlers.keydown({...event,repeat:true});assert.equal(h.node('#start-close').attributes['aria-label'],'Back to project');h.documentHandlers.keydown(event);assert.equal(h.dialog.open,true);h.documentHandlers.keydown(event);assert.equal(h.dialog.open,false);assert.equal(prevented,4);assert.equal(stopped,4);
});

test('scene changes retain the filmstrip, overview, disclosure and navigation controls',()=>{
 const media={innerHTML:''},details={open:true},notes={innerHTML:'',querySelector:()=>details},position={},previous={},next={};
 const thumbs=Array.from({length:3},(_,i)=>({dataset:{projectFrame:String(i)},attributes:{},setAttribute(k,v){this.attributes[k]=v;}}));
 const filmstrip={scrollLeft:340,overview:true},controls={},feedback={draft:'Keep my scene note'};
 const parts={'[data-scene-media]':media,'[data-scene-notes]':notes,'[data-scene-position]':position,'[data-frame-step="-1"]':previous,'[data-frame-step="1"]':next,'.project-thumbs':filmstrip,'#review-controls':controls,'#feedback-panel':feedback};
 const container={querySelector:s=>parts[s],querySelectorAll:()=>thumbs};
 const context={window:{},esc:String,document:{addEventListener(){}},I18N:i18nStub()};
 runInNewContext(readFileSync(join(__dirname,'dist/review-layout.js'),'utf8'),context);
 const a={type:'board',frames:Array.from({length:3},(_,i)=>({title:'Scene '+(i+1),available:true,url:'/scene-'+i+'.png',path:'scene-'+i+'.png',speech:'Line '+i}))};
 assert.equal(context.window.ReviewLayout.updateFrame(container,a,2),true);
 assert.match(media.innerHTML,/scene-2.png/);assert.match(notes.innerHTML,/Scene 3/);assert.equal(position.textContent,'3 / 3 · Scene');
 assert.equal(next.disabled,true);assert.equal(previous.disabled,false);assert.equal(details.open,true);
 assert.deepEqual(thumbs.map(t=>t.attributes['aria-pressed']),['false','false','true']);
 assert.equal(container.querySelector('.project-thumbs'),filmstrip);assert.equal(filmstrip.scrollLeft,340);assert.equal(filmstrip.overview,true);
 assert.equal(container.querySelector('#review-controls'),controls);assert.equal(feedback.draft,'Keep my scene note');
 assert.equal(context.window.ReviewLayout.updateFrame(container,a,0),true);assert.equal(previous.disabled,true);
 assert.equal(context.window.ReviewLayout.updateFrame(container,a,99),false);
});


test('automatic filmstrip reveal scrolls only horizontally and respects the overview',()=>{
 const strip={scrollLeft:200,classList:{contains:()=>false},getBoundingClientRect:()=>({left:100,right:600})};
 const selected={getBoundingClientRect:()=>({left:690,right:775})};
 const context={window:{},esc:String,document:{addEventListener(){}}};
 runInNewContext(readFileSync(join(__dirname,'dist/review-layout.js'),'utf8'),context);
 const container={querySelector:s=>s==='.project-thumbs'?strip:selected};
 context.window.ReviewLayout.revealFrame(container);assert.equal(strip.scrollLeft,379);
 selected.getBoundingClientRect=()=>({left:120,right:205});context.window.ReviewLayout.revealFrame(container);assert.equal(strip.scrollLeft,379);
 selected.getBoundingClientRect=()=>({left:20,right:105});context.window.ReviewLayout.revealFrame(container);assert.equal(strip.scrollLeft,295);
 strip.classList.contains=()=>true;context.window.ReviewLayout.revealFrame(container);assert.equal(strip.scrollLeft,295);
});

test('idea-first request uses writing context and does not require recorded footage',async()=>{
 const h=starter();h.node('journey-idea').listeners.click();h.input('start-goal','Explain the idea.');h.input('start-script','An opening draft.');h.input('start-references','A reference and what I like.');h.input('start-scriptreference','A video opening I want to adapt.');
 const message=h.node('#project-starter').value;
 assert.equal(message,'Help me write a script for a new video in this studio. Follow docs/SCRIPTING.md.\n\nIdea and audience: Explain the idea.\n\nInitial script draft:\nAn opening draft.\n\nScript reference and what I like: A video opening I want to adapt.');
 assert.doesNotMatch(message,/attach my raw video|Script I recorded|spoken cut first/);assert.equal(h.node('#start-location').hidden,true);
 await h.copy();assert.match(h.node('#start-status').textContent,/develop your script/);
 const id=copiedStarterId(h.copies[0]);assert.ok(id);assert.equal(h.copies[0],message+'\n\nStudio starter request ID: '+id);
 h.api.close();const restored=starter({storage:h.storage});assert.equal(restored.node('journey-idea').attributes['aria-checked'],'true');assert.match(restored.node('#project-starter').value,/An opening draft/);
});
test('journey switches retain legacy request text without hidden overrides in the writing path',()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({start:'idea',goal:'My visible idea.',messages:{video:'My edited footage request.','video-idea':'My earlier custom writing request.'}})]]),h=starter({storage});
 assert.match(h.node('#project-starter').value,/My visible idea/);assert.doesNotMatch(h.node('#project-starter').value,/earlier custom writing/);
 h.node('journey-footage').listeners.click();assert.equal(h.node('#project-starter').value,'My edited footage request.');h.node('journey-idea').listeners.click();assert.match(h.node('#project-starter').value,/My visible idea/);
 h.type('carousel');assert.equal(h.node('#start-journeys').hidden,true);h.type('video');assert.match(h.node('#project-starter').value,/My visible idea/);
 assert.equal(JSON.parse(h.storage.get('ai-video-studio-starter-v2')).messages['video-idea'],'My earlier custom writing request.');
});
test('Script navigation is hidden (Script screen out of scope for Task 4) but the underlying stage never creates a review approval',()=>{
 const context={window:{},document:{addEventListener(){}},esc:String,I18N:i18nStub()};runInNewContext(readFileSync(join(__dirname,'dist/review-layout.js'),'utf8'),context);
 const layout=context.window.ReviewLayout,p={format:'video',artifacts:[{id:'spoken-v1',type:'video',label:'Spoken cut'}],primary_artifact:'spoken-v1'};
 assert.doesNotMatch(layout.navigation(p,p.artifacts[0]),/data-stage="script"/);assert.equal(layout.versions(p,'script')[0].type,'script');
 assert.equal(layout.content(p,layout.script(p),0),'');p.format='carousel';assert.doesNotMatch(layout.navigation(p,p.artifacts[0]),/data-stage="script"/);
});

function scriptEditor(options={}){
 const copies=[],calls=[],storage=options.storage||new Map(),handlers={},nodes=new Map();
 const decode=value=>value.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&amp;/g,'&');
 const escape=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
 class Node{
  constructor(){this.children=new Map();this.style={};this.hidden=false;this.isConnected=true;this.value='';this.textContent='';this.scrollHeight=740;this.listeners={};this.dataset={};}
  set innerHTML(value){this.html=value;this.children.clear();}get innerHTML(){return this.html||'';}
  querySelector(selector){
   if(this.children.has(selector))return this.children.get(selector);
   const attr=selector.startsWith('[')?selector.slice(1,-1):selector;
   const match=this.innerHTML.match(new RegExp('<[^>]*'+attr+'[^>]*>'));
   if(!match)return null;
   const child=new Node();child.hidden=/\shidden(?:\s|>)/.test(match[0]);
   if(/^<textarea/.test(match[0]))child.value=decode(this.innerHTML.match(new RegExp('<textarea[^>]*'+attr+'[^>]*>([\\s\\S]*?)</textarea>'))[1]);
   if(attr==='data-script-status')child.textContent=decode(this.innerHTML.match(/<p[^>]*data-script-status[^>]*>([\s\S]*?)<\/p>/)[1]);
   if(attr.startsWith('data-use-hook'))child.dataset.useHook=match[0].match(/data-use-hook="([^"]+)"/)[1];
   child.open=/\sopen(?:\s|>)/.test(match[0]);
   this.children.set(selector,child);return child;
  }
  querySelectorAll(selector){return selector==='[data-use-hook]'?[...this.innerHTML.matchAll(/data-use-hook="([^"]+)"/g)].map(m=>this.querySelector('[data-use-hook="'+m[1]+'"]')):[];}
  addEventListener(name,fn){this.listeners[name]=fn;}closest(){return {hidden:false};}focus(){this.focused=true;}select(){this.selected=true;}showModal(){this.open=true;}scrollIntoView(){this.scrolled=true;}
 }
 const node=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
 let saved={project_id:'test',title:'Example',revision:'r1',version_id:'a'.repeat(64),current_version_id:'a'.repeat(64),text:'Current draft.',versions:[{id:'a'.repeat(64)}],version_count:1,assembled:null,...options.data};
 const original={...saved},savedTexts=new Map([[saved.version_id,saved.text]]);
 const feedbackRequests=[];let selectedHook='current';
 const hooks=()=>({revision:'h1',selected_id:selectedHook,options:selectedHook?options.hooks||[]:[]});
 let brief={idea:'The creator’s original idea.',references:'https://example.org/clip — the opening question.',ready_script:null,revision:'b1',...options.brief};
 const context={window:{addEventListener:(name,fn)=>handlers[name]=fn},document:{hidden:false},$:node,esc:escape,location:{hash:'#project=test&stage=script',href:'http://localhost:6000/'},URL,URLSearchParams,crypto:{randomUUID:()=>require('node:crypto').randomUUID()},history:{replaceState(){}},setInterval:fn=>handlers.refresh=fn,sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},navigator:{clipboard:{writeText:async text=>{if(options.clipboardWait)await options.clipboardWait;if(options.failCopy)throw Error('Clipboard unavailable');copies.push(text);}}},fetch:async(url,init)=>{
  calls.push({url,init});
  if(url==='/script-ready'){
   const body=JSON.parse(init.body);
   if(body.revision!==brief.revision||body.script_version!==saved.current_version_id||body.script_revision!==saved.revision)return {ok:false,status:409,json:async()=>({error:'The saved script changed.'})};
   brief={...brief,revision:brief.revision+'x',ready_script:body.ready?body.script_version:null};
   return {ok:true,json:async()=>({...brief,ready:body.ready})};
  }
  if(url.startsWith('/script-hooks')){if(options.hooksWait)await options.hooksWait;return {ok:true,json:async()=>hooks()};}
  if(url.startsWith('/script-feedback')){
   if(init?.method==='POST'){
    if(options.feedbackWait)await options.feedbackWait;
    if(options.feedbackError)return {ok:false,status:503,json:async()=>({error:'Feedback save unavailable.'})};
    const body=JSON.parse(init.body),record={...body,id:body.request_id,content_revision:'c'.repeat(64)};if(!feedbackRequests.some(r=>r.id===record.id))feedbackRequests.push(record);return {ok:true,json:async()=>record};
   }return {ok:true,json:async()=>({requests:feedbackRequests})};
  }
  if(init?.method==='POST'){
   if(options.saveWait)await options.saveWait;
   if(options.conflict)return {ok:false,status:409,json:async()=>({error:'This script changed elsewhere.'})};
   const body=JSON.parse(init.body),text=url==='/script-hook'?options.variantText:body.text;
   selectedHook=url==='/script-hook'?body.option_id:text===original.text?'current':null;
   const known=[...savedTexts].find(([,value])=>value===text),id=known?.[0]||'bcdef'[savedTexts.size-1].repeat(64);savedTexts.set(id,text);
   saved={...saved,text,revision:'r'+(calls.filter(c=>c.init?.method==='POST').length+1),version_id:id,current_version_id:id,versions:[...savedTexts.keys()].reverse().map(id=>({id})),version_count:savedTexts.size,hooks:hooks()};
  }
  const requested=new URL(url,'http://localhost').searchParams.get('version');const value=url.startsWith('/script-brief')?{...brief,ready:brief.ready_script===saved.current_version_id}:{...saved,...options.versionData?.[requested]};
  return {ok:true,json:async()=>value};
 }};
 runInNewContext(readFileSync(join(__dirname,'dist/project-script-ui.js'),'utf8'),context);
 const panel=node('#project-script-panel');
 return {api:context.window.ProjectScript,panel,node,copies,calls,storage,handlers,context,feedbackRequests,updateSaved:delta=>{saved={...saved,...delta};},updateBrief:delta=>{brief={...brief,...delta};},async mount(full=true){await context.window.ProjectScript.mount({id:'test',title:'Example',format:'video',stage:options.stage||'script'},{type:full?'script':'video'});},field:()=>panel.querySelector('[data-script-text]'),button:name=>panel.querySelector('[data-'+name+']'),input(text){const field=this.field();field.value=text;field.listeners.input();}};
}

test('Script keeps context under Project details and retains an unsaved draft through reload',async()=>{
 const h=scriptEditor();await h.mount();
 assert.doesNotMatch(h.panel.innerHTML,/Idea & references|Save context|FROM THOUGHT|Your writing preferences|data-script-idea/);
 assert.match(h.node('#project-script-context').innerHTML,/The creator’s original idea/);assert.match(h.node('#project-script-context').innerHTML,/https:\/\/example.org\/clip/);
 assert.equal(h.button('save-script').hidden,true);assert.equal(h.button('reload-script').hidden,true);assert.equal(h.field().style.height,'742px');
 h.input('Keep this unsaved revision.');assert.equal(h.button('save-script').hidden,false);assert.equal(h.button('copy-script-feedback').disabled,true);
 const reloaded=scriptEditor({storage:h.storage});await reloaded.mount();assert.equal(reloaded.field().value,'Keep this unsaved revision.');assert.equal(reloaded.api.hasDraft(),true);
 await reloaded.button('save-script').onclick();assert.equal(reloaded.api.hasDraft(),false);assert.equal(reloaded.button('save-script').hidden,true);
});

test('Script refinement pins feedback to the exact version and stays a writing request with legacy readiness metadata',async()=>{
 const h=scriptEditor();await h.mount();await h.button('copy-script').onclick();assert.equal(h.copies.length,0);assert.equal(h.button('script-feedback').focused,true);h.button('script-feedback').value='Give me a stronger opening.';h.button('script-feedback').listeners.input();await h.button('copy-script-feedback').onclick();
 assert.equal(h.copies.length,1);assert.match(h.copies[0],new RegExp('script='+'a'.repeat(64)));assert.match(h.copies[0],/compatible opening options/);
 assert.match(h.copies[0],/Give me a stronger opening/);assert.match(h.copies[0],/script-feedback=/);assert.doesNotMatch(h.copies[0],/attach my recorded footage|build or refine the spoken cut/);assert.match(h.button('script-feedback-status').textContent,/paste into your editing chat/);
 const spoken=scriptEditor();spoken.context.ReviewLayout={stage:()=> 'spoken'};await spoken.mount(false);await spoken.button('copy-script').onclick();assert.match(spoken.copies[0],/attach my recorded footage/);
});

test('a conflicting script save keeps the draft and reveals comparison before retrying',async()=>{
 const options={conflict:true},h=scriptEditor(options);await h.mount();h.input('My local changes.');await h.button('save-script').onclick();
 assert.equal(h.field().value,'My local changes.');assert.equal(h.button('reload-script').hidden,false);assert.equal(h.button('save-script').disabled,true);
 await h.button('reload-script').onclick();assert.equal(h.button('saved-comparison').hidden,false);assert.equal(h.field().value,'My local changes.');assert.equal(h.button('save-script').disabled,false);
 options.conflict=false;await h.button('save-script').onclick();assert.equal(h.api.hasDraft(),false);
});

test('choosing a saved version while editing never replaces or drops the local draft',async()=>{
 const h=scriptEditor();await h.mount();h.input('Keep my draft while browsing history.');const menu=h.button('script-history');menu.value='b'.repeat(64);await menu.onchange();
 assert.equal(h.field().value,'Keep my draft while browsing history.');assert.match(h.button('script-status').textContent,/Save your draft/);assert.equal(menu.value,'a'.repeat(64));
 assert.equal(h.calls.filter(c=>c.init?.method==='POST').length,0);
});

test('a fresh video starter reveals fields only after an explicit, keyboard-accessible journey choice',()=>{
 const h=starter({unselected:true});
 assert.equal(h.node('#start-fields').hidden,true);assert.equal(h.node('#start-copy').hidden,true);assert.equal(h.node('#start-footer').hidden,true);assert.equal(h.node('journey-idea').attributes['aria-checked'],'false');assert.equal(h.node('journey-idea').tabIndex,0);
 assert.match(h.dialog.innerHTML,/Help me write a script<small>Start with an idea, draft, or reference/);
 const keyboard=starter({unselected:true});keyboard.node('journey-idea').listeners.keydown({key:'ArrowRight',preventDefault(){}});assert.equal(keyboard.node('journey-footage').attributes['aria-checked'],'true');
 h.node('journey-idea').listeners.click();assert.equal(h.node('#start-fields').hidden,false);assert.equal(h.node('#start-script-field').open,false);assert.equal(h.node('#start-script-reference-field').open,false);
 for(const id of ['start-inspiration','start-extras','start-preview'])assert.equal(h.node('#'+id).hidden,true);
 assert.equal(h.node('#start-copy').disabled,true);
 h.node('journey-idea').listeners.keydown({key:'ArrowRight',preventDefault(){}});assert.equal(h.node('journey-footage').attributes['aria-checked'],'true');assert.equal(h.node('journey-footage').focused,true);assert.equal(h.node('#start-location').hidden,false);
});

test('an idea, a draft, or a reference can each start script writing without filling the other fields',async()=>{
 for(const [id,value] of [['start-goal','Show how this feature works.'],['start-script','My existing opening draft.'],['start-scriptreference','https://example.org/video — borrow its opening question.']]){
  const h=starter({unselected:true});h.node('journey-idea').listeners.click();h.input(id,value);assert.equal(h.node('#start-copy').disabled,false);await h.copy();assert.equal(h.copies.length,1);assert.ok(h.copies[0].includes(value));assert.match(h.copies[0],/Follow docs\/SCRIPTING\.md/);assert.ok(copiedStarterId(h.copies[0]));assert.doesNotMatch(h.copies[0],/attach my raw video/);
  h.api.close();const restored=starter({storage:h.storage});assert.equal(restored.node('#'+id).value,value);assert.equal(restored.node('journey-idea').attributes['aria-checked'],'true');
 }
});

test('hidden editing context cannot leak into or block the simple writing request',async()=>{
 const storage=new Map([['ai-video-studio-starter-v2',JSON.stringify({start:'footage',keep:'Keep this footage-only detail.',references:'Other old editing link.',inspiration:[{message:'An old exact visual example.'}]})]]);
 const h=starter({storage,referenceError:'This visual source changed.'});h.node('journey-idea').listeners.click();h.input('start-goal','My new script idea.');await h.copy();
 assert.equal(h.copies.length,1);assert.doesNotMatch(h.copies[0],/footage-only detail|Other old editing link|old exact visual example/);
 h.node('journey-footage').listeners.click();assert.match(h.node('#project-starter').value,/Keep this footage-only detail/);assert.match(h.node('#project-starter').value,/An old exact visual example/);await h.copy();assert.equal(h.copies.length,1);assert.match(h.node('#start-status').textContent,/source changed/);
});

test('script clipboard failure reveals a manual-copy fallback only when needed',async()=>{
 const h=starter({fail:true,unselected:true});h.node('journey-idea').listeners.click();h.input('start-goal','Keep this idea through a clipboard failure.');assert.equal(h.node('#start-preview').hidden,true);await h.copy();
 assert.equal(h.node('#start-preview').hidden,false);assert.equal(h.node('#start-preview').open,true);assert.equal(h.node('#project-starter').readOnly,true);assert.equal(h.node('#project-starter').selected,true);assert.match(h.node('#project-starter').value,/Keep this idea/);assert.match(h.node('#start-status').textContent,/Select and copy/);
});


test('footage starts with a brief, collapsed script, unified inspiration and a read-only message',async()=>{
 const h=starter();assert.equal(h.node('#start-goal-label').textContent,'What would you like to make?');assert.equal(h.node('#start-extras').hidden,true);assert.equal(h.node('#start-other-links').hidden,true);assert.equal(h.node('#start-script-field').open,false);assert.equal(h.node('#start-script-summary').textContent,'Add your recorded script');assert.equal(h.node('#start-inspiration-title').textContent,'Add inspiration');
 assert.equal(h.node('#start-preview').hidden,true);assert.equal(h.node('#project-starter').readOnly,true);assert.equal(h.node('#start-see-message').hidden,false);
 h.input('start-goal','Show my workflow and preserve the sponsor line.');const expected=h.node('#project-starter').value;
 h.node('#start-see-message').listeners.click();assert.equal(h.node('#start-preview').hidden,false);assert.equal(h.node('#start-preview').open,true);assert.equal(h.node('#start-see-message').attributes['aria-expanded'],'true');await h.copy();assert.equal(h.copies[0],expected);
 h.node('#start-see-message').listeners.click();assert.equal(h.node('#start-preview').hidden,true);assert.equal(h.node('#start-see-message').textContent,'See message');
});
test('earlier requirements are editable in the footage brief without leaking into script writing',()=>{
 const original={start:'footage',goal:'My video.',keep:'Preserve the exact sponsor wording.',references:'https://example.org/old — borrow the opening.'},storage=new Map([['ai-video-studio-starter-v2',JSON.stringify(original)]]),h=starter({storage});
 assert.match(h.node('#start-goal').value,/My video[\s\S]*Preserve the exact sponsor wording/);assert.equal(h.node('#start-other-links').hidden,false);assert.equal(h.node('#start-other-links-label').textContent,'Your saved links and notes');assert.equal(h.node('#start-inspiration').open,true);
 h.input('start-goal','My updated video. Keep the disclaimer.');assert.doesNotMatch(h.node('#project-starter').value,/sponsor wording/);h.api.close();const reloaded=starter({storage});assert.equal(reloaded.node('#start-goal').value,'My updated video. Keep the disclaimer.');assert.match(reloaded.node('#project-starter').value,/example.org\/old/);
 reloaded.node('journey-idea').listeners.click();assert.doesNotMatch(reloaded.node('#project-starter').value,/sponsor wording|Keep the disclaimer|example.org\/old/);assert.equal(JSON.parse(storage.get('ai-video-studio-starter-v2')).keep,original.keep);
});
test('recorded scripts open when populated and remain optional when empty after reload',()=>{
 const h=starter();h.input('start-script','My supplied original.');h.api.close();const restored=starter({storage:h.storage});assert.equal(restored.node('#start-script-field').open,true);assert.match(restored.node('#project-starter').value,/My supplied original/);assert.equal(restored.node('#start-preview').hidden,true);
});
test('footage clipboard fallback reveals the exact read-only handoff',async()=>{
 const h=starter({fail:true});h.input('start-goal','My demonstration.');const expected=h.node('#project-starter').value;await h.copy();assert.equal(h.node('#project-starter').readOnly,true);assert.equal(h.node('#start-preview').hidden,false);assert.equal(h.node('#project-starter').value,expected);assert.equal(h.node('#project-starter').selected,true);
});


test('Script keeps all opening choices visible and marks the chosen opening without scrolling away',async()=>{
 const options={hooks:[{id:'current',opening:'Current draft.'},{id:'other',opening:'Another opening.'},{id:'third',opening:'A third opening.'}],variantText:'Another opening.\n\nThe same body.'},h=scriptEditor(options);await h.mount();assert.match(h.panel.innerHTML,/Hook options/);assert.equal(h.panel.querySelectorAll('[data-use-hook]').length,3);assert.match(h.panel.innerHTML,/data-use-hook="current" aria-pressed="true"/);assert.doesNotMatch(h.panel.innerHTML,/data-other-openings/);
 await h.panel.querySelector('[data-use-hook="other"]').onclick();assert.equal(h.field().value,options.variantText);const request=JSON.parse(h.calls.find(c=>c.url==='/script-hook').init.body);assert.equal(request.script_version,'a'.repeat(64));assert.equal(request.hook_revision,'h1');assert.equal(request.option_id,'other');assert.match(h.panel.innerHTML,/Opening updated/);assert.match(h.panel.innerHTML,/data-use-hook="other" aria-pressed="true"/);assert.match(h.panel.innerHTML,/opening-changed/);assert.equal(h.button('undo-opening').hidden,false);assert.equal(h.panel.scrolled,undefined);assert.equal(h.panel.querySelector('[data-use-hook="other"]').focused,true);
});
test('unsaved scripts block hook changes while offering Save & copy feedback',async()=>{
 const h=scriptEditor({hooks:[{id:'current',opening:'Current draft.'},{id:'other',opening:'Another opening.'}]});await h.mount();h.input('My unsaved edit.');h.button('script-feedback').value='Make it shorter.';h.button('script-feedback').listeners.input();assert.equal(h.button('copy-script-feedback').disabled,false);assert.equal(h.button('copy-script-feedback').textContent,'Save & copy feedback');assert.equal(h.panel.querySelector('[data-use-hook="other"]').disabled,true);assert.equal(h.button('copy-script').disabled,false);await h.panel.querySelector('[data-use-hook="other"]').onclick();assert.equal(h.calls.filter(c=>c.init?.method==='POST').length,0);assert.match(h.button('feedback-hint').textContent,/Saves your changes/);
});
test('reference-only revision requests survive reload and carry one exact immutable request',async()=>{
 const h=scriptEditor();await h.mount();h.button('script-reference').value='https://example.org/new — borrow the question.';h.button('script-reference').listeners.input();assert.equal(h.button('copy-script-feedback').disabled,false);
 const restored=scriptEditor({storage:h.storage});await restored.mount();assert.equal(restored.button('script-reference').value,'https://example.org/new — borrow the question.');assert.equal(restored.button('script-feedback').value,'');await restored.button('copy-script-feedback').onclick();const request=JSON.parse(restored.calls.find(c=>c.url==='/script-feedback'&&c.init?.method==='POST').init.body);assert.equal(request.script_version,'a'.repeat(64));assert.equal(request.feedback,'');assert.match(restored.copies[0],/script-feedback=/);assert.match(restored.copies[0],/borrow the question/);assert.equal(restored.button('script-reference').value,request.references);assert.match(restored.node('#project-script-context').innerHTML,/References added during revisions/);
 await restored.button('copy-script-feedback').onclick();assert.equal(restored.feedbackRequests.length,1);assert.equal(restored.api.hasPendingFeedback(),false);
});
test('feedback save failure and clipboard fallback keep the draft without claiming it was sent',async()=>{
 const h=scriptEditor({feedbackError:true});await h.mount();h.button('script-feedback').value='Keep this feedback.';h.button('script-feedback').listeners.input();await h.button('copy-script-feedback').onclick();assert.equal(h.copies.length,0);assert.equal(h.button('script-feedback').value,'Keep this feedback.');assert.match(h.button('script-feedback-status').textContent,/unavailable/);assert.equal(h.api.hasPendingFeedback(),true);
 const fallback=scriptEditor({failCopy:true});await fallback.mount();fallback.button('script-feedback').value='Try this opening.';fallback.button('script-feedback').listeners.input();await fallback.button('copy-script-feedback').onclick();assert.equal(fallback.copies.length,0);assert.equal(fallback.node('#link-dialog').open,true);assert.match(fallback.node('#link-text').value,/Try this opening/);assert.match(fallback.node('#link-text').value,/script-feedback=/);assert.equal(fallback.api.hasPendingFeedback(),true);
});
test('late feedback preparation never copies or confirms changed input',async()=>{
 let finish;const wait=new Promise(resolve=>finish=resolve),h=scriptEditor({feedbackWait:wait});await h.mount();h.button('script-feedback').value='Earlier feedback.';h.button('script-feedback').listeners.input();const pending=h.button('copy-script-feedback').onclick();h.button('script-feedback').value='Keep my newer feedback.';h.button('script-feedback').listeners.input();finish();await pending;assert.equal(h.copies.length,0);assert.equal(h.button('script-feedback').value,'Keep my newer feedback.');assert.equal(h.button('copy-script-feedback').textContent,'Copy feedback for chat');
});
test('a late clipboard response cannot mark newly edited feedback as copied',async()=>{
 let finish;const wait=new Promise(resolve=>finish=resolve),h=scriptEditor({clipboardWait:wait});await h.mount();h.button('script-feedback').value='Earlier feedback.';h.button('script-feedback').listeners.input();const pending=h.button('copy-script-feedback').onclick();await new Promise(resolve=>setImmediate(resolve));h.button('script-feedback').value='New feedback.';h.button('script-feedback').listeners.input();finish();await pending;assert.match(h.copies[0],/Earlier feedback/);assert.equal(h.button('copy-script-feedback').textContent,'Copy feedback for chat');assert.equal(h.button('script-feedback').value,'New feedback.');assert.equal(h.api.hasPendingFeedback(),true);
});
test('a new assistant revision keeps unsent feedback on its original script',async()=>{
 const h=scriptEditor();await h.mount();h.button('script-feedback').value='Feedback on the original.';h.button('script-feedback').listeners.input();h.updateSaved({text:'New assistant revision.',revision:'r2',version_id:'b'.repeat(64),current_version_id:'b'.repeat(64),versions:[{id:'b'.repeat(64)},{id:'a'.repeat(64)}],version_count:2});await h.handlers.refresh();assert.equal(h.field().value,'Current draft.');assert.equal(h.button('script-feedback').value,'Feedback on the original.');assert.match(h.button('script-status').textContent,/newer script is saved/);await h.button('copy-script-feedback').onclick();assert.equal(h.feedbackRequests[0].script_version,'a'.repeat(64));
});
test('after feedback is copied, a new revision appears while earlier feedback remains recoverable',async()=>{
 const a='a'.repeat(64),b='b'.repeat(64),h=scriptEditor({versionData:{[a]:{version_id:a,text:'Current draft.'}}});await h.mount();h.button('script-feedback').value='My original feedback.';h.button('script-feedback').listeners.input();await h.button('copy-script-feedback').onclick();h.updateSaved({text:'The revised script.',revision:'r2',version_id:b,current_version_id:b,versions:[{id:b},{id:a}],version_count:2});await h.handlers.refresh();assert.equal(h.field().value,'The revised script.');assert.equal(h.button('script-feedback').value,'');h.button('script-history').value=a;await h.button('script-history').onchange();assert.equal(h.button('script-feedback').value,'My original feedback.');
});
test('video navigation removes Project notes as a creative stage while retaining artifact links',()=>{
 const context={window:{},document:{addEventListener(){}},esc:String,I18N:i18nStub()};runInNewContext(readFileSync(join(__dirname,'dist/review-layout.js'),'utf8'),context);const p={format:'video',artifacts:[{id:'intake',label:'Project notes',type:'document'},{id:'spoken-v1',label:'Spoken cut',type:'video'}]};assert.doesNotMatch(context.window.ReviewLayout.navigation(p,context.window.ReviewLayout.script(p)),/data-stage="notes"/);assert.equal(context.window.ReviewLayout.versions(p,'notes')[0].id,'intake');
});


test('an exact saved-script link never silently advances when an assistant saves a newer draft',async()=>{
 const h=scriptEditor();h.context.location.hash='#project=test&script='+'a'.repeat(64);await h.mount();h.updateSaved({text:'A newer script.',revision:'r2',version_id:'b'.repeat(64),current_version_id:'b'.repeat(64),versions:[{id:'b'.repeat(64)},{id:'a'.repeat(64)}],version_count:2});await h.handlers.refresh();assert.equal(h.field().value,'Current draft.');assert.match(h.button('script-status').textContent,/exact saved version/);
});

test('Edit script reveals the existing document editor and Cancel restores saved text without a write',async()=>{
 const h=scriptEditor();await h.mount();assert.equal(h.field().hidden,true);assert.equal(h.button('script-document').hidden,false);await h.button('edit-script').onclick();assert.equal(h.field().hidden,false);assert.equal(h.field().focused,true);assert.equal(h.button('script-edit-bar').hidden,false);h.input('My temporary edit.');h.button('script-feedback').value='Keep this feedback.';h.button('script-feedback').listeners.input();await h.button('cancel-script').onclick();assert.equal(h.field().value,'Current draft.');assert.equal(h.field().hidden,true);assert.equal(h.button('script-feedback').value,'Keep this feedback.');assert.equal(h.api.hasDraft(),false);assert.equal(h.calls.filter(c=>c.init?.method==='POST').length,0);
});
test('Undo restores the exact previous opening while preserving the newer version in history',async()=>{
 const h=scriptEditor({hooks:[{id:'current',opening:'Current draft.'},{id:'other',opening:'Different opening.'}],variantText:'Different opening.\n\nThe body.'});await h.mount();await h.panel.querySelector('[data-use-hook="other"]').onclick();await h.button('undo-opening').onclick();assert.equal(h.field().value,'Current draft.');assert.equal(h.button('undo-opening').hidden,true);assert.match(h.panel.innerHTML,/Previous opening restored/);assert.match(h.panel.innerHTML,/Version 2/);assert.match(h.panel.innerHTML,/Version 1 · Current/);const request=JSON.parse(h.calls.filter(c=>c.url==='/project-script'&&c.init?.method==='POST')[0].init.body);assert.equal(request.text,'Current draft.');assert.notEqual(request.revision,'r1');
});
test('Undo refuses to overwrite a concurrent revision and keeps the displayed script',async()=>{
 const options={hooks:[{id:'current',opening:'Current draft.'},{id:'other',opening:'Different opening.'}],variantText:'Different opening.'},h=scriptEditor(options);await h.mount();await h.panel.querySelector('[data-use-hook="other"]').onclick();options.conflict=true;await h.button('undo-opening').onclick();assert.equal(h.field().value,'Different opening.');assert.match(h.button('script-status').textContent,/changed elsewhere/);assert.equal(h.button('reload-script').hidden,false);assert.equal(h.button('undo-opening').disabled,true);h.updateSaved({text:'Concurrent words.',revision:'r3',version_id:'c'.repeat(64),current_version_id:'c'.repeat(64)});await h.button('reload-script').onclick();assert.equal(h.button('undo-opening').disabled,true);const writes=h.calls.filter(c=>c.init?.method==='POST').length;await h.button('undo-opening').onclick();assert.equal(h.calls.filter(c=>c.init?.method==='POST').length,writes);
});
test('Save & copy saves edited words first and pins feedback and references to the resulting version',async()=>{
 const h=scriptEditor();await h.mount();await h.button('edit-script').onclick();h.input('The words I actually want.');h.button('script-feedback').value='Make the ending sharper.';h.button('script-feedback').listeners.input();h.button('script-reference').value='https://example.org/new — borrow its question.';h.button('script-reference').listeners.input();await h.button('copy-script-feedback').onclick();const writes=h.calls.filter(c=>c.init?.method==='POST');assert.deepEqual(writes.map(c=>c.url),['/project-script','/script-feedback']);assert.equal(JSON.parse(writes[0].init.body).text,'The words I actually want.');assert.equal(JSON.parse(writes[1].init.body).script_version,'b'.repeat(64));assert.match(h.copies[0],new RegExp('script='+'b'.repeat(64)));assert.match(h.copies[0],/Make the ending sharper/);assert.match(h.copies[0],/borrow its question/);assert.equal(h.api.hasDraft(),false);assert.equal(h.field().hidden,true);const drafts=JSON.parse(h.storage.get('ai-video-studio-script-feedback-v1'));assert.equal(drafts['test/'+'a'.repeat(64)].feedback,'Make the ending sharper.');assert.equal(drafts['test/'+'b'.repeat(64)].copied,true);
});
test('a script conflict stops Save & copy before creating or copying feedback',async()=>{
 const h=scriptEditor({conflict:true});await h.mount();h.input('Keep my edited words.');h.button('script-feedback').value='Keep my feedback.';h.button('script-feedback').listeners.input();await h.button('copy-script-feedback').onclick();assert.equal(h.field().value,'Keep my edited words.');assert.equal(h.button('script-feedback').value,'Keep my feedback.');assert.equal(h.feedbackRequests.length,0);assert.equal(h.copies.length,0);assert.equal(h.api.hasDraft(),true);assert.equal(h.button('reload-script').hidden,false);
});
test('feedback failure after saving keeps the new script and can retry without another script save',async()=>{
 const options={feedbackError:true},h=scriptEditor(options);await h.mount();h.input('A saved manual revision.');h.button('script-feedback').value='Refine this version.';h.button('script-feedback').listeners.input();await h.button('copy-script-feedback').onclick();assert.equal(h.api.hasDraft(),false);assert.equal(h.button('script-feedback').value,'Refine this version.');assert.equal(h.copies.length,0);options.feedbackError=false;await h.button('copy-script-feedback').onclick();assert.equal(h.calls.filter(c=>c.url==='/project-script'&&c.init?.method==='POST').length,1);assert.equal(h.feedbackRequests[0].script_version,'b'.repeat(64));assert.equal(h.copies.length,1);
});
test('an active clean edit session is not replaced by background refresh',async()=>{
 const h=scriptEditor();await h.mount();await h.button('edit-script').onclick();h.updateSaved({text:'Assistant revision.',revision:'r2',version_id:'b'.repeat(64),current_version_id:'b'.repeat(64)});await h.handlers.refresh();assert.equal(h.field().value,'Current draft.');assert.equal(h.field().hidden,false);
});
test('reload during a version transition never rebases old on-screen text or feedback onto the chosen version',async()=>{
 const a='a'.repeat(64),b='b'.repeat(64),options={versionData:{[b]:{version_id:b,text:'Earlier saved words.'}}},h=scriptEditor(options);await h.mount();h.button('script-feedback').value='Feedback for the original.';h.button('script-feedback').listeners.input();let finish;options.hooksWait=new Promise(resolve=>finish=resolve);h.button('script-history').value=b;const loading=h.button('script-history').onchange();await new Promise(resolve=>setImmediate(resolve));h.handlers.beforeunload();const drafts=JSON.parse(h.storage.get('ai-video-studio-script-drafts-v1')),feedback=JSON.parse(h.storage.get('ai-video-studio-script-feedback-v1'));assert.equal(drafts.test.text,'Earlier saved words.');assert.equal(drafts.test.base,b);assert.equal(feedback['test/'+a].feedback,'Feedback for the original.');assert.equal(feedback['test/'+b],undefined);finish();await loading;assert.equal(h.field().value,'Earlier saved words.');assert.equal(h.button('script-feedback').value,'');
});
test('initial routing waits for deferred studio modules even when local assets respond immediately',async()=>{
 const nodes=new Map(),events={},calls=[];let routes=0;
 const node=selector=>{if(!nodes.has(selector))nodes.set(selector,{value:'',hidden:true,open:false,addEventListener(){},close(){},pause(){}});return nodes.get(selector);};
 const context={window:{addEventListener(){}},document:{readyState:'interactive',querySelector:node,querySelectorAll:()=>[],addEventListener:(name,fn)=>events[name]=fn},localStorage:{getItem:()=>null},location:{protocol:'http:',hash:'#project=example'},fetch:async url=>{calls.push(url);return {ok:url==='/catalog.json',json:async()=>({entries:[],techniques:[]})};},I18N:i18nStub()};
 runInNewContext(readFileSync(join(__dirname,'dist/app.js'),'utf8'),context);assert.deepEqual(calls,[]);context.window.Studio={route:()=>{routes++;return true;}};await events.DOMContentLoaded();assert.deepEqual(calls,['/site-settings.json','/catalog.json']);assert.equal(routes,1);
});


test('script approval saves the exact version and reveals a separate recording handoff with retained hooks and feedback',async()=>{
 const h=scriptEditor({hooks:[{id:'current',opening:'Current draft.'},{id:'other',opening:'Another hook.\n\nA bridge.'}]});
 await h.mount();
 assert.equal(h.button('record-script').hidden,true);
 h.button('script-feedback').value='A note for later.';h.button('script-feedback').listeners.input();
 await h.button('approve-script').onclick();
 const a='a'.repeat(64),request=h.calls.find(c=>c.url==='/script-ready');
 assert.equal(JSON.parse(request.init.body).script_version,a);
 assert.equal(JSON.parse(request.init.body).script_revision,'r1');
 assert.equal(h.copies.length,0);
 assert.equal(h.button('script-state').textContent,'Script approved ✓');
 assert.equal(h.button('approve-row').hidden,true);
 assert.equal(h.button('script-refinement').hidden,true);
 assert.equal(h.button('record-script').hidden,false);
 assert.match(h.panel.innerHTML,/<details class="script-openings script-hooks-approved"><summary>Hook options/);
 assert.match(h.panel.innerHTML,/Another hook[\s\S]*A bridge/);
 assert.equal(h.panel.querySelectorAll('[data-use-hook]').length,0);
 await h.button('copy-recording').onclick();
 const [intent,link]=h.copies[0].split('\n\n');
 assert.equal(intent,'Use my approved script to turn this footage into a spoken cut. Share it with me for review before storyboarding.');
 assert.deepEqual(Object.fromEntries(new URLSearchParams(new URL(link).hash.slice(1))),{project:'test',script:a,handoff:'spoken-cut'});
 assert.match(h.button('ready-status').textContent,/Copied. Paste into your editing chat and attach your raw footage/);
 await h.mount();
 assert.equal(h.button('record-script').hidden,false);
 await h.button('reopen-script').onclick();
 assert.equal(h.button('record-script').hidden,true);
 assert.equal(h.button('script-refinement').hidden,false);
 assert.equal(h.button('script-feedback').value,'A note for later.');
 assert.equal(h.panel.querySelectorAll('[data-use-hook]').length,2);
 assert.equal(h.field().value,'Current draft.');
});

test('dirty or stale script versions cannot approve, and an obsolete approval cannot copy a handoff',async()=>{
 const h=scriptEditor();await h.mount();h.input('Uncommitted words.');
 assert.equal(h.button('script-decision').hidden,true);
 await h.button('approve-script').onclick();
 assert.equal(h.calls.some(c=>c.url==='/script-ready'),false);
 await h.button('cancel-script').onclick();
 h.updateSaved({revision:'r2'});
 await h.button('approve-script').onclick();
 assert.match(h.button('ready-status').textContent,/changed/);
 await h.handlers.refresh();
 await h.button('approve-script').onclick();
 assert.equal(h.button('record-script').hidden,false);
 h.updateBrief({ready_script:null,revision:'b2'});
 await h.button('copy-recording').onclick();
 assert.equal(h.copies.length,0);
 assert.match(h.button('ready-status').textContent,/approval changed/);
});

test('a clean reader remount adopts a saved revision without turning the previous script into an unsaved draft',async()=>{
 const h=scriptEditor();await h.mount();h.api.retain();
 const b='b'.repeat(64);h.updateSaved({text:'The new revision.',version_id:b,current_version_id:b,revision:'r2',versions:[{id:b},{id:'a'.repeat(64)}],version_count:2});
 await h.mount();
 assert.equal(h.field().value,'The new revision.');
 assert.equal(h.api.hasDraft(),false);
 assert.equal(h.button('script-state').textContent,'Saved');
});

function writingMemory(options = {}) {
 const nodes = new Map(), copies = [], requests = [], documentHandlers = {};
 const example = { id: 'example', before: 'A long explanation.', after: 'A short explanation.', feedback: 'Shorter, but still not great.', context: 'Spoken line revision.' };
 let state = { revision: '1'.repeat(64), forgotten_ids: [], preferences: [{ id: 'memory', text: '<Keep it direct>', source: 'Explicit feedback.', examples: [example] }] };
 const original = structuredClone(state.preferences[0]);
 const receipts = new Map();
 let loseReply = options.loseReply;
 const node = key => {
  if (!nodes.has(key)) nodes.set(key, {
   hidden: false, value: '', textContent: '', innerHTML: '', open: false, isConnected: true, listeners: {},
   setAttribute() {}, addEventListener(name, handler) { this.listeners[name] = handler; },
   querySelector: selector => node(selector), querySelectorAll: () => [],
   showModal() { this.open = true; }, close() { this.open = false; this.listeners.close?.(); },
   focus() { this.focused = true; }, select() { this.selected = true; }
  });
  return nodes.get(key);
 };
 const context = {
  I18N: i18nStub(),
  window: {}, URL, URLSearchParams, location: { href: 'http://127.0.0.1:9999/#projects' },
  crypto: require('node:crypto'), esc: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
  document: { createElement: () => node('dialog'), body: { append() {} }, addEventListener: (name, handler) => { documentHandlers[name] = handler; } },
  navigator: { clipboard: { async writeText(text) { if (options.clipboardFailure) throw Error('Unavailable'); copies.push(text); } } },
  fetch: async (url, request) => {
   requests.push({ url, body: request?.body ? JSON.parse(request.body) : null });
   if (request?.body) {
    const body = JSON.parse(request.body);
    if (!receipts.has(body.request_id)) {
     if (body.revision !== state.revision) return { ok: false, json: async () => ({ error: 'Writing memory changed.' }) };
     state = { ...state, revision: String(Number(state.revision[0]) + 1).repeat(64),
      preferences: body.forgotten ? [] : [structuredClone(original)], forgotten_ids: body.forgotten ? ['memory'] : [] };
     receipts.set(body.request_id, true);
     if (loseReply) { loseReply = false; throw Error('Connection lost'); }
    }
   }
   return { ok: true, json: async () => structuredClone(state) };
  }
 };
 runInNewContext(readFileSync(join(__dirname, 'dist/writing-voice-ui.js'), 'utf8'), context);
 const flush = () => new Promise(resolve => setImmediate(resolve));
 return {
  node, copies, requests, context,
  open: () => context.window.WritingVoice.open(node('opener')),
  async click(selector, dataset) {
   node('dialog').listeners.click({ target: { closest: key => key === selector ? { dataset } : null } });
   await flush(); await flush();
  },
  async undo() { node('[data-undo-voice]').onclick(); await flush(); await flush(); },
  async retry() { node('[data-retry-voice]').onclick(); await flush(); await flush(); },
  changeElsewhere() { state.revision = '9'.repeat(64); },
  get state() { return state; }
 };
}

test('writing memory shows readable notes and exact feedback instead of a preference form', async () => {
 const h = writingMemory(); await h.open();
 assert.match(h.node('dialog').innerHTML, /Writing memory/);
 assert.doesNotMatch(h.node('dialog').innerHTML, /Save preferences|Add a preference|data-voice-text/);
 const content = h.node('[data-voice-list]').innerHTML;
 assert.match(content, /&lt;Keep it direct&gt;/);
 assert.match(content, /A long explanation/); assert.match(content, /Shorter, but still not great/);
 assert.match(content, /Correct in chat/); assert.equal(h.copies.length, 0);
});

test('forget saves immediately and undo restores the same memory with its evidence', async () => {
 const h = writingMemory(); await h.open();
 await h.click('[data-forget-memory]', { forgetMemory: 'memory' });
 assert.equal(h.state.preferences.length, 0); assert.equal(h.node('[data-undo-voice]').hidden, false);
 await h.open(); assert.match(h.node('[data-voice-list]').innerHTML, /It starts with your first script/);
 await h.undo(); assert.equal(h.state.preferences[0].examples[0].feedback, 'Shorter, but still not great.');
 assert.equal(h.node('[data-undo-voice]').hidden, true);
 h.node('[data-done-voice]').onclick(); assert.equal(h.node('dialog').open, false);
});

test('retrying a lost forget response reuses its request identity', async () => {
 const h = writingMemory({ loseReply: true }); await h.open();
 await h.click('[data-forget-memory]', { forgetMemory: 'memory' });
 assert.equal(h.node('[data-retry-voice]').hidden, false);
 await h.retry();
 const posts = h.requests.filter(row => row.body);
 assert.deepEqual(posts[0].body, posts[1].body);
 assert.equal(h.state.preferences.length, 0); assert.equal(h.node('[data-undo-voice]').hidden, false);
});

test('a conflicting memory action requires a fresh read and keeps the winning memory', async () => {
 const h = writingMemory(); await h.open(); h.changeElsewhere();
 await h.click('[data-forget-memory]', { forgetMemory: 'memory' });
 assert.equal(h.state.preferences.length, 1);
 assert.match(h.node('[data-voice-status]').textContent, /changed/);
 await h.open();
 await h.click('[data-forget-memory]', { forgetMemory: 'memory' });
 assert.equal(h.state.preferences.length, 0);
});

test('correct in chat pins the memory and revision and provides manual copying when needed', async () => {
 const h = writingMemory(); await h.open();
 await h.click('[data-correct-memory]', { correctMemory: 'memory' });
 assert.match(h.copies[0], /writing-memory=memory&memory-revision=111/);
 assert.match(h.copies[0], /<Keep it direct>/); assert.equal(h.requests.filter(row => row.body).length, 0);
 const manual = writingMemory({ clipboardFailure: true }); await manual.open();
 await manual.click('[data-correct-memory]', { correctMemory: 'memory' });
 assert.equal(manual.node('[data-memory-copy]').hidden, false);
 assert.equal(manual.node('[data-memory-copy]').selected, true);
});
