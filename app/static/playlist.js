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
  const cards = () => Array.from(stack.querySelectorAll('.asset[data-asset-id]'));
  const ids = () => cards().map((card) => card.dataset.assetId);
  let reordering = false;
  let dragged = null;
  let toastTimer = null;

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
      const buttons = card.querySelectorAll('.move-controls button');
      if (buttons.length === 2) {
        buttons[0].disabled = index === 0;
        buttons[1].disabled = index === all.length - 1;
      }
    });
  }

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
    const editState = card.querySelector('.asset-inline-edit [name="enabled"]');
    if (editState) editState.value = enabled ? 'on' : 'off';
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
      form.dataset.pending = 'yes';
      // The Save button lives beside Delete, but submits this edit form
      // through its HTML form attribute (including without JavaScript).
      const button = card.querySelector('.asset-toolbar-actions .inline-save');
      if (!button) return;
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
        notify('Titel und Dauer gespeichert ✓');
      } catch (error) {
        notify(error.message || 'Änderung nicht gespeichert.', true);
      } finally {
        button.disabled = false;
        delete form.dataset.pending;
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
        return;
      }
      slider.value = String(Math.max(5, Math.min(120, seconds)));
      output.textContent = number.value + ' Sek.';
    }
  });

  // Make website and upload equally discoverable; no-JS users still see both forms.
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
  if (modeButtons.length) selectMode('website');

  // Drag by the grip only. Touch/keyboard always retain the ↑ ↓ POST controls.
  const clearDrag = () => {
    cards().forEach((card) => card.classList.remove('is-dragging', 'drop-before', 'drop-after'));
    dragged = null;
  };
  stack.querySelectorAll('.drag-handle').forEach((handle) => {
    handle.addEventListener('dragstart', (event) => {
      if (reordering) { event.preventDefault(); return; }
      dragged = handle.closest('.asset');
      if (!dragged) { event.preventDefault(); return; }
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', dragged.dataset.assetId);
      dragged.classList.add('is-dragging');
    });
    handle.addEventListener('dragend', clearDrag);
  });

  stack.addEventListener('dragover', (event) => {
    if (!dragged || reordering) return;
    const target = event.target.closest('.asset');
    if (!target || target === dragged) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    cards().forEach((card) => card.classList.remove('drop-before', 'drop-after'));
    const below = event.clientY > target.getBoundingClientRect().top + target.getBoundingClientRect().height / 2;
    target.classList.add(below ? 'drop-after' : 'drop-before');
  });

  stack.addEventListener('drop', async (event) => {
    if (!dragged || reordering) return;
    const target = event.target.closest('.asset');
    if (!target || target === dragged) { clearDrag(); return; }
    event.preventDefault();
    const previous = cards();
    const baseline = previous.map((card) => card.dataset.assetId);
    const below = event.clientY > target.getBoundingClientRect().top + target.getBoundingClientRect().height / 2;
    stack.insertBefore(dragged, below ? target.nextSibling : target);
    const wanted = ids();
    clearDrag();
    updatePositions();
    if (wanted.every((id, index) => id === baseline[index])) return;
    reordering = true;
    const payload = new FormData();
    payload.append('csrf', queue.dataset.csrf);
    baseline.forEach((id) => payload.append('baseline', id));
    wanted.forEach((id) => payload.append('ids', id));
    try {
      await postForm(queue.dataset.reorderUrl, payload);
      notify('Neue Reihenfolge gespeichert ✓');
    } catch (error) {
      previous.forEach((card) => stack.appendChild(card));
      updatePositions();
      notify((error.message || 'Sortierung nicht gespeichert.') + ' Die Ansicht wurde zurückgesetzt.', true);
    } finally {
      reordering = false;
    }
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
