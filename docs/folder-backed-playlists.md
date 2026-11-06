# Folder-backed templates — read-only import, optional Pi publication

This feature is **experimental**. Its normal use is one approved parent SMB
mount with a directory per screen, not a separate SMB mount per playlist.

For a new VM, follow the [single-root setup and migration runbook](single-root-smb-setup.md)
first. It distinguishes **registering** a UNC in the UI from mounting it on
the host and verifying it for the isolated importer.

## Data flow

```text
SMB parent (one host mount)
  /srv/anthias-sources/default/Screen-A/*.png
    -> Hub /sources/default/Screen-A
    -> source alias default/Screen-A
    -> Hub library playlist template (imported media)
    -> optional, explicit tracked publication to a selected Pi
```

- The source picker lists only immediate child directories of
  `/sources/default`. Directory names may include spaces or umlauts;
  symlinks, hidden directories and nested directories are not playlist
  sources. Imported files must be directly inside their child folder.
- Web and importer containers need **read-only** `/sources` access. Compose
  examples and worker configuration are in `compose.folder-import.yaml`.
  Do not overwrite an existing site-specific override. The default web
  Compose setup does **not** include the network share.
- A separate root-controlled mount/coordinator may be used, with a protected
  allowlist and SMB credential file. The Flask process only stores
  `alias + UNC` in a private registry: **it cannot mount the share itself**.
- The worker uses `FOLDER_REQUIRE_MOUNT=1` and
  `FOLDER_REQUIRE_VERIFIED=1`. A running host-coordinator/status process is
  therefore needed for registered sources; saving a UNC is not enough.
- The worker imports incrementally every 300 seconds by default. Images keep
  their stored duration, identity and order when the file is replaced.
  Manual media and websites in a template remain separate.
- When a share is unavailable, imports stop; cached Hub media and Pi
  playlists are **not** deleted.
- Any existing imported template tied to an old alias cannot simply be
  rebound to `default/<child>`. That safety check is intentional. Run the
  [non-destructive migration checklist](single-root-smb-setup.md#existing-hub-read-only-preflight-no-unmounts-yet)
  before removing old mounts or registry entries.

## Optional Pi publication

A folder template may be assigned to selected devices, but assignment alone
does not publish anything. `FOLDER_AUTO_PUBLISH=0` is the server default.
Only after real test-Pi acceptance may IT enable `FOLDER_AUTO_PUBLISH=1`
for the separate importer worker.

Tracked publication uses source/version markers and journals under
`/data/folder-publications`. It targets only Hub-owned imported media and
does not replace all Pi playlist content. Changed files can be updated
without reuploading unrelated manual assets. Reordering is applied only when
the whole target playlist is known to belong to the same managed template.
Native schedules and manual enablement must be checked on the actual Pi.

**No strict mirror semantics:** deleting a file on SMB does not
automatically delete its Pi asset. The feature is intentionally conservative
until removal-after-repeated-verified-scan behavior is accepted.

## Operational acceptance

1. Confirm a **real read-only** parent mount and fresh host verification.
2. Confirm both containers can list the same direct child sources.
3. Create a template from `default/Screen-A`; run the importer with
   automatic Pi publication off; verify media/timing in the Hub only.
4. Verify changing a file retains Hub timing; verify a simulated missing
   share does not cause media removal.
5. Assign **one disposable test Pi**, explicitly enable publication, and
   check physical playback, schedules, retry/idempotency and rollback.
6. Retain a confidential backup of Hub state, journal and each Pi's own
   playlist before enabling production publishing. Never delete an old
   host mount merely to force source rediscovery.

The repository supports the app and importer, but a totally fresh machine
still needs OS/Docker, network security, host mount/coordinator, credentials
and real-device acceptance. This is not an unattended, one-click SMB installer.
