# Holy Lois release history

Historical player notes, retained from the README. Current setup and play instructions are in [README.md](README.md).

## Pack 2.2.1

A small fix for the Holy Lootbox.

**Fixed**

- The Holy Lootbox shows as Legendary everywhere, also in the daily reward screen and the recipe viewer.

## What's new in pack 2.2.0 and launcher 1.6.0

Catch the fish you see, one set of rarity colours for every item and a new /played command.

**Added**

- A bite catches the fish swimming right at your bobber: you land that exact fish, with its size and rarity.
- /played shows your total, active and AFK time, plus time spent fishing and listening to boomboxes.
- Gear on dungeon shelves sometimes comes out as a Runeforged piece.
- The Bell-Keeper's Hook relic gives +1 luck while held, so rarer fish bite more often.
- Every trophy fish now helps while held in either hand: Pondie adds health, Plentifin luck for better catches, Devilfish shortens burning, Stormfish softens falls, and a Pufferfish hurts whoever hits you.
- Launcher: Holy Lois: Reborn appears in Windows Installed apps, so you can remove it from there and choose to keep your data.
- Launcher: Settings is split into sections: Player and launch, Graphics and memory, Help and diagnostics, Shortcuts and links, Advanced.
- Launcher: Help and diagnostics has a Screenshots folder button.

**Changed**

- Every item uses the same rarity colours as fish: Uncommon green, Rare blue, Epic purple, Legendary gold with a shine, Mythic red. Enchanted gear moves up one tier, and Runeforged gear, stones and gems use the same tiers. Alien-Cursed gear and Cursed elites are Mythic, other Cursed gear has its own violet tier, and elite name tags use the same colours. Charged gem weapons are Rare, and a Sealed stone is as rare as the affix sealed in it.
- Legendary, Mythic and Cursed tooltips get gold, red and violet frames, other tooltips keep the plain look, and item names sit centred without the item picture. Epic and better items sparkle on the ground, and pickup cards chime brighter for higher tiers.
- Trophy fish only glint when Mythic or Shiny, and heavy fish look clearly bigger the more they weigh.
- The Journal shows mobs with their Fresh Animations look and idle motion on a bigger preview.
- The Holy Lootbox has a new gold block look.
- 3D Skin Layers 1.11.4 fixes skin textures piling up in memory.
- Fresh Animations 1.11 gives polar bears and pandas full animations, and baby mobs get their own look.
- Crickets chirp near rivers again, and grass sounds better match the ground you walk on.
- Distant Horizons now draws 64 chunks far at medium detail instead of 128, so laptops run smoother, and it no longer updates itself. If you changed these settings yourself, they stay.
- Achievements and the server login screen are in Russian and Latvian too.
- New installs start without update and donation pop-ups from mods, and pressing R while playing no longer reloads shaders.
- Launcher: What changed shows the pack and the launcher as separate entries.
- Launcher: The main window opens larger on big screens and still fits small laptops.
- Launcher: Installing again after a removal shows the first-time setup again.
- Launcher: Pack updates keep your own values in settings files that use sections (TOML), changing only what the pack changed.
- Launcher: Update shows only what it downloads, and Install shows how much space the game takes.
- Launcher: Windows Installed apps shows the real size of the installation.
- Launcher: The launcher update and removal windows use your language.

**Fixed**

- Mining no longer shows a "Run /amber doctor" hint that players cannot use.

## What's new in pack 2.1.0 and launcher 1.5.0

The loud patch: colossal fish, a friendlier claims menu, fair prices and a faster launcher.

**Added**

- Land claims menu overhaul: a search bar, option categories, tooltips that explain every setting and a quick sub-claim menu.
- Colossal Mythic fish: a tiny share of Mythics weigh 100 to 255 kg.
- Launcher: choose how much memory Minecraft gets in Settings, and a free disk space check before every download.

**Changed**

- Heavier trophy fish look bigger all the way up, in your hands, on the ground and in item frames.
- New installs: K opens the Journal and F7 turns shaders on or off. Existing keys stay as you set them.
- Selling: enchanted books and gear count every enchantment they carry, at new lower enchantment prices. Tools, weapons and armor sell for half as much.
- Land of a player who has not played for 30 days goes back to wilderness.
- Free-play names: a bought Minecraft account's name can still be used, but that free-play account is moved to backup when the real owner joins. The launcher asks first.
- Launcher: pack files download several at a time.
- Vein mining no longer breaks blocks in spawn protection or past the world border, and the block that breaks your tool drops its items.

**Fixed**

- Right-clicking with the vein mining key no longer strips or tills blocks your tool cannot change.
- Launcher: a slow connection no longer shows Cancelled, and an unexpected error shows a message instead of closing the app.

## What's new in launcher 1.4.7

Clearer texts in every language.

**Fixed**

- Russian and Latvian release notes for the newest pack now show in your language instead of English.
- The uninstall text no longer calls the app a test launcher, and the repair hint names the real Check files button.
- The name check says "could not check" when Holy Lois does not answer, instead of guessing, and no longer makes the window jump while you type.

## What's new in pack 2.0.4 and launcher 1.4.6

Pick a name with confidence: the launcher now checks it while you type.

**Added**

- Free play name check: green means the name is free and stays yours on Holy Lois once you join, orange means it is a bought Minecraft account's name, red means someone already plays with it.

**Changed**

- Smoother chat animation update with new translations.
- Crash and start help in the launcher now point to Pastor on Discord.

## Quiet updates: pack 2.0.1 to 2.0.3 and launchers 1.4.3 to 1.4.5

Small fixes without a public note: client fixes for the Journal and fishing screens (2.0.1, 2.0.2), updated libraries with a server lag fix (2.0.3, 2026-10-16), and launchers that embed the newer pack and follow the move to the holylois GitHub organization (1.4.3 to 1.4.5).

## What's new in pack 2.0.0

Holy Lois 2.0: your adventure journal, trophy fishing and more dungeons to explore.

**Added**

- My journal records your strongest confirmed creature defeats. Living creatures, including Witches, have rotating previews with Pause and saved gear. Named elite traits stay in the details, with a matching persistent aura around the preview. New world firsts preserve the original defeat. Creature icons use familiar drops; details scroll only when needed.
- Open /journal for your fish collection, visited places and lifetime creature defeats. Search entries and add a personal waypoint or open their recorded location on the map.
- World firsts has its own Journal tab: first discoveries, bosses, elites and the first defeat of each hostile creature type. Passive kills stay in your personal history.
- Fish collections keep separate Heaviest and Rarest catches, with their own model, date and map location. Rarity and Shiny break record ties. Earlier counts and weight records stay intact; missing historical appearances and locations are never invented.
- Earn A Myth on the Line, A Shining Legend and A Shining Myth for your first real Mythic, Shiny Legendary and Shiny Mythic catches. Gifts and command-generated items do not award these milestones. The existing Legendary achievement stays unchanged.
- A quiet Journal notice marks your first fish species, creature type or notable place. Nearby updates combine; repeated catches and defeats stay quiet. Use /journalalerts on or off to choose.
- Notable pickups get a short item card. Use /itemcards on or off to choose whether to show them.
- Easy Anvils and Easy Magic keep items in their blocks and improve repairs and enchanting. Enchantment re-rolls have a cost.
- More mineshafts, ruins, towers, towns and other structures await in newly generated land. Their treasure chests can hold legends and Runeforged loot.
- Smelting is a new pickaxe enchantment, available from enchanting tables and librarian books. Mined iron, copper and gold become ingots, and ancient debris becomes netherite scrap. Fortune stays useful; Silk Touch is incompatible.

**Changed**

- Journal models keep a stable idle pose, spiders fit their leg span, and Witches no longer use their recorded potion. Fish entries preview the heaviest catch in a swimming pose; new catches save Fish of Thieves variants without inventing old appearances.
- Fish and fillets have a thin rarity outline around their inventory picture. Legendary stays gold with a white shine; Mythic keeps its moving colour gradient.
- Fish tooltips omit colour swatches and variant labels. Fish of Thieves fish shrink bite by bite while eaten, and large meals start their eating feedback promptly.
- Fish tooltips separate eaten effects from held bonuses, with catcher/date last. Matching Uncommon pickups merge into older stacks. Treasure maps have a readable name and numbered inscription. New world-first kills preserve their first defeated level.
- Vanilla trophy fish also have useful held bonuses: Cod armor scales with rarity and weight, starting at 10 for Mythic; Salmon movement speed and Tropical Fish swimming. Cooked whole fish retain stronger eaten effects but have half the raw held bonus. Placed boombox notes are half as large; handheld notes are 1.5 times their previously reduced size.
- Wooden, Iron and Golden Crates share the fish rarity palette as Uncommon, Rare and Legendary. Their cards show the name once; loot contents are unchanged.
- Cooked trophy fish give stronger, longer effects; fillets can be eaten even when you are full. Rarer trophy fish take longer to eat.
- Swimming and shoal fish keep their rarity and Fish of Thieves variant when caught. Common and Uncommon stack without weight; Uncommon has short effects and a green outline. Rare and above keep trophy weights. Bigger fish swim in wider circles, natural shoals include vanilla fish, and catches fly from the hook toward you before pickup.
- Explorer maps use the proper holding pose and first-person map view. Held boomboxes sway more gently.
- Held boombox music notes are smaller. Disabled Holy Lois buttons keep the ordinary cursor, and selected Journal tabs are easier to read.
- Empty Journal categories explain how to start a collection. Clipped names have tooltips, and entry dates say what happened.
- World-first discovery names are plain yellow, with a star in the description and a personal firsts filter. Creature icons use familiar drops; long fish details scroll. Refreshing keeps the previous list visible.
- REI's favorite button and left panel are hidden by default without deleting saved favorites. Crate tooltips explain how to place and break them for loot.
- Use /cinematic on or off and /cinematic fishing on or off to control the idle and fishing cameras.
- Shader names are shorter and sorted from light to heavy. Required animation packs stay enabled while your own resource packs remain available.
- The website has a cleaner background, and daily-coins help now explains that coins arrive when you join.
- Updated stable libraries, including Puzzles Lib and Polymer. Your existing keybinds and settings stay yours.

**Fixed**

- Placing a one-item fish back into its slot no longer leaves it stuck on your cursor after a quick double-click.
- Login and registration forms hide the game HUD until the transition finishes.
- The Journal no longer gets stuck after a resize or quick filter change. If the server does not respond, Retry lets you try again.
- Delayed Journal replies no longer reopen a closed menu or replace newer results.
- Fish and item cards remain visible over the cinematic camera; /cinematiccards on|off is your choice. Journal notices wait until visible, then show quiet outlined text near chat. Use /journalalerts motion off to stop their pop and Journal text shine.
- Uploaded song links must contain real MP3 or WAV audio. BlueMap's updated renderer fixes lost low-resolution tile writes.

## What's new in pack 1.9.4

A fishing cinematic with real camera work, and boombox music without anything playing over it.

**Changed**

- Minecraft's background music pauses while boombox or music disc music reaches you, like it does for a jukebox.

**Fixed**

- While fishing, the cinematic no longer repeats one shot on a loop: every shot is a new angle on you and your bobber until a fish bites, then it stays on the catch until you reel it in or it gets away, and changes angle 3 seconds after you reel in.
- The cinematic no longer starts its own soundtrack over a playing boombox or music disc, so that music plays clearly in your ears.

## What's new in pack 1.9.3

The carried boombox swings the right way and its notes come out of the speakers.

**Changed**

- Notes from a carried boombox now pop out of its speakers, low at your hand, instead of floating up by your hip.

**Fixed**

- A carried boombox swings out from your body and back in, like a real weight on a handle, instead of forward and out.

## What's new in pack 1.9.2 and launcher 1.4.2

Boombox music now plays in your ears during the cinematic camera.

**Changed**

- With a boombox or music disc playing nearby, stand still for a minute: the cinematic camera fades in and the music moves into your ears, then back to the speaker when you move. Just standing close no longer does it.

**Launcher 1.4.2**

- Fixed: updating no longer asks you to close Minecraft when only another Java program is open, and no longer gets stuck waiting for it.
- Changed: What changed now sorts every release into Added, Changed, Fixed and Removed.

## What's new in pack 1.9.1

Boombox music right in your ears, your death loot back in its slots and a smarter cinematic camera.

**Added**

- Pick up your death loot and every stack goes back to its old slot, armor and off-hand too, if that slot is still free.
- Food shrinks bite by bite while you eat, Farmer's Delight meals included.
- Stand still for a minute while a boombox or music disc plays nearby and the cinematic camera fades in.
- Standing right next to a playing boombox or music disc plays the music in your ears instead of from the speaker.

**Changed**

- The boombox in your hand pulses with the music and only sways side to side. Notes hop out sideways, bigger when the music is louder, and never in your first-person view.
- The cinematic camera stays out of walls, films you instead of cave walls, and stays on you while you fish.
- The idle cinematic waits 15 minutes on a fresh install too, instead of 30 seconds.
- The Holy Lootbox tooltip is short: what it is and which key opens it.
- Cancel buttons are grey, so only the dangerous choice is red.
- The Tab list is tidier, with lines of even width.

**Fixed**

- Invisible item frames in dungeons no longer drop a spare frame when you punch the loot out.
- A chest you had open no longer looks open when you come back after a teleport.
- A boombox in your off hand is no longer placed by accident.
- R on an empty slot sorts without opening a recipe.
- Respawning no longer fades in through the panorama.

**Removed**

- /spawn: Holy Lois is an open world without a spawn hub.

## What's new in pack 1.9.0

Homes, parties, trophy fish you can see and a fresh new look. `/homes` manages your three starter homes, `/party` or `/group` manages your party with wide health bars, and a rally card can request travel to its author. Trophy fish look as big as they weigh, 10 kg and up are carried over your head, and the new Mythic fish is 40 kg and up. Joining is one smooth scene from our title panorama to the world, the day-7 Holy Lootbox is its own gold block, armor looks 3D, and Enter works in every form again. Launcher 1.3.2 is unchanged and installs the update. The [player guide](PLAYER-GUIDE.md#pack-190-homes-parties-and-equipment) has the details.

## What's new in launcher 1.4.1

- Gold now marks only what matters most: the main button, your current state and the newest update. Keys, commands, land and gift tips use quiet text colors.
- The built-in help no longer lists /spawn: Holy Lois is an open world without a spawn hub.

## What's new in launcher 1.4.0

- One big button follows what you need: Install, Update, Repair or Play, with progress and status right under it.
- The two ways to play are now called **I own Minecraft** and **Play with a name**. Your account card shows your name and, once you have played, your skin head.
- The main screen shows the latest update with a picture and the most used keys and commands.
- New players get a short three-step setup with real server screenshots. Settings are grouped, the built-in help is current, and the old 3D armor switch is gone.

## What's new in pack 1.8.3 and launcher 1.3.2

- Launcher setup keeps shortcut options reachable while entering your name.
- Quick start accepts valid player names without a Mojang ownership lookup; existing Holy Lois names still need their server password.
- Admin-requested private forms let players change names without losing progress or recover a forgotten server password.

## What's new in pack 1.8.2

- Party members are protected from friendly fire, with an optional health and food panel.
- Use /rally to share a meeting point with your party for 90 seconds.
- Daily supplies appear in a clear reward card, with daily coins claimed through their existing reward system.
- Voice chat can recover its connection after login; /voicefix requests another attempt.
- Cleaner login messages and matching release news across the website and launcher.

## What's new in pack 1.8.1

- Placed relics keep their name and lore.
- Fishing crates give their proper enchanted rewards.
- Bows, maps and fishing rods work better with the first-person body view.
- Combat teleports and land protection behave more reliably.
- Login and registration quiet world sounds.
- At most two placed boomboxes play per chunk, with six streams across the server.
- Your selected server skin appears on your statistics head.

## What's new in pack 1.8.0

- Catch ten kinds of fish in different waters, weather and times of day.
- Fish range from Common to Legendary in size. Rare catches keep their weight and your name as trophies.
- Reel in loot crates, messages in bottles and buried treasure maps.
- Find named relics in dungeon, tavern and town chests. Complete their sets to earn achievements.

## What's new in launcher 1.3.1

- Handmade server-list icon, matching the refreshed website and BlueMap branding. No gameplay changes.

## What's new in launcher 1.3.0

- **Fast start**: press Play and Minecraft opens straight from the Holy Lois launcher with your player name. No SKlauncher. Java 25, Minecraft and Fabric come from Mojang and Fabric, are checked by hash and are reused from another launcher on the PC when it already has them. A start window shows each step; if the game crashes, the launcher comes back with a report you can copy.
- **Join Holy Lois on start** for everyone, also for bought accounts in Minecraft Launcher. Turn it off in Settings for singleplayer.
- **Player names** with history: a new name is a new player on the server, so the launcher warns first, keeps every earlier name one click away and allows three new names a day. A name that belongs to a bought Minecraft account is refused.
- Pack stays 1.7.11, no server restart.

## What's new in pack 1.7.11

- **Quick Play is removed.** In testing it never joined the server by itself, so Play did the same as the old way. **Launcher 1.2.7** drops the setting: Play opens your Minecraft launcher, then you join from Multiplayer (singleplayer works as before). Holy Lois Extras 1.5.1 no longer contains the Quick Play part.
- ~~Coming later: Integrated start~~ (arrived as fast start in launcher 1.3.0).
- No server restart for this release.

## What's new in pack 1.7.10

- ~~Quick Play~~ (removed in 1.7.11, it never joined by itself).
- **Launcher 1.2.6** closes Minecraft and its launcher for you when an update needs it, after you press **Agree**. Greener Play button, new icons for the launcher and the Minecraft window.
- **AFK time no longer counts as playing**: achievements, land claims, leaderboards, stats and the Tab list skip it (Essential Commands decides who is AFK; it starts counting from this release).
- **Secret code**: a code of the day hides somewhere on holylois.com. `/redeem CODE` in game gives one prize per player per day.
- **Quieter owner**: no join, leave, AFK, advancement or discovery notices for the server owner; deaths still show.
- **Calmer world generation**: the terrain job works in short slices with rests, so the server does not fall behind while the border grows.
- **Rules**: rule 3 says to play with the launcher's mods and nothing else (the mod check from 1.7.8); shaders and resource packs stay your choice as long as they are not x-ray.

## What's new in pack 1.7.8

- **One pack for everyone**: the server checks the mod list when you join. Extra mods are turned away with a message that says how to fix it; shaders, resource packs and your own settings stay yours. The launcher's **Play** button moves extra mods out of the Holy Lois folder (kept in a quarantine folder, never deleted), repairs changed pack files and switches the pack's resource packs back on.
- **New crown icon**: the Minecraft window and taskbar icon is the Holy Lois crown, crisp at every size, and the server list has a new icon.
- **Clearer achievements**: new texts for Discoverer, Dungeon Delver, Deeper Still and Odd Pillar.
- The server restarts once (a one-minute countdown first).

## What's new in pack 1.7.7

- **Fixes from the 1.7.6 test**: the first-person body may sink into a wall a little, the camera is lifted in bed so your eyes are not inside your head, and the tool swap line reads "Switched to ...".
- **Dynamic lights follow your shader setting**: with a shader pack on, the shader lights what you hold and dropped torches and mobs still glow; with shaders off, dynamic lights are fully on again.
- No server restart for this one.

## What's new in pack 1.7.6

- **Dungeons**: every underground dungeon (small, medium and large, in plains, ice and sand styles) and every obelisk is announced when someone first finds it, with new achievements: Dungeon Delver, Deeper Still, Dungeon Master and Odd Pillar. Their chests can drop Runeforged runes.
- **Boombox**: it now reaches from 16 blocks on volume 1 up to 48 blocks on volume 10.
- **Tools**: a broken tool is replaced by an unenchanted spare of the same kind, lowest material first. Your enchanted tools are never swapped in for you.
- **Fixes**: **R** on an empty slot sorts without opening a recipe, the first-person body steps forward when a wall is behind you and hides while you sleep, and with a shader pack on torches light yellow (dynamic lights pause while shaders are on).
- **Mods**: all Holy Lois mods now show the logo, author and links in Mod Menu.

## What's new in pack 1.7.5

- **Boombox**: sneak + scroll changes its volume (1-10, louder reaches further), music notes float while it plays, and six new stations: dubstep, drum and bass, trap, lo-fi, hardstyle and techno.
- **Smarter keys**: **R** on an item shows its recipe, **R** on an empty slot sorts. A broken tool is replaced by the same kind, cheapest first, with a soft chime. Enchantment descriptions show while you hold Shift.
- **Homes and portals**: with several homes, `/home` goes to the one named `home`; `/Home` works too. Walking back through a Nether portal takes you to the portal you came from. Clicking a command in chat runs it without the confirm screen.
- **Bigger world**: the border is 20,000 blocks wide. New land is prepared while the server is empty, and `/structures` tells you what you are standing in.
- **Polish**: no flickering lines between glass blocks with shaders, a crown window icon, 30 FPS in the background, and a launcher that shows new updates in a gold card with an Update now button.
- **Correction**: the world map opens with **J** (the 1.7.4 notes said M).

## What's new in pack 1.7.4

- **Land on the map**: press **J** for the world map, right-click a chunk and claim it (Open Parties and Claims replaces Flan). 16 chunks are free, playtime earns more and `/claims buy` adds extra ones for coins. Teams with `/oparties`.
- **Zone titles**: entering a new biome or someone's land shows its name at the top of the screen, or Wilderness.
- **Fair fights**: logging out mid-fight kills you; PvP deaths leave the loot for the winner with no death marker. `/rtp` never drops you into or next to someone's land.
- **Help**: `/support MESSAGE` reaches the owner on Discord right away, `/report PLAYER REASON` for player problems, `/donate` for the wallets.

## What's new in pack 1.7.3

- **Hotfix**: achievement tabs switch with a left click (1.7.2 broke them), a placed boombox shows its real texture instead of a pink cube.
- **Text**: game and mod text uses plain hyphens; `/support` lists TRON, labels Bitcoin SegWit and explains each network on hover.

## What's new in pack 1.7.2

- **Boombox**: set it down on any block and it keeps playing for everyone nearby. Game music pauses while one plays near you.
- **Fixes**: achievement tabs switch again with Num Lock on, Holy Lois comes first, one enchantment description instead of two.
- **Daily coins** get a [Claim] button at login, seven new achievements, and `/support`.
- **Defaults**: the recipe list shows only while you search, plain tools are used until they break, the first-person body sits a bit further back.

## What's new in pack 1.7.0

- **Boombox**: a portable speaker that plays internet radio to everyone nearby through voice chat.
- **Daily gifts**: a small gift every day you log in, and a **Holy Lootbox** every 7th day in a row.
- **Achievements**: a Holy Lois advancement tab with secret challenges such as Grand Tour and Five-Star Chef.
- **Auction house**: `/ah`, `/sell`, orders and `/pay` with server coins.
- **Recipe lookup** with Roughly Enough Items, and descriptions for every modded enchantment.
- **Macaw's Holidays**: Christmas trees, lights, garlands, candy canes and Halloween decorations, plus gifts and fireworks on Latvian holidays.
- **Tab leaderboards**: diamonds, ancient debris, playtime, mob kills, blocks mined and more, a new board each time the page comes round.
- **Discoveries**: the first visit to a big structure (Ancient City, Tavern, Illager Manor, any dungeon and many more) is announced to everyone.
- **After death**: chat shows where you died, and the minimap death point disappears when you get there.
- **Looks**: framed rarity tooltips, held torches light up the area, falling leaves, connected glass, effect timer bars and shulker box previews.
- **Fixes**: J opens the world map again, no more chest flicker with shaders, no key clashes, and real chunks load further out before the distant view takes over.

## What's new in pack 1.6.x

- **Farmer's Delight** cooking: knife, cutting board, cooking pot, burgers, sushi rolls, pumpkin slices and new crops.
- **Macaw's Furniture**: chairs you can sit on, tables, drawers, wardrobes and kitchen cabinets.
- **Xaero's Minimap and World Map** (J opens the map, M stays voice mute) and **Jade** block info.
- **Dungeons and Taverns** and **Towns and Towers** in newly explored land, with Runeforged loot in their chests.
- **Custom music discs** with `/audioplayer`, played through voice chat.
- Hold **Tab** for live server stats, Latvian name days and leaderboards. Right-click ripe crops to harvest and replant. One sleeping player skips the night.
