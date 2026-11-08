const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const stamp=t=>Number.isFinite(t)?Math.floor(t/60)+':'+Math.floor(t%60).toString().padStart(2,'0'):'—';
const exact=t=>Math.floor(t/60)+':'+(t%60).toFixed(2).padStart(5,'0').replace(/0+$/,'').replace(/\.$/,'');
// Task 13: a moment saved without a time (seen in Matt's demo data) shows a dash and is not a seek button -- never "NaN:NaN".
function momentsHtml(moments){return moments.map(m=>Number.isFinite(m.time)?'<button class="moment" data-time="'+m.time+'"><span>'+stamp(m.time)+'</span>'+esc(m.label)+'</button>':'<p class="moment moment-untimed"><span aria-hidden="true">—</span>'+esc(m.label)+'</p>').join('');}
let removedIds=new Set();
let entries=[],techniques=[],view='videos',collection='mine',active=null,selected=new Set(),choices={},toastTimer;
let referenceNotes={},briefIds=[];
let quickCopyTimer;
const copyIcon='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M15 8V4H4v11h4"/></svg>';
function referenceHash(id,exampleId=null,slideIndex=null){const e=item(id),params=new URLSearchParams();params.set(isTech(e)?'technique':'style',id);if(isTech(e))params.set('example',exampleId||example(e,false).id);if(isCarousel(e)&&slideIndex!==null)params.set('slide',String(slideIndex+1));return '#'+params.toString();}
function referenceUrl(id,exampleId=null,slideIndex=null){const url=new URL('./',location.href);url.hash=referenceHash(id,exampleId,slideIndex);return url.href;}
function cardActions(e,x=null){return '<span class="card-actions"><button class="copy-card" data-copy-reference="'+esc(e.id)+'"'+(x?' data-copy-example="'+esc(x.id)+'"':'')+' aria-label="'+I18N.t('library.card.copyForChatAria',{title:esc(e.title)})+'" title="'+I18N.t('dialog.style.copyForChat')+'">'+copyIcon+'</button><button class="select-card" data-id="'+esc(e.id)+'" aria-label="'+I18N.t('library.card.selectAria',{title:esc(e.title)})+'" aria-pressed="false">+</button></span>';}
try{referenceNotes=JSON.parse(localStorage.getItem('ai-video-studio-notes-v1')||'{}');}catch{}
try{selected=new Set(JSON.parse(localStorage.getItem('ai-video-studio-selection-v1')||'[]'));choices=JSON.parse(localStorage.getItem('ai-video-studio-examples-v1')||'{}');}catch{}
const source=id=>entries.find(e=>e.id===id);
const item=id=>source(id)||techniques.find(t=>t.id===id);
const isTech=e=>!!e.examples;
const isCarousel=e=>e.asset_type==='carousel';
const isRemoved=e=>!!e&&(removedIds.has(e.id)||!!e.archived_from&&removedIds.has(e.archived_from));
const browseEntries=()=>entries.filter(e=>!e.archived_from&&!isRemoved(e));
const browseExamples=t=>t.examples.filter(x=>!isRemoved(source(x.style_id)));
const browseTechniques=()=>techniques.filter(t=>browseExamples(t).length);
const viewEntries=()=>browseEntries().filter(e=>isCarousel(e)===(view==='carousels'));
const viewHash=()=>view==='techniques'?'#techniques':view==='carousels'?'#carousels':'#videos';
const creatorKey=e=>e.creator_id||e.creator;
const matchesSource=e=>!isRemoved(e)&&(collection==='all'||e.collection===collection)&&($('#creator').value==='all'||creatorKey(e)===$('#creator').value);
const used=t=>t.examples.some(x=>source(x.style_id).collection==='mine');
function example(t,filtered=true){const chosen=t.examples.find(x=>x.id===choices[t.id])||t.examples.find(x=>x.id===t.default_example);return !filtered||matchesSource(source(chosen.style_id))?chosen:t.examples.find(x=>matchesSource(source(x.style_id)))||chosen;}
function notify(text){$('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,2200);}
function saveSelection(){try{localStorage.setItem('ai-video-studio-selection-v1',JSON.stringify([...selected]));localStorage.setItem('ai-video-studio-examples-v1',JSON.stringify(choices));}catch{notify(I18N.t('library.selection.storageUnavailable'));}updateSelection();}
function updateSelection(){
 const n=selected.size;
 const visible=!!n&&(!window.Studio||window.Studio.currentSection==='library');
 $('#selection-bar').hidden=!visible;document.body.classList.toggle('has-selection',visible);
 $('#selected-count').textContent=n===1?I18N.t('selection.bar.count'):I18N.t('selection.bar.countMany',{n});
 $('#selection-description').textContent=I18N.t('selection.bar.addNotesHint');
 document.querySelectorAll('.select-card').forEach(b=>{const chosen=selected.has(b.dataset.id);b.setAttribute('aria-pressed',String(chosen));const label=I18N.t(chosen?'library.card.removeSelectionAria':'library.card.addSelectionAria',{title:esc(item(b.dataset.id).title)});b.setAttribute('aria-label',label);b.title=label;b.textContent=chosen?'✓':'+';b.closest('.style-card').classList.toggle('is-selected',chosen);});
 $('#selected-previews').innerHTML=[...selected].slice(0,4).map(id=>{const e=item(id),poster=isTech(e)?example(e,false).poster:e.poster;return '<img src="'+esc(poster)+'" alt="'+esc(e.title)+'">';}).join('');
 if(active)$('#detail-add').textContent=selected.has(active.id)?I18N.t('dialog.style.inSelection'):I18N.t('dialog.style.addToSelection');
}
function toggleSelection(id){const e=item(id);if(!e)return;if(selected.has(id))selected.delete(id);else{selected.add(id);if(isTech(e))choices[id]=active?.id===id?example(e,false).id:example(e).id;}saveSelection();notify(selected.has(id)?I18N.t('library.selection.added'):I18N.t('library.selection.removed'));}
function populateCreators(){
 const current=$('#creator').value,groups=new Map();
 const rows=view!=='techniques'?viewEntries().map(e=>({id:e.id,source:e})):browseTechniques().flatMap(t=>browseExamples(t).map(x=>({id:t.id,source:source(x.style_id)})));
 for(const row of rows){const e=row.source;if(collection!=='all'&&e.collection!==collection)continue;const key=creatorKey(e);if(!groups.has(key))groups.set(key,{name:e.creator,ids:new Set()});groups.get(key).ids.add(row.id);}
 $('#creator').innerHTML='<option value="all">'+I18N.t('library.filter.allCreators')+'</option>'+[...groups].sort((a,b)=>a[1].name.localeCompare(b[1].name)).map(([key,c])=>'<option value="'+esc(key)+'">'+esc(c.name)+' ('+c.ids.size+')</option>').join('');
 $('#creator').value=groups.has(current)?current:'all';
}
function updateControls(){
 document.querySelectorAll('[data-view]').forEach(b=>{const on=b.dataset.view===view;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
 const names={mine:view==='techniques'?I18N.t('library.collection.usedInMyWork'):I18N.t('library.collection.mine'),reference:I18N.t('library.collection.reference'),all:I18N.t('library.collection.all')};
 document.querySelectorAll('[data-collection]').forEach(b=>{const c=b.dataset.collection,on=c===collection;let n=view!=='techniques'?viewEntries().filter(e=>c==='all'||e.collection===c).length:browseTechniques().filter(t=>browseExamples(t).some(x=>c==='all'||source(x.style_id).collection===c)).length;b.innerHTML=names[c]+(c==='all'?'':' <span>'+n+'</span>');b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
 $('#view-description').textContent=view==='videos'?I18N.t('library.viewDescription.videos'):view==='carousels'?I18N.t('library.viewDescription.carousels'):I18N.t('library.viewDescription.techniques');
 $('#search').placeholder=view==='techniques'?I18N.t('library.search.placeholder.techniques'):view==='carousels'?I18N.t('library.search.placeholder.carousels'):I18N.t('library.search.placeholder');
 $('#filter-name').textContent=view==='techniques'?I18N.t('library.filter.category'):I18N.t('library.filter.technique');
 const options=view!=='techniques'?[...new Set(viewEntries().flatMap(e=>e.tags))]:[...new Set(browseTechniques().map(t=>t.category))];
 $('#technique').innerHTML='<option value="all">'+(view==='techniques'?I18N.t('library.filter.allCategories'):I18N.t('library.filter.allTechniques'))+'</option>'+options.sort().map(t=>'<option>'+esc(t)+'</option>').join('');
 $('#gallery').setAttribute('aria-label',view==='videos'?I18N.t('library.galleryAria'):view==='carousels'?I18N.t('library.galleryAria.carousels'):I18N.t('library.galleryAria.techniques'));
 populateCreators();
 $('#creator').parentElement.hidden=$('#creator').options.length<3;
 $('#analysis-filter').parentElement.hidden=view==='techniques';
}
function videoCard(e){
 const carousel=isCarousel(e),preview=carousel?I18N.t('library.card.viewCarousel',{count:e.slides.length}):e.asset_type==='project'?I18N.t('library.card.viewProject'):e.media_path?I18N.t('library.card.viewStyle')+(e.duration?' · '+stamp(e.duration):''):I18N.t('library.card.viewReference');
 return '<article class="style-card" data-id="'+esc(e.id)+'"><div class="card-visual" style="--card-bg:'+esc(e.palette[0])+'"><button class="poster-button" data-open="'+esc(e.id)+'" aria-label="'+I18N.t('library.card.viewAria',{title:esc(e.title)})+'">'+(e.poster==='assets/link-reference.svg'?referencePoster(e,true):'<img src="'+esc(e.poster)+'" width="540" height="960" alt="'+esc(e.title)+' — '+(carousel?I18N.t('library.alt.carouselCover'):e.asset_type==='project'?I18N.t('library.alt.projectArtwork'):e.media_path?I18N.t('library.alt.videoFrame',{version:e.version}):I18N.t('library.alt.noLocalVideo'))+'" loading="lazy">')+'<span class="preview-pill"><span class="play-symbol">'+(carousel?'▤':e.media_path?'▶':'↗')+'</span>'+preview+'</span></button><div class="card-badges"><span class="version">'+(e.collection==='mine'?esc(e.version)+(e.delivery_status==='final'?' · '+I18N.t('library.badge.final'):e.review_status==='review_pending'?' · '+I18N.t('library.badge.review'):''):(e.analysis_status==='not_analyzed'?I18N.t('dialog.style.awaitingAnalysis'):e.analysis_status==='partial'?I18N.t('library.badge.partlyAnalyzed'):I18N.t('library.badge.reference')))+'</span>'+cardActions(e)+'</div></div><div class="card-info"><div class="card-heading"><h2>'+esc(e.title)+'</h2><button data-open="'+esc(e.id)+'" aria-label="'+I18N.t('library.card.viewDetailsAria',{title:esc(e.title)})+'">↗</button></div><p class="card-subtitle">'+esc(e.subtitle)+'</p><div class="tags">'+e.tags.slice(0,3).map(t=>'<span class="tag">'+esc(t)+'</span>').join('')+'</div><div class="card-palette">'+e.palette.map(c=>'<span class="swatch" style="--swatch:'+esc(c)+'" title="'+(e.asset_type==='link'&&!e.media_path?I18N.t('library.card.cardColorPrefix'):I18N.t('library.card.colorPalettePrefix'))+esc(c)+'" aria-label="'+(e.asset_type==='link'&&!e.media_path?I18N.t('library.card.cardColorPrefix'):I18N.t('library.card.colorPalettePrefix'))+esc(c)+'"></span>').join('')+'<span class="card-source">'+esc(e.creator)+'</span></div></div></article>';
}
function techniqueCard(t){
 const x=example(t),e=source(x.style_id);
 return '<article class="style-card technique-card" data-id="'+esc(t.id)+'"><div class="card-visual" style="--card-bg:'+esc(e.palette[0])+'"><button class="poster-button" data-open="'+esc(t.id)+'" aria-label="'+I18N.t('library.card.viewAria',{title:esc(t.title)})+'"><img src="'+esc(x.poster)+'" width="540" height="960" alt="'+esc(t.title+' — '+x.label+' '+I18N.t('library.alt.actualSourceFrame'))+'" loading="lazy"><span class="preview-pill"><span class="play-symbol">▶</span>'+I18N.t('library.card.viewExample',{seconds:(x.end-x.start).toFixed(1)})+'</span></button><div class="card-badges"><span class="version '+(used(t)?'used':'')+'">'+(used(t)?I18N.t('library.badge.usedInMyWork'):I18N.t('library.badge.technique'))+'</span>'+cardActions(t,x)+'</div></div><div class="card-info"><div class="card-heading"><h2>'+esc(t.title)+'</h2><button data-open="'+esc(t.id)+'" aria-label="'+I18N.t('library.card.viewDetailsAria',{title:esc(t.title)})+'">↗</button></div><p class="card-subtitle">'+esc(t.summary)+'</p><div class="tags"><span class="tag">'+esc(t.category)+'</span></div><div class="card-palette"><span class="example-count">'+(t.examples.length===1?I18N.t('library.card.exampleCountOne'):I18N.t('library.card.exampleCountMany',{n:t.examples.length}))+'</span><span class="card-source">'+esc(e.creator)+'</span></div></div></article>';
}
function render(){
 const query=$('#search').value.toLowerCase().trim().split(/\s+/).filter(Boolean),filter=$('#technique').value;
 let visible;
 if(view!=='techniques')visible=viewEntries().filter(e=>matchesSource(e)&&(filter==='all'||e.tags.includes(filter))&&query.every(q=>[e.title,e.subtitle,e.creator,e.creator_handle||'',e.source_url||'',e.reference_note||'',...(e.creator_aliases||[]),e.summary,...e.tags,...Object.values(e.traits)].join(' ').toLowerCase().includes(q)));
 else visible=browseTechniques().filter(t=>t.examples.some(x=>matchesSource(source(x.style_id)))&&(filter==='all'||t.category===filter)&&query.every(q=>[t.title,t.summary,t.direction,t.category,...t.aliases,...browseExamples(t).flatMap(x=>{const e=source(x.style_id);return[x.label,e.title,e.creator,e.creator_handle,...(e.creator_aliases||[])];})].join(' ').toLowerCase().includes(q)));
 const mode=$('#library-sort').value,status=$('#analysis-filter').value;
 if(view!=='techniques'&&status!=='all')visible=visible.filter(e=>status==='pending'?e.analysis_status==='not_analyzed':!!e.media_path||isCarousel(e));
 const date=e=>{const value=Date.parse(e.created_at||e.added_at||e.added_on||'');return Number.isFinite(value)?value:null;};
 visible.sort((a,b)=>{if(mode==='name')return a.title.localeCompare(b.title);const x=date(a),y=date(b);if(x===null&&y===null)return 0;if(x===null)return 1;if(y===null)return -1;return mode==='oldest'?x-y:y-x;});
 renderActiveFilters();
 const resultsNoun=view==='videos'?'video':view==='carousels'?'carousel':'technique',resultsScope=collection==='mine'?'Mine':collection==='reference'?'Reference':'',resultsKey='library.results.'+resultsNoun+resultsScope+(visible.length===1?'One':'Many');
 $('#result-count').textContent=I18N.t(resultsKey,{n:visible.length});
 $('#empty').hidden=!!visible.length;const isNew=!entries.length&&!techniques.length;$('#empty em').textContent=isNew?I18N.t('library.empty.newTitle'):I18N.t('library.empty.title');$('#empty p').textContent=isNew?I18N.t('library.empty.newBody'):I18N.t('library.empty.body');$('#reset').hidden=isNew;$('#gallery').innerHTML=visible.map(view==='techniques'?techniqueCard:videoCard).join('');updateSelection();
}
function setView(next){if(!['videos','carousels','techniques'].includes(next))return;view=next;collection='all';$('#analysis-filter').value='all';$('#search').value='';$('#creator').value='all';updateControls();render();history.replaceState(null,'',viewHash());}
function pausePreview(){const v=$('#detail-media video');if(v)v.pause();}
function closeStyle(updateUrl=true){window.ReferenceNotes?.retain();pausePreview();$('#reference-more').open=false;$('#style-dialog').close();active=null;if(updateUrl)history.replaceState(null,'',viewHash());}
function bindMedia(e,x){
 const video=$('#detail-media video');if(!video)return;video.muted=true;
 video.addEventListener('error',()=>{const p=document.createElement('p');p.className='media-error';p.textContent=I18N.t('library.media.previewError');$('#detail-media').append(p);});
 if(!x)return;
 let firstPlay=true;
 const seekPoster=()=>{video.currentTime=x.poster_at;video.pause();};
 if(video.readyState>=1)seekPoster();else video.addEventListener('loadedmetadata',seekPoster,{once:true});
 video.addEventListener('timeupdate',()=>{if(video.currentTime>=x.end&&!video.paused){video.pause();video.currentTime=x.end;}});
 video.addEventListener('seeking',()=>{if(video.currentTime<x.start-.02)video.currentTime=x.start;else if(video.currentTime>x.end+.02)video.currentTime=x.end;});
 video.addEventListener('play',()=>{if(firstPlay||video.currentTime>=x.end-.05)video.currentTime=x.start;firstPlay=false;});
 $('#replay-example').addEventListener('click',()=>{video.currentTime=x.start;video.play().catch(()=>notify(I18N.t('library.media.useVideoButton')));});
}
function sharedDetails(e){
 $('#detail-keep').innerHTML=e.keep.map(t=>'<li>'+esc(t)+'</li>').join('');$('#detail-avoid').innerHTML=e.avoid.map(t=>'<li>'+esc(t)+'</li>').join('');
}
function quickReference(original=false){
 if(!active)return null;
 const t=isTech(active)?active:null,x=t?example(t,false):null,e=x?source(x.style_id):active;
 if(original)return e.source_url?{kind:'original',label:I18N.t('dialog.style.copyOriginalLink'),text:e.source_url}:null;
 const slide=isCarousel(e)?Number($('#detail-media').dataset.slideIndex)||0:null;
 return {kind:'reference',label:I18N.t('dialog.style.copyForChat'),text:referenceUrl(active.id,x?.id,slide),hint:I18N.t('library.card.copyHint')};
}
async function copyCardReference(id,exampleId,button){
 if(window.ReferenceNotes)return window.ReferenceNotes.copyCard(id,exampleId,button);
 const text=referenceUrl(id,exampleId);
 try{await navigator.clipboard.writeText(text);button.textContent='✓';notify(I18N.t('library.card.linkCopied'));setTimeout(()=>{if(button.isConnected)button.innerHTML=copyIcon;},2200);}
 catch{$('#link-text').value=text;$('#link-dialog').showModal();$('#link-text').focus();$('#link-text').select();}
}
function updateQuickCopy(){
 clearTimeout(quickCopyTimer);const ref=quickReference();if(!ref)return;
 $('#detail-quick-copy').textContent=ref.label;$('#detail-quick-copy').title=ref.hint;$('#detail-quick-hint').textContent=ref.hint;
 $('#detail-quick-status').textContent='';$('#detail-quick-fallback').hidden=true;$('#detail-quick-text').value='';
}
async function copyQuickReference(original=false){
 if(!original&&window.ReferenceNotes)return window.ReferenceNotes.copyCurrent();
 const ref=quickReference(original);if(!ref)return;const token=active.id,button=original?$('[data-copy-original]'):$('#detail-quick-copy');clearTimeout(quickCopyTimer);
 try{
  await navigator.clipboard.writeText(ref.text);
  if(active?.id!==token||quickReference(original)?.text!==ref.text)return;
  button.textContent=I18N.t('dialog.style.copiedCheck');$('#detail-quick-status').textContent=original?I18N.t('dialog.style.originalLinkCopied'):I18N.t('library.card.linkCopied');
  quickCopyTimer=setTimeout(()=>{if(button.isConnected&&active?.id===token&&quickReference(original)?.text===ref.text)button.textContent=ref.label;},2200);
 }catch{
  if(active?.id!==token||quickReference(original)?.text!==ref.text)return;
  $('#detail-quick-fallback').hidden=false;$('#detail-quick-text').value=ref.text;$('#detail-quick-status').textContent=I18N.t('dialog.style.copyManually');$('#detail-quick-text').focus();$('#detail-quick-text').select();
 }
}
function showCarouselSlide(e,index){
 const i=Math.max(0,Math.min(e.slides.length-1,index)),s=e.slides[i];pausePreview();
 const url='/slides/'+encodeURIComponent(e.id)+'/'+i;
 const media=s.media_type==='video'?'<video controls muted loop playsinline preload="metadata" poster="'+esc(s.poster)+'" src="'+url+'" aria-label="'+esc(e.title+' slide '+(i+1))+'"></video>':'<img src="'+url+'" alt="'+esc(s.title||e.title+' slide '+(i+1))+'">';
 $('#detail-media').dataset.slideIndex=i;
 $('#detail-media').innerHTML='<div class="carousel-stage">'+media+'</div><div class="carousel-controls"><button data-carousel-step="-1" aria-label="'+I18N.t('dialog.style.prevCarouselSlide')+'" '+(i===0?'disabled':'')+'>←</button><span>'+(i+1)+' / '+e.slides.length+' · '+(s.media_type==='video'?I18N.t('library.carousel.video')+' · '+s.duration+'s':I18N.t('library.carousel.image'))+'</span><button data-carousel-step="1" aria-label="'+I18N.t('dialog.style.nextCarouselSlide')+'" '+(i===e.slides.length-1?'disabled':'')+'>→</button></div><div class="carousel-thumbs">'+e.slides.map((s,n)=>'<button data-carousel-slide="'+n+'" aria-label="'+I18N.t('dialog.style.carouselSlideAria',{n:n+1,title:esc(s.title)})+'" aria-pressed="'+(n===i)+'"><img src="'+esc(s.poster)+'" alt=""><span>'+(n+1)+'</span></button>').join('')+'</div>';
 bindMedia(e);updateQuickCopy();window.ReferenceNotes?.mountCurrent();history.replaceState(null,'',referenceHash(e.id,null,i));
}
function referencePoster(e,compact=false){
 if(e.poster!=='assets/link-reference.svg')return '<img src="'+esc(e.poster)+'" alt="'+esc(e.title)+' — '+I18N.t('library.alt.savedCoverImage')+'">';
 const pending=e.analysis_status==='not_analyzed',partial=e.analysis_status==='partial';
 const title=pending?I18N.t('library.poster.readyForAnalysis'):partial?I18N.t('library.poster.previewNotSaved'):I18N.t('library.poster.videoUnavailable');
 const body=pending?(compact?I18N.t('library.poster.analyzeCompact'):I18N.t('library.poster.analyzeFull')):partial?I18N.t('library.poster.partialSaved'):I18N.t('library.poster.savedWatch');
 const tag=compact?'span':'div',heading=compact?'span':'h3',copy=compact?'span':'p';
 return '<'+tag+' class="link-preview-placeholder'+(compact?' card-placeholder':'')+'"><svg viewBox="0 0 24 24" width="54" height="54" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true"><rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 9 6-3v12l-6-3"/></svg><'+heading+' class="placeholder-title">'+title+'</'+heading+'><'+copy+' class="placeholder-description">'+body+'</'+copy+'></'+tag+'>';
}
function showStyle(id){
 const e=source(id);if(!e)return;pausePreview();active=e;$('#style-dialog .reference-deep-details').open=false;
 $('#detail-media').classList.remove('technique-preview');$('#detail-media').classList.toggle('carousel-preview',isCarousel(e));$('#technique-examples').hidden=true;
 $('#detail-title').textContent=e.title;$('#detail-category').textContent=e.collection==='mine'?(isCarousel(e)?I18N.t('library.detail.myCarousel'):e.asset_type==='project'?I18N.t('library.detail.myProject'):I18N.t('library.detail.myVideo'))+e.version+(e.delivery_status==='final'?' · '+I18N.t('library.badge.final'):''):I18N.t('library.detail.otherCreator');$('#detail-subtitle').textContent=e.collection==='reference'?e.creator+' · '+e.subtitle:e.subtitle;$('#detail-summary').textContent=e.summary;
 if(isCarousel(e))showCarouselSlide(e,0);
 else{$('#detail-media').innerHTML=e.media_path?'<video controls muted playsinline preload="metadata"'+(e.poster==='assets/link-reference.svg'?'':' poster="'+esc(e.poster)+'"')+' src="/media/'+encodeURIComponent(e.id)+'" aria-label="'+I18N.t('library.detail.videoPreviewAria',{title:esc(e.title)})+'"></video>':'<div class="source-preview">'+referencePoster(e)+(e.project_id?'<a href="#project='+encodeURIComponent(e.project_id)+'">'+I18N.t('library.detail.openApprovedAssets')+'</a>':e.source_url?'<a href="'+esc(e.source_url)+'" target="_blank" rel="noopener noreferrer">'+I18N.t('library.detail.openOriginalVideo')+'</a>':'<p>'+I18N.t('library.detail.readProjectNotes')+'</p>')+(e.asset_type==='link'&&!e.media_path?(e.poster!=='assets/link-reference.svg'?'<p class="cover-only">'+I18N.t('library.detail.coverOnly')+'</p>':''):'')+'</div>';bindMedia(e);}
 $('#moments-section').hidden=!e.moments.length;$('#detail-moments').innerHTML=momentsHtml(e.moments);
 $('#detail-traits').innerHTML=Object.entries(e.traits).map(([key,value])=>'<div class="trait"><dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd></div>').join('');sharedDetails(e);$('#detail-evidence').textContent=e.evidence;
 $('#detail-links').innerHTML=(e.project_id?'<a href="#project='+encodeURIComponent(e.project_id)+'">'+I18N.t('library.detail.openProject')+'</a>':'')+(e.archive_path?'<a href="/download/'+encodeURIComponent(e.id)+'" download="'+esc(e.archive_path.split('/').pop())+'">'+I18N.t('library.detail.downloadAll',{count:e.slides.length})+'</a>':'')+(e.related_style_id?'<button data-source-video="'+esc(e.related_style_id)+'">'+I18N.t('library.detail.sourceVideoLink')+'</button>':'')+(e.article_url?'<a href="'+esc(e.article_url)+'" target="_blank" rel="noopener noreferrer">'+I18N.t('library.detail.companionArticle')+'</a>':'')+(e.source_url?'<a href="'+esc(e.source_url)+'" target="_blank" rel="noopener noreferrer">'+I18N.t('library.detail.watchOriginal')+'</a><button data-copy-original>'+I18N.t('dialog.style.copyOriginalLink')+'</button>':'')+e.notes.slice(0,2).map((n,i)=>'<a href="/notes/'+encodeURIComponent(e.id)+'/'+i+'" target="_blank" rel="noopener">'+(i===0?I18N.t('library.detail.projectNotes'):I18N.t('library.detail.designReviewNotes'))+' ↗</a>').join('');
 $('#detail-context').textContent=[I18N.t('library.detail.styleId')+e.id,isCarousel(e)?I18N.t('library.detail.carouselInfo',{count:e.slides.length,ratio:e.aspect_ratio}):e.media_path?I18N.t('library.detail.exampleLabel')+e.media_path:I18N.t('library.detail.originalLinkedAbove'),e.composition?I18N.t('library.detail.editable')+e.composition:'',...e.notes].filter(Boolean).join('\n');
 const existing=$('.detail-actions .detail-download');if(existing)existing.remove();if(e.archive_path){const a=document.createElement('a');a.className='secondary detail-download';a.href='/download/'+encodeURIComponent(e.id);a.setAttribute('download',e.archive_path.split('/').pop());a.textContent=I18N.t('library.detail.downloadCarousel');$('.detail-actions').append(a);}
 window.LibraryVisibility?.details(e);window.ReferenceIntake?.details(e);updateSelection();updateQuickCopy();window.ReferenceNotes?.mountCurrent();if(!$('#style-dialog').open)$('#style-dialog').showModal();history.replaceState(null,'',referenceHash(id,null,isCarousel(e)?0:null));
}
function showTechnique(id,exampleId){
 $('.detail-actions .detail-download')?.remove();window.LibraryVisibility?.hideDetails();window.ReferenceIntake?.hideDetails();
 const t=techniques.find(t=>t.id===id);if(!t)return;pausePreview();active=t;$('#style-dialog .reference-deep-details').open=false;
 let x=exampleId?t.examples.find(x=>x.id===exampleId):example(t);if(!x)x=example(t);window.LibraryVisibility?.techniqueNotice(source(x.style_id));choices[t.id]=x.id;
 const e=source(x.style_id);saveSelection();
 $('#detail-media').classList.remove('carousel-preview');$('#detail-media').classList.add('technique-preview');$('#technique-examples').hidden=false;$('#moments-section').hidden=true;
 $('#detail-title').textContent=t.title;$('#detail-category').textContent=used(t)?I18N.t('library.detail.techUsedInMyWork'):I18N.t('library.detail.techReference');$('#detail-subtitle').textContent=t.category+' · '+(t.examples.length===1?I18N.t('library.card.exampleCountOne'):I18N.t('library.card.exampleCountMany',{n:t.examples.length}));$('#detail-summary').textContent=t.summary;
 $('#detail-media').innerHTML='<video controls muted playsinline preload="metadata" poster="'+esc(x.poster)+'" src="/media/'+encodeURIComponent(e.id)+'" aria-label="'+I18N.t('library.detail.examplePreviewAria',{title:esc(t.title)})+'"></video><div class="clip-controls"><span>'+esc(e.creator)+' · '+exact(x.start)+'–'+exact(x.end)+'<small>'+I18N.t('library.detail.selectedExcerpt',{seconds:(x.end-x.start).toFixed(1)})+'</small></span><button id="replay-example">'+I18N.t('library.detail.replayExample')+'</button><a class="full-video-link" href="#style='+encodeURIComponent(e.id)+'">'+I18N.t('library.detail.viewFullVideo')+'</a></div>';bindMedia(e,x);
 $('#example-list').innerHTML=t.examples.map(v=>{const s=source(v.style_id);return '<button class="example-choice" data-example="'+esc(v.id)+'" aria-label="'+I18N.t('dialog.style.chooseExample')+': '+esc(v.label)+'" role="radio" aria-checked="'+(v.id===x.id)+'" tabindex="'+(v.id===x.id?'0':'-1')+'"><img src="'+esc(v.poster)+'" alt=""><span><strong>'+esc(v.label)+'</strong><small>'+esc(s.creator)+' · '+exact(v.start)+'–'+exact(v.end)+(s.collection==='mine'?I18N.t('library.detail.myWorkTag'):'')+(isRemoved(s)?I18N.t('library.detail.removedFromLibraryTag'):'')+'</small></span><span class="choice-check" aria-hidden="true"></span></button>';}).join('');
 const own=[...new Set(t.examples.filter(v=>source(v.style_id).collection==='mine').map(v=>source(v.style_id).title))];
 const traits={};
 traits[I18N.t('library.detail.useItFor')]=t.summary;
 traits[I18N.t('library.detail.direction')]=t.direction;
 traits[I18N.t('library.detail.alsoKnownAs')]=t.aliases.join(' · ');
 traits[I18N.t('library.detail.ourExamples')]=own.length?own.join(' · '):I18N.t('library.detail.refOnlyNotLinked');
 $('#detail-traits').innerHTML=Object.entries(traits).map(([key,value])=>'<div class="trait"><dt>'+esc(key)+'</dt><dd>'+esc(value)+'</dd></div>').join('');sharedDetails(t);$('#detail-evidence').textContent=t.evidence+' '+e.evidence;
 $('#detail-links').innerHTML='<button data-source-video="'+esc(e.id)+'">'+I18N.t('library.detail.openFullVideo')+'</button>'+(e.source_url?'<a href="'+esc(e.source_url)+'" target="_blank" rel="noopener noreferrer">'+I18N.t('library.detail.watchOriginal')+'</a><button data-copy-original>'+I18N.t('dialog.style.copyOriginalLink')+'</button>':'')+'<a href="/notes/'+encodeURIComponent(e.id)+'/0" target="_blank" rel="noopener">'+I18N.t('library.detail.sourceNotesLink')+'</a>';
 $('#detail-context').textContent=[I18N.t('library.detail.techniqueId')+t.id,I18N.t('library.detail.chosenExample')+x.id,I18N.t('library.detail.sourceVideoLabel')+e.id,I18N.t('library.detail.sourceWindow')+exact(x.start)+'–'+exact(x.end),I18N.t('library.detail.exampleLabel')+e.media_path,e.composition?I18N.t('library.detail.editableSource')+e.composition:I18N.t('library.detail.refOnlyAdapt'),...e.notes].join('\n');
 updateSelection();updateQuickCopy();window.ReferenceNotes?.mountCurrent();if(!$('#style-dialog').open)$('#style-dialog').showModal();history.replaceState(null,'',referenceHash(id,x.id));
}
function briefTokens(ids){return ids.map(id=>{const e=item(id);return e&&isTech(e)?id+'@'+example(e,false).id:id;});}
function openBrief(ids){return window.ReferenceNotes?.openSelection(ids);}
$('.view-switch').addEventListener('click',event=>{const b=event.target.closest('[data-view]');if(b)setView(b.dataset.view);});
$('.collections').addEventListener('click',event=>{const b=event.target.closest('[data-collection]');if(!b)return;collection=b.dataset.collection;const category=$('#technique').value;updateControls();if([...$('#technique').options].some(x=>x.value===category))$('#technique').value=category;render();});
$('#gallery').addEventListener('click',event=>{const copy=event.target.closest('[data-copy-reference]');if(copy)return copyCardReference(copy.dataset.copyReference,copy.dataset.copyExample||null,copy);const b=event.target.closest('.select-card');if(b)return toggleSelection(b.dataset.id);const open=event.target.closest('[data-open]');if(open){const e=item(open.dataset.open);if(e)isTech(e)?showTechnique(e.id):showStyle(e.id);}});
$('#search').addEventListener('input',render);$('#technique').addEventListener('change',render);$('#creator').addEventListener('change',render);$('#analysis-filter').addEventListener('change',render);$('#library-sort').addEventListener('change',render);
function clearFilters(){ $('#search').value='';$('#technique').value='all';$('#creator').value='all';$('#analysis-filter').value='all';render(); }
function renderActiveFilters(){
 const applied=[['search',$('#search').value.trim()?I18N.t('library.search.resultsLabel',{text:$('#search').value.trim()}):'']];
 for(const id of ['creator','technique',...(view==='techniques'?[]:['analysis-filter'])]){const field=$('#'+id);if(field.value!=='all')applied.push([id,field.options[field.selectedIndex].textContent]);}
 const active=applied.filter(([,text])=>text),count=active.filter(([id])=>id!=='search').length;
 $('#filter-count').textContent=count?String(count):'';
 $('#active-filters').hidden=!active.length;
 $('#active-filters').innerHTML=active.map(([id,text])=>'<button data-clear-filter="'+id+'" aria-label="'+I18N.t('library.filter.removeAria',{text:esc(text)})+'">'+esc(text)+' <span aria-hidden="true">×</span></button>').join('')+(active.length?'<button class="clear-all" data-clear-all>'+I18N.t('library.filter.clearAll')+'</button>':'');
 $('#reset-filters').disabled=!active.length;
}
$('#toggle-filters').addEventListener('click',()=>{const open=$('#toggle-filters').getAttribute('aria-expanded')!=='true';$('#toggle-filters').setAttribute('aria-expanded',String(open));$('#library-filter-panel').hidden=!open;});
$('#active-filters').addEventListener('click',event=>{if(event.target.closest('[data-clear-all]'))return clearFilters();const b=event.target.closest('[data-clear-filter]');if(!b)return;const id=b.dataset.clearFilter;$('#'+id).value=id==='search'?'':'all';render();$('#search').focus();});
$('#reset').addEventListener('click',clearFilters);
$('#reset-filters').addEventListener('click',clearFilters);
$('#clear-selection').addEventListener('click',()=>{selected.clear();saveSelection();});$('#copy-selection').addEventListener('click',()=>openBrief([...selected]));
$('#detail-add').addEventListener('click',()=>{if(active)toggleSelection(active.id);});
$('#detail-quick-copy').addEventListener('click',()=>copyQuickReference());
$('#example-list').addEventListener('click',event=>{const b=event.target.closest('[data-example]');if(b&&active&&isTech(active)){showTechnique(active.id,b.dataset.example);render();}});
$('#example-list').addEventListener('keydown',event=>{if(!['ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;const buttons=[...$('#example-list').querySelectorAll('[data-example]')],at=buttons.indexOf(event.target.closest('[data-example]'));if(at<0)return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(at+(['ArrowDown','ArrowRight'].includes(event.key)?1:-1)+buttons.length)%buttons.length,id=buttons[next].dataset.example;showTechnique(active.id,id);render();$('#example-list').querySelector('[data-example="'+id+'"]')?.focus();});
$('#detail-links').addEventListener('click',event=>{if(event.target.closest('[data-copy-original]'))return copyQuickReference(true);const b=event.target.closest('[data-source-video]');if(b)showStyle(b.dataset.sourceVideo);});
$('#detail-media').addEventListener('click',event=>{if(!active||!isCarousel(active))return;const direct=event.target.closest('[data-carousel-slide]'),step=event.target.closest('[data-carousel-step]');if(direct)showCarouselSlide(active,Number(direct.dataset.carouselSlide));else if(step)showCarouselSlide(active,Number($('#detail-media').dataset.slideIndex)+Number(step.dataset.carouselStep));});
$('#detail-moments').addEventListener('click',event=>{const b=event.target.closest('[data-time]'),video=$('#detail-media video');if(!b||!video)return;const seek=()=>video.currentTime=Number(b.dataset.time);if(video.readyState>=1)seek();else video.addEventListener('loadedmetadata',seek,{once:true});});
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>b.dataset.close==='style-dialog'?closeStyle():$('#'+b.dataset.close).close()));
$('#style-dialog').addEventListener('cancel',event=>{event.preventDefault();closeStyle();});$('#style-dialog').addEventListener('click',event=>{if(event.target===$('#style-dialog'))closeStyle();});$('#brief-dialog').addEventListener('click',event=>{if(event.target===$('#brief-dialog'))$('#brief-dialog').close();});
let libraryRoute=0;
async function applyRoute(){
 const token=++libraryRoute;
 for(const id of ['analysis-dialog','link-dialog'])if($('#'+id).open)$('#'+id).close();
 if($('#removed-references-dialog').open)$('#removed-references-dialog').close();
 if(window.Studio?.route()){closeStyle(false);if($('#brief-dialog').open)$('#brief-dialog').close();return;}
 try{await window.refreshReferenceCatalog();}catch{notify(I18N.t('library.error.refreshFailed'));}
 if(token!==libraryRoute)return;
 const hash=location.hash.slice(1),params=new URLSearchParams(hash),styleId=params.get('style'),techId=params.get('technique'),e=source(styleId),t=techniques.find(t=>t.id===techId);
 if($('#brief-dialog').open)$('#brief-dialog').close();
 view=t||hash==='techniques'?'techniques':isCarousel(e||{})||hash==='carousels'?'carousels':'videos';collection=e||t||view!=='videos'||!browseEntries().some(e=>e.collection==='mine'&&!isCarousel(e))?'all':'mine';
 $('#search').value='';$('#creator').value='all';updateControls();render();
 if(e){showStyle(e.id);if(isCarousel(e)){const n=Number(params.get('slide'));if(Number.isInteger(n)&&n>=1&&n<=e.slides.length)showCarouselSlide(e,n-1);}}
 else if(t){const wanted=params.get('example');showTechnique(t.id,wanted);render();if(wanted&&!t.examples.some(x=>x.id===wanted))notify(I18N.t('library.error.exampleUnavailable'));}
 else{closeStyle(false);if(styleId||techId)notify(I18N.t('library.error.referenceUnavailable'));}
}
window.addEventListener('hashchange',applyRoute);
window.addEventListener('focus',async()=>{
 if(window.Studio?.currentSection!=='library'||document.querySelector('dialog[open]'))return;
 const before=JSON.stringify([entries,[...removedIds]]),category=$('#technique').value,creator=$('#creator').value;
 try{await window.refreshReferenceCatalog();if(before!==JSON.stringify([entries,[...removedIds]])){updateControls();$('#technique').value=[...$('#technique').options].some(x=>x.value===category)?category:'all';$('#creator').value=[...$('#creator').options].some(x=>x.value===creator)?creator:'all';render();}}catch{}
});
window.refreshReferenceCatalog=async()=>{
  const response=await fetch('/catalog.json',{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();entries=data.entries;techniques=data.techniques||[];removedIds=new Set(Object.keys(data.removed_references||{}));
  selected=new Set([...selected].filter(id=>item(id)));for(const t of techniques)if(!t.examples.some(x=>x.id===choices[t.id]))delete choices[t.id];
  const browsable=browseEntries(),families=browseTechniques(),carouselCount=browsable.filter(isCarousel).length,referenceCount=browsable.length-carouselCount;$('#catalog-count').textContent=(referenceCount===1?I18N.t('library.catalog.referenceOne'):I18N.t('library.catalog.referenceMany',{n:referenceCount}))+' · '+(carouselCount===1?I18N.t('library.results.carouselOne'):I18N.t('library.results.carouselMany',{n:carouselCount}))+' · '+(families.length===1?I18N.t('library.results.techniqueOne'):I18N.t('library.results.techniqueMany',{n:families.length}));$('#video-count').textContent=referenceCount;$('#carousel-count').textContent=carouselCount;$('#technique-count').textContent=families.length;window.LibraryVisibility?.refresh();
};
function renderLibraryLanguage(){if(window.Studio?.currentSection==='library'||!window.Studio){updateControls();render();}}
document.addEventListener('i18n:change',renderLibraryLanguage);
// #library-nav-label isn't data-i18n-driven (a custom installation label must survive
// I18N.render(), see site_settings()'s docstring), but its *default* text is still
// language-dependent server-side (library.py: 'השראה' vs 'Reference Library'). Re-fetch
// it on i18n:change too, so toggling the language live updates the nav label the same
// way a fresh page load in that language would, without touching a real custom label.
async function applySiteSettings(){
 try{const response=await fetch('/site-settings.json');if(response.ok){const settings=await response.json();const studioName=settings.studio_name||I18N.t('brand.name');$('#studio-name').textContent=studioName;$('#library-nav-label').textContent=settings.library_label;window.studioName=studioName;$('#studio-monogram').textContent=settings.monogram;$('#studio-footer-monogram').textContent=settings.monogram;if(!window.Studio||window.Studio.currentSection==='projects')document.title=studioName+' · '+I18N.t('app.nav.projects');const credit=$('#studio-credit');credit.hidden=!settings.credit.name;if(settings.credit.name){credit.textContent=I18N.t('footer.builtBy',{name:settings.credit.name});credit.href=settings.credit.url;}}}catch{}
}
document.addEventListener('i18n:change',applySiteSettings);
async function init(){
 if(location.protocol==='file:')return;
 await I18N.ready;
 await applySiteSettings();
 try{
  await window.refreshReferenceCatalog();
  applyRoute();
 }catch{$('#result-count').textContent='';$('#load-error').hidden=false;window.Studio?.route();}
}
// The first route needs every deferred UI module, even when local fetches finish first.
if(document.readyState==='complete')init();
else document.addEventListener('DOMContentLoaded',init,{once:true});
