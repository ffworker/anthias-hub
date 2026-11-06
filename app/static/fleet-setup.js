/* Progressive enhancement for the compact Add Screen disclosure.
   Never submits the form and never changes an Anthias player. */
(() => {
  'use strict';
  const setup = document.getElementById('device-setup');
  if (!setup || setup.tagName !== 'DETAILS') return;
  const label = setup.querySelector('[data-fleet-setup-action]');
  const first = setup.querySelector('input[name="name"]');
  const update = () => {
    if (label) label.textContent = setup.open ? 'Formular schließen' : 'Formular öffnen';
  };
  function show(focusField) {
    setup.open = true;
    update();
    if (focusField) window.requestAnimationFrame(() => {
      first?.focus({preventScroll: true});
    });
  }
  document.querySelectorAll('a[href="#device-setup"]').forEach(link => {
    link.addEventListener('click', () => show(true));
  });
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#device-setup') show(false);
  });
  if (window.location.hash === '#device-setup') show(false);
  setup.addEventListener('toggle', update);
  update();
})();
