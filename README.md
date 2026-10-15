# Anthias Hub

[![Tests & Publish](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml)
[![GHCR Container](https://img.shields.io/badge/container-GHCR-2496ED?logo=docker&logoColor=white)](https://github.com/ffworker/anthias-hub/pkgs/container/anthias-hub)
[![MIT License](https://img.shields.io/github/license/ffworker/anthias-hub)](LICENSE)
[![Status: Pilot](https://img.shields.io/badge/status-pilot-e9a23b)](#quick-deployment-linuxdocker-internal-test-only)
[![Self-hosted](https://img.shields.io/badge/deployment-self--hosted-61cab8)](docs/deploy-docker-host.md)
[![Branch: main](https://img.shields.io/badge/branch-main-465d76?logo=git)](https://github.com/ffworker/anthias-hub/tree/main)

[**CI / Workflows**](https://github.com/ffworker/anthias-hub/actions) · [**Container images**](https://github.com/ffworker/anthias-hub/pkgs/container/anthias-hub) · [**Branches**](https://github.com/ffworker/anthias-hub/branches) · [**Issues**](https://github.com/ffworker/anthias-hub/issues) · [**Release & VM runbook**](docs/reproducible-production.md)

**Independent self-hosted management interface for multiple Anthias players.**

**IT manages devices. Marketing manages individual playlists.** No central CMS, database, media-server rewrite, or per-screen license. Anthias Hub is a **third-party project** and is **not affiliated with, sponsored by, or officially supported by Screenly, Inc. / Anthias**.

> **Pilot status (13 October 2026):** API reachability and reading a real Anthias Pi playlist have been confirmed by the operator. Writing, upload, delete, player compatibility across versions, and company-wide Marketing deployment have **not yet been fully validated**. Do not expose the pilot directly to the internet. Use the [real Pi/monitor pilot acceptance gate](docs/pilot-acceptance.md) before internal rollout. Hand a first-time Marketing tester the [**one-page printable practice checklist (PDF)**](docs/marketing-praxistest.pdf) to mark what worked, what was unclear, and what should be improved.

## Features

| Feature | IT | Marketing | Viewer |
| --- | :---: | :---: | :---: |
| Sign in with a static account | ✓ | ✓ | ✓ |
| Device list, API status and playlist preview/list | ✓ | ✓ | ✓ |
| Register, edit and remove device connections | ✓ | — | — |
| Link to the native Anthias administration | ✓ | — | — |
| Add websites / upload PNG, JPEG, WebP, MP4 (max 50 MB) | — | ✓ | — |
| Rename, activate/deactivate, reorder, delete playlist items | — | ✓ | — |
| Delete entire local library templates (typed-name confirmation) | — | ✓ | — |

**Media thumbnails:** The player playlist and local playlist-library detail views now show small image previews and lazy, muted video stills in place of generic icons. These are **media-file previews, not a live capture of the television**. The Hub serves previews only to logged-in users from a registered Anthias device's fixed asset-preview path (or an existing, verified library file); it does not follow redirects to arbitrary external media. Older Anthias versions, remote URL assets, missing files, oversized images, or blocked media requests fall back to the original icon. Video metadata loading may download part of a clip; it never autoplays. The full Pi/display still requires on-site verification.

The hub connects to **Anthias REST API v2** on each registered player. Media and playlists stay on the player, and edits take effect directly there. Changes are **per device**; group actions may be considered later. A playlist list is *not* a real screenshot or verification of what the TV is displaying.

**Marketing pilot improvements (14 October 2026):** Upload forms on both player playlists and local library pages now show the selected filename/size, browser-to-Hub upload percentage, a distinct server/player processing stage, and clear success/error messages. **100% only means the browser finished sending data to Hub**; Anthias processing may still be underway. For uncertain player transfer failures, inspect the Pi playlist before retrying to avoid duplicates. Clicking an image or video thumbnail opens an accessible, keyboard-closeable large preview; videos have native play/pause controls and never autoplay. The preview is not a live TV capture. In a screen's `Bibliothek` add-content tab, Marketing can now append **one selected reusable library item** to a nonempty playlist, or choose `Zu Bildschirm` next to a saved item in its library template. Existing assets are not replaced/reordered. Changes take effect immediately on Anthias; no drafts/approvals or automatic rollback exist yet.

**Playlist-Bibliothek (new, staging-first):** Marketing can create reusable templates from URLs and locally uploaded PNG/JPG/WebP/MP4 files under `data/library/`, reorder them, export/import portable ZIPs, and transfer a **whole** template to a selected **empty** Anthias playlist. The destination is checked immediately before transfer; existing content is never replaced. This is not an atomic multi-file operation: after a partial failure, inspect the Pi before retrying. The archive contains only Hub-library media, not media previously uploaded directly to a Pi. Back up `data/library/` off-host alongside the rest of `data/`; it is not recreated by Git or the Docker image. Test uploads and output on a spare player before using the feature for Marketing production.

**ZIP & multi-file uploads (Marketing pilot):** Choose one ordinary ZIP archive containing PNG/JPG/WebP/MP4 media or select up to 20 files without zipping. Import into an existing **library template** or directly append to a **screen playlist**. Browser upload percentage, per-file results and partial-failure warnings are shown; existing player entries are never cleared. This is different from **Playlist-ZIP importieren**, which still expects a Hub-exported archive with `manifest.json`. [Step-by-step workflow and security limits](docs/marketing-bulk-import.md).

**Playlist Studio 2.0 (pre-pilot):** The screen playlist now uses the full available width, with cleaner media cards. Click a card to open its inline title/duration and pause/delete actions; only one card can be open at a time, and unsubmitted edits require explicit discard. The existing media preview is a separate thumbnail action; drag handles still work with mouse, touch and keyboard. `Inhalt hinzufügen` opens an accessible right-side panel on desktop and a full-screen panel on mobile, with image/video and library import prioritized over optional website URLs. Without JavaScript, the forms remain available below the playlist. **Marketing can now delete an entire saved library template** from the library overview or its detail header using an exact-name confirmation and acknowledgment. This permanently deletes only Hub-local template items and their stored media; **it never clears a Pi playlist, deletes a device, or removes already-transferred Pi assets**. Back up `data/library/` before permanent deletion; restoration requires an existing backup ZIP.

**Media-first Marketing workflow:** On a player playlist, **Bild / Video** opens by default, **Bibliothek** is the other primary choice, and **Optional: Webseite** is a smaller secondary control for occasional links such as RSS2Slideshow. In a saved library template, single-media upload and bulk-media ZIP import appear before the collapsed **Optional: Webseite verlinken** form. The existing URL endpoints, CSRF and Marketing permissions remain unchanged. This presentation-only change also preserves the separate pause/resume state safety fix from [PR #9](https://github.com/ffworker/anthias-hub/pull/9): changing title or duration must never overwrite `is_enabled`.

**Import paths are distinct:** The library overview prominently offers **ordinary image/video ZIP upload**, with a required target library template, while **Restore Anthias-Hub backup** is a secondary, expandable action for Hub-exported `manifest.json` ZIPs only. The playlist editor can now append **an entire saved template** to an existing screen playlist (or one selected item), without clearing existing content. Marketing edits an item's **title, precise 5–120 second slider, exact numeric duration (5–3600 seconds) and Save button directly in the compact playlist toolbar** next to reorder and delete (videos auto-duration). Manual values above the slider's maximum remain unchanged until explicitly saved. **Playlist UI polish:** Sorting is drag-handle only (no visible up/down arrows); mouse and touch users drag the grip, keyboard users focus it, press Space, move with ↑/↓, then Enter to save or Escape to cancel. Changes are sent as an optimistic-baseline reorder and the original order returns if rejected. Drag/drop displays a clear target line and completion feedback. The edit **Save button activates only for changed titles/durations** (and confirms successful save); normal no-JavaScript editing still works. Delete is a small, labelled trash icon with the existing protected confirmation.

The editing inputs remain inline; **Save and Delete now sit together as an aligned action group at the right edge** instead of drifting apart. Delete still requires explicit confirmation, with its expanded confirmation separate from the normal compact row. On smaller screens the paired actions move below the fields; Save remains explicitly triggered (including without JavaScript), and pause/resume remains separate. **Publishing an entire saved template** is now a prominent primary action directly below the template heading (with target screen picker and confirmation), rather than being buried beneath media upload forms. Details: [media and template import guide](docs/marketing-bulk-import.md).

**There is no dependency on RSS2Slideshow or any other news-kiosk software.** Any reachable webpage may be used as an ordinary Anthias website asset. This repository does **not** bundle Anthias itself.

## Deployment modes: test VM versus future production

**Our current VM is a disposable test environment, not the long-term production server.** Reinstall the final VM from a documented source commit/image instead of cloning experiments from the test host. On the fresh host, first configure a **non-root SSH admin with an ED25519 key, a client-side SSH alias and verified key-only access**, then disable SSH root/password logins only after a successful second session: [SSH/tunnels & VM hardening (PowerShell or Linux)](docs/ssh-access.md).

- **Test/staging:** use the existing local `compose.yaml` or the optional `:main`-following automatic updater in [the test-only CD guide](docs/auto-deploy.md). Every green `main` push currently publishes a new image; if the timer is installed, it may then deploy it.
- **Future production:** use [the reproducible new-VM and release runbook](docs/reproducible-production.md). Pin `ANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-<APPROVED_FULL_SHA>` with `compose.cd.yaml`, deploy only after manual approval and keep a tested rollback image. **Do not enable today's auto-deploy timer on production:** the script currently forces `:main`.
- **Co-located RSS2Slideshow:** on the planned VMware vSphere VM, RSS remains a separate local-build Compose app with CI checks and deliberately **manual** updates after approval; Hub's timer never updates RSS. Debian 13 minimal (amd64), 4 vCPU, 8 GB RAM and 80 GB SSD are initial sizing with headroom, not measured consumption. See [the new-VM runbook](docs/reproducible-production.md) and the [RSS manual-update guide](https://github.com/ffworker/rss2slideshow/blob/main/docs/manual-vm-deploy.md) (private repository).
- **Image names:** `:main` tracks the integration branch today. Future `:latest` could mean *latest built* (not production-safe), `:stable` *latest approved release* (moving pointer), and `:vX.Y.Z` *named, approved version*. For a truly reproducible VM pin `:sha-<FULL_SHA>` today, ideally an OCI `@sha256:...` digest. `:stable`, `:latest` and `:vX.Y.Z` **are not currently published by CI**; a Git tag alone does not create those image tags. No separate `live` Git branch is needed.

## Shared GH-PiHub test VM (both applications)

Already cloned **Anthias Hub + RSS2Slideshow** into sibling folders? Use the safe [two-app test-VM bootstrap](docs/gh-pihub-test-vm.md): `bash scripts/bootstrap-test-vm.sh doctor` to inspect prerequisites, then `init` only if needed, `deploy` explicitly to build/start both apps, and `status` to check them. Existing credentials, feeds and runtime state are not overwritten. The RSS repo remains private and independently deployed; this is **not** the approved production workflow.

## Quick deployment (Linux/Docker; internal test only)

Requirements: Docker Engine + Compose plugin, Git, OpenSSL, curl, route from the host to the authorized Pi network.

~~~bash
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
bash scripts/setup-pilot.sh
docker compose -p anthias-hub ps
curl -fsS http://127.0.0.1:8765/healthz
~~~

The interactive setup creates a random session secret and prompts for **distinct** IT and Marketing passwords (minimum 12 characters). It works for a normal Docker-capable host user **or as root**; the container still runs with an unprivileged UID/GID (10001:10001 after root-driven setup). The script refuses to overwrite an existing .env. Re-running it is not the update procedure.

**Updating an existing checkout:** `git pull --ff-only && docker compose -p anthias-hub up -d --build`. Do **not** run `docker compose pull` for this Compose file: its `image: anthias-hub:pilot` is a locally built tag, not a Docker Hub repository. The CI-published image is separately available as `ghcr.io/ffworker/anthias-hub:main`; using it requires an explicit Compose image change, not a pull of `anthias-hub:pilot`.

**Automatic pull-based CD (test VM only, optional):** After manual migration to `compose.cd.yaml`, the timer in [the test-only CD runbook](docs/auto-deploy.md) follows `:main`, checks `/healthz`, and attempts rollback on failure. That is convenient for a **disposable test VM** but does **not** constitute an approval-gated production release process. It is not installed by cloning the repository. See [controlled releases](docs/reproducible-production.md) for the future VM.

**Appearance:** The header’s Design menu offers Nordlicht (dark teal), Tageslicht (light) and Kupfer (warm dark). The choice is stored only in the current browser (`localStorage`), not in Hub accounts, playlists or on the Pis. Editor controls remain in their original forms/API routes: move controls beside each item, edit in the item’s action bar, add content in the dedicated composer.

**Access from PowerShell or Linux/macOS (SSH-key + alias):** Choose your operating system in the [expandable setup guide](docs/ssh-access.md). Use `ssh gh-pihub` for a shell or start **both** localhost-only forwards with:

~~~powershell
ssh -N gh-pihub-tunnel
~~~

Then open **http://127.0.0.1:8765** (Hub) and, if RSS2Slideshow is installed on that same host, **http://127.0.0.1:8085** (RSS). Both forwards bind to your own PC's loopback address. The VM Compose ports intentionally bind to **127.0.0.1** on the server; don't expose them broadly to 'fix' direct LAN access. If you only need one forward, the [guide](docs/ssh-access.md) also shows `ssh -N -L ... gh-pihub`.

For ordinary company-user access, first set up a restricted internal **HTTPS reverse proxy / VPN**, set COOKIE_SECURE=1, and isolate Anthias player-management ports. Direct access to the Pi can otherwise bypass the hub's role checks.

## Architecture

~~~text
IT -----------------------------------> Hub web UI -> device inventory/diagnostics
Marketing --login-> Anthias Hub ------> Anthias Pi #1 -> Screen #1
                     (REST API v2) +--> Anthias Pi #2 -> Screen #2
                                  +--> Anthias Pi #N -> Screen #N

Website assets are external URLs independently configured on Anthias.
~~~

The hub is a small Flask + Gunicorn service with file-based storage. No PostgreSQL, Redis, Kubernetes, cloud account or proprietary signage backend is needed. Local instance state (not in Git):

- .env — session secret, cookie/network and runtime UID/GID settings
- config/users.json — scrypt password hashes and roles
- data/devices.json — device inventory (private IPs)
- data/audit.jsonl — basic write-event history

The current Marketing role applies to **all** registered screens; no per-location authorization yet.

## Documentation

- **[IT Administrator Guide](docs/IT_ADMIN_GUIDE.md):** architecture, deployment, permission model, account/password maintenance, backups/restores, updates, logs, troubleshooting, operational checks.
- **[SSH keys, selectable PowerShell/Linux steps & VM hardening](docs/ssh-access.md):** non-root administrative access, shared SSH alias, both application tunnels and lockout-safe hardening.
- [First Docker deployment](docs/deploy-docker-host.md): isolated pilot, SSH tunnel and safe access.
- **[Reproducible fresh VM & controlled releases](docs/reproducible-production.md):** approved SHA-pinned image, backups, manual promotion, verification, rollback and future release-channel design.
- **[Pilot acceptance and release gate](docs/pilot-acceptance.md):** real Pi/monitor test matrix, client-to-Pi isolation, restore rehearsal, and go/no-go criteria.
- [Security boundary](SECURITY.md): roles, firewall/HTTPS, session and upload limitations.
- [License and independence](docs/LICENSING.md): GPLv2 upstream, independent MIT API client, attribution, employer-rights and release checklist.
- [Official Anthias API](https://anthias.screenly.io/api/)

## Developers / CI

~~~bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app scripts wsgi.py
~~~

CI uses Python 3.12 and runs offline tests; **green unit tests are not proof of compatibility with any particular installed Pi**. Pilot write operations should be tested on a spare player and backed up independently.

## License and upstream credit

Project-authored Anthias Hub source is under **MIT** ([LICENSE](LICENSE)). The separate Anthias player is **dual-licensed GPLv2/commercial** and has its own terms. Anthias and Screenly names are used to identify compatibility, not sponsorship. See [licensing and rights considerations](docs/LICENSING.md), especially if employer-developed code or bundled commercial appliances are involved.
