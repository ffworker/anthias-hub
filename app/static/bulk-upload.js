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
    const showError = (text) => {
      report.replaceChildren();
      report.hidden = false;
      report.dataset.state = 'error';
      const paragraph = document.createElement('p');
      paragraph.textContent = text;
      report.appendChild(paragraph);
    };
    fileInput.addEventListener('change', () => {
      const files = Array.from(fileInput.files || []);
      selected.textContent = files.length
        ? files.length + ' Datei(en) ausgewählt · ' +
          (files.reduce((n, file) => n + file.size, 0) / MiB).toFixed(1) + ' MB gesamt'
        : '';
      report.hidden = true;
      report.replaceChildren();
      progress.hidden = true;
      bar.style.width = '0%';
    });
    form.addEventListener('submit', (event) => {
      if (inFlight || !form.reportValidity()) { event.preventDefault(); return; }
      event.preventDefault();
      const files = Array.from(fileInput.files || []);
      const archives = files.filter((file) => /\.zip$/i.test(file.name));
      if (!files.length || files.length > 20 || (archives.length && files.length !== 1) ||
          files.some((file) => !allowed.test(file.name)) ||
          files.reduce((n, file) => n + file.size, 0) > 50 * MiB) {
        showError('Bitte 1 ZIP allein oder bis zu 20 PNG/JPG/WebP/MP4 auswählen; maximal 50 MB Upload gesamt.');
        return;
      }
      inFlight = true;
      button.disabled = true;
      const oldText = button.textContent;
      button.textContent = 'Import läuft …';
      report.hidden = true;
      progress.hidden = false;
      progressText.textContent = 'Upload wird vorbereitet …';
      bar.style.width = '0%';

      const xhr = new XMLHttpRequest();
      xhr.open('POST', form.action);
      xhr.setRequestHeader('Accept', 'application/json');
      xhr.timeout = 350000;
      xhr.upload.addEventListener('progress', (e) => {
        if (!e.lengthComputable) {
          progressText.textContent = 'Dateien werden hochgeladen …';
          return;
        }
        const percentage = Math.min(100, Math.round(e.loaded / e.total * 100));
        bar.style.width = percentage + '%';
        progressText.textContent = percentage < 100
          ? percentage + '% an Anthias Hub übertragen …'
          : '100% am Hub – Dateien werden einzeln geprüft und importiert. Bitte warten …';
      });

      const release = () => {
        inFlight = false;
        button.disabled = false;
        button.textContent = oldText;
      };
      xhr.onload = () => {
        let payload = null;
        try { payload = JSON.parse(xhr.responseText); } catch (_) { /* HTML or error page */ }
        if (!payload || !Array.isArray(payload.results)) {
          showError(payload?.error || (xhr.status === 413
            ? 'Upload zu groß (höchstens 50 MB gesamt).'
            : 'Import konnte nicht abgeschlossen werden. Ziel prüfen, bevor du erneut hochlädst.'));
          release();
          return;
        }
        report.replaceChildren();
        report.hidden = false;
        report.dataset.state = payload.failed ? 'partial' : 'success';
        const heading = document.createElement('p');
        heading.className = 'bulk-result-summary';
        heading.textContent = payload.message;
        report.appendChild(heading);
        if (payload.results.length) {
          const list = document.createElement('ul');
          list.className = 'bulk-result-list';
          payload.results.forEach((entry) => {
            const li = document.createElement('li');
            li.className = entry.status === 'imported' ? 'imported' : 'failed';
            const label = document.createElement('strong');
            label.textContent = entry.status === 'imported' ? '✓' : '!';
            li.append(label, document.createTextNode(' ' + entry.name + ' — ' + entry.message));
            list.appendChild(li);
          });
          report.appendChild(list);
        }
        if (payload.failed) {
          const warning = document.createElement('p');
          warning.textContent = 'Teilerfolge werden nicht zurückgerollt. Bitte zuerst Ziel-Playlist/Bibliothek prüfen, um Duplikate zu vermeiden.';
          report.appendChild(warning);
        }
        if (payload.redirect) {
          const link = document.createElement('a');
          link.href = payload.redirect;
          link.className = 'button';
          link.textContent = 'Aktualisierte Inhalte ansehen →';
          report.appendChild(link);
        }
        progressText.textContent = payload.failed
          ? 'Import abgeschlossen – bitte Ergebnisbericht prüfen.'
          : 'Import erfolgreich abgeschlossen.';
        release();
      };
      xhr.onerror = xhr.ontimeout = () => {
        showError('Verbindung unterbrochen oder Zeitlimit erreicht. Einige Dateien könnten bereits importiert sein. Ziel prüfen; nicht blind wiederholen.');
        release();
      };
      xhr.send(new FormData(form));
    });
  });
})();
