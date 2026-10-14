# Structure density balance

Deployed on 14 October 2026 after the 2.0.2 client patch, following isolated tests and a full compared backup. This is a server-only quiet balance change, with no new client pack, launcher executable, public announcement or MOTD change.

The configuration keeps the global Sparse Structures factor at 1 and the original salts. Explicit per-set rules widen 197 of the 269 actual loaded sets:

- 47 dense Moog's Voyager sets use a factor of 2, roughly 75% fewer candidate positions.
- 150 other additions use a factor of 1.5, roughly 53-57% fewer candidate positions after integer rounding.
- Already rare sets, vanilla progression, stronghold rings, fishing structures and the separately tuned village sets keep their existing placement. The vanilla-mineshaft replacement remains in effect.

These are reductions in candidate positions, not a promise of a fixed distance between structures from different sets. Biome eligibility and each mod's generation rules still apply. Only new chunks change; existing generated structures remain. Do not regenerate/delete terrain or raise RTP early. Install and verify this configuration before resuming the existing guarded pregeneration task.

Sparse Structures also matches member structure IDs, so selector order is deliberate. Do not alphabetically sort the JSON entries: a shared member could otherwise pick up a different set's factor. Moog's own library rounds its multiplier after Sparse Structures; the comparison accounts for that rounding.

An isolated baseline and final candidate boot each loaded 269 sets. The runtime comparison verified all 197 intended changes, identical other registry data and a successful locate of a modified MVS structure. The private probe is test-only and must never be installed on production.

The separate deployment helper accepts only `--check` or `--deploy`. Run it from the prepared private directory with the exact tested config and test receipt. Its read-only preflight checks candidate/live hashes, zero online players and backup capacity. Actual deployment requires owner approval, a full compared backup, a healthy restart and automatic rollback on failure. Keep the existing public release news and client pack unchanged.
