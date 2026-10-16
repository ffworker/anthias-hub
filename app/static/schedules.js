/* Small enhancements for native, server-rendered Anthias schedule forms. */
(() => {
  'use strict';
  for (const form of document.querySelectorAll('[data-schedule-form]')) {
    form.querySelectorAll('[data-schedule-example]').forEach(button => {
      button.addEventListener('click', () => {
        const event = button.dataset.scheduleExample === 'event';
        const name = form.querySelector('[name="name"]');
        if (name) name.value = event ? 'Event' : 'Werktag_Default';
        form.querySelector('[name="start"]').value = event ? '10:00' : '08:00';
        form.querySelector('[name="end"]').value = event ? '14:00' : '18:00';
        form.querySelectorAll('[name="days"]').forEach(input => {
          input.checked = event ? input.value === '6' : Number(input.value) <= 5;
        });
      });
    });
  }
  const form = document.querySelector('[data-schedule-assign]');
  if (!form) return;
  const checks = Array.from(form.querySelectorAll('input[name="asset_ids"]'));
  form.querySelector('[data-schedule-select-all]')?.addEventListener('click', () => {
    checks.forEach(check => { check.checked = true; });
  });
  form.querySelector('[data-schedule-select-none]')?.addEventListener('click', () => {
    checks.forEach(check => { check.checked = false; });
  });
  let pending = false;
  form.addEventListener('submit', event => {
    if (pending) { event.preventDefault(); return; }
    if (!checks.some(check => check.checked)) {
      event.preventDefault();
      form.querySelector('[data-schedule-feedback]').hidden = false;
      form.querySelector('[data-schedule-feedback]').textContent = 'Bitte mindestens einen Inhalt auswählen.';
      return;
    }
    if (!form.reportValidity()) return;
    pending = true;
    const feedback = form.querySelector('[data-schedule-feedback]');
    feedback.hidden = false;
    feedback.textContent = 'Zeitplanung wird auf dem Pi gespeichert …';
    form.querySelector('button[type="submit"]').disabled = true;
  });
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    pending = false;
    const feedback = form.querySelector('[data-schedule-feedback]');
    feedback.hidden = true;
    form.querySelector('button[type="submit"]').disabled = false;
  });
})();
