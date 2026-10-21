"""Post Holy Lois server down/up alerts to #server-status (through the Holy Lois bot; the webhook is only the fallback).

  discord-alert.py check     every 2 minutes (timer): alerts after two failed status checks, and on recovery
  discord-alert.py failure   OnFailure= hook of minecraft.service: immediate crash report
  discord-alert.py test      sends a test message
  discord-alert.py message TEXT
  discord-alert.py staff-message TEXT   private diagnostics only, never public fallback
Every restart, planned or not, is announced once.

Players read #server-status, so alerts go there through the bot (token /etc/holylois/discord-bot-token, root 600). The old
webhook in /etc/holylois/discord-webhook points at a staff channel and is used only when the bot cannot post.
Without either, every mode exits quietly. During planned work /run/holylois-maintenance holds the reason (deploy scripts write
it, e.g. "Adding new structures"): players get one "restarting for an update" note and a "back online" note after, no alarm.
A deliberate stop (systemctl stop, no crash) is announced as a shutdown by an admin, not as a crash.
Lag watch: one 5s stall or 3+ spikes in 10 minutes with current/recent players sends one private note per hour.
Spark background history is requested at most every 30 minutes, independently of the note cooldown.
"""
import glob, json, os, re, shutil, socket, struct, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

WEBHOOK = Path("/etc/holylois/discord-webhook")
BOT_TOKEN = Path("/etc/holylois/discord-bot-token")
STATUS_CHANNEL = "server-status"
STATE = Path("/var/lib/holylois/discord-alert.json")
MAINTENANCE = Path("/run/holylois-maintenance")
ROOT = Path("/opt/minecraft")
GOLD, RED, GREEN = 0xF4C542, 0xC2362F, 0x34D27B


def bot_api(path, body=None):
    # Discord rate limits per route (429 with retry_after, usually under a second): wait and retry instead of
    # falling back to the staff webhook (the terrain-fix notice of 2026-10-19 landed there this way).
    for _ in range(5):
        request = urllib.request.Request("https://discord.com/api/v10" + path, data=None if body is None else json.dumps(body).encode(),
            headers={"Authorization": "Bot " + BOT_TOKEN.read_text().strip(), "User-Agent": "HolyLoisMonitor/1.1", "Content-Type": "application/json"},
            method="GET" if body is None else "POST")
        try:
            return json.load(urllib.request.urlopen(request, timeout=15))
        except urllib.error.HTTPError as error:
            if error.code != 429: raise
            time.sleep(min(10.0, float(json.loads(error.read() or b"{}").get("retry_after", 1))) + 0.25)
    raise IOError("Discord kept rate limiting")


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


LAG_WINDOW, LAG_STALLS, LAG_QUIET, SPARK_QUIET, BOOT_GRACE = 600, 3, 3600, 1800, 300
LAG_SEVERE_MS, RECENT_PLAYERS, SPARK_RETRY = 5000, 180, 300
LAG_STATE_KEYS = ('lag_alert_at', 'lag_alert_event_us', 'lag_players_at', 'lag_invocation',
                  'spark_at', 'spark_posted', 'spark_event_us', 'spark_retry_at', 'storage')
# Profile links only: spark also prints https://spark.lucko.me/docs/... help links, which once got posted instead.
SPARK_LINK = re.compile(r"https://spark\.lucko\.me/(?!docs\b)[A-Za-z0-9]{6,}\b")
LAG_WARNING = re.compile(r"^\[\d{2}:\d{2}:\d{2}\] \[Server thread/WARN\]: Can't keep up! .*?Running (\d+)ms")


def post_staff(title, description, color, fields=()):
    """Private diagnostics never fall back to the public server-status channel."""
    url = WEBHOOK.read_text().strip() if WEBHOOK.exists() else ""
    if not url.startswith(("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")):
        print('Private staff alert unavailable; diagnostic details withheld from public channels.', file=sys.stderr)
        return False
    embed = {"title": title, "description": description[:3900], "color": color,
             "fields": [{"name": n, "value": v[:1000] or "-", "inline": False} for n, v in fields],
             "footer": {"text": "Holy Lois: Reborn server monitor"}}
    body = json.dumps({"username": "Holy Lois Server", "embeds": [embed], "allowed_mentions": {"parse": []}}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "HolyLoisMonitor/1.2"})
    urllib.request.urlopen(request, timeout=15).read()
    return True


def stalls(since):
    """Lag spikes ("Can't keep up") logged since a time: (count, worst delay in ms)."""
    log = subprocess.run(["journalctl", "-u", "minecraft", "--since", "@%d" % int(since), "-n", "4000", "-o", "cat", "--no-pager"],
                         capture_output=True, text=True, errors="replace").stdout
    delays = [int(m) for m in re.findall(r"Can't keep up! .*?Running (\d+)ms", log)]
    return len(delays), max(delays, default=0), log


def service_started():
    value = subprocess.run(["systemctl", "show", "minecraft", "-p", "ExecMainStartTimestampMonotonic", "--value"],
                           capture_output=True, text=True).stdout.strip()
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    return time.time() - (uptime - int(value) / 1e6) if value.isdigit() and int(value) else 0


def lag_events(since):
    """Only event times/durations escape this bounded journal reader, never player/chat text."""
    result = subprocess.run(['journalctl', '-u', 'minecraft', '--since', '@%d' % int(since),
                             '--no-pager', '-n', '2000', '-o', 'json', '--grep', "Can't keep up!"],
                            capture_output=True, text=True, errors='replace', timeout=15)
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return []  # journalctl grep: no matches, not an evidence-reader failure.
    if result.returncode:
        raise OSError('Lag event journal query failed')
    events = {}
    for line in result.stdout.splitlines():
        row = json.loads(line)
        match = LAG_WARNING.search(row.get('MESSAGE', ''))
        if match:
            stamp = int(row['__REALTIME_TIMESTAMP'])
            if stamp >= since * 1000000:
                events[stamp] = {'at_us': stamp, 'delay_ms': int(match[1])}
    return sorted(events.values(), key=lambda event: event['at_us'])


def lag_watch(state, players):
    """Capture severe/sustained stalls using background history; bound alerts and uploads separately."""
    now = time.time()
    run = state.get('invocation')
    if run and state.get('lag_invocation') not in (None, run):
        for key in LAG_STATE_KEYS:
            if key != 'storage':
                state.pop(key, None)
    if run:
        state['lag_invocation'] = run
    if players:
        state['lag_players_at'] = now
    spark_at = state.get("spark_at")
    if spark_at and not state.get("spark_posted") and now - spark_at > 140:
        links = SPARK_LINK.findall(stalls(spark_at)[2])
        link = links[-1] if links else None
        if link or now - spark_at > 600:
            delivered = post_staff("Holy Lois lag profile", f"Automatic spark profile from the lag alert: {link}" if link
                                   else "The background spark snapshot produced no link; check /spark profiler info before starting another capture.", GOLD)
            if delivered is not False:
                state["spark_posted"] = True
    started = service_started()
    if (now - started < BOOT_GRACE or MAINTENANCE.exists()
            or (not players and now - state.get('lag_players_at', 0) > RECENT_PLAYERS)):
        return
    events = lag_events(max(now - LAG_WINDOW, started + BOOT_GRACE))
    if not events:
        return
    count = len(events)
    worst = max(event['delay_ms'] for event in events)
    latest = events[-1]['at_us']
    if count < LAG_STALLS and worst < LAG_SEVERE_MS:
        return
    presence = f'{players} player(s) online' if players else 'players seen within the last 3 minutes; none online now'
    note = f"{count} lag spikes in the last 10 minutes (worst {worst / 1000:.1f} s), {presence}."
    pending = spark_at and not state.get('spark_posted')
    if (not pending and latest > state.get('spark_event_us', 0) and now - (spark_at or 0) >= SPARK_QUIET
            and now >= state.get('spark_retry_at', 0) and Path('/run/minecraft-console.fifo').exists()):
        try:
            console = os.open('/run/minecraft-console.fifo', os.O_WRONLY | os.O_NONBLOCK)
            try:
                payload = b'spark profiler open\n'
                if os.write(console, payload) != len(payload):
                    raise OSError('Incomplete background history request')
            finally:
                os.close(console)
            state.update(spark_at=now, spark_posted=False, spark_event_us=latest)
            state.pop('spark_retry_at', None)
            note += " Spark's background history was requested; its link follows here."
        except OSError:
            state['spark_retry_at'] = now + SPARK_RETRY
            note += ' Background history request failed; bounded retry will follow.'
    if latest > state.get('lag_alert_event_us', 0) and now - state.get('lag_alert_at', 0) >= LAG_QUIET:
        if post_staff('Holy Lois server is lagging', note, RED) is not False:
            state.update(lag_alert_at=now, lag_alert_event_us=latest)


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"up": True, "failures": 0, "down_since": None}


def storage_watch(state):
    """Private capacity warnings only. Never prune backups, tiles or rehearsal evidence."""
    disk = shutil.disk_usage(ROOT)
    pressure = 1 - disk.free / disk.total
    level = 3 if pressure >= .95 or disk.free < 10 * 1024**3 else 2 if pressure >= .90 else (
        1 if pressure >= .80 or disk.free < 40 * 1024**3 else 0)
    previous = state.get('storage', {})
    now = time.time()
    if level == 0 and not (pressure < .75 and disk.free >= 45 * 1024**3):
        return  # Hysteresis avoids repeated warnings around a threshold.
    if level == previous.get('level', 0):
        return
    if previous.get('retry_at', 0) > now:
        return
    description = (f"Available {disk.free / 1024**3:.1f} GiB of {disk.total / 1024**3:.1f} GiB. "
                   f"Capacity pressure {pressure:.0%}. "
                   + ('Space has recovered.' if level == 0 else
                      'Review local staging, restore copies and verified off-site receipts. '
                      'World deployments require 40 GiB available. Nothing was deleted.'))
    try:
        delivered = post_staff('Holy Lois storage recovered' if level == 0 else 'Holy Lois storage needs attention',
                               description, GREEN if level == 0 else RED if level >= 2 else GOLD)
    except Exception:
        state['storage'] = {**previous, 'retry_at': now + 900}
        raise
    if delivered is False:
        state['storage'] = {**previous, 'retry_at': now + 900}
    else:
        state['storage'] = {'level': level}


def save(state):
    STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def service():
    """(ActiveState, Result) of minecraft.service, e.g. ("inactive", "success") after a deliberate stop."""
    out = subprocess.run(["systemctl", "show", "minecraft", "-p", "ActiveState", "-p", "Result", "--value"], capture_output=True, text=True).stdout.split()
    return (out + ["", ""])[:2]


def report_down(state, reason):
    status, crash, health, tail = diagnostics()
    since = time.strftime('%d.%m %H:%M UTC', time.gmtime(state['down_since']))
    # Players get the short version; logs and stack traces go to the private staff channel only.
    post("Holy Lois server is DOWN", f"{reason}\nSince {since}. The admins are on it.", RED, ping=True)
    post_staff("Holy Lois server is DOWN (details)", f"{reason}\nSince {since}.", RED,
               [("Service", status), ("Crash report", crash or "No recent crash report."), ("Recent errors", f"```{tail[-900:]}```"),
                ("Health", health), ("What to do", advice(crash, health))])


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode == "test":
        post("Holy Lois monitor test", "Alerts are connected. You will hear from me when the server goes down and when it is back.", GOLD)
        return
    if mode == "message":
        post("Holy Lois server", " ".join(sys.argv[2:]), GOLD)
        return
    if mode == "staff-message":
        if not post_staff("Holy Lois backup or operations alert", " ".join(sys.argv[2:]), RED):
            raise RuntimeError('Private staff destination is unavailable')
        return
    state = load()
    if mode == 'check':
        try:
            storage_watch(state)
        except Exception as error:
            print('Storage watch failed (' + type(error).__name__ + ').', file=sys.stderr)
        save(state)
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
            post("Holy Lois server crashed and restarted itself", f"It is back up with {players} player(s) online.", GOLD)
            post_staff("Holy Lois crash details", f"Back up with {players} player(s) online.", GOLD,
                       [("Crash report", crash or "No recent crash report."), ("Recent errors", f"```{tail[-900:]}```"), ("Health", health)])
        elif restarted:
            # Planned restarts (updates, the owner's restart button) get a short friendly note.
            post("Holy Lois server restarted", f"Back up with {players} player(s) online.", GREEN)
        fresh = {"up": True, "failures": 0, "down_since": None, "restarts": restarts, "invocation": run,
                 **{k: state[k] for k in LAG_STATE_KEYS if k in state}}
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
