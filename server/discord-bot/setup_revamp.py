"""Idempotent 2.2.0 Discord revamp (needs the bot role with Administrator). Run on the server as root.

Dry run by default: prints every change. `--apply` makes them; `--gate` also hides the server behind the ✅ under #rules.

📊 SERVER STATS  locked voice counters: address, 🟢 Online (bot), 👥 Members (bot), website
📌 START HERE    welcome, rules (✅ verify), roles (📢 Updates / 🎉 Events / 🔄 Restarts pings), new-members
📢 NEWS          announcements, server-status, events (read-only)
💬 COMMUNITY     general, minecraft-chat, screenshots, suggestions, help
🔊 VOICE         General, In game
⛪ THE CONGREGATION  only the Deacon role (the owner's coworkers): fellowship-hall, Choir Practice voice
🛠 STAFF         unchanged, private

Channels keep their history: they are renamed and moved, never deleted. With --gate, every current member gets Member
first, so nobody is locked out; the bot gives Member to whoever reacts ✅ later.
"""
import json, sys, time, urllib.request, urllib.error

APPLY, GATE = "--apply" in sys.argv, "--gate" in sys.argv
TOKEN = open("/etc/holylois/discord-bot-token").read().strip()
H = {"Authorization": "Bot " + TOKEN, "User-Agent": "DiscordBot (https://holylois.com, 1.0)", "Content-Type": "application/json"}
VIEW, SEND, CONNECT, REACT = 1 << 10, 1 << 11, 1 << 20, 1 << 6


def api(method, path, body=None):
    if method != "GET" and not APPLY:
        print("  would", method, path, json.dumps(body, ensure_ascii=False)[:160] if body else "")
        return {"id": "dry-run", "name": (body or {}).get("name", "?"), "type": (body or {}).get("type", 0)}
    for _ in range(6):
        req = urllib.request.Request("https://discord.com/api/v10" + path, method=method, headers=H,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            raw = urllib.request.urlopen(req).read()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            text = error.read()
            if error.code == 429:
                time.sleep(json.loads(text).get("retry_after", 2) + 0.5); continue
            raise RuntimeError(f"{method} {path}: {error.code} {text[:220]}")
    raise RuntimeError("rate limited")


gid = api("GET", "/users/@me/guilds")[0]["id"]
me = api("GET", "/users/@me")["id"]
chans = lambda: api("GET", f"/guilds/{gid}/channels")


def find(*names, kind=None, prefix=None):
    """First channel whose name is one of names, ends with "・" + a name (already revamped) or starts with prefix (counters)."""
    for c in chans():
        if kind is not None and c["type"] != kind: continue
        if any(c["name"] == n or c["name"].endswith("・" + n) for n in names) or prefix and c["name"].startswith(prefix): return c
    return None


def role(name, color=0, mentionable=False):
    found = next((r for r in api("GET", f"/guilds/{gid}/roles") if r["name"] == name), None)
    if found: return found["id"]
    print("role", name)
    return api("POST", f"/guilds/{gid}/roles", {"name": name, "color": color, "mentionable": mentionable, "permissions": "0"})["id"]


member = role("Member", 0xF4C542) if GATE else None
for name in ["Updates", "Events", "Restarts"]: role(name)
deacon = role("Deacon", 0x9B59B6)


def overwrites(read_only=False, locked_voice=False, private_to=None, hidden_until_verified=False, votes_only=False):
    rules = [{"id": me, "type": 1, "allow": str(VIEW | SEND | REACT), "deny": "0"}]
    # votes_only: people can click the bot's existing reactions but not add new ones (Discord allows that without Add Reactions).
    deny = (SEND if read_only else 0) | (CONNECT if locked_voice else 0) | (REACT if votes_only else 0)
    if private_to or hidden_until_verified: deny |= VIEW
    rules.append({"id": gid, "type": 0, "allow": "0", "deny": str(deny)})
    if private_to: rules.append({"id": private_to, "type": 0, "allow": str(VIEW | SEND | CONNECT), "deny": "0"})
    elif hidden_until_verified: rules.append({"id": member, "type": 0, "allow": str(VIEW), "deny": "0"})
    return rules


def category(name, old=(), **perms):
    c = find(name, *old, kind=4)
    body = {"name": name, "permission_overwrites": overwrites(**perms)}
    if c is None:
        print("category", name); return api("POST", f"/guilds/{gid}/channels", {"type": 4, **body})
    if c["name"] != name: print("category", c["name"], "->", name)
    api("PATCH", f"/channels/{c['id']}", body); return c


def place(parent, position, name, old=(), kind=0, topic=None, prefix=None, **perms):
    c = find(name.split("・")[-1], *old, kind=kind, prefix=prefix)
    body = {"name": name, "parent_id": parent["id"], "position": position, "permission_overwrites": overwrites(**perms)}
    if topic is not None and kind == 0: body["topic"] = topic
    if c is None:
        print("create", name, "in", parent["name"]); return api("POST", f"/guilds/{gid}/channels", {"type": kind, **body})
    if prefix: body.pop("name")  # the bot owns the counter's number
    print("place", c["name"], "->", body.get("name", c["name"]), "in", parent["name"])
    return api("PATCH", f"/channels/{c['id']}", body)


if GATE:
    # Everyone already here keeps access: Member first, then the gate.
    after, given = "0", 0
    while True:
        page = api("GET", f"/guilds/{gid}/members?limit=1000&after={after}")
        if not page: break
        for m in page:
            if not m["user"].get("bot") and member not in m["roles"]:
                api("PUT", f"/guilds/{gid}/members/{m['user']['id']}/roles/{member}"); given += 1
        after = page[-1]["user"]["id"]
    print("Member given to", given, "current members")

hidden = {"hidden_until_verified": GATE}
stats = category("📊 SERVER STATS")
start = category("📌 START HERE", old=("📌 INFO",))
news = category("📢 NEWS", **hidden)
community = category("💬 COMMUNITY", **hidden)
voice = category("🔊 VOICE", **hidden)
church = category("⛪ THE CONGREGATION", private_to=deacon)

place(stats, 0, "🎮 play.holylois.com", old=("🟢 play.holylois.com", "IP: MC.HOLYLOIS.EU"), kind=2, locked_voice=True)
place(stats, 1, "🟢 Online: offline", prefix="🟢 Online: ", kind=2, locked_voice=True)
place(stats, 2, "👥 Members: 0", prefix="👥 Members: ", kind=2, locked_voice=True)
place(stats, 3, "🌐 holylois.com", old=("www.holylois.eu",), kind=2, locked_voice=True)

place(start, 0, "👋・welcome", topic="Start here: what Holy Lois is, how to join and every link", read_only=True)
place(start, 1, "📜・rules", topic="Read before playing. React ✅ under the rules to unlock the server" if GATE else "Read before playing", read_only=True)
place(start, 2, "🎭・roles", topic="Pick which pings you want", read_only=True)
place(start, 3, "🆕・new-members", topic="Who just joined the Discord", read_only=True)

place(news, 0, "📢・announcements", topic="Updates and server news", read_only=True, **hidden)
place(news, 1, "🟢・server-status", topic="Live status of play.holylois.com", read_only=True, **hidden)
place(news, 2, "🎉・events", topic="Events on the server", read_only=True, **hidden)

place(community, 0, "💬・general", topic="Talk about anything", **hidden)
place(community, 1, "⛏・minecraft-chat", topic="Talk with players in game. Messages here appear in Minecraft chat.", **hidden)
place(community, 2, "📸・screenshots", topic="Builds, views and funny moments (F2 in game)", **hidden)
place(community, 3, "💡・suggestions", topic="Ideas for the server, mods and events. Vote with 👍 or 👎", votes_only=True, **hidden)
place(community, 4, "🆘・help", topic="Stuck with the launcher or the game? Ask here", **hidden)

place(voice, 0, "🔊 General", old=("General",), kind=2, **hidden)
place(voice, 1, "🎮 In game", old=("In game",), kind=2, **hidden)

place(church, 0, "🙏・fellowship-hall", topic="Coworkers only. Coffee, gossip and the weekly sermon", private_to=deacon)
place(church, 1, "🎤 Choir Practice", kind=2, private_to=deacon)

order = ["📊 SERVER STATS", "📌 START HERE", "📢 NEWS", "💬 COMMUNITY", "🔊 VOICE", "⛪ THE CONGREGATION", "🛠 STAFF"]
for pos, name in enumerate(order):
    c = find(name, kind=4)
    if c: api("PATCH", f"/channels/{c['id']}", {"position": pos})
print("revamp", "applied" if APPLY else "dry run done (add --apply)", "| gate", "on" if GATE else "off")
