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

> **Pilot status (13 October 2026):** API reachability and reading a real Anthias Pi playlist have been confirmed by the operator. Writing, upload, delete, player compatibility across versions, and company-wide Marketing deployment have **not yet been fully validated**. Do not expose the pilot directly to the internet.

## Features

| Feature | IT | Marketing | Viewer |
| --- | :---: | :---: | :---: |
| Sign in with a static account | ✓ | ✓ | ✓ |
| Device list, API status and playlist preview/list | ✓ | ✓ | ✓ |
| Register, edit and remove device connections | ✓ | — | — |
| Link to the native Anthias administration | ✓ | — | — |
| Add websites / upload PNG, JPEG, WebP, MP4 (max 50 MB) | — | ✓ | — |
| Rename, activate/deactivate, reorder, delete playlist items | — | ✓ | — |

The hub connects to **Anthias REST API v2** on each registered player. Media and playlists stay on the player, and edits take effect directly there. Changes are **per device**; group actions may be considered later. A playlist list is *not* a real screenshot or verification of what the TV is displaying.

**There is no dependency on RSS2Slideshow or any other news-kiosk software.** Any reachable webpage may be used as an ordinary Anthias website asset. This repository does **not** bundle Anthias itself.

## Deployment modes: test VM versus future production

**Our current VM is a disposable test environment, not the long-term production server.** Reinstall the final VM from a documented source commit/image instead of cloning experiments from the test host.

- **Test/staging:** use the existing local `compose.yaml` or the optional `:main`-following automatic updater in [the test-only CD guide](docs/auto-deploy.md). Every green `main` push currently publishes a new image; if the timer is installed, it may then deploy it.
- **Future production:** use [the reproducible new-VM and release runbook](docs/reproducible-production.md). Pin `ANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-<APPROVED_FULL_SHA>` with `compose.cd.yaml`, deploy only after manual approval and keep a tested rollback image. **Do not enable today's auto-deploy timer on production:** the script currently forces `:main`.
- **Co-located RSS2Slideshow:** on the planned VMware vSphere VM, RSS remains a separate local-build Compose app with CI checks and deliberately **manual** updates after approval; Hub's timer never updates RSS. Debian 13 minimal (amd64), 4 vCPU, 8 GB RAM and 80 GB SSD are initial sizing with headroom, not measured consumption. See [the new-VM runbook](docs/reproducible-production.md) and the [RSS manual-update guide](https://github.com/ffworker/rss2slideshow/blob/main/docs/manual-vm-deploy.md) (private repository).
- **Image names:** `:main` tracks the integration branch today. Future `:latest` could mean *latest built* (not production-safe), `:stable` *latest approved release* (moving pointer), and `:vX.Y.Z` *named, approved version*. For a truly reproducible VM pin `:sha-<FULL_SHA>` today, ideally an OCI `@sha256:...` digest. `:stable`, `:latest` and `:vX.Y.Z` **are not currently published by CI**; a Git tag alone does not create those image tags. No separate `live` Git branch is needed.

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

**Access from Windows:** Open PowerShell on the client:

~~~powershell
ssh -N -L 8765:127.0.0.1:8765 ADMIN@YOUR-DOCKER-HOST
~~~

Then open http://localhost:8765 in the browser. The Compose port intentionally binds to **127.0.0.1** on the server. Connecting directly to the host's LAN IP on port 8765 will not work and must not be "fixed" with a broad firewall rule.

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
- [First Docker deployment](docs/deploy-docker-host.md): isolated pilot, SSH tunnel and safe access.
- **[Reproducible fresh VM & controlled releases](docs/reproducible-production.md):** approved SHA-pinned image, backups, manual promotion, verification, rollback and future release-channel design.
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
