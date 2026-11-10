# Public repository hygiene

Anthias Hub is public. The source tree must not contain employer inventory,
operational hostnames, real SMB paths, passwords, private keys, Caddy CA keys,
internal network maps, actual player URLs or live customer/media data.

## Controls for future contributions

- Keep all runtime state private: `.env`, `config/`, `data/`, mount
  credentials, site-specific Compose overrides, SSL keys and backups must
  never be committed.
- `scripts/check_public_repo.py` is executed in CI and inspects **tracked
  text files only**. It blocks obvious key/token formats, runtime artifact
  filenames and company-style internal host identifiers. It prints categories
  and file/line locations **without printing values**.
- Site-specific VLAN IDs, DHCP scopes, lease allocations, Pi MACs and internal IP maps belong in restricted internal documentation, not in the repository. The `.gitignore` excludes common internal documentation names, but this is only a safeguard; review staged files and history before any commit.
- Use dummy names such as `Screen-A` and documentation-only DNS suffixes.
  RFC 5737 addresses are appropriate for example public/test IPs.
- Before uploading any screenshots, media, PDFs or ZIPs, check their content
  and metadata manually. The text scanner explicitly does **not** understand
  binary attachments or distinguish confidential business material from
  ordinary documents.
- Run a credential scanner on the **full Git history** (including branches,
  old commits, releases and CI artifacts), not only `HEAD`, before describing
  the public repository as free of secrets. `.gitignore` does not protect
  anything already committed.
- An accidentally committed secret must be **revoked/rotated immediately**.
  Removing it from `main` does not remove the leaked historical object,
  forks, cached pages or build artifacts.

## Local checks, from a complete clone

```bash
git fetch --all --tags
python3 scripts/check_public_repo.py
git ls-files -- .env config data
# Review history privately. Never paste potential secret values into issues.
git log --all --name-only --pretty=format: | sort -u
```

The source checker cannot guarantee that every private detail has been found.
A public GitHub repository is the wrong place for company-specific runbooks or
installation secrets, even if a test machine is only used temporarily.
