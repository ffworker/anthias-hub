# One SMB root: clean installation and safe consolidation

This guide covers both a **new empty Hub** and moving an existing Hub from
separately mounted screen folders to one common read-only SMB parent. It does
not automatically change player media, schedules or passwords.

## Target architecture

```text
Approved private SMB share/subfolder   (exactly one host CIFS mount)
  -> /srv/anthias-sources/default       (host)
  -> /sources/default                   (web + importer containers)
       |-- Screen-A/                    (direct child = source default/Screen-A)
       |-- Screen-B/                    (direct child = source default/Screen-B)
       '-- ...
```

Each screen folder has its media as **direct files**. Only the direct child
folders of `default` are discovered. Nested `Screen-A/2026/` is not another
playlist. Hidden entries, symlinks and invalid names are skipped; only
PNG/JPEG/WebP/MP4 files are imported. **Discovery of folders is not automatic
creation of a playlist or activation of auto-publishing.**

## What works from a genuinely empty system?

1. `bash scripts/setup-pilot.sh --solo` creates a random session secret and
   an Owner account without requiring any SMB source or player. With no
   `--solo`, IT and Marketing accounts are created. The Hub web UI is reachable
   only on localhost by default.
2. IT registers a reachable Anthias Pi (the Pi runs independently).
3. Manual Pi uploads, ZIP import and library templates work without SMB.
4. For the optional folder workflow, IT mounts the **single** approved SMB
   parent read-only on the Docker **host**, at
   `/srv/anthias-sources/default`, using a protected host-only credentials
   file. The Hub container and separate importer both need read-only
   `/srv/anthias-sources:/sources` access in the existing site-specific
   Compose override / `compose.folder-import.yaml`.
5. In **Ordner & Quellen**, IT registers **alias `default`** and the approved
   `//PRIVATE-IP/SHARE/subfolder`. This saves a registry entry; it **does not
   give the unprivileged Flask process mount privileges**.
6. If the optional host mount coordinator is deployed, it must be running,
   have an explicit private allowlist, and report a recent successful
   verification. Saving the UNC in the UI **alone does not install** the
   coordinator or mount anything.
7. Once the parent is actually accessible at `/sources/default`, the direct
   children appear in the **Library → Create Playlist** dropdown as
   `default/Screen-A` etc. No per-screen CIFS mounts are necessary.
8. The separate importer must be running to copy those files into the Hub
   library. `compose.folder-import.yaml` requires
   `FOLDER_REQUIRE_MOUNT=1` and `FOLDER_REQUIRE_VERIFIED=1`; if the host
   coordinator/status verification is missing it **intentionally blocks**
   imports from registered shares. Do not disable these safeguards just to
   make a red status appear green.
9. `FOLDER_AUTO_PUBLISH=0` is the default. To publish to a Pi automatically,
   IT must separately assign its destination and explicitly approve the
   publisher after real-device testing. Until then the Pi playlist is unchanged.

**Important limitation:** a freshly cloned repository provides the Hub setup,
registry, importer and templates, **not an automatic privileged SMB host
bootstrap**. Set up the host mount/coordinator and private credential allowlist
before claiming the single-UNC workflow is ready. This is an operational
prerequisite, not a browser-only setting.

## Existing Hub: read-only preflight, no unmounts yet

Run on the **Hub host**, not on a Raspberry Pi. These commands do **not**
reconfigure Docker, Pi playlists or SMB. Do not post the output publicly:
source paths and registered device locations are operational information.

```bash
cd ~/apps/anthias-hub
# Does the approved parent mount REALLY exist? Listing a plain directory is not enough.
findmnt -M /srv/anthias-sources/default -o TARGET,SOURCE,FSTYPE,OPTIONS
findmnt -R /srv/anthias-sources -o TARGET,SOURCE,FSTYPE

# What is actually configured for templates? Names/aliases only, not credentials.
python3 - <<'PY'
from pathlib import Path
import json
for p in sorted(Path("data/library").glob("*/manifest.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    imported = sum(bool(i.get("source_file")) for i in d.get("items", []))
    print(f"{d.get('name','?')!r}: source={d.get('folder_source','—')!r}, "
          f"imported={imported}, target_count={len(d.get('auto_devices',[]))}")
PY

# Confirm the importer and Hub containers are separate, preserving live media.
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

**Keep the original mounts active** while verifying
`/srv/anthias-sources/default`. If the old and new mount point at the same
share/folder, compare a representative media file by hash, not only filename
or the web UI's folder count. Do not assume case or path-name equivalence.

### Why simply deleting old aliases is unsafe

A template that imported media from alias `screen-a` retains
`folder_source=screen-a` and all its item IDs, durations, ordering and
optional `auto_devices` assignments. Removing that mount does **not** rewrite
it to `default/Screen-A`. The library **intentionally refuses rebinding a
template with imported media** to a different alias, to protect its history.

Use a test copy of the template (or an explicitly reviewed migration procedure)
to validate the new source, duration settings and target mappings before
retiring the old alias. Do **not** directly edit JSON manifests while the web
app or folder importer is running. Do not remove the old alias or parent mount
as a way to force the UI to discover it.

### Safe retirement gate

- [ ] Full restricted backup of `.env`, `config/`, `data/` and the separate
      Pi playlist/schedules. Store it **outside the public Git working tree**.
- [ ] New single parent is a real read-only CIFS mount, reachable from **both**
      the Hub and importer. Host verification is current, not only an HTTP 200.
- [ ] All expected direct folders appear; exact folder names and files verified.
- [ ] Every existing `folder_source` and `auto_devices` mapping is recorded.
- [ ] Old imported templates have been safely migrated/recreated and their
      durations, order and optional RSS web slides checked.
- [ ] Importer logs and heartbeat show successful scans with no Pi publishing.
- [ ] One **test Pi** confirms intended media, timing and scheduling before
      auto-publishing is enabled for any production screen.
- [ ] Only then retire obsolete entries in the **host mount configuration** and
      the **Hub source registry**, one at a time. Do not delete source media.
      `findmnt` must show the expected remaining parent afterward.

The current Hub registry has **no bulk deletion/migration button** for old
aliases. Deleting a registry entry or unmounting a host share without updating
its dependent templates is not a supported shortcut.
