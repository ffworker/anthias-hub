# Publishing this as a NEW public repository

This folder is intentionally **not** committed to `ffworker/rss2slideshow`. Make a separate **public** GitHub repository (suggested name: `anthias-hub`).

1. In GitHub, create **New repository** -> name `anthias-hub` -> **Public** -> create **empty** (no generated README, .gitignore or license).
2. From the local extracted folder:

   ```bash
   git init -b main
   git add .
   git status --short
   git commit -m "feat: initial Anthias Hub with static IT and Marketing roles"
   git remote add origin https://github.com/YOUR_ACCOUNT/anthias-hub.git
   git push -u origin main
   ```

3. Review `.gitignore` before pushing. Do **not** commit `.env`, `config/users.json`, actual internal device IP addresses, or `data/`.
4. In `ffworker/rss2slideshow` add a one-line README reference to the newly verified GitHub URL after the new repository exists. The Anthias Hub README already links back to RSS2Slideshow.

Never treat source/publication as proof of a successful production rollout. Run the tests and validate with a nonproduction Anthias Pi.

Fast path when GitHub CLI is available: `bash scripts/publish_to_github.sh anthias-hub` (interactive confirmation, creates a new public repo).

## Windows → Docker host test deployment

From Windows PowerShell, you can publish using `git` as shown in the README;
no Linux Bash or GitHub CLI is needed for that path. After the push, SSH into
your test Docker host, clone the *new* repo into `~/apps/anthias-hub`, and execute:

```bash
bash scripts/setup-pilot.sh
```

This starts a separate Compose project on localhost port 8765 and creates
IT/Marketing accounts interactively without installing Python packages on the
host. See [docs/deploy-docker-host.md](docs/deploy-docker-host.md) for safety checks,
tunnel, troubleshooting and restrictions.
