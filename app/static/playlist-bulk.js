(() => {
  'use strict';
  const studio = document.querySelector('.playlist-studio-v2[data-can-edit="yes"]');
  const panel = studio?.querySelector('[data-bulk-management]');
  const form = studio?.querySelector('#playlist-bulk-form');
  if (!studio || !panel || !form) return;

  const choices = Array.from(studio.querySelectorAll('[data-bulk-check]'));
  const toggle = form.querySelector('[data-bulk-toggle]');
  const selectAll = form.querySelector('[data-bulk-all]');
  const count = form.querySelector('[data-bulk-count]');
  const ack = form.querySelector('[data-bulk-ack]');
  const selectedButton = form.querySelector('[data-bulk-delete-selected]');
  const clearButton = form.querySelector('[data-bulk-clear-all]');
  const nameInput = form.querySelector('[data-bulk-device-name]');
  const exactName = nameInput?.getAttribute('placeholder') || '';

  function selected() { return choices.filter(choice => choice.checked); }
  function refresh() {
    const total = selected().length;
    count.textContent = total + ' ausgewählt';
    selectedButton.disabled = total === 0 || !ack.checked;
    clearButton.disabled = !ack.checked || nameInput.value !== exactName;
    selectAll.textContent = total === choices.length ? 'Auswahl aufheben' : 'Alle auswählen';
  }
  function selecting(enabled) {
    studio.classList.toggle('bulk-select-mode', enabled);
    toggle.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    toggle.textContent = enabled ? 'Auswahl beenden' : 'Auswahl starten';
    selectAll.hidden = !enabled;
    if (!enabled) choices.forEach(choice => { choice.checked = false; });
    refresh();
  }
  toggle.addEventListener('click', () => selecting(!studio.classList.contains('bulk-select-mode')));
  selectAll.addEventListener('click', () => {
    const next = selected().length !== choices.length;
    choices.forEach(choice => { choice.checked = next; });
    refresh();
  });
  choices.forEach(choice => choice.addEventListener('change', refresh));
  ack.addEventListener('change', refresh);
  nameInput.addEventListener('input', refresh);

  form.addEventListener('submit', event => {
    const mode = event.submitter?.value;
    if (mode === 'selected') {
      if (!selected().length || !ack.checked ||
          !window.confirm(selected().length + ' ausgewählte Inhalte endgültig vom Player löschen?')) {
        event.preventDefault();
      }
    } else if (mode === 'all') {
      if (!ack.checked || nameInput.value !== exactName ||
          !window.confirm('Alle ' + choices.length + ' Inhalte von „' + exactName +
                          '“ löschen? Die Bildschirm-Playlist wird geleert.')) {
        event.preventDefault();
      }
    } else {
      event.preventDefault();
    }
  });
  // The checkboxes remain usable when JavaScript is disabled; when enabled,
  // they are shown only while explicit selection mode is active.
  selecting(false);
  refresh();
})();