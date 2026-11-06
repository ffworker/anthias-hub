# Folder-backed playlist templates (experimental)

This first increment adds **automatic import to Hub library templates**, not yet
automatic deployment to Anthias players. Existing Pi playlists, schedules and
manual media are **never changed** by the folder worker.

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
