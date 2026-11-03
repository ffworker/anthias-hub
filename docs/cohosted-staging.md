# Co-hosted test VM — Anthias Hub + RSS2Slideshow

**Only for a disposable test/staging VM.** The applications are independent: different repositories, Compose projects, credentials, data and backups. This guide does **not** promote or update production. Anthias Hub uses a separate approved SHA-pinned image for production; [see the production runbook](reproducible-production.md).

Both projects have **public source repositories**. RSS2Slideshow does **not** need a private deploy key for a normal HTTPS clone. The older `bootstrap-test-vm.sh key` / `clone-rss` commands remain for deliberately configured private SSH remotes and are **not** part of the recommended new setup.

## Already running? Inspect only

```bash
cd ~/apps/anthias-hub
bash scripts/bootstrap-test-vm.sh doctor
bash scripts/bootstrap-test-vm.sh status
```

Neither command intentionally recreates a service. **Do not run `init` or `deploy` to check a live system**; the latter can rebuild and recreate pilot containers. Never use this script on a host running Hub with `ANTHIAS_HUB_IMAGE` pinned.

## New disposable test VM

1. Install Debian (or another maintained supported Linux host), Docker Engine + Compose plugin, Git, curl and OpenSSL. Use a named non-root administrator with a tested ED25519 SSH key. Verify the second SSH login and console recovery **before** restricting SSH; see [SSH hardening](ssh-access.md).
2. Assign a stable network identity (prefer a DHCP reservation), verify DNS/NTP and the host firewall. Do not expose Hub, RSS admin access or Pi management APIs to the public internet.
3. Clone the two separate public repositories:

```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/ffworker/anthias-hub.git
git clone https://github.com/ffworker/rss2slideshow.git
cd anthias-hub
bash scripts/bootstrap-test-vm.sh doctor
bash scripts/bootstrap-test-vm.sh init
```

`init` runs the **interactive initial Hub account setup** on a fresh VM (separate IT/Marketing credentials) and only creates missing RSS sample configuration files. It must **not** be run on a production installation or used to repair missing production state.

4. Review `~/apps/rss2slideshow/.env`, `config.yaml` and `content/feeds.txt`. Replace the example feed, set strong admin credentials, and check content rights. For a **new disposable test VM only**:

```bash
cd ~/apps/anthias-hub
bash scripts/bootstrap-test-vm.sh deploy
bash scripts/bootstrap-test-vm.sh status
```

`deploy` builds/recreates **both pilot Compose projects**. It refuses a Hub with `ANTHIAS_HUB_IMAGE` configured; do not remove that protection to force a deployment. It does not pull newer code in existing checkouts or install an updater.

## Verify the two separate services

| Application | Default local binding | Also check |
| --- | --- | --- |
| Anthias Hub | `127.0.0.1:8765` | Login, roles, registered devices and a real Pi playlist |
| RSS2Slideshow | `127.0.0.1:8085` | `/healthz`, **fresh articles** in `/api/articles` and the actual kiosk screen |

The default bindings are host-loopback only. Use an authorized SSH tunnel for administration or an approved restricted HTTPS reverse proxy for internal access. For the **Anthias Pi to display RSS**, explicitly provide a reachable internal **kiosk** URL; localhost on the VM is not reachable from the Pi. Do not publish RSS `/admin` as the player URL.

`/healthz` checks process health, **not** media playback or RSS freshness. Check a complete loop on the physical monitor. The Hub can go offline without stopping Anthias's existing playlist, but the RSS website must stay reachable separately.

## Troubleshooting and existing data

- To inspect the Hub on the **pilot Compose** setup: `cd ~/apps/anthias-hub && docker compose -p anthias-hub logs --tail=80`. For a **GHCR/Caddy installation with an override**, use the exact `-f compose.cd.yaml -f "$OVERRIDE"` commands from [IT administration](IT_ADMIN_GUIDE.md); **never substitute the pilot Compose file**.
- RSS logs: `cd ~/apps/rss2slideshow && docker compose -p rss2slideshow logs --tail=80 signage`.
- If RSS `config.yaml` is unexpectedly a directory (an older Docker bind-mount failure), **stop only signage**, inspect its contents and use `rmdir config.yaml` **only if empty**; copy `config.example.yaml` and review it before restarting. Never delete an unknown directory recursively.
- **Do not delete Hub `.env`** to repair accounts. See [account recovery](IT_ADMIN_GUIDE.md#first-installation-and-access). The Hub's own setup script can resume interrupted account setup without replacing existing secrets.
- Before any deployment or rebuild, back up confidential Hub `.env`, `config/`, `data/` and RSS `.env`, `config.yaml`, `content/` independently. A hub template ZIP does not back up Pi media/playlists. See [releases and recovery](reproducible-production.md).

For a permanent rollout, use a **separately approved image** and [production checklist](pilot-acceptance.md) instead of the auto-moving test channel.
