# Reproducible VM installation and controlled releases

**Purpose:** rebuild Anthias Hub from scratch on a new VM, keep the current throwaway VM as test/staging, and stop production from tracking every `main` push. A separate `live` Git branch is unnecessary: production should run a reviewed image reference.

> **CURRENT STATE, 13 Oct 2026:** CI publishes `ghcr.io/ffworker/anthias-hub:main` and `ghcr.io/ffworker/anthias-hub:sha-<FULL_40_CHAR_GIT_SHA>` after a successful `main` build. It does **not** publish `:v1.0.0` tags. `compose.cd.yaml` supports an `ANTHIAS_HUB_IMAGE` override, but `scripts/auto_deploy.py` **hardcodes `:main`**, ignoring that setting, and checks for `:main` or its rollback image. **NEVER install/enable the current `anthias-hub-cd.timer` on the future production VM**; disable any inherited timer before attempting a pinned deployment. This document is the manual, repeatable solution using the already-published SHA-tagged image. Automated approved releases require future code changes.

This is a deployment blueprint, **not** an assertion that the current pilot has been validated for unrestricted company-wide/Internet use.

## Desired workflow

| Where | Code/image | Trigger |
| --- | --- | --- |
| Feature branches | Feature code + PR checks | Developer |
| `main` | Integrated source; CI publishes `:main` and `:sha-FULL_SHA` | Reviewed merge |
| Test VM/staging | Exact SHA-tagged candidate image, real Pi test | Developer/IT |
| Fresh production VM | `ghcr.io/ffworker/anthias-hub:sha-APPROVED_FULL_SHA` | **Explicit approval and manual deployment** |

For even stronger immutability, pin the image by its **OCI digest** (`ghcr.io/ffworker/anthias-hub@sha256:...`) rather than a mutable registry tag. A Git SHA and an OCI digest are **different things**. Record both where possible.

Release gate: PR reviewed -> CI green on `main` -> image published -> same image tested in staging (UI, player API, spare screen, failure/recovery) -> IT approval -> Hub and Pi backups -> manually promote pinned image -> health/login/API/physical-display checks -> record version, image ID/digest and rollback reference.

## 1. Prepare a fresh VM

Choose a maintained Linux VM, stable network identity, DNS/NTP, and outbound access to GitHub and GHCR. **Before deploying applications**, create a named non-root admin account, install a workstation-specific ED25519 SSH key and `~/.ssh/config` alias, verify a new key-only login and sudo, then block SSH root/password logins and restrict the SSH ingress firewall. Use the [complete SSH + host-hardening runbook](ssh-access.md) (including console access to prevent lockout). Clone under the admin user's `~/apps`, not `/root/apps`. Install Docker Engine, Compose plugin, Git, OpenSSL, curl and iproute2 (for `ss`) using the current instructions for your distro. CI currently publishes the image for **linux/amd64**; verify VM architecture. Docker daemon access and `docker` group membership are effectively root: restrict to trusted administrators.

Ensure the VM can reach the designated Anthias management VLAN. Scope `ANTHIAS_ALLOWED_CIDRS` in `.env` to the actual subnet. Network ACLs must block Marketing clients from reaching the Pis' management APIs directly, which would bypass Hub role restrictions.

Both Compose variants bind **`127.0.0.1:8765` on the host**, deliberately. Start with an SSH tunnel. For real internal Marketing use, configure an **internal HTTPS reverse proxy or VPN** and `COOKIE_SECURE=1`; do not expose the pilot directly to the Internet.

**Keep RSS2Slideshow independent.** Co-location on the same VMware vSphere VM is planned, with separate checkouts, Compose project names and backup policies. Recommended starting guest: Debian 13 minimal (amd64), 4 vCPU, 8 GB RAM, 80 GB SSD; these are planning values with headroom, not measured usage. The Hub is not the Pi's content or media backup. RSS2Slideshow keeps its existing CI checks but is deliberately updated **manually** after green CI; do not install an RSS CD timer or invent a GHCR RSS image. See its [new-VM/manual-update runbook](https://github.com/ffworker/rss2slideshow/blob/main/docs/manual-vm-deploy.md) (private repo; authorized access required).

## 2. Fresh bootstrap on a new, empty host

Choose a **real full 40-character Git commit SHA** from a successful `main` Actions run and check that the corresponding `:sha-...` image was published. Replace the placeholder below, not with a branch name.

```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/ffworker/anthias-hub.git
cd anthias-hub
RELEASE_SHA='REPLACE_WITH_TESTED_FULL_40_CHARACTER_MAIN_SHA'
git fetch origin
git cat-file -t "$RELEASE_SHA"        # must be "commit"
git checkout --detach "$RELEASE_SHA"
docker compose version

# ONE-TIME initialization, never over an existing .env:
# creates .env/session key, config/users.json, data and the local :pilot image,
# prompts for independent IT and Marketing credentials and starts local pilot.
bash scripts/setup-pilot.sh

# Override the CD Compose image with the exact tested Git-SHA image.
# Ensure .env does not already contain ANTHIAS_HUB_IMAGE before appending.
grep -q '^ANTHIAS_HUB_IMAGE=' .env && {
  echo 'Already pinned: edit existing ANTHIAS_HUB_IMAGE, do not add another' >&2
  exit 1
}
printf '\nANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-%s\n' "$RELEASE_SHA" >> .env
chmod 600 .env

docker compose -f compose.cd.yaml -p anthias-hub pull anthias-hub
docker compose -f compose.cd.yaml -p anthias-hub up -d --no-deps --force-recreate anthias-hub
docker compose -f compose.cd.yaml -p anthias-hub ps
curl -fsS --max-time 10 http://127.0.0.1:8765/healthz
cid=$(docker compose -f compose.cd.yaml -p anthias-hub ps -q anthias-hub)
docker inspect --format '{{.Config.Image}} {{.Image}}' "$cid"
git rev-parse HEAD
```

The initial `setup-pilot.sh` builds/starts `anthias-hub:pilot` *only for first-time account setup*. The subsequent `compose.cd.yaml` commands replace it with the approved prebuilt image. If setup is interrupted or `users.json` is deleted, rerun `bash scripts/setup-pilot.sh` from this checkout: it keeps `.env` and existing accounts and creates missing roles, using the pinned image when `ANTHIAS_HUB_IMAGE` is set. Use `--reset-users` to choose which existing role passwords to replace. Never `docker compose pull` the default `compose.yaml`: its `anthias-hub:pilot` tag is local-only. Do not start `scripts/install-auto-deploy.sh` on production.

To access from Windows, configure an **independent production key and alias** as in [SSH access & VM hardening](ssh-access.md). For a production VM rename the example `gh-pihub` / `gh-pihub-tunnel` aliases to `hub-prod` / `hub-prod-tunnel` and replace `VM_IP` with its own address. Then:

```powershell
ssh hub-prod           # authenticated admin shell
ssh -N hub-prod-tunnel # separate PowerShell window: Hub 8765 + optional RSS 8085
```

Open `http://127.0.0.1:8765` (and `http://127.0.0.1:8085` if RSS is installed on this host). These are localhost-only SSH test tunnels, **not** a way to publish RSS signage to Pis. Verify login, IT/Marketing roles, devices, and a **read-only** Anthias playlist before any writes. `/healthz` checks the web process only; it cannot confirm player/HDMI/TV output. Bootstrap sets `COOKIE_SECURE=0` **for SSH-tunneled HTTP testing**; switch it to `1` and recreate the container before normal internal HTTPS access.

Do not clone the throwaway VM or carry over its test users/devices by default. If you intentionally migrate state, first review it and move it through a secure backup.

### Optional: RSS2Slideshow on the same new VM

The two applications are **separate**, even on one VM. Their hostnames, proxy routes, source revisions, local state and backups must be recorded independently. **RSS2Slideshow is a private repository**, requiring an explicitly authorized GitHub credential or read-only deploy key on the new VM. Never commit that key or the runtime configuration.

After the Hub has been deployed, use a **different directory** for the RSS application:

~~~bash
cd ~/apps
# Requires prior access to the private ffworker/rss2slideshow repository:
git clone git@github.com:ffworker/rss2slideshow.git
cd rss2slideshow
# Choose/document an explicitly approved RSS2Slideshow commit before starting:
git rev-parse HEAD
cp .env.example .env
cp config.example.yaml config.yaml
cp content/feeds.example.txt content/feeds.txt
chmod 600 .env
# Edit .env, config.yaml and content/feeds.txt for the new installation.
# Set a unique strong ADMIN_USER and ADMIN_PASSWORD if /admin is required.
docker compose config --quiet
docker compose -p rss2slideshow up -d --build
docker compose -p rss2slideshow ps
curl -fsS --max-time 10 http://127.0.0.1:8085/healthz
~~~

The example RSS feeds, configuration and branding are **not** a restore of the existing Bistro installation; check source rights and the [RSS configuration guide](https://github.com/ffworker/rss2slideshow/blob/main/docs/configuration.md) before real use. For an actual migration, securely restore the separately backed-up runtime `.env`, `config.yaml`, `content/`, optional local assets and branding overrides with proper ownership; do **not** overwrite runtime data with examples. The RSS repo's older `docs/deployment.md` contains a **specific historical gh-bistro update** and is **not** a generic installer for a fresh VM.

The RSS Compose project uses **host port 8085 on 127.0.0.1 by default**, versus **8765 for the Hub**, avoiding port conflicts. For actual Anthias players to display the RSS site, publish only the approved internal URL via a tightly scoped reverse proxy/internal routing and verify that the Pis can reach it. The Hub's localhost-only admin access must stay restricted. Do not expose RSS `/admin` to untrusted clients. RSS has its own CI checks; after an approved fix, manually fast-forward its private checkout and rebuild the local Compose image, then check fresh articles and the Pi screen. Hub's GHCR release and test-VM auto-updater do **not** update RSS.

## 3. Backups, promotion and rollback

Hub's confidential persistent state is `.env`, `config/users.json`, `data/devices.json`, `data/audit.jsonl` and `data/library/` (template manifests and original Hub uploads; some paths might not yet exist on an empty installation). Store encrypted/off-host backups with correct UID/GID, budget disk space for uploaded videos and verify restore on staging. A template ZIP contains only its own Hub-uploaded media, not media already stored on a Pi. **Anthias player playlists, media and schedules live on the Pis and must be backed up separately.** Follow the [IT backup guide](IT_ADMIN_GUIDE.md#5-backup-vor-jedem-upgrade).

Before every approved image promotion:

```bash
cd ~/apps/anthias-hub
# This command checks only; if it reports enabled, STOP the old test updater:
systemctl is-enabled anthias-hub-cd.timer 2>/dev/null || true
# sudo systemctl disable --now anthias-hub-cd.timer

umask 077
cp -p .env ".env.before-release-$(date +%Y%m%d-%H%M%S)"
cid=$(docker compose -f compose.cd.yaml -p anthias-hub ps -q anthias-hub)
docker inspect --format '{{.Config.Image}} {{.Image}}' "$cid"

# After backup and written approval, EDIT THE EXISTING LINE in .env:
# ANTHIAS_HUB_IMAGE=ghcr.io/ffworker/anthias-hub:sha-NEW_TESTED_FULL_SHA
# Do not append another ANTHIAS_HUB_IMAGE variable.
vi .env

docker compose -f compose.cd.yaml -p anthias-hub pull anthias-hub
docker compose -f compose.cd.yaml -p anthias-hub up -d --no-deps --force-recreate anthias-hub
curl -fsS --max-time 10 http://127.0.0.1:8765/healthz
cid=$(docker compose -f compose.cd.yaml -p anthias-hub ps -q anthias-hub)
docker inspect --format '{{.Config.Image}} {{.Image}}' "$cid"
```

Then verify browser login, device list, actual player API and test-TV output. **Record** operator, approval, time, old/new Git SHAs, image references and resolved image IDs/digests and test results.

**Rollback:** edit only `ANTHIAS_HUB_IMAGE` back to the previously recorded approved image (the saved `.env.before-release-*` is a reference; do **not** overwrite other changed secrets/settings). Repeat `docker compose -f compose.cd.yaml -p anthias-hub pull anthias-hub` and `up -d --no-deps --force-recreate anthias-hub`, then recheck health/login/player. Keep a local copy of the previous image for registry outages; an image rollback does **not** roll back any Pi playlist/media changes.

## 4. Disaster recovery / reinstall

1. Reinstall Linux + Docker/Compose and restore restricted network/SSH/HTTPS access.
2. Recover the approved **Git commit + exact image reference/digest** from an off-host release record.
3. Checkout that source SHA (as in section 2). Use `setup-pilot.sh` **only** for a clean first installation, never over restored state.
4. For a genuine restore, instead restore your backed-up `.env`, `config/` and `data/` securely (correct owners/permissions), then use `compose.cd.yaml` with the saved `ANTHIAS_HUB_IMAGE`.
5. Confirm the timer is **not** tracking `:main`. Verify actual running image, `/healthz`, logins, roles, Anthias connectivity and physical screen behavior.
6. Restore each Pi separately if it lost its own playlist/media; the Hub backup cannot rebuild those assets. Test backup restoration, not just backup creation.

## 5. Version names: latest, stable and definitive releases

We should use meaningful names **without confusing convenience with reproducibility**:

| Proposed GHCR reference | Meaning | Production? |
| --- | --- | --- |
| `:main` | Most recent successfully built `main` commit | **No**, changes whenever `main` moves |
| `:latest` | Optional alias for latest successful build (not published today) | **No**, mutable and ambiguous |
| `:stable` | Optional alias for latest **approved** production release (not published today) | Useful channel for an intentionally automatic fleet, but **still mutable** |
| `:v0.3.0` | Proposed named approved version (not published today) | Human-readable, record exact image digest |
| `:sha-<FULL_40_CHAR_SHA>` | **Already published** per successful `main` commit | Best currently available source-to-image pin; tag still technically mutable |
| `@sha256:<IMAGE_DIGEST>` | Exact content-addressed image | **Best reproducibility**, including rollback |

A Git release named `v0.3.0 — Playlist Studio` may have a friendly title in release notes. That name is **metadata**, not an immutable executable artifact. For the live VM, document **release name + Git SHA + OCI digest**, and pin the deployed image digest wherever practical.

## 5. Future improvements (NOT available yet)

- Versioned releases such as `v0.2.0`: create a Git tag/release tied to an approved commit **and promote the already-tested container image/digest** to a corresponding GHCR `:v0.2.0` alias. The current CI only creates `:main` and `:sha-FULL_SHA`, so creating a Git tag alone does not produce a versioned image. Keep the promotion job behind explicit approval.
- Optionally add an approved `:stable` channel, but only after updating and testing `scripts/auto_deploy.py` to support an explicit release channel/digest, preserve rollback/quarantine and stop forcing `:main`. Until then, **manual pinned deployments are the safe default**.
- Introduce real staging checks and documented Pi API write tests before exposing Marketing to production playlists.

The [test-VM automatic deployment guide](auto-deploy.md) documents the existing, intentionally **`:main`-following** timer. It is not the future production release process.
