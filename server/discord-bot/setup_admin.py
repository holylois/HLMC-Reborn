"""Idempotent safety and cleanup setup for the Holy Lois Discord (needs the bot role with Administrator).

- Verification level Medium, explicit media filter for all members, join messages in #new-members.
- AutoMod: slurs and sexual content (Discord presets), spam, mention raids, foreign invites and nitro scams; alerts to #mod-log.
- Old address voice channels renamed and locked; read-only info channels; empty old categories removed.
Nothing with messages is deleted; the old #helpful-links is moved into the private staff category.
"""
import json, time, urllib.request, urllib.error

TOKEN = open("/etc/holylois/discord-bot-token").read().strip()
H = {"Authorization": "Bot " + TOKEN, "User-Agent": "DiscordBot (https://holylois.com, 1.0)", "Content-Type": "application/json"}
VIEW, SEND, CONNECT = 1 << 10, 1 << 11, 1 << 20


def api(method, path, body=None):
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
find = lambda name, kind=None: next((c for c in chans() if c["name"] == name and (kind is None or c["type"] == kind)), None)
info, staff = find("📌 INFO", 4), find("ADMIN CATEGORY", 4) or find("🛠 STAFF", 4)
read_only = [{"id": gid, "type": 0, "allow": "0", "deny": str(SEND)}, {"id": me, "type": 1, "allow": str(SEND | VIEW), "deny": "0"}]
locked_voice = [{"id": gid, "type": 0, "allow": "0", "deny": str(CONNECT)}]

if staff:
    api("PATCH", f"/channels/{staff['id']}", {"name": "🛠 STAFF"}); print("staff category named")
log = find("mod-log") or api("POST", f"/guilds/{gid}/channels", {"name": "mod-log", "type": 0, "parent_id": staff["id"], "topic": "AutoMod alerts and bot notices"})
print("mod-log ready")

for old, new, pos in [("IP: MC.HOLYLOIS.EU", "🟢 play.holylois.com", 0), ("www.holylois.eu", "🌐 holylois.com", 1)]:
    c = find(old, 2) or find(new, 2)
    if c:
        api("PATCH", f"/channels/{c['id']}", {"name": new, "parent_id": info["id"], "position": pos, "permission_overwrites": locked_voice}); print("voice display:", new)
for name, pos in [("welcome", 2), ("rules", 3), ("announcements", 4), ("server-status", 5), ("new-members", 6)]:
    c = find(name)
    if c:
        api("PATCH", f"/channels/{c['id']}", {"parent_id": info["id"], "position": pos, "permission_overwrites": read_only}); print("read-only:", name)
links = find("helpful-links")
if links and staff:
    api("PATCH", f"/channels/{links['id']}", {"parent_id": staff["id"], "name": "old-helpful-links"}); print("archived helpful-links into staff")
for old in ["HOLY LOIS", "WELCOME", "Holy Lois Server", "TEXT CHANNELS", "VOICE CHANNELS"]:
    c = find(old, 4)
    if c and not any(ch.get("parent_id") == c["id"] for ch in chans()):
        api("DELETE", f"/channels/{c['id']}"); print("removed empty category", old)

new_members, rules, announcements = find("new-members"), find("rules"), find("announcements")
api("PATCH", f"/guilds/{gid}", {"verification_level": 2, "explicit_content_filter": 2, "system_channel_id": new_members["id"],
                               "description": "Holy Lois: Reborn - an adventure-focused modded Minecraft survival server. play.holylois.com"})
print("verification Medium, media filter all members, join messages in #new-members")

alert = {"type": 2, "metadata": {"channel_id": log["id"]}}
block = lambda text: {"type": 1, "metadata": {"custom_message": text}}
wanted = [
    {"name": "Holy Lois: slurs and sexual content", "event_type": 1, "trigger_type": 4,
     "trigger_metadata": {"presets": [2, 3]}, "actions": [block("That message was blocked by the server rules."), alert]},
    {"name": "Holy Lois: spam", "event_type": 1, "trigger_type": 3, "actions": [{"type": 1, "metadata": {}}, alert]},
    {"name": "Holy Lois: mention raids", "event_type": 1, "trigger_type": 5,
     "trigger_metadata": {"mention_total_limit": 5, "mention_raid_protection_enabled": True},
     "actions": [{"type": 1, "metadata": {}}, {"type": 3, "metadata": {"duration_seconds": 3600}}, alert]},
    {"name": "Holy Lois: invites and scams", "event_type": 1, "trigger_type": 1,
     "trigger_metadata": {"keyword_filter": ["*discord.gg/*", "*discord.com/invite*", "*discordapp.com/invite*", "*free nitro*", "*nitro gift*",
                                             "*steamcommunlty*", "*steamcomunity*", "*@everyone free*"],
                          "allow_list": ["discord.gg/NHgjB9rsXW", "discord.gg/FzBJSZwY2c", "holylois.com/discord"]},
     "actions": [block("Invites to other servers and scam links are not allowed here."), alert]},
]
existing = {r["name"]: r for r in api("GET", f"/guilds/{gid}/auto-moderation/rules")}
for rule in wanted:
    body = {**rule, "enabled": True}
    if rule["name"] in existing:
        api("PATCH", f"/guilds/{gid}/auto-moderation/rules/{existing[rule['name']]['id']}", body)
    else:
        try:
            api("POST", f"/guilds/{gid}/auto-moderation/rules", body)
        except RuntimeError as error:
            print("automod rule skipped:", rule["name"], str(error)[:140]); continue
    print("automod:", rule["name"])
print("admin setup done")
