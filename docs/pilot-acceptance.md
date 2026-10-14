# Anthias Hub pilot acceptance and release gate

Use a spare Anthias Pi and a real connected monitor. Do not run destructive tests on a production playlist. CI and `/healthz` are necessary but cannot prove Pi API compatibility, HDMI output, or TV playback. Record the date, Hub commit/image digest, Anthias version, Pi identity, monitor, operator and exact non-secret inputs and observed results. Keep passwords and internal addresses out of public issues.

**First-time Marketing usability test:** Print the [one-page Marketing practice checklist (PDF)](marketing-praxistest.pdf) for a colleague using a separate test Pi. Let the tester tick **Klappt** or **Unklar** for each task and jot down questions or requests without coaching. Collect the sheet alongside the technical acceptance evidence below. Use repeated stumbling points as input for later onboarding/crash courses; the sheet is not a substitute for this IT/production release gate.

## 1. Prepare and establish the boundary

- [ ] Record a backup of Hub `.env`, `config/`, `data/`, **and separately the Pi playlist/media**. Verify an off-host copy exists and restore each kind of backup to a disposable staging instance; check login, library manifests and media, and Pi content after restoration. Do not replace live state for this exercise.
- [ ] Deploy the tested Hub image to staging (pin a SHA or OCI digest). Record its running image ID and verify login, roles, device inventory, read-only playlist and `/healthz`. Leave production auto-deploy of `:main` disabled.
- [ ] Confirm the intended IT and Marketing accounts have distinct credentials and Marketing cannot add/edit/remove devices. Marketing currently has access to **every** registered screen; if teams must be separated by screen/location, stop and implement authorization before their rollout.
- [ ] From an actual Marketing workstation, verify the approved Hub HTTPS/VPN route works, while a direct request to each Pi management UI/API fails. From the Hub host/container verify the authorized Pi API is reachable. Record the source, target, port, test command and observed outcome. A Hub role check is not sufficient if the client can bypass the Hub.

## 2. Real player and monitor test (spare Pi)

For each operation, compare the Hub playlist with the Pi's native UI/API **and watch the physical display**. Record pass/fail and any difference. Keep a backup and known-good playlist ready.

- [ ] IT registers/edits/removes a spare device entry; removing it does not change Pi content. Viewer cannot perform writes.
- [ ] Marketing adds a website, image and MP4; confirm file handling, play order, actual display, video length and website reachability. Check an invalid file and an unreachable player show a usable error.
- [ ] Edit title and image/website duration (including a value over 120 seconds); pause and resume; drag-reorder with mouse, touch (if available) and keyboard; delete an item with confirmation. Verify each change in Pi and on screen. An open stale editor must not reverse a second user's pause/resume.
- [ ] Build a local library template, add URL and media, export and re-import its ZIP, and verify media integrity. Apply to an **empty** spare playlist; it must refuse a nonempty target without altering it.
- [ ] Append one library item and then a full template to a **nonempty** playlist; prior entries/order remain intact. Check duplicate-URL handling and inspect for duplicate media on retry.
- [ ] Import an ordinary media ZIP and a multi-file selection separately, both to library and to Pi; verify progress, per-file outcomes, size-limit errors and actual playback. A Hub-exported `manifest.json` ZIP belongs only in the backup-import action.
- [ ] Exercise a safe, controlled mid-transfer failure on the spare Pi (for example, interrupt its network after the first item). Confirm the partial-success warning, inspect the Pi before retrying, and recover manually. Neither apply nor append is atomic; rollback of the Hub image cannot undo Pi writes.
- [ ] Verify previews are of stored media, not live monitor screenshots; check missing media/unsupported types fail safely. Inspect logs and audit entries without leaking secrets.

## 3. Go / no-go

Ship to the intended internal audience only if: the exact image passed CI, the above operations passed on the installed Anthias version and physical display, access isolation was observed from the real client, and Hub **and Pi** restores were rehearsed. Obtain IT/Marketing sign-off, pin the approved image, retain a rollback image, and repeat login/API/display checks after promotion. Record any known limitations (including global Marketing access, static accounts, and absence of drafts/approvals). If any destructive operation or boundary check fails, remain in pilot and fix it first. Do not delay solely for cosmetic UI perfection; prioritize mistakes that could alter or delete screen content.
