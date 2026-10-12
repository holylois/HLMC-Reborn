"""Combined 2.0.0 deployment from the passed workshop kit. --check is read-only.

Always gives the owner's one-minute countdown, then stops and verifies a complete backup.
Restores the pre-update world, config and mods if startup fails. No accounts are deleted.
pack-stable must move immediately after Done; terrain is resumed separately after that.
"""
from pathlib import Path
from importlib import util
import datetime,fcntl,hashlib,json,os,re,shutil,stat,subprocess,sys,tarfile,time

KIT=Path(__file__).resolve().parent
ROOT=Path('/opt/minecraft');BACKUPS=Path('/opt/minecraft-backups/maintenance')
FIFO=Path('/run/minecraft-console.fifo');MAINTENANCE=Path('/run/holylois-maintenance')
TERRAIN=Path('/usr/local/lib/holylois/expand-terrain.py');ALERT=Path('/usr/local/lib/holylois/discord-alert.py')
BOT=Path('/opt/holylois-bot/bot.py');MOTD=ROOT/'config/MiniMOTD/main.conf'
BAR='holylois:restart'
HEADLINE='<#FFAD42>✦ New:</#FFAD42> <white>Journal & Smelting!</white>'
FATAL=('Failed to start','Crash report','Incompatible mods','Failed to load datapacks','Mixin apply failed',
       'Registry loading errors','Encountered an unexpected exception','could not lock admin-only commands')
MARKERS=('holylois-extras 1.8.0','holylois-onboarding 1.10.0','bluemap 5.29','polymer-core 0.18.4',
         'autosmelt 1.0.2','easyanvils 26.3.1','easymagic 26.3.0','repurposed_structures 7.8.2',
         'Holy Lois claims: ready for OPAC','Holy Lois discoveries')

def load(name,path):
    spec=util.spec_from_file_location(name,path);module=util.module_from_spec(spec);spec.loader.exec_module(module);return module
workshop=load('workshop',KIT/'test-workshop.py')
base=load('previous',Path('/home/ubuntu/hl-170/deploy-release-170.py'))
def run(*args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def console(*commands):
    assert stat.S_ISFIFO(FIFO.stat().st_mode),'Console FIFO missing'
    with FIFO.open('w') as stream:
        for command in commands:stream.write(command+'\n')
def tell(text):console('tellraw @a '+json.dumps([{'text':'[Holy Lois] ','color':'gold','bold':True},{'text':text,'color':'yellow'}]))

def countdown():
    print('One-minute countdown started.',flush=True)
    console('gamerule send_command_feedback false',f'bossbar remove {BAR}',
            f'bossbar add {BAR} '+json.dumps({'text':'Holy Lois 2.0 update in 60 seconds'}),
            f'bossbar set {BAR} max 60',f'bossbar set {BAR} color yellow',f'bossbar set {BAR} style notched_10',
            f'bossbar set {BAR} players @a','title @a times 0 25 5')
    start=time.monotonic()
    for left in range(60,0,-1):
        time.sleep(max(0,60-left-(time.monotonic()-start)))
        commands=[f'bossbar set {BAR} value {left}',f'bossbar set {BAR} players @a',
                  f'bossbar set {BAR} name '+json.dumps({'text':f'Holy Lois 2.0 update in {left}s - update with the launcher','color':'yellow' if left>10 else 'red'})]
        if left==10:commands.append(f'bossbar set {BAR} color red')
        if left<=10:
            commands+=['title @a subtitle '+json.dumps({'text':'Close Minecraft, then open the launcher and click Update','color':'yellow'}),
                       'title @a title '+json.dumps({'text':str(left),'color':'gold','bold':True})]
        console(*commands)
        if left in (60,30,10):tell(f'Updating to Holy Lois 2.0 in {left} seconds: Journal, trophy fishing, Smelting and new dungeons. Update through the launcher before rejoining.')
    time.sleep(max(0,60-(time.monotonic()-start)))
    console(f'bossbar remove {BAR}','gamerule send_command_feedback true','title @a times 0 200 0',
            'title @a title '+json.dumps({'text':'Holy Lois is updating!','color':'gold','bold':True}),
            'title @a subtitle '+json.dumps({'text':'Back soon - update through the launcher','color':'yellow'}))
    time.sleep(2)
    console('kick @a Holy Lois is updating to 2.0.0. Open the launcher and click Update before rejoining.','save-all flush')
    time.sleep(2)

def precheck():
    assert os.geteuid()==0,'Run as root'
    receipt=json.loads((KIT/'test-workshop-receipt.json').read_text())
    assert receipt['live_changed'] is False and all(receipt['checks'].values()),'Loopback did not pass'
    assert receipt['versions']['pack']=='2.0.0'
    for name,digest in workshop.hashes.items():assert sha(KIT/'jars'/name)==digest,'Candidate artifact changed: '+name
    for name,digest in workshop.structures.HASHES.items():
        path=KIT/'structures'/('jars/'+name if name.endswith('.jar') else name)
        assert sha(path)==digest,'Structure artifact changed: '+name
    names={p.name for p in (ROOT/'mods').glob('*.jar')}
    assert {'holylois-extras-1.7.1+26.3.jar','holylois-onboarding-1.9.1+26.3.jar'}<=names,'Live add-ons changed'
    assert set(workshop.structures.REPLACED)<=names,'Live dependency versions changed'
    assert not set(workshop.structures.NEW_JARS)&names,'Structures already installed'
    assert not MAINTENANCE.exists(),'Another maintenance operation is active'
    assert shutil.disk_usage(ROOT).free>60*1024**3,'Insufficient full-backup/rollback space'
    assert len(re.findall(r'(?m)^\s*line2=',MOTD.read_text()))==1
    tests=run(sys.executable,str(KIT/'structures/test-expand-terrain.py'),cwd=KIT/'structures',capture_output=True,text=True)
    print('Terrain synthetic checks passed.',flush=True)
    for name in ['bot.py','discord-alert.py']:
        source=KIT/name;assert source.is_file();compile(source.read_text(encoding='utf-8'),name,'exec')
    for name in ['mythic','shiny_legendary','shiny_mythic']:
        assert (KIT/'advancements'/f'{name}.json').is_file()
    print('Preflight passed; online count:',base.online_players(),flush=True)

def start():
    for attempt in (1,2):
        since=datetime.datetime.now(datetime.timezone.utc).isoformat()
        run('systemctl','start','minecraft-console.socket','minecraft.service')
        log=''
        for _ in range(600):
            time.sleep(1);log=base.journal(since)
            if 'Done (' in log and 'Holy Lois claims: ready for OPAC' in log:break
            if any(marker in log for marker in FATAL):break
        if 'Failed to load datapacks' in log and attempt==1:
            print('Known datapack startup race; one restart.',flush=True)
            run('systemctl','stop','minecraft-console.socket','minecraft.service');continue
        assert 'Done (' in log,'Startup timeout or failure'
        for marker in MARKERS:assert marker in log,'Missing loaded marker: '+marker
        assert not any(marker in log for marker in FATAL),'Startup error detected'
        assert all(sha(ROOT/'mods'/name)==digest for name,digest in workshop.hashes.items())
        console(f'bossbar remove {BAR}','gamerule send_command_feedback true')
        return attempt
    raise RuntimeError('Server startup failed')

def main():
    with open('/run/holylois-release200.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);precheck()
        if sys.argv[1:]==['--check']:return
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup=BACKUPS/('release200-'+stamp);backup.mkdir(mode=0o700)
        archive=backup/'complete-server.tar'
        timers={name:subprocess.run(['systemctl','is-active','--quiet',name]).returncode==0 for name in ['holylois-stats.timer','holylois-terrain-expansion.timer']}
        external=[TERRAIN,ALERT,BOT]
        for path in external:shutil.copy2(path,backup/path.name)
        countdown()
        MAINTENANCE.write_text('Updating to Holy Lois 2.0: Journal, fishing, Smelting and new dungeons')
        changed=False
        try:
            run('systemctl','stop','holylois-stats.timer','holylois-stats.service','holylois-terrain-expansion.timer','holylois-terrain-expansion.service')
            run('systemctl','stop','minecraft-console.socket','minecraft.service')
            print('Server stopped. Creating complete backup...',flush=True)
            run('tar','--exclude=minecraft/backups','-cf',str(archive),'-C','/opt','minecraft');archive.chmod(0o600)
            with tarfile.open(archive) as tar:
                members=tar.getmembers();names={m.name for m in members}
                for required in ['minecraft/world/level.dat','minecraft/server.jar','minecraft/config','minecraft/mods','minecraft/EasyAuth','minecraft/world/data/openpartiesandclaims']:
                    assert required in names,'Required backup path missing'
                assert all(m.offset_data+m.size<=archive.stat().st_size for m in members if m.isfile())
                for path in [*(ROOT/'mods').glob('*.jar'),MOTD,ROOT/'config/holylois-pack.json',ROOT/'config/holylois-legends.json',ROOT/'config/runeforged-monsters.json']:
                    assert tar.extractfile('minecraft/'+path.relative_to(ROOT).as_posix()).read()==path.read_bytes(),'Changed-file restore bytes differ'
            print('Complete backup structure and changed-file restore bytes verified.',flush=True)
            changed=True
            workshop.structures.apply_changes(ROOT,KIT/'structures');workshop.apply_workshop(ROOT)
            guard=ROOT/'config/holylois-mods.json';settings=json.loads(guard.read_text())
            settings['allowed']=sorted(set(settings['allowed'])|{'autosmelt','easyanvils','easymagic','resourcepackoverrides'})
            guard.write_text(json.dumps(settings,indent=2)+'\n')
            shutil.copy2(KIT/'structures/expand-terrain.py',TERRAIN);TERRAIN.chmod(0o755)
            shutil.copy2(KIT/'discord-alert.py',ALERT);ALERT.chmod(0o755)
            shutil.copy2(KIT/'bot.py',BOT)
            dest=ROOT/'world/datapacks/holylois-advancements/data/holylois/advancement/fishing';dest.mkdir(parents=True,exist_ok=True)
            for source in (KIT/'advancements').glob('*.json'):shutil.copy2(source,dest/source.name)
            text,count=re.subn(r'(?m)^(\s*line2=).*$',lambda m:m.group(1)+json.dumps(HEADLINE,ensure_ascii=False),MOTD.read_text(),count=1)
            assert count==1;MOTD.write_text(text)
            run('chown','-R','minecraft:minecraft',str(ROOT/'mods'),str(ROOT/'config'),str(ROOT/'world/datapacks/holylois-advancements'))
            print('Exact candidate installed; starting server...',flush=True)
            attempts=start()
        except BaseException:
            print('Update failed; restoring pre-update world, mods and config automatically.',flush=True)
            subprocess.run(['systemctl','stop','minecraft-console.socket','minecraft.service'])
            if changed:
                failed=backup/'failed';failed.mkdir()
                for relative in ['mods','config','world']:
                    tree=ROOT/relative;assert tree.resolve().is_relative_to(ROOT.resolve()) and tree.resolve()!=ROOT.resolve()
                    shutil.move(tree,failed/relative)
                run('tar','-xf',str(archive),'-C','/opt','minecraft/mods','minecraft/config','minecraft/world')
                for path in external:shutil.copy2(backup/path.name,path)
            run('systemctl','start','minecraft-console.socket','minecraft.service')
            print('Rollback complete. Verified backup retained:',archive,flush=True)
            raise
        finally:
            MAINTENANCE.unlink(missing_ok=True)
            # Stats can return now; the terrain hold is deliberately still present until pack-stable moves.
            for name,active in timers.items():
                if active:subprocess.run(['systemctl','start',name])
        run('systemctl','restart','holylois-discord-bot')
        result={'result':'Done','pack':'2.0.0','backup':str(archive),'start_attempts':attempts,'minimum':'2.0.0',
                'jar_hashes':workshop.hashes,'terrain_hold_present':Path('/opt/minecraft-backups/terrain-expansion/hold').exists(),
                'backup_verification':'complete archive structure, required paths and exact changed-file restore bytes','motd':HEADLINE}
        (KIT/'deploy-receipt.json').write_text(json.dumps(result,indent=2)+'\n');(backup/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
