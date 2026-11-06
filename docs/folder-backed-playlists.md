# Folder-backed playlist templates (experimental)

The folder importer supports **automatic import to Hub library templates** and
opt-in publication of folder-managed media to selected Anthias players.
**Automatic Pi publication is disabled by default** (server-side). Existing manual
Pi assets are never modified.

## Host setup

Mount SMB/NFS shares on the **Docker host**, read-only, in distinct subfolders
under one root, e.g. `/srv/anthias-sources/bistro` and
`/srv/anthias-sources/empfang`. Mount with systemd/fstab credentials protected
outside the repository; **never** store credentials in the Hub UI or Git.

Example mappings:

| Source alias in Hub | Host directory | Destination |
| --- | --- | --- |
| `bistro` | `/srv/anthias-sources/bistro` | Hub template “Bistro” |
| `empfang` | `/srv/anthias-sources/empfang` | Hub template “Empfang” |

In production use the existing `compose.cd.yaml` and its **existing external
override**. Add `compose.folder-import.yaml` to the same compose command:

```bash
export MEDIA_SOURCE_HOST_PATH=/srv/anthias-sources
export FOLDER_SYNC_INTERVAL=300
docker compose -f compose.cd.yaml -f "$HUB_COMPOSE_OVERRIDE" \
  -f compose.folder-import.yaml -p anthias-hub up -d --no-deps anthias-folder-import
```

The worker is isolated from the web server, reads host folders from `/sources`
(read-only), and writes only to the existing Hub library under `/data/library`.
**Do not recreate the production Hub web container** just to start this worker.
The existing Hub web container also needs read-only access to `/sources` to
validate newly entered aliases. Add that binding in the existing site override
before using the UI:

```yaml
services:
  anthias-hub:
    volumes:
      - /srv/anthias-sources:/sources:ro
```

Merge this entry into the existing override; preserve all other service settings
and volume bindings. Do not replace the override with this snippet.

Open the template in the library, expand **Netzwerkordner als Medienquelle (IT)**,
and enter only the alias (e.g. `bistro`), *not* the UNC path.

## Safety / scope

- Allowed extensions: PNG, JPG, JPEG, WebP and MP4; existing size/signature
  checks apply.
- The importer reads only regular direct children; no symlink traversal.
- Changes are imported incrementally; existing manually uploaded media and
  websites are not touched.
- Missing, empty and unavailable shares **do not delete** previously imported
  media. Removing a source binding also leaves imported media in place.
- A completed import updates the **Hub library template only**. Use the
  existing explicit "Vorlage zur Playlist hinzufügen" action for player delivery.
  Repeating that action can duplicate media on a Pi.
- Automatic tracked publish/update/delete, timing, per-device assignment and
  crash-safe idempotent reconciliation need a separate implementation and
  real-device acceptance tests before enabling them.
- If the worker reports an error, check its logs and the share mount; the
  current playing playlist is deliberately left alone.


## Optional automatic Pi publishing (second phase)

Each folder-backed Hub template can have one or more registered target Pis.
IT opens the template, enters a source alias, and selects **Zielbildschirme**.
This mapping is inactive until the worker is launched with
`FOLDER_AUTO_PUBLISH=1` (default: `0`). Use only a **test Pi** first.
The folder importer continues to run even while auto publishing is off.

Expected workflow:

1. Mount each SMB/NFS folder read-only on the Hub host. Check permissions
   for the UID/GID of the Hub container.
2. Give the Web Hub and worker read-only `/sources` access using the
   documented Compose override. Preserve the original network and TLS settings.
3. Create a Hub template, bind `bistro` as folder alias, and select a
   registered **test Pi** under the IT-only targets.
4. With `FOLDER_AUTO_PUBLISH=0`, run the worker and verify files appear
   in Hub library. The Pi must remain untouched.
5. On a test device only, enable the worker option with
   `FOLDER_AUTO_PUBLISH=1` and validate playback, schedules and error recovery.
6. Switch to Bistro only after separate on-screen acceptance.

The worker writes a per-template / per-device journal at
`/data/folder-publications/<template-id>/<device-id>.json`.
Keep it with your normal `/data` backups. Losing it can make adoption
ambiguous: never wipe it while auto publishing is running.

### Reconciliation safety

- Only folder-imported media entries are managed, never manually added
  Pi content or Hub websites.
- Per-file deterministic version markers avoid duplicating remote assets
  after a process crash. No playlist-wide replace, no reorder.
- New media is created disabled and checked before enabling it.
- On a file update, the previous asset's Anthias-native schedule is copied
  and confirmed before the old version is disabled. Current manual enable/
  disable state is retained across revisions.
- A remote asset that was renamed outside the Hub is **not overwritten**.
  IT must resolve the conflict before continuing.
- Failures stop that file; other source templates/devices continue.
- No automatic remote deletion. **Removed files are retained** as a deliberate
  safety restriction until mount-health and removal policy are proven.
  Do not claim strict mirror semantics yet.
- The Pi remains able to play its existing files if the Hub, NAS, or worker
  goes offline.

### Important limitations

The new feature must not be enabled on production devices until it is
validated with a real Anthias player and recovery tests. Upstream Anthias
API behavior varies across versions; the automated tests use a simulated
player, not a live display.

The UI stores the target mapping, but server-side publication activation is
an IT deployment operation. Never expose SMB credentials in the UI.
