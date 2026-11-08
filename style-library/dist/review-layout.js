/* Presentation helpers. IDs, files and approval decisions remain in their existing registries. */
window.ReviewLayout = (() => {
  const h = esc;
  const STAGE_KEYS = ['script', 'spoken', 'storyboard', 'edit', 'carousel', 'slides', 'studies', 'notes'];
  function stage(p, a) {
    if (STAGE_KEYS.includes(a.stage)) return a.stage;
    const words = (a.id + ' ' + a.label).toLowerCase();
    if (a.type === 'carousel') return 'carousel';
    if (a.type === 'video') return a.role === 'assembly' || /spoken|speech|available-cut/.test(words) ? 'spoken' : 'edit';
    if (a.type === 'board') return p.format === 'presentation' ? 'slides' : /storyboard/.test(words) ? 'storyboard' : 'studies';
    return /visual.plan|direction|storyboard/.test(words) ? 'storyboard' : 'notes';
  }
  // Recomputed on every call (not a module-load constant) so the stage tab labels follow
  // I18N.t() live — this file re-renders via studio.js's i18n:change handler, never on its own.
  function stageLabels() {
    return {script: I18N.t('review.stage.script'), spoken: I18N.t('review.stage.spoken'), storyboard: I18N.t('review.stage.storyboard'), edit: I18N.t('review.stage.edit'), carousel: I18N.t('review.stage.carousel'), slides: I18N.t('review.stage.slides'), studies: I18N.t('review.stage.studies'), notes: I18N.t('review.stage.notes')};
  }
  function script(p) { return {id: "@script", type: "script", stage: "script", label: I18N.t('review.script.label'), available: true}; }
  function versions(p, name) {
    if (name === "script") return p.format === "video" ? [script(p)] : [];
    return p.artifacts.filter(a => stage(p, a) === name).sort((a, b) => {
      if (a.id === p.primary_artifact) return -1;
      if (b.id === p.primary_artifact) return 1;
      const number = a => Number((String(a.version || '').match(/V(\d+)/i) || [])[1] || 0);
      return number(b) - number(a);
    });
  }
  function badge(p, a) {
    if(p.stale)return I18N.t('review.badge.notesUpdated');
    const tags = [];
    if(a.id!==p.primary_artifact&&versions(p,stage(p,a))[0]?.id===a.id)tags.push(I18N.t('review.badge.latestSaved'));
    if (a.id === p.primary_artifact) tags.push(I18N.t('review.badge.latest'));
    if (a.role === 'final') tags.push(I18N.t('review.badge.final'));
    else if (a.role === 'approved') tags.push(I18N.t('review.badge.approved'));
    else if (a.role === 'baseline') tags.push(I18N.t('review.badge.accepted'));
    return tags.join(' · ') || (a.role === 'history' ? I18N.t('review.badge.earlierVersion') : I18N.t('review.badge.savedVersion'));
  }
  function navigation(p, a) {
    const name = stage(p, a), rows = versions(p, name), stageLabel = stageLabels();
    // The Script screen is out of scope for the Hebrew-first studio (Task 4); its tab
    // is hidden here but `script`/`versions('script', ...)` stay intact for direct links.
    return `<div class="review-navigation"><div class="stage-tabs" role="group" aria-label="${h(I18N.t('review.navigation.stagesAria'))}">${Object.entries(stageLabel).filter(([key]) => key === 'script' ? false : key === 'notes' && p.format === 'video' ? false : p.artifacts.some(v => stage(p, v) === key)).map(([key, label]) => `<button data-stage="${h(key)}" aria-pressed="${key === name}">${h(label)}</button>`).join('')}</div>
      ${name==='script'?'':`<details class="version-picker"><summary>${h(a.version || a.label)} <span>${h(badge(p, a))}</span> <span aria-hidden="true">⌄</span></summary><div class="version-list" role="group" aria-label="${h(I18N.t('review.navigation.versionsAria', {stage: stageLabel[name] || name}))}">${rows.map(v => `<button data-artifact="${h(v.id)}" aria-label="${h(I18N.t('review.navigation.viewVersionAria', {label: v.label, version: v.version || ''}))}" aria-pressed="${v.id === a.id}"><span><strong>${h(v.version || v.label)}</strong><small>${h(badge(p, v))}</small></span><b>${h(v.label)}</b><span class="version-description">${h(v.description || '')}</span></button>`).join('')}</div></details>`}</div>`;
  }
  function download(d) {
    return d.available ? `<a href="${h(d.url)}" download="${h(d.path.split('/').pop())}">${h(d.label)} ↓</a>` : `<span class="unavailable">${h(I18N.t('review.downloads.unavailable', {label: d.label}))}</span>`;
  }
  function downloads(a) {
    const files = [...(a.downloads || [])];
    // The synthetic "download video" entry is translated for display, so it can no
    // longer be told apart from the other (data-provided, untranslated) download labels
    // by matching English text — an explicit marker keeps it sorted into `primary` in
    // every UI language.
    if (a.type === 'video' && a.available) files.unshift({...a, label: I18N.t('review.downloads.video'), isPrimaryVideo: true});
    const primary = files.filter(d => d.isPrimaryVideo || /^(captions|download all|all slides|powerpoint|slide deck|final assets|carousel.*zip)/i.test(d.label));
    const extra = files.filter(d => !primary.includes(d));
    return `<div class="review-downloads">${primary.map(download).join('')}${extra.length ? `<details class="more-downloads"><summary>${h(I18N.t('review.downloads.more'))}</summary><div>${extra.map(download).join('')}</div></details>` : ''}</div>`;
  }
  function details(p) {
    return `${p.format==='video'?`<details class="script-idea-details" hidden><summary>${h(I18N.t('review.details.ideaReferences'))}</summary><div id="project-script-context" class="script-context" hidden></div></details>`:''}<details class="project-details"><summary>${h(I18N.t('review.details.title'))} <span>${h(I18N.t('review.details.subtitle'))}</span></summary><div class="project-details-body"><div class="project-detail-summary"><section><h3>${h(I18N.t('review.details.about'))}</h3><p>${h(p.summary || p.input_note || '')}</p></section>${p.baseline ? `<section><h3>${h(I18N.t('review.details.acceptedDirection'))}</h3><p>${h(p.baseline)}</p></section>` : ''}<section><h3>${h(I18N.t('review.details.nextStep'))}</h3><p>${h(p.next_step || '')}</p></section></div><div class="note-choices">${p.source_notes.map((n, i) => `<button class="secondary" data-project-note="${i}" ${n.available ? '' : 'disabled'}>${h(n.label)}</button>`).join('')}</div><article id="readable-project-note" class="readable-note" hidden></article><details class="original-notes"><summary>${h(I18N.t('review.details.originalFiles'))}</summary><div>${p.source_notes.map(n => n.available ? `<a href="${h(n.url)}" target="_blank" rel="noopener">${h(n.label)}</a>` : `<span>${h(I18N.t('review.downloads.unavailable', {label: n.label}))}</span>`).join('')}</div></details>${p.reference_id && entries.some(e => e.id === p.reference_id) ? `<a class="plain-link" href="#style=${encodeURIComponent(p.reference_id)}">${h(I18N.t('review.details.viewInLibrary'))}</a>` : ''}</div></details>`;
  }
  function readable(text) {
    let code = false;
    return text.split('\n').map(line => {
      if (line.startsWith('```')) { code = !code; return ''; }
      if (code) return `<pre>${h(line)}</pre>`;
      if (!line.trim() || /^<!--/.test(line)) return '';
      const heading = line.match(/^#{1,6}\s+(.+)/);
      if (heading) return `<h4>${h(heading[1])}</h4>`;
      return `<p>${h(line.replace(/^[-*]\s+/, '• ').replace(/\*\*([^*]+)\*\*/g, '$1'))}</p>`;
    }).join('');
  }
  function heading(p, a) {
    return `<div class="artifact-heading"><div><p class="eyebrow">${h(badge(p, a))}</p><h3>${h(a.label)}${a.version ? ' · ' + h(a.version) : ''}</h3></div>${downloads(a)}</div>`;
  }
  function frameMedia(f) {
    return !f.available ? `<p>${h(I18N.t('review.frame.unavailable'))}</p>` : f.media_type === 'video' ? `<video controls muted playsinline preload="metadata" src="${h(f.url)}" aria-label="${h(f.title)}"></video>` : `<button class="enlarge-frame" data-enlarge-frame aria-label="${h(I18N.t('review.frame.enlargeAria', {title: f.title}))}"><img src="${h(f.url)}" alt="${h(f.title)}"><span>${h(I18N.t('review.frame.enlarge'))}</span></button>`;
  }
  function frameNotes(a, f) { return `<p class="frame-timing">${h(f.timing || '')}</p><h4 class="frame-title">${h(f.title)}</h4>${f.speech ? `<div class="frame-note"><h5>${h(I18N.t('review.frame.spokenLine'))}</h5><p>${h(f.speech)}</p></div>` : ''}${f.copy ? `<div class="frame-note"><h5>${h(I18N.t('review.frame.onScreen'))}</h5><p>${h(f.copy)}</p></div>` : ''}<details class="scene-details"><summary>${h(I18N.t('review.frame.movementSound'))}</summary>${[[I18N.t('review.frame.movement'), f.motion], [I18N.t('review.frame.sound'), f.sound]].filter(([, v]) => v).map(([label, value]) => `<div class="frame-note"><h5>${h(label)}</h5><p>${h(value)}</p></div>`).join('')}<p>${h(a.description || '')}</p>${f.available ? `<a href="${h(f.url)}" download="${h(f.path.split('/').pop())}">${h(I18N.t(a.type === 'carousel' ? 'review.frame.downloadSlide' : 'review.frame.downloadFrame'))}</a>` : ''}</details>`; }
  function revealFrame(container) {
    const strip = container.querySelector('.project-thumbs'), selected = container.querySelector('[data-project-frame][aria-pressed="true"]');
    if (!strip || !selected || strip.classList.contains('is-overview')) return;
    const bounds = strip.getBoundingClientRect(), item = selected.getBoundingClientRect();
    const delta = item.left < bounds.left ? item.left - bounds.left - 4 : item.right > bounds.right ? item.right - bounds.right + 4 : 0;
    if (delta) strip.scrollLeft += delta;
  }
  function updateFrame(container, a, index) {
    const media = container.querySelector('[data-scene-media]'), notes = container.querySelector('[data-scene-notes]');
    if (!media || !notes || !a.frames?.[index]) return false;
    const expanded = notes.querySelector('.scene-details')?.open;
    media.innerHTML = frameMedia(a.frames[index]);
    notes.innerHTML = frameNotes(a, a.frames[index]);
    const details = notes.querySelector('.scene-details'); if (details) details.open = !!expanded;
    container.querySelector('[data-scene-position]').textContent = I18N.t('review.frame.position', {current: index + 1, total: a.frames.length, unit: I18N.t(a.type === 'carousel' ? 'review.unit.slide' : 'review.unit.scene')});
    container.querySelector('[data-frame-step="-1"]').disabled = index === 0;
    container.querySelector('[data-frame-step="1"]').disabled = index === a.frames.length - 1;
    container.querySelectorAll('[data-project-frame]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.projectFrame) === index)));
    revealFrame(container);
    return true;
  }
  function content(p, a, frameIndex) {
    if (a.type === "script") return "";
    const title = heading(p, a);
    const earlier = a.id !== p.primary_artifact ? `<div class="viewing-saved"><span>${h(I18N.t('review.viewing.message', {version: a.version || a.label, badge: badge(p, a)}))}</span><button class="text-button" data-back-current>${h(I18N.t('review.viewing.backToLatest'))}</button>${a.type === 'video' ? `<button class="text-button" data-use-version>${h(I18N.t('review.viewing.useAsStart'))}</button>` : ''}</div>` : '';
    if (!a.available) return title + earlier + `<p class="project-notice">${h(I18N.t('review.unavailable.body'))}</p>`;
    const thumbs = a.frames ? `<div class="storyboard-toolbar"><button class="text-button" data-overview>${h(I18N.t(a.type === 'carousel' ? 'project.seeAllSlides' : 'project.seeAllScenes', {n: a.frames.length}))}</button></div><div class="project-thumbs" aria-label="${h(I18N.t('review.thumbs.chooseAria'))}">${a.frames.map((f, i) => `<button data-project-frame="${i}" aria-label="${h(I18N.t('review.thumbs.sceneAria', {number: i + 1, title: f.title}))}" aria-pressed="${i === frameIndex}">${f.available && f.media_type !== 'video' ? `<img src="${h(f.url)}" alt="" loading="lazy">` : '<span class="thumb-video">▶</span>'}<span>${String(i + 1).padStart(2, '0')}</span><small>${h(f.title)}</small></button>`).join('')}</div>` : '';
    let media;
    if (a.type === 'video') {
      // T9b: every video gets a poster -- the project's human-curated cover for the
      // primary artifact when there is one, otherwise the server-generated frame at
      // <a.url>?poster=1 (tone-mapped to SDR for HEVC/HLG iPhone footage) -- so the player
      // never shows a black box, including for a browser that can't decode the source at
      // all. A poster that isn't ready/available simply 404s; the <video> element then
      // just shows nothing special for `poster`, same as having none.
      const poster = a.id === p.primary_artifact && p.cover ? p.cover : a.url + '?poster=1';
      media = `<div class="artifact-stage video-stage"><video controls muted playsinline preload="metadata" poster="${h(poster)}" src="${h(a.url)}" aria-label="${h(I18N.t('review.video.describeAria', {title: p.title, label: a.label, version: a.version || ''}))}"></video></div>`;
    } else if (a.frames) {
      media = `<div class="storyboard-media"><div data-scene-media class="artifact-stage frame-stage ${p.format === 'presentation' ? 'landscape-stage' : ''}">${frameMedia(a.frames[frameIndex])}</div><div class="frame-navigation"><button data-frame-step="-1" aria-label="${h(I18N.t('review.frame.previousAria'))}" ${frameIndex === 0 ? 'disabled' : ''}>←</button><span data-scene-position>${h(I18N.t('review.frame.position', {current: frameIndex + 1, total: a.frames.length, unit: I18N.t(a.type === 'carousel' ? 'review.unit.slide' : 'review.unit.scene')}))}</span><button data-frame-step="1" aria-label="${h(I18N.t('review.frame.nextAria'))}" ${frameIndex === a.frames.length - 1 ? 'disabled' : ''}>→</button></div>${thumbs}</div>`;
    } else media = `<article class="readable-note project-document">${h(I18N.t('review.notes.loadingPlaceholder'))}</article>`;
    const f = a.frames?.[frameIndex];
    const notes = f ? `<div data-scene-notes>${frameNotes(a, f)}</div>` : `<h4 class="what-changed">${h(I18N.t(a.id === p.primary_artifact ? 'review.whatChanged.ready' : 'review.whatChanged.aboutVersion'))}</h4><p class="artifact-description">${h(a.description || '')}</p>`;

    return title + earlier + `<div class="artifact-layout ${a.frames ? 'storyboard-layout' : ''} ${p.format === 'presentation' ? 'landscape-artifact' : ''}">${media}<div class="artifact-notes">${notes}<div id="review-controls"></div><section id="feedback-panel"></section></div></div>`;
  }
  document.addEventListener('click', event => {
    document.querySelectorAll('.version-picker[open]').forEach(menu => {if(!menu.contains(event.target))menu.open=false;});
  });
  document.addEventListener('keydown', event => {
    if(event.key!=='Escape')return;
    const menu=document.querySelector('.version-picker[open]');
    if(menu){menu.open=false;menu.querySelector('summary').focus();event.preventDefault();event.stopPropagation();}
  });
  return {stage, script, versions, navigation, details, heading, content, readable, updateFrame, revealFrame};
})();
