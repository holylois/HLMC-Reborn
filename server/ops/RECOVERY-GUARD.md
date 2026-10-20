# Restore privacy barrier

Guard 224 is deployed as a silent operations update on 20 October 2026. This is a conservative start/restore
barrier, not an account-erasure executor.
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

The owner explicitly approved this deployment. Installed source hashes, the systemd hook, private file permissions,
the zero-request ledger/anchor pair and original whitelist/timers were verified after the empty-server restart.
New deployments still require explicit approval; this file and tests do not change services by themselves.

## External checkpoint helper

`guard_snapshot.py` creates a bounded private archive of the ledger and subject key while holding the guard
lock. It requires a valid current anchor and no pending restore. It writes a new private directory outside the
server and guard roots, with an independent original receipt. Existing evidence is never overwritten.

The verification action checks the archive against that trusted original receipt, allows exactly the expected
regular files, rereads recovered disk bytes and validates the recovered state/key in a new private directory.
It cannot replace live state, start Minecraft, clear requests or release a barrier. It has no upload, pruning,
service or automatic restore behavior. The root operator must choose private unlinked paths with protected parents.

Example operator commands, using the reviewed source beside the matching `recovery_guard.py`:

```
sudo python3 guard_snapshot.py snapshot --output NEW_PRIVATE_CHECKPOINT_DIR
sudo python3 guard_snapshot.py verify --archive CHECKPOINT_DIR/guard-state.tar --receipt TRUSTED_ORIGINAL_RECEIPT --output NEW_PRIVATE_PROOF_DIR
```

Keep the original receipt independently protected. A digest supplied only by an archive/download is insufficient.
An old snapshot can pass byte verification while being unsafe to substitute for a later ledger. The helper grants
no freshness or production replacement authority. Preserve newer requests and every incomplete-transaction marker.
Take a new reviewed checkpoint after ledger/generation changes; a one-time proof is not a scheduled backup service.
Missing latest state still requires operator review. Do not initialize an empty ledger to recover from key loss.

Fixture checks cover nonempty requests, old-copy recovery preserving new live requests/barriers, exact private
disk recovery, corruption, unsafe paths/types/permissions, duplicate/incomplete archives and lock contention.

## Scheduled checkpoints

`guard_checkpoint.py` and its three systemd units were deployed on 20 October after the owner explicitly approved
the unit-only service, future automatic private ledger/key uploads and private failure notices. The first real
current-state upload/readback passed before timer enablement. Installed hashes, the fresh pair and timer state
were verified; Minecraft kept its process with zero automatic restarts. The earlier one-time checkpoint approval
alone did not authorize this timer. Committing source or running fixtures does not enable a service.

The job checks every 15 minutes, creates a private set when the ledger/key pair changes, and rechecks
unchanged remote copies against local originals. Each immutable archive and companion receipt receives provider
hash checks and bounded actual readback. Complete interrupted uploads can resume. Incomplete local evidence is
retained for review. A current-state change during preparation/upload refuses to update the latest-proof index.

The service has read-only access to the live ledger/key, write access to the existing lock, its own private state
directory and the existing root-only provider configuration directory for token refresh. Minecraft is not restarted
by a unit-only rollout. The job has no account adapters, prune, reset, ledger replacement or barrier-release action.
Resource limits: CPU 20%, memory 256 MB, ten-minute service timeout and low I/O priority. Failure notices
use only the existing private staff operation, limited to one alert start per hour, with no public fallback.

A private latest.json index is evidence of one successful check, not an erasure permit. Future erasure workflows
must synchronously verify that the exact current ledger/key pair has current independent off-site protection.
Never choose an older valid ledger to make a server start. Keep all earlier checkpoints and unresolved evidence.

## Prepared per-store review228

Prepared source only, not installed. The scheduled227 service and guard224 keep their existing deployed bytes.
`guard_checkpoint.py --verify-current` adds synchronous verification of an existing exact-current checkpoint:
it checks the current ledger/key fingerprint, independent local archive receipt, provider hashes and bounded
readback. It performs no upload, snapshot creation, latest-index refresh or state replacement. An old timer
success cannot stand in for this check. Missing evidence or a concurrent request/change refuses completion.

`privacy_review.py` is an offline library with no default account paths or service control. A trusted operator
workflow supplies the private identity cases, complete native store registry, stopped-writer lease and current
source/inventory verifier. Every HMAC ledger request must have exactly one matching case. The identity review
must explicitly list all linked online/offline/forced and case-variant UUIDs plus reviewed aliases; lowercase
aliases alone cannot reconstruct case-sensitive free-play UUIDs. A proof digest references that separate review,
it does not discover accounts or prove that an operator's identity inventory is complete.

Every linked identity is checked across all ten store groups twice. A changed store fingerprint, source review,
writer state, guard pair, missing case or unresolved store blocks the review. Only aggregate counts are returned.
Even a successful review has `allow_start=false` and `erasure_authorized=false`. The existing guard still blocks
all recorded requests. There is no erase, clear-request, production restore-completion or barrier-release API.

Generated tests exercise this library with native-shaped SQLite/JSON/NBT/Anvil records, recovery tokens,
shared records, exports and Discord fixture history. They prove detection/review behavior, not a completed real
account erasure. The older215 SQLite-ledger pilot must never replace the deployed pseudonymous guard.
Before any activation or erasure: finish current native bindings and ownership/hold decisions, adapt export
suppression to the current guard/cases, prove the complete flow on an isolated generated account, then obtain
separate deploy approval and exact account-action approval. No real deletion or new data upload is authorized.

## Prepared exporter suppression229

Not deployed. `privacy_exports.py` replaces the old pilot's SQLite-ledger dependency for public export policy.
The private policy is bound to reviewed cases/linked identities and the current HMAC request inventory. Activation
requires exact policy approval, stopped writers and synchronous exact-current checkpoint readback. It grants no
erasure, startup or restore-completion permission. All existing request barriers remain.

The production Guard binding closes an operator-owned serving gate before adding a request or arming a restore.
Failure/interruption keeps serving closed. The HTTP service checks the gate epoch and exact output hashes;
old/corrupt or incomplete output returns503. Current stats/recap code applies UUID and alias suppression, including
renamed records and legacy names linked through the identity cache. Weekly snapshots use atomic private writes.
Name checks return unknown for withheld names, rather than claiming an account name is available before review.

The HTTP DynamicUser needs only identity-free gate/control metadata and its existing output cache. It never reads
the HMAC key, private case/policy files or accounts. No-store responses prevent new cached successes. Copies
already delivered to browsers/CDNs or Discord still require the separate expiry/purge/history workflow.

Ship all eight matching guard/snapshot/checkpoint/review/policy/exporter modules as one sealed, rehearsed update,
with gate/policy initialization and exact-current off-site proof. A single exporter copy without its dependencies
must not be deployed. Live224/227 bytes and services are unchanged. Generated tests cover current exporter code,
restored records, unrelated-account preservation, interruption and actual loopback HTTP; they are not a native
Minecraft account-erasure proof. Current store bindings, exact reversible plans and native rehearsal remain.
