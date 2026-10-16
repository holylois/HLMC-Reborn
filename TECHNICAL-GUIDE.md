# Holy Lois: Reborn - technical reference

Use [ADMIN-GUIDE.md](ADMIN-GUIDE.md) for the current simple owner workflow. This reference preserves earlier manual release and implementation details; version examples describe historical releases.

Your CurseForge profile is the workshop. GitHub Releases are the delivery point. Friends use Holy Lois to check and install the signed release. Editing your local mods folder does not publish those files automatically.

## Your folders

Example paths use `%USERPROFILE%`. Configure your SSH host and user privately, never in published source.

| Purpose | Location |
| --- | --- |
| Edit and test the client pack | `%USERPROFILE%\curseforge\minecraft\Instances\Holy Lois Reborn` |
| Launcher source and owner tools | This guide's folder, alongside `maintainer` |
| Server JAR staging | `%USERPROFILE%\Downloads\server-mods` |
| Running server | `/opt/minecraft` on your server |
| Pack releases | <https://github.com/holylois/HLMC-Reborn/releases> |

Keep the publisher's `private/release-private.pem` and your SSH key private. Neither belongs in GitHub, Discord, a client pack or a friend-facing installer.

## First practice: install Chat Animation yourself

This is the one requested mod left for you to install. It is client-only and needs no additional dependency beyond your existing Fabric setup.

1. Close Minecraft.
2. Open the [verified Chat Animation 26.3 Fabric download](https://modrinth.com/mod/chatanimation/version/zbvXFs0t).
3. Download `chatanimation-fabric-1.3.3+mc26.3.jar`.
4. In CurseForge, open **Holy Lois: Reborn**, use **Open Folder**, then open `mods`.
5. Put that JAR in `mods`. Do not unzip it. Do not put it on the server.
6. Launch the profile, join and open chat. Confirm the animation works.
7. Close Minecraft. Follow the release steps below to deliver it to friends. They do not need to copy the JAR manually.

The verified SHA-256 is `a4c44eeaecaabddbf650f293d5dbe4a244daf4a5e864cd242b53ced6d18844fb`.

## Add or update a mod

1. Close Minecraft before changing files.
2. Choose a file explicitly supporting **Minecraft 26.3 and Fabric**. A project's general version list is not enough. Keep Java 25 and Fabric Loader 0.19.5 unless a tested change requires otherwise.
3. Check the download's required dependencies and whether it is client-only, server-only or required on both. Native libraries must support Windows x64 on clients and Linux ARM64 on this server.
4. Add it to the CurseForge test profile with its dependencies. Keep one version of each mod. Move replaced JARs into a backup outside `mods`.
5. Launch and test the actual feature. Also test shaders, a resource reload and a server reconnect for rendering mods. If gameplay changes, test in a separate world first.
6. For mods required on both sides, deploy the server part before publishing the client release. Client-only interface/rendering mods stay off the server. Server-only administration mods stay out of the client release.
7. Prepare and publish a new pack version. Friends see an update when Holy Lois next checks, normally within two minutes while it is open.

Do not click Update All and immediately publish. A later version may change game-version support or dependencies. Paper plugins cannot run in Fabric's mods folder.

## Prepare a client release

Open PowerShell in this guide's folder. Run:

```powershell
& .\maintainer\Prepare-Pack.ps1 -Version 1.4.2
```

Use a new higher version every time, for example `1.4.2`, then `1.4.3`. The helper uses your CurseForge profile, the existing reviewed defaults and the private signing key. It writes `publish\pack-VERSION\pack.json`, `pack.json.sig` and `defaults.zip`.

The publisher finds new files by their hash in Modrinth metadata, checks final 26.3 Fabric release compatibility and records the author's download URL. Known reviewed files keep their original download URLs. It does not upload all mods to your repository. A file with no verified match, an unreviewed alpha, or an incompatible build stops preparation. Review that file instead of disabling validation.

Our current Better Advancements and Remove Reloading Screen files are explicitly reviewed alpha mod releases for final Minecraft 26.3. Their exact hashes and URLs are curated in the base manifest. This approval does not automatically approve later alpha builds.

Changing the mods or shaders needs a new pack release, but does not require rebuilding the launcher EXE. Changing launcher behavior or its embedded starting pack does require rebuilding and publishing the app.

## Publish the prepared release

1. Sign in to your [GitHub releases page](https://github.com/holylois/HLMC-Reborn/releases).
2. Choose **Draft a new release**. Create a new tag `pack-v1.4.2`, substituting your version.
3. Give it a clear title, such as `Holy Lois: Reborn - Pack 1.4.2`, and short notes describing changes and any required server update.
4. Upload `defaults.zip`. Any Holy Lois-owned helper JAR referenced by this release must also exist at its exact versioned URL. Third-party JARs remain at their authors' URLs.
5. Set the release label to **None**, then publish. Keep the launcher release marked **Latest**, because the small installer uses the app catalog from Latest.
6. Test the immutable assets. Then edit the existing **pack-stable** release. Replace both `pack.json` and `pack.json.sig` with the new pair and save. Keep its label **None** too. Do not mix versions of those two files.
7. Open Holy Lois and check for updates. Test a fresh installation and an existing installation. Confirm the version, server entry, resource packs, shader-off initial default and preservation of personal settings.

GitHub upload/release preparation is an explicit owner action. Files are not published merely because you add them to CurseForge. This lets you test before friends receive them.

For repeat releases, the optional `maintainer\Publish-Pack.ps1` automates those GitHub release steps through the official GitHub CLI. Install the CLI from <https://cli.github.com/> and run `gh auth login` yourself once. After testing a prepared release, run `& .\maintainer\Publish-Pack.ps1 -Version 1.4.2 -Publish`. Without `-Publish` it only previews the plan. This helper is provided for future use; the current release was published and checked through the signed-in browser.

Never edit the content of an already released pack version. If a release is faulty, publish a new higher version containing the last good content. The updater intentionally rejects version rollback and changed content under the same version.

## Change shared defaults safely

The release's `assets\defaults.zip` contains reviewed files under `config/yosbr/`. YOSBR applies them where the destination settings are missing. Existing friends keep their preferences.

To change defaults, close Minecraft and review just the settings you intend to share. Update the corresponding files in a temporary copy of the ZIP, preserving its directory layout, then test a fresh import. Shared starting values include shaders off, normal render distance around 10-12 and DH distance 64. Your personal DH distance can be higher.

Do not copy your whole config folder blindly. Exclude voice device files, account/launcher files, auth databases, passwords, personal waypoints, worlds, screenshots, logs and DH caches. The publisher checks ZIP paths and excludes voicechat configuration; privacy still needs your review.

Shader `.zip.txt` settings are personal files alongside shader packs. They are not automatically captured by the publisher. Set intended shader defaults through a reviewed supported defaults path or document the menu choices. Merely adding a shader ZIP does not enable it.

## Use the separate server admin tool

From PowerShell in this guide's folder:

```powershell
& .\maintainer\Server-Admin.ps1
```

Choose Status, Start, Stop, Restart, Logs, Check staged mods, or Back up and install staged mods. You can also run direct actions:

```powershell
& .\maintainer\Server-Admin.ps1 -Action status
& .\maintainer\Server-Admin.ps1 -Action restart
& .\maintainer\Server-Admin.ps1 -Action check
& .\maintainer\Server-Admin.ps1 -Action update
```

For an update, put only reviewed server JARs and their dependencies in the server staging folder first. Keep one version of each staged mod. The tool rejects client-only mods and files without Fabric metadata. It hashes the files, uploads a unique staging folder, and checks the server's replacement plan before installation.

An update stops the managed service, verifies no manual `server.jar` remains, checks free space, creates and checks a stopped-server archive of the worlds, authentication data, permissions, claims, configs, mods and launcher, replaces only the staged mod IDs, starts the service and waits for a new **Done** message. Existing scheduled backup archives under `backups` are excluded to avoid copying those backups inside every new backup. If startup fails, it restores the previous JARs and retains the stopped-server backup. World files are preserved. The command is a mod update and restart, not a world reset.

The tool retains the latest two complete maintenance archives under `/opt/minecraft-backups/maintenance`. Scheduled JEB backups have their own retention. Uploaded staging folders and small replacement receipts are retained for review; remove reviewed stages periodically. Historical backups made before this tool are not deleted automatically.

A failed update may have changed a mod's data before startup failed. Inspect logs and use the complete backup for recovery if necessary. Restoring an entire server directory is a separate, stopped-server operation. Do not restore over a running world.

## Fresh PowerShell: connect and manage Minecraft

Run this in **Windows PowerShell**:

```powershell
ssh -i "$env:USERPROFILE\.ssh\id_ed25519" SSH_USER@SERVER_HOST
```

After connecting, these commands belong in the **Ubuntu shell**:

```bash
sudo systemctl status minecraft --no-pager -l
sudo systemctl start minecraft
sudo systemctl stop minecraft
sudo systemctl restart minecraft
sudo journalctl -u minecraft -n 100 --no-pager
sudo journalctl -u minecraft -f
df -h /
sudo du -sh /opt/minecraft/world /opt/minecraft-backups
exit
```

Run only the command you need. `Ctrl+C` leaves a live journal view without stopping Minecraft. `exit` disconnects SSH; an active systemd service stays running. Minecraft player commands such as `/rtp`, `/tpa NAME` and `/home set base` belong in **Minecraft chat**, not the Ubuntu shell. Do not start a second manual server against the same world.

## Backups and disk space

JEB is configured for differential backups every 10 minutes and full backups every six hours, with twelve differential and two full retained, an approximately 8 GB budget, a 2 GB free-space reserve and scheduled idle skipping. Required dependency chains are retained. A size limit can stop new backups when removing old data would break a chain.

Old backups are rotated, but storage can still fill through world exploration, DH caches, logs, manual archives or uploads. Check `df -h /` periodically and confirm completed backups with `/jeb list`. The maintenance tool's complete archives have a separate two-archive retention. Copy important complete archives off the VM. Never distribute them to players because they include authentication and other private server data.

## Keybinds from new mods (launcher 1.2.0)

`options.txt` keybinds stay personal on update. Launcher 1.2.0 adds one exception: a `key_` line that first appears in this release's shared `config/yosbr/options.txt` is added to a player's options once, only if they have no line for that control and no other control already uses the key. Pack 1.6.0 uses this for Xaero's map keys. Keys already used by F3 debug combos count as taken.

## Current server behavior

- Real player cap: 20. Server-list display: online players plus one available spot. This display does not increase server capacity.
- First characters receive a random location after authentication. Returning players keep their position. `/rtp` is limited to the pregenerated area with a margin.
- Ordinary friends have survival teleport/home/claim/shop/skin access, not administrator powers. Three homes per player. Keep the owner as the only operator.
- Premium identity is preserved. New offline users register with a password of at least five characters and no spaces. Premium-reserved and already registered accounts have ownership checks.
- Voice requires the client mod and UDP 24454. A red disconnected plug means no server voice connection; a muted microphone is a separate state. Press V for each player's own devices and test with another person.
- RTP pregeneration and DH LOD generation are different jobs. Do not run heavy Chunky and DH generation together on this two-core VM.

## Shaders and Distant Horizons

The supplied crash reports point to Iris lazily uploading the enchanted glint texture while a render pass is already open. The small Holy Lois Glint Preload client helper loads those textures at the beginning of a client tick. The owner tested Reimagined and other shaders successfully afterward. This is a targeted local workaround, not an official Iris bug-fix release or a guarantee for every shader.

Shared installs still start with shaders off. If a new rendering problem appears, close Minecraft and use Holy Lois's **Disable shaders** button, then test one change at a time.

The DH overlap setting is now `overdrawPrevention="0.9"`, and biome blending is reduced to 1 to lower LOD loading work. The owner reported faster loading. Coarse distant models can still briefly appear after a long teleport before detailed terrain arrives. Client logs also recorded terrain-download retries; those are separate from the Iris crash. Increasing DH distance is not a fix for download delays.

DH fog is set to start later and be lighter: start 0.75, end 1.4, density 1.0. Complementary's own atmospheric fog is a separate setting: in Shader Pack Settings, find Atmosphere/Fog Settings and increase Fog Distance. The tested Reimagined and Unbound settings use `ATM_FOG_DISTANCE=200`. Euphoria can have its own generated shader-settings file.

## What to test after each release

Join with a non-operator account, try home/TPA/RTP, claim protection and shops. Test Visual Workbench with another player, the advancements screen and plaque popup, inventory shortcuts, resource-pack reloading and shader gameplay with an enchanted item. Confirm a new completed backup and verify the update on both a fresh and an existing client installation.

Avoid adding more rendering or world-generation systems until this release is stable. spark and Ledger are already installed for diagnosis and rollback. New world-generation mods affect new chunks and must be chosen before any further pregeneration.

## Launcher 0.4.0 startup and first setup

The public catalog stays `holylois-app-v1` so installed 0.3.x checkers can upgrade without a replacement installer. Every new main app embeds its matching native checker. Before showing the main window, it installs those trusted bytes atomically, waiting briefly if the previous checker still holds its executable open. A direct main-app launch hands off to the checker, which checks the signed catalog and starts the verified app. Owner arguments survive this handoff.

Downloads are bounded HTTPS streams and verified by pinned RSA-PSS and SHA-256. Numeric version rollback and replacement content under the same version are refused. A network/service failure may use the last locally signed catalog; signature failure on an available release is not treated as an offline fallback. Cached application bytes are checked again before execution.

The new checker never creates shortcuts. First setup records the player's launcher and separate Desktop/Start menu choices in `setup-completed.json`. An old shortcut marker or existing player settings migrates without creating missing links. Cancelling setup writes no completed receipt. Later launches never recreate deleted or customized links.

Setup includes the owner-supplied launcher artwork, English default, Russian and Latvian, and a centered dark window. Launcher authentication remains in Minecraft Launcher or SKlauncher. Source builds require the official llvm-mingw toolchain before WPF compilation because the checker is an embedded resource.

## Auth UI and server helper 1.2.0

Pack 1.5.2 contains the client-only `holylois-auth-ui-1.0.1+26.3.jar`. The server-only onboarding helper sends an authoritative S2C status only to clients advertising that channel. Password submission uses the existing EasyAuth Brigadier command and its packet policy; no custom C2S auth bypass is installed. The payload contains a mode and minimum length, never an account password, hash or IP.

The form masks text and narration, clears input on submit/exit/state changes and never writes credentials. Each distinct screen state gets a new Screen instance to invalidate Minecraft's GUI draw cache. Arrival is a plain black screen with centered text. EasyAuth's server-side restrictions also protect clients without the UI; those clients retain chat commands.

First-registration placement retains a 30-tick black-screen hold after teleport and a 100-tick temporary damage guard. No-bed death respawns are queued from AFTER_RESPAWN only when vanilla clears the respawn config. Valid beds/anchors and living End returns retain vanilla behavior. The existing EasyAuth 86400-second session was preserved.

Sources live in `addons/auth-ui` and `addons/onboarding`. Compile against the exact Minecraft 26.3, Java 25, Fabric Loader 0.19.5 and Fabric API classpath. Onboarding also requires EasyAuth 3.4.4. These addons are specific to those installed APIs. Deployment must stop the service and preserve the complete backup first.

Rebuildable DH SQLite, WAL and SHM caches are excluded from scheduled backups for all three vanilla dimensions. The full and differential integrity/restore checks verified 286 files in a separate folder. The live world was not replaced. Off-VM backup copies are still an owner task.

The client mixin cancels only the `download.pack.title` progress toast on Holy Lois. The `download.pack.failed` toast remains visible. Routine EasyAuth reminders and the repeated insecure-server popup are suppressed only on Holy Lois; authentication errors, welcome text and chat validation remain active. Full-pack runtime checks verified progress suppression, visible failures and unchanged progress on other servers.
