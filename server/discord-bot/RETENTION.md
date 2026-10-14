# Routine retention

The bot uses a root-private retention-policy.json in its state directory. Use policy.example.json as the
schema, with the actual private support channel ID. Defaults are disabled. Never commit the live policy,
registry, Discord credentials or audit receipts. Policy must be root-owned0600; audit directory0700.

- Closed Minecraft archives only: older than90days by conservative file date and modification time.
  latest.log, unknown names, links and reviewed holds are excluded. Daily timer; downtime delays expiry.
- Tracked routine support roots and linked replies:180days after BOTH resolution and latest activity.
  Reports and legacy requests start held. Startup/disconnect holds existing requests against missed events.
  Staff Hold/Release hold remains available after Solved. Release explicitly classifies a request as routine.
- Fresh replies/edits/holds invalidate the plan. Discord404 only means absent; permission/network failures
  stop cleanup. Root authorship, exact channel and tracked references are checked. No channel-wide purge.
- Durable opaque intent/completion receipts support interrupted runs. Metadata is forgotten only after all
  tracked messages are absent. Provider-held copies or attachment caches are outside this executor.
- No automatic account, backup, shared-world or public-chat deletion. Backup removal needs separate exact
  approval and verified complete recovery sets. Full account erasure/restore suppression remains separate.

Run synthetic tests from this directory: python3 -m unittest discover -p 'test_*.py' -v
Use only a synthetic fixture or a read-only aggregate inventory for preflight. Deployment requires explicit
owner approval, a verified backup of the affected bot service and registry, rollback and live health checks.
Install all five runtime modules together. The daily log units live in ../ops/units. Do not enable either
scope until the policy's private channel and held archive names have been reviewed.
