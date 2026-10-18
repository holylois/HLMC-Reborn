"""Post Holy Lois server down/up alerts to #server-status (through the Holy Lois bot; the webhook is only the fallback).

  discord-alert.py check     every 2 minutes (timer): alerts after two failed status checks, and on recovery
  discord-alert.py failure   OnFailure= hook of minecraft.service: immediate crash report
  discord-alert.py test      sends a test message
  discord-alert.py message TEXT
Every restart, planned or not, is announced once.

Players read #server-status, so alerts go there through the bot (token /etc/holylois/discord-bot-token, root 600). The old
webhook in /etc/holylois/discord-webhook points at a staff channel and is used only when the bot cannot post.
Without either, every mode exits quietly. During planned work /run/holylois-maintenance holds the reason (deploy scripts write
it, e.g. "Adding new structures"): players get one "restarting for an update" note and a "back online" note after, no alarm.
A deliberate stop (systemctl stop, no crash) is announced as a shutdown by an admin, not as a crash.
Lag watch: 3+ "Can't keep up" spikes in 10 minutes with players online sends one admin note per hour (staff webhook) and
starts a 2-minute spark profile at most every 6 hours; the profile link follows on a later check.
"""
import glob, json, os, re, shutil, socket, struct, subprocess, sys, time, urllib.request
from pathlib import Path

WEBHOOK = Path("/etc/holylois/discord-webhook")
BOT_TOKEN = Path("/etc/holylois/discord-bot-token")
STATUS_CHANNEL = "server-status"
STATE = Path("/var/lib/holylois/discord-alert.json")
MAINTENANCE = Path("/run/holylois-maintenance")
ROOT = Path("/opt/minecraft")
GOLD, RED, GREEN = 0xF4C542, 0xC2362F, 0x34D27B


def bot_api(path, body=None):
    request = urllib.request.Request("https://discord.com/api/v10" + path, data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bot " + BOT_TOKEN.read_text().strip(), "User-Agent": "HolyLoisMonitor/1.1", "Content-Type": "application/json"},
        method="GET" if body is None else "POST")
    return json.load(urllib.request.urlopen(request, timeout=15))


def status_channel():
    """The id of #server-status in the bot's guild (plain or with an emoji prefix like "🟢・server-status")."""
    guild = bot_api("/users/@me/guilds")[0]
    return next(c["id"] for c in bot_api(f"/guilds/{guild['id']}/channels") if c["name"] == STATUS_CHANNEL or c["name"].endswith("・" + STATUS_CHANNEL))


def restarts_role():
    """The opt-in "Restarts" ping role from #roles, or None."""
    guild = bot_api("/users/@me/guilds")[0]
    return next((r["id"] for r in bot_api(f"/guilds/{guild['id']}/roles") if r["name"] == "Restarts"), None)


def post(title, description, color, fields=(), ping=False):
    embed = {"title": title, "description": description[:3900], "color": color,
             "fields": [{"name": n, "value": v[:1000] or "-", "inline": False} for n, v in fields],
             "footer": {"text": "Holy Lois: Reborn server monitor"}}
    if BOT_TOKEN.exists():
        try:
            role = restarts_role() if ping else None
            body = {"embeds": [embed], "allowed_mentions": {"parse": [], "roles": [role] if role else []}}
            if role: body["content"] = f"<@&{role}>"
            bot_api(f"/channels/{status_channel()}/messages", body)
            return
        except Exception as error:
            print("Bot post failed (" + type(error).__name__ + "); using the webhook.")
    if not WEBHOOK.exists():
        print("No Discord webhook configured; nothing sent.")
        return
    url = WEBHOOK.read_text().strip()
    if not url.startswith("https://discord.com/api/webhooks/") and not url.startswith("https://discordapp.com/api/webhooks/"):
        print("The webhook file does not contain a Discord webhook URL.")
        return
    body = json.dumps({"username": "Holy Lois Server", "avatar_url": "https://holylois.com/apple-touch-icon.png", "embeds": [embed]}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "HolyLoisMonitor/1.0"})
    urllib.request.urlopen(request, timeout=15).read()


def varint(value):
    out = bytearray()
    while True:
        b = value & 127; value >>= 7
        out.append(b | (128 if value else 0))
        if not value:
            return bytes(out)


def online():
    """Returns the online player count, or None when the server does not answer a status ping."""
    try:
        with socket.create_connection(("127.0.0.1", 25565), timeout=8) as s:
            host = b"localhost"
            packet = b"\x00" + varint(0) + varint(len(host)) + host + struct.pack(">H", 25565) + b"\x01"
            s.sendall(varint(len(packet)) + packet + b"\x01\x00")
            data, deadline = b"", time.time() + 8
            while time.time() < deadline:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                start = data.find(b"{")
                if start >= 0:
                    try:
                        return json.loads(data[start:].decode("utf-8"))["players"]["online"]
                    except ValueError:
                        continue
    except OSError:
        return None
    return None


def diagnostics():
    status = subprocess.run(["systemctl", "show", "minecraft", "-p", "ActiveState,SubState,Result,NRestarts,ExecMainStatus"],
                            capture_output=True, text=True).stdout.strip().replace("\n", ", ")
    journal = subprocess.run(["journalctl", "-u", "minecraft", "-n", "400", "--no-pager", "-o", "cat"],
                             capture_output=True, text=True, errors="replace").stdout.splitlines()
    errors = [l for l in journal if any(k in l for k in ("ERROR", "Exception", "FATAL", "Caused by", "OutOfMemory", "Crash"))]
    crash = ""
    reports = sorted(glob.glob(str(ROOT / "crash-reports" / "*.txt")), key=os.path.getmtime)
    if reports and time.time() - os.path.getmtime(reports[-1]) < 3600:
        text = Path(reports[-1]).read_text(errors="replace").splitlines()
        description = next((l for l in text if l.startswith("Description:")), "Description: unknown")
        first = next((i for i, l in enumerate(text) if l.strip() and l[0] not in "-/ " and "Exception" in l), None)
        crash = description + ("\n" + "\n".join(text[first:first + 6]) if first is not None else "") + f"\n({Path(reports[-1]).name})"
    disk = shutil.disk_usage("/")
    memory = Path("/proc/meminfo").read_text().split("\n")
    available = next((l.split()[1] for l in memory if l.startswith("MemAvailable")), "0")
    health = f"Disk free {disk.free / 1024**3:.1f} GB, memory available {int(available) / 1024**2:.1f} GB"
    log_tail = "\n".join((errors or journal)[-12:])
    return status, crash, health, log_tail


def advice(crash, health):
    tips = ["It usually restarts by itself within a minute; this channel says when it is back."]
    if "OutOfMemory" in crash:
        tips.append("Out of memory: someone may have loaded a huge area. Check /spark health after it is back.")
    if "Disk free 0." in health or "Disk free 1." in health:
        tips.append("The disk is almost full. Free space before the next backup.")
    tips.append("If it stays down, open Holy Lois Admin > Server start / stop / update > Status and Logs, or send this message to the assistant.")
    return "\n".join(f"- {t}" for t in tips)


def invocation():
    """systemd gives every start of the service a new id, so any restart is noticed."""
    return subprocess.run(["systemctl", "show", "minecraft", "-p", "InvocationID", "--value"], capture_output=True, text=True).stdout.strip() or None


def restart_count():
    value = subprocess.run(["systemctl", "show", "minecraft", "-p", "NRestarts", "--value"], capture_output=True, text=True).stdout.strip()
    return int(value) if value.isdigit() else 0


LAG_WINDOW, LAG_STALLS, LAG_QUIET, SPARK_QUIET, BOOT_GRACE = 600, 3, 3600, 6 * 3600, 300
# Profile links only: spark also prints https://spark.lucko.me/docs/... help links, which once got posted instead.
SPARK_LINK = re.compile(r"https://spark\.lucko\.me/(?!docs\b)[A-Za-z0-9]{6,}\b")


def post_staff(title, description, color, fields=()):
    """Admin notes (lag, profiles) go to the staff webhook; without it they fall back to #server-status."""
    url = WEBHOOK.read_text().strip() if WEBHOOK.exists() else ""
    if not url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        post(title, description, color, fields)
        return
    embed = {"title": title, "description": description[:3900], "color": color,
             "fields": [{"name": n, "value": v[:1000] or "-", "inline": False} for n, v in fields],
             "footer": {"text": "Holy Lois: Reborn server monitor"}}
    body = json.dumps({"username": "Holy Lois Server", "embeds": [embed], "allowed_mentions": {"parse": []}}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "HolyLoisMonitor/1.2"})
    urllib.request.urlopen(request, timeout=15).read()


def stalls(since):
    """Lag spikes ("Can't keep up") logged since a time: (count, worst delay in ms)."""
    log = subprocess.run(["journalctl", "-u", "minecraft", "--since", "@%d" % int(since), "-o", "cat", "--no-pager"],
                         capture_output=True, text=True, errors="replace").stdout
    delays = [int(m) for m in re.findall(r"Can't keep up! .*?Running (\d+)ms", log)]
    return len(delays), max(delays, default=0), log


def service_started():
    value = subprocess.run(["systemctl", "show", "minecraft", "-p", "ExecMainStartTimestampMonotonic", "--value"],
                           capture_output=True, text=True).stdout.strip()
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    return time.time() - (uptime - int(value) / 1e6) if value.isdigit() and int(value) else 0


def lag_watch(state, players):
    """Sustained stalls with players online: one admin alert per hour and an automatic 2-minute spark profile at most
    every 6 hours, whose link is posted on a later check. Empty-server stalls (pregen) and boot stalls are ignored."""
    now = time.time()
    spark_at = state.get("spark_at")
    if spark_at and not state.get("spark_posted") and now - spark_at > 140:
        links = SPARK_LINK.findall(stalls(spark_at)[2])
        link = links[-1] if links else None
        if link or now - spark_at > 600:
            post_staff("Holy Lois lag profile", f"Automatic spark profile from the lag alert: {link}" if link
                       else "The automatic spark profile produced no link; run /spark profiler start --timeout 120 in game.", GOLD)
            state["spark_posted"] = True
    if not players or now - service_started() < BOOT_GRACE or now - state.get("lag_alert_at", 0) < LAG_QUIET:
        return
    count, worst, _ = stalls(now - LAG_WINDOW)
    if count < LAG_STALLS:
        return
    state["lag_alert_at"] = now
    note = f"{count} lag spikes in the last 10 minutes (worst {worst / 1000:.1f} s) with {players} player(s) online."
    if now - (spark_at or 0) > SPARK_QUIET and Path("/run/minecraft-console.fifo").exists():
        console = os.open("/run/minecraft-console.fifo", os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(console, b"spark profiler start --timeout 120\n")
        finally:
            os.close(console)
        state.update(spark_at=now, spark_posted=False)
        note += " A 2-minute spark profile started; its link follows here."
    post_staff("Holy Lois server is lagging", note, RED)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"up": True, "failures": 0, "down_since": None}


def save(state):
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def service():
    """(ActiveState, Result) of minecraft.service, e.g. ("inactive", "success") after a deliberate stop."""
    out = subprocess.run(["systemctl", "show", "minecraft", "-p", "ActiveState", "-p", "Result", "--value"], capture_output=True, text=True).stdout.split()
    return (out + ["", ""])[:2]


def report_down(state, reason):
    status, crash, health, tail = diagnostics()
    post("Holy Lois server is DOWN", f"{reason}\nSince {time.strftime('%d.%m %H:%M UTC', time.gmtime(state['down_since']))}.", RED,
         [("Service", status), ("Crash report", crash or "No recent crash report."), ("Recent errors", f"```{tail[-900:]}```"),
          ("Health", health), ("What to do", advice(crash, health))], ping=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "test":
        post("Holy Lois monitor test", "Alerts are connected. You will hear from me when the server goes down and when it is back.", GOLD)
        return
    if mode == "message":
        post("Holy Lois server", " ".join(sys.argv[2:]), GOLD)
        return
    state = load()
    if MAINTENANCE.exists():
        # Planned work: one friendly note with the reason, no crash alarm.
        if not state.get("maintenance"):
            try: reason = MAINTENANCE.read_text(encoding="utf-8").strip()
            except OSError: reason = ""
            reason = reason or "Planned maintenance"
            post("Holy Lois server is restarting for an update", f"{reason}. Back in a few minutes.", GOLD, ping=True)
            state.update(maintenance=reason, maintenance_since=time.time()); save(state)
        print("Planned maintenance; alerts paused.")
        return
    if mode == "failure":
        if state["up"]:
            state.update(up=False, down_since=time.time(), alerted=True)
            save(state)
            report_down(state, "The Minecraft service crashed or exited with an error.")
        return
    restarts = restart_count()
    run = invocation()
    players = online()
    if players is not None:
        restarted = state.get("invocation") not in (None, run)
        if state.get("maintenance"):
            minutes = int((time.time() - state.get("maintenance_since", time.time())) / 60)
            post("Holy Lois server is back online", f"Update done: {state['maintenance']}. Down for about {minutes} minute(s). {players} player(s) online.", GREEN)
        elif not state["up"] and state.get("alerted"):
            minutes = int((time.time() - (state["down_since"] or time.time())) / 60)
            post("Holy Lois server is back online", f"Down for about {minutes} minute(s). {players} player(s) online.", GREEN)
        elif restarts > state.get("restarts", restarts):
            # A crash that restarted between two checks: report it once, with its crash report.
            status, crash, health, tail = diagnostics()
            post("Holy Lois server crashed and restarted itself", f"It is back up with {players} player(s) online.", GOLD,
                 [("Crash report", crash or "No recent crash report."), ("Recent errors", f"```{tail[-900:]}```"), ("Health", health)])
        elif restarted:
            # Planned restarts (updates, the owner's restart button) get a short friendly note.
            post("Holy Lois server restarted", f"Back up with {players} player(s) online.", GREEN)
        fresh = {"up": True, "failures": 0, "down_since": None, "restarts": restarts, "invocation": run,
                 **{k: state[k] for k in ("lag_alert_at", "spark_at", "spark_posted") if k in state}}
        try:
            lag_watch(fresh, players)
        except Exception as error:
            print("Lag watch skipped (" + type(error).__name__ + ").")
        save(fresh)
        return
    state["restarts"] = restarts
    state.pop("maintenance", None)
    active, result = service()
    if state["up"] and active in ("inactive", "failed") and result == "success":
        # Stopped on purpose (systemctl stop): say so, without crash diagnostics.
        state.update(up=False, down_since=time.time(), alerted=True, failures=0)
        post("Holy Lois server was shut down", "An admin stopped the server on purpose. It will be back later.", GOLD)
        save(state); return
    state["failures"] = state.get("failures", 0) + 1
    if state["up"] and state["failures"] >= 2:
        state.update(up=False, down_since=time.time() - 240, alerted=True)
        report_down(state, "The server stopped answering status checks for about 4 minutes.")
    save(state)


if __name__ == "__main__":
    main()
