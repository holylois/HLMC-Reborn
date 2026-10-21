# Holy Lois: Reborn - easy owner guide

Release builds use a frozen release profile and the current tested publishing scripts. The owner's CurseForge play profile can lag behind live and is not the release source. Friends use the normal Holy Lois app to install updates. The older Admin-app walkthrough below is historical; follow the current operator runbook and release checklist for publishing.

Launcher 1.6.2 updates itself through the signed app channel. Players do not rerun the installer for each launcher release. First setup offers a launcher choice and optional Desktop and Start menu shortcuts. Deleted shortcuts stay deleted, and existing players keep their setup. The EXE is not Authenticode-signed.

## Add a mod, resource pack or shader

**Mods also need the mod check.** The server only lets in the mod ids listed in `config/holylois-mods.json` (see **Mod check** below). A new mod has to be added there (`work/make-mod-allowlist.py`, or its fabric.mod.json ids including nested jars) before the pack that ships it goes live, or everyone who updates is turned away.

1. Close Minecraft.
2. Open your **Holy Lois: Reborn** CurseForge profile and choose **Open Folder**.
3. Put the download in the right folder:

| Download | Folder | Server too? |
| --- | --- | --- |
| Client mod JAR | `mods` | No |
| Gameplay mod JAR | `mods` | If its download page says required on the server |
| Resource pack ZIP | `resourcepacks` | Usually no |
| Shader ZIP | `shaderpacks` | No |

Choose the exact **Minecraft 26.3 Fabric** file and add its required dependencies. Keep only one release of each mod. Do not unzip JARs or pack ZIPs. Do not use Paper plugins.

4. Launch the profile. Enable the resource packs you want players to use. Test the new feature, joining the server, resource reloads and shaders if relevant.
5. Close Minecraft and its launcher.

The app checks mod dependencies and official download metadata before preparing a release. It can stop if a download is incompatible, an unreviewed alpha, or has no verified source. Fix the reported file rather than bypassing the check.

## Send the update to friends

Open **Holy Lois Admin** on your Desktop or Start menu. Friends get **Holy Lois Reborn** in both places when they install.

1. **Choose folder**: select your tested CurseForge profile folder, the one containing `mods`, `config` and `options.txt`.
2. Enter a new version such as **1.5.3** and a short description of your changes.
3. Review **Shared settings**. Existing reviewed files start checked. New config files start unchecked so you can choose what players should receive. Never select account, voice-device or personal map files.
4. Tick the box confirming that you tested the profile and closed Minecraft.
5. Click **Prepare update**. The app checks files, captures the selected settings and creates a signed release.
6. If a mod needs the server, update the server before the next step.
7. Click **Publish to friends**.

The first publish needs **Connect GitHub once**. Complete GitHub's sign-in and permission review yourself in its browser/window. Holy Lois never asks you to enter a GitHub password or token. The owner tool uses the official GitHub CLI already included in your local toolchain.

After publishing, friends see an update on the next check, normally within two minutes while Holy Lois is open. They close their game/launcher, then click **Update Holy Lois**. They do not need a new EXE for each mod change.

A new release applies changed shared settings before the next game launch. Supported JSON/options/properties and TOML merge changed published values while preserving unrelated personal values. Unsupported personal TOML stays byte for byte. Other shared formats follow their reviewed policy. Existing keybinds in `options.txt`, voice devices, accounts, worlds and caches stay personal. Previous settings are retained in the update recovery backup. Repairing the same version does not repeatedly reset settings.

Starting graphics stay at render distance 12, DH distance 64, shaders off. Resource-pack activation follows the shared Minecraft options. Adding a shader does not turn shaders on.

If you make a mistake, prepare a **higher** version containing the last good content. For example, fix 1.5.3 by publishing 1.5.4. Never edit an already released version or lower its number.

## Update the server

All paths below are examples. Keep your real SSH host, username and key location private. Configure `HOLYLOIS_SSH_HOST` and `HOLYLOIS_SSH_USER` locally, or pass `-HostName`, `-User`, `-Key` and `-Stage` to Server-Admin.ps1.

The server is separate from the client release. Your survival world is kept.

1. Close Minecraft. Put only the new **server-compatible JARs**, plus dependencies, in:

```text
%USERPROFILE%\Downloads\server-mods
```

Keep one version of each mod in that staging folder. Client-only animations, shaders and interface mods stay off the server.

2. In **Holy Lois Admin**, click **Server start / stop / update**.
3. Choose **Check staged mods**. Read the replacement plan.
4. Choose **Back up and install staged mods**.
5. Wait for the tool to report successful startup and **Done**. Test joining before publishing the client update.

The tool stops Minecraft, makes and verifies a complete maintenance backup, replaces the staged mod IDs, starts the service and checks startup. A failed startup restores the previous JARs and retains the backup. It does not wipe your world. Some mods can change data before failing; full restoration is a separate stopped-server operation.

## Start, stop or check the server

Use **Server start / stop / update** in Holy Lois Admin. Choose **Status**, **Start**, **Stop**, **Restart** or **Logs**.

If you prefer a fresh Windows PowerShell window, connect with:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" SSH_USER@SERVER_HOST
```

Once connected, run the command you need in the **Ubuntu shell**:

```bash
sudo systemctl status minecraft --no-pager -l
sudo systemctl start minecraft
sudo systemctl stop minecraft
sudo systemctl restart minecraft
sudo journalctl -u minecraft -n 100 --no-pager
df -h /
exit
```

Closing SSH does not stop the server. `/rtp`, `/tpa NAME` and other player commands belong in **Minecraft chat**.

## If a friend's SK pack was deleted

Close Minecraft and SKlauncher, then reopen Holy Lois so it updates to launcher 1.0.3 or newer.

1. Choose **SKlauncher** and click **Install** (or **Check files** under the button).
2. Click **Play** in Holy Lois. Open **Library > Holy Lois: Reborn** in SKlauncher.
3. If SKlauncher shows **Install**, click it once to prepare Minecraft and Java, then **Play**.

The updater installs directly into SKlauncher's own instance folder and restores a deleted Library entry automatically. Manual import and folder linking are no longer needed. Personal files and unrelated instances are preserved.

## Official Minecraft Launcher

Microsoft Store and desktop installs are detected. Store users do not need to search for an EXE. Click **Open Minecraft Launcher**, then choose **Installations > Holy Lois: Reborn > Play**. Sign in inside Minecraft Launcher.

For an unusual desktop install, **Find launcher** accepts its EXE or a Windows shortcut. The profile and HQ icon are prepared separately from other Minecraft installations.

## Backups and space

Google Drive (`Holy Lois Backups`) is the off-site recovery destination. Local staging and restore tests still consume VM disk until verified cleanup is approved. Copying to Drive alone does not reclaim those bytes.

- **World (JEB)**: differential every 30 minutes, full every 3 hours, with the repaired 64 GB local size limit. The off-site job runs every three hours with a small random delay and selects the newest complete native full/differential chain. It does not automatically reclaim every older local JEB archive. Keep the base required for subsequent differentials; review original receipts, provider hashes and dependencies before local cleanup.
- **Release backups**: jar/config-only changes back up mods and config. World changes require a complete stopped backup excluding rebuildable BlueMap tiles. The off-site job can upload completed recognized maintenance sets, verify every member, then reclaim eligible local staging. Held, unfinished, failed or unrecognized sets stay protected. A successful upload does not release a hold.
- **One-time move**: `server/ops/move-backups-to-drive.py` moved the older maintenance folders, legacy archives and old JEB files to `maintenance/`, `legacy/` and `world/` on Drive, each verified before deletion. `/opt/minecraft-backups/terrain-expansion` is the terrain job's state, not a backup, and stays.
- **Restore**: follow [the recovery guard procedure](server/ops/RECOVERY-GUARD.md). Verify complete recovery sets and preserve the latest external request ledger/key before extraction or startup. A raw copy followed by starting Minecraft is not a complete restore procedure. Archives include private server data; never send them to friends.

Check disk headroom before backups, deployments and large rehearsals. Local archives, held sets and extracted test servers can grow faster than the live world. Preserve proof receipts, and obtain exact deletion approval for completed local test copies. Remote pruning remains disabled.

## Release tools and pack 2.2.0 changes

- **Preflight**: `python scripts/preflight.py` checks that the docs name the current versions, no private data, no em dash in tracked text (both public repos) and that the launcher embeds the newest release notes. Pack signatures, launcher builds and server rehearsals stay separate steps.
- **Config drift**: copy `server/` to the host and run `sudo python3 ops/check-config-drift.py DIR`. It compares the tracked server configs (OPAC, Easy*, legends, rules, Tab, stats lists) with `/opt/minecraft`. After a release only intended changes may differ; take live-only edits back into git.
- **Smelting** (the `autosmelt:auto_smelt` pickaxe enchantment) is built into Holy Lois Extras 1.9.0 with the same id, so old pickaxes keep it. The separate `Auto Smelt 26.3.jar` is gone from the pack and the server (Extras refuses to load next to it), and so is `holylois-glint-preload` (now inside Extras).
- **Achievements** are translatable: `server/advancements/make-advancements.py` writes `holylois.adv.*` keys with English fallbacks (server log, Discord and stats stay English) plus lang files from `translations.json`; copy `server/advancements/lang/*.json` into `addons/extras/assets/holylois_adv/lang/` when titles change.
- **Title panorama** lives in the `HolyLois-FishEating.zip` resource pack (`addons/fish-eating`), not in the Auth UI jar (72 KB instead of 6.5 MB).
- **Extras mixins**: `holylois-extras.mixins.json` (vanilla targets) fails loudly on a missing injection point; `holylois-extras-compat.mixins.json` (other mods) stays optional.

## Server release for pack 2.1.0 and launcher 1.5.0

Deployed 2026-10-18 with `server/ops/hl-deploy.py` (plan `~/hl-210/plan.json`, loopback rehearsal receipt next to it, jars/config backup in `/opt/minecraft-backups/maintenance/release-210-*`). Swaps: OPAC 0.33.0, Liteminer 4.5.2, Amber 11.7.0, JEB 1.2.0.9, MidnightLib 1.10.0, Repurposed Structures 7.8.4, EconomyCraft 1.11.0 (its config.json converts to sections on first boot), Extras 1.8.0 to 1.8.3 (colossal fish). Files: revised `config/economycraft/prices.json` (enchantments 6% of the old sell value, at least 4; tools, weapons and armor half), OPAC `playerClaimsExpirationTime = 720` with `playerClaimsConvertExpiredClaims = false` (claims of players inactive for 30 days return to wilderness), MiniMOTD headline.

**Free-play name rule (owner 2026-10-18):** a free-play account that took a bought account's name (the launcher asks the player to confirm) is moved into the backup folder when the premium owner first joins: move its player data, stats, advancements, claims and homes like the 1.7.3 profile cleanup and remove its login with `auth remove NAME`. A free-play name registered before the name was bought stays locked. A player who owns both asks on Discord to move their progress. From pack 2.2.0 this is automatic: EasyAuth runs with `premium-auto-login=true` (server `online-mode=true`) and `check-offline-players-with-online-usernames=true` in `config/EasyAuth/extended.conf`, so a name that was free at registration is stored as offline and stays locked, while a bought name taken by free play stays claimable. When the real owner joins verified by Mojang, onboarding (`FreePlayNames`) moves every file named after the name's offline UUID (playerdata, stats, advancements, mod player data) into `world/holylois/private-account-backups/free-play-NAME-TIME/` with a `moved.txt` receipt and tells online operators. Claims of the old character expire after 30 days like any inactive land. Names already stored as offline before 2.2.0 stay locked; use `auth markAsOnline NAME` only after checking with the player.

## Quiet pack 2.0.3 and server lag fix

Pack 2.0.3 (2026-10-16) updates Fabric API 0.163.0, Puzzles Lib 26.3.15, EMF 3.3.12 and ETF 7.2.6; public history is
unchanged. The server-only `server/entity-residency` mod 1.1.0 also skips Runeforged's per-tick gear attribute recompute
while a player's weapon, armor and effects are unchanged (recompute on change and at least once a second). The pregen
controller accepts Chunky's "No tasks to pause" reply and restarts its pause deadline after a server restart.

## Pack 1.9.4

Published 2026-10-11, client only (Extras 1.7.4). Fishing cinematic: while waiting for a bite, each shot is Ji's FishingShot with the next of its five presets (CinematicManagerMixin + CinematicShotsMixin drive evaluateFrame on our own clock); on a bite the mod's own focus holds until the catch or escape; 3 s after reeling in the normal shots return. Ji's CinematicMusicManager and vanilla MusicManager stay silent while BoomboxPulse.musicNearby(). Server unchanged (Extras 1.7.1).

## Pack 1.9.3

Published 2026-10-10, client only (Extras 1.7.3): the carried boombox swings about the holder's forward axis in world space (out from the body and back in) instead of a model axis that the arm pose turned diagonal, and held notes start at the speaker cones (positions recorded while the boombox is drawn). Server unchanged (Extras 1.7.1); sync at the next server deploy.

## Pack 1.9.2 and launcher 1.4.2

Published 2026-10-10. Pack 1.9.2 changes only Holy Lois Extras on the client (1.7.2: boombox and music disc music moves into your ears while the Ji AFK cinematic runs, instead of by distance). The server keeps Extras 1.7.1 until the next server deploy; nothing in 1.7.2 talks to the server, and the pack minimum stays 1.9.1. Launcher 1.4.2: only Java processes that are Minecraft (a Minecraft/Holy Lois window or LWJGL loaded) block an update, so build tools or other Java apps no longer make "Close Minecraft to update" hang; What changed shows Added / Changed / Fixed / Removed. Pack history may carry "fixed" only once launchers older than 1.4.2 are gone (they reject unknown manifest fields).

## Launcher 1.4.1

Published 2026-10-10 as `v1.4.1` (signed pack 1.9.0 built in); `app-stable` `app-release.txt` and `app-release.catalog` point to it. Visual only: gold kept for the main action and state, Help without /spawn. No server change.

## Launcher 1.4.0

Published 2026-10-10 as `v1.4.0` with the signed pack 1.9.0 built in; `app-stable` now points to it in both `app-release.txt` (the file launchers read) and `app-release.catalog`. Until then `app-release.txt` had still pointed to 1.3.1, so 1.3.1 installs update straight to 1.4.0. No server change. The skin head reads the public `stats.holylois.com/stats.json` and Mojang textures; the website privacy page says so.

## Server release for pack 1.9.0

Extras 1.7.0 and onboarding 1.9.0 are live with client Auth UI 1.1.0; launcher 1.3.2 is unchanged. `server/deploy-release-190.py` swaps 10 mod jars for 11 (Open Parties and Claims 0.32.8, Farmer's Delight 3.6.28, REI 26.3.824, Fabric API 0.162.0, ModernFix and library updates), turns off the Fish of Thieves tropical island biome (`config/fishofthieves.json`, new chunks only), sets `maxPlayingPerChunk` to 6, installs the Tab style from `server/styledplayerlist`, adds the 1.9.0 client mod ids to `config/holylois-mods.json` and raises the pack minimum to 1.9.0. Extras registers the Holy Lootbox item, so older clients cannot join.

`server/test-190.py` boots the same change set on an isolated loopback copy with the live OPAC data first. OPAC 0.32.8 rewrites `config/openpartiesandclaims-server.toml` once in its new layout: every existing value stays, and only the new claiming-anchor keys are added (anchor claiming off). REI 26.3.824 logs harmless "Failed to fill display" errors for brewing recipes at start.

## Server release for pack 1.8.3

Onboarding 1.8.3 carries `/party` and `/group` redirects to native OPAC, installed after command registration and after successful datapack reloads. Existing command roots are preserved. Membership, permissions and claim access remain native; no migration.

The SkinsRestorer 15.12.6/Fabric 26.3 compatibility hook carries the returned skin profile into vanilla's `authenticatedProfile` field before login finishes. It checks the same UUID and activates only for installed version 15.12.6. Upstream issue 2162 / PR 2163 describes the fix; remove the workaround after verifying a released upstream fix.

BlueMap gets a selected-skin provider through its supported API. Skin URLs are vetted Mojang textures; downloads are bounded and redirects rejected. No signatures/authentication records are exported. Native skin fallback, icon factory, player visibility and marker refresh timing remain. Launcher head previews are not implemented. Native map render consumers remain disabled in the isolated probe; real marker appearance is an owner check.

Pack 1.8.3 and launcher 1.3.2 were published and deployed on 2026-10-08. Automatic custom scans failed with 0x80508023. The owner then completed a manual Defender scan with zero threats and reported VirusTotal 0/69 for the exact matching final EXE SHA-256. Record that as owner scan evidence, not an automatic scan pass or antivirus guarantee.

## Server release for pack 1.8.2

Extras 1.6.2, onboarding 1.8.2 and client Auth UI 1.0.5 are live. Party membership comes from OPAC; snapshots require authenticated exact-party membership. No allied-party/outsider health or rally delivery. One transient mark per party,90sec expiry,10sec sender cooldown, cleared on sender departure or server stop. HUD updates every10ticks, with bounded64-member payloads. No passive member coordinates in this payload; OPAC's pre-existing location settings remain separate.

Friendly-fire guards use server damage attribution and harmful-effect application; healing and unrelated PvP/environment damage remain. They do not provide immunity from arbitrary environmental traps/modded hazards. Daily coins use `EconomyManager.claimDaily(UUID)` and its original ledger/calendar. Do not add a separate raw coin payment or reset that ledger.

The candidate passed isolated real-membership/damage/effect/privacy/rally/daily retry tests and existing reliability regressions. The test-only probe jar is never a public/release asset. Owner HUD/reward/network visuals still need real play checks. Pack 1.8.2 is published and deployed with a fresh verified full backup and automatic rollback. See the private current handoff for artifact/check locations.

## Server release for pack 1.8.1

`config/holylois-quiet.json` includes pjampjam and pjamtest. The existing hot-reload suppresses join/leave, AFK, advancement and discovery broadcasts. Discord also omits their automatic death notices and status-list entries. Typed chat still forwards; in-game death messages retain the previous policy. Existing additional quiet names are preserved. The follow-up config was tested in the isolated copy and against synthetic Discord events, then applied with exact restore bytes from the verified 1.8.1 backup; no further restart.

`server/deploy-release-181.py` installs Extras 1.6.1 and onboarding 1.8.1, statistics exports/visibility defaults, pack minimum 1.8.1 and the MOTD. Auth UI 1.0.4 is client-only. The loopback regression probe covers relic recovery/restart, crate rewards, combat teleports, protected mob damage/push and radio controls/caps. Deployment takes a full verified backup and restores changed files automatically if startup fails. Keep launcher/app-stable 1.3.1 unchanged and move pack-stable immediately after a healthy server start.

Owner/test exclusions merge with `/etc/holylois/stats-hidden.txt` and `config/holylois-stats-hidden.json`; they remove public rankings, totals, discoveries and head exports without deleting game progress. SkinsRestorer remains the skin store. The bridge exports only vetted Mojang texture URLs to `world/holylois/skin-textures.json`, with no authentication data. Personal privacy commands remain planned. Pack 1.8.3 adds the administrator-requested account forms described below.

## Server release for pack 1.8.0

`server/deploy-release-180.py` (run as root from `~/hl-180`; `--check` only runs the pre-checks) installs Fish of Thieves, Fishing Loot Crates and any required library the server does not run yet (jars and SHA-512 from `new-mods.json`, made by `make-pack-180.py` from Modrinth), Holy Lois Extras 1.6.0, `config/holylois-legends.json`, `config/holylois-fish.json`, the advancements (legends and fishing), the new mod ids in `config/holylois-mods.json`, pack minimum 1.8.0 and the MOTD. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails. Test first with `server/stage-and-test-180.py` (loopback copy on port 25566 that checks its own log and stops).

- **Legends** (`server/legends/holylois-legends.json`): each legend has an id, a name, a chat colour and items. An item has an id, a base item (`treasure_map` for a real buried treasure map), a name, lore lines, `where` (`chests`, `fishing` or `both`), a weight, optional enchantments and an optional `light`. `chestChance` (1.2%) is per structure chest (`chestTables`, `*:chests/*`), `crateChance` (5%) per fished loot crate (`crateTables`), `treasureChance` (30%) per vanilla fishing treasure catch, which then becomes a bottle, a map or a fishing legend item by `treasure` weights. Edit the file and run `/legends reload`; run `python server/advancements/make-advancements.py` too when items or legends change, because the achievements are made from the same file.
- **Fish weights** (`server/legends/holylois-fish.json`): lightest and heaviest kg per species; other edible items in `#minecraft:fishes` or the `fishofthieves` namespace use `fallback`. `curve` 2.5 gives about 76% Common, 13% Uncommon, 7% Rare, 3% Epic and 1% Legendary. `mythicChance` (1/60 of Legendary catches, about 1 in 5,000 fish) turns a Legendary into a Mythic, announced with a sound to everyone. Trophy weights come from `bands` (kg per rarity: Rare 1-2.99, Epic 3-19.99, Legendary 20-40, Mythic 40-100), not the species range; `shinyChance` (1/250) makes a trophy Shiny. Effects per species (eaten and held in the main hand) are in `FishTraits.java`; cooking keeps them and adds half again. Size follows weight (`FishData.scaleKg`), and 10 kg and up is carried overhead; `FishHands` keeps the off hand empty meanwhile (every 5 ticks, the item goes back into the inventory or drops), and `FishHands{Click,Slot,Swap}Mixin` refuse F swaps and off-hand slot placement on both sides, so the client never predicts a heavy fish into the off hand (that race duplicated fish in creative, where the inventory trusts the client). On the cutting board a trophy gives `round(2 + kg / 1.5)` slices (2-64), four per cut; the fish keeps a damage bar between cuts. Slices keep rarity, Shiny and a quarter-length, one-level-lower copy of the eaten effects. Nutrition and saturation grow with log2(1 + kg) and shrink with each cut (`FishTraits.wear`).
- **Commands** (operators): `/legends list`, `/legends reload`, `/legends give <item id | bottle | map | fish | rare | epic | legendary | mythic | shiny>` (the last five make a test catch of that rarity, `shiny` a Shiny Legendary; a Mythic or Legendary test catch is announced like a real one).
- **Capture** (operators, client commands): `/capture ultra` switches your client to the capture profile (render distance 32, far Distant Horizons, shaders on) and back to your own settings. `/capture panorama [seconds]` hides the HUD, turns to the six cube faces at a 90-degree field of view, waits [seconds] (default 3) per face for the shader to settle and saves square shots as `screenshots/holylois-panorama-DATE/panorama_0..5.png` (title-screen order). Keep the mouse still while it runs; `/tick freeze` stops clouds and water between faces.
- **Mod check**: Fabric Loader's own built-ins (java, minecraft, fabricloader, mixinextras) are always allowed now, so the hotfix `allow-loader-mods.py` is no longer needed for new lists.
- Held legend items with `light` glow through LambDynamicLights (`assets/holylois/dynamiclights/item/legend_light.json` in the Extras jar); this is an owner check in game.

## Server release for pack 1.7.11

`server/deploy-release-1711.py` (run as root from `~/hl-1711`; `--check` only runs the pre-checks). Pack 1.7.11 removes Quick Play: Holy Lois Extras 1.5.1 drops `QuickPlayClient`, launcher 1.2.7 drops the setting and deletes a leftover `holylois-quickplay.json` on Play. The server keeps extras 1.5.0 (the removed part was client-only, so the server behaves the same) and does not restart. The step replaces the MOTD headline that still promised Quick Play, runs `minimotd reload`, puts the old `main.conf` back if the reload fails, and posts the Discord note. Next server release installs extras 1.5.1 or newer with its other changes.

## Server release for pack 1.7.10

`server/deploy-release-1710.py` (run as root from `~/hl-1710`; `--check` only runs the pre-checks) installs onboarding 1.8.0, Holy Lois Extras 1.5.0, `config/holylois-daily.secret`, the datapack with its logo, the new server icon, `max-tick-time=120000`, the AFK-free Tab playtime, the pack-only rule in `rules.txt`, MOTD, then (after the server is up) the Discord bot, `make-stats.py`, `weekly-recap.py` and the lag-guard terrain job, and resumes the terrain job from its Chunky checkpoint. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails.

- **Quiet names**: `config/holylois-quiet.json` is `{"names": ["pjampjam", "pjamtest", "pjanpjan"]}`, re-read when the file changes. Join, leave, AFK, advancement and discovery broadcasts about these names are not sent; death messages still are. The Discord bot reads the same file (hidden from the Players field, status and the join/leave lines; deaths never reach Discord for them).
- **Staff out of the online lists** (onboarding 1.11.0): operators and quiet names are not counted or listed for other players in the server list (count and hover), the Tab list (`%holylois:online%`/`%holylois:slots%` in the Tab header), `/list` and the Discord status. They stay visible in the world, and operators still see everyone. Pings from the server itself that name `localhost` (pregeneration, deploys, lag watch) keep the real count; the Discord bot and `make-stats.py` ping as `play.holylois.com` and get the public view. Command name suggestions can still complete a hidden name.
- **Name check** (launcher 1.4.6): `https://stats.holylois.com/name/NAME` answers `{"taken": true|false}` for one valid name, 30 checks per visitor per minute, from `taken-names.json` that `make-stats.py` writes (joined names, renamed accounts, staff; never the auth database, never served whole). EasyAuth locks a name on its first join: a free-play first join stays free play even if someone buys the name later (that buyer gets the login form), a premium first join needs that Microsoft account from then on.
- **AFK ledger**: `world/holylois/afk.json` adds one second per AFK second (Essential Commands decides, `auto_afk_time` is 15 minutes, `/afk` too). Playtime for achievements, claims, leaderboards, stats, recap and Tab is vanilla `play_time` minus the ledger, counted from this release on. If Essential Commands is missing the ledger waits and nothing is subtracted.
- **Secret code**: `/redeem CODE`. The code is HMAC-SHA256 of the Riga date (Europe/Riga, since 1.9.0) with `config/holylois-daily.secret`, the same as the website (`docs/DAILY-CODE.md` in the website repo; Worker secrets `CODE_SECRET` and `DAILY_CODE=on`). Yesterday's code works until 01:00 Riga time. One redeem per UUID per Riga day (`world/holylois/redeem.json`); since 1.9.0 a redeem needs 2 hours of active play in total and 20 active minutes that day (AFK time never counts, active minutes are counted in the same file), 5 wrong tries per hour, prize rolled from player and date (coins 50%, lootbox 25%, diamonds 13%, rune find 11.5%, legendary 0.5%). The secret lives in `private/holylois-daily.secret`; never put it in a repository or chat. Rotating it changes every code from that moment.
- **Terrain job**: slices of 15 minutes with 10 minute rests, 20 minutes when the log shows 100 or more ticks behind (`server/terrain/README.md`). Test with `server/terrain/test-expand-terrain.py` (23 tests).
- **Launcher 1.2.6**: Play mode in Settings (Quick Play, removed again in 1.2.7). Update asks before closing Minecraft and its launcher.
- **Launcher 1.3.0 (fast start)**: player-name accounts ("name", and SKlauncher players unless they switch back) start Minecraft from the app. Java and Minecraft live in `%LOCALAPPDATA%\HolyLoisReborn\data\game` (files shared with other launchers are hard-linked), game output and the last start record in `data\logs`, names in `data\players.json` (kept on uninstall unless the player ticks "forget"). The game gets Minecraft's own `--quickPlayMultiplayer play.holylois.com` when Join Holy Lois on start is on; bought accounts get the same option in the Minecraft Launcher profile. Offline UUIDs are the standard `OfflinePlayer:NAME` ones, the same the server computes, so SKlauncher players keep their progress. Launcher 1.3.2 accepts valid names without a Mojang ownership lookup. Holy Lois account names are first-come and protected by the existing server password; selecting a name never grants ownership of an existing account. A launcher-side name limit is only a courtesy: bots do not use the launcher, so real protection stays on the server (EasyAuth, the mod check).

## Server release for pack 1.7.8

`server/deploy-release-178.py` (run as root from `~/hl-178`) installs Holy Lois Extras 1.4.0, `config/holylois-mods.json`, the advancement texts and `server-icon.png`. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails (the mod list is removed again on rollback). The pack minimum stays 1.7.5.

- **Mod check**: `config/holylois-mods.json` is `{"mode": "enforce" | "warn" | "off", "missing": "warn" | "kick", "legacy": "allow" | "block", "exempt": ["name"], "allowed": ["modid"]}`. It is read on every join, so changes need no restart. In `enforce`, a client with a mod id that is not allowed is kicked with an EN/RU/LV message naming the mods. Missing pack mods are only logged unless `missing` is `kick`. Clients too old to answer (extras before 1.4.0) get in while `legacy` is `allow`. `exempt` names skip the check (the owner). The list holds every id of the pack including libraries nested in jars. If friends are locked out by mistake: set `"mode": "off"` and tell the owner. It stops accidents and casual extras, not a cheat client that fakes its list.
- **Loader mods in the mod check**: every client also reports what Fabric Loader itself provides (`fabricloader`, `java`, `minecraft`, `mixinextras`). The list made from the pack's jars lacked `mixinextras`, so every non-exempt player was turned away until `server/allow-loader-mods.py` (run as root, `--check` first; no restart) added them. Keep these four in the list whenever it is regenerated.
- **Launcher 1.2.4**: Play moves foreign jars from `mods/` to `state/quarantine/<time>` (never deletes), repairs changed pack mods and re-enables the pack resource packs.
- **Window icon**: crown icons drawn pixel-perfect for 16 to 64 px (`work/make-brand.py`). **Server icon**: new 64 px crown.

## Server release for pack 1.7.6

`server/deploy-release-176.py` (run as root from `~/hl-176`) installs onboarding 1.7.2 and Holy Lois Extras 1.3.1. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails. The pack minimum stays 1.7.5 because nothing new is registered.

- **Discoveries**: all Epic Dungeons (`epic:*`, 9 dungeons and 3 obelisks) and the small undead and creeping crypts are announced. Other `small_` structures stay quiet. A large plains dungeon is `epic:large_dungeon`.
- **Achievements**: datapack `holylois-advancements` gained Dungeon Delver, Deeper Still, Dungeon Master (hidden, all 9 dungeons) and Odd Pillar (`server/advancements/make-advancements.py`).
- **Runeforged**: `server/structures/runeforged-epic-additions.json` adds the 17 `epic:chests/*` tables to `config/runeforged-monsters.json` (treasure tier 1, magic, scary, mineral, library, potions and the weapon tables tier 2, the rest tier 3). Epic dungeons are jigsaw structures that pick random rooms, so a dungeon may have no treasure room at all.
- **Boombox range**: `range(volume)` runs from 16 blocks (volume 1) to 48 (volume 10); `distance` in the config is no longer used.
- **Server list line** shortened to fit.

## Server release for pack 1.7.5

`server/deploy-release-175.py` (run as root from `~/hl-175`) installs onboarding 1.7.1 and Holy Lois Extras 1.3.0. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails.

- **Pack check**: `config/holylois-pack.json` holds `{"minimum": "1.7.5"}`. Joining clients send their pack version during login; an older pack gets a friendly EN/RU/LV "update in the Holy Lois launcher" message instead of registry errors. No file means no check. Raise `minimum` with every release that both sides need.
- **World border**: 20,000 blocks wide (10,000 from 0,0). `server/bluemap/set-render-bounds.py BORDER` keeps BlueMap inside it (the Nether gets 1/8). The old radius-4,000 terrain task and job state were moved into the release backup.
- **Terrain**: `expand-terrain.py` with `BORDER = 20000` pregenerates all 1,565,001 chunks inside the border while nobody is online (about 12 hours of empty server) and raises `/rtp` to 5,000 only after every chunk is proven `Status=full`.
- **Homes**: `/home` with several homes uses the one named `home` in any capitals; names that differ only in capitals are refused; `/Home` is an alias.
- **Portals**: a player who walks back into the portal they arrived at (within 16 blocks) returns to the portal they left from, if it still exists. In memory only, so a restart forgets it.
- **Recipes**: datapack `world/datapacks/holylois-recipes` removes the recovery compass recipe (copy in `server/datapacks/`).
- **Boombox stations**: the six new stations were appended to the live `config/holylois-boombox.json` (13 in total, the boombox cycles through at most 16).
- **Tab list**: `%holylois:slots%` shows online + 1, like the server list.

## Server release for pack 1.7.4

`server/deploy-release-174.py` (run as root from `~/hl-174`) replaces Flan with Open Parties and Claims 0.31.6 and installs onboarding 1.7.0 and Holy Lois Extras 1.2.0. Same safety as earlier releases: 0 players or a one-minute countdown, complete verified backup, rollback if startup fails. Afterwards it sets the world border, updates the Discord bot and the off-site backup job.

- **Claims (OPAC)**: `config/openpartiesandclaims-server.toml` (copy in `server/opac/`). Permissions through LuckPerms, 16 free chunks, 2 force-loaded chunks, OPAC's own welcome messages off because Holy Lois Extras draws the zone titles. Players claim on the world map (J, right-click; M is voice mute) or with `/oclaims`; teams with `/oparties`. Admins: `/opac` and `/oclaims` server claims.
- **Extra chunks**: `config/holylois-claims.json`. One earned chunk per 2 hours played (up to 48), bought chunks cost 500 coins for the first and 15% more each (up to 64), selling refunds half. Purchases are stored in `world/holylois/claims.json`; the add-on sets OPAC's bonus claim count to earned + bought every five minutes and at login.
- **/rtp**: handled by the add-on now (Essential Commands' rtp is off). Overworld only, 5-minute cooldown, 3 seconds standing still, and never within one chunk of a claim. First-join and bed-less respawn spots use the same rule.
- **Combat tag**: a PvP hit tags both players for 20 s, a mob hit only delays teleports for 5 s. Logging out while PvP-tagged kills the player and drops the loot. Teleport commands (rtp, home, tpa, spawn, back, warp) are refused while tagged.
- **Deaths**: normal deaths keep the drops for 30 minutes, owner-only for the first 5. PvP deaths get no coordinates, no pickup lock and no minimap death point.
- **/support and /report**: logged as `HOLYLOIS-SUPPORT {json}`; the Discord bot posts them to #support under STAFF with an owner ping and two buttons ("On my way", "Solved") that message the player in game. Five-minute cooldown each.
- **/donate**: the wallet list moved here from the old `/support`; addresses are in `DonateCommand.java`.
- **World border**: 14,000 blocks wide (7,000 from spawn), warning at 64 blocks. Raise it later with `worldborder set`; never lower it below land people live on.

## Journal for pack 2.0.0

Discoveries v3 adds personal fish/visit/creature records to `world/holylois/discoveries.json`, keyed by stable player UUID. It migrates v1/v2 discoveries without clearing firsts. A broken store fails loading instead of replacing the history. New catches, visits and best creature levels start when the candidate is installed; lifetime kill counts still come from vanilla stats.

`/journal`, `/discoveries` and `/discoveries mine` open read-only screens for authenticated players. Page requests have no target identity, are rate-limited and return at most eight entries. Personal records are sent only to their owner. The public stats exporter selects world-first fields explicitly and never exports the `journals` collection. Waypoints stay on the requesting client; Map opens the existing public BlueMap location.

Per-mob firsts use `mob:NAMESPACE:TYPE` keys. Repeated kills can raise their highest recorded level but never replace the original first player, time or location. Ordinary mob firsts have a compact gold broadcast without the challenge chime. Boss firsts retain their existing celebration.

## Server release for pack 1.7.0

`server/deploy-release-170.py` (run as root from `~/hl-170`) adds Macaw's Holidays and onboarding 1.5.0, installs the cleaner Tab style, removes the old tagline from the server list, raises `view-distance` to 12, updates the Discord monitor and enables the weekly recap. It refuses while players are online, backs up the complete server first and rolls back if the server does not start. Afterwards it posts the update notes to Discord.

- **Leaderboards** come from the vanilla stats files, refreshed every two minutes off the main thread.
- **Discoveries** are stored in `world/holylois/discoveries.json`. Never edit the file while the service is running; back it up before any reviewed correction.
- **Weekly recap**: `holylois-weekly-recap.timer` posts on Sundays at 19:00 Riga time. A week with no play posts nothing.
- **Restart notes**: every restart, planned or not, is announced once in Discord #server-status.
- **Daily gifts and events**: `world/holylois/daily.json` (streaks) and `world/holylois/events.json` (holiday gifts, day counter). Time and weather pause while the server is empty, so the day counter follows real play. `/dailytest <1-7>` (operators) previews the reward card for that streak day; it gives nothing and changes no streak.
- **Economy**: EconomyCraft with the admin shop and sidebar scoreboard off (`config/economycraft/config.json`). Item prices are in `prices.json`.
- **Boombox stations**: `config/holylois-boombox.json`, then `/boombox reload`. Plain MP3 streams only; at most 6 play at once (held and placed together), and at most 6 placed speakers per chunk by default (`maxPlayingPerChunk`, 1-6; a config saved before 1.9.0 may still say 2). Controls follow effective OPAC access. Placed boomboxes that are switched on are listed in `world/holylois/boomboxes.json`.
- **Server list line**: `line2` in `config/MiniMOTD/main.conf` always announces the newest exciting change; update it with every release.
- **/donate** (named `/support` before 1.7.4): the wallet addresses and the hover help per network live in `DonateCommand.java` (onboarding add-on); keep holylois.com/donate in sync. Donations never buy anything in game (Minecraft server rules).
- **Restart countdown**: release scripts show a one-minute boss bar when players are online. Custom boss bars are saved in the world, so the scripts remove `holylois:restart` before stopping; if one is ever stuck, run `bossbar remove holylois:restart`.
- **Public stats**: `server/stats/make-stats.py` (installed in `/usr/local/lib/holylois/`). Names matching the slur filter are masked as first letter plus stars; names listed in `/etc/holylois/stats-hidden.txt` are left out entirely. `server.online` is a live count at generation time.
- **Removing old profiles**: release 1.7.3 moved test and duplicate accounts into `removed-profiles/` inside its backup folder (player data, stats, advancements, claims, homes), dropped them from `usercache.json` and onboarding, and removed their logins with `auth remove NAME`. Move the files back to restore one.
- **No em dashes for players**: SkinsRestorer translations that used them have dash-free copies in `config/skinsrestorer/locales/custom/` (they take priority over `repository/`). Delete a copy to get upstream text back.
- **BlueMap**: renders only while nobody is online and serves on 127.0.0.1:8100. It becomes public once the domain tunnel points `map.` at it.
- **Live map branding**: `bluemap/web/index.html` title and `assets/favicon-*.png` were replaced with the Holy Lois crown. A BlueMap update can restore its defaults; re-apply if the tab says BlueMap again.
- **Discord**: the bot (`holylois-discord-bot`) keeps #server-status, #minecraft-chat and #rules in sync; #rules comes from `/opt/holylois-bot/RULES.md` (copy of RULES.md), refreshed on bot restart.
- **Vein mining**: shapeless only; the add-on forces it on the server and Holy Lois Extras removes shape switching on clients.

## Server release for pack 1.6.1

`server/deploy-release-161.py` installed Farmer's Delight and Macaw's Furniture (required on both sides), and the server-only Styled Player List, RightClickHarvest with Jamlib, Krypton, Alternate Current, Dungeons and Taverns, Towns and Towers with Cristel Lib, AudioPlayer and onboarding 1.4.0. It refuses while players are online, makes a complete verified backup under `/opt/minecraft-backups/maintenance/release161-*` and restores the previous files if startup fails.

- **Player list:** `server/styledplayerlist/` holds the Tab header and footer (`config/styledplayerlist` on the server). Edit `styles/holylois.json` and run `/styledplayerlist reload` as an operator.
- **Quote of the day:** edit `/opt/minecraft/config/holylois-quotes.txt` (`quote | author`, one per line). Changes apply without a restart. The welcome message and `%holylois:quote%` share it.
- **Java:** `/etc/systemd/system/minecraft.service.d/jvm.conf` sets a fixed 6 GB heap with Aikar's G1 flags. If the VM is resized to 4 OCPU / 24 GB (the Oracle Always Free limit), raise both -Xms and -Xmx to 10G and run `sudo systemctl daemon-reload && sudo systemctl restart minecraft` while nobody is online.
- **Backups:** the JEB budget is 12 GB so two full backups of the larger world still fit. Watch `df -h /`.
- **Structures:** Dungeons and Taverns and Towns and Towers appear only in newly generated land. `world/datapacks/holylois-structure-tuning` spaces their extra villages to 68 chunks so villages are about 1.5x vanilla, not 2x. Their 223 chest loot tables are linked to Runeforged tiers in `config/runeforged-monsters.json` (vaults and bosses T1, dungeons T2, houses and camps T3).
- **Sleep:** `players_sleeping_percentage` is 1, so one sleeping player skips the night.
- **Terrain:** `holylois-terrain-expansion.timer` runs while the server is empty. Since 1.7.5 it pregenerates everything inside the 20,000 world border while the server is empty, then raises RTP to 5,000. See `server/terrain/README.md`.

## Monitoring, bots and off-site backups

- **Discord alerts:** create a webhook in Discord (channel settings > Integrations > Webhooks > New Webhook > Copy Webhook URL), then on the server run `sudo nano /etc/holylois/discord-webhook`, paste it, save, and run `sudo chmod 600 /etc/holylois/discord-webhook && sudo python3 /usr/local/lib/holylois/discord-alert.py test`. The monitor checks every 2 minutes, reports crashes with the crash report and log tail, and says when the server is back. Planned deploys create `/run/holylois-maintenance` to stay quiet.
- **Bot wall:** `holylois-botwall.timer` counts the usernames SSH bots try (no IPs) for the Tab list and the operator command `/botwall`. fail2ban bans repeat knockers for an hour, longer for repeat offenders. SSH stays key-only.
- **Own Google client (since 2026-10-04):** rclone's built-in client is shared by all rclone users and gets rate limited (1 GB took 25 minutes). The remote now uses the owner's own OAuth client: Google Cloud project "Holy Lois Backups", Drive API enabled, Google Auth Platform External and **In production** (Testing logins expire after 7 days), no logo (a logo forces verification), home page holylois.com, privacy holylois.com/privacy, client type Desktop app. The owner typed the client ID and secret into `sudo rclone config` (edit `gdrive`) and signed in with `rclone authorize` on the PC; about 39 MB/s since. With scope drive.file a client sees only its own files, so backups made with the old client stay in the older "Holy Lois Backups" folder in Drive and new ones go into a fresh folder of the same name.
- **Google Drive:** run `sudo rclone config` once: `n` (new remote), name `gdrive`, storage `drive`, leave client id/secret empty, scope `3` (drive.file: rclone sees only its own files), no advanced config, and answer `n` to auto config. It prints a `rclone authorize "drive" ...` command: run that on your PC (install rclone with `winget install Rclone.Rclone`), sign in to Google in the browser, and paste the result back. Then `sudo systemctl start holylois-offsite-backup` uploads the first copy. Every 3 hours it uploads new world backups, changed server settings and finished release backups into `Holy Lois Backups` (release backups are then removed from the VM), and above 500 GB deletes the oldest while always keeping the newest 30 of each kind.

## Current pack and tests

Pack 1.5.2 has 50 client mods, four resource packs and seven optional shaders. The server has 29 mods. All 14 shared mods match by hash. Required dependency metadata, including bundled Fabric libraries, was checked on both sides.

The shader helper addresses the supplied Iris enchanted-glint crash. The owner tested shaders successfully afterward. Brief coarse DH terrain and terrain-download retries are separate issues, not certified fully fixed.

The normal launcher defaults to English, with Russian and Latvian selectable. GitHub notes and owner documentation remain English. The native installer remains under 1 MB and does not need a separate .NET install. Windows Authenticode signing is still absent, so SmartScreen warnings remain possible.

Keep your SSH key and `private/release-private.pem` private. Friends receive only the public installer and signed downloads. More implementation detail is in [TECHNICAL-GUIDE.md](TECHNICAL-GUIDE.md).

## Login, arrival and inventory defaults

The owner confirmed pack 1.5.2 joins through the existing Minecraft Launcher and SKlauncher. The original 0.4.0 downloads were withdrawn again after browser detection recurred. Microsoft diagnostic follow-up is required; see SECURITY-NOTICE.md. The owner confirmed offline registration/RTP and premium joins; 1.5.2 is the stable pack.

The centered form uses the existing EasyAuth account database and does not store a password on the client. Premium verification and the 24-hour same-IP session stay enabled. Before authentication, EasyAuth blocks movement, combat, inventory actions and damage. Escape in the form offers Back and Disconnect.

First registration uses safe RTP inside the pregenerated Overworld, followed by a 1.5-second black arrival screen. Returning players keep their position. A death respawn uses RTP only when vanilla finds no usable bed or anchor; leaving the End alive does not count as death. Brief arrival damage protection is temporary.

Inventory Profiles Next sorting remains available. Slot locking is opt-in; failed-replacement and low-durability visual/sound alerts are off. Friends on older settings can open R + C to disable those options immediately.

The old chained backup schedule reached its size cap and stopped making new backups. It was replaced by the schedule above, and a full plus differential backup was restored and hash-checked separately. Rebuildable Distant Horizons SQLite caches are excluded from scheduled world backups; terrain and player data are included. Complete stopped-server maintenance backups still protect authentication, permissions, claims and configs outside the world. Other files can still fill storage, so verify completed backups and disk usage periodically.

Use [TEST-GUIDE.md](TEST-GUIDE.md) for the premium, offline, respawn, voice and non-operator checks. No additional server mods are required for this release. Test the existing features before adding more systems.

## Account requests (pack 1.8.3, launcher 1.3.2)

These commands require an authenticated administrator with `holylois:account.admin` (fallback operator level 4), or the server console. They address registered accounts whether online or offline. Verify ownership before authorising recovery; a matching name alone is not proof.

- `/account rename grant NAME`: allow that authenticated player to choose an available new name. The private clickable reminder opens `/account rename`. The request lasts seven days and is used once.
- `/account password grant NAME`: allow a password change for one hour. An authenticated player can use the form directly. An unauthenticated player must enter the private recovery code. The command reports a private file path, never the code. Deliver the code privately after verifying ownership. Never paste it into server/chat commands or release logs.
- `/seen NAME` (operators only): online now (and AFK), or how long ago and when (Riga time) NAME was last on.
- `/account password reset NAME`: quick reset for a friend who forgot their password, no code. For the next 10 minutes the next
  player who joins as NAME can set a new password right away, so only use it while you are talking to them (anyone could join with a
  free-play name). Online admins get a chat message the moment it is used; it is also in the server log.
- `/account rename status NAME` and `/account password status NAME`: check for a pending request.
- `/account rename revoke NAME` and `/account password revoke NAME`: cancel a request. Creating another grant replaces the previous one.

Five invalid recovery codes revoke the grant. Attempts have a persisted cooldown, including reconnects. Requests and reminders are private; reminders repeat at most once every 30 seconds. Passwords are entered twice in masked fields, sent through the bounded game packet and hashed by EasyAuth. A successful password change revokes the remembered session; reconnect and authenticate again.

Renaming uses EasyAuth's native forced UUID. Inventory, homes and other UUID-based progress keep the same identity. Previous and new names stay reserved to that protected profile; previous names are not released for another player. The player reconnects after completing the form. Existing launcher names are not silently rewritten.

Private server files under `world/holylois`: `account-requests.json`, `private-recovery/` and `private-account-backups/`. Keep these in protected backups, never in public archives. Exporters read only `account-profile-names.json` (display names and aliases), not requests or authentication records. Statistics retain exclusions across aliases and show one canonical row per profile.

Account rename/password submissions and `/logout` wait for the existing combat cooldown (since 1.8.3). A denied submission retains its grant. Disconnecting during PvP still follows the existing death penalty. In server console, omit `/` from `account rename|password grant|status|revoke PLAYER`; online and offline registered accounts are supported.
