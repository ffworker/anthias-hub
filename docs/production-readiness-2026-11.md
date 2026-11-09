# Release gate: Hub host to site display (November 2026)

**Prepared 2026-11-09. This is a plan, NOT production approval.**

Candidate: `ffworker/anthias-hub` main commit `0473444764d827546675243b266c7c97b49ce46b` (merged PR #59).
CI evidence: [main Tests & Publish success](https://github.com/ffworker/anthias-hub/actions/runs/42402077615).
Candidate image: `ghcr.io/ffworker/anthias-hub:sha-0473444764d827546675243b266c7c97b49ce46b`.
**Confirm its actual availability and OCI digest before a release.** A Git commit SHA is not an OCI digest. No assumption is made that Hub host runs this image or that site display is already migrated.

## Operating principles

- First inventory, then protected off-host backup, restore rehearsal, isolated test Pi, approved site display change window, and only then expansion to other screens.
- Keep the existing live Compose override, Caddy access, Pi media and the independently deployed RSS2Slideshow application intact.
- `FOLDER_AUTO_PUBLISH=0` is required during early acceptance. Enabling that global worker flag while existing templates have `auto_devices` mappings can write to **every mapped Pi**. Use a separate, explicitly scoped test setup or prove the only destination is the spare Pi.
- Never treat registered UNC as an existing CIFS mount, HTTP /healthz as actual TV playback, or Hub template ZIP as a full Hub+Pi backup.
- Avoid putting hostnames, addresses, account values, paths to company shares, screenshots or secret-bearing command output into this public repository or public issues. Keep acceptance evidence in approved internal storage.

## Gate 0 — read-only Hub host baseline

From the existing checkout on the **Docker host**, as an authorized operator (not from a Pi):

~~~bash
cd ~/apps/anthias-hub
bash -n scripts/preflight-readonly.sh
bash scripts/preflight-readonly.sh
~~~

The preflight only reads local files, service status, a localhost health endpoint, Docker state and mount metadata; it does not deploy, mount, back up, reboot, enable a publisher or connect to a Pi. Record the running image **ID/digest**, release SHA, whether the update timer is enabled, and the original external Compose override privately. Check container port bindings, Caddy HTTPS and actual login separately. Inspect the real legacy mount list and imported template bindings before replacing any source.

**No-go:** missing/unreadable override, unexpected publisher value, unknown release, stale host verification, mismatched media mappings or unknown current site display boot state.

## Gate 1 — demonstrate recoverability before touching production

- Consistent confidential off-host backup of Hub `.env`, `config/`, `data/` (including library, schedules and folder-publication journals); preserve existing external Compose override and separate Caddy CA/PKI.
- Separate Pi backup of local playlists, media, schedules and boot medium. Do not overwrite a known-good SD.
- Rehearse Hub restore into an isolated disposable environment: verify credentials/roles, device inventory, templates with representative media hashes, schedules and health.
- Rehearse spare Pi restore and real HDMI playback. Prepare an exact image/digest and Compose rollback route. **An image rollback does not undo writes already made to the Pi.**

**Go:** Independently verified Hub and Pi restore, dated evidence, operator acknowledgement.

## Gate 2 — consolidate the single read-only SMB parent

- Keep existing source mounts until migration is proven. Verify `/srv/anthias-sources/default` is a real, read-only CIFS mount; check root-only allowlist and credentials *permissions*, without exposing values.
- Confirm matching fresh host mount verification and read-only `/sources/default` visibility in **both** web and import worker containers (including required `rslave` propagation).
- Compare direct subfolder names and representative media hashes with expected files. Previously observed test media counts were provisional and must be verified afresh.
- Inventory `folder_source`, image durations, item IDs/order, RSS URL items and `auto_devices` in each existing template. Do not force-rebind a template with already imported media from old alias to `default/<folder>`. Use a test template and migrate mappings explicitly.
- Retire unused legacy aliases one by one **after** confirming no active bindings. UI removal does not unmount old CIFS host mounts; host cleanup needs a separate controlled maintenance action. No deletions of SMB source files.

**Go:** Verified default parent + direct folders and media; no existing Pi changed.

## Gate 3 — import-only worker and access controls

- Check running worker `FOLDER_AUTO_PUBLISH=0`, `FOLDER_REQUIRE_MOUNT=1` and `FOLDER_REQUIRE_VERIFIED=1`. Observe heartbeat, logs, repeated scans and restart.
- On an isolated test source: add/replace an image/video and confirm unchanged display duration and playlist order in the Hub template; test SMB outage without losing cached media. File deletion from SMB is intentionally **not** an automatic Pi deletion.
- Test Owner/IT/Marketing/Viewer permissions. From a real Marketing workstation, confirm Hub HTTPS works and direct Pi management/API access is blocked; Hub-to-Pi management must be permitted.
- Confirm no automatic or unintended writes reached a production player.

**Go:** Importer, role boundary and client network isolation observed; production Pi content untouched.

## Gate 4 — spare Anthias Pi + physical monitor

- Record supported OS, Anthias version, IP/DHCP reservation, original spare boot medium and native Pi playlist/schedule.
- Verify spare Pi REST API, a website from RSS2Slideshow **reachable from the Pi**, images, MP4, duration, order, pause/resume and native schedule on the *physical monitor*.
- In an isolated test configuration and only for this spare Pi, enable controlled publishing: test new/replaced media, two unchanged sync cycles (no active duplicates), no accidental global reorder on a mixed/manual playlist, player reboot and Hub-unavailable playback.
- Simulate one recoverable mid-transfer interruption and an SMB outage. Review actual player state before any manual retry; transfers may be partial.
- Test expected HDMI control only where the device supports it and has a safe recovery method.

**Go:** Signed real-screen pass with backup and proven Pi rollback. **No-go:** API or preview-only success.

## Gate 5 — deliberate site display cutover

- **First verify reality**: previous Raspberry Slideshow vs Anthias, current media/SD boot, networking, TV and operating schedule. No presumption that the requested migration has already happened.
- Preserve the working SD untouched; stage another verified Anthias medium with an approved IP/DHCP reservation and documented recovery. Keep RSS2Slideshow running independently.
- In a dedicated, operator-approved maintenance window: register and test the site display player; bind its intended single-root folder template plus the RSS website, check image order/durations, schedule, reboot persistence and *actual HDMI/TV output*.
- On an unacceptable result, restore the old boot medium and verify the previous TV output. Old mounts remain until stable new site display content has been accepted.

**Go:** IT and Marketing confirm actual site display image, operations and recovery. Integrate other screens separately.

## Gate 6 — pinned production, hardening, handover

- Use the **same already-tested image** pinned to verified digest (or SHA image tag) with `compose.cd.yaml` **plus the preexisting external override**; keep rollback reference. Disable test-only `anthias-hub-cd.timer` on a production-pinned deployment. Never use plain `docker compose up -d --build`.
- Check loopback port 8765, Caddy HTTPS and trust chain, secure cookies, access isolation, mount service, worker heartbeat and physical playback after promotion. Document monitoring, credentials/backup owners and restore instructions.
- Observe operations through at least a planned initial stability window; document any errors, retry procedures, on-call owner and an approved escalation path.
- Repository hygiene before public signoff: review **full Git history, binaries/PDF metadata and artifacts** beyond the HEAD-only tracked-text scanner. `main` currently is not protected; configure required checks/review policy if desired. Do not claim privacy clearance solely because CI passed.

## Private operator sign-off

| Gate | Status | Private evidence location | Reviewer / date |
| --- | --- | --- | --- |
| 0 Hub host baseline | Pending | | |
| 1 Hub + Pi restores | Pending | | |
| 2 Single SMB root | Pending | | |
| 3 Import-only worker | Pending | | |
| 4 Spare Pi + monitor | Pending | | |
| 5 site display cutover + rollback | Pending | | |
| 6 Pinned release and handover | Pending | | |

**Stop immediately if** any backup/recovery is unverified, the importer is unintentionally publishing, a default source is not host-verified, private management endpoints are publicly reachable, Pi writes occur unexpectedly, or the old site display boot medium is unavailable.

See [single-root SMB setup](single-root-smb-setup.md), [company folder workflow](company-folder-workflow.md), [pilot acceptance](pilot-acceptance.md), [IT admin/backup guide](IT_ADMIN_GUIDE.md), [player onboarding](player-onboarding.md), [controlled release guide](reproducible-production.md) and [public repo hygiene](public-repo-hygiene.md).
