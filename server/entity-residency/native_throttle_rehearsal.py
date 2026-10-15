"""Loopback generated-world Runeforged attribute throttle regression. No live configs/accounts/worlds copied."""
import hashlib,json,os,shutil,socket,subprocess,time
from pathlib import Path
LIVE=Path('/opt/minecraft');TEST=Path('/opt/minecraft-test-throttle-218')
OUT=Path('/home/ubuntu/hl-throttle-218');UNIT='holylois-throttle-native-218'
def command(*args):return subprocess.run(args,check=True,capture_output=True,text=True)
def main():
    if os.geteuid()!=0:raise RuntimeError('Private preparation requires root')
    for port,kind in ((25566,socket.SOCK_STREAM),(24455,socket.SOCK_DGRAM)):
        with socket.socket(socket.AF_INET,kind) as sock:sock.bind(('127.0.0.1',port))
    if TEST.exists():raise RuntimeError('Test folder already exists; preserve prior evidence')
    pid=command('systemctl','show','minecraft','--property=MainPID','--value').stdout.strip()
    TEST.mkdir(mode=0o750)
    shutil.copy2(LIVE/'server.jar',TEST/'server.jar')
    for name in ('mods','.fabric','libraries','versions'):shutil.copytree(LIVE/name,TEST/name)
    (TEST/'mods/holylois-entity-residency-1.0.0+26.3.jar').unlink()
    candidate=OUT/'holylois-entity-residency-1.1.0+26.3.jar'
    shutil.copy2(candidate,TEST/'mods'/candidate.name)
    shutil.copy2(OUT/'holylois-throttle-fixture.jar',TEST/'mods/holylois-throttle-fixture.jar')
    (TEST/'eula.txt').write_text('eula=true\n')
    generator={'biome':'minecraft:plains','features':False,'lakes':False,'layers':[{'block':'minecraft:bedrock','height':1},{'block':'minecraft:dirt','height':2},{'block':'minecraft:grass_block','height':1}],'structure_overrides':[]}
    (TEST/'server.properties').write_text('server-ip=127.0.0.1\nserver-port=25566\nonline-mode=true\nenforce-secure-profile=false\nmax-players=1\nview-distance=2\nsimulation-distance=2\nlevel-name=world\nlevel-type=minecraft:flat\ngenerate-structures=false\ngenerator-settings='+json.dumps(generator,separators=(',',':'))+'\npause-when-empty-seconds=0\nmotd=Private throttle fixture\n')
    config=TEST/'config';config.mkdir(exist_ok=True);(config/'voicechat').mkdir()
    (config/'voicechat/voicechat-server.properties').write_text('port=24455\nbind_address=127.0.0.1\n')
    (config/'justenoughbackups.json').write_text(json.dumps({'automaticBackupsEnabled':False}))
    (config/'bluemap').mkdir();(config/'bluemap/webserver.conf').write_text('enabled: false\n');(config/'bluemap/webapp.conf').write_text('enabled: false\n')
    command('chown','-R','minecraft:minecraft',str(TEST))
    log=OUT/'native-console.log';started=time.monotonic()
    with log.open('xb') as stream:
        process=subprocess.Popen(['systemd-run','--pipe','--wait','--collect','--unit='+UNIT,'--uid=minecraft','--gid=minecraft','--property=WorkingDirectory='+str(TEST),'--property=CPUQuota=35%','--property=MemoryMax=2G','--property=RuntimeMaxSec=720','--property=TimeoutStopSec=40','/usr/lib/jvm/java-25-openjdk-arm64/bin/java','-Xms128M','-Xmx1400M','-Dholylois.throttle.test=true','-jar','server.jar','nogui'],stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.STDOUT)
        try:
            while process.poll() is None and time.monotonic()-started<690:
                time.sleep(2)
                text=log.read_text(errors='replace')
                if any(t in text for t in ('Incompatible mods found','Failed to start the minecraft server','Critical injection failure','Mixin apply failed')):raise RuntimeError('Private native bootstrap failed; inspect private diagnostic log')
            if process.poll() is None:raise RuntimeError('Private native fixture timed out')
        finally:
            if process.poll() is None:subprocess.run(['systemctl','stop',UNIT],check=False,capture_output=True);process.wait(timeout=50)
            if process.stdin:process.stdin.close()
    receipt=TEST/'throttle-test-receipt.json'
    if not receipt.exists():
        for line in log.read_text(errors='replace').splitlines():
            if 'THROTTLE_NATIVE_TEST_FAIL' in line or 'Mixin' in line and 'holylois' in line:print(line,flush=True)
        raise RuntimeError('Native fixture did not produce success receipt')
    result=json.loads(receipt.read_text());result.update(candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),console_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),elapsed_seconds=round(time.monotonic()-started,1),live_pid_unchanged=command('systemctl','show','minecraft','--property=MainPID','--value').stdout.strip()==pid,live_data_copied=False)
    if not result['live_pid_unchanged']:raise RuntimeError('Live process changed during fixture')
    (OUT/'native-receipt.json').write_text(json.dumps(result,indent=2)+'\n');os.chmod(OUT/'native-receipt.json',0o644)
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
