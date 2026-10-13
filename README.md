# Anthias Hub

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

**Automatic pull-based CD (optional):** After the first manual migration to `compose.cd.yaml`, install the host-side systemd timer from [the CD runbook](docs/auto-deploy.md). It pulls the public GHCR image outbound after green CI, only restarts on a new image, checks local `/healthz`, rolls back on failure and quarantines a failing image. No inbound GitHub SSH access and no registry login are needed. The timer is **not** installed just by pulling this repository.

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
