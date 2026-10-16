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
