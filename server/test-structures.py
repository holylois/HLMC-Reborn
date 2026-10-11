"""Boot an isolated loopback copy of the live server with the structures update, check its log, locate results and configs, stop it.

Run as root from ~/hl-structures. Never touches /opt/minecraft except to read it. Port 25566, voice 24455, Just Enough Backups off,
spawn region files plus the Open Parties and Claims data. Same changes as the deploy (apply_changes): the new structure mods
(Hopo Better Mineshaft/Underwater Ruins/Ruined Portals, Repurposed Structures, Structory, Structory: Towers, MVS, MES,
Villages&Pillages, Sparse Structures and their libraries), BlueMap 5.29, Polymer 0.18.3, the overlap toggles, the legend loot
tables and the Runeforged chest tiers for the new chests. Exit code 0 means every check passed.
"""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path

HOME = Path(__file__).resolve().parent
r = Path('/opt/minecraft'); t = Path('/opt/minecraft-test-structures'); UNIT = 'minecraft-test-structures'
HASHES = json.loads((HOME / 'artifact-hashes.json').read_text())
REPLACED = {'bluemap-5.28-fabric.jar': 'bluemap-5.29-fabric.jar', 'polymer-bundled-0.18.2+26.3.jar': 'polymer-bundled-0.18.3+26.3.jar'}
NEW_JARS = sorted(name for name in HASHES if name.endswith('.jar') and name not in REPLACED.values())
LEGEND_TABLES = ["*:chests/*", "kaisyn:village/*", "kaisyn:outpost/*", "mvs:*", "mes:end_*", "mes:mega_ship_*",
                 "structory:outcast/*", "structory:harvest/*", "structory:library/*", "structory:mood/*", "structory:ruin/*", "structory:extra/*",
                 "structory_towers:basic/*", "structory_towers:top/*", "structory_towers:end_tower", "structory_towers:workshop_minecart",
                 "villagesandpillages:village_witch/*"]
FOUND = ['hopo:mineshaft/oak_mineshaft', 'mvs:castle_ruins', 'structory:abandoned_chapel', 'structory_towers:engineer_tower',
         'villagesandpillages:village_witch', 'repurposed_structures:village_oak', 'nova_structures:tavern_oak']
GONE = ['repurposed_structures:village_birch', 'repurposed_structures:outpost_oak', 'repurposed_structures:mineshaft_birch', 'minecraft:mineshaft']


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def apply_changes(root, source):
    """The structures update file changes, shared with deploy-structures.py. root is the server folder to change."""
    mods = root / 'mods'
    for old, new in REPLACED.items():
        assert (mods / old).exists(), 'Live jar missing: ' + old
        (mods / old).unlink()
    for name in NEW_JARS + list(REPLACED.values()):
        jar = source / 'jars' / name; assert digest(jar) == HASHES[name], name; shutil.copy2(jar, mods / name)
    toggles = root / 'config/cristellib/repurposed_structures'; toggles.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / 'cristellib/repurposed_structures/structure_toggle_config.json5', toggles / 'structure_toggle_config.json5')
    shutil.copy2(source / 'sparsestructures.json5', root / 'config/sparsestructures.json5')
    # Legend items may roll in every structure chest, also the mods that do not use chests/ paths; only real fishing crates are crates.
    p = root / 'config/holylois-legends.json'; legends = json.loads(p.read_text(encoding='utf-8'))
    legends['chestTables'] = LEGEND_TABLES; legends['crateTables'] = ['fishing_crates:*']
    p.write_text(json.dumps(legends, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Runes in the new structure chests (and Towns and Towers, missing so far), by tier; existing entries stay as they are.
    p = root / 'config/runeforged-monsters.json'; monsters = json.loads(p.read_text())
    known = {e['loot_table'] for e in monsters['chest_loot_tables']}
    added = [e for e in json.loads((source / 'runeforged-workshop-additions.json').read_text()) if e['loot_table'] not in known]
    monsters['chest_loot_tables'] += added
    p.write_text(json.dumps(monsters, indent=1) + '\n')
    # BlueMap 5.29 upgrade note: the webapp is rewritten when its index.html is gone.
    (root / 'bluemap/web/index.html').unlink(missing_ok=True)
    return added


def console(fifo, *commands):
    with open(fifo, 'w') as stream:
        for c in commands: stream.write(c + '\n')


if __name__ == '__main__':
    subprocess.run(['systemctl', 'stop', UNIT], stderr=subprocess.DEVNULL)
    subprocess.run(['systemctl', 'reset-failed', UNIT], stderr=subprocess.DEVNULL)
    if t.exists(): shutil.rmtree(t)
    t.mkdir(mode=0o750)
    for name in ['server.jar', 'eula.txt']: shutil.copy2(r / name, t / name)
    shutil.copytree(r / 'mods', t / 'mods'); shutil.copytree(r / 'config', t / 'config')
    if (r / '.fabric').exists(): shutil.copytree(r / '.fabric', t / '.fabric')
    added = apply_changes(t, HOME)
    world = t / 'world'; world.mkdir()
    shutil.copy2(r / 'world/level.dat', world / 'level.dat')
    (world / 'data/minecraft').mkdir(parents=True)
    shutil.copy2(r / 'world/data/minecraft/world_gen_settings.dat', world / 'data/minecraft/world_gen_settings.dat')
    shutil.copytree(r / 'world/data/openpartiesandclaims', world / 'data/openpartiesandclaims')
    claim_files = sum(1 for _ in (world / 'data/openpartiesandclaims').rglob('*') if _.is_file())
    shutil.copytree(r / 'world/datapacks', world / 'datapacks')
    regions = r / 'world/dimensions/minecraft/overworld/region'
    region = world / regions.relative_to(r / 'world'); region.mkdir(parents=True)
    for source in regions.glob('r.*.*.mca'):
        parts = source.name.split('.')
        if abs(int(parts[1])) <= 1 and abs(int(parts[2])) <= 1: shutil.copy2(source, region / source.name)
    (t / 'server.properties').write_text('server-ip=127.0.0.1\nserver-port=25566\nonline-mode=true\nenforce-secure-profile=false\nmax-players=1\n'
                                         'view-distance=2\nsimulation-distance=2\nlevel-name=world\npause-when-empty-seconds=0\n')
    p = t / 'config/voicechat/voicechat-server.properties'; p.write_text(p.read_text().replace('port=24454', 'port=24455').replace('bind_address=\n', 'bind_address=127.0.0.1\n'))
    p = t / 'config/justenoughbackups.json'; j = json.loads(p.read_text()); j['automaticBackupsEnabled'] = False; p.write_text(json.dumps(j))
    # BlueMap must not serve or render on the test copy.
    p = t / 'config/bluemap/webserver.conf'; p.write_text(p.read_text().replace('enabled: true', 'enabled: false', 1))
    fifo = t / 'console.fifo'; subprocess.run(['mkfifo', str(fifo)], check=True)
    subprocess.run(['chown', '-R', 'minecraft:minecraft', str(t)], check=True)
    subprocess.Popen(['setsid', 'sh', '-c', f'exec sleep 1200 > {fifo}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(['systemd-run', f'--unit={UNIT}', '--uid=minecraft', '--gid=minecraft', '--property=WorkingDirectory=' + str(t),
                    f'--property=StandardInput=file:{fifo}', '--property=RuntimeMaxSec=900', '--property=KillSignal=SIGINT',
                    '--property=TimeoutStopSec=30', '/usr/lib/jvm/java-25-openjdk-arm64/bin/java', '-Xms256M', '-Xmx2G',
                    '-jar', 'server.jar', 'nogui'], check=True)
    print('Test server launched on loopback 25566 with', len(NEW_JARS), 'new jars,', len(added), 'new rune chest tables; waiting...', flush=True)

    latest = t / 'logs/latest.log'; log = ''
    for _ in range(600):
        time.sleep(1)
        log = latest.read_text(errors='replace') if latest.exists() else ''
        if 'Done (' in log or 'Crash report' in log or 'Incompatible mods' in log or 'Failed to start' in log or 'Failed to load datapacks' in log: break
        if subprocess.run(['systemctl', 'is-active', '--quiet', UNIT]).returncode != 0 and latest.exists(): break
    started = 'Done (' in log
    if started:
        for s in FOUND: console(fifo, 'locate structure ' + s); time.sleep(6)
        # Switched-off sets are searched far from the copied spawn regions, whose old chunks still hold vanilla mineshafts.
        for s in GONE: console(fifo, 'execute positioned 9000 64 9000 run locate structure ' + s); time.sleep(6)
        time.sleep(30)
        console(fifo, 'save-all flush'); time.sleep(8)
    subprocess.run(['systemctl', 'stop', UNIT])
    time.sleep(2); log = latest.read_text(errors='replace') if latest.exists() else log
    shutil.copy2(latest, HOME / 'test-structures-latest.log') if latest.exists() else None
    errors = [l for l in log.splitlines() if '/ERROR]' in l or '/FATAL]' in l]
    rei = sum('[REI] Failed to fill display' in l for l in errors)
    errors = [l for l in errors if '[REI] Failed to fill display' not in l]
    claims_after = sum(1 for _ in (world / 'data/openpartiesandclaims').rglob('*') if _.is_file())
    found = {s for s in FOUND if f'The nearest {s} is at' in log}
    gone = {s for s in GONE if f'The nearest {s} is at' not in log and s in log}
    toggles = (t / 'config/cristellib/repurposed_structures/structure_toggle_config.json5').read_text(encoding='utf-8')
    sparse = (t / 'config/sparsestructures.json5').read_text(encoding='utf-8')
    monsters = json.loads((t / 'config/runeforged-monsters.json').read_text())
    legends = json.loads((t / 'config/holylois-legends.json').read_text(encoding='utf-8'))

    wanted = {'repurposed_structures': '7.8.2', 'mvs': '5.1.3', 'mes': '2.1.1', 'structory': '1.3.18', 'structory_towers': '1.0.19',
              'villagesandpillages': '2.0.0', 'sparsestructures': '3.1.5', 'midnightlib': '1.9.3', 'bluemap': '5.29', 'polymer-bundled': '0.18.3',
              'holylois-extras': '1.7.1', 'holylois-onboarding': '1.9.1', 'mr_dungeons_andtaverns': '6.0.2', 'hopobettermineshaft': '1.3.8', 'moogs_structures': '3.4.2', 't_and_t': '1.13.12'}
    listed = [l.split('- ', 1)[1] for l in log.splitlines() if l.lstrip(' \t|-').startswith(tuple(wanted)) and '- ' in l]
    missing = [mod for mod, version in wanted.items() if not any(x.startswith(mod + ' ') and version in x for x in listed)]
    checks = {'server started': started,
              'new and kept mods loaded': not missing,
              'onboarding ready (claims line)': 'Holy Lois claims: ready for OPAC' in log,
              'OPAC data kept after save and stop': claims_after >= claim_files > 0,
              'new structures located': found == set(FOUND),
              'duplicates switched off (RS birch village/outposts/mineshafts, vanilla mineshaft)': gone == set(GONE),
              'RS toggles kept after first boot': toggles.count(': false') >= 29,
              'Sparse Structures neutral (factor 1, original salts)': '"spreadFactor": 1' in sparse and '"idBasedSalt": false' in sparse,
              'Runeforged tiers merged': sum(e['loot_table'].startswith('mvs:') for e in monsters['chest_loot_tables']) > 10,
              'legend chest tables set': legends['chestTables'] == LEGEND_TABLES and legends['crateTables'] == ['fishing_crates:*'],
              'no datapack or registry errors': 'Registry loading errors' not in log and 'Failed to load datapacks' not in log,
              'no mixin or loader errors': 'Mixin apply failed' not in log and 'Incompatible mods' not in log,
              'no other ERROR lines': not errors}
    width = max(map(len, checks))
    for name, ok in checks.items(): print(f'{name:<{width}}  {"OK" if ok else "FAILED"}')
    print('Missing load lines:', missing)
    print('Located:', sorted(found), '| switched off:', sorted(gone))
    print('REI brewing display errors (same in every dev run):', rei)
    print('Other ERROR lines:', len(errors)); [print('  ', l[:220]) for l in errors[:25]]
    print('Log copy:', HOME / 'test-structures-latest.log')
    shutil.rmtree(t, ignore_errors=True)
    (HOME / 'test-structures.ok').unlink(missing_ok=True)
    if all(checks.values()): (HOME / 'test-structures.ok').write_text('passed')
    sys.exit(0 if all(checks.values()) else 1)
