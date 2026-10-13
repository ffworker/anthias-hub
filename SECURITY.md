# Security model / deployment boundary

- **Do not expose Anthias directly to Marketing clients.** By default, the Anthias API is intended for trusted networks, and it may have no authentication. Enforcement of per-role privileges only works if Pi management endpoints are restricted to the hub and trusted IT clients by firewall/VLAN rules.
- **Do not expose this hub to the public internet in its current form.** Protect it with an internal HTTPS reverse proxy, VPN, and an allowlisted audience. Simple static logins are adequate for the intended internal use, not for a multi-tenant public SaaS.
- Static credentials are locally configured, **scrypt-hashed**, and deliberately not in Git. Use individual passwords, change them if shared, and protect `config/users.json` with filesystem permissions.
- One Gunicorn worker uses a memory-based login rate limit. A hostile internet-facing deployment requires stronger rate limiting, centralized sessions, audit retention, and security review.
- User-controlled device API paths are not forwarded directly. Registered device addresses require private IP literals inside `ANTHIAS_ALLOWED_CIDRS`. Anthias calls never follow HTTP redirects.
- Upload validation is rudimentary file signature checking only. Scan content and consider a separate quarantined media workflow if expanded to less trusted users.
- All POST forms are protected by signed-session CSRF tokens. Use `COOKIE_SECURE=1` when served over HTTPS; set `COOKIE_SECURE=0` **only** for localhost/SSH tunnel testing.
- Full Anthias device settings are **not** exposed to Marketing through the hub. However, all authorized Marketing users in this version can edit any registered playlist. No per-location role scoping yet.
- Back up host-owned `./data/` (`devices.json` and `audit.jsonl`), `./config/users.json`, and the Anthias players' own data independently. Use host UID/GID values in `.env` so the container runs without root while retaining access to private `0600` account hashes.
- This code is unverified against production Pi versions and must be security-tested prior to real company-wide use.

Please report potential vulnerabilities privately to the repository owner; avoid posting company addresses or credentials in public issues.
