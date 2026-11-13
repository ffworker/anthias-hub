/* Read-only player storage diagnostics in the DEV management workspace. */
(() => {
  'use strict';
  for (const details of document.querySelectorAll('[data-control-storage]')) {
    const label = details.querySelector('[data-storage-feedback]');
    if (!label) continue;
    let inflight = false;
    details.addEventListener('toggle', async () => {
      if (!details.open || inflight) return;
      inflight = true;
      label.textContent = 'Gerätespeicher wird abgefragt …';
      try {
        const response = await fetch(details.dataset.storageUrl, {
          headers: {Accept: 'application/json'}, credentials: 'same-origin',
          cache: 'no-store'
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const status = await response.json();
        if (status.ok && Number.isFinite(Number(status.usable_gib))) {
          label.textContent = Number(status.usable_gib).toLocaleString('de-DE', {
            maximumFractionDigits: 2
          }) + ' GiB für neue Inhalte verfügbar.';
        } else {
          label.textContent = 'Speicherprüfung nicht verfügbar: ' +
            String(status.message || 'unbekannt');
        }
      } catch {
        label.textContent = 'Gerät nicht erreichbar oder Speicherwert nicht verfügbar.';
      } finally {
        inflight = false;
      }
    });
  }
})();
