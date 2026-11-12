/* One-time SMB folder import: display *confirmed* file counts from the Pi API.
 * A streamed POST stays a single operation. Never auto-retry after a disconnect:
 * earlier files may already have reached the player.
 * Without Fetch/ReadableStream, the ordinary HTML POST still works. */
(() => {
  'use strict';
  const form = document.querySelector('form[data-network-import-form]');
  if (!form || !window.fetch || !window.ReadableStream || !window.TextDecoder) return;

  const submit = form.querySelector('button[type="submit"]');
  const feedback = form.querySelector('[data-network-import-feedback]');
  const counter = form.querySelector('[data-network-import-counter]');
  const stage = form.querySelector('[data-network-import-stage]');
  const track = form.querySelector('[data-network-import-bar]');
  const fill = form.querySelector('[data-network-import-fill]');
  const reload = form.querySelector('[data-network-import-reload]');
  if (!submit || !feedback || !counter || !stage || !track || !fill || !reload) return;

  const tabs = Array.from(document.querySelectorAll('.composer-source-menu [data-add-mode]'));
  let inFlight = false;
  let submitted = false;

  function count(done, total) {
    const completed = Math.max(0, Number(done) || 0);
    const size = Math.max(0, Number(total) || 0);
    counter.textContent = size
      ? completed + ' / ' + size + ' Dateien übertragen'
      : 'Netzwerkordner wird geprüft …';
    track.setAttribute('aria-valuemax', String(Math.max(1, size)));
    track.setAttribute('aria-valuenow', String(Math.min(completed, Math.max(1, size))));
    fill.style.width = (size ? Math.min(100, Math.round(completed / size * 100)) : 0) + '%';
  }

  function onUpdate(data) {
    count(data.done, data.total);
    const total = Math.max(0, Number(data.total) || 0);
    const done = Math.max(0, Number(data.done) || 0);
    switch (data.type) {
      case 'preparing':
        stage.textContent = data.message || 'Dateien werden geprüft …';
        break;
      case 'start':
        stage.textContent = 'Alle Dateien geprüft. Übertragung zum Pi startet …';
        break;
      case 'active':
        stage.textContent = 'Datei ' + data.index + '/' + total +
          ' wird übertragen: ' + (data.name || '');
        break;
      case 'progress':
        stage.textContent = 'Datei ' + done + '/' + total + ' erfolgreich hinzugefügt: ' +
          (data.name || '');
        break;
      case 'complete':
        submitted = true;
        feedback.dataset.state = 'success';
        stage.textContent = data.message || 'Alle Dateien wurden hinzugefügt.';
        reload.hidden = false;
        break;
      case 'error':
        submitted = true;
        feedback.dataset.state = 'error';
        stage.textContent = (data.message || 'Import abgebrochen.') +
          ' Bereits übertragene Dateien nicht blind erneut importieren.';
        reload.hidden = false;
        break;
      default:
        break;
    }
  }

  window.addEventListener('beforeunload', event => {
    if (!inFlight) return;
    event.preventDefault();
    event.returnValue = '';
  });

  form.addEventListener('submit', async event => {
    if (inFlight || submitted) {
      event.preventDefault();
      return;
    }
    // Native required/select/checkbox constraints remain authoritative.
    if (!form.checkValidity()) return;
    event.preventDefault();
    inFlight = true;
    form.dataset.running = 'true';
    submit.disabled = true;
    tabs.forEach(tab => { tab.disabled = true; });
    feedback.hidden = false;
    feedback.dataset.state = 'running';
    reload.hidden = true;
    count(0, 0);
    stage.textContent = 'Verbindung zum Pi wird geprüft …';

    try {
      const data = new FormData(form);
      data.set('progress_stream', '1');
      const response = await fetch(form.action, {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: { Accept: 'text/event-stream' }
      });
      if (!response.ok || !response.body ||
          !(response.headers.get('Content-Type') || '').includes('text/event-stream')) {
        throw new Error('Keine gültige Fortschrittsverbindung zum Hub.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Each server event is a JSON "data:" line delimited by a blank line.
      // A single chunk may contain zero, one or many complete events.
      function parseFrames(chunk) {
        buffer += chunk.replace(/\r/g, '');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          for (const line of frame.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const data = JSON.parse(line.slice(6));
            onUpdate(data);
          }
        }
      }
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parseFrames(decoder.decode(value, { stream: true }));
      }
      parseFrames(decoder.decode());
      if (!submitted) {
        throw new Error('Fortschrittsverbindung vor dem Ergebnis unterbrochen.');
      }
    } catch (error) {
      if (!submitted) {
        feedback.dataset.state = 'error';
        stage.textContent = (error.message || 'Verbindung unterbrochen.') +
          ' Es könnten schon Dateien auf dem Pi liegen. Playlist zuerst prüfen, nicht automatisch wiederholen.';
        reload.hidden = false;
        submitted = true;
      }
    } finally {
      inFlight = false;
      delete form.dataset.running;
      tabs.forEach(tab => { tab.disabled = false; });
      // Deliberately require a playlist review before another manual import.
      submit.disabled = submitted;
    }
  });
})();
