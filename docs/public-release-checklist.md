# Community publication checklist

This public repository is still a pilot. Before actively promoting a release:

- [ ] Inspect **tracked files, old Git commits, tags, releases and Actions artifacts** for secrets and internal details. Latest-tree cleanup does **not** erase Git history. Revoke/rotate any exposed secret before discussing history rewriting.
- [ ] Confirm the author owns the rights to license the project. Keep MIT and upstream credits; do not imply official Anthias/Screenly endorsement.
- [ ] Verify a fresh solo `--solo` install and existing team-account upgrade and session behavior.
- [ ] Exercise role boundaries with unauthorized POST attempts, CSRF and media tests.
- [ ] Test the exact Anthias version and physical display for writes, upload/delete, HDMI/CEC and recovery.
- [ ] Check DNS, HTTPS secure cookies, ACLs, backup/restore and optional Compose override after update/rollback.
- [ ] Prepare screenshots using **generated demonstration records**, not a company workstation or real device inventory.
- [ ] Produce first manually approved Git tag and immutable image reference (digest); current CI has no stable channel.
- [ ] Add clearly scoped Issues templates / contribution guidance and invite feedback after pilot approval.

Use [pilot-acceptance.md](pilot-acceptance.md) for real-device checks and [SECURITY.md](../SECURITY.md) for the operational security model.
