# Licensing, independence and public release checks

**Independent third-party project.** Anthias Hub is not developed, sponsored, endorsed or supported by Screenly, Inc. or the Anthias maintainers. The name is descriptive of the supported interface, not a claim of affiliation. Do not use the official Anthias/Screenly logo as the Hub's project branding or copy upstream UI assets without permission.

## Licensing summary

| Component | License / owner | Relationship |
| --- | --- | --- |
| Anthias Hub application source | MIT, see ../LICENSE | Our separate app: UI, auth, device inventory and HTTP client |
| Anthias player (not included here) | Dual GPLv2 / commercial, see https://github.com/Screenly/Anthias/blob/master/LICENSE | Software running on a different device, contacted via REST API v2 |
| Flask | BSD-3-Clause | Installed Python dependency |
| Requests | Apache-2.0 | Installed Python dependency |
| Gunicorn | MIT | Installed Python dependency |
| Python Docker base image and transitive Python packages | Each keeps its own license | Review when distributing container images |

The official Anthias FAQ (https://anthias.screenly.io/faq/) confirms GPLv2 + commercial licensing. **Anthias Hub does not bundle, link with, copy, patch, fork or redistribute Anthias source or binaries**. An independently authored application exchanging HTTP messages with a separate GPLv2 server normally can have a different license, including MIT; the API boundary alone does not generally impose GPLv2 on an independent program.

**Important qualification:** This is a technical licensing assessment, not legal advice or a comprehensive provenance audit. If the product ever embeds/redistributes Anthias, reuses its code or images, distributes a modified Anthias player, or ships Pi appliances, examine GPLv2 obligations and any separate commercial license before distributing. If you ship prebuilt Docker images, preserve upstream dependency license notices and inspect transitive dependencies.

## Copyright and reuse

Anthias Hub is a separately authored project released under MIT; preserve the copyright notice when distributing copies or substantial portions. Only contributors with rights to their contributions may grant a license. Commercial use and support are permitted by MIT; no paid edition or proprietary license key is required. For material copied from elsewhere, confirm attribution and license compatibility before publication.

## Pre-publication / commercial distribution checklist

- [ ] Confirm ownership and contributor rights for any code released.
- [ ] Verify no internal inventory, identifying names, credentials, private addresses, real deployment screenshots or secrets exist in tracked files, **Git history**, tags, releases or workflow logs.
- [ ] Retain this repo's MIT LICENSE and copyright holder statement only if legally correct.
- [ ] Retain third-party notices for redistributed libraries/images and comply with their actual versions' terms.
- [ ] Distinguish the upstream Anthias player (GPLv2/commercial) from the independent REST client (MIT).
- [ ] No official Anthias/Screenly logo, trademark implication or misleading endorsement.
- [ ] Disclose that the app is a limited **self-hosted internal pilot**, not a vendor-supported SaaS.
- [ ] If the scope changes to distribution of modified player binaries, get a specific license review.

The project is technically separable from any particular website or news kiosk. It needs only reachable Anthias-compatible players. A third-party website (newsfeed, menu, dashboard) can be placed in Anthias as a normal URL; no application-specific integration is required.
