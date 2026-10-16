/* Marketing bulk media upload: one ZIP or multi-select, with per-item results. */
(() => {
  'use strict';
  const MiB = 1024 * 1024;
  const allowed = /\.(png|jpe?g|webp|mp4|zip)$/i;

  document.querySelectorAll('form[data-bulk-upload]').forEach((form) => {
    const fileInput = form.querySelector('input[type="file"][name="media"]');
    const button = form.querySelector('button[type="submit"]');
    const selected = form.querySelector('[data-bulk-selected]');
    const progress = form.querySelector('[data-bulk-progress]');
    const bar = form.querySelector('[data-bulk-progress-bar]');
    const progressText = form.querySelector('[data-bulk-progress-text]');
    const report = form.querySelector('[data-bulk-report]');
    if (!fileInput || !button || !selected || !progress || !bar || !progressText || !report ||
        !window.XMLHttpRequest) return;

    let inFlight = false;
    let active = null;
    let cancelled = false;
    const cancel = form.querySelector('[data-bulk-cancel]');
    const isPlayer = form.action.includes('/devices/');

    function showReport(results, remaining, url) {
      report.replaceChildren();
      report.hidden = false;
      report.dataset.state = remaining || results.some(x => x.status !== 'imported') ? 'partial' : 'success';
      const summary = document.createElement('p');
      summary.className = 'bulk-result-summary';
      summary.textContent = results.filter(x => x.status === 'imported').length + ' importiert, ' +
        results.filter(x => x.status === 'failed').length + ' fehlgeschlagen' +
        (remaining ? ', ' + remaining + ' nicht versucht' : '') + '.';
      report.appendChild(summary);
      const list = document.createElement('ul');
      list.className = 'bulk-result-list';
      for (const item of results) {
        const li = document.createElement('li');
        li.className = item.status;
        const strong = document.createElement('strong');
        strong.textContent = item.status === 'imported' ? '✓' : '!';
        li.append(strong, document.createTextNode(' ' + item.name + ' — ' + item.message));
        list.appendChild(li);
      }
      report.appendChild(list);
      if (report.dataset.state !== 'success') {
        const warning = document.createElement('p');
        warning.textContent = 'Bereits übertragene Medien können auf dem Player liegen. ' +
          'Erst Playlist und freien Speicher prüfen; keine automatische Wiederholung.';
        report.appendChild(warning);
      }
      if (url) {
        const link = document.createElement('a');
        link.href = url;
        link.className = 'button';
        link.textContent = 'Aktualisierte Inhalte ansehen →';
        report.appendChild(link);
      }
    }

    fileInput.addEventListener('change', () => {
      const files = Array.from(fileInput.files || []);
      selected.textContent = files.length ?
        files.length + ' Datei(en) · ' +
        (files.reduce((n, file) => n + file.size, 0) / MiB).toFixed(1) + ' MiB ausgewählt' : '';
      report.hidden = true;
      report.replaceChildren();
      progress.hidden = true;
      bar.style.width = '0%';
    });

    function sendOne(file, index, total) {
      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        active = xhr;
        xhr.open('POST', form.action);
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.timeout = 7200000;
        xhr.upload.addEventListener('progress', (e) => {
          const percent = e.lengthComputable ? Math.min(100, Math.round(e.loaded / e.total * 100)) : 0;
          bar.style.width = Math.round((index + percent / 100) / total * 100) + '%';
          progressText.textContent = 'Datei ' + (index + 1) + '/' + total + ': ' +
            percent + '% an Hub übertragen' + (percent === 100 ? ' · Verarbeitung läuft …' : '');
        });
        xhr.onload = () => {
          active = null;
          let data = null;
          try { data = JSON.parse(xhr.responseText); } catch (_) { /* HTML response */ }
          if (xhr.status >= 200 && xhr.status < 300 && Array.isArray(data?.results)) {
            resolve({ok: !!data.ok, results:data.results, url:data.redirect});
          } else {
            resolve({ok:false,results:[{name:file.name,status:'failed',message:
              data?.error || 'Hub antwortete mit HTTP ' + xhr.status + '. Ziel prüfen.'}]});
          }
        };
        const interrupted = () => {
          active = null;
          resolve({ok:false,results:[{name:file.name,status:'failed',
            message:'Unterbrochen: möglicherweise bereits übertragen. Ziel prüfen.'}]});
        };
        xhr.onerror = xhr.ontimeout = xhr.onabort = interrupted;
        const fields = new FormData(form);
        fields.delete('media'); // Important: send ONE of the selected files, not all.
        fields.append('media', file, file.name);
        xhr.send(fields);
      });
    }

    cancel?.addEventListener('click', () => {
      if (!inFlight) return;
      cancelled = true;
      cancel.disabled = true;
      active?.abort();
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (inFlight || !form.reportValidity()) return;
      const files = Array.from(fileInput.files || []);
      const archives = files.filter(file => /\.zip$/i.test(file.name));
      if (!files.length || files.length > 20 ||
          (archives.length && files.length !== 1) ||
          files.some(file => !allowed.test(file.name)) ||
          files.some(file => file.size > (archives.length ? 50 : 4096) * MiB)) {
        report.replaceChildren();
        report.hidden = false;
        report.dataset.state = 'error';
        const error = document.createElement('p');
        error.textContent = 'Max. 20 Medien, je 4 GiB (einzeln übertragen); ZIP allein max. 50 MiB.';
        report.appendChild(error);
        return;
      }
      inFlight = true; cancelled = false;
      const oldText = button.textContent;
      button.disabled = true; button.textContent = 'Import läuft …';
      if (cancel) {cancel.hidden = false; cancel.disabled = false;}
      progress.hidden = false; report.hidden = true;
      bar.style.width = '0%';
      const results = [];
      let remaining = 0, url = '';
      try {
        for (let index = 0; index < files.length; index++) {
          if (cancelled) {remaining = files.length - index; break;}
          if (isPlayer && window.AnthiasStorage?.refresh) {
            progressText.textContent = 'Gerätespeicher wird geprüft …';
            const disk = await window.AnthiasStorage.refresh();
            const acknowledge = form.querySelector('[name="ignore_storage_check"]')?.checked;
            if ((!disk && !acknowledge) ||
                (disk && disk.usable_bytes < files[index].size)) {
              results.push({name:files[index].name,status:'failed',message:disk ?
                'Sicherheitsreserve erreicht. Freien Pi-Speicher prüfen.' :
                'Speicherprüfung fehlgeschlagen: nach manueller Pi-Prüfung „Speicherprüfung ignorieren“ bestätigen.'});
              remaining = files.length - index - 1;
              break;
            }
          }
          if (cancelled) {remaining = files.length - index; break;}
          const response = await sendOne(files[index], index, files.length);
          results.push(...response.results);
          url = response.url || url;
          if (!response.ok || response.results.some(x => x.status === 'failed')) {
            remaining = files.length - index - 1;
            break;
          }
          bar.style.width = Math.round((index + 1) / files.length * 100) + '%';
        }
        showReport(results, remaining, url);
        progressText.textContent = remaining || cancelled || results.some(x => x.status === 'failed')
          ? 'Angehalten – Ergebnis und Ziel prüfen.' : 'Import erfolgreich abgeschlossen.';
      } catch (_) {
        showReport([...results, {name:'Upload',status:'failed',message:
          'Vorgang unterbrochen; Ziel prüfen.'}], remaining, url);
      } finally {
        inFlight = false; active = null;
        button.disabled = false; button.textContent = oldText;
        if (cancel) {cancel.hidden = true; cancel.disabled = false;}
        if (isPlayer) window.AnthiasStorage?.refresh?.();
      }
    });
  });
})();
