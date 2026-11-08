const {test}=require('node:test'),assert=require('node:assert/strict'),{readFileSync}=require('node:fs'),{join}=require('node:path'),{runInNewContext}=require('node:vm');
// Task 4: start-references.js now calls I18N.t(key, vars) for UI copy. This sandboxed
// context doesn't load the real i18n.js, so it gets a stub that looks up the same
// strings a Hebrew-first page would show in English (en.json), with the same `{name}`
// interpolation i18n.js itself implements (same approach as test_studio_ui.js's own
// i18nStub()).
function i18nStub() {
  const en = JSON.parse(readFileSync(join(__dirname, 'dist/i18n/en.json'), 'utf8'));
  return {ready: Promise.resolve(), lang: () => 'en', t(key, vars) { const value = en[key] ?? key; if (!vars) return value; return Object.keys(vars).reduce((text, name) => text.split('{' + name + '}').join(vars[name]), value); }};
}
function library(){
 const entries=[{id:'video',title:'Original video',creator:'Creator',poster:'cover.png',media_path:'source.mp4',collection:'reference',analysis_status:'analyzed',summary:'A real reference.'}],technique={id:'type',title:'Typography',examples:[{id:'first',style_id:'video',label:'First treatment',poster:'first.png',start:0,end:2},{id:'second',style_id:'video',label:'Second treatment',poster:'second.png',start:4,end:6}]};
 const calls=[],notes=[{id:'note-id',slide:null,text:'Use restrained type.'}];let stale=false,changed=false;
 const context={window:{},exact:t=>Math.floor(t/60)+':'+(t%60).toFixed(2).padStart(5,'0').replace(/0+$/,'').replace(/\.$/,''),URL,URLSearchParams,localStorage:{getItem:()=>null},selected:new Set(['type']),item:id=>id==='type'?technique:entries.find(e=>e.id===id),source:id=>entries.find(e=>e.id===id),isTech:e=>!!e.examples,isCarousel:()=>false,isRemoved:()=>false,example:()=>technique.examples[0],referenceUrl:(id,example)=>'http://localhost/#'+(example?'technique='+id+'&example='+example:'style='+id),fetch:async(url,options={})=>{
  calls.push({url,body:options.body&&JSON.parse(options.body)});
  if(url.startsWith('/reference-notes'))return {ok:true,json:async()=>({context_revision:'source-revision',notes})};
  const rows=JSON.parse(options.body).references;
  if(stale)return {ok:false,json:async()=>({error:'The selected source or notes changed.'})};
  const blocks=rows.map(r=>{const label=r.example_id==='second'?'Second treatment':'First treatment';return (r.example_id?'Typography — Creator · '+label+' (0:04–0:06)':'Original video — Creator')+'\nhttp://localhost/#'+(r.example_id?'technique=type&example='+r.example_id:'style=video')+'\nWhat to borrow: '+(changed?'Changed note.':'Use restrained type.');});
  return {ok:true,json:async()=>({text:(rows.length===1?'Use this reference:':'Use these references:')+'\n\n'+blocks.join('\n\n')})};
 },I18N:i18nStub()};
 runInNewContext(readFileSync(join(__dirname,'dist/start-references.js'),'utf8'),context);
 return {context,api:context.window.StartReferences,calls,entries,technique,notes,stale(){stale=true;},changeNote(){changed=true;}};
}
test('project inspiration captures the exact chosen example and current saved notes',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});
 assert.equal(row.example_id,'second');assert.equal(row.details.label,'Second treatment');assert.equal(row.details.poster,'second.png');assert.match(row.details.url,/example=second/);assert.match(row.message,/Second treatment/);assert.deepEqual([...row.note_ids],['note-id']);assert.equal(h.calls[1].body.references[0].example_id,'second');assert.equal(h.calls[1].body.references[0].context_revision,'source-revision');
});
test('missing technique examples are rejected without substituting the default',async()=>{
 const h=library();await assert.rejects(h.api.capture({reference_id:'type',example_id:'gone',slide:null}),/exact technique example/);assert.equal(h.calls.length,0);
});
test('combined project text keeps exact links, library notes and project-only borrowing intent',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});row.note='Use this opening with my footage.';const text=h.api.text([row]);assert.match(text,/example=second/);assert.match(text,/Use restrained type/);assert.match(text,/For this project:\nSecond treatment: Use this opening/);assert.equal(h.calls.length,2);assert.ok(h.calls.every(c=>c.url!=='/reference-note'));
});
test('stale sources and changed saved notes block the handoff instead of broadening it',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});await h.api.validate([row]);h.stale();await assert.rejects(h.api.validate([row]),/source or notes changed/);
 const h2=library(),row2=await h2.api.capture({reference_id:'video',example_id:null,slide:null});h2.changeNote();await assert.rejects(h2.api.validate([row2]),/Remove it and select it again/);
});
test('restoring a project draft keeps distinct examples and filters malformed or duplicate selections',()=>{
 const h=library(),base={reference_id:'type',example_id:'first',slide:null,context_revision:'revision',note_ids:[],message:'Exact link',details:{title:'Typography'}};
 const rows=h.api.restore([base,base,{...base,example_id:'second',note:'Keep me'},null,{reference_id:'bad'}]);assert.equal(rows.length,2);assert.equal(rows[1].example_id,'second');assert.equal(rows[1].note,'Keep me');
});
test('an empty inspiration choice requires no library request',async()=>{const h=library();await h.api.validate([]);assert.equal(h.api.text([]),'');assert.equal(h.calls.length,0);});

test('project timestamps including zero stay with the exact example in the copied request',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});row.note='Use the word emphasis';row.time=4.25;assert.match(h.api.text([row]),/Second treatment — At 0:04.25: Use the word emphasis/);assert.match(h.api.text([row]),/example=second/);const first=await h.api.capture({reference_id:'type',example_id:'first',slide:null});first.time=0;assert.match(h.api.text([first]),/At 0:00/);
});
test('cover-only moment descriptions remain free text rather than invented timestamps',async()=>{
 const h=library();h.entries[0].media_path=null;const row=await h.api.capture({reference_id:'video',example_id:null,slide:null});row.note='Borrow the card reveal';row.focus='0:02–0:05';assert.match(h.api.text([row]),/Moment or time range: 0:02–0:05: Borrow the card reveal/);assert.equal(h.api.noteValue(row).time,null);assert.equal(row.details.media,null);
});
test('restoring old and current draft notes preserves their text and validates timestamps',()=>{
 const h=library(),base={reference_id:'video',example_id:null,slide:null,context_revision:'version',note_ids:[],message:'Exact reference',details:{title:'Video'},note:'Existing note'};assert.equal(h.api.restore([base])[0].time,null);const row=h.api.restore([{...base,time:2.456,focus:'Opening'}])[0];assert.equal(row.time,2.46);assert.equal(row.focus,'Opening');assert.equal(h.api.noteValue({time:-1}).time,null);assert.equal(h.api.noteValue({time:Infinity}).time,null);
});

test('a timestamp outside its chosen example is rejected before the handoff',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});row.time=1;const calls=h.calls.length;await assert.rejects(h.api.validate([row]),/timestamp for this exact example/);assert.equal(h.calls.length,calls);
});


test('pasted video links retain borrowing intent without fetching or cataloguing anything',async()=>{
 const h=library(),row=h.api.link(' https://www.example.org/watch?v=123#t=4 ','Use the opening question.');assert.equal(row.url,'https://www.example.org/watch?v=123#t=4');assert.equal(row.details.title,'example.org');assert.match(h.api.text([row]),/example.org\/watch\?v=123#t=4/);assert.match(h.api.text([row]),/For this project:\nhttps:\/\/www.example.org\/watch\?v=123#t=4: Use the opening question/);await h.api.validate([row]);assert.equal(h.calls.length,0);
});
test('pasted links and exact library examples validate independently in a mixed request',async()=>{
 const h=library(),saved=await h.api.capture({reference_id:'type',example_id:'second',slide:null}),pasted=h.api.link('https://example.org/clip','Use its pacing.');saved.note='Use the diagrams.';const text=h.api.text([saved,pasted]);assert.match(text,/example=second/);assert.match(text,/https:\/\/example.org\/clip/);assert.match(text,/Second treatment: Use the diagrams/);assert.match(text,/https:\/\/example.org\/clip: Use its pacing/);await h.api.validate([saved,pasted]);assert.equal(h.calls.at(-1).body.references.length,1);assert.equal(h.calls.at(-1).body.references[0].example_id,'second');h.stale();await assert.rejects(h.api.validate([saved,pasted]),/source or notes changed/);
});
test('link draft restore deduplicates safely and keeps notes without trusting saved display markup',()=>{
 const h=library(),a=h.api.link('https://example.org/clip','My specific note.');const rows=h.api.restore([a,{...a,details:{title:'<script>wrong</script>'}},h.api.link('https://example.org/other'),{kind:'link',url:'javascript:alert(1)'},{kind:'link',url:null}]);assert.equal(rows.length,2);assert.equal(rows[0].details.title,'example.org');assert.equal(rows[0].note,'My specific note.');assert.equal(h.api.targetKey(rows[0]),h.api.targetKey(a));assert.notEqual(h.api.targetKey(rows[0]),h.api.targetKey(rows[1]));
});
test('invalid or credential-bearing video links are rejected before any request',()=>{
 const h=library();for(const value of ['not a link','javascript:alert(1)','file:///private/video.mp4','https://name:secret@example.org/clip'])assert.throws(()=>h.api.link(value),/link/);assert.equal(h.calls.length,0);
});

function picker(h,initial=[]){
 const nodes=new Map();
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',value:'',textContent:'',listeners:{},focus(){this.focused=true;},querySelector:selector=>node(id+' '+selector),querySelectorAll:()=>[],addEventListener(name,fn){this.listeners[name]=fn;}});return nodes.get(id);};
 let rows=initial,linkDraft='',drafts={};h.context.selected=new Set();h.context.esc=value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
 const dialog=node('dialog'),summary=node('dialog #start-reference-summary'),api=h.api.create({dialog,get:()=>rows,set:value=>{rows=value;},showPicker(){},getLinkDraft:()=>linkDraft,setLinkDraft:value=>{linkDraft=value;},getDrafts:()=>drafts,setDrafts:value=>{drafts=value;}});api.render();
 return {api,summary,node,get rows(){return rows;},get linkDraft(){return linkDraft;},get drafts(){return drafts;},click(attr,value=''){const b={dataset:{[attr.replace('data-','').replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]:value},hasAttribute:name=>name===attr,closest:()=>null};summary.listeners.click({target:{closest:()=>b}});},inputLink(value){node('dialog #start-reference-summary #start-video-link').value=value;summary.listeners.input({target:{id:'start-video-link',value,dataset:{}}});},note(index,value){summary.listeners.input({target:{value,dataset:{refSummaryNote:String(index)}}});}};
}
test('the inspiration card flow keeps link drafts, deduplicates notes and removes only its own selection',()=>{
 const h=library(),p=picker(h);p.click('data-ref-paste');p.inputLink('not a link');p.click('data-ref-add-link');assert.equal(p.rows.length,0);assert.match(p.node('dialog #start-reference-summary .start-reference-status').textContent,/Paste a full video link/);
 p.inputLink('https://example.org/clip');assert.equal(p.linkDraft,'https://example.org/clip');p.click('data-ref-add-link');assert.equal(p.rows.length,1);assert.equal(p.linkDraft,'');p.note(0,'Borrow the opening.');p.click('data-ref-paste');p.inputLink('https://example.org/clip');p.click('data-ref-add-link');assert.equal(p.rows.length,1);assert.equal(p.rows[0].note,'Borrow the opening.');assert.match(p.summary.innerHTML,/What would you like to borrow/);assert.doesNotMatch(p.summary.innerHTML,/start-source-options/);
 p.click('data-ref-remove','0');assert.equal(p.rows.length,0);assert.equal(Object.keys(p.drafts).length,0);assert.equal(h.calls.length,0);
});
test('compact library cards preserve exact examples, timestamps and safely rendered project notes',async()=>{
 const h=library(),row=await h.api.capture({reference_id:'type',example_id:'second',slide:null});row.note='Use <this> diagram.';row.time=4.25;const p=picker(h,[row,h.api.link('https://example.org/clip','Use its reveal.')]);assert.match(p.summary.innerHTML,/data-example-id="second"/);assert.match(p.summary.innerHTML,/Use &lt;this&gt; diagram/);assert.match(p.summary.innerHTML,/At 0:04.25/);assert.match(p.summary.innerHTML,/Reference details/);
 p.note(0,'New diagram direction.');assert.equal(p.rows[0].time,4.25);assert.equal(p.rows[0].example_id,'second');p.click('data-ref-remove','1');assert.equal(p.rows.length,1);assert.equal(p.rows[0].reference_id,'type');assert.equal(h.calls.length,2);
});
