/* Progressive enhancement for the Anthias Hub playlist.
 * The ordinary server-rendered controls still work without JavaScript.
 * Keep playlist writes sequential and never silently overwrite a stale order. */
(() => {
  'use strict';

  const workspace = document.querySelector('.playlist-workspace[data-can-edit="yes"]');
  if (!workspace) return;

  const queue = document.getElementById('playlist-queue');
  const stack = document.getElementById('playlist-items');
  const feedback = document.getElementById('playlist-feedback');
  const activeCount = document.getElementById('active-count');
  const sortStatus = document.getElementById('playlist-sort-status');
  const cards = () => Array.from(stack.querySelectorAll('.asset[data-asset-id]'));
  const ids = () => cards().map((card) => card.dataset.assetId);
  let reordering = false;
  let dragged = null;
  let toastTimer = null;
  let pointerDrag = null;
  let keyboardDrag = null;

  function notify(message, error = false) {
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle('is-error', error);
    feedback.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { feedback.hidden = true; }, error ? 8000 : 3200);
  }

  async function postForm(url, form) {
    const response = await fetch(url, {
      method: 'POST',
      body: form,
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    });
    const data = await response.json().catch(() => null);
    if (!data) throw new Error('Keine gültige Antwort. Bitte Anmeldung, Verbindung und Playlist prüfen.');
    if (!response.ok || !data.ok) throw new Error(data.error || 'Die Änderung konnte nicht gespeichert werden.');
    return data;
  }

  function updatePositions() {
    const all = cards();
    all.forEach((card, index) => {
      const label = card.querySelector('.asset-index');
      if (label) {
        label.textContent = String(index + 1).padStart(2, '0');
        label.setAttribute('aria-label', 'Position ' + (index + 1));
      }
      const handle = card.querySelector('.drag-handle');
      if (handle) {
        const name = card.querySelector('.asset-name')?.textContent || 'Inhalt';
        handle.setAttribute('aria-label', name + ' verschieben, Position ' +
          (index + 1) + ' von ' + all.length);
      }
    });
  }

  const editValue = (form) => JSON.stringify([
    form.querySelector('[name="name"]')?.value || '',
    form.querySelector('.duration-number')?.value ?? null
  ]);
  function refreshSave(card) {
    const form = card.querySelector('.asset-inline-edit');
    const button = card.querySelector('.asset-toolbar-actions .inline-save');
    if (!form || !button) return;
    const dirty = editValue(form) !== form.dataset.savedValues;
    button.disabled = !dirty || form.dataset.pending === 'yes';
    button.dataset.saveReady = String(dirty);
    button.title = dirty ? 'Änderungen speichern' : 'Keine ungespeicherten Änderungen';
  }
  function showSaved(card) {
    const indicator = card.querySelector('.save-indicator');
    if (!indicator) return;
    indicator.textContent = '✓ Gespeichert';
    indicator.classList.add('is-visible');
    window.clearTimeout(indicator._clearTimer);
    indicator._clearTimer = window.setTimeout(() => {
      indicator.textContent = '';
      indicator.classList.remove('is-visible');
    }, 2500);
  }
  cards().forEach((card) => {
    const form = card.querySelector('.asset-inline-edit');
    if (!form) return;
    form.dataset.savedValues = editValue(form);
    refreshSave(card);
  });

  function updateEnabled(card, enabled) {
    card.dataset.enabled = enabled ? '1' : '0';
    card.classList.toggle('is-paused', !enabled);
    const status = card.querySelector('.asset-status');
    if (status) {
      status.textContent = enabled ? 'Aktiv' : 'Pausiert';
      status.classList.toggle('ok', enabled);
      status.classList.toggle('off', !enabled);
    }
    const toggle = card.querySelector('.quick-toggle-form');
    if (toggle) {
      toggle.querySelector('[name="expected"]').value = enabled ? '1' : '0';
      toggle.querySelector('[name="enabled"]').value = enabled ? '0' : '1';
      const button = toggle.querySelector('button');
      const verb = enabled ? 'pausieren' : 'aktivieren';
      button.title = enabled ? 'Inhalt pausieren' : 'Inhalt aktivieren';
      button.setAttribute('aria-label', (card.querySelector('.asset-name')?.textContent || 'Inhalt') + ' ' + verb);
      button.querySelector('[aria-hidden="true"]').textContent = enabled ? 'Ⅱ' : '▶';
      button.querySelector('.quick-label').textContent = enabled ? 'Pausieren' : 'Aktivieren';
    }
    if (activeCount) activeCount.textContent = String(cards().filter((item) => item.dataset.enabled === '1').length);
  }

  // One-click pause/resume. If the API responds with a stale state, do not guess.
  stack.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const card = form.closest('.asset');
    if (!card) return;

    if (form.matches('.quick-toggle-form')) {
      event.preventDefault();
      if (form.dataset.pending === 'yes') return;
      form.dataset.pending = 'yes';
      const button = form.querySelector('button');
      button.disabled = true;
      try {
        const result = await postForm(form.action, new FormData(form));
        updateEnabled(card, result.enabled);
        notify(result.enabled ? 'Inhalt ist wieder aktiv ✓' : 'Inhalt ist pausiert ✓');
      } catch (error) {
        notify(error.message || 'Bitte die Seite neu laden.', true);
      } finally {
        button.disabled = false;
        delete form.dataset.pending;
      }
      return;
    }

    // Inline editing without leaving the card; HTML form is the no-JS fallback.
    if (form.matches('.asset-edit')) {
      event.preventDefault();
      if (form.dataset.pending === 'yes') return;
      // Capture what was actually sent. If a user edits more while the
      // request is in flight, those newer changes must remain unsaved.
      const submitted = editValue(form);
      form.dataset.pending = 'yes';
      const button = card.querySelector('.asset-toolbar-actions .inline-save');
      if (!button) { delete form.dataset.pending; return; }
      button.disabled = true;
      try {
        const result = await postForm(form.action, new FormData(form));
        const changes = result.asset;
        card.querySelector('.asset-name').textContent = changes.name;
        const duration = card.querySelector('.asset-duration');
        if (duration && Object.prototype.hasOwnProperty.call(changes, 'duration')) {
          duration.textContent = changes.duration + ' Sek.';
        }
        updateEnabled(card, changes.is_enabled);
        const preview = card.querySelector('[data-media-lightbox]');
        if (preview) {
          preview.dataset.previewTitle = changes.name;
          preview.setAttribute('aria-label', changes.name + ' groß ansehen');
        }
        form.dataset.savedValues = submitted;
        showSaved(card);
        updatePositions();
        notify('Änderungen gespeichert ✓');
      } catch (error) {
        notify(error.message || 'Änderung nicht gespeichert.', true);
      } finally {
        delete form.dataset.pending;
        refreshSave(card);
      }
    }
  });

  // The short-range slider is precise for everyday durations (5–120 s).
  // The number field is the *only* submitted value and supports 5–3600 s.
  // Changing either control updates the other without clamping manual values.
  // Both remain local until the user presses Save.
  stack.addEventListener('input', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const container = input.closest('.inline-edit-duration');
    if (!container) return;
    const slider = container.querySelector('.duration-range');
    const number = container.querySelector('.duration-number');
    const output = container.querySelector('.duration-value');
    if (!slider || !number || !output) return;
    if (input === slider) {
      number.value = slider.value;
      output.textContent = slider.value + ' Sek.';
    } else if (input === number) {
      const seconds = Number(number.value);
      if (!number.value || !Number.isFinite(seconds)) {
        output.textContent = '– Sek.';
      } else {
        slider.value = String(Math.max(5, Math.min(120, seconds)));
        output.textContent = number.value + ' Sek.';
      }
    }
    refreshSave(input.closest('.asset'));
  });
  stack.addEventListener('input', (event) => {
    if (event.target.matches('.asset-inline-edit input[name="name"]')) {
      refreshSave(event.target.closest('.asset'));
    }
  });

  // Media and reusable library content are the common path for Marketing.
  // Website is an available but visually secondary option. With no JS, all
  // forms remain accessible; this only chooses the initial enhanced view.
  const modeButtons = Array.from(document.querySelectorAll('[data-add-mode]'));
  const panes = Array.from(document.querySelectorAll('[data-add-pane]'));
  function selectMode(mode) {
    for (const button of modeButtons) {
      const chosen = button.dataset.addMode === mode;
      button.classList.toggle('selected', chosen);
      button.setAttribute('aria-pressed', String(chosen));
    }
    for (const pane of panes) pane.hidden = pane.dataset.addPane !== mode;
  }
  modeButtons.forEach((button) => button.addEventListener('click', () => selectMode(button.dataset.addMode)));
  if (modeButtons.length) selectMode('media');

  // All sorting input methods share one server commit: IDs + optimistic
  // baseline. On error, restore the original DOM and visible positions.
  function announceSort(message) {
    if (sortStatus) sortStatus.textContent = message;
  }
  const snapshot = () => cards();
  const sameOrder = (before, after) =>
    before.length === after.length &&
    before.every((card, index) => card.dataset.assetId === after[index]);
  function clearMarks() {
    cards().forEach((card) =>
      card.classList.remove('is-dragging', 'is-keyboard-grabbed', 'drop-before', 'drop-after'));
    dragged = null;
  }
  function restoreOrder(before) {
    before.forEach((card) => stack.appendChild(card));
    updatePositions();
  }
  function lockSort(busy) {
    reordering = busy;
    stack.querySelectorAll('.drag-handle').forEach((grip) => {
      grip.setAttribute('aria-disabled', String(busy));
    });
    stack.classList.toggle('is-reordering', busy);
  }
  async function commitOrder(before) {
    const after = cards();
    if (sameOrder(before, after.map((card) => card.dataset.assetId))) {
      clearMarks();
      updatePositions();
      announceSort('Reihenfolge unverändert.');
      return;
    }
    const payload = new FormData();
    payload.append('csrf', queue.dataset.csrf);
    before.forEach((card) => payload.append('baseline', card.dataset.assetId));
    after.forEach((card) => payload.append('ids', card.dataset.assetId));
    clearMarks();
    updatePositions();
    lockSort(true);
    announceSort('Neue Reihenfolge wird gespeichert …');
    try {
      await postForm(queue.dataset.reorderUrl, payload);
      announceSort('Neue Reihenfolge gespeichert.');
      notify('Neue Reihenfolge gespeichert ✓');
    } catch (error) {
      restoreOrder(before);
      announceSort('Sortieren fehlgeschlagen. Ursprüngliche Reihenfolge wiederhergestellt.');
      notify((error.message || 'Sortierung nicht gespeichert.') +
        ' Die Ansicht wurde zurückgesetzt.', true);
    } finally {
      lockSort(false);
    }
  }

  function hint(target, after) {
    cards().forEach((card) => card.classList.remove('drop-before', 'drop-after'));
    if (target) target.classList.add(after ? 'drop-after' : 'drop-before');
  }
  function targetAt(y, source) {
    const rect = stack.getBoundingClientRect();
    if (y < rect.top - 25 || y > rect.bottom + 25) return null;
    const others = cards().filter((card) => card !== source);
    if (!others.length) return null;
    let best = null;
    let distance = Infinity;
    others.forEach((card) => {
      const r = card.getBoundingClientRect();
      const middle = r.top + r.height / 2;
      if (Math.abs(middle - y) < distance) {
        distance = Math.abs(middle - y);
        best = { card, after: y >= middle };
      }
    });
    return best;
  }

  // Mouse: native HTML drag-and-drop, sourced exclusively from the grip.
  stack.querySelectorAll('.drag-handle').forEach((handle) => {
    handle.addEventListener('dragstart', (event) => {
      if (reordering || pointerDrag || keyboardDrag || !event.dataTransfer) {
        event.preventDefault();
        return;
      }
      dragged = handle.closest('.asset');
      if (!dragged) { event.preventDefault(); return; }
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', dragged.dataset.assetId);
      dragged.classList.add('is-dragging');
      announceSort('Inhalt wird verschoben.');
    });
    handle.addEventListener('dragend', () => { if (!reordering) clearMarks(); });
  });
  stack.addEventListener('dragover', (event) => {
    if (!dragged || reordering) return;
    const target = event.target.closest('.asset');
    if (!target || target === dragged) { hint(null); return; }
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    const rect = target.getBoundingClientRect();
    hint(target, event.clientY > rect.top + rect.height / 2);
  });
  stack.addEventListener('drop', (event) => {
    if (!dragged || reordering) return;
    event.preventDefault();
    const source = dragged;
    const candidate = targetAt(event.clientY, source);
    if (!candidate) { clearMarks(); return; }
    const before = snapshot();
    stack.insertBefore(source, candidate.after ? candidate.card.nextSibling : candidate.card);
    void commitOrder(before);
  });

  // Touch / pen: native HTML DnD is unreliable in mobile browsers, so use
  // Pointer Events only on the grip. Tapping without moving does nothing.
  stack.addEventListener('pointerdown', (event) => {
    if (!['touch', 'pen'].includes(event.pointerType) || !event.isPrimary ||
        reordering || keyboardDrag || pointerDrag) return;
    const handle = event.target.closest('.drag-handle');
    if (!handle) return;
    const source = handle.closest('.asset');
    if (!source) return;
    handle.draggable = false; // avoid duplicate native dragstart on long press
    pointerDrag = { id: event.pointerId, handle, source,
                    startX: event.clientX, startY: event.clientY,
                    before: snapshot(), moved: false, target: null };
    handle.setPointerCapture?.(event.pointerId);
  });
  stack.addEventListener('pointermove', (event) => {
    const state = pointerDrag;
    if (!state || state.id !== event.pointerId) return;
    if (!state.moved && Math.hypot(event.clientX - state.startX,
                                   event.clientY - state.startY) < 8) return;
    state.moved = true;
    state.source.classList.add('is-dragging');
    event.preventDefault();
    const best = targetAt(event.clientY, state.source);
    state.target = best;
    hint(best?.card, best?.after);
    // Move the viewport near the edges for long playlists.
    if (event.clientY < 58) window.scrollBy(0, -14);
    else if (event.clientY > window.innerHeight - 58) window.scrollBy(0, 14);
  });
  function endPointer(event, canceled) {
    const state = pointerDrag;
    if (!state || state.id !== event.pointerId) return;
    pointerDrag = null;
    state.handle.draggable = true;
    if (state.handle.hasPointerCapture?.(event.pointerId)) {
      state.handle.releasePointerCapture(event.pointerId);
    }
    if (canceled || !state.moved || !state.target) {
      clearMarks();
      if (canceled) announceSort('Verschieben abgebrochen.');
      return;
    }
    const { source, target, before } = state;
    stack.insertBefore(source, target.after ? target.card.nextSibling : target.card);
    void commitOrder(before);
  }
  stack.addEventListener('pointerup', (event) => endPointer(event, false));
  stack.addEventListener('pointercancel', (event) => endPointer(event, true));

  // Keyboard: Space picks up a focused grip; arrows move one position.
  // Enter/Space saves; Escape restores the original position without writing.
  stack.addEventListener('keydown', (event) => {
    const grip = event.target.closest('.drag-handle');
    if (!grip || reordering || pointerDrag || dragged) return;
    const key = event.key;
    if (keyboardDrag && keyboardDrag.handle !== grip) return;
    if (key === ' ' || key === 'Spacebar' || key === 'Enter') {
      event.preventDefault();
      if (!keyboardDrag) {
        const source = grip.closest('.asset');
        keyboardDrag = { handle: grip, source, before: snapshot(), moving: false };
        source.classList.add('is-keyboard-grabbed');
        grip.setAttribute('aria-pressed', 'true');
        announceSort('Aufgenommen. Pfeiltasten verschieben, Enter legt ab, Esc bricht ab.');
      } else {
        const { before } = keyboardDrag;
        keyboardDrag = null;
        grip.setAttribute('aria-pressed', 'false');
        void commitOrder(before);
        grip.focus();
      }
      return;
    }
    if (!keyboardDrag) return;
    if (key === 'Escape' || key === 'Tab') {
      if (key === 'Escape') event.preventDefault();
      const { before } = keyboardDrag;
      keyboardDrag = null;
      grip.setAttribute('aria-pressed', 'false');
      clearMarks();
      restoreOrder(before);
      announceSort('Verschieben abgebrochen; Reihenfolge unverändert.');
      if (key === 'Escape') grip.focus();
      return;
    }
    if (key !== 'ArrowUp' && key !== 'ArrowDown') return;
    event.preventDefault();
    const { source } = keyboardDrag;
    const all = cards();
    const index = all.indexOf(source);
    keyboardDrag.moving = true;
    if (key === 'ArrowUp' && index > 0) {
      stack.insertBefore(source, all[index - 1]);
    } else if (key === 'ArrowDown' && index < all.length - 1) {
      stack.insertBefore(source, all[index + 1].nextSibling);
    }
    updatePositions();
    grip.focus(); // Moving a focused DOM node can otherwise lose focus.
    keyboardDrag.moving = false;
    announceSort((source.querySelector('.asset-name')?.textContent || 'Inhalt') +
      ' auf Position ' + (cards().indexOf(source) + 1) + ' von ' + cards().length + '.');
  });
  stack.addEventListener('focusout', (event) => {
    if (!keyboardDrag || keyboardDrag.moving || event.target !== keyboardDrag.handle) return;
    // Don't leave a hidden, unsaved keyboard preview behind when tabbing out.
    const { before, handle } = keyboardDrag;
    keyboardDrag = null;
    handle.setAttribute('aria-pressed', 'false');
    clearMarks();
    restoreOrder(before);
    announceSort('Verschieben abgebrochen.');
  });

  // The browser validates the checkbox even if JavaScript is disabled.
  stack.querySelectorAll('.delete-panel form').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm('Diesen Inhalt wirklich endgültig vom Player entfernen?')) {
        event.preventDefault();
      }
    });
  });
})();
