# Playing Holy Lois: Reborn

Guide for pack 1.9.4 and launcher 1.4.2. Start with the [download and setup steps](README.md#download-and-play). The server is already saved in Multiplayer (**play.holylois.com**, **mc.holylois.com** is an alias).

Click **Play** in the Holy Lois launcher. With a player name, Minecraft opens straight from the launcher and joins Holy Lois by itself. With a bought Minecraft account, Minecraft Launcher opens: pick **Holy Lois: Reborn**, press Play, and the game joins by itself too. For singleplayer, turn off **Join Holy Lois on start** in Settings.

If the game does not start or crashes, the launcher shows what happened. **Settings > Help and diagnostics** copies a report (your Windows user name, login details and IP addresses are removed) to send to pjampjam on Discord.

## Joining

Offline accounts see a centered registration or login form. Register with a server password of at least five characters, without spaces. Use a separate password from your Minecraft account. Your login is remembered for **24 hours on the same IP**. Verified premium accounts skip the form.

On your first registration, wait for the arrival screen to finish while the server finds a safe starting location. You can press Escape to leave if needed.

## Voice and controls

| Key | Action |
| --- | --- |
| **V** | Choose your microphone, output device and voice settings. |
| **Hold Caps Lock** | Talk to nearby players. |
| **Page Down** | Switch between full-body and classic hand view. |
| **Tab** | Player list with your ping, server TPS and uptime, playtime, the day, server location, Latvian name days and leaderboards. |
| **J** | Open the world map. |
| **Y** / **Z** | Minimap settings / larger minimap. |
| **U** | Uses for the hovered item in inventory; waypoint list in the world. |
| **R** | Recipes for the hovered item; sort inventory on an empty slot. |
| **'** | Party and claims menu. |
| **M** | Mute your microphone (unchanged). |
| **C** | Zoom. |
| **Hold `** (left of 1) | Mine the whole ore vein or tree while breaking a block. The HUD shows how many blocks will break. |

Map keys are added only where the key was free, and Holy Lois fixes known clashes when the pack updates. If one does nothing, open **Options > Controls > Key Binds**: the search bar and the conflict filter show what shares a key. Jade shows a small label for whatever you look at, including crop growth.

If your body clips through the view, press **Page Down** to use the simpler view while keeping animated arms. Shaders start off; choose a supplied shader in Minecraft's video settings when ready. **Disable shaders** in Holy Lois is available if rendering causes trouble.

## Homes

Use a name such as `base` for a saved location. Replace it with your own home name.

| Command | What it does |
| --- | --- |
| `/home set base` | Save your current location. |
| `/home tp base` | Return to that location. |
| `/home list` | Show your saved homes. |
| `/home delete base` | Remove that saved home. |
| `/home` | Go to your only home. With several, it goes to the one named `home` (save it with `/home set home`), otherwise it lists them to click. |

Home names that differ only in capitals (`Home` and `home`) count as the same name. Clicking a command in chat, such as a home in that list or a tpa accept, runs it right away. These are the pack's [Essential Commands home commands](https://github.com/John-Paul-R/Essential-Commands#commands).

## Teleporting

Replace `NAME` with the player's name.

| Command | What it does |
| --- | --- |
| `/tpa NAME` | Ask to visit a player. |
| `/tpaccept NAME` | Accept that player's request. |
| `/tpdeny NAME` | Decline that player's request. |
| `/rtp` | Find a safe new place, never in or next to someone's land. Stand still for 3 seconds; five-minute cooldown. |

The request commands come from [Essential Commands](https://github.com/John-Paul-R/Essential-Commands#commands); `/rtp` is Holy Lois's own and stays within the server's prepared area. Teleports do not work during a fight (see **Fights** below).

Walking back through a Nether portal takes you to the portal you came from, not to whichever portal is nearest. The world is 20,000 blocks wide (10,000 out from the centre in each direction).

## Protect your land

Land is claimed in whole chunks (16 x 16 blocks, from bedrock to sky) with **Open Parties and Claims**.

1. Press **J** for the world map, right-click a chunk near you and choose **Claim**. Drag over several chunks to claim an area. You can also stand in a chunk and type `/oclaims claim`.
2. Claimed land shows on the minimap and world map in your colour. Other players cannot build, break, open chests or hurt animals there.
3. Give your land a name and colour: press **'** (OPAC menu), open your player config and set **Claimed Area Name** and the claim colour. The zone title then shows "Name (Owner)".

You don't need a team to claim. Everyone, admins included, claims under the same limits.

**How much land?** Everyone gets **16 chunks free**, earns **1 more for every 2 hours played** (up to 48), and can buy more with coins: `/claims` shows your numbers, `/claims buy` buys the next chunk (500 coins, each next one 15% more) and `/claims sell` sells one back for half price.

**Teams:** `/party create`, then `/party invite NAME`. Team members can build on each other's land. When you walk into someone's land, the zone title at the top of the screen says whose it is; outside claims it says **Wilderness**.

See the [Open Parties and Claims wiki](https://github.com/thexaero/open-parties-and-claims/wiki) for every option.

## Sell to other players

List items on the auction house with `/ah`, or post a buy request with `/orders`. See **Money and the auction house** below.

## Cooking and furniture

**Farmer's Delight** adds real meals. Start with a **knife** (a stick plus flint, iron, gold or diamond) and a **cutting board** (planks and sticks). Place an ingredient on the cutting board, then right-click it with the knife to slice it: pumpkins become pumpkin slices, cabbages become leaves, fish become sushi ingredients. A **cooking pot** over a campfire or **stove** makes soups and stews; a **skillet** fries. Try hamburgers, salmon and cod rolls (sushi), pies and stuffed pumpkins. Wild cabbages, tomatoes, onions and rice grow in newly explored land. Your recipe book shows every recipe once you hold the ingredients.

**Macaw's Furniture** adds chairs and benches you can sit on (right-click), tables, desks, drawers, wardrobes and kitchen cabinets. Most pieces are made from planks or logs of the wood you want; drawers and wardrobes store items like chests.

**Macaw's Holidays** adds Christmas trees, string lights, garlands, wreaths, candy canes, presents and Halloween pumpkins and decorations.

Right-click a fully grown crop to harvest it and replant automatically. One player sleeping in a bed is enough to skip the night.

## Explore

Newly explored land has **Dungeons and Taverns** (taverns, crypts, illager camps and manors, shrines, wells and more) and **Towns and Towers** (new village styles and towers). Their chests can roll Runeforged stones and gear: vaults and boss rooms give the best rewards. Areas you already explored stay as they are.

The first time anyone walks into a big structure, the whole server sees who discovered it. Villages, wells, camps and small ruins stay quiet, but every underground dungeon (small, medium or large, in plains, ice and sand styles) and every lone obelisk is announced and earns achievements. Each dungeon is built from random rooms, so one may have a treasure room and the next none; the treasure rooms hold the best loot and Runeforged runes. Type `/structures` to see which structure you are standing in. Walking into a structure also shows its name at the top of the screen: red for dungeons and other dangerous places, green for villages, blue for ruins and the rest. Biome names show in gold. Hold **Tab** to see the leaderboards; each time the page comes round it shows another one, from diamonds and ancient debris to playtime and fish caught.

## Fishing, legends and treasure

**Fish of Thieves** adds ten kinds of fish in many colours; some live only in certain waters, at night or in storms. Every fish you catch has a size: **Common**, **Uncommon**, **Rare**, **Epic** or **Legendary**. Common fish stay plain and stack as always, Uncommon ones get a green name. Rare and better keep their weight in kg and your name and do not stack, so they work as trophies. A Legendary catch is announced to everyone. Trophies weigh by rarity: Rare 1-2.99 kg, Epic 3-19.99 kg, Legendary 20-40 kg. Very rarely (about one fish in 5,000) a Legendary turns **Mythic**: a red name, 40 kg and up, and the whole server hears it. Legendary and Mythic names shimmer wherever they show up: in chat, in tooltips and in the death message when someone finishes you off with one. About one trophy in 250 comes up **Shiny**: a sparkle before its name, a glint, extra sparkles, its own jingle and stronger effects. Luck of the Sea makes big fish more likely.

Trophy fish look as big as they weigh (a 10 kg fish is clearly bigger than a 2 kg one) and take on their rarity colour: in hands, on the ground, in item frames and on the cutting board. Fish of 10 kg and more are carried over your head with both hands: nothing stays in your off hand meanwhile (it goes back into your inventory, or drops if the inventory is full), and such a fish cannot be put in the off hand. In your inventory, chests and backpacks they have a glow in their rarity colour and their weight in kg in the top-left corner of the slot. Put one on a **cutting board** and slice it with a knife (all Fish of Thieves fish can be sliced too). Heavier fish give more slices, about two plus one per 1.5 kg, at most four per cut, so a big fish takes several cuts and shows wear in between (the board tells you how many cuts are left); take it off the board and the wear stays, and a half-cut fish fills you up less. Every slice keeps the rarity colour, the Shiny star and a shorter, weaker share of the eaten effects, and matching slices stack. Bigger fish fill you up more when eaten. Each kind of trophy does its own thing, and the tooltip lists exactly what. Eaten: cod gives Haste, salmon and battlegill Strength, tropical fish Night Vision, splashtail Speed, pondie Regeneration, islehopper Jump Boost, ancientscale Resistance, plentifin Saturation, wildsplash Dolphin's Grace, stormfish Slow Falling and Speed, devilfish Fire Resistance with some Weakness, and pufferfish poisons you. A wrecker is a pure trophy with no effect. Held in your main hand: pufferfish and ancientscale add armor, splashtail speed, islehopper jump height, wildsplash swimming, battlegill attack damage and wrecker knockback resistance. Higher rarity, a bigger fish and Shiny make it last longer and hit harder. Cooking keeps the rarity, weight and effects, and the effects last half again as long.

Now and then a loot crate comes up on the hook (**Fishing Loot Crates**). Fishing treasure can also be a **message in a bottle** or a **map to buried treasure**.

**Legends**: rare named items hide in dungeon, tavern and town chests, each with an old inscription in grey. Every item belongs to a legend, and more of the same legend are out there; some only come from the sea. Finding one earns Touched by Legend, a whole set earns that legend's own achievement.

## Your own music

Put your own songs on music discs and goat horns. They play through voice chat, so other players hear them nearby and caves echo.

1. Type `/audioplayer`, click **Upload audio via Filebin**, and follow the link to upload an MP3 or WAV (up to 20 MB, 5 minutes).
2. Back in game, click the confirm message. Hold a music disc or goat horn and click **put on item**.
3. Play the disc in a jukebox. `/audioplayer volume` changes your own listening volume.

Only upload music you are allowed to share.

## Daily gifts and the Holy Lootbox

Log in once a day (Riga time) for a small gift: food, ores, books or rockets. The gold block on holylois.com sometimes shows a **secret code of the day**: type `/redeem CODE` in game for a prize, once per day, after 20 minutes of active play that day (new players first need 2 hours of play). Everyone gets the same code, so ask around if someone found it. Every 7th day in a row you get a **Holy Lootbox**, a gold present; right-click it to open. Lootboxes hold diamonds, Runeforged stones, golden apples and more, and sometimes a named tool or weapon with your name on it. Each finished week raises the lootbox tier, up to tier 3. Missing a day starts the streak again. A **secret code** of the day hides somewhere on holylois.com: type `/redeem CODE` in game for one prize per player per day (coins, a lootbox, diamonds, a Runeforged find, and very rarely a legendary weapon). Holidays such as Christmas, New Year, Jāņi, Halloween and 18 November bring their own greeting and gift.

## Money and the auction house

Everyone starts with 250 coins. `/sell` turns spare items into coins, `/ah` opens the auction house to buy and list items, `/orders` lets you ask for items at your price, `/pay NAME AMOUNT` sends coins and `/bal` shows your balance. 100 daily coins arrive by themselves with your first login each day; if they ever do not, the daily message shows a **[Claim]** button.

## Boombox

Craft a boombox from string (top), iron ingot + jukebox + iron ingot (middle) and amethyst shard + redstone + amethyst shard (bottom).

- **Carry it**: hold it in either hand and right-click the air to play internet radio. Everyone in earshot hears it through voice chat (16 blocks at volume 1, about 30 at the default 5, 48 at volume 10), and it follows you. Right-click again for the next station, sneak + right-click to stop. Sneak + scroll while holding it, or while looking at a placed one, sets its volume from 1 to 10; louder also reaches further. It stops when you drop it or put it away.
- **Set it down**: right-click a block with it. Right-click the placed boombox to play or switch stations; sneak with an empty hand and right-click to turn it off. It keeps playing while anyone is nearby, even after a restart. Break it to pick it up again.

Stand still for a minute near a playing boombox or music disc and the cinematic camera fades in; while it runs, the music plays right in your ears, and it goes back to the speaker when you move. Minecraft's background music and the cinematic's own soundtrack stay quiet while boombox or disc music reaches you. While fishing, the cinematic keeps changing angles on you and your bobber and stays on a catch until you reel it in.

Placed radio controls follow claim permissions. At most six placed boomboxes can play in one chunk; at most six streams play server-wide, including held radios.

The song title shows above your hotbar, music notes pop from a playing boombox on the beat, a carried boombox hangs at your hip and swings as you walk and turn, and the game's own music pauses while a boombox plays near you. Your own Boombox volume slider is in the voice chat settings (press V, then the volume button). `/boombox stations` lists the stations.

## Achievements and recipes

Press **L**; the **Holy Lois** tab comes first. Time spent AFK does not count towards playtime goals, land claims, leaderboards or stats. Some goals are hidden until you get close, such as visiting every kind of dungeon or eating every Farmer's Delight meal. In your inventory, hover an item and press **R** for its recipe or **U** for what it is used in. **R** over an empty slot sorts your inventory instead.

## After death

Chat tells you where you died, and the minimap marks the spot until you reach it. Your dropped items stay for **30 minutes of loaded-world time**, and only you can pick them up for the first 5 minutes. When you pick them up, each stack goes back to the slot it came from (hotbar, armor and off-hand too) if that slot is still free; the rest is picked up as usual. Time does not advance while the area is unloaded. Recover them promptly: **fire, lava and the void can still destroy items**.

## Fights

Hitting another player, or being hit by one, puts you both **in combat for 20 seconds** (a red counter above the hotbar). While in combat, `/rtp`, `/home`, `/tpa` and `/back` do not work, and **logging out kills you**. A PvP death drops your loot unlocked for the winner, with no coordinates in chat and no minimap marker. Getting hit by a monster only blocks teleports for 5 seconds. PvP still needs both players' consent (rule 5).

## Help, reports and donations

- `/support MESSAGE`: pjampjam gets it on Discord right away and replies in game. Start with `bug`, `help` or `grief` if it fits.
- `/report NAME REASON`: report a player privately.
- `/donate`: crypto wallets if you want to help pay for the server. Donations never buy anything in game.

## Only the Holy Lois mods

The server checks your mod list when you join. If you added mods of your own, you are turned away with a message that names them. Open the Holy Lois launcher and press **Play** (or **Repair / check files**): extra mods are moved out of the game folder (not deleted, you find them in the launcher's quarantine folder) and the pack's files and resource packs are put back. Shaders, resource packs, keybinds and settings are yours and are not checked.

## Keep your pack updated

You can launch the saved pack directly from Minecraft Launcher or SKlauncher after installation. Open Holy Lois periodically to check for updates. When an update needs Minecraft or its launcher closed, Holy Lois asks first (press **Agree**) and closes them for you; then open your launcher again.

If the SKlauncher entry was deleted or moved, close both Minecraft and SKlauncher and use **Repair / check files** in Holy Lois. It restores the managed files and adds the Holy Lois profile automatically.

Sorting remains available in your inventory. Profile overlays, matching-item hover highlights, slot locking, continuous crafting and failed-replacement alerts are off by default. Tools and armor show quiet remaining/max durability numbers in their tooltips. When a tool breaks, an unenchanted spare of the same kind from your inventory takes its place (lowest material first, then the most worn), with a soft chime. Enchanted tools are never swapped in for you. Enchantment descriptions show while you hold Shift over an item.

## Adventuring together (pack 1.8.2)

Create a party with `/party create`, invite a friend with `/party invite NAME`, and use the existing OPAC party interface (press '). Membership is shared with claims; there is no second party account/database.

Party members are protected from player-attributed damage and harmful effects. Healing still works. This covers normal melee, attributed projectiles and harmful potion effects, not every environmental trap or effect from another mod. Leave the party before an agreed PvP duel.

The optional party HUD shows member health and absorption, including offline/other-dimension status. `/partyhud on` and `/partyhud off` control your panel. `*` means another dimension. The panel shows a compact subset when space is short.

`/rally` deliberately shares your current position with authenticated party members for90seconds. It has a10second cooldown. `/rally clear` removes your mark; the party owner can also clear it. The HUD shows a direction arrow, distance and time remaining. Pings never teleport anyone or publish a point to website stats/BlueMap. Leaving/kicking the sender revokes the mark. `/partyhud pings off` hides notifications locally; it does not change membership or delivery to other party members.

Daily item gifts remain once per Riga day. Coins use EconomyCraft's own daily claim operation and native daily ledger/reset schedule, without a second deposit. A corner card and short chat receipt show delivered rewards. The seventh-day lootbox keeps its central celebration. If the coins ever do not arrive, the daily message shows a **[Claim]** button.

Voice recovery retries the existing mod handshake after authentication when there is no active native connection. `/voicefix` requests another attempt, with a short cooldown. It does not unmute your microphone or change volume settings. If voice stays unavailable, use V to check the setup and contact support.

## Pack 1.8.1 fixes

Placed relics keep their full item data when recovered. Fishing Crates retain intended enchantments and stack counts. Combat protection also checks accepted and delayed teleports. Login/register screens quiet world audio without changing your volume settings. First-person bow aiming and filled maps are compatible with the visible-body view, and fishing lines follow the actual rod pose in either camera.

Other players' claim overlays appear only after the map has cached terrain there; your own claims remain visible. Untrusted players cannot directly push or deal player-attributed damage to mobs inside protected claims. This is not immunity to every environmental hazard or other mod.

Your selected `/skin` or `/skins` skin is saved by SkinsRestorer and supplies your public statistics head. Personal privacy toggles remain planned. Account forms are described below.

## Pack 1.9.0: homes, parties and equipment

`/homes` opens your three starter home slots. Save your current spot, rename a home or confirm its deletion. Selecting a saved home uses the usual teleport checks. Slots you have not unlocked show greyed out. Existing extra homes are retained; no new purchase or play-time unlock is offered yet. Press Enter to confirm a name. Plain `/home` still goes to your only home or the one named `home`.

`/party` or `/group` opens party management and the health roster. Create a party, invite a friend by name, accept an invitation using an online member's name, or leave with confirmation. The owner sees Disband party instead of Leave party; disbanding requires confirmation and ends shared party access. Membership and shared land access remain OPAC's; `/oparties` and the apostrophe menu still work.

Use `/rally` to share a point for 90 seconds. Open chat to click its card, request travel to the author, or collapse it. Click the compact card to reopen it, or use `/rally menu`. Travel uses the normal `/tpa` acceptance flow to the author's current location, with combat and destination checks. Clearing/expiry or the author leaving the party revokes the point.

Lois's Lantern gives +10% mining speed while held. Placed, it heals eligible nearby players by half a heart every five seconds within four blocks, with a clear path and outside combat. The Staff of Quiet Roads gives +8% movement speed while held. The Circlet of the Wanderer gives +1 luck on your head. Copies do not stack; the original items and metadata stay intact.

Rare fish catches have a personal card above the hotbar and a chime. `/catchcards off` disables both; `/catchcards on` restores them. Rarity and coin rewards are unchanged.

Boomboxes support waterlogging. A held eating/drinking press cannot become an off-hand radio click after it finishes; release and press again to control the radio. Six placed boxes can be powered per chunk, while six streams remain the server-wide limit. Unheard placed boxes can wait for listeners; the current audio system does not share station decoders or select only the nearest three sources.

Worn armor looks 3D for everyone (the 3D Armor mod, with dyes and trims). Gameplay and inventory icons stay the same. Mob armor, saddles, 32x and Curios support advertised as planned by that project are not promises of this version.

Enter confirms every form (login, register, homes, party invites) and Esc on the login form asks whether to leave the server. Alt-tab no longer opens the pause menu (F3+P turns pausing back on). Fish of Thieves tropical islands and fruit trees no longer appear in newly generated land, so the world keeps its vanilla look; their fish and items stay. Fishy Business counts Fish of Thieves fish too.

In your inventory the boombox shows as a flat icon; in your hand it is a 3D boombox carried by the middle of its handle, speakers facing out, pumping and popping notes on the beat while it plays.

Maps are held up in front of you, food goes to your mouth and shrinks bite by bite while you eat (Eating Animation by ThatCuteOne, CC BY 4.0, plus its Farmer's Delight add-on) and lanterns hang from your hand and swing as you move, in first and third person. The daily reward card fades in above the hotbar with the Holy Lootbox (a gold block with the Holy Lois logo; right-click to open it) in sight all week, menus fit their content, green buttons confirm and red ones cancel or delete, and party health bars are wider. The title screen shows our own panorama and a Holy Lois: Reborn button that joins the server; connecting, loading and the login form keep the same blurred panorama and fade into the world once you are in. When you join, the resource download shows on the loading bar instead of a popup. The AFK camera starts a few seconds after you cast a line or once you are marked AFK (15 minutes), not after 30 seconds of standing still; if you changed its timing yourself, your setting stays.

Your saved skin returns on rejoin, and BlueMap uses it when refreshing your marker. Skins, guide keys and statistics head layouts retain the earlier prepared fixes.

## Account help (pack 1.8.3)

Quick start accepts a valid player name without checking Minecraft ownership. Names already claimed on Holy Lois still need their server password.

If an admin requests a name change, log in and click the private reminder or type `/account rename`. Choose an available name. Your inventory, homes and progress stay with you; your previous name remains protected. Reconnect when the form finishes. You can use your new name or your saved previous name for the same profile.

For a forgotten server password, contact support. After ownership is verified, an admin can issue a one-use recovery code. Open `/account password` and enter the code and your new password in the private form. Never post either in chat. The recovery request expires after one hour; five incorrect codes cancel it. Reconnect and log in with your new password after it changes.

`/logout` and account changes are blocked during combat. Wait for the combat cooldown before using the account form; disconnecting during a PvP fight still triggers the existing death penalty.
