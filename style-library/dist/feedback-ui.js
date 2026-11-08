/* Local review notes, independent of assistant accounts and approval decisions. */
window.ProjectFeedback = (() => {
  let target = null, data = null, loading = 0, busy = false;
  const drafts = new Map(), saves = new Map(), changes = new Map(), editDrafts = new Map(), noteScroll = new Map();
  let editing = null, deleted = null, notice = '';
  // Separate from `notice`'s text so paintList()/render() can detect "this notice
  // asks for a reload" without matching literal English inside a now-translatable
  // string (the old code checked notice.includes('Refresh notes'), which would stop
  // working the moment the notice text itself became Hebrew).
  let noticeNeedsReload = false;
  async function reply(response) {
    try { return await response.json(); } catch { throw Error(I18N.t('feedback.error.loadFailed')); }
  }
  const key = t => [t.project.id, t.artifact.id, t.frame ?? ''].join('/');
  const timeLabel = t => { const ticks = Math.round(t * 100); return `${Math.floor(ticks / 6000)}:${((ticks % 6000) / 100).toFixed(2).padStart(5, '0')}`; };
  const newest = notes => notes.slice().sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || '')));
  const visibleNotes = () => newest((data?.notes || []).filter(n => !n.deleted_at));
  const openNotes = () => visibleNotes().filter(n => n.status === 'open');
  const versionNotes = () => visibleNotes().filter(n => n.artifact_id === target?.artifact.id);
  const dateLabel = value => { const d = new Date(value); return Number.isNaN(d.valueOf()) ? '' : d.toLocaleString(I18N.lang(), {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}); };
  const versionKey = t => t.project.id + '/' + t.artifact.id;
  function retain() {
    const list = document.querySelector('.feedback-note-list');
    if (target && list && Number.isFinite(list.scrollTop)) noteScroll.set(versionKey(target), list.scrollTop);
    const text = document.querySelector('#feedback-text');
    if (target && text) drafts.set(key(target), {text: text.value, time: target.time});
    const edit = document.querySelector('[data-feedback-edit-text]');
    if (editing && edit) editing.text = edit.value;
    if (editing) editDrafts.set(editing.project + '/' + editing.id, {...editing});
  }
  function contextLabel(t) {
    return t.frame ? I18N.t('feedback.context.frameLabel', {unit: I18N.t(t.artifact.type === 'carousel' ? 'review.unit.slide' : 'review.unit.scene'), number: t.frame}) :
      t.time !== null ? I18N.t('feedback.context.atTime', {time: timeLabel(t.time)}) : I18N.t('feedback.context.wholeVersion');
  }
  function noteLink(n) {
    const q = new URLSearchParams({project: target.project.id, artifact: n.artifact_id});
    if (n.frame) q.set('frame', n.frame);
    if (n.time !== null) q.set('time', n.time);
    return '#' + q;
  }
  function application(n) {
    if (n.status === 'open') return `<span class="feedback-badge">${esc(I18N.t('feedback.badge.open'))}</span>`;
    const applied = n.applied_in, id = applied?.artifact_id;
    const label = typeof applied === 'string' ? applied : applied?.version;
    const text = label ? I18N.t('feedback.badge.appliedIn', {label}) : I18N.t('feedback.badge.applied');
    const found = target.project.artifacts?.some(a => a.id === id);
    return found ? `<a class="feedback-badge applied" href="${esc('#' + new URLSearchParams({project: target.project.id, artifact: id}))}" data-close-feedback>${esc(text)}</a>` : `<span class="feedback-badge applied">${esc(text)}</span>`;
  }
  function noteCards(notes, all = false) {
    return notes.map(n => {
      const edit = editing?.project === target.project.id && editing.id === n.id && editing.all === all;
      const conflict = edit && editing.revision !== n.revision;
      const history = (n.history || []).filter(e => e.before?.text).slice().reverse();
      return `<article data-feedback-note="${esc(n.id)}"${data?.selection?.note_ids.includes(n.id) ? ' class="linked-feedback-note"' : ''}>
        <div class="feedback-note-heading"><a href="${esc(noteLink(n))}" data-close-feedback>${all ? esc((n.label || '') + ' ' + (n.version || '')) + ' · ' : ''}${esc(n.frame ? I18N.t('feedback.note.sceneLabel', {number: n.frame}) : n.time !== null ? timeLabel(n.time) : I18N.t('feedback.context.wholeVersion'))}</a>${n.deleted_at ? `<span class="feedback-badge">${esc(I18N.t('feedback.badge.deleted'))}</span>` : application(n)}</div>
        ${edit ? `<label class="sr-only" for="feedback-edit-text">${esc(I18N.t('feedback.edit.srLabel'))}</label><textarea id="feedback-edit-text" data-feedback-edit-text maxlength="2000" rows="3" ${busy ? 'disabled' : ''}>${esc(editing.text)}</textarea>${n.status !== 'open' ? `<p class="feedback-note-meta">${esc(I18N.t('feedback.edit.statusNote'))}</p>` : ''}${conflict ? `<div class="feedback-conflict"><p>${esc(I18N.t('feedback.conflict.intro'))}</p><p>${esc(n.text)}</p><button class="text-button" data-feedback-rebase>${esc(I18N.t('feedback.conflict.useMine'))}</button></div>` : ''}<div class="feedback-note-actions"><button class="primary" data-feedback-change="edit" data-note-id="${esc(n.id)}" ${busy || conflict ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.saveChanges'))}</button><button class="secondary" data-feedback-cancel ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.cancel'))}</button></div>` : `<p>${esc(n.text)}</p><div class="feedback-note-actions">${n.deleted_at ? `<button class="text-button" data-feedback-change="restore" data-note-id="${esc(n.id)}" ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.restore'))}</button>` : `<button class="text-button" data-feedback-edit="${esc(n.id)}" data-note-scope="${all ? 'all' : 'version'}" ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.edit'))}</button><button class="text-button feedback-delete" data-feedback-change="delete" data-note-id="${esc(n.id)}" ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.delete'))}</button>`}</div>`}
        <span class="feedback-note-meta">${n.updated_at ? esc(I18N.t('feedback.note.dateEdited', {date: dateLabel(n.updated_at || n.created_at)})) : esc(dateLabel(n.updated_at || n.created_at))}</span>
        ${history.length ? `<details class="feedback-note-history"><summary>${esc(I18N.t('feedback.history.summary', {count: history.length}))}</summary>${history.map(e => `<div><span>${esc(I18N.t(e.action === 'edit' ? 'feedback.history.beforeEdit' : e.action === 'delete' ? 'feedback.history.beforeDelete' : 'feedback.history.beforeRestore'))} · ${esc(dateLabel(e.at))}</span><p>${esc(e.before.text)}</p>${e.before.status !== 'open' ? application(e.before) : ''}</div>`).join('')}</details>` : ''}
      </article>`;
    }).join('');
  }
  function paintList() {
    const dialog = document.querySelector('#feedback-dialog');
    if (!dialog?.open || !target || !data) return;
    const notes = visibleNotes(), removed = newest(data.notes.filter(n => n.deleted_at));
    dialog.querySelector('.feedback-all-scope').textContent = I18N.t('feedback.list.scopeSummary', {project: target.project.title, count: notes.length, open: openNotes().length});
    dialog.querySelector('.saved-feedback-list').innerHTML = (notes.length ? noteCards(notes, true) : `<p>${esc(I18N.t('feedback.list.empty'))}</p>`) + (removed.length ? `<details class="feedback-deleted"><summary>${esc(I18N.t('feedback.list.deletedSummary', {count: removed.length}))}</summary>${noteCards(removed, true)}</details>` : '');
    dialog.querySelector('[data-feedback-copy]').disabled = busy || !openNotes().length;
    dialog.querySelector('[data-feedback-copy]').textContent = I18N.t('feedback.list.copyOpen');
    const status = dialog.querySelector('.feedback-dialog-status'); status.textContent = notice;
    if (noticeNeedsReload) { const refresh = document.createElement('button'); refresh.className = 'text-button'; refresh.dataset.feedbackReload = ''; refresh.textContent = I18N.t('feedback.actions.refreshNotes'); status.append(document.createElement('br'), refresh); }
  }
  function paint() {
    const box = document.querySelector('#feedback-panel');
    if (!box || !target) return;
    const active = document.activeElement, field = ['feedback-text', 'feedback-edit-text'].includes(active?.id) ? {id: active.id, start: active.selectionStart, end: active.selectionEnd} : null;
    const notes = visibleNotes(), current = versionNotes(), pending = current.filter(n => n.status === 'open'), attached = target.time !== null;
    const version = target.artifact.version || target.artifact.label;
    const linked = data?.selection, completed = linked ? data.notes.filter(n => linked.note_ids.includes(n.id) && n.status !== 'open').length : 0;
    box.innerHTML = `<div class="feedback-heading"><h4>${esc(I18N.t('feedback.heading.title'))}</h4>
      <button class="text-button" data-feedback-list ${!data ? 'disabled' : ''}>${esc(I18N.t('feedback.heading.allSavedNotes', {count: notes.length}))}</button></div>
      ${linked ? `<p class="feedback-link-context">${esc(I18N.t(linked.note_ids.length === 1 ? (completed ? 'feedback.link.contextOneApplied' : 'feedback.link.contextOne') : (completed ? 'feedback.link.contextManyApplied' : 'feedback.link.contextMany'), {count: linked.note_ids.length, completed}))}</p>` : ''}
      <div class="feedback-context ${attached ? 'is-attached' : ''}" id="feedback-position" role="status">${attached ? `<span><span aria-hidden="true">✓</span> ${I18N.t('feedback.context.noteTime', {time: '<strong>' + esc(timeLabel(target.time)) + '</strong>', version: esc(version)})}</span><span class="moment-options"><button data-feedback-remove-moment ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.removeTimestamp'))}</button></span>` : `<span>${esc(I18N.t('feedback.context.versionContext', {version, context: contextLabel(target)}))}</span>`}</div>
      <label class="sr-only" for="feedback-text">${esc(I18N.t('feedback.textarea.srLabel'))}</label>
      <textarea id="feedback-text" maxlength="2000" rows="3" ${busy ? 'disabled' : ''} placeholder="${esc(I18N.t('feedback.textarea.placeholder'))}">${esc(drafts.get(key(target))?.text || '')}</textarea>
      <div class="feedback-actions">${target.artifact.type === 'video' ? `<button class="secondary moment-button" data-feedback-moment ${busy ? 'disabled' : ''} title="${esc(I18N.t('feedback.actions.addTimestampTitle'))}">${esc(I18N.t('feedback.actions.addTimestamp'))}</button>` : ''}
      <button class="primary" data-feedback-save ${!data?.contexts?.[target.artifact.id] || busy ? 'disabled' : ''}>${esc(busy ? I18N.t('project.saving') : I18N.t('feedback.actions.saveFeedback'))}</button></div>
      <button class="text-button feedback-refresh" data-feedback-reload ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.refreshNotes'))}</button>
      <p id="feedback-status" role="status">${esc(notice || (data ? I18N.t('feedback.status.readyHint') : I18N.t('feedback.status.loadingHint')))}</p>
      ${deleted && data?.notes.some(n => n.id === deleted && n.deleted_at) ? `<p class="feedback-undo">${esc(I18N.t('feedback.undo.notice'))} <button class="text-button" data-feedback-change="restore" data-note-id="${esc(deleted)}" ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.actions.undo'))}</button></p>` : ''}
      <div class="feedback-notes" aria-label="${esc(I18N.t('feedback.notes.sectionAria'))}">${current.length ? `<h5 id="version-feedback-heading">${esc(I18N.t('feedback.notes.savedHeading', {count: current.length}))}</h5><div class="feedback-note-list" role="region" aria-labelledby="version-feedback-heading" tabindex="0">${noteCards(current)}</div>` : ''}</div>
      ${pending.length ? `<section class="feedback-handoff" aria-label="${esc(I18N.t('feedback.handoff.ariaLabel'))}"><div><h5>${esc(I18N.t('feedback.handoff.heading'))}</h5><p><strong>${esc(I18N.t(pending.length === 1 ? 'feedback.handoff.statusOne' : 'feedback.handoff.statusMany', {count: pending.length, version}))}</strong></p></div><button class="primary" data-feedback-copy="version" ${busy ? 'disabled' : ''}>${esc(I18N.t('feedback.handoff.copyButton'))}</button><p>${esc(I18N.t('feedback.handoff.copyHelp'))}</p><p class="feedback-copy-status" role="status"></p></section>` : ''}`;
    paintList();
    const list = document.querySelector('.feedback-note-list');
    if (list) list.scrollTop = noteScroll.get(versionKey(target)) || 0;
    if (field) { const next = document.querySelector('#' + field.id); if (next && !next.disabled) { next.focus({preventScroll: true}); if (typeof field.start === 'number') next.setSelectionRange(field.start, field.end); } }
  }
  async function render(project, artifact, frameIndex = 0) {
    retain();
    const sameProject = target?.project.id === project.id;
    if (target?.artifact.id !== artifact.id || target?.frame !== (artifact.frames ? frameIndex + 1 : null)) { notice = ''; noticeNeedsReload = false; }
    if (!sameProject) { editing = null; deleted = null; notice = ''; noticeNeedsReload = false; data = null; }
    if (editing && !editing.all && data?.notes.find(n => n.id === editing.id)?.artifact_id !== artifact.id) editing = null;
    target = {project, artifact, frame: artifact.frames ? frameIndex + 1 : null, time: null};
    target.time = drafts.get(key(target))?.time ?? null;
    const token = ++loading;
    paint();
    try {
      const params = new URLSearchParams(location.hash.slice(1));
      const selection = params.get('project') === project.id ? params.get('feedback') : null;
      const response = await fetch('/feedback?project=' + encodeURIComponent(project.id) + (selection !== null ? '&selection=' + encodeURIComponent(selection) : ''), {cache: 'no-store'});
      const result = await reply(response);
      if (token !== loading) return;
      if (!response.ok) { data = null; paint(); const error = Error(I18N.server(result.error) || I18N.t('feedback.error.notesCouldNotLoad')); error.selection = selection !== null; throw error; }
      if (result.selection?.artifact_id && result.selection.artifact_id !== artifact.id) { data = null; paint(); const error = Error(I18N.t('feedback.error.wrongVersionLink')); error.selection = true; throw error; }
      retain(); data = result; if (noticeNeedsReload) { notice = I18N.t('feedback.notice.refreshed'); noticeNeedsReload = false; } paint();
    } catch (error) {
      if (token === loading && document.querySelector('#feedback-status')) {
        const status = document.querySelector('#feedback-status');
        status.textContent = (error instanceof TypeError ? I18N.t('feedback.error.network') : error.message) + I18N.t('feedback.error.reopenRetry');
        if (error.selection) { const button = document.createElement('button'); button.className = 'text-button'; button.dataset.feedbackShowProject = ''; button.textContent = I18N.t('feedback.actions.showProjectFeedback'); status.append(document.createElement('br'), button); }
      }
    }
  }
  function moment() {
    if (!target || busy) return;
    const video = document.querySelector('#project-artifact video');
    if (!video || target.artifact.type !== 'video' || !Number.isFinite(video.currentTime)) return;
    video.pause();
    retain(); target.time = Math.round(video.currentTime * 1000) / 1000;
    drafts.set(key(target), {...drafts.get(key(target)), time: target.time});
    paint();
    document.querySelector('#feedback-status').textContent = I18N.t('feedback.moment.set', {time: timeLabel(target.time)});
    document.querySelector('#feedback-text')?.focus();
  }
  function removeMoment() {
    if (!target || busy) return;
    retain(); target.time = null;
    drafts.set(key(target), {...drafts.get(key(target)), time: null});
    paint();
    document.querySelector('#feedback-status').textContent = I18N.t('feedback.moment.removed');
    document.querySelector('#feedback-text')?.focus();
  }
  async function save() {
    const text = document.querySelector('#feedback-text');
    if (busy || !target || !data || !text?.value.trim()) {
      if (text && !text.value.trim()) { text.focus(); document.querySelector('#feedback-status').textContent = I18N.t('feedback.save.writeNoteFirst'); }
      return;
    }
    retain();
    const destination = target, token = key(target), position = contextLabel(target);
    let body = {project_id: target.project.id, artifact_id: target.artifact.id,
      context_revision: data.contexts[target.artifact.id], text: text.value,
      time: target.time, frame: target.frame, request_id: crypto.randomUUID()};
    const signature = JSON.stringify({...body, request_id: null});
    if (saves.get(token)?.signature === signature) body = saves.get(token).body;
    else saves.set(token, {signature, body});
    ++loading; busy = true; notice = ''; noticeNeedsReload = false;
    paint();
    document.querySelector('#feedback-status').textContent = I18N.t('project.saving');
    try {
      const response = await fetch('/feedback', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'feedback'}, body: JSON.stringify(body)});
      const result = await reply(response);
      if (!response.ok) { const error = Error(I18N.server(result.error) || I18N.t('feedback.save.failedDefault')); error.conflict = response.status === 409; throw error; }
      drafts.delete(token); saves.delete(token); noteScroll.set(versionKey(destination), 0); busy = false;
      if (target === destination) {
        target.time = null; data = result; paint();
        const status = document.querySelector('#feedback-status');
        status.textContent = I18N.t('feedback.save.savedStatus', {position});
        status.classList.add('feedback-saved');
      } else { retain(); if (target?.project.id === destination.project.id) data = result; paint(); }
      notify(I18N.t('feedback.save.toast'));
    } catch (error) {
      busy = false;
      if (target !== destination) { retain(); paint(); }
      if (target === destination) {
        retain(); paint();
        document.querySelector('#feedback-status').textContent = error instanceof TypeError ? I18N.t('feedback.save.networkPreserved') : error.message;
        if (error.conflict) {
          document.querySelector('[data-feedback-save]').disabled = true;
          const button = document.createElement('button'); button.className = 'secondary';
          button.dataset.feedbackRefresh = ''; button.textContent = I18N.t('feedback.save.refreshButton');
          document.querySelector('#feedback-status').append(document.createElement('br'), button);
        }
      }
    }
  }
  function list() {
    if (!data || !target) return;
    retain();
    if (editing && !editing.all) editing.all = true;
    const dialog = document.querySelector('#feedback-dialog');
    dialog.showModal(); paint();
  }
  function beginEdit(id, all) {
    if (busy || !data || !target) return;
    retain();
    const n = data.notes.find(n => n.id === id && !n.deleted_at);
    if (!n) return;
    editing = editDrafts.get(target.project.id + '/' + id) || {id, project: target.project.id, text: n.text, revision: n.revision, all};
    editing.all = all; notice = ''; noticeNeedsReload = false; paint();
    document.querySelector('[data-feedback-edit-text]')?.focus();
  }
  async function changeNote(action, id) {
    if (busy || !target || !data) return;
    retain();
    const n = data.notes.find(n => n.id === id);
    if (!n || (action === 'edit' && (!editing || !editing.text.trim() || editing.revision !== n.revision))) return;
    const project = target.project.id;
    let body = {project_id: project, note_id: id, revision: action === 'edit' ? editing.revision : n.revision, action, request_id: crypto.randomUUID(), ...(action === 'edit' ? {text: editing.text} : {})};
    const signature = JSON.stringify({...body, request_id: null});
    if (changes.has(signature)) body = changes.get(signature);
    else changes.set(signature, body);
    ++loading; busy = true; notice = I18N.t('project.saving'); noticeNeedsReload = false; paint();
    try {
      const response = await fetch('/feedback-note', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'feedback-note'}, body: JSON.stringify(body)});
      const result = await reply(response);
      if (!response.ok) throw Error(I18N.server(result.error) || I18N.t('feedback.note.changeFailedDefault'));
      changes.delete(signature);
      if (target?.project.id === project) {
        data = result;
        if (action === 'edit' && n.artifact_id === target.artifact.id) noteScroll.set(versionKey(target), 0);
        editDrafts.delete(project + '/' + id);
        if (editing?.id === id) editing = null;
        deleted = action === 'delete' ? id : deleted === id ? null : deleted;
        notice = I18N.t(action === 'delete' ? 'feedback.note.deletedUndo' : action === 'restore' ? 'feedback.note.restored' : 'feedback.note.changesSaved');
        noticeNeedsReload = false;
      }
    } catch (error) {
      if (target?.project.id === project) { notice = (error instanceof TypeError ? I18N.t('feedback.save.networkPreserved') : error.message) + I18N.t('feedback.note.useRefreshSuffix'); noticeNeedsReload = true; }
    } finally { busy = false; paint(); }
  }
  async function copyNotes(all = false, button = null) {
    if (!target || !data || busy || button?.disabled) return;
    const destination = target, notes = all ? openNotes() : versionNotes().filter(n => n.status === 'open');
    if (!notes.length) return;
    const project = target.project, version = target.artifact.version || target.artifact.label;
    const body = {project_id: project.id, artifact_id: all ? null : target.artifact.id, note_ids: notes.map(n => n.id), note_revisions: Object.fromEntries(notes.map(n => [n.id, n.content_revision]))};
    const status = document.querySelector(all ? '.feedback-dialog-status' : '.feedback-copy-status');
    if (button) button.disabled = true;
    if (status) status.textContent = I18N.t('feedback.copy.preparingLink');
    let text;
    try {
      const response = await fetch('/feedback-link', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'feedback-link'}, body: JSON.stringify(body)});
      const selection = await reply(response);
      if (!response.ok) throw Error(selection.error || I18N.t('feedback.copy.linkFailed'));
      if (!/^[a-f0-9]{24}$/.test(selection.id) || selection.project_id !== body.project_id || selection.artifact_id !== body.artifact_id || JSON.stringify(selection.note_ids?.slice().sort()) !== JSON.stringify(body.note_ids.slice().sort()))
        throw Error(I18N.t('feedback.copy.linkUnverified'));
      const link = new URL('#' + new URLSearchParams({project: project.id, ...(!all ? {artifact: destination.artifact.id} : {}), feedback: selection.id}), location.href);
      const messageKey = all
        ? (notes.length === 1 ? 'feedback.copy.messageOneAll' : 'feedback.copy.messageManyAll')
        : (notes.length === 1 ? 'feedback.copy.messageOneVersion' : 'feedback.copy.messageManyVersion');
      text = I18N.t(messageKey, {count: notes.length, project: project.title, version, link: link.href});
    } catch (error) {
      if (status?.isConnected) status.textContent = error instanceof TypeError ? I18N.t('feedback.copy.networkPreserved') : error.message;
      if (button?.isConnected) button.disabled = false;
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      if (target === destination) {
        if (button?.isConnected) button.textContent = I18N.t('feedback.copy.doneStatus');
        if (status?.isConnected) status.textContent = I18N.t('feedback.copy.doneHelp');
      }
      notify(I18N.t('feedback.copy.toastCopied'));
    } catch {
      const field = document.querySelector('#feedback-copy-text'); field.value = text;
      document.querySelector('#feedback-copy-dialog').showModal(); field.focus(); field.select();
    } finally {
      if (button?.isConnected) button.disabled = false;
    }
  }
  document.addEventListener('click', event => {
    const edit = event.target.closest('[data-feedback-edit]');
    if (edit) beginEdit(edit.dataset.feedbackEdit, edit.dataset.noteScope === 'all');
    const change = event.target.closest('[data-feedback-change]');
    if (change) changeNote(change.dataset.feedbackChange, change.dataset.noteId);
    if (event.target.closest('[data-feedback-cancel]') && !busy) { retain(); if (editing) editDrafts.delete(editing.project + '/' + editing.id); editing = null; notice = ''; noticeNeedsReload = false; paint(); }
    if (event.target.closest('[data-feedback-rebase]') && editing && !busy) { retain(); editing.revision = data.notes.find(n => n.id === editing.id)?.revision; notice = I18N.t('feedback.note.readyToSave'); noticeNeedsReload = false; paint(); }
    if (event.target.closest('[data-feedback-reload]') && target && !busy) render(target.project, target.artifact, (target.frame || 1) - 1);
    if (event.target.closest('[data-feedback-moment]')) moment();
    if (event.target.closest('[data-feedback-remove-moment]')) removeMoment();
    if (event.target.closest('[data-feedback-save]')) save();
    if (event.target.closest('[data-feedback-list]')) list();
    if (event.target.closest('[data-feedback-refresh]')) window.Studio?.route();
    if (event.target.closest('[data-feedback-show-project]')) { const params = new URLSearchParams(location.hash.slice(1)); params.delete('feedback'); history.replaceState(null, '', '#' + params); window.Studio?.route(); }
    const copy = event.target.closest('[data-feedback-copy]');
    if (copy) copyNotes(copy.dataset.feedbackCopy === 'all', copy);
    if (event.target.closest('[data-close-feedback]')) { retain(); document.querySelector('#feedback-dialog').close(); if (editing) { editing.all = false; if (data?.notes.find(n => n.id === editing.id)?.artifact_id !== target?.artifact.id) editing = null; } paint(); }
  });
  document.querySelector('#feedback-dialog')?.addEventListener?.('close', () => { retain(); if (editing) { editing.all = false; if (data?.notes.find(n => n.id === editing.id)?.artifact_id !== target?.artifact.id) editing = null; } paint(); });
  return {render, retain, moment, hasDraft: () => !!document.querySelector('#feedback-text')?.value.trim() || !!editing || busy};
})();
