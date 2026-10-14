"""Install the passed server-only density config. --check reads only; --deploy needs owner approval.

Refuses online players, verifies a full backup before installation, and restores the prior state on failed startup.
No MOTD, public release announcement, client pack, launcher, mod jar or terrain-hold changes.
Run from the private preparation directory containing the candidate config and test-receipt.json.
"""
from pathlib import Path
import argparse, datetime, fcntl, hashlib, importlib.util, json, os, shutil, stat, subprocess, tarfile, time

HOME = Path(__file__).resolve().parent
ROOT = Path('/opt/minecraft')
TARGET = ROOT/'config/sparsestructures.json5'
SOURCE = HOME/'sparsestructures.json5'
FIFO = Path('/run/minecraft-console.fifo')
MAINTENANCE = Path('/run/holylois-maintenance')
HOLD = Path('/opt/minecraft-backups/terrain-expansion/hold')
FATAL = ('Failed to start','Crash report','Incompatible mods','Failed to load datapacks','Mixin apply failed',
         'Registry loading errors','Encountered an unexpected exception')

def run(*args, **kwargs): return subprocess.run(args, check=True, **kwargs)
def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): result.update(block)
    return result.hexdigest()
def console(command):
    assert stat.S_ISFIFO(FIFO.stat().st_mode)
    with FIFO.open('w') as stream: stream.write(command+'\n')
def helpers():
    path = Path('/home/ubuntu/hl-170/deploy-release-170.py')
    spec = importlib.util.spec_from_file_location('density_previous', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
def precheck(base):
    assert os.geteuid() == 0, 'Run as root'
    assert not MAINTENANCE.exists(), 'Another maintenance operation is active'
    assert not TARGET.is_symlink() and TARGET.resolve().parent == ROOT/'config'
    receipt = json.loads((HOME/'test-receipt.json').read_text())
    assert receipt['live_changed'] is False and all(receipt['checks'].values())
    assert sha(SOURCE) == receipt['candidate_sha256'], 'Candidate differs from the passing test'
    assert sha(TARGET) == receipt['live_sha256'], 'Live config changed since the comparison'
    assert not any('density-probe' in p.name for p in (ROOT/'mods').glob('*.jar')), 'Private probe must never be installed live'
    assert subprocess.run(['systemctl','is-active','--quiet','minecraft']).returncode == 0
    assert base.online_players() == 0, 'Players online; coordinate a separate approved countdown'
    assert shutil.disk_usage(ROOT).free > 60*1024**3, 'Insufficient full-backup/rollback space'
    print('Read-only preflight passed: tested bytes, zero players, full-backup capacity.', flush=True)
    return receipt
def start(base):
    since = datetime.datetime.now(datetime.timezone.utc).isoformat()
    run('systemctl','start','minecraft-console.socket','minecraft.service')
    for _ in range(600):
        time.sleep(1); log = base.journal(since)
        if any(marker in log for marker in FATAL): raise RuntimeError('Server startup failure; automatic rollback required')
        if 'Done (' in log and 'Holy Lois claims: ready for OPAC' in log:
            assert 'sparsestructures 3.1.5' in log
            return
    raise TimeoutError('Server startup timed out')
def verify_backup(archive):
    with tarfile.open(archive) as tar:
        members = tar.getmembers(); names = {m.name for m in members}
        for required in ['minecraft/world/level.dat','minecraft/server.jar','minecraft/config','minecraft/mods','minecraft/EasyAuth']:
            assert required in names, 'Full backup is missing a required tree'
        assert all(m.offset_data+m.size <= archive.stat().st_size for m in members if m.isfile())
        assert tar.extractfile('minecraft/config/sparsestructures.json5').read() == TARGET.read_bytes()
    # Compare every archived file to the stopped server. Output may contain private paths, so do not print it.
    compared = subprocess.run(['tar','--compare','--file',str(archive),'-C','/opt'],capture_output=True)
    diagnostic = archive.parent/'backup-compare-private.log'
    diagnostic.write_bytes(compared.stdout+b'\n'+compared.stderr)
    diagnostic.chmod(0o600)
    (archive.parent/'backup-check.json').write_text(json.dumps({'comparison_exit':compared.returncode,
        'required_paths':True,'changed_config_matches':True,'archive_bytes':archive.stat().st_size}))
    assert compared.returncode == 0, 'Full backup comparison failed; keep the archive and inspect privately'
def deploy(base, tested):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = Path('/opt/minecraft-backups/maintenance')/('density-'+stamp); backup.mkdir(mode=0o700)
    archive = backup/'complete-server.tar'
    timers = {unit:subprocess.run(['systemctl','is-active','--quiet',unit]).returncode == 0
              for unit in ['holylois-stats.timer','holylois-terrain-expansion.timer','holylois-offsite-backup.timer']}
    assert subprocess.run(['systemctl','is-active','--quiet','holylois-offsite-backup.service']).returncode != 0, 'Backup job running; wait for completion'
    held = HOLD.exists(); installed = False
    MAINTENANCE.write_text('Applying a quiet structure-density balance patch')
    try:
        console('save-all flush'); time.sleep(2)
        run('systemctl','stop','holylois-stats.timer','holylois-stats.service','holylois-terrain-expansion.timer','holylois-terrain-expansion.service','holylois-offsite-backup.timer')
        run('systemctl','stop','minecraft-console.socket','minecraft.service')
        print('Creating and comparing a full stopped-server backup...', flush=True)
        run('tar','--exclude=minecraft/backups','-cf',str(archive),'-C','/opt','minecraft'); archive.chmod(0o600)
        verify_backup(archive)
        previous = TARGET.stat(); temporary = TARGET.with_name(TARGET.name+'.density-new')
        temporary.write_bytes(SOURCE.read_bytes()); temporary.chmod(stat.S_IMODE(previous.st_mode)); os.chown(temporary,previous.st_uid,previous.st_gid)
        os.replace(temporary,TARGET); installed = True
        print('Installing the exact tested config and starting Minecraft...', flush=True)
        start(base)
        assert sha(TARGET) == tested['candidate_sha256'] and HOLD.exists() == held
    except BaseException:
        run('systemctl','stop','minecraft-console.socket','minecraft.service')
        if installed:
            failed = backup/'failed'; failed.mkdir(mode=0o700)
            for relative in ['config','world','EasyAuth']:
                tree = ROOT/relative
                assert tree.resolve().is_relative_to(ROOT.resolve()) and tree.resolve() != ROOT.resolve()
                if tree.exists(): shutil.move(tree,failed/relative)
            run('tar','-xf',str(archive),'-C','/opt','minecraft/config','minecraft/world','minecraft/EasyAuth')
        run('systemctl','start','minecraft-console.socket','minecraft.service')
        print('Previous state restored; full backup and failed candidate retained privately.', flush=True)
        raise
    finally:
        MAINTENANCE.unlink(missing_ok=True)
        for unit, active in timers.items():
            if active: subprocess.run(['systemctl','start',unit],check=False)
    result = {'result':'live','silent':True,'server_only':True,'client_pack_changed':False,'launcher_changed':False,
              'config_sha256':sha(TARGET),'backup':str(archive),'backup_verification':'full archive compare plus required paths and exact changed-file bytes',
              'terrain_hold_preserved':HOLD.exists() == held,'changed_sets':tested['changed_sets']}
    (HOME/'deploy-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    (backup/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True); group.add_argument('--check',action='store_true'); group.add_argument('--deploy',action='store_true')
    args = parser.parse_args()
    with open('/run/holylois-density.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        base = helpers(); tested = precheck(base)
        if args.deploy: deploy(base,tested)
