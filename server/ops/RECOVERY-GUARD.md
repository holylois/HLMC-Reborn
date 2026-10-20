# Restore privacy barrier

Candidate 224, not deployed yet. This is a conservative start/restore barrier, not an account-erasure executor.
The owner confirmed on 20 October 2026 that no player-data erasure request has been completed. Free-play character
quarantine is a recoverable move, not erasure and not a reason to invent a deletion record.

## Behavior

The systemd pre-start hook runs `recovery_guard.py start` as root before the Minecraft user can start Java.
Private state and its HMAC key live outside the Minecraft backup root in /var/lib/holylois/recovery-guard, mode 700;
files are mode 600. Request records contain a random request ID, a keyed UUID digest and a timestamp, not names,
raw UUIDs, credentials or message content. This is still private pseudonymous metadata, not anonymous public data.

A matching generation marker in config changes on each start. Missing/old markers, missing/corrupt private state,
an interrupted two-file transaction or a pending restore all refuse startup. Initialization never replaces existing
state or creates an empty ledger for a root that already contains a generation marker.

The deploy kit arms an external pending-restore barrier before rollback extraction. Only successful extraction
can release it, and only when the request ledger is empty. A failed extraction leaves startup blocked. The outside
ledger is never taken from the restored archive. Every recorded request blocks both startup and new restores;
there is no clear-request command, supplied-receipt shortcut, automatic erasure or silent override.

## Limits and operator workflow

- Normal restarts with an empty ledger remain automatic. A recorded request intentionally requires a separately
  reviewed per-store workflow before startup can resume. Do not record test requests in production.
- Before any real erasure, implement and verify the real auth, aliases, inventories, claims/party, economy,
  permission, journal/discovery, cache/export, support and relevant embedded-world adapters. Export an independently
  protected off-site recovery copy of the latest external ledger/key and prove its restore before erasure.
  The older Minecraft-root backup does not include this newly external state. No erasure/expiry is authorized here.
- Privileged operators must arm the barrier before every production restore, including a partial/world-only copy.
  The supported deploy rollback does this automatically. A manual copy that bypasses the restore tool can bypass
  detection when it leaves the marker unchanged, including a copy from the same generation. A marker is not a
  complete per-store content inventory or protection against a privileged operator disabling the guard.
- For a manual recovery, with the game and known data writers stopped, run
  `sudo python3 /usr/local/lib/holylois/recovery_guard.py begin-restore --id RANDOM_CANONICAL_UUID` before extraction.
  Completion requires a reviewed trusted restore caller; no general release-barrier CLI is exposed. Never clear
  the ledger/pending state or substitute an old ledger just to make the server boot.
- An approved real request would be recorded while writers are stopped with `record-request --id REQUEST_UUID
  --subject SUBJECT_UUID`. It does not erase data or claim the request is completed. Stop before this step until
  the per-store workflow and external-state backup described above are ready and explicitly approved.
- Interrupted generation writes retain transaction.json. Keep the server off and review both state/anchor copies;
  do not guess which half is current, remove the barrier, or reinitialize. Missing external state after a host loss
  needs independent ledger/key recovery; a successful old world boot is insufficient evidence.

## Deployment and rollback

The private reviewed installer uses the established hl-deploy.py with a mods/config backup, zero-player restart,
original whitelist/timer preservation and automatic rollback. It installs only the guard and deploy helper, one
systemd pre-start drop-in and local metadata. No gameplay mod, signed pack or player database changes.

The first empty-ledger deployment can restore previous operations files/drop-in if normal rollback succeeds and
there are still no requests. Its private evidence is kept. Any unresolved privacy transaction/restore failure
keeps maintenance and background jobs paused for review. A failed rollout is not a deployed privacy guarantee.

The owner must explicitly approve deployment. This file and tests do not change the live server by themselves.
