// Analysis handoff regressions; no browser packages or owner data required.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {readFileSync}=require('node:fs');
const {join}=require('node:path');
const {runInNewContext}=require('node:vm');
const source=readFileSync(join(__dirname,'dist/reference-ui.js'),'utf8');
// Task 4: reference-ui.js now calls I18N.t(key, vars) for UI copy. This sandboxed
// context doesn't load the real i18n.js, so it gets a stub that looks up the same
// strings a Hebrew-first page would show in English (en.json), with the same
// `{name}` interpolation i18n.js itself implements (same approach as
// test_studio_ui.js's own i18nStub()).
function i18nStub() {
  const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  return {ready: Promise.resolve(), lang: () => 'en', t(key, vars) { const value = en[key] ?? key; if (!vars) return value; return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value); }};
}
const entry=id=>({id,title:'Reference '+id,analysis_status:'not_analyzed',collection:'reference',source_url:'https://example.com/'+id,reference_note:'Borrow the card reveal',keep:[],avoid:[],poster:'assets/link-reference.svg'});
function harness(options={}){
 const nodes=new Map();
 const node=key=>{if(!nodes.has(key)){const classes=new Set();nodes.set(key,{textContent:'',value:'',hidden:false,disabled:false,open:false,classes,listeners:{},classList:{toggle(name,on){on?classes.add(name):classes.delete(name);}},addEventListener(type,fn){this.listeners[type]=fn;},insertBefore(){},querySelectorAll(){return [];},reportValidity(){return true;},focus(){},select(){},showModal(){this.open=true;},close(){this.open=false;}});}return nodes.get(key);};
 node('#style-dialog').open=true;
 const copies=[];
 const context={window:{},$:node,active:entry('one'),entries:[],isTech:e=>!!e.examples,pausePreview(){},notify(){},referenceUrl:id=>'http://127.0.0.1:4870/#style='+id,document:{addEventListener(){}},navigator:{clipboard:{writeText:async text=>{if(options.fail)throw Error('Clipboard unavailable');if(options.wait)await options.wait;copies.push(text);}}},fetch:async()=>{throw Error('Analysis copying must not write or fetch');},I18N:i18nStub()};
 runInNewContext(source,context);
 return {context,node,copies,details:e=>context.window.ReferenceIntake.details(e),click:()=>node('#reference-analyze').listeners.click()};
}
test('pending reference has a direct next step without automatic copying',()=>{
 const h=harness();h.details(h.context.active);
 assert.equal(h.node('#reference-analyze').textContent,'Copy analysis request');assert.equal(h.node('#reference-analysis-title').textContent,'Next: analyze this reference.');assert.equal(h.copies.length,0);assert.equal(h.node('#pending-link-heading').hidden,false);assert.ok(h.node('#reference-use').classes.has('awaiting-analysis'));
 h.context.active={...entry('partial'),analysis_status:'partial'};h.details(h.context.active);assert.equal(h.node('#reference-analysis-title').textContent,'Continue analyzing this reference.');assert.equal(h.node('#pending-link-heading').hidden,true);
});
test('explicit copy identifies this exact source and original note without changing analysis',async()=>{
 const h=harness();h.details(h.context.active);await h.click();
 assert.equal(h.copies.length,1);assert.match(h.copies[0],/#style=one/);assert.match(h.copies[0],/Borrow the card reveal/);assert.equal(h.context.active.analysis_status,'not_analyzed');assert.equal(h.node('#reference-analyze').textContent,'Copied ✓');assert.equal(h.node('#analysis-dialog').open,false);
 h.details(h.context.active);assert.equal(h.node('#reference-analyze').textContent,'Copied ✓');
});
test('unavailable clipboard opens the exact request for manual copying',async()=>{
 const options={fail:true},h=harness(options);h.details(h.context.active);await h.click();assert.equal(h.copies.length,0);assert.equal(h.node('#analysis-dialog').open,true);assert.match(h.node('#analysis-text').value,/#style=one/);assert.match(h.node('#analysis-status').textContent,/copy it/);options.fail=false;await h.node('#analysis-copy').listeners.click();assert.equal(h.copies.length,1);assert.equal(h.node('#reference-analyze').textContent,'Copied ✓');
});
test('late clipboard completion does not change a different reference’s controls',async()=>{
 let finish;const wait=new Promise(resolve=>finish=resolve),h=harness({wait});h.details(h.context.active);const copying=h.click();h.context.active=entry('two');h.details(h.context.active);finish();await copying;
 assert.match(h.copies[0],/#style=one/);assert.equal(h.node('#reference-analyze').textContent,'Copy analysis request');assert.doesNotMatch(h.node('.analysis-next-helper').textContent,/^Copied/);
});
async function pendingCover(){
 const h=harness(),c=h.context,reply=data=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>data});let complete,covered=false;
 c.entries=[c.active];c.location={hash:'#style=one'};c.referenceHash=id=>'#style='+id;
 c.window.Studio={currentSection:'library'};c.window.refreshReferenceCatalog=async()=>{if(covered)c.entries=[{...c.entries[0],poster:'assets/reference-previews/cover.jpg'}];};
 h.rendered=[];h.opened=[];
 c.render=()=>{h.node('#gallery').innerHTML=c.entries[0].poster;h.rendered.push(c.entries[0].poster);};
 c.showStyle=id=>{c.active=c.entries.find(e=>e.id===id);h.opened.push(id);};
 c.applyRoute=()=>{c.active=c.entries[0];c.render();};
 c.fetch=async url=>{if(url==='/references')return reply({id:'one',duplicate:false});assert.equal(url,'/reference-preview');return new Promise(resolve=>{complete=()=>{covered=true;resolve(reply({id:'one',changed:true,available:true}));};});};
 await h.node('#reference-form').listeners.submit({preventDefault(){}});
 assert.equal(h.node('#gallery').innerHTML,'assets/link-reference.svg');assert.equal(typeof complete,'function');
 h.complete=async()=>{complete();await new Promise(resolve=>setImmediate(resolve));};return h;
}
test('a cover arriving in the open saved reference updates its library card before closing',async()=>{
 const h=await pendingCover();await h.complete();
 assert.equal(h.node('#gallery').innerHTML,'assets/reference-previews/cover.jpg');assert.equal(h.node('#style-dialog').open,true);assert.deepEqual(h.opened,['one']);assert.equal(h.context.active.poster,'assets/reference-previews/cover.jpg');assert.equal(h.context.active.analysis_status,'not_analyzed');
});
test('a late cover refreshes browsing without reopening a closed or different reference',async()=>{
 for(const state of ['closed','different','projects']){
  const h=await pendingCover();h.context.active=state==='different'?entry('two'):null;h.node('#style-dialog').open=state==='different';if(state==='projects')h.context.window.Studio.currentSection='projects';
  await h.complete();assert.deepEqual(h.opened,[],state);assert.equal(h.rendered.length,state==='projects'?1:2,state);if(state!=='projects')assert.equal(h.node('#gallery').innerHTML,'assets/reference-previews/cover.jpg');if(state==='different')assert.equal(h.context.active.id,'two');
 }
});
test('Task 13: a dropped video with no link is uploaded as the reference, without a link save or cover fetch',async()=>{
 const h=harness(),c=h.context,uploads=[],fetched=[],notes=[];
 c.entries=[];c.location={hash:''};c.referenceHash=id=>'#style='+id;c.applyRoute=()=>{};c.notify=text=>notes.push(text);
 c.window.refreshReferenceCatalog=async()=>{};c.fetch=async url=>{fetched.push(url);throw Error('no fetch expected');};
 const file={name:'reel.mp4',size:3};
 c.window.Inspiration={pendingFile:()=>file,resetDrop(){},upload:async(f,params,progress)=>{uploads.push([f,{...params}]);progress(40);return {id:'file-1',duplicate:false,saved:true};}};
 h.node('#reference-title').value='פתיחה';h.node('#reference-note').value='הכתוביות';
 await h.node('#reference-form').listeners.submit({preventDefault(){}});
 assert.deepEqual(fetched,[]);assert.equal(uploads.length,1);assert.equal(uploads[0][0],file);
 assert.equal(JSON.stringify(uploads[0][1]),JSON.stringify({title:'פתיחה',creator:'',note:'הכתוביות'}));
 assert.equal(c.location.hash,'#style=file-1');assert.deepEqual(notes,['Saved. Next: learn the style.']);
});
test('Task 13: a link plus a dropped video saves the link, then adds the file to it',async()=>{
 const h=harness(),c=h.context,uploads=[],fetched=[];
 c.entries=[];c.location={hash:''};c.referenceHash=id=>'#style='+id;c.applyRoute=()=>{};c.window.refreshReferenceCatalog=async()=>{};
 c.fetch=async url=>{fetched.push(url);if(url==='/references')return {ok:true,headers:{get:()=>'application/json'},json:async()=>({id:'link-1',duplicate:false})};return new Promise(()=>{});};
 c.window.Inspiration={pendingFile:()=>({name:'reel.mp4'}),resetDrop(){},upload:async(f,params)=>{uploads.push({...params});return {id:'link-1'};}};
 h.node('#reference-url').value='https://example.com/reel';
 await h.node('#reference-form').listeners.submit({preventDefault(){}});
 assert.deepEqual(fetched,['/references','/reference-preview']);assert.equal(JSON.stringify(uploads),JSON.stringify([{reference:'link-1'}]));
});

test('fix round 1: with the style card panel, Matt’s analysis box steps aside and stays in the options menu',()=>{
 const h=harness(),mounted=[];h.context.window.Inspiration={mount:e=>mounted.push(e.id),unmount(){}};h.details(h.context.active);
 assert.deepEqual(mounted,['one']);assert.equal(h.node('#reference-analysis-next').hidden,true);
 assert.equal(h.node('#detail-analyze').hidden,false);assert.equal(h.node('#detail-analyze').textContent,'Copy analysis request');
 h.context.active={...entry('mine'),collection:'mine'};h.details(h.context.active);assert.equal(h.node('#reference-analysis-next').hidden,false);
});
test('fix round 1: if the file fails after the link saved, say the link is kept',async()=>{
 const h=harness(),c=h.context;let refreshed=0;
 c.entries=[];c.location={hash:''};c.referenceHash=id=>'#style='+id;c.applyRoute=()=>{};c.window.refreshReferenceCatalog=async()=>{refreshed++;};
 c.fetch=async url=>({ok:true,headers:{get:()=>'application/json'},json:async()=>({id:'link-1',duplicate:false})});
 c.window.Inspiration={pendingFile:()=>({name:'reel.mp4'}),resetDrop(){},upload:async()=>{throw Error('The video is too large.');}};
 h.node('#reference-url').value='https://example.com/reel';h.node('#reference-dialog').open=true;
 await h.node('#reference-form').listeners.submit({preventDefault(){}});
 assert.equal(h.node('#reference-error').textContent,'The link was saved, but the file wasn’t attached. Try again.');
 assert.equal(h.node('#reference-dialog').open,true);assert.equal(refreshed,1);assert.equal(h.node('#reference-save').disabled,false);
});
test('fix round 1: an uploaded file with no link does not offer "use the saved link"',()=>{
 const h=harness(),e={...entry('file'),source_url:undefined,source_file:'reel.mp4',media_path:'references/file/source.mp4'};
 h.context.window.Inspiration={mount(){},unmount(){}};h.details(e);
 assert.equal(h.node('#pending-link-heading').hidden,true);assert.equal(h.node('#detail-edit-reference').hidden,false);
});
