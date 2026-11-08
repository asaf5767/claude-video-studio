/* Task 9: the "your materials" tile grid on the project page -- upload (drag-and-drop
   or file picker), tag, note and claim ownership of raw footage, B-roll, images, logos,
   music and SFX, plus adding from the personal library. Consumes Task 8's routes
   (PUT/GET /materials, POST /material-update, POST /material-from-library,
   GET /material-library, GET /project-materials/<project>/<item>).
   Built with document.createElement rather than innerHTML strings for the tile grid: each
   tile keeps direct references to its own controls (thumbnail/select/note/checkbox/status),
   so a tag change, a debounced note save or an upload progress tick only ever touches that
   one tile -- never a full-grid rerender that would drop focus or restart a progress bar. */
window.MaterialsUI = (() => {
  const VIDEO_EXT = new Set(['.mp4', '.mov', '.webm', '.m4v']);
  const IMAGE_EXT = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif']);
  const TAGS = ['raw', 'broll', 'screen', 'image', 'logo', 'music', 'voice', 'sfx'];
  const TAG_LABEL_KEY = {raw: 'materials.tag.raw', broll: 'materials.tag.broll', screen: 'materials.tag.screen',
    image: 'materials.tag.image', logo: 'materials.tag.logo', music: 'materials.tag.music', voice: 'materials.tag.voice', sfx: 'materials.tag.sfx'};
  const NOTE_SAVE_DELAY = 600;

  function extOf(name) {
    const text = String(name ?? '');
    const i = text.lastIndexOf('.');
    return i === -1 ? '' : text.slice(i).toLowerCase();
  }

  // Mirrors materials.py's _auto_tag(): a video is the project's first raw take, every
  // later video is B-roll; an image is just an image; anything else allowed (audio) is
  // music. Exposed so a freshly-dropped file can show the right tag immediately, before
  // the server's own answer comes back.
  function tagFor(filename, hasRaw) {
    const ext = extOf(filename);
    if (VIDEO_EXT.has(ext)) return hasRaw ? 'broll' : 'raw';
    if (IMAGE_EXT.has(ext)) return 'image';
    return 'music';
  }

  function kindOf(filename) {
    const ext = extOf(filename);
    if (VIDEO_EXT.has(ext)) return 'video';
    if (IMAGE_EXT.has(ext)) return 'image';
    return 'audio';
  }

  function isAsciiName(name) { return /^[\x00-\x7F]*$/.test(String(name ?? '')); }

  function fileUrl(projectId, item) {
    return '/project-materials/' + encodeURIComponent(projectId) + '/' + encodeURIComponent(item.id);
  }

  let run = 0;

  function mount(el, projectId) {
    const token = ++run;
    const state = {items: [], hasRaw: false};
    let libraryPanel = null;

    const section = document.createElement('section');
    section.className = 'materials-section';
    section.setAttribute('aria-label', I18N.t('materials.sectionAria'));

    const head = document.createElement('div');
    head.className = 'materials-head';
    const heading = document.createElement('h2');
    heading.textContent = I18N.t('materials.title');
    const count = document.createElement('span');
    count.className = 'materials-count';
    const libraryButton = document.createElement('button');
    libraryButton.type = 'button';
    libraryButton.className = 'secondary materials-library-button';
    libraryButton.textContent = I18N.t('materials.addFromLibrary');
    head.append(heading, count, libraryButton);

    const status = document.createElement('p');
    status.className = 'materials-status';
    status.setAttribute('role', 'status');

    const grid = document.createElement('div');
    grid.className = 'materials-grid';

    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.multiple = true;
    fileInput.hidden = true;
    fileInput.accept = 'video/*,image/*,audio/*';

    const dropTile = document.createElement('button');
    dropTile.type = 'button';
    dropTile.className = 'material-tile material-drop';
    const dropTitle = document.createElement('div');
    dropTitle.className = 'material-drop-title';
    dropTitle.textContent = I18N.t('materials.drop.title');
    const dropHint = document.createElement('div');
    dropHint.className = 'material-drop-hint';
    dropHint.textContent = I18N.t('materials.drop.hint');
    dropTile.append(dropTitle, dropHint);

    grid.append(dropTile);
    section.append(head, status, grid, fileInput);
    el.innerHTML = '';
    el.append(section);

    function updateCount() {
      const n = state.items.length;
      count.textContent = n === 1 ? I18N.t('materials.count.one') : I18N.t('materials.count.many', {n});
    }

    function recomputeHasRaw() { state.hasRaw = state.items.some(i => i.tag === 'raw'); }

    async function patch(itemId, body, statusEl) {
      try {
        const response = await fetch('/material-update', {
          method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'material-update'},
          body: JSON.stringify({project: projectId, item: itemId, ...body}),
        });
        let result = null;
        try { result = await response.json(); } catch { /* fall through to the generic message below */ }
        if (!response.ok) throw Error(I18N.t(result?.error || 'materials.saveError'));
        if (statusEl) statusEl.textContent = '';
        return result;
      } catch (error) {
        if (statusEl) statusEl.textContent = error instanceof TypeError ? I18N.t('materials.saveError') : error.message;
        throw error;
      }
    }

    // Swaps `oldNode` for `newNode` among its own siblings. Not Element.replaceWith(): the
    // vm-sandbox fake DOM test_materials_ui.js uses only implements append/insertBefore/
    // remove, and this reads the same in a real browser.
    function replaceNode(oldNode, newNode) {
      if (!oldNode.parentNode) return;
      oldNode.parentNode.insertBefore(newNode, oldNode);
      oldNode.remove();
    }

    function videoPlaceholder() {
      const icon = document.createElement('div');
      icon.className = 'material-thumb material-thumb-video-pending';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '▶';
      return icon;
    }

    function buildThumb(item) {
      const kind = kindOf(item.file || '');
      if (kind === 'image') {
        const img = document.createElement('img');
        img.className = 'material-thumb';
        img.loading = 'lazy';
        img.alt = '';
        img.src = fileUrl(projectId, item);
        return img;
      }
      if (kind === 'video') {
        // T9b: a server-generated poster <img> instead of <video preload="metadata"> --
        // HEVC/HLG video shot on an iPhone renders a BLACK frame there in Chrome on
        // Windows, which can't decode it, where the poster (tone-mapped to SDR, generated
        // with ffmpeg) always shows a real frame. While the poster isn't ready yet (first
        // request, still generating) or ffmpeg couldn't produce one at all, the ?poster=1
        // request 404s and the img's error event swaps in a plain film-strip placeholder.
        // The tile stays clickable either way: it's a link that opens the actual video.
        const link = document.createElement('a');
        link.className = 'material-thumb-link';
        link.href = fileUrl(projectId, item);
        link.target = '_blank';
        link.rel = 'noopener';
        link.setAttribute('aria-label', I18N.t('materials.video.openAria'));
        const img = document.createElement('img');
        img.className = 'material-thumb';
        img.loading = 'lazy';
        img.alt = '';
        img.src = fileUrl(projectId, item) + '?poster=1';
        img.addEventListener('error', () => replaceNode(img, videoPlaceholder()), {once: true});
        link.append(img);
        return link;
      }
      const icon = document.createElement('div');
      icon.className = 'material-thumb material-thumb-audio';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = '♪';
      return icon;
    }

    function buildTile(item) {
      const tile = document.createElement('div');
      tile.className = 'material-tile';
      tile.dataset.itemId = item.id;

      tile.append(buildThumb(item));

      const meta = document.createElement('div');
      meta.className = 'material-meta';

      const name = document.createElement('b');
      name.className = 'material-name';
      const bdi = document.createElement('bdi');
      const filename = (item.file || '').split('/').pop();
      bdi.textContent = filename;
      if (isAsciiName(filename)) bdi.setAttribute('dir', 'ltr');
      name.append(bdi);

      const tagSelect = document.createElement('select');
      tagSelect.className = 'material-tag';
      tagSelect.setAttribute('aria-label', I18N.t('materials.tag.aria'));
      for (const tag of TAGS) {
        const option = document.createElement('option');
        option.value = tag;
        option.textContent = I18N.t(TAG_LABEL_KEY[tag]);
        tagSelect.append(option);
      }
      tagSelect.value = item.tag;

      const noteField = document.createElement('textarea');
      noteField.className = 'material-note';
      noteField.maxLength = 300;
      noteField.setAttribute('placeholder', I18N.t('materials.notePlaceholder'));
      noteField.value = item.note || '';

      const ownedLabel = document.createElement('label');
      ownedLabel.className = 'material-owned';
      const ownedCheckbox = document.createElement('input');
      ownedCheckbox.type = 'checkbox';
      ownedCheckbox.checked = !!item.owned;
      const ownedText = document.createElement('span');
      ownedText.textContent = I18N.t('materials.ownedLabel');
      ownedLabel.append(ownedCheckbox, ownedText);

      const tileStatus = document.createElement('p');
      tileStatus.className = 'material-tile-status';
      tileStatus.setAttribute('role', 'status');

      meta.append(name, tagSelect, noteField, ownedLabel, tileStatus);
      tile.append(meta);

      tagSelect.addEventListener('change', () => { patch(item.id, {tag: tagSelect.value}, tileStatus).then(r => { if (r) item.tag = r.tag; recomputeHasRaw(); }).catch(() => {}); });
      ownedCheckbox.addEventListener('change', () => { patch(item.id, {owned: ownedCheckbox.checked}, tileStatus).then(r => { if (r) item.owned = r.owned; }).catch(() => {}); });
      noteField.addEventListener('input', () => {
        clearTimeout(tile._noteTimer);
        tile._noteTimer = setTimeout(() => { patch(item.id, {note: noteField.value}, tileStatus).then(r => { if (r) item.note = r.note; }).catch(() => {}); }, NOTE_SAVE_DELAY);
      });

      tile._status = tileStatus;
      return tile;
    }

    function addSettledTile(item) {
      state.items.push(item);
      recomputeHasRaw();
      grid.insertBefore(buildTile(item), dropTile);
      updateCount();
    }

    function buildUploadingTile(file) {
      const tile = document.createElement('div');
      tile.className = 'material-tile material-tile-uploading';
      const name = document.createElement('b');
      name.className = 'material-name';
      const bdi = document.createElement('bdi');
      bdi.textContent = file.name;
      if (isAsciiName(file.name)) bdi.setAttribute('dir', 'ltr');
      name.append(bdi);
      const track = document.createElement('div');
      track.className = 'material-progress-track';
      const bar = document.createElement('div');
      bar.className = 'material-progress-bar';
      bar.setAttribute('aria-label', I18N.t('materials.upload.progressAria', {name: file.name}));
      track.append(bar);
      const tileStatus = document.createElement('p');
      tileStatus.className = 'material-tile-status';
      tileStatus.setAttribute('role', 'status');
      tile.append(name, track, tileStatus);
      tile._bar = bar;
      tile._status = tileStatus;
      return tile;
    }

    function uploadOne(file) {
      const tile = buildUploadingTile(file);
      grid.insertBefore(tile, dropTile);
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = event => {
        if (event.lengthComputable) tile._bar.style.width = Math.round((event.loaded / event.total) * 100) + '%';
      };
      xhr.onload = () => {
        if (xhr.status === 201) {
          let item;
          try { item = JSON.parse(xhr.responseText); } catch { tile._status.textContent = I18N.t('materials.error.filesystem'); return; }
          tile.remove();
          addSettledTile(item);
          return;
        }
        let key = 'materials.error.filesystem';
        try { key = JSON.parse(xhr.responseText).error || key; } catch { /* keep the generic key */ }
        tile._status.textContent = I18N.t(key);
      };
      xhr.onerror = () => { tile._status.textContent = I18N.t('materials.loadError'); };
      xhr.open('PUT', '/materials?' + new URLSearchParams({project: projectId, name: file.name}));
      xhr.setRequestHeader('X-Studio-Action', 'materials');
      xhr.send(file);
    }

    function handleFiles(files) {
      // One request per file (brief): a later file's progress/error never blocks an
      // earlier one, since each gets its own XHR and its own tile.
      Array.from(files || []).forEach(uploadOne);
    }

    fileInput.addEventListener('change', () => { handleFiles(fileInput.files); fileInput.value = ''; });
    dropTile.addEventListener('click', () => fileInput.click());
    dropTile.addEventListener('dragover', event => { event.preventDefault(); dropTile.classList.add('drag-over'); });
    dropTile.addEventListener('dragleave', () => dropTile.classList.remove('drag-over'));
    dropTile.addEventListener('drop', event => {
      event.preventDefault();
      dropTile.classList.remove('drag-over');
      handleFiles(event.dataTransfer && event.dataTransfer.files);
    });

    function closeLibraryPanel() { if (libraryPanel) { libraryPanel.remove(); libraryPanel = null; } }

    async function openLibraryPanel() {
      if (libraryPanel) { closeLibraryPanel(); return; }
      const panel = document.createElement('div');
      panel.className = 'materials-library-panel';
      const title = document.createElement('h3');
      title.textContent = I18N.t('materials.library.title');
      const closeButton = document.createElement('button');
      closeButton.type = 'button';
      closeButton.className = 'close-button';
      closeButton.setAttribute('aria-label', I18N.t('materials.library.closeAria'));
      closeButton.textContent = '×';
      closeButton.addEventListener('click', closeLibraryPanel);
      const list = document.createElement('div');
      list.className = 'materials-library-list';
      panel.append(title, closeButton, list);
      section.append(panel);
      libraryPanel = panel;
      try {
        const response = await fetch('/material-library', {cache: 'no-store'});
        const data = await response.json();
        if (!response.ok) throw Error(I18N.t('materials.library.loadError'));
        if (!data.items.length) {
          const empty = document.createElement('p');
          empty.textContent = I18N.t('materials.library.empty');
          list.append(empty);
          return;
        }
        for (const libraryItem of data.items) {
          const row = document.createElement('div');
          row.className = 'materials-library-item';
          const rowName = document.createElement('bdi');
          rowName.textContent = (libraryItem.file || '').split('/').pop();
          const addButton = document.createElement('button');
          addButton.type = 'button';
          addButton.className = 'secondary';
          addButton.textContent = I18N.t('materials.library.add');
          addButton.setAttribute('aria-label', I18N.t('materials.library.addAria', {title: rowName.textContent}));
          const rowStatus = document.createElement('span');
          rowStatus.className = 'material-tile-status';
          addButton.addEventListener('click', async () => {
            addButton.disabled = true;
            try {
              const addResponse = await fetch('/material-from-library', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Action': 'material-from-library'},
                body: JSON.stringify({project: projectId, item: libraryItem.id}),
              });
              const added = await addResponse.json();
              if (!addResponse.ok) throw Error(I18N.t(added.error || 'materials.saveError'));
              addSettledTile(added);
              closeLibraryPanel();
            } catch (error) {
              addButton.disabled = false;
              rowStatus.textContent = error instanceof TypeError ? I18N.t('materials.saveError') : error.message;
            }
          });
          row.append(rowName, addButton, rowStatus);
          list.append(row);
        }
      } catch {
        const error = document.createElement('p');
        error.textContent = I18N.t('materials.library.loadError');
        list.append(error);
      }
    }

    libraryButton.addEventListener('click', openLibraryPanel);

    async function load() {
      try {
        const response = await fetch('/materials?' + new URLSearchParams({project: projectId}), {cache: 'no-store'});
        if (!response.ok || token !== run || !el.isConnected) return;
        const data = await response.json();
        if (token !== run || !el.isConnected) return;
        state.items = [];
        for (const item of data.items) addSettledTile(item);
      } catch {
        if (token === run && el.isConnected) status.textContent = I18N.t('materials.loadError');
      }
    }

    updateCount();
    load();
    return {refresh: load};
  }

  return {mount, tagFor};
})();
