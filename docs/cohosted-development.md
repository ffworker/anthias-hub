# Anthias Hub – production and development on one server

Two independent Docker Compose projects can share one host without sharing
their applications, credentials, media or player inventory.

| Property | Production (unchanged) | Co-hosted DEV |
|---|---|---|
| Git checkout | Existing production directory | /root/apps/anthias-hub-dev |
| Docker project | anthias-hub | anthias-hub-dev |
| Local web port | 127.0.0.1:8765 | 127.0.0.1:8766 |
| Image | Existing pinned SHA | anthias-hub:dev-cohost |
| Config / data | Existing production paths | Separate ./config and ./data |
| Source | Existing verified SMB shares | Local `./dev-sources/demo` or SMB configured in DEV browser, read-only |
| Automatic Pi publish | Existing setting | OFF by default |

**Never copy production .env, config, data or SMB mounts into DEV. Never
register a production Pi as an editable test target.** The development helper
refuses to operate from a path other than the new checkout and does not issue
commands against the production Compose project.

## Installation – on the EXISTING host, in a NEW directory

```bash
git clone https://github.com/ffworker/anthias-hub.git /root/apps/anthias-hub-dev
cd /root/apps/anthias-hub-dev
git fetch origin dev/screen-source-of-truth-v2-20261113
git switch --track origin/dev/screen-source-of-truth-v2-20261113

bash scripts/dev-cohost.sh init
bash scripts/dev-cohost.sh start
bash scripts/dev-cohost.sh status
```

The first command prepares a second checkout. The init command creates a
**new** secret, accounts, data directories and a separate local image,
prompting for a new test owner password. If that prompt fails or passwords do not match, **run `bash scripts/dev-cohost.sh init` again** to safely finish creating the missing owner account; do not delete or copy production data. There is no production restart.
The development importer scans the local demo source every **60 seconds**;
production keeps its own configured interval.

## Open DEV from a workstation

DEV is bound only to the server's localhost. On your workstation:

```bash
ssh -N -L 127.0.0.1:8766:127.0.0.1:8766 USER@SERVER
```

Then open http://127.0.0.1:8766 on the workstation. The production
URL and port are unchanged. DEV clearly displays its TESTSYSTEM indicator.
Local source-built UI images show `Build lokal/dev`, not a baked GHCR SHA.

## Test media and test players

Place sample PNG or JPG files into `/root/apps/anthias-hub-dev/dev-sources/demo`.
Create a folder-backed playlist with source `demo` in the DEV UI and verify
the periodic Hub import. **Assigned screens are read-only in DEV v2:** edit the
central playlist, not individual Pi media. Alternatively configure SMB under
**Ordner & Quellen** in the DEV browser; that needs no host CIFS mount.

Initially the separate DEV .env contains
`ANTHIAS_ALLOWED_CIDRS=127.0.0.0/8`. This intentionally **blocks
connections to real Raspberry Pis**, protecting production screens.
Only after choosing a disposable/test Pi, change this DEV-only setting to
the **single test Pi address /32** and run:

```bash
cd /root/apps/anthias-hub-dev
bash scripts/dev-cohost.sh start
```

Avoid setting a broad private subnet that also includes production Pis.

Automatic DEV publication is disabled (`DEV_AUTO_PUBLISH=0`). If and only if
the registered target is a verified disposable test Pi, set
`DEV_AUTO_PUBLISH=1` in the DEV-only .env and recreate its importer:

```bash
docker compose -p anthias-hub-dev \
  -f compose.yaml -f compose.dev.yaml \
  up -d --no-build --no-deps --force-recreate anthias-folder-import
```

Missing-file pruning (`DEV_PRUNE_MISSING=0`) remains OFF by default.
Change `FOLDER_SYNC_INTERVAL=1800` in the DEV .env to test the
30-minute cadence; first-run rapid testing uses 60 seconds.

## Operations

```bash
cd /root/apps/anthias-hub-dev
bash scripts/dev-cohost.sh status
bash scripts/dev-cohost.sh logs
bash scripts/dev-cohost.sh stop
```

Stop preserves DEV data; it does not restart or stop production.
Do not run `docker compose --remove-orphans` or a shared `down -v`.

**Limit:** Both instances still share host CPU/RAM/disk/kernel. Use a
different VM if full failure isolation is later required. And writing
tests to a Pi still require a separate, intentionally configured device.
