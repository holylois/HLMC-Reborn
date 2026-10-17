"""Thread guard: restarts Minecraft cleanly before its thread count reaches the systemd TasksMax limit.

  thread-guard.py check      every 5 minutes (timer): logs the count, restarts when needed
  thread-guard.py dry-run    prints the decision without acting

Why (2026-10-17): while Chunky pregenerates, Distant Horizons switches its world generator off and back on whenever
Chunky goes quiet for 2 seconds (5,013 times in one 21-hour run). Each switch leaked threads until the service hit
TasksMax (13008), Chunky could not start a thread and the server crashed with two players online.

Empty server at 60% of the limit: quiet restart. Players online: wait until 85%, then the owner-approved one-minute
countdown from hl-deploy.py. At most one guard restart per hour. Skips while a deploy or other maintenance runs.
The restart writes /run/holylois-maintenance, so discord-alert.py posts a calm restart note instead of a crash alarm.
"""
import fcntl, importlib.util, json, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path('/var/lib/holylois/thread-guard.json')
QUIET, URGENT, COOLDOWN = 0.60, 0.85, 3600
REASON = 'a quick health restart'


def kit():
    spec = importlib.util.spec_from_file_location('hl_deploy', HERE / 'hl-deploy.py')
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def tasks():
    out = subprocess.run(['systemctl', 'show', 'minecraft', '-p', 'TasksCurrent', '-p', 'TasksMax', '-p', 'ActiveState'],
                         capture_output=True, text=True, check=True).stdout
    values = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    if values.get('ActiveState') != 'active' or not values.get('TasksCurrent', '').isdigit() or not values.get('TasksMax', '').isdigit():
        return None, None
    return int(values['TasksCurrent']), int(values['TasksMax'])


def decide(current, limit, players, last_restart, now):
    """'restart-quiet', 'restart-countdown' or a reason to wait."""
    if current is None:
        return 'wait: minecraft not active'
    if now - last_restart < COOLDOWN:
        return 'wait: restarted less than an hour ago'
    if players is None:
        return 'wait: no status reply'
    if players == 0 and current >= QUIET * limit:
        return 'restart-quiet'
    if players > 0 and current >= URGENT * limit:
        return 'restart-countdown'
    return 'ok'


def restart(hl, countdown):
    hl.MAINTENANCE.write_text('Quick health restart')
    try:
        subprocess.run(['systemctl', 'stop', 'holylois-terrain-expansion.timer', 'holylois-terrain-expansion.service'], check=False)
        if countdown:
            hl.countdown(hl.helper(), {'reason': REASON, 'launcher_update': False})
        hl.console('save-all flush')
        time.sleep(3)
        hl.run('systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service')
        hl.start(hl.helper(), {'expect_log': []})
    finally:
        hl.MAINTENANCE.unlink(missing_ok=True)
        subprocess.run(['systemctl', 'start', 'holylois-terrain-expansion.timer'], check=False)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'dry-run'
    if mode not in ('check', 'dry-run'):
        raise SystemExit(__doc__)
    hl = kit()
    if hl.MAINTENANCE.exists():
        print('thread-guard: maintenance active, skipped'); return
    with open('/run/hl-deploy.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('thread-guard: a deploy is running, skipped'); return
        current, limit = tasks()
        try:
            players = hl.online_players() if current is not None else None
        except OSError:
            players = None
        try:
            state = json.loads(STATE.read_text())
        except (OSError, ValueError):
            state = {}
        now = time.time()
        action = decide(current, limit, players, state.get('last_restart', 0), now)
        print(f'thread-guard: threads {current}/{limit}, players {players}: {action}', flush=True)
        if mode == 'dry-run' or not action.startswith('restart'):
            return
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({'last_restart': now, 'threads': current, 'limit': limit, 'players': players}))
        restart(hl, action == 'restart-countdown')
        print(f'thread-guard: restarted, threads now {tasks()[0]}', flush=True)


if __name__ == '__main__':
    main()
