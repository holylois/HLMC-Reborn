# Holy Lois: Reborn

An adventure-focused modded Minecraft survival server for friends: claim land on the map, explore dungeons, earn achievements and Runeforged runes, trade in the auction house and play radio with a boombox. A Windows launcher installs the pack and keeps it updated.

**Launcher 1.4.7 / pack 2.0.4 / Minecraft 26.3 / Fabric 0.19.5 / Java 25**

## Latest update: launcher 1.4.7 and pack 2.0.4

Launcher 1.4.7 fixes Russian and Latvian texts, shows the newest notes in your language and makes the name check calmer. Since launcher 1.4.6 it checks a player name while you type: green means it is free and stays yours on Holy Lois once you join, orange means it belongs to a bought Minecraft account, red means someone already plays with it. Chat Animation got new translations.

The big update before it, pack 2.0.0, brought the Holy Lois Journal (world firsts, your fish, places and creature defeats with waypoints and map links), notable-item cards, Easy Anvils/Magic, the Smelting pickaxe enchantment and more structures in new land. See [CHANGELOG.md](CHANGELOG.md) for everything.

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
