/* Read the chosen palette before styles paint; allowed by the same-origin CSP. */
try {
  const theme = localStorage.getItem('anthias-hub-theme');
  if (['nordlicht', 'tageslicht', 'kupfer'].includes(theme)) {
    document.documentElement.dataset.theme = theme;
  }
} catch (_) { /* private storage may be disabled */ }
