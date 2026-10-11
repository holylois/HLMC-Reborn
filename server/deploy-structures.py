"""Structures update (server only, pack unchanged). Run as root from ~/hl-structures; --check validates only and changes nothing.

Same file changes as the passed loopback test (test-structures.py apply_changes): the new structure mods and libraries, BlueMap 5.29,
Polymer 0.18.3, the overlap toggles, legend loot tables and Runeforged chest tiers. Also the faster terrain pacing
(expand-terrain.py, its tests must pass here first), the MOTD headline and the monitor's update/shutdown notes
(discord-alert.py; the maintenance flag now carries the reason players see in #server-status).
Online players get the approved one-minute countdown first. A fresh complete backup is verified before anything changes; if the
server does not come up healthy, mods, config, claims data and the terrain script return automatically. Only after a healthy
start: BlueMap re-renders the map center (lost low-zoom tiles, fixed in 5.29) and the terrain hold file is removed (pregen resumes).
"""
from pathlib import Path
from importlib import util
import datetime, hashlib, json, os, re, shutil, subprocess, sys, tarfile, time


def load(name, path):
    spec = util.spec_from_file_location(name, path); module = util.module_from_spec(spec); spec.loader.exec_module(module); return module


base = load('base', '/home/ubuntu/hl-170/deploy-release-170.py')      # online_players, journal
helpers = load('helpers', '/home/ubuntu/hl-174/deploy-release-174.py')  # console, say, countdown
KIT = Path(__file__).resolve().parent
test = load('teststructures', str(KIT / 'test-structures.py'))           # apply_changes, HASHES, NEW_JARS, REPLACED
ROOT = Path('/opt/minecraft')
MOTD = ROOT / 'config/MiniMOTD/main.conf'
MAINTENANCE = Path('/run/holylois-maintenance')
TERRAIN = Path('/usr/local/lib/holylois/expand-terrain.py')
ALERT = Path('/usr/local/lib/holylois/discord-alert.py')
# Shown in #server-status while the update runs (the monitor reads the maintenance flag).
REASON = 'Adding hundreds of new structures to explore'
HOLD = Path('/opt/minecraft-backups/terrain-expansion/hold')
BAR = 'holylois:restart'
# Server list line under the name: the newest exciting change, capital letter after "New:".
HEADLINE = '<#FFAD42>✦ New:</#FFAD42> <white>Hundreds of new structures out in the wild!</white>'
TREES = [ROOT / 'mods', ROOT / 'config', ROOT / 'world/data/openpartiesandclaims']
CHANGED = ['config/holylois-legends.json', 'config/runeforged-monsters.json', 'config/MiniMOTD/main.conf'] + ['mods/' + n for n in test.REPLACED]
FATAL = ('Failed to start', 'Crash report', 'Incompatible mods', 'Failed to load datapacks', 'Mixin apply failed',
         'Registry loading errors', 'Encountered an unexpected exception', 'could not lock admin-only commands')
MARKERS = ('holylois-extras 1.7.1', 'repurposed_structures 7.8.2', 'mvs 5.1.3', 'structory 1.3.18', 'bluemap 5.29',
           'Holy Lois claims: ready for OPAC', 'holylois_boombox')


def run(*args, **kwargs): return subprocess.run(args, check=True, **kwargs)


def countdown():
    """The approved countdown (boss bar, big numbers, goodbye title, kick with the update hint); only the chat line differs."""
    original = helpers.say
    helpers.say = lambda text: original(text.replace('land claims on the map, zone titles, /support', 'hundreds of new structures out in the wild'))
    try: helpers.countdown()
    finally: helpers.say = original


def start_and_check():
    """Start and wait for Done plus the Holy Lois start-up lines; one more try only for the old REI datapack race."""
    for attempt in (1, 2):
        since = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run('systemctl', 'start', 'minecraft-console.socket', 'minecraft.service')
        log = ''
        for _ in range(600):
            time.sleep(1)
            log = base.journal(since)
            if 'Done (' in log and 'Holy Lois claims: ready for OPAC' in log: break
            if any(needle in log for needle in FATAL): break
        if 'Failed to load datapacks' in log and attempt == 1:
            print('Startup hit the known datapack race; trying once more.', flush=True)
            run('systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service'); continue
        assert 'Done (' in log, 'Server did not finish starting'
        for needle in MARKERS: assert needle in log, 'Missing startup marker: ' + needle
        bad = [needle for needle in FATAL if needle in log]
        assert not bad, 'Startup errors: ' + ', '.join(bad)
        return attempt


def main():
    assert os.geteuid() == 0, 'Run as root'
    assert (KIT / 'test-structures.ok').exists(), 'Isolated loopback test has not passed'
    for name, sha in test.HASHES.items():
        path = KIT / ('jars/' + name if name.endswith('.jar') else name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, 'Artifact hash: ' + name
    live = {p.name for p in (ROOT / 'mods').glob('*.jar')}
    assert set(test.REPLACED) <= live, 'Live BlueMap/Polymer are not the expected ones'
    assert not set(test.NEW_JARS) & live, 'Structure mods are already installed'
    assert len(re.findall(r'(?m)^\s*line2=', MOTD.read_text(encoding='utf-8'))) == 1, 'MOTD line2 not found'
    assert shutil.disk_usage(ROOT).free > 30 * 1024**3, 'Backup space too low'
    tests = subprocess.run([sys.executable, str(KIT / 'test-expand-terrain.py')], cwd=KIT, capture_output=True, text=True)
    assert tests.returncode == 0, 'Terrain tests failed:\n' + tests.stdout[-2000:] + tests.stderr[-2000:]
    print('Terrain tests:', (tests.stderr.strip().splitlines() or ['?'])[-1], flush=True)
    print('Online players:', base.online_players(), flush=True)
    if sys.argv[1:] == ['--check']:
        print('All pre-checks passed; nothing changed.', flush=True); return

    countdown()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/opt/minecraft-backups/maintenance') / ('structures-' + stamp); backup.mkdir(mode=0o700)
    archive = backup / 'complete-server.tar'
    timer_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'holylois-stats.timer']).returncode == 0
    changed = False
    MAINTENANCE.write_text(REASON, encoding='utf-8')
    try:
        run('systemctl', 'stop', 'holylois-stats.timer', 'holylois-stats.service')
        run('systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service')
        for tree in TREES: shutil.copytree(tree, backup / 'trees' / tree.relative_to(ROOT), symlinks=True)
        shutil.copy2(TERRAIN, backup / 'expand-terrain.py'); shutil.copy2(ALERT, backup / 'discord-alert.py')
        print('Creating fresh complete server backup...', flush=True)
        run('tar', '--exclude=minecraft/backups', '-cf', str(archive), '-C', '/opt', 'minecraft'); archive.chmod(0o600)
        with tarfile.open(archive) as tar:
            members = tar.getmembers(); names = {m.name for m in members}
            for name in ('minecraft/world/level.dat', 'minecraft/server.jar', 'minecraft/config', 'minecraft/mods', 'minecraft/EasyAuth',
                         'minecraft/world/data/openpartiesandclaims'):
                assert name in names, 'Missing required backup path ' + name
            assert all(m.offset_data + m.size <= archive.stat().st_size for m in members if m.isfile())
            for rel in CHANGED:
                assert tar.extractfile('minecraft/' + rel).read() == (ROOT / rel).read_bytes(), 'Restore-byte mismatch: ' + rel
        print('Full archive structure, required paths and changed-file restore bytes verified.', flush=True)

        changed = True
        added = test.apply_changes(ROOT, KIT)
        shutil.copy2(KIT / 'expand-terrain.py', TERRAIN); TERRAIN.chmod(0o755)
        shutil.copy2(KIT / 'discord-alert.py', ALERT); ALERT.chmod(0o755)
        text, count = re.subn(r'(?m)^(\s*line2=).*$', lambda m: m.group(1) + json.dumps(HEADLINE, ensure_ascii=False),
                              MOTD.read_text(encoding='utf-8'), count=1)
        assert count == 1; MOTD.write_text(text, encoding='utf-8')
        run('chown', '-R', 'minecraft:minecraft', str(ROOT / 'mods'), str(ROOT / 'config'))
        attempts = start_and_check()
        helpers.console(f'bossbar remove {BAR}', 'gamerule send_command_feedback true')
    except BaseException:
        print('Deployment failed. Restoring mods, config, claims data and the terrain script automatically...', flush=True)
        subprocess.run(['systemctl', 'stop', 'minecraft-console.socket', 'minecraft.service'])
        if changed:
            for tree in TREES:
                saved = backup / 'trees' / tree.relative_to(ROOT)
                if saved.exists():
                    shutil.rmtree(tree, ignore_errors=True); shutil.copytree(saved, tree, symlinks=True)
                    run('chown', '-R', 'minecraft:minecraft', str(tree))
            shutil.copy2(backup / 'expand-terrain.py', TERRAIN); shutil.copy2(backup / 'discord-alert.py', ALERT)
        run('systemctl', 'start', 'minecraft-console.socket', 'minecraft.service')
        print('Rolled back. Complete backup kept at', archive, '- the terrain hold stays in place.', flush=True)
        raise
    finally:
        MAINTENANCE.unlink(missing_ok=True)
        if timer_active: subprocess.run(['systemctl', 'start', 'holylois-stats.timer'])

    # Healthy: re-render the map center (its low-zoom tiles were lost to the race fixed in BlueMap 5.29), then resume the pregen.
    helpers.console('bluemap force-update world 0 0 400')
    HOLD.unlink(missing_ok=True)
    receipt = {'result': 'Done', 'update': 'structures', 'pack': 'unchanged (1.9.4)', 'backup': str(archive), 'start_attempts': attempts,
               'backup_verification': 'complete tar structure, required paths, exact changed-file restore bytes',
               'added': {name: test.HASHES[name] for name in test.NEW_JARS}, 'replaced': test.REPLACED,
               'runeforged_chest_tables_added': len(added), 'terrain': {'pacing': 'run 45 min, rest 2 min, lag rest 10 min', 'hold_removed': not HOLD.exists()},
               'bluemap': 'force-update world 0 0 400', 'motd': HEADLINE}
    for destination in (backup / 'receipt.json', KIT / 'deploy-receipt.json'):
        destination.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)
    subprocess.run(['systemd-run', '--on-active=900', '--unit=holylois-offload-structures', 'systemctl', 'start', 'holylois-offsite-backup.service'])


if __name__ == '__main__':
    main()
