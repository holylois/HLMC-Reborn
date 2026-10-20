# Backup policy source

This source matches inventory205, safeguard207 and the silent safeguards223 deployment on 20 October 2026.
The off-site uploader verifies new copies, writes private receipts, and reports capacity without remote pruning.
Removing older remote recovery sets needs a complete reviewed recovery catalog and explicit owner approval.

Provider hashes alone are not proof of original upload correctness, archive recoverability or full/differential
relationships. Historical copies without receipts remain protected until separately verified. Capacity may
exceed the reminder threshold while removal waits for approval. Never restore the old per-file cap-pruning code.

Run audit_backup_inventory.py for aggregate read-only coverage. Private receipts and member lists stay outside
the public repository. Account/profile/quarantine recovery copies need separate reviewed handling; moving data
into a protected backup is not final erasure. Routine log/support expiry is independent of backup approval.

Recovery safeguards are deployed: native world selection uses backup IDs, stream and creation time.
The drill requires original upload receipts and reconstructs the final snapshot, including file removals.
A passing world drill proves world recovery only. It does not prove account/config/economy consistency.

World-scope deployments now require an explicit data_migration boolean, verified stopped writers, a compared
whole-server archive and recovery-set.json. Root files changed by a plan are included in rollback, and newly
created trees are quarantined on failure. A failed rollback boot keeps maintenance and background jobs paused.
The complete stopped archive preserves account database sidecars alongside the world, permissions, economy,
configuration and software. BlueMap tiles and recursive backups are excluded. Off-site verification and a restore
boot remain separate evidence. A recovery-set receipt never grants expiry/deletion approval.

Routine live server/config archives are supplementary copies, not consistent recovery points paired with JEB.
Their receipts explicitly say application_consistent=false. This batch does not introduce automatic shutdowns
or claim that historical copies have been upgraded. A scheduled stopped recovery window needs owner approval.

Local maintenance offload now requires a recognized successful deployment receipt for every folder name, not
only folders beginning with release. Held, unfinished and unrecognized historical folders stay on the VM for
review. This may retain more local evidence; it does not authorize remote cleanup. Backup failure diagnostics
go only to the private staff alert destination, with no fallback to public server-status.

The first safeguards223 stopped recovery archive passed full off-site verification and isolated restoration on
20 October 2026. Its 23,179,407,360-byte Drive stream matched the original SHA-256 and provider MD5; companion
objects matched original hashes. Independent disk checks verified all 5,901 files. The exact archived server
software booted, loaded datapacks, saved and stopped cleanly. No production restart or real account login/query
was part of that proof. Original and restored evidence remain held; this does not validate every historical JEB
chain, a whole host restore, or future erasure adapters. It grants no cleanup approval.

Guard224 adds the deployed external privacy/start barrier, described in RECOVERY-GUARD.md. It does not perform
erasure. Its external ledger/key need independent recovery protection before any real
erasure is allowed. The earlier Minecraft-root recovery set cannot supply those newly external files.
