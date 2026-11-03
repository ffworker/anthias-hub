# Changelog

This file summarizes the **current feature baseline and meaningful changes**.
For individual commits and historical implementation decisions, use
[GitHub history](https://github.com/ffworker/anthias-hub/commits/main).

## 2026-11-03 — Feature freeze and operator-confirmed pilot status

- **Feature set complete; maintenance-only phase.** No new features planned; handle only demonstrated defects, necessary security/compatibility work and small UI corrections.
- **Operator-confirmed practical checks:** multiple weeks of stable operation; edited image, website and playlist content verified on physical displays; recurring scheduling; screen on/off and Raspberry Pi power/device controls. These observations describe the existing installation, not an independent or full fleet-wide acceptance test.
- **Pending before formal production approval:** off-host Hub and Pi backups with restoration rehearsal, reproducible onboarding for additional players, real-client access-boundary checks, and approved/pinned production version with rollback instructions.
- **Architecture:** Anthias continues playback and local scheduling per Pi without the Hub. Direct Anthias UI remains a supported maintenance fallback; RSS2Slideshow is a separate website service that must itself remain reachable for live RSS content.

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
