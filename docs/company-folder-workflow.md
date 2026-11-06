# Folder-first Digital Signage – Marketing & IT workflow

## Intended company workflow (prototype)

**Marketing keeps using the existing file shares.** No new upload routine and
no SMB credentials in the browser. IT configures named read-only source
directories and maps one Hub playlist template to one or more registered
Anthias players.

| Who | Where | Responsibility |
| --- | --- | --- |
| Marketing | Existing SMB folder | Add, replace or remove files as before |
| Marketing | Hub playlist template | Set display seconds for individual images and web slides |
| IT / Owner | Hub template | Select source alias, target Pis, and configure RSS2Slideshow web feed |
| IT / Owner | Host deployment | Mount read-only folders, deploy importer, approve auto-publish |
| Anthias Pi | Native playlist | Play cached media and webpage URLs independently of Hub |

**Roles:** IT now inherits all Marketing editing operations. Marketing cannot
change devices, network shares or auto-publication targets. Viewer is read-only.

## User journey

1. **Preferred:** IT mounts one approved parent SMB directory read-only at
   `/srv/anthias-sources/default`; its direct subfolders become independent
   sources such as `default/Screen-A`. Multiple individual CIFS mounts are
   optional legacy compatibility, not necessary for this workflow. See the
   [single-root setup](single-root-smb-setup.md).
2. IT ensures both the Hub web container and the optional importer see that
   directory at `/sources` (read-only).
3. IT chooses an available network folder while creating a playlist in the
   library and assigns the target Pis. Alternatively, under **Bildschirm →
   Playlist → Inhalt hinzufügen → Netzwerkordner**, IT explicitly chooses:
   **one-time import** (up to 20 files, append-only to Pi) or **automatic
   binding** (no immediate upload; server-side publisher remains disabled).
4. Marketing continues saving images and videos in the share. The importer
   scans every 300 seconds by default and shows a heartbeat in the template.
5. Marketing opens the **same template**, edits each image's duration, and
   saves. These settings persist even if the image is replaced on the share.
   Video playback uses its native full length.
6. IT optionally adds the *existing* RSS2Slideshow custom design URL as a
   website entry. It is published alongside imported media and its display
   duration is editable in the same template.
7. After test-Pi acceptance, IT activates `FOLDER_AUTO_PUBLISH=1` for the
   separate worker. The per-template target mapping is an additional opt-in.

The feed URL must be reachable **from the Anthias Pi**, not just from Hub;
its visuals and availability remain the responsibility of RSS2Slideshow.
Do not duplicate the RSS service inside Anthias Hub.

## Change handling and safety

- Supported folder media: PNG/JPG/JPEG/WebP/MP4. ZIP and Thumbs.db are ignored.
- New files are imported; changed files keep item ID, order and Marketing
  duration in the Hub template.
- The worker uses versioned Anthias asset names. On a changed file it stages
  the replacement before deactivating the previous managed version.
- A changed image or website *duration* is PATCHed directly and confirmed by
  a fresh player read; there is no unnecessary media reupload.
- The worker never deletes remote assets or changes unrelated manual media.
- An unavailable/missing SMB folder does not remove previously cached assets.
  **Deleted files are not yet removed automatically**: implement conservative
  missing-file reconciliation only after repeated verified scans and test-pi
  acceptance. Do not mistake this prototype for a strict mirror.
- Order changes in the Hub library are applied **only** when the target Pi
  contains exclusively assets tracked by that Hub template. Mixed/manual
  playlists are never globally reordered because Anthias' API order call
  affects the whole player playlist.
- Startup default: `FOLDER_AUTO_PUBLISH=0`. A saved folder-to-device mapping
  alone must not cause Pi writes.
- Worker heartbeat at `/data/folder-sync-status.json` shows last import health
  and actual worker publication flag. Backup `/data/folder-publications`
  alongside normal Hub data.

## Prototype acceptance checklist

- [ ] Verify the single SMB parent at `/srv/anthias-sources/default` is a real
      read-only mount, **not only a directory**. Credentials and allowlist
      remain host-private.
- [ ] Hub web dropdown lists the expected direct `default/<subfolder>` sources.
      A registered UNC is not proof of a verified mounted source.
- [ ] Import worker runs and reports recent heartbeat.
- [ ] Existing SMB media appears in Hub template; no changes on the Bistro Pi.
- [ ] Marketing image timing survives two replacements of the SMB source.
- [ ] IT can perform all Marketing actions; Marketing cannot change sources or targets.
- [ ] RSS2Slideshow design URL opens correctly in a test Pi's Anthias viewer.
- [ ] New and changed files publish to test Pi, preserve native schedule.
- [ ] Repeated imports/publishes do not create duplicated active assets.
- [ ] SMB outage does not wipe active content.
- [ ] Missing-file handling designed and tested before promoting to production.
- [ ] Backs up and restores Hub data; rollback to original Bistro boot media tested.
- [ ] For each remaining legacy screen, confirm the new Anthias player and playlist before switching devices.

## Remaining development priorities

1. Safe removal of missing files after repeated successful scans with explicit
   mount-health checks; disable only previously owned assets.
2. Clear handling of manually hidden/slotted assets and cross-device ordering.
3. Per-screen observability and operator retry controls after partial writes.
4. Real Pi acceptance and repeatable rollout instructions for additional screens.

For any replacement screen, retain its previous boot media as a rollback path
until the Anthias display is accepted. Never apply new folder publishing to a
production screen just because CI passed.
