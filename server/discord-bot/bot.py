"""Holy Lois Discord bot: live server status, a Minecraft <-> Discord chat bridge and a few slash commands.

- #server-status: one message, edited every minute (online, players, address, website, map).
- #minecraft-chat: game chat, joins, leaves, deaths, advancements and discoveries are posted here; messages
  written here appear in game as [Discord] Name: text.
- /status, /players, /ip, /map.

Runs as the holylois-discord-bot service. The token lives only in /etc/holylois/discord-bot-token.
Player IP addresses from the log are never forwarded.
"""
import asyncio, json, os, re, socket, struct, subprocess, time
from pathlib import Path

import discord
from support_registry import Registry
from routine import load_policy, ensure_audit, support as expire_support
from discord import app_commands

TOKEN = Path("/etc/holylois/discord-bot-token").read_text().strip()
STATE = Path("/var/lib/holylois/discord-bot.json")
FIFO = "/run/minecraft-console.fifo"
ADDRESS, WEBSITE, MAP = "play.holylois.com", "https://holylois.com", "https://map.holylois.com"
CATEGORY, STATUS_CHANNEL, CHAT_CHANNEL, RULES_CHANNEL, WELCOME_CHANNEL = "📌 START HERE", "server-status", "minecraft-chat", "rules", "welcome"
ROLES_CHANNEL = "roles"
# New posts in #suggestions get these votes from the bot; the channel denies Add Reactions, so they are the only choices.
SUGGESTIONS_CHANNEL, VOTES = "suggestions", ("👍", "👎")
# Reactions that hand out roles: ✅ under the rules unlocks the server (setup_revamp.py --gate), the rest are opt-in pings in #roles.
VERIFY, PINGS = ("✅", "Member"), [("📢", "Updates", "new releases and big news"), ("🎉", "Events", "events on the server"),
                                   ("🔄", "Restarts", "restarts and downtime")]
# Locked voice channels in 📊 SERVER STATS renamed by the bot (Discord allows 2 renames per 10 minutes per channel).
ONLINE_PREFIX, MEMBERS_PREFIX = "🟢 Online: ", "👥 Members: "
RULES_FILE = Path("/opt/holylois-bot/RULES.md")
GOLD, GREEN, RED = 0xF4C542, 0x34D27B, 0xC2362F

STAFF_CATEGORY, SUPPORT_CHANNEL = "🛠 STAFF", "support"
# Written by the onboarding add-on for /support and /report (one JSON object per line).
SUPPORT = re.compile(r"\]: HOLYLOIS-SUPPORT (\{.*\})$")
CHAT = re.compile(r"\]: (?:\[Not Secure\] )?<([A-Za-z0-9_]{3,16})> (.+)$")
LOGIN = re.compile(r"\]: ([A-Za-z0-9_]{3,16})\[/[^\]]+\] logged in with entity id")
SYSTEM = re.compile(r"\]: System chat: (.+)$")
NAME = re.compile(r"^[A-Za-z0-9_]{3,16}$")
# Same filter and fixed-length mask as the website (server/stats/make-stats.py): keep the row, never the word.
SLURS = re.compile(r'n[i1!|l][g6q9]{2}|f[a@4][g6q9]{1,2}[o0]t|f[a@4][g6q9]$|r[e3]t[a@4]rd|p[i1!]d[o0a]r|k[i1!]ke|ch[i1!]nk|tr[a@4]nn(?:y|ie)|п[иі]д[оа]р', re.I)


def shown(name):
    return name[0].upper() + "*****" if SLURS.search(name) else name
# Names from the add-on's config/holylois-quiet.json: no joins, leaves, advancements, discoveries or deaths in Discord, and not in the player list.
QUIET_FILE = Path("/opt/minecraft/config/holylois-quiet.json")
_quiet = {"stamp": None, "names": {"pjampjam"}}


def text(guild, base):
    """A text channel by its base name, plain ("rules") or with an emoji prefix ("📜・rules")."""
    return next((c for c in guild.text_channels if c.name == base or c.name.endswith("・" + base)), None)


def quiet_names():
    try:
        stamp = QUIET_FILE.stat().st_mtime
        if stamp != _quiet["stamp"]:
            _quiet["names"] = {n.lower() for n in json.loads(QUIET_FILE.read_text()).get("names", []) if isinstance(n, str)}
            _quiet["stamp"] = stamp
    except (OSError, ValueError):
        pass  # keep the last known names
    return _quiet["names"]


def visible(result):
    """ping() result without the quiet players: (count, names, version) or None."""
    if result is None: return None
    count, names, version = result
    hidden = quiet_names()
    shown = [n for n in names if n.lower() not in hidden]
    return max(0, count - (len(names) - len(shown))), shown, version


def varint(value):
    out = bytearray()
    while True:
        b = value & 127; value >>= 7
        out.append(b | (128 if value else 0))
        if not value: return bytes(out)


def ping():
    """Server list ping on localhost as the public sees it (play.holylois.com: staff hidden): (online, names, version) or None."""
    try:
        with socket.create_connection(("127.0.0.1", 25565), timeout=5) as s:
            host = b"play.holylois.com"
            packet = b"\x00" + varint(0) + varint(len(host)) + host + struct.pack(">H", 25565) + b"\x01"
            s.sendall(varint(len(packet)) + packet + b"\x01\x00")
            data, deadline = b"", time.time() + 5
            while time.time() < deadline:
                chunk = s.recv(65536)
                if not chunk: break
                data += chunk
                start = data.find(b"{")
                if start >= 0:
                    try:
                        status = json.loads(data[start:].decode("utf-8"))
                    except ValueError:
                        continue
                    players = status.get("players", {})
                    names = [p.get("name", "") for p in players.get("sample", []) if NAME.match(p.get("name", ""))]
                    return players.get("online", 0), names, status.get("version", {}).get("name", "")
    except OSError:
        return None
    return None


def uptime():
    value = subprocess.run(["systemctl", "show", "minecraft", "-p", "ActiveEnterTimestampMonotonic", "--value"], capture_output=True, text=True).stdout.strip()
    if not value.isdigit() or value == "0": return ""
    seconds = time.clock_gettime(time.CLOCK_MONOTONIC) - int(value) / 1e6
    hours, minutes = int(seconds // 3600), int(seconds % 3600 // 60)
    return f"{hours} h {minutes} min" if hours else f"{minutes} min"


def tellraw(name, text):
    """Shows a Discord message in game. Written without blocking, as JSON, so nothing can inject commands."""
    text = " ".join(text.split())[:240]
    if not text: return
    payload = json.dumps(["", {"text": "[Discord] ", "color": "#5865F2"}, {"text": name + ": ", "color": "gray"}, {"text": text, "color": "white"}], ensure_ascii=False)
    try:
        fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
        try: os.write(fd, ("tellraw @a " + payload + "\n").encode("utf-8"))
        finally: os.close(fd)
    except OSError:
        pass


def tell_player(name, parts):
    """Private in-game message to one player (JSON text, so nothing can inject commands)."""
    if not NAME.match(name or ""): return
    try:
        fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
        try: os.write(fd, (f"tellraw {name} " + json.dumps(parts, ensure_ascii=False) + "\n").encode("utf-8"))
        finally: os.close(fd)
    except OSError:
        pass


def load_state():
    try: return json.loads(STATE.read_text())
    except (OSError, ValueError): return {}


def save_state(state):
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


class HolyLoisBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.state = load_state()
        self.status_channel = self.chat_channel = self.support_channel = None
        self.online = set()
        self.support_registry = Registry("/var/lib/holylois/support-retention.sqlite")
        self.support_registry.protect_after_gap()

    async def setup_hook(self):
        @self.tree.command(name="status", description="Is the Holy Lois server online?")
        async def status(interaction: discord.Interaction):
            await interaction.response.send_message(embed=self.status_embed())

        @self.tree.command(name="players", description="Who is playing right now?")
        async def players(interaction: discord.Interaction):
            result = visible(ping())
            text = "The server is offline." if result is None else ("Nobody is online." if not result[0] else f"{result[0]} online: " + ", ".join(result[1]))
            await interaction.response.send_message(text)

        @self.tree.command(name="ip", description="The server address")
        async def ip(interaction: discord.Interaction):
            await interaction.response.send_message(f"Server address: **{ADDRESS}**\nDownload the launcher: {WEBSITE}")

        @self.tree.command(name="map", description="Open the live world map")
        async def world_map(interaction: discord.Interaction):
            await interaction.response.send_message(f"Live map: {MAP}")

    async def on_ready(self):
        if not self.guilds:
            print("Not in a Discord server yet; waiting for the invite.")
            return
        guild = self.guilds[0]
        self.status_channel, self.chat_channel = await self.ensure_channels(guild)
        self.support_channel = await self.ensure_support(guild)
        print(f"Ready in {guild.name}: #{self.status_channel.name}, #{self.chat_channel.name}", flush=True)
        if not getattr(self, "_started", False):
            self._started = True
            await self.post_rules(guild)
            await self.post_welcome(guild)
            await self.post_roles(guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self.loop.create_task(self.status_loop())
            self.loop.create_task(self.log_loop())
            self.loop.create_task(self.retention_loop())
            self.loop.create_task(self.counter_loop(guild))

    async def on_guild_join(self, guild):
        await self.on_ready()

    async def ensure_channels(self, guild):
        status, chat = text(guild, STATUS_CHANNEL), text(guild, CHAT_CHANNEL)
        if status and chat: return status, chat
        category = discord.utils.get(guild.categories, name=CATEGORY) or discord.utils.get(guild.categories, name="📌 INFO") or await guild.create_category(CATEGORY)
        if status is None:
            overwrites = {guild.default_role: discord.PermissionOverwrite(send_messages=False), guild.me: discord.PermissionOverwrite(send_messages=True)}
            status = await guild.create_text_channel(STATUS_CHANNEL, category=category, overwrites=overwrites, topic=f"Live status of {ADDRESS}")
        chat = chat or await guild.create_text_channel(
            CHAT_CHANNEL, category=category, topic="Talk with players in game. Messages here appear in Minecraft chat.")
        return status, chat

    async def ensure_support(self, guild):
        """Private #support in the STAFF category: in-game /support and /report land here."""
        channel = text(guild, SUPPORT_CHANNEL)
        staff = discord.utils.get(guild.categories, name=STAFF_CATEGORY)
        if channel is None and staff is not None:
            channel = await guild.create_text_channel(SUPPORT_CHANNEL, category=staff, topic="Help requests and reports from in game (/support, /report)")
        return channel

    async def post_support(self, data):
        """One embed per request, pinging the server owner, with buttons that answer the player in game."""
        if self.support_channel is None: return
        player, kind = str(data.get("player", "")), data.get("kind", "help")
        if not NAME.match(player) or kind not in ("help", "report"): return
        safe = lambda text: discord.utils.escape_mentions(discord.utils.escape_markdown(str(text)))[:1000]
        report = kind == "report"
        embed = discord.Embed(title=("🚩 Report about " + safe(data.get("target", "?"))) if report else "🆘 Help request",
                              description=safe(data.get("message", "")) or "(no message)", color=RED if report else GOLD)
        embed.add_field(name="From", value=player)
        embed.add_field(name="Where", value=f"{safe(data.get('dimension', '?'))} {data.get('x')}, {data.get('y')}, {data.get('z')}")
        if data.get("category"): embed.add_field(name="Type", value=safe(data["category"]))
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="On my way", style=discord.ButtonStyle.primary, custom_id=f"hl-support:onway:{player}"))
        view.add_item(discord.ui.Button(label="Solved", style=discord.ButtonStyle.success, custom_id=f"hl-support:solved:{player}"))
        view.add_item(self.hold_button(player, report))
        owner = self.support_channel.guild.owner_id
        sent = await self.support_channel.send(content=f"<@{owner}>" if owner else None, embed=embed, view=view,
                                        allowed_mentions=discord.AllowedMentions(users=True))
        self.support_registry.received(sent.id, sent.channel.id, sent.created_at.isoformat(),
                                       retention_class="case" if report else "routine")

    async def on_interaction(self, interaction):
        custom = (interaction.data or {}).get("custom_id", "") if interaction.type == discord.InteractionType.component else ""
        if not custom.startswith("hl-support:"): return
        parts = custom.split(":", 2)
        if len(parts) != 3 or parts[1] not in ("onway", "solved", "hold", "release"): return
        _, action, player = parts
        if (self.support_channel is None or interaction.channel_id != self.support_channel.id
                or interaction.message is None or interaction.message.author.id != self.user.id): return
        if not interaction.permissions.manage_messages and not interaction.permissions.administrator:
            await interaction.response.send_message("Only staff can change support requests.", ephemeral=True)
            return
        snapshot = self.support_registry.snapshot(interaction.message.id)
        if snapshot is None:
            await interaction.response.send_message("This older request requires manual retention review.", ephemeral=True)
            return
        if action in ("hold", "release"):
            self.support_registry.hold(interaction.message.id, interaction.channel_id, action == "hold")
            view = discord.ui.View(timeout=None)
            if not snapshot['resolved']:
                view.add_item(discord.ui.Button(label="Solved", style=discord.ButtonStyle.success,
                                               custom_id=f"hl-support:solved:{player}"))
            view.add_item(self.hold_button(player, action == "hold"))
            await interaction.response.edit_message(view=view)
            await interaction.followup.send("Retention hold enabled." if action == "hold" else
                                            "Reviewed as routine. Expiry uses the latest resolution or activity.",
                                            ephemeral=True)
            return
        helper = interaction.user.display_name[:24]
        if action == "onway":
            tell_player(player, [{"text": "[Holy Lois] ", "color": "gold", "bold": True}, {"text": f"{helper} saw your request and will help you soon.", "color": "yellow", "bold": False}])
            note, done = f"🟡 {helper} is on it", False
        else:
            tell_player(player, [{"text": "[Holy Lois] ", "color": "gold", "bold": True}, {"text": f"{helper} marked your request as solved. Thanks!", "color": "green", "bold": False}])
            note, done = f"✅ Solved by {helper}", True
        embed = interaction.message.embeds[0] if interaction.message and interaction.message.embeds else None
        if embed is not None:
            embed.set_footer(text=note)
            if done: embed.color = GREEN
        view = discord.ui.View(timeout=None)
        if not done:
            view.add_item(discord.ui.Button(label="Solved", style=discord.ButtonStyle.success, custom_id=f"hl-support:solved:{player}"))
        view.add_item(self.hold_button(player, bool(snapshot["held"])))
        await interaction.response.edit_message(embed=embed, view=view)
        if done:
            self.support_registry.resolve(interaction.message.id, interaction.channel_id,
                                          discord.utils.utcnow().isoformat())

    async def post_welcome(self, guild):
        """One start-here message in #welcome: what the server is, how to join and every link."""
        embed = discord.Embed(title="Welcome to Holy Lois: Reborn", color=GOLD, url=WEBSITE,
            description="An adventure-focused modded Minecraft survival world for friends: cooking and furniture, dungeons with real loot, "
                        "a boombox radio, daily gifts, an auction house and proximity voice chat with cave echo.")
        embed.add_field(name="How to join", inline=False, value=(
            f"1. Download the launcher from **{WEBSITE}**\n"
            "2. Open it and click **Install Holy Lois**\n"
            f"3. Start Minecraft and join **{ADDRESS}**"))
        embed.add_field(name="Links", inline=False, value=(
            f"[Website and download]({WEBSITE}) - [Live map]({MAP}) - [Rules]({WEBSITE}/rules) - [How to play]({WEBSITE}/guide)"))
        around = [(RULES_CHANNEL, "read before playing"), (ROLES_CHANNEL, "pick which pings you want"),
                  (STATUS_CHANNEL, "live status and who is online"), (CHAT_CHANNEL, "talk with players in game"),
                  ("help", "launcher or game problems"), (SUGGESTIONS_CHANNEL, "ideas for the server, vote with 👍 or 👎")]
        embed.add_field(name="Around here", inline=False, value="\n".join(
            f"{c.mention if (c := text(guild, base)) else '#' + base} - {what}" for base, what in around))
        embed.add_field(name="Bot commands", inline=False, value="/status - /players - /ip - /map")
        embed.set_footer(text="Holy Lois: Reborn")
        channel = text(guild, WELCOME_CHANNEL)
        if channel is None:
            category = discord.utils.get(guild.categories, name=CATEGORY)
            overwrites = {guild.default_role: discord.PermissionOverwrite(send_messages=False), guild.me: discord.PermissionOverwrite(send_messages=True)}
            try:
                channel = await guild.create_text_channel(WELCOME_CHANNEL, category=category, overwrites=overwrites, position=0,
                                                          topic="Start here: what Holy Lois is, how to join and every link")
            except discord.Forbidden:
                channel = await guild.create_text_channel(WELCOME_CHANNEL, category=category, position=0,
                                                          topic="Start here: what Holy Lois is, how to join and every link")
        message = None
        if self.state.get("welcome_message"):
            try: message = await channel.fetch_message(self.state["welcome_message"])
            except discord.NotFound: message = None
        if message: await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed)
            self.state["welcome_message"] = message.id; save_state(self.state)

    async def post_rules(self, guild):
        """Keeps one read-only #rules message in sync with RULES.md (edited in place when the file changes)."""
        if not RULES_FILE.exists(): return
        lines = RULES_FILE.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].startswith("# "): lines = lines[1:]
        # Markdown headings become bold lines; Discord embeds do not render "##".
        lines = ["**" + l[3:].strip() + "**" if l.startswith("## ") else l for l in lines]
        merged = []
        for line in lines:
            # Rejoin hard-wrapped Markdown so sentences are not broken in the embed.
            if merged and merged[-1] and line.strip() and not re.match(r"^(\d+\.|- |\*\*)", line.strip()):
                merged[-1] += " " + line.strip()
            else:
                merged.append(line.strip())
        lines = merged
        embed = discord.Embed(title="Holy Lois: Reborn - Server rules", description="\n".join(lines).strip()[:4000], color=GOLD)
        gated = discord.utils.get(guild.roles, name=VERIFY[1]) is not None
        embed.set_footer(text=(f"React {VERIFY[0]} below to agree and unlock the server  |  " if gated else "") + f"Short version in game: /rules  |  {WEBSITE}/rules")
        channel = text(guild, RULES_CHANNEL)
        if channel is None:
            category = discord.utils.get(guild.categories, name=CATEGORY)
            overwrites = {guild.default_role: discord.PermissionOverwrite(send_messages=False), guild.me: discord.PermissionOverwrite(send_messages=True)}
            channel = await guild.create_text_channel(RULES_CHANNEL, category=category, overwrites=overwrites, topic="Read before playing", position=0)
        message = None
        if self.state.get("rules_message"):
            try: message = await channel.fetch_message(self.state["rules_message"])
            except discord.NotFound: message = None
        if message: await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed)
            self.state["rules_message"] = message.id; save_state(self.state)
        if gated and not any(str(r.emoji) == VERIFY[0] for r in message.reactions): await message.add_reaction(VERIFY[0])

    async def post_roles(self, guild):
        """#roles: react to get pinged for updates, events or restarts (exists once setup_revamp.py has run)."""
        channel = text(guild, ROLES_CHANNEL)
        if channel is None: return
        embed = discord.Embed(title="Pick your pings", color=GOLD, description="React below to get a ping, react again to stop.\n\n"
                              + "\n".join(f"{emoji} **{role}** - {what}" for emoji, role, what in PINGS))
        embed.set_footer(text="Holy Lois: Reborn")
        message = None
        if self.state.get("roles_message"):
            try: message = await channel.fetch_message(self.state["roles_message"])
            except discord.NotFound: message = None
        if message: await message.edit(embed=embed)
        else:
            message = await channel.send(embed=embed)
            self.state["roles_message"] = message.id; save_state(self.state)
        for emoji, _, _ in PINGS:
            if not any(str(r.emoji) == emoji for r in message.reactions): await message.add_reaction(emoji)

    def reaction_role(self, payload):
        """The role a reaction on the rules or #roles message stands for, or None."""
        guild = self.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None or payload.user_id == self.user.id: return None, None
        emoji = str(payload.emoji)
        if payload.message_id == self.state.get("rules_message") and emoji == VERIFY[0]: name = VERIFY[1]
        elif payload.message_id == self.state.get("roles_message"): name = next((r for e, r, _ in PINGS if e == emoji), None)
        else: name = None
        return guild, discord.utils.get(guild.roles, name=name) if name else None

    async def on_raw_reaction_add(self, payload):
        guild, role = self.reaction_role(payload)
        if role is None: return
        member = payload.member or await guild.fetch_member(payload.user_id)
        try: await member.add_roles(role, reason="Reaction role")
        except discord.HTTPException as error: print("Reaction role failed:", error)

    async def on_raw_reaction_remove(self, payload):
        guild, role = self.reaction_role(payload)
        if role is None: return
        try: await (await guild.fetch_member(payload.user_id)).remove_roles(role, reason="Reaction role removed")
        except discord.HTTPException as error: print("Reaction role removal failed:", error)

    async def counter_loop(self, guild):
        """Keeps the 🟢 Online and 👥 Members counter channels current (every 10 minutes, only when a number changed)."""
        while not self.is_closed():
            try:
                result = visible(await asyncio.to_thread(ping))
                counts = await self.fetch_guild(guild.id, with_counts=True)
                wanted = {ONLINE_PREFIX: ONLINE_PREFIX + (str(result[0]) if result else "offline"),
                          MEMBERS_PREFIX: MEMBERS_PREFIX + str(counts.approximate_member_count or guild.member_count)}
                for channel in guild.voice_channels:
                    for prefix, name in wanted.items():
                        if channel.name.startswith(prefix) and channel.name != name: await channel.edit(name=name, reason="Counter")
            except Exception as error:
                print("Counter update failed:", error)
            await asyncio.sleep(600)

    def status_embed(self):
        result = visible(ping())
        if result is None:
            embed = discord.Embed(title="Holy Lois: Reborn is offline", description="It may be restarting or updating. Check back in a few minutes.", color=RED)
        else:
            count, names, version = result
            embed = discord.Embed(title="Holy Lois: Reborn is online", color=GREEN)
            embed.add_field(name="Players", value=(", ".join(names) if names else "Nobody right now") + f" ({count})", inline=False)
            embed.add_field(name="Version", value=version or "Minecraft 26.3", inline=True)
            up = uptime()
            if up: embed.add_field(name="Up for", value=up, inline=True)
        embed.add_field(name="Address", value=f"`{ADDRESS}`", inline=False)
        embed.add_field(name="Links", value=f"[Website and launcher]({WEBSITE}) - [Live map]({MAP})", inline=False)
        embed.set_footer(text="Updated every minute")
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def status_loop(self):
        while not self.is_closed():
            try:
                embed = await asyncio.to_thread(self.status_embed)
                message = None
                if self.state.get("status_message"):
                    try: message = await self.status_channel.fetch_message(self.state["status_message"])
                    except discord.NotFound: message = None
                if message and (self.status_channel.last_message_id or 0) > message.id:
                    try: await message.delete()
                    except discord.HTTPException: pass
                    message = None
                if message: await message.edit(embed=embed)
                else:
                    message = await self.status_channel.send(embed=embed)
                    self.state["status_message"] = message.id; save_state(self.state)
                result = visible(ping())
                activity = discord.Game(f"{result[0]} on {ADDRESS}" if result else "server offline")
                await self.change_presence(activity=activity)
            except Exception as error:
                print("Status update failed:", error)
            await asyncio.sleep(60)

    async def log_loop(self):
        while not self.is_closed():
            process = await asyncio.create_subprocess_exec("journalctl", "-u", "minecraft", "-f", "-n", "0", "-o", "cat",
                                                           stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                async for raw in process.stdout:
                    line = raw.decode("utf-8", "replace").rstrip()
                    try: await self.forward(line)
                    except Exception as error: print("Forward failed:", error)
            finally:
                if process.returncode is None: process.kill()
                await process.wait()
            await asyncio.sleep(5)

    async def forward(self, line):
        if match := SUPPORT.search(line):
            try: await self.post_support(json.loads(match.group(1)))
            except ValueError: pass
            return
        if self.chat_channel is None: return
        safe = discord.utils.escape_mentions
        if match := CHAT.search(line):
            name, text = match.groups()
            if text.startswith("/") or text.startswith("./"): return
            await self.chat_channel.send(f"**{shown(name)}**: {safe(discord.utils.escape_markdown(text))}"[:1900])
        elif match := LOGIN.search(line):
            self.online.add(match.group(1))
            if match.group(1).lower() in quiet_names(): return
            await self.chat_channel.send(f"➕ **{shown(match.group(1))}** joined the server")
        elif match := SYSTEM.search(line):
            text = match.group(1).lstrip("✦ ").strip()
            first = text.split(" ", 1)[0]
            if text.startswith("[") or not NAME.match(first): return
            if first.lower() in quiet_names():
                if text.endswith("left the game"): self.online.discard(first)
                return
            text = shown(first) + text[len(first):]
            if text.endswith("left the game"):
                self.online.discard(first)
                await self.chat_channel.send(f"➖ **{shown(first)}** left the server")
            elif "has made the advancement" in text or "has completed the challenge" in text or "has reached the goal" in text:
                await self.chat_channel.send(f"🏆 {safe(text)}")
            elif " discovered " in text or "Holy Lootbox" in text:
                await self.chat_channel.send(f"✦ {safe(text)}")
            elif first in self.online:
                await self.chat_channel.send(f"☠ {safe(text)}")

    @staticmethod
    def hold_button(player, held):
        return discord.ui.Button(label="Release hold" if held else "Hold", style=discord.ButtonStyle.secondary,
                                 custom_id=f"hl-support:{'release' if held else 'hold'}:{player}")

    async def retention_loop(self):
        while not self.is_closed():
            try:
                policy = load_policy()
                if policy.get('support_enabled') is True and self.support_channel is not None:
                    ensure_audit()
                    result = await expire_support(self.support_registry, self.support_channel, self.user.id, policy)
                    print("Support retention:", json.dumps(result, sort_keys=True), flush=True)
            except Exception as error:
                print("Support retention blocked:", type(error).__name__, flush=True)
            await asyncio.sleep(86400)

    async def on_disconnect(self):
        self.support_registry.protect_after_gap()

    async def on_raw_message_edit(self, payload):
        if self.support_channel is not None and payload.channel_id == self.support_channel.id:
            stamp = payload.data.get('edited_timestamp')
            if stamp:
                self.support_registry.touch_message(payload.message_id, payload.channel_id, stamp)

    async def on_message(self, message):
        if (self.support_channel is not None and message.channel.id == self.support_channel.id
                and not message.author.bot and message.reference is not None
                and message.reference.message_id is not None):
            self.support_registry.reply(message.id, message.channel.id, message.reference.message_id,
                                        message.created_at.isoformat())
        if not message.author.bot and message.guild is not None and message.channel == text(message.guild, SUGGESTIONS_CHANNEL):
            for emoji in VOTES:
                try: await message.add_reaction(emoji)
                except discord.HTTPException: pass  # deleted meanwhile or missing permission: never break the chat bridge
            return
        if message.author.bot or self.chat_channel is None or message.channel.id != self.chat_channel.id: return
        line = message.clean_content
        if message.attachments: line = (line + " [attachment]").strip()
        await asyncio.to_thread(tellraw, message.author.display_name[:24], line)


if __name__ == "__main__":
    HolyLoisBot().run(TOKEN)
