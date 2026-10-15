# Anthias Hub UI/UX review – approved decisions

**Status:** implementation specification for the approved Nordlicht-only UI refresh.
**Scope:** UI, navigation, text, icons and responsiveness only. Do not change Anthias APIs, persistence, role boundaries, SSH or deployment behavior.

## Decisions 1–12

| # | Area | Approved |
|---|---|---|
| 1 | Main navigation | Filled active tab with `aria-current="page"`. |
| 2 | Desktop header | Keep logo, navigation, username/role and logout separately; improve spacing. The color picker disappears because only one theme remains. |
| 3 | Mobile header | Two rows; logo/user actions first, two fully labelled tabs below. |
| 4 | Devices | Compact screen cards with the playlist action prominent. |
| 5 | Status / controls | Honest API availability badge and playlist count. IT sees two collapsible actions, **Steuern** and **Verwalten**; Marketing sees only its existing reboot help. |
| 6 | Playlist items | Slightly condensed visual cards. Preserve preview, drag handle, keyboard reordering, inline edit/save, pause and deletion. |
| 7 | Add drawer | Three equal tabs: **Bild / Video**, **Bibliothek**, **Webseite**; top and bottom add buttons (empty-state CTA remains). |
| 8 | Upload | Single upload visible; multi-file/ZIP import collapsible. Short labels and preserved independent progress/error handling. |
| 9 | Drawer library | Single item as default; collection picker filters item picker; whole-template append collapsible and requires an explicit acknowledgement. |
| 10 | Library overview | Templates on the left, small create form on the right; media uploads live *inside* a template. Backup restore remains separately available. |
| 11 | Template detail | Compact publishing panel; numbered list, previews, up/down ordering; per-item actions under ellipsis; template backup export and deletion under **Vorlagenoptionen**. |
| 12 | Finish | Consistent status/errors, local SVG icon set, readable typography, **Nordlicht only**, robust mobile layouts and consistent Marketing/IT terminology. |

## Behavioral invariants

- **Bibliothek speichern != zur Playlist hinzufügen.** Library uploads never publish a screen by themselves.
- Template append adds to, never silently replaces, the existing playlist.
- Maintain three roles: Marketing may edit content, IT may configure/control registered devices, Viewer may only read.
- CSRF and device/action allowlists, explicit confirmations (including exact name for shutdown/clear), audit records and safe uncertain-response behavior remain intact.
- Only API health is observable, not the HDMI output or TV power. No screenshot/VNC functionality is included.
- Retain normal ZIP-media imports separately from Hub manifest backup restore.
- Keep normal browser upload and bulk import progress states; a 100% transfer to Hub is not proof of finished Anthias transfer.
- No extra frontend framework or external icon dependency. No deployment or Pi operations as part of UI changes.

## Acceptance checks

- `python -m pytest -q`
- `node --test tests/playlist-ui.test.cjs tests/playlist-studio-ui.test.cjs tests/playlist-bulk-ui.test.cjs`
- Check IT, Marketing and Viewer pages as well as direct unauthorized POSTs.
- Verify desktop 1440/1024 and mobile 768/390/320 CSS pixels, 200% zoom, touch and keyboard focus; no clipped drawers or menus.
- Exercise single/bulk uploads, media previews, library transfers, reordering, status/errors, destructive confirmations and logout.
- Test a real Anthias Pi only in an independently authorized acceptance pass. CI does not use live devices.
