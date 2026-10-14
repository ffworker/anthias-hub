# GH-PiHub: repeatable two-app TEST VM bootstrap

This is a **disposable test/staging VM** procedure for Debian 13 with Docker Engine + Compose plugin, Git, curl, OpenSSL and OpenSSH. It is **not** the approved production release workflow. The apps remain entirely independent: separate Git repos, Compose projects, credentials, data and backups. This script does **not** install system packages, adjust SSH/network settings, fetch new code into existing checkouts, auto-approve releases, delete anything, or install systemd CD timers.

## Existing VM (both repositories already cloned)

Assuming `~/apps/anthias-hub` and `~/apps/rss2slideshow` are siblings, as on GH-PiHub:

```bash
cd ~/apps/anthias-hub
bash scripts/bootstrap-test-vm.sh doctor   # read-only; lists missing requirements
bash scripts/bootstrap-test-vm.sh init     # only creates MISSING samples; Hub fresh setup is interactive
# REVIEW ~/apps/rss2slideshow/.env, config.yaml, content/feeds.txt
bash scripts/bootstrap-test-vm.sh deploy   # explicit build/up; may recreate existing pilot containers
bash scripts/bootstrap-test-vm.sh status   # read-only compose/HTTP checks
```

**If both apps are already running:** run `doctor` and `status` only. `deploy` is not a passive health check and may recreate containers. An existing Hub `.env` is never overwritten or passed through `setup-pilot.sh`. If it exists but `config/users.json` is absent, stop and restore/recreate accounts deliberately, not by regenerating a session secret.

Before running `deploy`, **edit/review** RSS `.env`, `config.yaml` and `content/feeds.txt`; new samples are *not* the live Bistro settings. No RSS auto-updates are configured. Example feeds are not acceptable as a production acceptance test.

## Fresh test VM (new clean machine)

1. Configure a **unique, stable IP / DHCP reservation**, verify no duplicate address, working DNS, NTP and VM console. The SSH host fingerprint changing after a disconnection may be a network/IP issue; never bypass SSH host-key validation.
2. Install Docker Engine + Compose plugin from Docker's official Debian instructions. Check `docker version`, `docker compose version`, `docker info`. Avoid duplicate Docker APT repository entries with conflicting `Signed-By` keys. Ensure `git curl openssl openssh-client` are installed.
3. Use one operator account consistently for Git and the private deploy key. Docker daemon access is effectively root-level; do not grant it broadly.

```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
bash scripts/bootstrap-test-vm.sh key
```

The `key` command generates a **new ED25519 key for this VM only if missing** and prints **only the public key**. Register it in the private [RSS2Slideshow repository deploy keys](https://github.com/ffworker/rss2slideshow/settings/keys) with **read-only** access. On first SSH contact verify [GitHub's published SSH fingerprints](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints). Do not upload or paste the private key anywhere, and do not disable host-key verification.

```bash
cd ~/apps/anthias-hub
bash scripts/bootstrap-test-vm.sh clone-rss   # after GitHub deploy key is approved
bash scripts/bootstrap-test-vm.sh doctor
bash scripts/bootstrap-test-vm.sh init        # prompts for fresh Hub IT and Marketing passwords
# Review the new RSS sample files. Edit real feeds and settings before serving content.
bash scripts/bootstrap-test-vm.sh deploy
bash scripts/bootstrap-test-vm.sh status
```

`clone-rss` explicitly uses `~/.ssh/rss2slideshow_deploy_ed25519` (or `RSS_DEPLOY_KEY` when intentionally set), validates read access via `git ls-remote`, and configures the private repository's *local* Git SSH command. If the repo already exists, it checks its remote and preserves its revision and working tree. It never invokes `git pull`, `git reset --hard`, or `git checkout`. Key troubleshooting: [RSS read-only deploy key runbook](https://github.com/ffworker/rss2slideshow/blob/main/docs/github-deploy-key.md) (private).

## URLs, access and verification

| Application | Local binding | Compose project | Verify |
| --- | --- | --- | --- |
| Anthias Hub | `127.0.0.1:8765` | `anthias-hub` | `curl -fsS http://127.0.0.1:8765/healthz` |
| RSS2Slideshow | `127.0.0.1:8085` by default (configurable) | `rss2slideshow` | `curl -fsS http://127.0.0.1:8085/healthz` and `/api/articles` |

Hub over an SSH tunnel from the admin workstation:

```powershell
ssh -N -L 8765:127.0.0.1:8765 root@TEST_VM_IP
```

Then browse to http://localhost:8765. Neither default port listens on the VM's external interface. The **RSS kiosk page must be deliberately published on a reachable internal address** before the Anthias Pi can load it (internal reverse proxy, or a carefully constrained bind/network path). Keep `/admin` protected; do not expose Hub, RSS admin access or Pi management APIs broadly. Test authentication, real RSS article freshness, the actual Pi playlist, and a complete TV loop. `/healthz` alone is insufficient.

For troubleshooting use:

```bash
cd ~/apps/anthias-hub
docker compose -p anthias-hub logs --tail=80
cd ~/apps/rss2slideshow
docker compose -p rss2slideshow logs --tail=80 signage
```

## Existing data, upgrades, release safety

- **Do not rerun fresh initialization to repair a broken installation.** The script copies only missing RSS example files; it never replaces existing `.env`, Hub users, feed selections, design settings or runtime data. If `.env` is already present but accounts are missing, repair separately. Protect owner-only secrets and make tested **off-host backups** before any upgrade/rebuild.
- The `deploy` command checks both Compose configs before building either app. It refuses to use the Hub pilot Compose file when `ANTHIAS_HUB_IMAGE` is set in the Hub `.env`, to avoid accidentally reverting a pinned release to a local pilot build.
- `main` is **not** an approved production version. Don't install Anthias Hub's `anthias-hub-cd.timer` on the future production VM; its current updater follows `:main`. See [Hub approved-SHA production runbook](reproducible-production.md) and [RSS manual deployment](https://github.com/ffworker/rss2slideshow/blob/main/docs/manual-vm-deploy.md) (private).
- On a new **production** VM, create a different deploy key; pick an explicitly **tested/approved commit** and Hub immutable image reference, preserve a rollback reference, back up data and verify the output at the physical screen. This test script is intentionally **not** a production promotion tool.
- To update the source deliberately, use each repository's own reviewed update runbook. Running this script by itself never updates Git.

## Script syntax check

CI checks the shell syntax, and the script supports a read-only `doctor` and `status`. For manual inspection:

```bash
bash -n scripts/bootstrap-test-vm.sh
bash scripts/bootstrap-test-vm.sh help
```
