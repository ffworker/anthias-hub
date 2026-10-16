# Anthias Hub

**A lightweight, self-hosted dashboard for managing multiple Anthias digital-signage players.**

[![Tests & Publish](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/ffworker/anthias-hub/actions/workflows/tests.yml)
[![MIT License](https://img.shields.io/github/license/ffworker/anthias-hub)](LICENSE)
[![Pilot](https://img.shields.io/badge/status-pilot-orange)](docs/pilot-acceptance.md)
[![Docker](https://img.shields.io/badge/deployment-Docker-blue)](docs/deploy-docker-host.md)

Anthias Hub gives solo Raspberry Pi enthusiasts and small teams one interface to view connected screens, edit their individual playlists, upload media, and reuse content. The **Anthias player still runs on every Pi**; Hub talks to the player over its REST API. No cloud service, database, subscription, or separate central CMS required.

> **Pilot software, not production-certified.** API connectivity and read-only playlist display have been observed. On **15 October 2026**, the operator also reported successful use of the library's **import/export and template-backup functions**. This is field feedback, **not** proof of a complete Hub-host or Pi backup/restore. Player write/upload/delete compatibility across real player versions, power controls and recovery still require on-device acceptance. Do not put the current application directly on the public internet. See [pilot acceptance](docs/pilot-acceptance.md) and [security boundaries](SECURITY.md).

## Features

- **Screen overview** – register individual players, view connectivity and playlists.
- **Playlist studio** – add websites, PNG/JPEG/WebP/MP4, reorder and edit individual items.
- **Reusable library** – save playlists and media, import/export template ZIPs, append items to players. Single MP4 uploads and media-ZIP imports up to 4 GiB (pilot/test; at most 4 GiB unpacked per media ZIP) are supported with streaming and conservative per-player disk-space checks (reserve of at least 2 GiB or 20%, whichever is larger, plus room for two temporary copies). Automatic Pi uploads use the Anthias API free-space reading directly; no per-device storage attestation required. For history and limitations on external media mounts, see the [large-upload audit](docs/large-upload-audit.md).
- **Role-based access** – **Owner** (both device and playlist administration), **IT** (devices), **Marketing** (playlists), **Viewer** (read-only). Existing IT/Marketing installations keep their accounts.
- **Optional remote power controls** – reboot/shutdown and experimental HDMI-CEC on supported players; actions require confirmation.
- **Independent, self-hosted** – Docker Compose and local configuration, with optional internal network access and HTTPS termination.

## Quick start

Prerequisites: Linux with Docker Engine + Compose plugin, Git, OpenSSL and a network route to an existing compatible Anthias Pi.

```bash
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
bash scripts/setup-pilot.sh --solo  # one Owner account for a solo installation
# Alternatively: bash scripts/setup-pilot.sh (separate IT and Marketing accounts)
curl -fsS http://127.0.0.1:8765/healthz
```

The setup interactively creates strong credentials and a random application secret. It does not overwrite an existing `.env` or valid accounts. It binds the web port to **127.0.0.1:8765** by default (not to your LAN). Use an SSH tunnel from your workstation:

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 ADMIN@SERVER_IP
```

Open **http://127.0.0.1:8765** locally, log in and register your Anthias player's **private IP**. The web UI is currently German; the public documentation is English. Successful `/healthz` alone does not prove the Pi or TV works.

For a colleague or another LAN machine, see the optional [network access guide](docs/network-access.md): isolated direct LAN HTTP for limited tests, or **HTTPS through an existing reverse proxy** for regular users. No extra proxy container is installed by default.

## Roles

| Capability | Owner | IT | Marketing | Viewer |
| --- | :---: | :---: | :---: | :---: |
| View registered screens and library | ✓ | ✓ | ✓ | ✓ |
| Register, edit, remove players | ✓ | ✓ | – | – |
| Edit playlists and local library | ✓ | – | ✓ | – |
| HDMI-CEC and Pi shutdown | ✓ | ✓ | – | – |
| Confirmed Pi reboot | ✓ | ✓ | ✓ | – |

Every Marketing user currently has access to **all** registered screens. Player API access must be restricted at the network layer; Hub role checks do not secure a Pi reachable directly from another client.

## Deployment, operations and development

- [Optional LAN / HTTPS deployment](docs/network-access.md) – DNS examples use placeholders only.
- [Docker host deployment](docs/deploy-docker-host.md) – setup, local access and administration.
- [Security model](SECURITY.md) – boundaries, secrets, authentication, backups and reporting.
- [IT administration guide](docs/IT_ADMIN_GUIDE.md) – maintenance, roles and recovery.
- [Controlled releases / new host](docs/reproducible-production.md) – image pins, rollout and rollback.
- [Test-only auto-deploy](docs/auto-deploy.md) – follows `:latest`, with health check and automatic rollback.
- [Marketing bulk import](docs/marketing-bulk-import.md) · [UI behavior](docs/ui-ux-review.md)
- [Pilot acceptance checklist](docs/pilot-acceptance.md) · [Changelog](CHANGELOG.md)

Successful `main` CI runs publish `ghcr.io/ffworker/anthias-hub:latest` for the test VM, plus a per-commit `:sha-<FULL_COMMIT_SHA>` image for traceability and recovery. **No alpha, beta or stable release channels are configured.** Real-device verification is still required before any production promises.

## License & upstream

Anthias Hub is an independently authored third-party REST API client under the **[MIT license](LICENSE)**. It does **not** bundle the Anthias player, whose source and licenses are separate. This project is **not affiliated with, endorsed by or supported by Screenly, Inc. or the Anthias maintainers**. See [licensing notes](docs/LICENSING.md). Contributions and bug reports are welcome, but **never include private credentials, real internal URLs or employee/company data** in public issues.
