/* Appearance is local to this browser; no account or player settings are changed. */
(() => {
  const choices = document.querySelectorAll('[data-theme-choice]');
  const valid = ['nordlicht', 'tageslicht', 'kupfer'];
  function apply(theme) {
    if (!valid.includes(theme)) return;
    document.documentElement.dataset.theme = theme;
    choices.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme)));
  }
  apply(document.documentElement.dataset.theme || 'nordlicht');
  choices.forEach((button) => button.addEventListener('click', () => {
    apply(button.dataset.themeChoice);
    try { localStorage.setItem('anthias-hub-theme', button.dataset.themeChoice); } catch (_) { /* non-persistent private context */ }
    button.closest('.theme-picker').open = false;
  }));
})();
