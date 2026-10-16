# Optional network access: SSH, isolated LAN, and HTTPS

These examples use **documentation-only values**. Substitute host-local values and keep them out of commits, public screenshots and issues. Anthias Hub listens on `127.0.0.1:8765` by default. DNS maps a name to an IP address; it **does not map TCP ports**.

## A. Local SSH tunnel (default)

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 ADMIN@SERVER_IP
```

Then open `http://127.0.0.1:8765` on that workstation. No server-side proxy is needed.

## B. Direct LAN HTTP (isolated testing only)

Create a DNS **A record** on your internal DNS server: `hub.example.internal` → private server address. This example is NOT an operational hostname. Bind only the desired host LAN IP on TCP/80:

```yaml
# /etc/anthias-hub/compose.lan.yaml -- VM-local, not committed
services:
  anthias-hub:
    ports:
      - "${HUB_LAN_BIND_IP:?Set HUB_LAN_BIND_IP}:80:8765"
```

In your private `.env`, add `HUB_LAN_BIND_IP=<SERVER_LAN_IP>` and
`HUB_COMPOSE_OVERRIDE=/etc/anthias-hub/compose.lan.yaml`. Keep `COOKIE_SECURE=0` only for a strictly isolated, temporary HTTP pilot. Then verify the merged config **before** recreating the running service:

```bash
docker compose -f compose.yaml -f /etc/anthias-hub/compose.lan.yaml -p anthias-hub config
docker compose -f compose.yaml -f /etc/anthias-hub/compose.lan.yaml -p anthias-hub up -d --no-build --no-deps anthias-hub
```

The existing localhost `127.0.0.1:8765` binding remains. Access `http://hub.example.internal`, test DNS and TCP/80 from an authorized workstation. **HTTP exposes login credentials and session cookies in transit; do not use it for regular business logins.** Restrict TCP/80 to approved clients and account for Docker port publishing bypassing naïve host firewall rules. Block direct client access to the Pi's management API. No proxy or DNS record is created automatically.

## C. HTTPS through an existing reverse proxy (recommended)

Keep the default localhost-only Hub port. On a trusted **host-local** reverse proxy, terminate TLS and forward to `http://127.0.0.1:8765`; preserve `Host` and set/overwrite `X-Forwarded-Proto: https` and `X-Forwarded-For`. For example, an existing Nginx can be configured with:

```nginx
server {
    listen 443 ssl;
    server_name hub.example.internal;
    ssl_certificate /etc/ssl/private/hub-cert.pem;
    ssl_certificate_key /etc/ssl/private/hub-key.pem;
    location / {
        # Hub backup request limit: 2 GiB + 2 MiB, including multipart body.
        client_max_body_size 2050m;
        client_body_timeout 2400s;
        proxy_read_timeout 2400s;
        proxy_send_timeout 2400s;
        proxy_request_buffering off;
        proxy_http_version 1.1;
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

Certificate files in this example are placeholders. For internal-only domains use your organization's internal CA and **distribute trust to clients**. Public CAs such as Let's Encrypt generally do not issue certificates for private `.internal` names. Alternatively use a publicly owned domain with DNS-01 validation and split DNS.

In the private `.env`, set `COOKIE_SECURE=1`. Set `TRUSTED_PROXY_COUNT=1` **only** when exactly one trusted proxy sits between browsers and Hub and users cannot reach the underlying application port directly. Otherwise leave it `0` (the default); forwarded headers will not be trusted. The app only trusts forwarded client IP and scheme, **not** forwarded host. Recreate the container to load changes. Terminate HTTPS on the proxy; do not expose the backend port publicly.

For a reverse proxy on another host, a host-local loopback bind cannot be reached: use an explicitly protected private/VPN interface listener with network ACLs instead. Do not replace loopback with `0.0.0.0` or rely on DNS alone for security.

## D. Optional: Caddy + your own internal HTTPS CA (no external CA required)

This option is suitable for a **private test/LAN VM** with an existing DNS A
record, no enterprise CA and no publicly trusted certificate. Caddy runs as
a **host systemd service**, not inside the Anthias Hub Compose project. Its
`tls internal` directive creates a Caddy-managed **local root CA and leaf
certificate**. Clients do **not** trust this CA automatically: IT must verify
and install the public root certificate on each authorized client (or deploy
it centrally). This is not publicly trusted Let's Encrypt HTTPS.

**Example values only:** `hub.example.internal` and `192.0.2.10`. Use the
actual VM DNS name and the VM's dedicated LAN address on your own system;
**never commit real company hostnames, IPs, credentials or CA keys.**

### 1. Check the existing services; keep both applications running

On the Hub VM, read-only:

```bash
sudo ss -lntp | grep -E ':(80|443|8765|8085)[[:space:]]' || true
docker ps --format 'table {{.Names}}\t{{.Ports}}'
systemctl is-active anthias-hub-cd.timer || true
curl -fsS http://127.0.0.1:8765/healthz
```

Confirm TCP/443 is available, the Hub still listens on
`127.0.0.1:8765`, and any second co-hosted app retains its own separate
Compose project and ports. If another HTTPS proxy is already installed,
**integrate with it instead of replacing or conflicting with it**. Resolve
`hub.example.internal` to the VM LAN address **from an actual workstation**
(the VM itself might use different DNS). Do not restart Docker or RSS2Slideshow.

### 2. Install and configure the host-local Caddy service

Debian/Ubuntu example using the distro-provided Caddy package:

```bash
sudo apt update
sudo apt install -y caddy
sudo cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak-$(date +%Y%m%d-%H%M%S)"
sudoedit /etc/caddy/Caddyfile
```

Example **entire** `/etc/caddy/Caddyfile` (replace the example name and IP):

```caddyfile
{
    auto_https disable_redirects
}

https://hub.example.internal {
    bind 192.0.2.10
    tls internal
    reverse_proxy 127.0.0.1:8765
}
```

Binding only to the VM LAN address on port 443 keeps the existing Docker
port-80 mapping undisturbed during the trial. `disable_redirects` prevents
Caddy from trying to serve an automatic port-80 redirect during this phase.
A package's initial default Caddy service may fail to bind port 80 if Docker
already owns that port; after replacing the configuration, check the service:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reset-failed caddy
sudo systemctl enable --now caddy
sudo systemctl restart caddy
sudo systemctl is-active caddy
sudo ss -lntp | grep ':443 '
```

Validate HTTPS using Caddy's **public** root certificate (the Debian package's
default storage path; locate it from Caddy's data directory if customized):

```bash
sudo test -f /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt
curl --fail --silent --show-error \
  --cacert /var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt \
  --resolve hub.example.internal:443:192.0.2.10 \
  https://hub.example.internal/healthz
```

Expected: `ok`. This proves that the **server's** certificate chains to the
new local CA; it does not yet make client browsers trust that CA. Do not
use `curl -k` or click through browser security warnings as a substitute.

### 3. Establish CA trust on an authorized Windows client

Transfer **only the public CA root certificate** via an authorized SSH/SCP
channel. Example Windows PowerShell (`ADMIN@SERVER` requires read access
to the public `root.crt` file; an administrator may need to make a temporary
readable copy for SCP):

```powershell
scp ADMIN@SERVER:/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt "$env:USERPROFILE\Downloads\hub-caddy-root.crt"
Get-FileHash "$env:USERPROFILE\Downloads\hub-caddy-root.crt" -Algorithm SHA256
```

On the VM, independently calculate `sudo sha256sum
/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt`.
**Compare the file's SHA256 hashes through your trusted SSH channel** before
importing. Trusting a root CA lets it issue certificates for *any* host; do
not install a root certificate from an unknown source or publish it as an
unverified web download.

For a single, explicitly authorized Windows user:

```powershell
Import-Certificate -FilePath "$env:USERPROFILE\Downloads\hub-caddy-root.crt" -CertStoreLocation Cert:\CurrentUser\Root
```

Windows domain-wide deployment should be an IT-approved GPO to **Trusted
Root Certification Authorities**, with appropriate ownership and lifecycle.
Close and reopen Edge/Chrome after importing. Firefox or non-Windows clients
may use separate certificate stores and need their own trust setup. Verify
`https://hub.example.internal/login` opens **without** a TLS warning and
that a freshly loaded form logs in on the **first attempt**. Do not switch
between IP address, `http://` and the DNS name while testing cookies. If
the browser still reports `Invalid CSRF token`, use the troubleshooting
section below; HTTPS alone does not prove or cure session-cookie issues.

### 4. Switch cookies to HTTPS and retire direct LAN HTTP

Do this **only once the HTTPS browser test succeeds**. Changing
`COOKIE_SECURE` alone does not protect port 80: the existing LAN Docker
publish remains reachable until the external Compose override is changed.
Conversely, enabling secure cookies while staff still use HTTP makes their
login fail.

For an existing `:latest` test VM with the systemd updater, **do not run
`scripts/setup-pilot.sh` or switch back to `compose.yaml`**. Take an
off-host backup of `.env`, `config/` and `data/` and inspect the currently
installed `HUB_COMPOSE_OVERRIDE` first. Pause only the Hub auto-deploy
timer during the coordinated switch:

```bash
cd ~/apps/anthias-hub
sudo systemctl stop anthias-hub-cd.timer
grep -E '^(COOKIE_SECURE|TRUSTED_PROXY_COUNT|HUB_COMPOSE_OVERRIDE|ANTHIAS_HUB_IMAGE)=' .env
# Back up .env and the existing external override in a restricted location.
# Edit the existing .env and override carefully; never replace other settings.
```

In the private `.env`, set `COOKIE_SECURE=1`. Remove the **LAN port
80 publish** from the existing external Compose override, while retaining
the base `127.0.0.1:8765` port and all other site-specific changes. The
override file must **continue to exist at the same absolute path** because
the updater relies on `HUB_COMPOSE_OVERRIDE`. If the override contained
*only* an additional LAN port, its minimal contents may become:

```yaml
services:
  anthias-hub: {}
```

With that port closed, and **only if Caddy is the sole trusted proxy route
to the backend**, set `TRUSTED_PROXY_COUNT=1` so Flask recognizes Caddy's
forwarded HTTPS scheme. Do not enable this while clients can connect
directly to Hub port 80 or another untrusted backend entry point: forged
`X-Forwarded-*` headers would then be accepted.

Preview **the actual resolved published ports** before any recreate;
Compose's full unfiltered output contains expanded secrets, so do not paste
it into logs or public issues:

```bash
OVERRIDE=$(sed -n 's/^HUB_COMPOSE_OVERRIDE=//p' .env)
test -n "$OVERRIDE" && test -f "$OVERRIDE" || { echo 'Missing override'; exit 1; }
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub config --format json \
  | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["services"]["anthias-hub"]["ports"],indent=2))'
# Expected: only the loopback 127.0.0.1:8765 binding; NO LAN :80.
```

If correct, recreate **only** Anthias Hub to apply environment and port
changes, keeping the existing `:latest` image:

```bash
docker compose -f compose.cd.yaml -f "$OVERRIDE" -p anthias-hub up -d --no-build --no-deps anthias-hub
curl -fsS http://127.0.0.1:8765/healthz
sudo ss -lntp | grep -E ':(80|443|8765|8085)[[:space:]]' || true
sudo systemctl start anthias-hub-cd.timer
```

Check the HTTPS login, authenticated navigation and transfers from an
authorized client. Port 443 should still be owned by Caddy; the Hub should
not be reachable over direct LAN HTTP. Confirm the Hub timer is active and
the other co-hosted application's container was never recreated. If
anything fails, restore the saved private environment/override through a
controlled rollback while keeping the previous service isolated from normal
LAN users.

### 5. Back up the CA; understand its trust scope

Caddy stores its local CA under its data directory (default on this setup:
`/var/lib/caddy/.local/share/caddy/pki/`). Back up **CA configuration,
certificate and private keys** securely, encrypted and **off-host**, with
limited administrator access and a tested restore procedure. Never commit
`root.key` or any private key to Git, distribute it to clients, or bundle
it with an application backup. Clients get **only `root.crt`**. Losing the
CA key during a VM rebuild may require distributing a new trusted root
to all clients; theft would compromise every client trusting it. For a
larger organization, prefer its centrally managed PKI over an ad hoc CA.

The Caddy service is separate from the Hub's GHCR automatic-image updater;
the latter does not upgrade, back up or restore Caddy's systemd configuration
or its CA files. **This runbook does not deploy certificates, host firewall
rules or changes to a running VM on its own.**

## Troubleshooting: login fails with CSRF error on a new browser

A **first-time login should work on its first attempt**. The login form's hidden
CSRF token belongs to a signed browser session cookie issued by `GET /login`.
`POST /login` needs that cookie **and** the corresponding form token. If the
cookie is missing, blocked, or signed by a different secret, the request is
rejected; the Hub does not skip CSRF even for the first login.

- **Verify the browser URL:** Keep the same exact origin (hostname/IP,
  scheme and port) from opening the login form through submitting it. Avoid
  switching HTTP ↔ HTTPS or IP ↔ DNS name across requests.
- **Verify cookie mode:** `COOKIE_SECURE=1` requires HTTPS for ordinary remote
  browsers. Direct LAN HTTP is only permitted during isolated testing with
  `COOKIE_SECURE=0`. After changing the private `.env`, recreate the Hub
  container via the correct Compose base and existing LAN override. Do not
  weaken cookie settings on a regular HTTPS deployment.
- **Check DevTools locally:** Network → `GET /login` should receive
  `Set-Cookie: session=...`; the matching `POST /login` should send a
  `Cookie: session=...` header. Inspect the browser's cookie-block reason.
  Never paste actual cookie contents or form tokens into an issue/chat.
- **Check logs:** The Hub logs `Login CSRF rejected:
  missing_session_token` when the submitted session has no token, or
  `token_mismatch` when the form and saved token differ. It also records
  only the request HTTPS state and secure-cookie setting, **not** credentials,
  cookies or token values. A missing session can also indicate inconsistent
  `APP_SECRET_KEY` values across multiple application instances.
- **Stale tabs:** Refresh the login page after changing the URL or deployment
  before retrying. The displayed message does not imply a bad password.

Login CSRF errors are a **browser → Hub session** problem, not a
Hub → Raspberry Pi API/firewall problem. If a clean HTTPS session still fails,
record the browser URL scheme (no internal hostname required), cookie blocked
reason and sanitized log failure category.

## Updates, rollback and local overrides

Standard `compose.yaml` and `compose.cd.yaml` remain unchanged. **All manual Compose commands affecting the Hub must repeat the same `-f <base> -f <absolute override>` list** (including pull/up/rollback), rather than switching back to base-only Compose. The optional test-only `scripts/auto_deploy.py` and `setup-pilot.sh` now read `HUB_COMPOSE_OVERRIDE` from the private `.env` and refuse a missing/non-absolute override. This prevents the next automatic container recreation from dropping the extra port mapping. Do not put LAN addresses in the checked-in source.

Validate `docker compose ... config`, DNS, TLS, login and Pi reachability after changing exposure. Do not turn the test-only `:latest` updater into a production rollout mechanism.

## Network boundaries

- Browser → Hub: allow only authorized clients via HTTPS/VPN (isolated HTTP pilot is exceptional).
- Hub → each Pi: permit necessary Anthias API requests.
- Browser → Pi management API: block except explicitly trusted IT clients.
- Keep SSH and any optional co-hosted application separately restricted.

Neither this guide nor the repository changes system DNS, firewall rules, TLS certificates or the live VM.
