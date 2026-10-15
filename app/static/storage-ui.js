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

  async function refresh() {
    if (button) button.disabled = true;
    try {
      const response = await fetch(strip.dataset.storageUrl, {
        credentials:'same-origin', headers:{Accept:'application/json'}, cache:'no-store'
      });
      const data = await response.json();
      if (!response.ok || !data.ok || !Number.isSafeInteger(data.usable_bytes)) {
        throw Error(data.message || 'Speicherplatz derzeit nicht lesbar.');
      }
      if (playerForm) playerForm.dataset.playerAvailable = String(data.usable_bytes);
      strip.dataset.state = data.usable_bytes > 0 ? 'ready' : 'blocked';
      label.textContent = data.usable_bytes > 0
        ? data.usable_gib + ' GiB für Uploads verfügbar'
        : 'Speicherreserve erreicht – Pi-Speicher prüfen';
      return data;
    } catch (_) {
      if (playerForm) playerForm.dataset.playerAvailable = '0';
      strip.dataset.state = 'blocked';
      label.textContent = 'Speicher nicht abrufbar – Upload geschützt';
      return null;
    } finally {
      if (button) button.disabled = false;
    }
  }
  button?.addEventListener('click', refresh);
  window.AnthiasStorage = {refresh};
})();
