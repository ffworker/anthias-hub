/* Open only native disclosures targeted by same-page links.
 * This never submits forms or mutates server/player state.
 */
(() => {
  'use strict';
  function reveal(hash) {
    if (!hash || hash[0] !== '#') return;
    let id;
    try { id = decodeURIComponent(hash.slice(1)); }
    catch { return; }
    const target = document.getElementById(id);
    if (!target) return;
    if (target.tagName === 'DETAILS') target.open = true;
    let parent = target.parentElement?.closest('details');
    while (parent) {
      parent.open = true;
      parent = parent.parentElement?.closest('details');
    }
  }
  document.addEventListener('click', (event) => {
    const link = event.target?.closest?.('a[href*="#"]');
    if (!link) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin === window.location.origin &&
        target.pathname === window.location.pathname &&
        target.search === window.location.search) {
      reveal(target.hash);
    }
  });
  window.addEventListener('hashchange', () => reveal(window.location.hash));
  reveal(window.location.hash);
})();
