"""Tested server-only Runeforged attribute throttle (entity residency 1.0.0 -> 1.1.0). --check reads; --deploy requires
explicit owner approval. Online players get the owner-approved one-minute countdown; a stopped, compared full backup
comes first and any failure restores the previous jar, world, config and EasyAuth automatically."""
import argparse,datetime,fcntl,hashlib,importlib.util,json,os,shutil,stat,subprocess,tarfile,time,zipfile
from pathlib import Path
HOME=Path(__file__).resolve().parent;ROOT=Path('/opt/minecraft')
SOURCE=HOME/'holylois-entity-residency-1.1.0+26.3.jar';TARGET=ROOT/'mods'/SOURCE.name
OLD=ROOT/'mods/holylois-entity-residency-1.0.0+26.3.jar';OLD_SHA='4db717ebacfc451115a6f5ede8dacfa6e31165ad39b504cea219c503459e85a4'
MAINTENANCE=Path('/run/holylois-maintenance');HOLD=Path('/opt/minecraft-backups/terrain-expansion/hold')
FATAL=('Failed to start','Crash report','Incompatible mods','Failed to load datapacks','Mixin apply failed','InvalidMixinException','Critical injection failure','Encountered an unexpected exception')
COUNTDOWN=60;BAR='holylois:restart'
def run(*args,**kw):return subprocess.run(args,check=True,**kw)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def mod_inventory():
    paths=list((ROOT/'mods').glob('*.jar'))
    if any(p.is_symlink() for p in paths):raise RuntimeError('Mod inventory contains a link')
    return {p.name:sha(p) for p in sorted(paths)}
def helper():
    spec=importlib.util.spec_from_file_location('throttle_previous','/home/ubuntu/hl-170/deploy-release-170.py')
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);return base
def console(*commands):
    fifo='/run/minecraft-console.fifo'
    if not stat.S_ISFIFO(os.stat(fifo,follow_symlinks=False).st_mode):raise RuntimeError('Console is not a FIFO')
    fd=os.open(fifo,os.O_WRONLY|os.O_NONBLOCK)
    try:
        for text in commands:
            b=(text+'\n').encode()
            if os.write(fd,b)!=len(b):raise RuntimeError('Incomplete console command')
    finally:os.close(fd)
def say(text):
    console('tellraw @a '+json.dumps([{'text':'[Holy Lois] ','color':'gold','bold':True},{'text':text,'color':'yellow','bold':False}]))
def countdown(base):
    """Boss bar countdown; command feedback off meanwhile, and the bar is removed because custom boss bars are saved in the world."""
    console(f'bossbar remove {BAR}')
    if base.online_players()==0:return
    console('gamerule send_command_feedback false',f'bossbar add {BAR} '+json.dumps({'text':'Server restart for a lag fix'}),
            f'bossbar set {BAR} max {COUNTDOWN}',f'bossbar set {BAR} value {COUNTDOWN}',f'bossbar set {BAR} color yellow',
            f'bossbar set {BAR} style notched_10',f'bossbar set {BAR} players @a','title @a times 0 25 5')
    start=time.monotonic()
    for left in range(COUNTDOWN,0,-1):
        time.sleep(max(0,COUNTDOWN-left-(time.monotonic()-start)))
        label=f'{left} second{"s" if left!=1 else ""}'
        commands=[f'bossbar set {BAR} value {left}',f'bossbar set {BAR} players @a',
                  f'bossbar set {BAR} name '+json.dumps({'text':f'Server restarting in {label} - lag fix, no update needed','color':'yellow' if left>10 else 'red'})]
        if left==10:commands.append(f'bossbar set {BAR} color red')
        if left<=10:
            commands+=['title @a subtitle '+json.dumps({'text':'Lag fix - just rejoin in a few minutes','color':'yellow'}),
                       'title @a title '+json.dumps({'text':str(left),'color':'gold','bold':True}),
                       'execute as @a at @s run playsound minecraft:block.note_block.hat master @s ~ ~ ~ 1 '+('2' if left<=3 else '1')]
        console(*commands)
        if left in (COUNTDOWN,30,10):say(f'Server restarts in {label} for a lag fix. No launcher update needed, just rejoin in a few minutes.')
    console(f'bossbar remove {BAR}','gamerule send_command_feedback true','title @a times 0 200 0',
            'title @a subtitle '+json.dumps({'text':'Back in a few minutes','color':'yellow'}),
            'title @a title '+json.dumps({'text':'Holy Lois','color':'gold','bold':True}))
    time.sleep(3)
    console('kick @a Holy Lois is restarting for a lag fix. Back in a few minutes, no update needed.')
    time.sleep(2)
def check(base):
    if os.geteuid()!=0:raise RuntimeError('Root required for deployment preflight')
    if MAINTENANCE.exists():raise RuntimeError('Another maintenance operation is active')
    receipt=json.loads((HOME/'native-receipt.json').read_text())
    if receipt.get('result')!='pass' or receipt.get('gear_changes_attributes') is not True or receipt.get('steady_full')!=5 or receipt.get('live_pid_unchanged') is not True:
        raise RuntimeError('Native regression receipt incomplete')
    if sha(SOURCE)!=receipt['candidate_sha256']:raise RuntimeError('Candidate differs from tested bytes')
    with zipfile.ZipFile(SOURCE) as z:
        if any('Native' in name for name in z.namelist()):raise RuntimeError('Fixture class in production jar')
        meta=json.loads(z.read('fabric.mod.json'))
        if meta['environment']!='server' or meta['version']!='1.1.0':raise RuntimeError('Candidate is not the server-only 1.1.0')
    baseline=json.loads((HOME/'baseline-mods.json').read_text())
    if mod_inventory()!=baseline:raise RuntimeError('Live mods changed since native rehearsal')
    if not OLD.exists() or sha(OLD)!=OLD_SHA or TARGET.exists():raise RuntimeError('Expected residency 1.0.0 only')
    if shutil.disk_usage(ROOT).free<60*1024**3:raise RuntimeError('Insufficient full-backup capacity')
    if subprocess.run(['systemctl','is-active','--quiet','minecraft']).returncode:raise RuntimeError('Minecraft is not active')
    result={'tested_sha256':receipt['candidate_sha256'],'mod_baseline_matches':True,'players_online':base.online_players(),'full_backup_capacity':True,'live_changed':False}
    print(json.dumps(result),flush=True);return receipt
def start(base):
    since=datetime.datetime.now(datetime.timezone.utc).isoformat()
    run('systemctl','start','minecraft-console.socket','minecraft.service')
    for _ in range(600):
        time.sleep(1);log=base.journal(since)
        if any(t in log for t in FATAL):raise RuntimeError('Startup failure; automatic rollback required')
        if 'Done (' in log and 'Holy Lois claims: ready for OPAC' in log:
            if 'holylois-entity-residency 1.1.0' not in log:raise RuntimeError('Expected residency 1.1.0 not loaded')
            return
    raise RuntimeError('Startup deadline exceeded')
def verified_backup(archive,backup):
    run('tar','--exclude=minecraft/backups','-cf',str(archive),'-C','/opt','minecraft');archive.chmod(0o600)
    with tarfile.open(archive) as tar:
        names={m.name for m in tar.getmembers()}
        for name in ('minecraft/world/level.dat','minecraft/server.jar','minecraft/config','minecraft/mods','minecraft/EasyAuth'):
            if name not in names:raise RuntimeError('Full backup required tree missing')
    compared=subprocess.run(['tar','--compare','--file',str(archive),'-C','/opt'],capture_output=True)
    log=backup/'backup-compare-private.log';log.write_bytes(compared.stdout+b'\n'+compared.stderr);log.chmod(0o600)
    if compared.returncode:raise RuntimeError('Stopped full backup comparison failed')
    check={'comparison_exit':0,'required_trees':True,'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive)}
    (backup/'backup-check.json').write_text(json.dumps(check));return check
def deploy(base,receipt):
    if subprocess.run(['systemctl','is-active','--quiet','holylois-offsite-backup.service']).returncode==0:raise RuntimeError('Scheduled backup running; wait for it')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=Path('/opt/minecraft-backups/maintenance')/('throttle-'+stamp);backup.mkdir(mode=0o700)
    archive=backup/'complete-server.tar';installed=False;backup_verified=False;held=HOLD.exists();backup_check=None
    timers={u:subprocess.run(['systemctl','is-active','--quiet',u]).returncode==0 for u in ('holylois-stats.timer','holylois-terrain-expansion.timer','holylois-offsite-backup.timer','holylois-botwall.timer')}
    MAINTENANCE.write_text('Applying the approved Runeforged attribute throttle')
    try:
        run('systemctl','stop','holylois-terrain-expansion.timer','holylois-terrain-expansion.service','holylois-offsite-backup.timer','holylois-botwall.timer','holylois-botwall.service')
        countdown(base)
        console('save-all flush');time.sleep(2)
        run('systemctl','stop','holylois-stats.timer','holylois-stats.service')
        run('systemctl','stop','minecraft-console.socket','minecraft.service')
        backup_check=verified_backup(archive,backup);backup_verified=True
        if mod_inventory()!=json.loads((HOME/'baseline-mods.json').read_text()):raise RuntimeError('Stopped mod baseline changed')
        temporary=TARGET.with_suffix('.jar.throttle-new');shutil.copyfile(SOURCE,temporary);temporary.chmod(0o644);shutil.chown(temporary,user='minecraft',group='minecraft')
        if sha(temporary)!=receipt['candidate_sha256']:raise RuntimeError('Copied candidate bytes differ')
        shutil.move(OLD,backup/OLD.name);os.replace(temporary,TARGET);installed=True;start(base)
        if sha(TARGET)!=receipt['candidate_sha256'] or OLD.exists() or HOLD.exists()!=held:raise RuntimeError('Post-start invariant failed')
    except BaseException:
        run('systemctl','stop','minecraft-console.socket','minecraft.service')
        if installed and backup_verified:
            failed=backup/'failed';failed.mkdir(mode=0o700)
            if TARGET.exists():shutil.move(TARGET,failed/TARGET.name)
            shutil.copy2(backup/OLD.name,OLD);shutil.chown(OLD,user='minecraft',group='minecraft')
            for name in ('world','config','EasyAuth'):
                tree=ROOT/name
                if tree.is_symlink() or tree.resolve().parent!=ROOT:raise RuntimeError('Unsafe rollback tree')
                if tree.exists():shutil.move(tree,failed/name)
            run('tar','-xf',str(archive),'-C','/opt','minecraft/world','minecraft/config','minecraft/EasyAuth')
        elif (backup/OLD.name).exists() and not OLD.exists():shutil.move(backup/OLD.name,OLD)
        run('systemctl','start','minecraft-console.socket','minecraft.service')
        print('Previous server restored; backup and failed candidate retained privately.',flush=True);raise
    finally:
        MAINTENANCE.unlink(missing_ok=True)
        for u,active in timers.items():
            if active:subprocess.run(['systemctl','start',u],check=False)
    result={'live':True,'server_only':True,'client_pack_changed':False,'candidate_sha256':sha(TARGET),'previous_jar_kept':str(backup/OLD.name),
            'full_backup':backup_check,'rollback_available':True,'terrain_hold_preserved':HOLD.exists()==held}
    (HOME/'deployment-receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();g=parser.add_mutually_exclusive_group(required=True);g.add_argument('--check',action='store_true');g.add_argument('--deploy',action='store_true');args=parser.parse_args()
    with open('/run/holylois-throttle.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);base=helper();receipt=check(base)
        if args.deploy:deploy(base,receipt)
