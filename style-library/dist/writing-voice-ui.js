/* Writing memory stays local. The editing assistant maintains its meaning. */
window.WritingVoice = (() => {
 let dialog = null;
 let opener = null;
 let data = null;
 let busy = false;
 let pending = null;
 let undoId = null;

 async function reply(response) {
  const value = await response.json();
  if (!response.ok) throw Error(I18N.server(value.error) || I18N.t('writingVoice.error.unavailable'));
  return value;
 }

 function message(value) {
  dialog.querySelector('[data-voice-status]').textContent = value;
 }

 function render() {
  const list = dialog.querySelector('[data-voice-list]');
  list.innerHTML = data.preferences.length ? data.preferences.map(memory => {
   const examples = (memory.examples || []).map(example =>
    '<div class="memory-example">' +
    (example.context ? '<p class="memory-context">' + esc(example.context) + '</p>' : '') +
    (example.before ? '<p><strong>' + esc(I18N.t('writingVoice.example.earlier')) + '</strong></p><blockquote>' + esc(example.before) + '</blockquote>' : '') +
    (example.after ? '<p><strong>' + esc(I18N.t('writingVoice.example.chosen')) + '</strong></p><blockquote>' + esc(example.after) + '</blockquote>' : '') +
    '<p><strong>' + esc(I18N.t('writingVoice.example.feedback')) + '</strong></p><blockquote>' + esc(example.feedback) + '</blockquote></div>'
   ).join('');
   return '<li data-memory="' + esc(memory.id) + '"><p class="memory-summary">' + esc(memory.text) + '</p>' +
    '<details><summary>' + esc(I18N.t('writingVoice.why')) + '</summary><p>' + esc(memory.source) + '</p>' + examples + '</details>' +
    '<div class="memory-actions"><button class="text-button" data-correct-memory="' + esc(memory.id) + '">' + esc(I18N.t('writingVoice.correct')) + '</button>' +
    '<button class="text-button" data-forget-memory="' + esc(memory.id) + '">' + esc(I18N.t('writingVoice.forget')) + '</button></div></li>';
  }).join('') : '<li class="voice-empty"><h3>' + esc(I18N.t('writingVoice.empty.title')) + '</h3>' +
   '<p>' + esc(I18N.t('writingVoice.empty.body')) + '</p></li>';
  dialog.querySelector('[data-undo-voice]').hidden = !undoId;
  dialog.querySelector('[data-retry-voice]').hidden = !pending;
  dialog.querySelectorAll('[data-forget-memory],[data-correct-memory],[data-undo-voice],[data-retry-voice]')
   .forEach(button => { button.disabled = busy || Boolean(pending && !button.hasAttribute('data-retry-voice')); });
 }

 async function load() {
  data = await fetch('/writing-voice', { cache: 'no-store' }).then(reply);
  if (undoId && !data.forgotten_ids.includes(undoId)) undoId = null;
  render();
 }

 async function changeMemory(id, forgotten) {
  if (busy) return;
  pending = pending || { revision: data.revision, request_id: crypto.randomUUID(), memory_id: id, forgotten };
  busy = true;
  render();
  message(forgotten ? I18N.t('writingVoice.status.forgetting') : I18N.t('writingVoice.status.restoring'));
  try {
   data = await fetch('/writing-memory-forget', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Studio-Action': 'writing-memory-forget' },
    body: JSON.stringify(pending)
   }).then(reply);
   undoId = forgotten ? id : null;
   pending = null;
   message(forgotten ? I18N.t('writingVoice.status.forgotten') : I18N.t('writingVoice.status.restored'));
  } catch (error) {
   message(error.message + ' ' + I18N.t('writingVoice.status.retryHint'));
  } finally {
   busy = false;
   render();
   if (dialog.open) dialog.querySelector(undoId ? '[data-undo-voice]' : '[data-done-voice]').focus();
  }
 }

 async function correctInChat(id) {
  const memory = data.preferences.find(item => item.id === id);
  if (!memory) return;
  const url = new URL(location.href);
  url.hash = new URLSearchParams({ 'writing-memory': id, 'memory-revision': data.revision }).toString();
  const text = I18N.t('writingVoice.correctRequest') + '\n' + url.href + '\n\n' + memory.text;
  const fallback = dialog.querySelector('[data-memory-copy]');
  fallback.hidden = true;
  try {
   await navigator.clipboard.writeText(text);
   message(I18N.t('writingVoice.status.copied'));
  } catch {
   fallback.value = text;
   fallback.hidden = false;
   fallback.focus();
   fallback.select();
   message(I18N.t('writingVoice.status.copyManually'));
  }
 }

 function mount() {
  if (dialog) return;
  dialog = document.createElement('dialog');
  dialog.className = 'writing-voice-dialog';
  dialog.setAttribute('aria-labelledby', 'writing-voice-title');
  dialog.innerHTML = '<div class="project-start-head"><div><p class="eyebrow">' + esc(I18N.t('writingVoice.eyebrow')) + '</p>' +
   '<h2 id="writing-voice-title" tabindex="-1">' + esc(I18N.t('writingVoice.title')) + '</h2>' +
   '<p>' + esc(I18N.t('writingVoice.intro')) + '</p></div>' +
   '<button class="close-button" data-close-voice aria-label="' + esc(I18N.t('writingVoice.closeAria')) + '">×</button></div>' +
   '<div class="voice-body"><ul data-voice-list></ul>' +
   '<textarea data-memory-copy readonly hidden aria-label="' + esc(I18N.t('dialog.brief.messageAria')) + '"></textarea></div>' +
   '<div class="project-start-foot"><div class="memory-status"><p data-voice-status role="status" aria-live="polite"></p>' +
   '<button class="text-button" data-undo-voice hidden>' + esc(I18N.t('library.undo.button')) + '</button>' +
   '<button class="text-button" data-retry-voice hidden>' + esc(I18N.t('writingVoice.retry')) + '</button></div>' +
   '<button class="primary" data-done-voice>' + esc(I18N.t('writingVoice.done')) + '</button></div>';
  document.body.append(dialog);
  const close = () => dialog.close();
  dialog.querySelector('[data-close-voice]').onclick = close;
  dialog.querySelector('[data-done-voice]').onclick = close;
  dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus(); });
  dialog.addEventListener('click', event => {
   const forget = event.target.closest('[data-forget-memory]');
   if (forget && !pending) changeMemory(forget.dataset.forgetMemory, true);
   const correct = event.target.closest('[data-correct-memory]');
   if (correct && !busy) correctInChat(correct.dataset.correctMemory);
  });
  dialog.querySelector('[data-undo-voice]').onclick = () => { if (!pending) changeMemory(undoId, false); };
  dialog.querySelector('[data-retry-voice]').onclick = () => {
   if (pending) changeMemory(pending.memory_id, pending.forgotten);
  };
 }

 async function open(button) {
  mount();
  opener = button;
  if (!dialog.open) dialog.showModal();
  dialog.querySelector('#writing-voice-title').focus();
  if (busy) return;
  pending = null;
  dialog.querySelector('[data-memory-copy]').hidden = true;
  message('');
  try { await load(); }
  catch (error) { message(error.message); }
 }

 document.addEventListener('click', event => {
  const button = event.target.closest('[data-writing-voice]');
  if (button) { event.preventDefault(); open(button); }
 });
 return { open };
})();
