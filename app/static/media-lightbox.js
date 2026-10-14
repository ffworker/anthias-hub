/* Read-only preview dialog shared by device playlists and the local library. */
(() => {
  'use strict';
  if (!document.querySelector('[data-media-lightbox]') || !('HTMLDialogElement' in window)) return;

  const dialog = document.createElement('dialog');
  dialog.className = 'media-lightbox';
  dialog.setAttribute('aria-labelledby', 'media-lightbox-title');
  dialog.innerHTML = '<div class="media-lightbox-panel">'
    + '<header class="media-lightbox-head"><h2 id="media-lightbox-title"></h2>'
    + '<button class="media-lightbox-close" type="button" aria-label="Vorschau schließen">✕</button></header>'
    + '<div class="media-lightbox-stage"></div><p class="media-lightbox-note" role="status"></p></div>';
  document.body.appendChild(dialog);
  const title = dialog.querySelector('h2');
  const stage = dialog.querySelector('.media-lightbox-stage');
  const note = dialog.querySelector('.media-lightbox-note');
  const closeButton = dialog.querySelector('.media-lightbox-close');
  let previousFocus = null;

  function close() { dialog.close(); }
  closeButton.addEventListener('click', close);
  dialog.addEventListener('click', (event) => {
    // Only clicks outside the panel should close the modal.
    if (event.target === dialog) close();
  });
  dialog.addEventListener('close', () => {
    const video = stage.querySelector('video');
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
    stage.replaceChildren();
    note.textContent = '';
    if (previousFocus?.isConnected) previousFocus.focus();
    previousFocus = null;
  });
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-media-lightbox]');
    if (!trigger || dialog.open) return;
    const src = trigger.dataset.previewUrl;
    const type = trigger.dataset.previewType;
    // URLs are emitted by Flask's url_for(), never arbitrary playlist URIs.
    if (!src || !src.startsWith('/') || src.startsWith('//') || !['image', 'video'].includes(type)) return;
    previousFocus = trigger;
    title.textContent = trigger.dataset.previewTitle || 'Medienvorschau';
    note.textContent = type === 'video'
      ? 'Video wird nur hier in der Vorschau abgespielt, nicht auf dem Fernseher.'
      : 'Dateivorschau – kein Livebild vom Fernseher.';
    stage.replaceChildren();
    const element = document.createElement(type === 'image' ? 'img' : 'video');
    element.className = 'media-lightbox-media';
    if (type === 'image') {
      element.alt = trigger.dataset.previewTitle || 'Bildvorschau';
      element.addEventListener('error', () => {
        note.textContent = 'Vorschau nicht verfügbar. Bitte die Verbindung zum Player prüfen.';
      });
    } else {
      element.controls = true;
      element.playsInline = true;
      element.preload = 'metadata';
      element.addEventListener('error', () => {
        note.textContent = 'Video-Vorschau nicht verfügbar oder Format wird nicht unterstützt.';
      });
    }
    element.src = src;
    stage.appendChild(element);
    dialog.showModal();
    closeButton.focus();
  });
})();
