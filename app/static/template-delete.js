(() => {
  'use strict';
  const menus = Array.from(document.querySelectorAll('[data-template-delete]'));
  for (const menu of menus) {
    const form = menu.querySelector('[data-delete-form]');
    if (!form) continue;
    const name = form.querySelector('[data-delete-name]');
    const ack = form.querySelector('[data-delete-ack]');
    const button = form.querySelector('[data-delete-submit]');
    if (!name || !ack || !button) continue;
    function refresh() {
      // Keep HTML form submission available without JavaScript; with JS,
      // prevent a mistaken click until the exact current name is typed.
      button.disabled = name.value !== form.dataset.expectedName || !ack.checked;
    }
    menu.addEventListener('toggle', () => {
      if (menu.open) {
        menus.filter(other => other !== menu).forEach(other => { other.open = false; });
      }
    });
    name.addEventListener('input', refresh);
    ack.addEventListener('change', refresh);
    refresh();
  }
  document.addEventListener('pointerdown', (event) => {
    menus.filter(menu => menu.open && !menu.contains(event.target))
      .forEach(menu => { menu.open = false; });
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      const opened = menus.find(menu => menu.open);
      if (opened) {
        opened.open = false;
        opened.querySelector('summary')?.focus();
      }
    }
  });
})();