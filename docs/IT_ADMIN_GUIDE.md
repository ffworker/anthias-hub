# IT administration — Anthias Hub

Anthias Hub is an independent Flask/Docker management interface for existing
Anthias players. It is **not** a player, Pi media backup, TV status monitor or
the RSS2Slideshow application. The current staging deployment uses
`ghcr.io/ffworker/anthias-hub:latest` and optional host-local Caddy HTTPS;
for a production VM, pin an approved immutable image and disable test-VM
auto-updates ([release guide](reproducible-production.md)).

## Roles and boundaries

| Role | Access |
| --- | --- |
| Owner | Device management and playlist/library editing |
| IT | Add/edit/remove registered players, view content, reboot/shutdown and experimental HDMI-CEC |
| Marketing | Edit content, manage library/schedules and confirmed troubleshooting reboot |
| Viewer | Read-only |

Marketing can currently modify content on **all registered players**. Hub
permissions do not protect a Pi API reachable directly from an unauthorized
client. Restrict browser → Hub through HTTPS/VPN, allow Hub → Pi API, and
block direct Marketing-client → Pi management access. Pi shutdown/CEC
capabilities vary by Anthias release, device hardware and connected monitor.

## Host layout and secrets

| Location | Purpose | Backup |
| --- | --- | --- |
| `.env` | Application session secret, cookie/proxy settings, CIDR allowlist, Compose override and image reference | **Yes, confidential** |
| `config/users.json` | Local password hashes and roles | **Yes, confidential** |
| `data/devices.json` | Registered players | Yes |
| `data/library/` | Reusable media and templates | **Yes** |
| `data/schedules.json` | Named schedules, device defaults and linked assignments | **Yes** |
| `data/audit.jsonl` | Non-tamper-evident audit events | Yes, retention policy |
| Every Anthias Pi | Native playlist, media, schedule state | **Separate backup and restore test** |
| Caddy data/PKI | Local root CA certificate and private key | **Separate encrypted off-host backup** |

Neither exported Hub library templates nor GHCR images contain all of these
states. Restrict permissions on secrets and CA private keys. Never commit or
post private addresses, credentials or certificate keys publicly.

## First installation and access

Use the [README quick start](../README.md), [SSH hardening](ssh-access.md),
[reproducible deployment](reproducible-production.md) and
[network/Caddy TLS instructions](network-access.md).

A fresh installation starts with `bash scripts/setup-pilot.sh --solo`
(Owner) or without `--solo` (IT and Marketing). On a **configured**
instance, never delete `.env` to repair users. To resume missing-account
setup, use `bash scripts/setup-pilot.sh`; for deliberate password
rotation, use `bash scripts/setup-pilot.sh --reset-users` and follow its
confirmation prompts. Retain a recovery console and verified SSH key before
hardening remote access. Do not expose port 8765 publicly.

## Operating the existing GHCR/Caddy test VM

In the correct checkout:

```bash
cd ~/apps/anthias-hub
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || exit 1

docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub ps
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub logs --tail=80 anthias-hub
curl -fsS http://127.0.0.1:8765/healthz
systemctl is-active anthias-hub-cd.timer
systemctl is-active caddy
```

The `/healthz` endpoint tests the web service, **not** live player playback.
The current deployment requires `COOKIE_SECURE=1`, one trusted Caddy proxy
(`TRUSTED_PROXY_COUNT=1` only when no other backend route exists), and
the Hub bound to **127.0.0.1:8765 only**. Staff clients must trust the
verified **public** Caddy CA root. Never share Caddy's CA private key.
See [network access](network-access.md) for client trust and CSRF troubleshooting.

**Manual container restart**, if no settings changed:

```bash
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub restart anthias-hub
```

**After editing `.env` or the Compose override**, first validate the
resolved port bindings (without printing expanded secrets), then recreate
*only* Anthias Hub:

```bash
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub config --format json \
  | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["services"]["anthias-hub"]["ports"], indent=2))'
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub up -d --no-build --no-deps --force-recreate anthias-hub
```

The test-only systemd timer manages normal GHCR `:latest` updates, including
its existing external override and rollback. If coordinating manual Compose
changes, pause the Hub timer first and re-enable it afterward. **Do not
run `docker compose up -d --build` without explicit Compose files:** it
selects the wrong local-build image. RSS2Slideshow is a separate Compose
project and must not be restarted while servicing the Hub. See
[auto-deploy](auto-deploy.md).

## Players, schedules and troubleshooting

- Register only permitted private player URLs; narrow
  `ANTHIAS_ALLOWED_CIDRS` to actual authorized device networks.
- A removed device registration does not erase native Pi assets.
- Library content is not published until explicitly appended/transferred.
  Non-atomic transfers may partially succeed: inspect the actual Pi state
  before attempting again. Template-backup ZIPs and ordinary media ZIPs
  have different formats.
- Shared schedule plans are stored in the Hub; the Pi executes native
  recurring play windows. Changing a plan does not automatically rewrite
  already scheduled Pi assets. See [scheduling](scheduling.md).
- Storage checks use the Anthias API `free_space` and apply a conservative
  reserve and two-copy budget. See [media importing](marketing-bulk-import.md).
- HDMI-CEC, reboot and shutdown require real-player acceptance and confirmation.
  Player reachability does not establish a working monitor image.

## Backup, recovery and release

Before upgrades or destructive Pi tests, take protected **off-host copies**
of the Hub `.env`, `config/`, `data/`; preserve permissions and coordinate a
consistent snapshot. Separately back up Pi media/playlists and the Caddy
PKI data. Record the running image digest, the exact Compose files/override,
the backup timestamp and the method of restoration. **Rehearse restoration
on a disposable host**; do not overwrite live states for a rehearsal.

Restore Hub state and matching code/image into an isolated environment,
confirm file ownership (`HUB_UID`/`HUB_GID`), health, login, device inventory,
library and schedule data. Pi content must be restored independently.
Rolling back an image never undoes Pi writes. Treat `data/audit.jsonl` as
basic operational evidence, not an immutable compliance ledger.

Before company-wide use, complete the [real-device acceptance checklist](pilot-acceptance.md)
and follow [controlled release procedures](reproducible-production.md).
