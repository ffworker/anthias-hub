/* Progressive upload experience for player and local-library media forms.
 * A 100% browser upload is not a completed Anthias transfer. */
(() => {
  'use strict';
  const limit = 1024 * 1024 * 1024;
  const goodExtensions = /\.(png|jpe?g|webp|mp4)$/i;
  const humanSize = (n) => n < 1024 * 1024
    ? (n / 1024).toFixed(0) + ' KB'
    : (n / (1024 * 1024)).toFixed(1) + ' MB';

  document.querySelectorAll('form[data-upload-form]').forEach((form) => {
    const input = form.querySelector('input[type="file"][name="media"]');
    const submit = form.querySelector('button[type="submit"]');
    const feedback = form.querySelector('.upload-feedback');
    const detail = form.querySelector('.upload-selected');
    const bar = feedback?.querySelector('[data-upload-bar]');
    const message = feedback?.querySelector('[data-upload-text]');
    const isPlayer = form.dataset.uploadForm === 'player';
    if (!input || !submit || !feedback || !bar || !message || !window.XMLHttpRequest) return;

    let busy = false;
    const setMessage = (text, state) => {
      feedback.hidden = false;
      feedback.dataset.state = state;
      message.textContent = text;
    };
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (detail) detail.textContent = file ? file.name + ' · ' + humanSize(file.size) : '';
      feedback.hidden = true;
      bar.style.width = '0%';
    });
    form.addEventListener('submit', async (event) => {
      if (busy || !form.reportValidity()) { event.preventDefault(); return; }
      const file = input.files?.[0];
      if (!file || file.size > limit || !goodExtensions.test(file.name)) {
        event.preventDefault();
        setMessage(!file ? 'Bitte eine Datei auswählen.'
          : file.size > limit ? 'Datei zu groß – höchstens 1 GiB.'
          : 'Unterstützt werden PNG, JPG, WebP und MP4.', 'error');
        return;
      }
      event.preventDefault();
      if (isPlayer) {
        // Re-read capacity after earlier attempts; server also checks immediately before writing.
        if (window.AnthiasStorage?.refresh) {
          submit.disabled = true;
          const disk = await window.AnthiasStorage.refresh();
          submit.disabled = false;
          if (!disk && !form.querySelector('[name="ignore_storage_check"]')?.checked) {
            setMessage('Speicherprüfung fehlgeschlagen. Pi-Speicher prüfen und anschließend „Speicherprüfung ignorieren“ ausdrücklich bestätigen.', 'error');
            return;
          }
        }
        const usable = Number(form.dataset.playerAvailable || 0);
        const confirmed = form.querySelector('[name="ignore_storage_check"]')?.checked;
        if (!Number.isSafeInteger(usable) ||
            (file.size > usable && !(confirmed &&
                window.AnthiasStorage?.lastUnknown === true))) {
          setMessage(usable > 0
            ? 'Sicherheitsreserve erreicht. Pi-Speicher prüfen und Anzeige aktualisieren.'
            : 'Speicherplatz nicht lesbar. Bitte am Pi prüfen und Anzeige aktualisieren.', 'error');
          return;
        }
      }
      const originalLabel = submit.textContent;
      busy = true;
      submit.disabled = true;
      input.disabled = false;
      submit.textContent = 'Bitte warten …';
      bar.style.width = '0%';
      setMessage('Upload wird vorbereitet …', 'progress');
      const request = new XMLHttpRequest();
      request.open('POST', form.action);
      request.setRequestHeader('Accept', 'application/json');
      request.timeout = 2400000; // upload to Hub + potentially slow transfer to Pi
      request.upload.addEventListener('progress', (progress) => {
        if (!progress.lengthComputable) {
          setMessage('Datei wird an Anthias Hub übertragen …', 'progress');
          return;
        }
        const percent = Math.min(100, Math.round(progress.loaded / progress.total * 100));
        bar.style.width = percent + '%';
        setMessage(percent < 100
          ? percent + '% an Anthias Hub übertragen …'
          : isPlayer ? '100% am Hub – wird zum Player übertragen und eingetragen …'
                     : '100% am Hub – Medium wird gespeichert …', 'progress');
      });
      const release = () => {
        busy = false;
        submit.disabled = false;
        submit.textContent = originalLabel;
      };
      request.onload = () => {
        let data = null;
        try { data = JSON.parse(request.responseText); } catch (_) { /* server may return HTML */ }
        if (request.status >= 200 && request.status < 300 && data?.ok && data.redirect) {
          bar.style.width = '100%';
          setMessage(data.message || 'Gespeichert. Playlist wird neu geladen …', 'success');
          window.location.assign(data.redirect);
          return;
        }
        setMessage(data?.error || (request.status === 413
          ? 'Datei zu groß – höchstens 1 GiB.'
          : request.status === 401 || request.status === 403
            ? 'Sitzung abgelaufen oder kein Zugriff. Bitte neu anmelden.'
            : 'Speichern fehlgeschlagen. ' + (isPlayer
              ? 'Bitte Player-Playlist vor erneutem Upload prüfen.'
              : 'Bitte Bibliothek vor erneutem Upload prüfen.')), 'error');
        release();
      };
      request.onerror = request.ontimeout = () => {
        setMessage('Verbindung unterbrochen. ' + (isPlayer
          ? 'Upload könnte am Player bereits angekommen sein. Playlist prüfen, nicht blind erneut hochladen.'
          : 'Bitte Bibliothek prüfen, bevor du es erneut versuchst.'), 'error');
        release();
      };
      request.send(new FormData(form));
    });
  });
})();