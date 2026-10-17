"""Holy Lois live deploy kit: one tested plan file per change instead of a new script per release.

  sudo python3 hl-deploy.py PLAN.json --check     read-only preflight (players, tested hashes, live state, disk)
  sudo python3 hl-deploy.py PLAN.json --deploy    re-launches itself detached (systemd-run), so the caller can disconnect
  sudo python3 hl-deploy.py PLAN.json --status    shows the detached run's journal

PLAN.json (paths relative to the plan's folder):
  {"name": "libs-221", "reason": "small mod updates", "scope": "jars" | "world",
   "swap": {"old.jar": "new.jar"}, "add": ["extra.jar"], "remove": ["gone.jar"],
   "files": {"config/x.json": "x.json"}, "expect_log": ["fabric-api 0.163.0"],
   "tested": {"new.jar": "sha256", "x.json": "sha256"}, "launcher_update": true}

Backup scope (owner decision 2026-10-16): "jars" backs up mods/ and config/ only (the world is covered by the latest JEB
snapshot and its off-site copy); "world" takes a complete stopped archive without the rebuildable bluemap/ tiles.
Online players get the owner-approved one-minute countdown. Any failure restores the backed-up trees and restarts.
"""
import argparse, datetime, fcntl, hashlib, json, os, shutil, socket, stat, struct, subprocess, sys, tarfile, time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path('/opt/minecraft')
BACKUPS = Path('/opt/minecraft-backups/maintenance')
MAINTENANCE = Path('/run/holylois-maintenance')
HOLD = Path('/opt/minecraft-backups/terrain-expansion/hold')
FIFO = '/run/minecraft-console.fifo'
FATAL = ('Failed to start', 'Crash report', 'Incompatible mods', 'Failed to load datapacks', 'Mixin apply failed',
         'InvalidMixinException', 'Critical injection failure', 'Encountered an unexpected exception')
TIMERS = ('holylois-stats.timer', 'holylois-terrain-expansion.timer', 'holylois-offsite-backup.timer', 'holylois-botwall.timer')
SERVICES = ('holylois-stats.service', 'holylois-terrain-expansion.service', 'holylois-botwall.service')
SCOPES = {'jars': ('mods', 'config'), 'world': None}
COUNTDOWN, BAR = 60, 'holylois:restart'


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_plan(path):
    path = Path(path).resolve()
    plan = json.loads(path.read_text(encoding='utf-8'))
    plan['home'] = path.parent
    if plan.get('scope') not in SCOPES:
        raise ValueError('scope must be "jars" or "world"')
    if not plan.get('name') or not plan['name'].replace('-', '').isalnum():
        raise ValueError('name must be letters, digits and hyphens')
    for key in ('swap', 'files', 'tested'):
        plan.setdefault(key, {})
    for key in ('add', 'remove', 'expect_log'):
        plan.setdefault(key, [])
    sources = list(plan['swap'].values()) + plan['add'] + list(plan['files'].values())
    if not sources and not plan['remove']:
        raise ValueError('plan changes nothing')
    for source in sources:
        if source not in plan['tested']:
            raise ValueError('untested candidate: ' + source)
    for target in plan['files']:
        if Path(target).is_absolute() or '..' in Path(target).parts:
            raise ValueError('config targets must stay inside the server folder: ' + target)
        if plan['scope'] == 'jars' and Path(target).parts[0] not in SCOPES['jars']:
            raise ValueError('a "jars" plan may only change mods/ and config/: ' + target)
    return plan


def changes(plan):
    """(live target, candidate name in the plan folder or None to retire it) for every change, in apply order."""
    out = [(ROOT / 'mods' / old, None) for old in list(plan['swap']) + plan['remove']]
    out += [(ROOT / 'mods' / new, new) for new in list(plan['swap'].values()) + plan['add']]
    out += [(ROOT / target, source) for target, source in plan['files'].items()]
    return out


def varint(value):
    out = bytearray()
    while True:
        b = value & 127; value >>= 7
        out.append(b | (128 if value else 0))
        if not value: return bytes(out)


def online_players():
    # "localhost" from 127.0.0.1: the real count, staff included (onboarding Hidden keeps staff out of public pings only).
    with socket.create_connection(('127.0.0.1', 25565), timeout=5) as s:
        host = b'localhost'
        packet = b'\x00' + varint(0) + varint(len(host)) + host + struct.pack('>H', 25565) + b'\x01'
        s.sendall(varint(len(packet)) + packet + b'\x01\x00')
        data = b''; s.settimeout(5)
        while True:
            chunk = s.recv(65536)
            if not chunk: break
            data += chunk
            start = data.find(b'{')
            if start >= 0:
                try: return json.loads(data[start:].decode('utf-8'))['players']['online']
                except ValueError: continue
    raise IOError('No status reply')


def journal(since):
    return subprocess.run(['journalctl', '-u', 'minecraft', '--since', since, '--no-pager', '-o', 'cat'],
                          capture_output=True, text=True, errors='replace').stdout


def helper():
    return SimpleNamespace(online_players=online_players, journal=journal)


def console(*commands):
    if not stat.S_ISFIFO(os.stat(FIFO, follow_symlinks=False).st_mode):
        raise RuntimeError('Console is not a FIFO')
    fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
    try:
        for text in commands:
            data = (text + '\n').encode()
            if os.write(fd, data) != len(data):
                raise RuntimeError('Incomplete console command')
    finally:
        os.close(fd)


def countdown(base, plan):
    console(f'bossbar remove {BAR}')
    if base.online_players() == 0:
        return
    after = 'then update in the Holy Lois launcher' if plan.get('launcher_update') else 'no update needed'
    console('gamerule send_command_feedback false', f'bossbar add {BAR} ' + json.dumps({'text': 'Server restart'}),
            f'bossbar set {BAR} max {COUNTDOWN}', f'bossbar set {BAR} value {COUNTDOWN}', f'bossbar set {BAR} color yellow',
            f'bossbar set {BAR} style notched_10', f'bossbar set {BAR} players @a', 'title @a times 0 25 5')
    start = time.monotonic()
    for left in range(COUNTDOWN, 0, -1):
        time.sleep(max(0, COUNTDOWN - left - (time.monotonic() - start)))
        label = f'{left} second{"s" if left != 1 else ""}'
        commands = [f'bossbar set {BAR} value {left}', f'bossbar set {BAR} players @a',
                    f'bossbar set {BAR} name ' + json.dumps({'text': f'Server restarting in {label} - {after}',
                                                             'color': 'yellow' if left > 10 else 'red'})]
        if left == 10:
            commands.append(f'bossbar set {BAR} color red')
        if left <= 10:
            commands += ['title @a subtitle ' + json.dumps({'text': f'Back in a few minutes - {after}', 'color': 'yellow'}),
                         'title @a title ' + json.dumps({'text': str(left), 'color': 'gold', 'bold': True}),
                         'execute as @a at @s run playsound minecraft:block.note_block.hat master @s ~ ~ ~ 1 ' + ('2' if left <= 3 else '1')]
        console(*commands)
        if left in (COUNTDOWN, 30, 10):
            console('tellraw @a ' + json.dumps([{'text': '[Holy Lois] ', 'color': 'gold', 'bold': True},
                                                 {'text': f'Server restarts in {label} for {plan["reason"]}; {after}.', 'color': 'yellow', 'bold': False}]))
    console(f'bossbar remove {BAR}', 'gamerule send_command_feedback true', 'title @a times 0 200 0',
            'title @a subtitle ' + json.dumps({'text': 'Back in a few minutes', 'color': 'yellow'}),
            'title @a title ' + json.dumps({'text': 'Holy Lois', 'color': 'gold', 'bold': True}))
    time.sleep(3)
    console(f'kick @a Holy Lois is restarting for {plan["reason"]}. Back in a few minutes, {after}.')
    time.sleep(2)


def check(base, plan):
    if os.geteuid() != 0:
        raise RuntimeError('Root required')
    if MAINTENANCE.exists():
        raise RuntimeError('Another maintenance operation is active')
    for source, digest in plan['tested'].items():
        if sha(plan['home'] / source) != digest:
            raise RuntimeError('Candidate differs from tested bytes: ' + source)
    for target, source in changes(plan):
        if source is None and not target.exists():
            raise RuntimeError('Expected live file missing: ' + target.name)
        if source is not None and target.parent.name == 'mods' and target.exists():
            raise RuntimeError('Candidate already installed: ' + target.name)
    need = 2 * 1024**3 if plan['scope'] == 'jars' else 40 * 1024**3
    if shutil.disk_usage(ROOT).free < need:
        raise RuntimeError('Not enough free disk for the backup')
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'minecraft']).returncode:
        raise RuntimeError('Minecraft is not active')
    result = {'plan': plan['name'], 'scope': plan['scope'], 'players_online': base.online_players(), 'live_changed': False}
    print(json.dumps(result), flush=True)


def backup(plan, folder):
    archive = folder / 'backup.tar'
    trees = SCOPES[plan['scope']]
    if trees:
        run('tar', '-cf', str(archive), '-C', str(ROOT.parent), *(ROOT.name + '/' + t for t in trees))
    else:
        run('tar', f'--exclude={ROOT.name}/backups', f'--exclude={ROOT.name}/bluemap', '-cf', str(archive), '-C', str(ROOT.parent), ROOT.name)
    archive.chmod(0o600)
    compared = subprocess.run(['tar', '--compare', '--file', str(archive), '-C', str(ROOT.parent)], capture_output=True)
    (folder / 'backup-compare-private.log').write_bytes(compared.stdout + b'\n' + compared.stderr)
    if compared.returncode:
        raise RuntimeError('Stopped backup comparison failed')
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    for required in (trees or ('world', 'config', 'mods', 'EasyAuth')):
        if ROOT.name + '/' + required not in names:
            raise RuntimeError('Backup is missing ' + required)
    return {'archive_bytes': archive.stat().st_size, 'archive_sha256': sha(archive), 'scope': plan['scope']}


def restore(plan, folder):
    failed = folder / 'failed'
    failed.mkdir(mode=0o700, exist_ok=True)
    trees = SCOPES[plan['scope']] or ('world', 'config', 'mods', 'EasyAuth')
    for name in trees:
        tree = ROOT / name
        if tree.is_symlink() or tree.resolve().parent != ROOT:
            raise RuntimeError('Unsafe rollback tree')
        if tree.exists():
            shutil.move(str(tree), str(failed / name))
    run('tar', '-xf', str(folder / 'backup.tar'), '-C', str(ROOT.parent), *(ROOT.name + '/' + t for t in trees))


def install(plan, folder):
    for target, source in changes(plan):
        if source is None:
            shutil.move(str(target), str(folder / ('replaced-' + target.name)))
            continue
        temporary = target.with_name(target.name + '.hl-new')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(plan['home'] / source, temporary)
        temporary.chmod(0o644)
        shutil.chown(temporary, user='minecraft', group='minecraft')
        if sha(temporary) != plan['tested'][source]:
            raise RuntimeError('Copied bytes differ: ' + target.name)
        os.replace(temporary, target)


def start(base, plan):
    since = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run('systemctl', 'start', 'minecraft-console.socket', 'minecraft.service')
    for _ in range(600):
        time.sleep(1)
        log = base.journal(since)
        if any(t in log for t in FATAL):
            raise RuntimeError('Startup failure')
        if 'Done (' in log and 'Holy Lois claims: ready for OPAC' in log:
            missing = [t for t in plan['expect_log'] if t not in log]
            if missing:
                raise RuntimeError('Expected startup lines missing: ' + ', '.join(missing))
            return
    raise RuntimeError('Startup deadline exceeded')


def deploy(base, plan):
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'holylois-offsite-backup.service']).returncode == 0:
        raise RuntimeError('Off-site backup running; wait for it')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder = BACKUPS / f'{plan["name"]}-{stamp}'
    folder.mkdir(mode=0o700, parents=True)
    held, backed_up, touched, info = HOLD.exists(), False, False, None
    timers = {u: subprocess.run(['systemctl', 'is-active', '--quiet', u]).returncode == 0 for u in TIMERS}
    MAINTENANCE.write_text(plan['reason'][:1].upper() + plan['reason'][1:])
    try:
        run('systemctl', 'stop', *(t for t in TIMERS if t != 'holylois-stats.timer'), 'holylois-terrain-expansion.service', 'holylois-botwall.service')
        countdown(base, plan)
        console('save-all flush')
        time.sleep(2)
        run('systemctl', 'stop', 'holylois-stats.timer', 'holylois-stats.service')
        run('systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service')
        info = backup(plan, folder)
        backed_up = touched = True
        install(plan, folder)
        start(base, plan)
        if HOLD.exists() != held:
            raise RuntimeError('Terrain hold changed')
    except BaseException:
        run('systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service')
        if touched and backed_up:
            restore(plan, folder)
        run('systemctl', 'start', 'minecraft-console.socket', 'minecraft.service')
        print('Previous server restored; backup and failed candidate kept in ' + str(folder), flush=True)
        raise
    finally:
        MAINTENANCE.unlink(missing_ok=True)
        for unit, active in timers.items():
            if active:
                subprocess.run(['systemctl', 'start', unit], check=False)
    receipt = {'live': True, 'plan': plan['name'], 'backup': info, 'folder': str(folder),
               'installed': {t.name: sha(t) for t, s in changes(plan) if s is not None}}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('plan')
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ('--check', '--deploy', '--status', '--detached'):
        mode.add_argument(flag, action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.plan)
    unit = 'hl-deploy-' + plan['name']
    if args.status:
        print(subprocess.run(['journalctl', '-u', unit, '-o', 'cat', '--no-pager'], capture_output=True, text=True).stdout[-4000:])
        return
    with open('/run/hl-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        base = helper()
        check(base, plan)
        if args.check:
            return
        if args.deploy:
            # Detached: the deploy keeps running if the SSH session or the owner's PC goes away.
            run('systemd-run', '--unit=' + unit, '--collect', '--property=WorkingDirectory=' + str(plan['home']),
                sys.executable, str(Path(__file__).resolve()), str(Path(args.plan).resolve()), '--detached')
            print(f'Launched {unit}; follow with --status.', flush=True)
            return
    with open('/run/hl-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        base = helper()
        check(base, plan)
        deploy(base, plan)


if __name__ == '__main__':
    main()
