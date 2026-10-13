# Anthias Hub

**IT configures devices. Marketing controls the content.** A compact, self-hosted hub to manage playlists across multiple [Anthias](https://anthias.screenly.io/) players from one website — without rebuilding a complete digital signage player.

> **Status:** Public-ready source / internal pilot. The Anthias API integration has **not yet been verified against a real company player**. Deploy to an isolated test environment first, back up the Pi playlist, then test writes. Do not expose directly to the internet.

## What it does

| Feature | IT | Marketing | Viewer |
|---|---|---|---|
| Sign in with a static username/password | ✓ | ✓ | ✓ |
| See all devices, status and playlists | ✓ | ✓ | ✓ |
| Register, edit or remove an Anthias Pi | ✓ | — | — |
| Open the original Anthias admin screen | ✓ | — | — |
| Add website URLs and upload PNG/JPG/WebP/MP4 | — | ✓ | — |
| Rename, enable/disable, change duration, reorder and delete playlist items | — | ✓ | — |

The app calls **Anthias API v2** directly from its backend. No device credentials, URLs or internal network addresses are included in this repository. Devices and account hashes remain in untracked local files; playlist changes apply to the original Pi, not to a separate database.

## Architecture

```text
IT login --------> Anthias Hub --------> Device registration / troubleshooting
Marketing login -> Anthias Hub --v2 API--> Anthias Pi A --> TV A
                           |----v2 API--> Anthias Pi B --> TV B
Viewer login ----> Anthias Hub (read only)

RSS2Slideshow (independent web application) --> website asset on any Anthias Pi
```

**Companion application:** [RSS2Slideshow](https://github.com/ffworker/rss2slideshow) is the independent news kiosk with article QR codes; Anthias Hub can add its kiosk URL as a website asset just like any other URL. It does not need RSS2Slideshow to function.

## Publish as a new public GitHub repository

This project is provided independently from the RSS2Slideshow repository. **A separate public GitHub repo still needs to be created by an authenticated account.** After extracting the source ZIP, install [GitHub CLI](https://cli.github.com/), run `gh auth login`, review the files and then:

```bash
bash scripts/publish_to_github.sh anthias-hub
```

The script verifies that tracked runtime secrets are absent, requires explicit `PUBLISH` confirmation, creates a **new public repository**, and pushes the project. It needs your GitHub account's authorization. Once GitHub returns the actual URL, add it to the link in RSS2Slideshow's [Anthias Hub integration note](https://github.com/ffworker/rss2slideshow/blob/main/docs/anthias-hub.md).

**Windows / PowerShell without GitHub CLI:** Create a new **empty, public** GitHub repository named `anthias-hub` on [GitHub → New repository](https://github.com/new) (do not add a generated README or license). Unpack the ZIP, then from the project folder run:

```powershell
git init -b main
git add .
git commit -m "feat: initial Anthias Hub"
git remote add origin https://github.com/ffworker/anthias-hub.git
git push -u origin main
```

Use your own GitHub username instead of `ffworker` if publishing under another account. Verify the newly created public repo URL before adding it elsewhere.

## First test on a separate Compose stack (recommended: an existing Docker host)

For a quick internal pilot, use an existing Docker host, but keep this
project completely separate from RSS2Slideshow (its directory, Compose project,
volumes and ports). The hub is only bound to `127.0.0.1:8765`; use an SSH tunnel.
No firewall rules, RSS feed configuration, kiosk assets or running signage
containers need to be changed.

See **[Docker host pilot setup](docs/deploy-docker-host.md)** for the concise,
Docker-only procedure. No Flask or Python environment needs to be installed
on the host. Add a second VM only if isolation becomes a real requirement.

## Quick start (Docker Compose)

Requirements: Docker + Compose, a trusted server that can reach the Anthias device subnet, and a browser able to reach the management site.

1. Copy this repo and configure a random session secret:

   ```bash
   cp .env.example .env
   python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
   # Paste the generated value into APP_SECRET_KEY in .env.
   mkdir -p config data
   # Check `id -u` and `id -g`, set HUB_UID/HUB_GID in .env to match.
   # Run Docker Compose as this same non-root host user.
   ```

2. Configure **individual static logins** using Python 3.12+ and a temporary venv. Passwords are never committed or stored as plaintext:

   ```bash
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/python -m scripts.create_user config/users.json it it
   .venv/bin/python -m scripts.create_user config/users.json marketing marketing
   # Optional: viewer account
   # .venv/bin/python -m scripts.create_user config/users.json viewer viewer
   ```

   The CLI prompts twice for a password (minimum 12 characters) and stores an `scrypt` hash. Never share the passwords among departments. `config/users.json` remains excluded from Git.

3. **Start locally**, not publicly:

   ```bash
   docker compose up -d --build
   docker compose ps
   curl -fsS http://127.0.0.1:8765/healthz
   ```

   Default bind is `127.0.0.1:8765`. For your first remote test, connect over SSH tunnel:

   ```bash
   ssh -L 8765:127.0.0.1:8765 user@YOUR_DOCKER_HOST
   # Browse http://localhost:8765/ via that SSH tunnel.
   ```

   **Cookie rule:** For a plain HTTP localhost/SSH tunnel pilot set `COOKIE_SECURE=0` in `.env` and restart. For actual company users, deploy behind an **HTTPS reverse proxy**, keep `COOKIE_SECURE=1`, and enforce network restrictions and access controls. Never publish the hub unauthenticated or over plaintext company Wi-Fi.

4. Sign in as **IT**, register one existing Anthias test Pi by its private IP, then confirm the playlist loads. Switch to the **Marketing** account to test content changes after taking a backup. Real Pi compatibility must be confirmed first.

5. The `ANTHIAS_ALLOWED_CIDRS` setting restricts which IP ranges IT may register. Default is RFC1918 (10/8, 172.16/12, 192.168/16). Restrict it to your actual management VLAN(s). **IP literals only** in v0.1 — no dynamic DNS and no redirects to other servers.

## Critical network boundary

Anthias' API is designed for trusted local networks and may not require its own authentication. **A Marketing account in this hub is not a network firewall.** If Marketing clients can reach Pi management ports directly, they can bypass the hub's role restrictions. Put the Pis' management API behind firewall rules that permit only the hub and IT administration paths; serve the hub itself only over HTTPS/VPN to authorized users.

This app deliberately does **not** proxy the full Anthias UI to Marketing, because that would expose player/system configuration. All playlist editing is implemented through allowlisted server-side Anthias asset API calls. IT can still open the original player dashboard to troubleshoot.

## Playlist operations

Per device, Marketing can:

- add an ordinary website by name, HTTPS/HTTP URL and duration
- upload a picture or MP4 up to 50 MB (simple signature + extension checks, not full malware scanning)
- rename, enable/disable and change non-video duration
- move individual items up/down (Anthias `/api/v2/assets/order`)
- delete individual assets after confirmation

Date/time schedules and advanced display settings are **not yet exposed** in the marketing UI; existing schedules are preserved when an asset is edited. Content is edited **one Pi at a time**. There is no central playlist database, group-write operation, cloud service, billing or AD integration in this version.

## Security and operational notes

- Static accounts (`it`, `marketing`, optionally `viewer`) are created by the CLI; no default password, no password management inside the UI.
- Session cookies: HttpOnly, SameSite=Lax, Secure when configured; signed Flask sessions; CSRF token on all POST forms.
- Basic in-memory login rate limit; the system is intended for internal use behind a reverse proxy, **not** internet-facing multi-tenant production.
- All device writes enforce roles server-side. User-controlled URLs cannot select device API endpoints.
- IP-restricted device inventory, no remote redirects, short API timeouts, audit log in `/data/audit.jsonl`.
- Device inventory is persistent in host-owned `./data/devices.json` and the audit trail in `./data/audit.jsonl`. Back up `./data/` and `./config/`, and the Anthias devices independently.
- Logging is intentionally minimal and avoids storing passwords. Static accounts are read from the local config file on requests.
- Device API reachable ≠ display content verified. Check the TV after significant changes.
- Upload security and access protections should be hardened further before broader deployments.

## Development & tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/pytest -q
.venv/bin/python -m compileall -q app scripts wsgi.py
```

Run on a test Pi before enabling Marketing in a production network. See [SECURITY.md](SECURITY.md) for deployment requirements. Anthias API reference: https://anthias.screenly.io/api/

## Future (only if needed)

Screen groups and deliberate batch API operations. Keep this release simple until you have demonstrated a need.

## License

MIT — see `LICENSE`. This project is independent of Anthias; Anthias has its own separate license. No company branding, company credentials, or private network inventory should be committed.
