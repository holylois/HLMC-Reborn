# Entity residency guard 1.0.0 for Minecraft 26.3

Server-only Fabric repair for entity sections that stay TRACKED after their terrain
holders disappear. Recheck on the server thread after 200 ticks, then ask the native
entity manager to hide, save and unload the section. Never discard entities directly.

Limits: 64 records inspected and four reconciled per dimension per tick, with a 1 ms
scan budget. Skip active, visible and pending-unload holders. Disable reconciliation
for a dimension if its visibility inventory exceeds 200,000 records.

The four production Java sources and two JSON descriptors match the tested jar.
`NativeResidencyTest.java` and `NativeUnloadProbe.java` are generated-world test
entrypoints only. Never include them or their classes in the production jar.
Compile against Minecraft 26.3, Java 25, Fabric Loader 0.19.5 and the matching Fabric
API/Mixin dependencies. Runtime accessors are required and fail fast on incompatibility.

The pinned production artifact SHA-256 is
`4db717ebacfc451115a6f5ede8dacfa6e31165ad39b504cea219c503459e85a4`.
Do not rebuild or replace those verified deployment bytes casually.

Verification receipts contain aggregate results only. Native save/reload preserved
UUIDs, names and equipment; resident chunks and pending unloads stayed protected.
Three equal 441-chunk generation workloads observed for 2,400 ticks left 442 orphaned
records without the guard and zero with it. Disabling the ModernFix chunk release
flag alone also left 442 records. The original notification producer is unconfirmed.

No client pack, launcher, spawning rules, terrain format or player data transformation.
Deploy only with explicit owner approval, the established countdown, a full verified
stopped-server backup and rollback. Keep raw reports, worlds and account data private.

Deployment on 15 October 2026 (Riga) verified the entire 19.7 GiB stopped-server
backup by tar comparison and SHA-256 before installing the pinned artifact.
Startup and claims readiness passed, with timers and the terrain hold preserved.
The first attempt aborted before installation because the periodic botwall snapshot
changed during comparison. Its timer and service were paused for the successful retry
and its prior timer state restored afterward. Both archives remain private.

A restart left the terrain controller's running marker stale while Chunky had no
active task. The owned checkpoint was preserved, absence of running tasks confirmed,
and the marker reconciled to paused. Generation stays guarded while players are online.

The post-deployment native sample with one player online recorded 399 entities,
zero without terrain holders, and 33.1 ms average tick time (50 ms target budget).
This is a short live sample, not a guarantee against every future source of lag.
Pregeneration remained paused with a player online. Raw native reports remain private.

## 1.1.0: Runeforged attribute throttle

Runeforged 0.2.4 recomputes every player's weapon/armor attribute modifiers at the end of each player tick
(`ArpgPlayerAttributeService.apply`). With multi-affix gear this re-decodes item data for every stat and was the largest
single server cost in the 2026-10-15 spark profile (16.9% of the server thread with one player).

`AttributeThrottle` (server players only, clients unchanged) skips that recompute while its inputs are unchanged: the
held weapon, the four armor slots (component identity) and active effects. It recomputes on any change, after any
`applyWeapon` outside the regular pass (off-hand attacks), and at least every 20 ticks. The mixin config is optional,
so a server without Runeforged still starts; a changed Runeforged signature fails loudly at startup.

`NativeThrottleTest` (fixture jar only) checks with real stat affixes: 5 recomputes per 100 unchanged ticks, and exact
Runeforged values after chest/weapon swaps, removed boots, in-place durability change, Slowness, Health Boost and an
off-hand weapon apply. `throttle-native-receipt.json` pins the tested jar.
