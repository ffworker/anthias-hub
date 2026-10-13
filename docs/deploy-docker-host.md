# Docker host pilot deployment (isolated Docker stack)

This is a **test installation only**. It must **not** modify the existing RSS2Slideshow
repository or Compose stack. Anthias player endpoints and their API semantics must
be verified against your actual test Pi before making any playlist changes.

## 0. Repository

Public source: https://github.com/ffworker/anthias-hub . Never publish `.env`, `config/` or `data/`.

## 1. Check host and Pi route (read-only)

Log in over SSH as the normal Docker-capable user on your Docker host.

```bash
ssh YOUR_USER@YOUR_DOCKER_HOST
hostname
docker compose version
ss -lnt | grep ':8765 ' || echo 'Port 8765 currently unused'
# Check connectivity to your TEST Pi; adjust IP after verifying it:
curl --max-time 5 -i http://TEST_PI_IP/api/v2/assets | head -n 16
```

If it is unreachable, investigate VLAN routing/firewall. A successful status
response does not confirm that the Anthias API schema matches our implementation.

## 2. Deploy as its own Compose project

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/YOUR_GITHUB_ACCOUNT/anthias-hub.git
cd anthias-hub
# This creates a local env, non-root permissions and an image; then prompts for logins:
bash scripts/setup-pilot.sh
```

The script uses the current host UID/GID for normal Docker-capable users. **When run
as root** (for example after `su -`), it instead configures the application
container to run as unprivileged UID/GID **10001:10001** and owns `config/` and
`data/` accordingly. This allows a privileged one-time deployment without
running the service itself as root. It creates a strong random session key,
sets `COOKIE_SECURE=0` **only for localhost HTTP over SSH tunneling**, builds
the image, and prompts for separate IT and Marketing passwords.

If your normal account can run `docker ps`, no `sudo` permissions are
required: use that account. If it cannot, log into root separately and run the
script there. You can `git pull --ff-only` as the repo-owning user **before**
switching to root to avoid Git's dubious ownership protection. Do not give a
normal account sudo solely to launch the Hub.

Do not run this in the existing RSS2Slideshow directory. The Compose project is
explicitly named `anthias-hub`. The `signage` Compose service is untouched.

## 3. Open from Windows PowerShell

```powershell
ssh -N -L 8765:127.0.0.1:8765 YOUR_USER@YOUR_DOCKER_HOST
```

In your Windows browser open http://localhost:8765 and sign in as `it`.
Use the IT dashboard to register the Pi by its private IP.

The `marketing` account manages playlists **inside the hub UI**; IT sees a
link to the original Anthias administration. Do not write to a production
playlist until you've taken a backup and tested the Anthias API against a spare
player. Editing content takes effect on the Pi itself, immediately.

## 4. Troubleshooting / updating (in the Hub directory only)

```bash
docker compose -p anthias-hub ps
docker compose -p anthias-hub logs --tail=80
docker compose -p anthias-hub down         # Stops ONLY the Hub; keeps ./config and ./data
git pull --ff-only
docker compose -p anthias-hub up -d --build
```

Never use `docker compose down` from the RSS2Slideshow directory to manage this
Hub. Do not use `docker system prune` just to update it.

## 5. Before Marketing uses this from normal company workstations

The SSH tunnel is for the initial test, not a company-wide access solution.
Implement an internal **HTTPS reverse proxy**, `COOKIE_SECURE=1`, network ACLs
and firewall isolation for the Pi API. Without those, a direct Pi management
URL may bypass the hub's IT/Marketing roles.

No live display preview is included in the pilot. The hub can show the playlist
and online/API status; a real capture of the TV output is a separate feature.
