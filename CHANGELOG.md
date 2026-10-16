# Changelog

This file summarizes the **current feature baseline and meaningful changes**.
For individual commits and historical implementation decisions, use
[GitHub history](https://github.com/ffworker/anthias-hub/commits/main).

## 2026-10-16 — Current main baseline

- Shared hub-wide named schedules, per-device defaults and playlist item assignments, with native Anthias scheduling and explicit synchronization.
- Compact Nordlicht-only fleet, playlist and library UI; accessible responsive controls and template publication.
- Media/library upload limits up to **4 GiB per media file** and **4 GiB per ordinary media ZIP (including extracted contents)**. Sequential batch uploads, disk-backed streaming, storage checks using Anthias `/api/v2/info.free_space`, conservative reserves and partial-transfer feedback.
- Owner, IT, Marketing and Viewer role model, CSRF protection, session-cookie diagnostics and optional player power controls.
- GHCR `:latest` for disposable test-VM automatic updates; SHA images for reproducible, explicitly approved deployments.
- Optional host-local Caddy HTTPS with an internal CA. Operator-confirmed working HTTPS login and Windows CA trust. Each additional workstation must trust the verified public root independently or through a managed rollout.

## Operational limitations

- Real-Pi compatibility, physical TV playback and 4-GiB uploads are not comprehensively certified; follow the [acceptance checks](docs/pilot-acceptance.md).
- The Hub library backup is **not** a backup of Hub credentials/configuration or a Pi's media/playlist. Rehearsed off-host restores are still required.
- Marketing currently has access to content on all registered screens. Pi management APIs must be protected at the network layer.
- The test-VM `:latest` channel is not a production release process. See [controlled releases](docs/reproducible-production.md).
