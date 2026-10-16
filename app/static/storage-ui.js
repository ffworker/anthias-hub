/* Compact storage controls. Capacity is always rechecked by the server before writing. */
(() => {
  'use strict';
  for (const menu of document.querySelectorAll('.fleet-storage-menu')) {
    // Hover opens for pointer users, native details tap/keyboard remains available.
    if (window.matchMedia?.('(hover: hover)').matches) {
      menu.addEventListener('mouseenter', () => { menu.open = true; });
      menu.addEventListener('mouseleave', () => { menu.open = false; });
    }
  }

  document.addEventListener('pointerdown', (event) => {
    for (const menu of document.querySelectorAll('.fleet-storage-menu')) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    for (const menu of document.querySelectorAll('.fleet-storage-menu[open]')) {
      menu.open = false;
      menu.querySelector('summary')?.focus();
    }
  });

  const strip = document.querySelector('[data-storage-status]');
  if (!strip) return;
  const label = strip.querySelector('[data-storage-label]');
  const button = strip.querySelector('[data-storage-refresh]');
  const playerForm = document.querySelector('form[data-upload-form="player"]');

  // Override is a conscious checkbox in the individual and batch forms.
  // Unknown storage alone is eligible; an actual low-space reading never is.
  const overrides = Array.from(document.querySelectorAll('[data-storage-override]'));
  const setOverrideVisible = (unknown) => {
    for (const label of overrides) {
      label.hidden = !unknown;
      const check = label.querySelector('input[name="ignore_storage_check"]');
      if (check) {
        check.disabled = !unknown;
        if (!unknown) check.checked = false;
      }
    }
  };
  const markUnknown = (message) => {
    if (playerForm) playerForm.dataset.playerAvailable = '0';
    strip.dataset.state = 'unknown';
    label.textContent = 'Speicherwert nicht verfügbar · ' + message;
    setOverrideVisible(true);
    if (window.AnthiasStorage) window.AnthiasStorage.lastUnknown = true;
  };
  const markKnown = (data) => {
    if (playerForm) playerForm.dataset.playerAvailable = String(data.usable_bytes);
    strip.dataset.state = data.usable_bytes > 0 ? 'ready' : 'blocked';
    label.textContent = data.usable_bytes > 0
      ? data.usable_gib + ' GiB für Uploads verfügbar'
      : 'Sicherheitsreserve erreicht – Pi-Speicher prüfen';
    setOverrideVisible(false);
    if (window.AnthiasStorage) window.AnthiasStorage.lastUnknown = false;
  };
  setOverrideVisible(!Number(strip.dataset.storageKnown));

  async function refresh() {
    if (button) button.disabled = true;
    try {
      const response = await fetch(strip.dataset.storageUrl, {
        credentials:'same-origin', headers:{Accept:'application/json'}, cache:'no-store'
      });
      const data = await response.json();
      if (!response.ok) throw Error('Info-Abfrage HTTP ' + response.status);
      if (!data.ok || data.status === 'unknown') {
        markUnknown(data.message || 'Keine nutzbaren Speicherdaten');
        return null;
      }
      if (!Number.isSafeInteger(data.usable_bytes) || data.usable_bytes < 0) {
        throw Error('Ungültige Speicherdaten');
      }
      markKnown(data);
      return data;
    } catch (error) {
      markUnknown(error.message || 'Antwort konnte nicht gelesen werden');
      return null;
    } finally {
      if (button) button.disabled = false;
    }
  }
  button?.addEventListener('click', refresh);
  window.AnthiasStorage = {refresh, lastUnknown: !Number(strip.dataset.storageKnown)};
})();
