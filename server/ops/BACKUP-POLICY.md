# Backup policy source

This source matches the previously deployed inventory205 and safeguard207, not a new live policy change.
The off-site uploader verifies new copies, writes private receipts, and reports capacity without remote pruning.
Removing older remote recovery sets needs a complete reviewed recovery catalog and explicit owner approval.

Provider hashes alone are not proof of original upload correctness, archive recoverability or full/differential
relationships. Historical copies without receipts remain protected until separately verified. Capacity may
exceed the reminder threshold while removal waits for approval. Never restore the old per-file cap-pruning code.

Run audit_backup_inventory.py for aggregate read-only coverage. Private receipts and member lists stay outside
the public repository. Account/profile/quarantine recovery copies need separate reviewed handling; moving data
into a protected backup is not final erasure. Routine log/support expiry is independent of backup approval.
