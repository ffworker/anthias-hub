(() => {
  'use strict';
  const studio = document.querySelector('.playlist-studio-v2[data-can-edit="yes"]');
  if (!studio) return;

  const cards = Array.from(studio.querySelectorAll('.asset[data-asset-id]'));
  let expanded = null;

  function isUnsaved(card) {
    const form = card?.querySelector('.asset-inline-edit');
    if (!form || !form.dataset.savedValues) return false;
    const name = form.querySelector('[name="name"]')?.value || '';
    const duration = form.querySelector('.duration-number')?.value ?? null;
    return JSON.stringify([name, duration]) !== form.dataset.savedValues;
  }
  function restoreFields(card) {
    const form = card?.querySelector('.asset-inline-edit');
    if (!form?.dataset.savedValues) return;
    let values;
    try { values = JSON.parse(form.dataset.savedValues); } catch { return; }
    const name = form.querySelector('[name="name"]');
    const duration = form.querySelector('.duration-number');
    const range = form.querySelector('.duration-range');
    const output = form.querySelector('.duration-value');
    if (name) name.value = values[0];
    if (duration && values[1] !== null) {
      duration.value = values[1];
      if (range) range.value = String(Math.min(120, Math.max(5, Number(values[1]))));
      if (output) output.textContent = values[1] + ' Sek.';
    }
    const save = card.querySelector('.inline-save');
    if (save) {
      save.disabled = true;
      save.dataset.saveReady = 'false';
    }
  }
  function closeCard(card) {
    if (!card) return true;
    if (card.querySelector('.asset-inline-edit')?.dataset.pending === 'yes') return false;
    if (isUnsaved(card)) {
      if (!window.confirm('Ungespeicherte Änderungen verwerfen?')) return false;
      restoreFields(card);
    }
    const editor = card.querySelector('.asset-toolbar');
    const trigger = card.querySelector('.asset-open');
    if (editor) editor.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    card.classList.remove('is-expanded');
    if (expanded === card) expanded = null;
    return true;
  }
  function openCard(card) {
    if (expanded && expanded !== card && !closeCard(expanded)) return;
    const editor = card.querySelector('.asset-toolbar');
    const trigger = card.querySelector('.asset-open');
    if (!editor || !trigger) return;
    editor.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    card.classList.add('is-expanded');
    expanded = card;
    editor.querySelector('input[name="name"]')?.focus();
  }
  cards.forEach(card => {
    const editor = card.querySelector('.asset-toolbar');
    if (editor) editor.hidden = true;
    const trigger = card.querySelector('.asset-open');
    trigger?.addEventListener('click', () => {
      if (expanded === card) {
        if (closeCard(card)) trigger.focus();
      } else {
        openCard(card);
      }
    });
  });

  const drawer = studio.querySelector('[data-composer-drawer]');
  const backdrop = studio.querySelector('.composer-backdrop');
  const triggers = Array.from(studio.querySelectorAll('[data-open-composer]'));
  const closeButtons = Array.from(studio.querySelectorAll('[data-close-composer]'));
  let previousFocus = null;

  if (drawer && backdrop) {
    function hasUnsubmittedContent() {
      for (const field of drawer.querySelectorAll('input, textarea, select')) {
        if (field.type === 'hidden' || field.type === 'submit') continue;
        if (field.type === 'file' && field.files?.length) return true;
        if ((field.type === 'checkbox' || field.type === 'radio') &&
            field.checked !== field.defaultChecked) return true;
        if (field.type !== 'file' && field.type !== 'checkbox' && field.type !== 'radio' &&
            field.value !== field.defaultValue && field.value !== '') return true;
      }
      return false;
    }
    function openDrawer() {
      previousFocus = document.activeElement;
      drawer.inert = false;
      drawer.removeAttribute('aria-hidden');
      drawer.setAttribute('role', 'dialog');
      drawer.setAttribute('aria-modal', 'true');
      studio.classList.add('composer-is-open');
      backdrop.hidden = false;
      document.body.classList.add('studio-drawer-open');
      drawer.querySelector('[data-close-composer]')?.focus();
    }
    function closeDrawer(force = false) {
      if (!studio.classList.contains('composer-is-open')) return;
      if (!force && hasUnsubmittedContent() &&
          !window.confirm('Nicht übertragene Eingaben oder ausgewählte Dateien verwerfen?')) return;
      studio.classList.remove('composer-is-open');
      backdrop.hidden = true;
      document.body.classList.remove('studio-drawer-open');
      drawer.inert = true;
      drawer.setAttribute('aria-hidden', 'true');
      drawer.removeAttribute('aria-modal');
      drawer.removeAttribute('role');
      if (previousFocus?.isConnected) previousFocus.focus();
    }
    drawer.inert = true;
    drawer.setAttribute('aria-hidden', 'true');
    triggers.forEach(trigger => trigger.addEventListener('click', event => {
      event.preventDefault();
      openDrawer();
    }));
    closeButtons.forEach(button => button.addEventListener('click', () => closeDrawer()));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && studio.classList.contains('composer-is-open')) {
        event.preventDefault();
        closeDrawer();
        return;
      }
      if (event.key === 'Escape' && expanded &&
          !event.target.closest('.drag-handle')) {
        if (closeCard(expanded)) expanded.querySelector('.asset-open')?.focus();
      }
      if (event.key !== 'Tab' || !studio.classList.contains('composer-is-open')) return;
      const focusable = Array.from(drawer.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary'
      )).filter(el => el.getClientRects().length > 0 && !el.closest('[hidden]'));
      if (!focusable.length) {
        event.preventDefault();
        drawer.focus();
        return;
      }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
    if (window.location.hash === '#add-content') openDrawer();
  }
  // Only after all no-JS fallbacks are in place do we turn the sidebar into
  // an overlay and hide card editors. Without JS both remain usable on page.
  studio.classList.add('js-ready');
})();