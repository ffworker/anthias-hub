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

1. IT mounts each SMB share read-only on the Hub host, under an alias in
   `/srv/anthias-sources/` (e.g. `bistro`, `reception`).
2. IT ensures both the Hub web container and the optional importer see that
   directory at `/sources` (read-only).
3. IT chooses an available network folder while creating a playlist in the
   library and assigns the target Pis. Alternatively, for one screen, use
   **Screen → Playlist → Add Content → Network Folder** to bind an existing
   share without uploading media. This does not enable automatic publishing.
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
- Order changes in Hub library are **not** automatically applied to Pi
  playlists. The folder-focused editor therefore does not promise reorder.
- Startup default: `FOLDER_AUTO_PUBLISH=0`. A saved folder-to-device mapping
  alone must not cause Pi writes.
- Worker heartbeat at `/data/folder-sync-status.json` shows last import health
  and actual worker publication flag. Backup `/data/folder-publications`
  alongside normal Hub data.

## Prototype acceptance checklist

- [ ] Verify Mount credentials and root directory on Hub host, read-only.
- [ ] Hub web dropdown lists only valid mounted aliases.
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
- [ ] Only then migrate Bistro from Binary Emotions to Anthias.

## Remaining development priorities

1. Safe removal of missing files after repeated successful scans with explicit
   mount-health checks; disable only previously owned assets.
2. Clear handling of manually hidden/slotted assets and cross-device ordering.
3. Per-screen observability and operator retry controls after partial writes.
4. Real Pi acceptance and repeatable rollout instructions for additional screens.

Keep the existing Binary Emotions SD card running until all acceptance items
are complete. Never apply the feature to production just because main passed CI.
