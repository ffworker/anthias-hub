/* Responsive, non-modal flyouts for existing IT/Marketing device <details>.
 * Progressive enhancement: without JS the original inline controls still work.
 * No commands are submitted by this script.
 */
(() => {
  'use strict';
  const menus = Array.from(document.querySelectorAll(
    '.fleet-device-actions > details.fleet-remote, .fleet-device-actions > details.fleet-settings'
  ));
  if (!menus.length) return;

  const panelFor = (menu) => Array.from(menu.children).find(
    (child) => child.classList?.contains('fleet-remote-body') ||
               child.classList?.contains('fleet-settings-content')
  );
  const pairs = menus.map(menu => ({menu, trigger: menu.querySelector('summary'), panel: panelFor(menu)}))
    .filter(entry => entry.trigger && entry.panel);
  if (!pairs.length) return;

  const mobile = window.matchMedia('(max-width: 760px)');
  const gap = 22;
  const margin = 12;
  let pending = false;

  function place(entry) {
    if (!entry.menu.open) return;
    const {trigger, panel} = entry;
    // Keep the panel inside the viewport even for the rightmost card.
    // At small widths CSS turns it into a bottom sheet.
    if (mobile.matches) {
      panel.style.removeProperty('left');
      panel.style.removeProperty('top');
      panel.style.removeProperty('width');
      return;
    }
    const width = Math.min(312, Math.max(240, window.innerWidth - margin * 2));
    const rect = trigger.getBoundingClientRect();
    const rightX = rect.right + gap;
    const leftX = rect.left - gap - width;
    const fitsRight = rightX + width <= window.innerWidth - margin;
    const fitsLeft = leftX >= margin;
    // Prefer the outer edge of the screen; if both sides are tight,
    // overlap neighboring cards rather than letting the panel escape the viewport.
    let x = fitsRight ? rightX : fitsLeft ? leftX
      : window.innerWidth - rect.right >= rect.left ? rightX : leftX;
    x = Math.max(margin, Math.min(x, window.innerWidth - width - margin));

    panel.style.width = width + 'px';
    panel.style.left = Math.round(x) + 'px';
    const visibleHeight = Math.min(panel.scrollHeight, window.innerHeight - margin * 2);
    const top = Math.max(margin, Math.min(rect.top - 8,
      window.innerHeight - visibleHeight - margin));
    panel.style.top = Math.round(top) + 'px';
  }

  function reposition() {
    if (pending) return;
    pending = true;
    window.requestAnimationFrame(() => {
      pending = false;
      pairs.forEach(place);
    });
  }

  pairs.forEach((entry) => {
    entry.panel.querySelector('[data-close-fleet-menu]')?.addEventListener('click', () => {
      entry.menu.open = false;
      entry.trigger.focus();
    });
    entry.menu.addEventListener('toggle', () => {
      if (entry.menu.open) {
        pairs.forEach(other => {
          if (other !== entry && other.menu.open) other.menu.open = false;
        });
        place(entry);
      }
    });
  });

  document.documentElement.classList.add('fleet-popovers-ready');
  document.addEventListener('pointerdown', (event) => {
    for (const entry of pairs) {
      if (entry.menu.open && !entry.menu.contains(event.target)) entry.menu.open = false;
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const opened = pairs.find(entry => entry.menu.open);
    if (!opened) return;
    opened.menu.open = false;
    opened.trigger.focus();
    event.preventDefault();
  });
  window.addEventListener('resize', reposition, {passive:true});
  window.addEventListener('scroll', reposition, {capture:true, passive:true});
  mobile.addEventListener?.('change', reposition);
})();
