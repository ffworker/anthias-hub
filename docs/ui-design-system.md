# Anthias Hub – UI design principles

## Product direction

The Hub follows a calm, compact, **paper + ink** visual language similar to
the current Signaturee application: useful workflows first, configuration
second. It is a standalone implementation, with no copied CSS/assets or
runtime dependencies from another project.

The primary user journey is now:

1. **Ordner & Quellen (IT):** configure one `default` SMB root; direct
   child directories become usable playlists with one click.
2. **Playlists:** edit imported-image duration and optional RSS/web slides.
   Marketing works in the familiar network directories, not an upload UI.
3. **Bildschirme:** monitor connected players, schedules, native Anthias
   playlist and actual playback separately.

Manual uploads and other SMB sources remain available as advanced/optional
workflows. A Pi may not be written to merely because a source was saved.
The server-side `FOLDER_AUTO_PUBLISH` flag remains off by default.

## Visual language

Shared, last-loaded `app/static/product-ui.css` owns the product look.
`app/static/product-theme.js` stores a light/dark preference locally; it
does not call external services.

- Light: warm `#eeece2` background, light paper surfaces, soft ruled borders.
- Ink masthead: `#191b1a` with visible coral highlight `#ff795c`.
- Typography: Georgia serif for major titles, Helvetica/Arial sans for body,
  Consolas/monospace for compact metadata and section indices.
- State colors: restrained green/error for actual statuses only.
- Buttons: one visible primary action per workflow section, subdued secondary.
- Navigation: **Ordner & Quellen** is at least as prominent as the other
  main navigation links for IT/Owner.
- No visual reliance on color alone for success, unavailable sources,
  or player statuses.
- Mobile: readable single-column layouts, horizontal tab scroll where
  appropriate, at least 42px-high primary controls, reduced motion respected.

Keep backend role enforcement and all existing form names/CSRF tokens;
do not replace working player controls with decorative widgets.

## Technical UX guardrails

- Retain the existing page-specific CSS for functional placement; common
  product appearance is an additive CSS layer loaded last.
- Preview/lightbox rendering and modal focus behavior must remain untouched.
- Folder names are rendered with Jinja HTML escaping. They can contain
  umlauts and spaces; do not interpolate them into URLs.
- A root mount is not enough: show a clear pending/error state until the
  root-only mount helper has confirmed the requested server/UNC.
- **Do not automatically unmount or replace** a working SMB source when the
  operator edits its path.
- Verify browser rendering at desktop and narrow/mobile widths on the real
  operator setup; automated HTML/tests are necessary but not a screenshot
  or genuine display acceptance.

## Acceptance checklist

- [ ] Login, dashboard, library, source manager, playlist, scheduling and
  lightweight dialogs readable in both light and dark mode.
- [ ] Keyboard navigation, focus indication, toggles and reduced motion.
- [ ] Default root lists the intended child screen folders, no traversal or
  untrusted symlinks.
- [ ] IT can create one playlist from each folder, then select an Anthias
  test player; Marketing can edit image timing only.
- [ ] Test live RSS2Slideshow webpage playback on a real Anthias test Pi.
- [ ] Existing Bistro Pi continues with Binary Emotions until verified.
