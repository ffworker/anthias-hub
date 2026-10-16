# Large uploads: audited limits and controlled rollout

> **Pilot amendment · 16 October 2026:** The operator has requested a **4-GiB hard per-file limit** for staged testing with a fresh Anthias Pi 3. Browser, Flask, streaming player upload, library and template ZIP backup limits have been aligned; the request cap is 4 GiB + 16 MiB, ZIP64 is kept, and browser/Gunicorn/Pi read timeouts are extended. **No 4-GiB real-device transfer has been verified yet.** The two-copy disk accounting, mounted-filesystem verification, 2-GiB/20% Pi reserve, 1-GiB Hub reserve and explicit unknown-only override remain unchanged. A 4-GiB file needs roughly 10+ GiB of genuine Pi free space. FAT32 cannot hold a full 4-GiB file. Test a small MP4 then 600 MB before larger sizes. Tables and results below describe the historical **1-GiB baseline** audited on 15 October, not the updated limits. See [Marketing upload limits](marketing-bulk-import.md).


> **Policy amendment · 16 October 2026:** The operator chose Anthias
> `/api/v2/info.free_space` as the authoritative source for the Pi3/Pi5 pilot.
> Automatic uploads no longer depend on `ANTHIAS_VERIFIED_STORAGE_URLS`.
> Each file is checked against the **API-derived, current available budget**,
> retaining space for two concurrent Pi copies and the existing reserve of
> max(2 GiB, 20% of measured free). The 4-GiB per-file hard cap is separate:
> a smaller file may still fit on a Pi with less than 4 GiB reported free.
> Explicit manual override is only for an unknown/unavailable API reading;
> reported insufficient space still blocks.
>
> The older storage attestation instructions and baseline below document
> historical policy and are superseded. Anthias measures root free space;
> external/separate media mounts remain a known accuracy limitation.

Audit base: Hub `4576e70` (2026-10-15). Upstream source inspected at
[Anthias 0edf7917](https://github.com/Screenly/Anthias/tree/0edf7917f776005167d26330c970b24dcc9a7959).
No live Hub or Pi was changed or load-tested. Installed Pi version, mount layout,
actual free bytes, proxy configuration and playback capability remain unverified.

## Why 1 GiB, and why not simply 4 GiB?

1 GiB is a Hub policy, not a demonstrated Anthias protocol limit. It occurs in
browser validation, Python media validation, library validation and bulk limits.
The incoming request ceiling is separately 2 GiB + 2 MiB for template backups.
Changing just Flask's limit would not make a larger video work end to end.

This release retains **1 GiB per file**. There is intentionally no partially
working `MAX_UPLOAD=4G` switch. First resolve storage provenance and qualify the
installed Anthias version. A later configurable ceiling should default to 1 GiB,
validate a bounded 1–4 GiB range at startup, generate browser limits/messages from
that same setting, and update the request, library and backup bounds together.
Ordinary media ZIP bomb limits must remain independent.

## End-to-end findings

| Stage | Finding / current limit |
| --- | --- |
| Browser | 1 GiB/file; at most 20 selected files, submitted sequentially. 40-minute XHR deadline includes both hops. 100% only means received by Hub. Browser error/cancel cannot reliably cancel a transfer already running on the Hub. |
| Flask / Werkzeug | Request cap 2 GiB + 2 MiB. Each multipart file now goes directly to a guarded disk temporary file, including while CSRF form parsing runs. Parsing errors close all opened streams even before `request.files` exists. |
| Hub storage | Docker already sets `TMPDIR=/data`; `/tmp` remains tmpfs. An explicitly invalid/unwritable TMPDIR now prevents startup instead of silently falling back. Do not set TMPDIR to tmpfs for large uploads. Each media write checks the actual file descriptor's filesystem and retains 1 GiB. |
| Library / ZIP | Media persists in bounded chunks; incoming spool and saved copy can coexist. Backup export and restore use disk and ZIP64. Exports whose uncompressed contents exceed the 2 GiB restore limit or 100,000-byte manifest limit are rejected before archive creation. Ordinary ZIPs remain 50 MiB compressed, 50 MiB/entry, 150 MiB expanded. |
| Gunicorn | Default one worker / four threads, timeout 2400 seconds. `gthread` worker timeout is a worker-liveness mechanism, not a guaranteed per-request deadline. Keep one worker: upload serialization and write checks are process-local. |
| Reverse proxy | Existing example needed body/time limits. Buffering may add a full extra temporary request copy on the proxy host. Effective limit is the smallest across every proxy and server. Actual deployment has not been inspected. |
| Hub → Pi | requests-toolbelt streams multipart `file_upload`; no automatic retry. Connect/read timeout `(8, 900)` is not a total transfer deadline. Upload and asset-create/enable are separate operations with ambiguous outcomes after disconnect. |
| Anthias | Inspected REST implementation streams `file_upload.chunks()` into assetdir, but Django may first spool a complete upload to a separate temporary filesystem. Two copies may coexist. Older installed releases may differ, including RAM-heavy reads; current upstream support does not certify an installed Pi. |
| Pi space | `/api/v2/info.free_space` uses `statvfs('/')`, not `statvfs(assetdir)`. Current API `storage` is health information, not an exact media-mount capacity contract. Root free space cannot prove room on a separate media mount. |

Source details: [info measurement](https://github.com/Screenly/Anthias/blob/0edf7917f776005167d26330c970b24dcc9a7959/src/anthias_server/api/views/v2.py#L1285),
[REST staging and chunk handling](https://github.com/Screenly/Anthias/blob/0edf7917f776005167d26330c970b24dcc9a7959/src/anthias_server/api/views/mixins.py#L446),
[Django upload settings](https://github.com/Screenly/Anthias/blob/0edf7917f776005167d26330c970b24dcc9a7959/src/anthias_server/django_project/settings.py#L803).

## Storage policy and operator verification

The Hub continues to subtract rounding uncertainty and a reserve of the greater
of 2 GiB or 20% of reported free space. It now divides the remaining bytes by two
for the single-shot upload's temporary copies. A 1 GiB upload needs at least
4 GiB of conservative measured free space; a hypothetical 4 GiB upload would
need at least 10 GiB (plus reporting-rounding allowance). These numbers do not
certify separate mounts, concurrent external writers or video decoding.

By default a numeric root reading is **not** advertised as verified upload space.
IT can set `ANTHIAS_VERIFIED_STORAGE_URLS` to a comma-separated list of exact
registered player URLs **only after checking inside each Anthias container** that
`/`, configured `assetdir`, and Django's actual temporary upload directory all
refer to the same filesystem. Check `findmnt -T PATH`, `df -B1 PATH` and device IDs
with `stat -c '%d' PATH` for each real path; inspect container bind mounts as well.
Host-root free space alone is insufficient. Reconfirm after mount/container changes.
Restart/recreate the Hub to load the environment. This is an operator attestation,
not an API-proven measurement or a setting Marketing can change.

If paths are on separate filesystems, leave that URL out. Automatic library apply
remains fail-closed. A direct media upload may use the existing explicit per-request
manual confirmation only after a person checks all actual target/temp filesystems.
A reported shortage still blocks **before** that exception is considered, even for
unverified topology. Unknown data never automatically authorizes an upload. The
checkbox is not persistent; requested exceptions continue to be audited.

Hub checks serialize each check/write/flush across threads, and use `f_bavail`
through the real open descriptor. They are not reservations against other
processes. Quota/full-disk failures are reported without blind retry. Ingress,
library copy, ZIP expansion, backup export and restore are covered. Several
concurrent incoming requests may consume the disk down to the floor; one will
then fail with HTTP 507 (bulk processing can report it as an item failure).
Small metadata writes are outside this media guard. The floor is fixed at 1 GiB.

## Controlled recovery

- 413: check both proxy and Hub limits. A new request is needed; no byte resume.
- 507 / known shortage: free or extend the correct storage deliberately, refresh
  measurements, and reselect only missing items. Do not use the unknown-space override.
- Unknown measurement/topology: inspect actual paths, free bytes and pending
  transfers; then explicitly confirm the specific direct upload if appropriate.
- Timeout, disconnect, cancel, invalid response or create/enable failure: wait for
  any server-side transfer to settle; inspect Pi assets **and** staged/orphan files.
  A file can exist without a playlist entry. Check library contents for local
  uploads. Never automatically repeat the whole batch.
- The browser stops its queue after an error and reports unattempted files. A
  multi-file POST without JavaScript or a media ZIP may have partial results;
  consult each result before selecting missing files for a new request.
- No resumable protocol is implemented by Hub. Upstream's newer Content-Range /
  upload-ID support is version-specific; adding it needs capability detection,
  pinned session totals, offset validation, expiry and commit reconciliation.
  Do not treat sending a new POST as resuming an old upload.

## Qualification before a 4 GiB option

1. Pin the actual Anthias version and verify bounded-memory upload code, Pi temp
   and media filesystems, writable permissions, quotas and current free bytes.
2. Propagate a single validated setting through browser, Flask, media, library,
   batch and ZIP64 backup/restore. Keep normal ZIP limits separate. Include
   multipart overhead above the media size; 4 GiB plus ZIP metadata exceeds 4 GiB.
3. Test 1 GiB + 1 byte, 2 GiB, exactly 4 GiB and one byte beyond the configured cap
   against a local streaming receiver first, with bounded RSS and digest checks.
4. Exercise real proxy/Gunicorn/container path, slow input/output, concurrency,
   near-full temp and media disks, quotas, disconnect during both hops, duplicate
   retry and asset-commit failure. Verify request cleanup and orphan reconciliation.
5. Only then run a separately approved staged Pi acceptance test, growing sizes
   gradually and measuring space/RSS/playback. No untested 4 GiB Pi load.

## Deployment with the pull timer

The existing timer is `anthias-hub-cd.timer` / `anthias-hub-cd.service`. It pulls
`:latest` after main CI publishes; it does not pull Git source. A merge can therefore
be picked up by an already enabled timer without a manual deployment. This audit
makes no direct host changes.

On the operator's host, inspect the unit to find its real checkout:

```bash
systemctl show anthias-hub-cd.service -p WorkingDirectory -p ExecStart
systemctl status anthias-hub-cd.timer --no-pager
systemctl list-timers anthias-hub-cd.timer
```

Before adopting this stricter policy, pause the timer if a controlled maintenance
window is needed; let an already-running service finish. Check and record player
storage topology, then edit the existing private `.env` entry without duplicates.
Do not invent confirmations merely to restore a green capacity badge.

After main **test and publish** jobs succeed, from the existing clean checkout:

```bash
git pull --ff-only
sudo systemctl reset-failed anthias-hub-cd.service
sudo systemctl start anthias-hub-cd.service
sudo journalctl -u anthias-hub-cd.service -n 40 --no-pager
curl -fsS http://127.0.0.1:8765/healthz
sudo systemctl start anthias-hub-cd.timer
```

Expect `updated` or `unchanged`. An environment-only change does not change the
image ID and the timer may report `unchanged`: in that case a manual container
recreation with **the existing `compose.cd.yaml` plus the exact current override**
is necessary to apply `.env`. Preserve project name `anthias-hub`, ports and volumes;
see [auto-deploy](auto-deploy.md) and [network access](network-access.md).
Validate login, storage unknown/confirmed/full states and one small upload. Healthz
alone does not validate upload safety or TV playback. Retain the prior SHA image
for rollback; do not silently discard the new storage protections to clear an error.

## Validation evidence

Fast suite: 190 Python tests and 30 Node UI tests passed locally. Regression cases
cover unknown/unverified topology, exact URL attestation, known shortage even
with override, two-copy budgeting, decimal-comma rounding, quota/ENOSPC,
unknown Hub disk measurement, multipart cleanup, HTTP 507, failed library staging,
backup restore cleanup and export/restore size consistency.

A separate localhost HTTP experiment transferred exactly 1,073,741,824 bytes into
the real Flask library route, verified the stored digest, exported/restored the
backup, then streamed 1,073,742,000 multipart bytes to a local mock Pi. It uses a
sparse synthetic MP4-signature file, so it exercises byte transport and checksums,
not decoding/playback. Run `PYTHONPATH=. python tests/manual_large_upload.py` from
the checkout with dependencies installed and at least 5 GiB available disk space.
It explicitly sets its temporary directory to its disk working directory; no
remote player address is used. With disk-backed temp storage, the local run took
11.17 seconds and peaked at 75.60 MiB RSS (same peak before and after transfer).
This is intentionally outside the fast CI suite.


## Speicheranzeige: gültiger API-Wert, aber keine Uploadfreigabe

Wenn beide Geräte als „Speicher nicht verfügbar“ erscheinen, liegt das häufig **nicht** an der Anthias-API: `/api/v2/info.free_space` meldet den **System-Root** (`statvfs('/')`). Hub zeigt mit der aktualisierten Diagnose diesen Systemwert an, erkennt ihn aber **nicht automatisch** als Medienkapazität an. Ohne eine IT-bestätigte Dateisystem-Zuordnung `ANTHIAS_VERIFIED_STORAGE_URLS` bleibt `usable_bytes=0` und die automatische Upload-Freigabe aus. Die Anzeige trennt nun „Root gemessen, Medien-Mount nicht bestätigt“ von „API nicht erreichbar/kein free_space“. Die echte Upload-Sperre und der explizite Unknown-Only-Override bleiben unverändert.

**Je Pi einmalig vor IT-Freigabe:** auf dem tatsächlichen Anthias-Host bzw. im Container prüfen, dass das Dateisystem von `/`, dem über Anthias konfigurierten `assetdir` und dem Django-Upload-Temporärverzeichnis identisch ist. Tatsächliche Pfade ermitteln, nicht raten, und `df -B1`, `findmnt -T`, `stat -c '%d'` für alle drei ausführen. Bei unterschiedlichen Dateisystemen **nicht** attestieren; die Root-Messung beweist keinen Medien-Freiraum. Sind alle drei identisch, die exakt im Hub registrierten Geräte-URLs kommagetrennt in der privaten Hub-`.env` als `ANTHIAS_VERIFIED_STORAGE_URLS` eintragen und den bestehenden Compose-Stack mit seinem LAN-Override kontrolliert neu erstellen. **Ein systemd-Timerlauf mit unveränderter Image-ID lädt geänderte .env nicht neu.** Bei unbekanntem Speicher kann Marketing nach separater Kontrolle weiterhin die vorhandene manuelle Bestätigung für einzelne Uploads verwenden; nachgewiesener Platzmangel bleibt gesperrt.
