# Anthias Hub

**Self-hosted control panel for multiple Anthias digital-signage players.**

[![Tests & Publish](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml)
[![MIT](https://img.shields.io/github/license/ffworker/anthias-hub)](LICENSE)
[![Docker](https://img.shields.io/badge/deployment-Docker-blue)](docs/reproducible-production.md)

Manage screens, playlists, local media and reusable content in one web UI. Each Raspberry Pi runs its own **Anthias** player; the Hub talks to its REST API. No cloud account, database or central player service is required.

**Status:** Actively developed, **not production-certified**. Automated tests do not replace testing uploads, schedules and playback on real Pi hardware. Do not expose the Hub or the players' management APIs to the public internet.

## Features

- **Screens and playlists:** Register players, view status, add/edit/reorder/pause content and preview stored media.
- **Local library:** Reusable templates, images, videos and websites. Import ordinary media ZIPs separately from Hub template-backup ZIPs. Append to existing playlists without replacing their contents.
- **Schedules:** Shared named schedule library across devices, independent device defaults, per-asset assignments and custom time windows. Scheduling runs natively on Anthias. See [scheduling](docs/scheduling.md).
- **Media:** PNG/JPEG/WebP/MP4, sequential batch uploads (up to 20 files) and ZIP import. Up to **4 GiB per file**, and **4 GiB total extracted media per ZIP**, subject to disk capacity and proxy limits. See [media import](docs/marketing-bulk-import.md).
- **Accounts:** Owner (IT + Marketing), IT, Marketing and Viewer. Marketing can edit content across **all** registered screens. Optional confirmed reboot/shutdown and experimental HDMI-CEC where supported.
- **Single-theme UI:** Nordlicht design, desktop/mobile layouts, no additional frontend framework.

## Quick start

Prerequisites: Linux, Docker Engine + Compose plugin, Git and a reachable Anthias player.

```bash
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
bash scripts/setup-pilot.sh --solo
curl -fsS http://127.0.0.1:8765/healthz
```

For separate IT and Marketing accounts omit `--solo`. Setup creates account hashes and a random session secret; it does not overwrite existing valid state. The default container binds **only** `127.0.0.1:8765`. Connect over an SSH tunnel:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 ADMIN@SERVER_IP
```

Open `http://127.0.0.1:8765`, sign in and register a player's private URL.

For regular LAN users, use a **restricted HTTPS reverse proxy**. The optional [Caddy guide](docs/network-access.md#d-optional-caddy--your-own-internal-https-ca-no-external-ca-required) explains a self-managed internal CA, browser trust on Windows, secure cookies and safely retiring direct HTTP. Installing a root CA grants broad trust; never distribute the CA private key.

## Running and updating

CI on `main` publishes `ghcr.io/ffworker/anthias-hub:latest` and a per-commit `:sha-<FULL_SHA>` image. The optional **test-VM** auto-updater follows `:latest`; use an approved immutable image reference and manual promotion for production.

If your deployment uses `compose.cd.yaml` and an external Compose override, **include both files in every manual command**:

```bash
cd ~/apps/anthias-hub
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || exit 1

# Restart the existing container (does not reload .env changes):
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub restart anthias-hub

# Apply changed .env / Compose settings to the Hub only:
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub up -d --no-build --no-deps --force-recreate anthias-hub
```

**Do not run plain `docker compose up -d --build` on a pull-based installation.** It selects the local-build `compose.yaml` and may restore obsolete bindings. First-time installations without an override follow the setup script instead. For full operations see [auto-deploy](docs/auto-deploy.md), [installation and release management](docs/reproducible-production.md), and [network access](docs/network-access.md).

### Current deployment feedback

On **16 October 2026**, the operator reported a working internal HTTPS login through a host-side Caddy reverse proxy, `COOKIE_SECURE=1`, `TRUSTED_PROXY_COUNT=1`, and an Anthias Hub container exposed only on `127.0.0.1:8765`. A browser warning disappeared after the Caddy root CA was trusted on the operator's Windows workstation; other devices need their own approved trust installation. The separate RSS2Slideshow container remains independent. **This is staging feedback, not a certified production deployment or proof of backup restoration.**

## Documentation

| Guide | When to use it |
| --- | --- |
| [Network / Caddy HTTPS](docs/network-access.md) | LAN access, client CA trust, CSRF and TLS |
| [Test-VM auto-deploy](docs/auto-deploy.md) | GHCR `:latest`, timer, rollback and manual Compose |
| [New host and controlled releases](docs/reproducible-production.md) | Reproducible install, backups and approved images |
| [IT administration](docs/IT_ADMIN_GUIDE.md) | Accounts, maintenance, Pi routes and recovery |
| [SSH and host hardening](docs/ssh-access.md) | Secure administrator access |
| [Shared schedules](docs/scheduling.md) | Device defaults, assignments and Anthias semantics |
| [Media / ZIP import](docs/marketing-bulk-import.md) | Limits, storage checks and partial transfers |
| [Acceptance checklist](docs/pilot-acceptance.md) | Real Pi testing and release readiness |
| [Co-hosted staging](docs/cohosted-staging.md) | Optional separate RSS2Slideshow VM workflow |

Also see [Security](SECURITY.md), [License](LICENSE) and [Changelog](CHANGELOG.md). The UI is in German; documentation is a mix of German and English.

## Development

Backend: Python/Flask, server-rendered templates, plain JavaScript and CSS. `style.css` provides the base, `modern.css` the Nordlicht theme, `workspace.css` shared layout, page-specific styles load through `extra_head`, and `ui-refinements.css` loads **last**. Keep form controls, popovers and grids responsive; do not add a second theme or framework.

```bash
python -m pytest -q
node --test tests/*.test.cjs
```

## License and attribution

Anthias Hub is a standalone **MIT-licensed** REST client. It neither bundles the Anthias player nor claims affiliation with, sponsorship from or support by Screenly or the Anthias maintainers. Anthias runs separately and retains its own licenses. See [licensing notes](docs/LICENSING.md).
