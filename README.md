# Holy Lois: Reborn

A player-run modded Minecraft survival server: claim land on the map, explore dungeons, earn achievements and Runeforged runes, trade in the auction house and play radio with a boombox. A Windows launcher installs the pack and keeps it updated.

**Launcher 1.6.2 / pack 2.2.0 / Minecraft 26.3 / Fabric 0.19.5 / Java 25**

## Latest feature update: launcher 1.6.0 and pack 2.2.0

Catch the fish you see: when a wild fish swims right at your bobber as it bites, you land that exact fish. Every item now uses the same rarity colours as fish, from Uncommon green to Mythic red, with gold, red and violet tooltip frames for Legendary, Mythic and Cursed gear, and sparkles and brighter pickup chimes for the good stuff. Trophy fish help in either hand, the Bell-Keeper's Hook relic gives +1 luck for rarer fish, and `/played` shows your time online, fishing and listening to boomboxes. Launcher 1.6.0 splits Settings into sections and appears in Windows Installed apps.

The update before it, pack 2.1.0, brought colossal Mythic fish up to 255 kg, a friendlier land claims menu and fair selling prices. See [CHANGELOG.md](CHANGELOG.md) for everything.

## Download and play

[Download HolyLoisReborn.exe](https://github.com/holylois/HLMC-Reborn-Packaging-Lab/releases/latest/download/HolyLoisReborn.exe) - about 66 MB, for Windows x64. Its runtime is included, so no separate .NET installation is needed.

1. Open the EXE. The three-step setup asks how you play: **Play with a name** (type the name you want in the game) or **I own Minecraft** (you bought Minecraft), then your optional Desktop and Start menu shortcuts.
2. Close Minecraft and your Minecraft launcher, then click **Install** beneath the logo.
3. The same button becomes **Play**. With **Play with a name**, **fast start** opens Minecraft straight from the Holy Lois launcher (the first start downloads Java and Minecraft once) and the game joins Holy Lois by itself. With **I own Minecraft**, Minecraft Launcher opens: select **Holy Lois: Reborn** and press Play, and the game joins Holy Lois by itself too.
4. The server is **play.holylois.com** (**mc.holylois.com** works too) and is already saved in Multiplayer. Website: https://holylois.com, Discord: https://holylois.com/discord

SKlauncher is no longer needed. Players who already use it keep their name, worlds and settings, and **Settings** can switch Play back to opening SKlauncher. **Settings** also has the player name with its history, **Join Holy Lois on start** (turn it off for singleplayer) and **Help and diagnostics** for a crash report to send on Discord. English is the default, with Russian and Latvian available on the main screen.

See the [player guide](PLAYER-GUIDE.md) for joining, voice chat, maps, cooking, furniture, homes, teleporting, claims and shops.

## Updates

Open Holy Lois whenever you want to check for updates. The app checks for its own updates before opening the main window, so you do not need another installer. Pack updates are checked on opening and every two minutes while the app is open. Close Minecraft and its launcher before installing an update.

After installation, you can also open the saved pack directly in Minecraft Launcher or SKlauncher. Return to Holy Lois to receive new pack versions.

Updates preserve worlds, personal voice-device choices and extra client mods or shaders. Changed shared defaults apply once per new pack version; unrelated preferences remain. **What changed** lists release history. Deleted shortcuts stay deleted. **Settings > Clear completed downloads** removes verified duplicate downloads and shows the space recovered; the working app, rollback copy and game data are retained.

## For the owner

Use **Holy Lois Admin** to choose your tested CurseForge profile, prepare a new version, deploy server-required changes and publish the update. Follow the [admin guide](ADMIN-GUIDE.md); use [technical notes](TECHNICAL-GUIDE.md) for the detailed workflow and [test guide](TEST-GUIDE.md) before promotion. The trusted-friends setup does not need an additional anti-cheat addon.

This repository holds the signed pack channel and admin documentation. Current launcher source and app releases live in the [launcher repository](https://github.com/holylois/HLMC-Reborn-Packaging-Lab). Its [setup and reset guide](https://github.com/holylois/HLMC-Reborn-Packaging-Lab/blob/main/RESET-AND-TEST.md) covers clean installation tests and app removal. Use the launcher repository to build the current player app. The legacy companion source archive remains historical; current launcher and add-on source lives in the launcher repository.

## Release and privacy notes

The app has no Windows publisher certificate, so SmartScreen may display **Unknown publisher**. Antivirus results can differ between computers. Historical installer notices are kept in [SECURITY-NOTICE.md](SECURITY-NOTICE.md); privacy and source-sharing rules are in [PRIVACY.md](PRIVACY.md).
