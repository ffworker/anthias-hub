/* Read-only, honest source readiness polling. Never asserts that SMB is
 * mounting unless a fresh root-controlled host report confirms it. */
(() => {
  'use strict';
  const root = document.querySelector('[data-source-monitor]');
  if (!root) return;
  const dest = root.querySelector('[data-source-progress="default"]');
  const summary = dest.querySelector('[data-progress-summary]');
  const stages = dest.querySelector('[data-progress-stages]');
  const lastCheck = dest.querySelector('[data-progress-check]');
  const refresh = root.querySelector('[data-source-check-now]');
  const count = root.querySelector('[data-folder-count]');
  let busy = false;
  let lastFingerprint = '';
  const messages = {
    done: 'Erledigt',
    waiting: 'Ausstehend',
    error: 'Problem',
  };

  async function check() {
    if (busy) return;
    busy = true;
    refresh.disabled = true;
    try {
      const response = await fetch(root.dataset.statusUrl, {
        credentials: 'same-origin', cache: 'no-store',
        headers: {Accept: 'application/json'}
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'Status konnte nicht geprüft werden');
      }
      const source = data.sources.find(row => row.alias === 'default');
      if (!source) {
        summary.textContent = 'Noch kein Netzwerkordner gespeichert.';
        stages.replaceChildren();
        lastCheck.textContent = 'Hostprüfung: nicht eingerichtet';
        if (count) count.textContent = '0';
        return;
      }
      const fingerprint = JSON.stringify(source);
      if (fingerprint === lastFingerprint) return;
      lastFingerprint = fingerprint;
      const list = document.createDocumentFragment();
      for (const step of source.stages) {
        const item = document.createElement('li');
        item.className = 'source-v2-step source-v2-step-' + step.state;
        const heading = document.createElement('strong');
        heading.textContent = (messages[step.state] || 'Unbekannt') + ' · ' + step.title;
        const description = document.createElement('span');
        description.textContent = step.detail;
        item.append(heading, description);
        list.append(item);
      }
      stages.replaceChildren(list);
      const firstIncomplete = source.stages.find(step => step.state !== 'done');
      summary.textContent = (firstIncomplete
        ? 'Nächster Schritt: ' + firstIncomplete.title
        : 'Alle gemeldeten Schritte abgeschlossen.');
      lastCheck.textContent = 'Letzte bestätigte Hostprüfung: ' +
        (source.last_host_check || 'keine Meldung') +
        (source.report_stale ? ' · Meldung veraltet' : '');
      if (count) count.textContent = String(source.discovered);
    } catch (error) {
      summary.textContent = 'Statusabfrage fehlgeschlagen: ' +
        (error instanceof Error ? error.message : 'unbekannt');
    } finally {
      busy = false;
      refresh.disabled = false;
    }
  }

  refresh.addEventListener('click', () => { void check(); });
  void check();
  window.setInterval(() => { if (!document.hidden) void check(); }, 10000);
})();
