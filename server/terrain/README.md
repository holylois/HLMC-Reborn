# Terrain expansion job

Pregenerates the whole Overworld inside the world border (20,000 wide, so a radius-10,000 square around 0,0) with Chunky 1.5.3, then raises `/rtp` and first-join placement to 5,000 blocks.

- `expand-terrain.py` runs one short step per timer tick. It generates only while no players are online and at least 6 GiB of disk space is free. The timer checks every 15 seconds and requests a pause when players are online.
- RTP changes only after Chunky reports natural completion of the job's own task **and** all 1,565,001 chunks in the square are stored with matching coordinates and `Status=full`. MCA files or headers alone are never treated as proof.
- Any unexpected state blocks the job and disables its timer. It never trims or deletes terrain.
- `test-expand-terrain.py` holds 28 synthetic tests. It never touches a real server.

## Install (server stopped)

1. Archive any existing `config/chunky/tasks/minecraft/overworld.properties` and old `/opt/minecraft-backups/terrain-expansion/job.json`.
2. Copy `expand-terrain.py` to `/usr/local/lib/holylois/` and the `.service`/`.timer` units to `/etc/systemd/system/`.
3. Start Minecraft, then `systemctl daemon-reload` and `systemctl enable --now holylois-terrain-expansion.timer`.

Check progress with `sudo journalctl -u holylois-terrain-expansion -n 20 --no-pager` and `sudo cat /opt/minecraft-backups/terrain-expansion/job.json`.

## Slices and lag guard (since 1.7.10)

The 2026-10-05 watchdog crash came after minutes of growing "ticks behind" while Chunky ran. The candidate runs in slices of 45 minutes and
rests 2 minutes between them, and a "Can't keep up ... N ticks behind" warning of 100 or more in the last three minutes pauses it for 10 minutes
(`LAG_TICKS`, `RUN_SECONDS`, `REST_SECONDS`, `LAG_REST_SECONDS` in `expand-terrain.py`). `server.properties` also gets `max-tick-time=120000` so a long
chunk burst is not mistaken for a hang.

Release procedure: install and verify the approved structure set before releasing the owner hold. Resume the existing
selection and confirm player pauses. Active checks read the saved task without repeatedly pausing/restarting Chunky;
the work-slice start time is preserved until an actual pause/resume. Do not regenerate existing chunks or raise RTP early.
The new schedule increases theoretical working time from 60% to about 96%; actual chunks/hour depends on CPU, worldgen and lag.
BlueMap retains one render worker and its existing empty-server guard. Do not raise worker counts blindly on a two-core
host. Measure actual chunk throughput and tick lag before increasing concurrency.
