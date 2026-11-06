/* Shared product appearance. Signaturee design language, independent code. */
(function () {
  'use strict';
  const KEY = 'anthias-hub-theme';
  const root = document.documentElement;
  let saved = null;
  try { saved = window.localStorage.getItem(KEY); } catch (_ignored) {}
  const theme = saved === 'dark' || saved === 'light' ? saved : 'light';
  root.setAttribute('data-theme', theme);

  function sync(button) {
    const isDark = root.getAttribute('data-theme') === 'dark';
    button.setAttribute('aria-pressed', isDark ? 'true' : 'false');
    button.textContent = isDark ? 'Hell' : 'Dunkel';
    button.title = isDark ? 'Helles Design aktivieren' : 'Dunkles Design aktivieren';
  }

  document.addEventListener('DOMContentLoaded', function () {
    const buttons = document.querySelectorAll('[data-product-theme-toggle]');
    buttons.forEach(function (button) {
      sync(button);
      button.addEventListener('click', function () {
        const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        try { window.localStorage.setItem(KEY, next); } catch (_ignored) {}
        buttons.forEach(sync);
      });
    });
  });
}());
