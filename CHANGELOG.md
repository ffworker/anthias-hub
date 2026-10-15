# Changelog

## Pilot UI handoff candidate — 2026-10-15

**Status: pilot/testing, not a production release.** The checked-in `main` commit and the
CI-published `ghcr.io/ffworker/anthias-hub:sha-<FULL_COMMIT_SHA>` image identify a
reproducible build. There is currently no separate stable/release channel and no
version-tag automation. See [controlled releases](docs/reproducible-production.md).

### Included in the pilot UI baseline

- Nordlicht-only appearance, explicit active navigation and readable mobile tabs.
- Compact screen cards with secondary IT controls and a restrained Marketing help action.
- Side-opening viewport-bounded device flyouts, compact button hierarchy and safe close behavior.
- Playlist Studio media cards, add-content drawer, single and batch upload workflows.
- Simplified template library and contextual publishing/management actions.
- CSS maintenance: remove obsolete tab/theme rules, keep late shared rules in
  `ui-refinements.css`, remove overridden declarations without intentionally changing visuals.
- Offline Python/Node regression tests, including responsive flyout behavior,
  stylesheet order and stylesheet block checks.

### Not yet certified

- Live Anthias write/upload/delete compatibility on every intended Pi version.
- Network isolation, TLS/VPN/client reachability and firewall rules.
- Physical-display verification, backup/restore rehearsal and formal IT/Marketing acceptance.

**Before colleague testing:** use [pilot acceptance](docs/pilot-acceptance.md) and the
[one-page Marketing practice sheet](docs/marketing-praxistest.pdf).
No automatic updates or changes to the Hub VM, firewall or Anthias Pis are performed
by this documentation/stylesheet cleanup.
