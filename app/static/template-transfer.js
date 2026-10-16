/* A native form POST can run for minutes while Anthias receives files.
 * Show immediate, truthful feedback; never retry/replay a non-atomic transfer.
 * The optional live count is read from Anthias via a separate Hub endpoint. */
(() => {
  'use strict';
  const forms = document.querySelectorAll('form[data-template-transfer]');
  for (const form of forms) {
    const box = form.querySelector('[data-transfer-feedback]');
    const msg = form.querySelector('[data-transfer-message]');
    const live = form.querySelector('[data-transfer-live]');
    const button = form.querySelector('button[type="submit"], button.primary');
    if (!box || !msg || !live || !button) continue;
    let started = false;
    let timer = null;

    const stop = () => {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
    };
    // Back/forward cache restores a live form, not a permanently disabled one.
    window.addEventListener('pageshow', event => {
      if (!event.persisted) return;
      stop();
      started = false;
      button.disabled = false;
      box.hidden = true;
    });

    form.addEventListener('submit', event => {
      if (started) { event.preventDefault(); return; }
      if (!form.reportValidity()) return;
      const target = form.dataset.transferDeviceId ||
        form.querySelector('select[name="device"]')?.value;
      if (!target) return;
      started = true;
      button.disabled = true; // Controls have no name; native form data is preserved.
      button.dataset.transferBusy = 'yes';
      box.hidden = false;
      msg.textContent = 'Vorlage wird übertragen …';
      live.textContent = 'Bitte nicht erneut senden. Die Dateien werden nacheinander auf dem Pi gespeichert.';

      // Native POST continues unchanged, preserving redirects, flashes, CSRF
      // and partial-transfer error handling. This GET observes but never writes.
      const path = form.dataset.transferOverviewPath?.replace(
        '__DEVICE__', encodeURIComponent(target)
      );
      if (!path) return;
      let polling = false;
      const check = async () => {
        if (polling || !started) return;
        polling = true;
        try {
          const response = await fetch(path, {
            credentials:'same-origin', headers:{Accept:'application/json'},
            cache:'no-store'
          });
          if (response.ok) {
            const data = await response.json();
            if (data.ok && Number.isSafeInteger(data.count) && data.count >= 0) {
              live.textContent = 'Player meldet aktuell ' + data.count +
                ' Playlist-Inhalte. Übertragung läuft – bitte nicht erneut senden.';
            }
          }
        } catch (_) {
          // A slow or offline Pi is NOT evidence that the transfer has failed.
        } finally {
          polling = false;
        }
      };
      void check();
      timer = window.setInterval(check, 3000);
    });
  }
})();
