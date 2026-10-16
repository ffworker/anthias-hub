/* Live fleet overview: the HTML must never wait for Pi network requests.
 * Statuses resolve independently, and disk info loads only when inspected. */
(() => {
  'use strict';
  const cards = Array.from(document.querySelectorAll('.fleet-device[data-overview-url]'));
  if (!cards.length) return;
  const online = document.querySelector('[data-fleet-online]');
  const offline = document.querySelector('[data-fleet-offline]');

  const totals = () => {
    const ready = cards.filter(card => card.dataset.overviewState === 'ready').length;
    const down = cards.filter(card => card.dataset.overviewState === 'offline').length;
    if (online) online.textContent = String(ready);
    if (offline) offline.textContent = String(down);
  };

  async function overview(card) {
    const badge = card.querySelector('[data-device-state]');
    const count = card.querySelector('[data-device-count]');
    try {
      const response = await fetch(card.dataset.overviewUrl, {
        credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}
      });
      if (!response.ok) throw Error('Playerstatus nicht abrufbar');
      const data = await response.json();
      if (!data.ok || !Number.isSafeInteger(data.count) || data.count < 0) {
        throw Error('Player nicht erreichbar');
      }
      card.dataset.overviewState = 'ready';
      badge.textContent = 'API erreichbar';
      badge.classList.remove('off', 'bad');
      badge.classList.add('ok');
      count.textContent = String(data.count);
      card.classList.remove('fleet-device-offline');
    } catch (_) {
      card.dataset.overviewState = 'offline';
      badge.textContent = 'Nicht erreichbar';
      badge.classList.remove('off', 'ok');
      badge.classList.add('bad');
      count.textContent = '–';
      card.classList.add('fleet-device-offline');
    }
    totals();
  }

  async function storage(menu) {
    if (menu.dataset.loading === '1') return;
    menu.dataset.loading = '1';
    const message = menu.querySelector('[data-storage-message]');
    const list = menu.querySelector('[data-storage-values]');
    const dot = menu.querySelector('[data-storage-warning]');
    message.hidden = false;
    message.textContent = 'Speicher wird abgefragt …';
    try {
      const response = await fetch(menu.dataset.storageUrl, {
        credentials:'same-origin', cache:'no-store', headers:{Accept:'application/json'}
      });
      if (!response.ok) throw Error('Speicherabfrage fehlgeschlagen');
      const data = await response.json();
      if (!data.ok || !Number.isSafeInteger(data.usable_bytes) || data.usable_bytes < 0) {
        throw Error(data.message || 'Anthias-Speicherwert nicht verfügbar');
      }
      menu.querySelector('[data-storage-reported]').textContent = data.reported;
      menu.querySelector('[data-storage-budget]').textContent = data.usable_gib + ' GiB';
      menu.querySelector('[data-storage-reserve]').textContent = data.reserve_gib + ' GiB';
      list.hidden = false;
      dot.hidden = data.usable_bytes > 0;
      if (data.usable_bytes === 0) {
        message.textContent = 'Sicherheitsreserve erreicht. Pi-Speicher prüfen.';
      } else {
        message.hidden = true;
      }
    } catch (error) {
      list.hidden = true;
      dot.hidden = false;
      message.textContent = error.message || 'Speicherwert nicht verfügbar';
    } finally {
      menu.dataset.loading = '0';
    }
  }

  for (const card of cards) {
    void overview(card);
    const menu = card.querySelector('.fleet-storage-menu[data-storage-url]');
    menu?.addEventListener('toggle', () => {
      if (menu.open) void storage(menu);
    });
  }
})();
