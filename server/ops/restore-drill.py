"""Restore drill: prove that the off-site world backups really bring the world back (owner roadmap, never done before).

Downloads the newest JEB full backup and every newer differential from Google Drive, checks each file's MD5 against Drive
(and against the local JEB copy when it still exists), restores full + differentials in order into an isolated server
copy and boots it on loopback (port 25566, voice 24455, JEB and BlueMap off, no Discord, no live files touched).
  sudo python3 restore-drill.py OUT_DIR      writes OUT_DIR/receipt.json; leaves /opt/restore-drill and the test copy for review
Run it detached (systemd-run) because the download takes a while. Nothing is deleted; remove the folders when the owner says so.
"""
import hashlib, json, os, re, shutil, socket, struct, subprocess, sys, time, zipfile
from pathlib import Path

LIVE = Path('/opt/minecraft'); JEB = LIVE / 'backups/world'
DOWNLOAD = Path('/opt/restore-drill'); TEST = Path('/opt/minecraft-restore-drill')
REMOTE = 'gdrive:Holy Lois Backups/world'
UNIT = 'holylois-restore-drill'
STAMP = re.compile(r'^(full|differential)-(\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d)\.zip$')
BAD = ('Incompatible mods found', 'Failed to start the minecraft server', 'Critical injection failure', 'Mixin apply failed',
       'Exception in server tick loop', 'Failed to load datapacks', 'Crash report saved', 'Failed to load level', 'Couldn\'t load level')
DATA_WARNINGS = ('Failed to load player data', 'Couldn\'t load chunk', 'Exception reading', 'corrupt', 'Failed to read level data')


def run(*args, **kw): return subprocess.run(args, check=True, capture_output=True, text=True, **kw)


def md5(path):
    digest = hashlib.md5()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''): digest.update(block)
    return digest.hexdigest()


def varint(n):
    out = b''
    while True:
        byte, n = n & 0x7f, n >> 7
        out += bytes([byte | (0x80 if n else 0)])
        if not n: return out


def ping():
    with socket.create_connection(('127.0.0.1', 25566), 10) as s:
        host = 'play.holylois.com'
        hello = b'\x00' + varint(0) + varint(len(host)) + host.encode() + struct.pack('>H', 25566) + varint(1)
        s.sendall(varint(len(hello)) + hello + b'\x01\x00')
        data, deadline = b'', time.time() + 10
        while time.time() < deadline:
            data += s.recv(65536)
            try: return json.loads(data[data.index(b'{'):].decode())
            except ValueError: continue
    raise RuntimeError('no status reply')


def chosen(listing):
    """Newest full backup plus every differential made after it, oldest first."""
    files = sorted((m.group(2), m.group(1), name) for name in listing if (m := STAMP.match(name)))
    fulls = [f for f in files if f[1] == 'full']
    if not fulls: raise RuntimeError('no full backup on Drive')
    newest = fulls[-1][0]
    return [fulls[-1][2]] + [f[2] for f in files if f[1] == 'differential' and f[0] > newest]


def main():
    if os.geteuid() != 0: raise RuntimeError('needs root')
    out = Path(sys.argv[1]).resolve(); out.mkdir(parents=True, exist_ok=True)
    for port, kind in ((25566, socket.SOCK_STREAM), (24455, socket.SOCK_DGRAM)):
        with socket.socket(socket.AF_INET, kind) as sock: sock.bind(('127.0.0.1', port))
    if TEST.exists(): raise RuntimeError(f'{TEST} already exists; keep the previous evidence or remove it first')
    receipt = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    live_pid = run('systemctl', 'show', 'minecraft', '--property=MainPID', '--value').stdout.strip()

    sums = dict(line.split(None, 1)[::-1] for line in run('rclone', 'md5sum', REMOTE).stdout.split('\n') if line.strip())
    names = chosen(sums)
    DOWNLOAD.mkdir(mode=0o700, exist_ok=True)
    files = []
    for name in names:
        started = time.monotonic()
        run('nice', '-n', '10', 'rclone', 'copy', f'{REMOTE}/{name}', str(DOWNLOAD))
        local = DOWNLOAD / name; got = md5(local)
        jeb = JEB / name
        files.append({'name': name, 'bytes': local.stat().st_size, 'md5': got, 'drive_md5_match': got == sums[name].strip(),
                      'local_jeb_md5_match': (md5(jeb) == got) if jeb.exists() else None,
                      'download_seconds': round(time.monotonic() - started)})
        if got != sums[name].strip(): raise RuntimeError(f'{name}: MD5 differs from Drive')
    receipt['backups'] = files

    TEST.mkdir(mode=0o750); world = TEST / 'world'; world.mkdir()
    for name in names:
        with zipfile.ZipFile(DOWNLOAD / name) as archive: archive.extractall(world)  # extraction checks every CRC
    restored_regions = sum(1 for _ in world.rglob('region/*.mca')); live_regions = sum(1 for _ in (LIVE / 'world').rglob('region/*.mca'))
    live_top = sorted(p.name for p in (LIVE / 'world').iterdir()); restored_top = sorted(p.name for p in world.iterdir())
    receipt['restore'] = {'regions_restored': restored_regions, 'regions_live_now': live_regions,
                          'top_level_missing_vs_live': [n for n in live_top if n not in restored_top and n != 'session.lock'],
                          'holylois_files': sorted(p.name for p in (world / 'holylois').glob('*.json')) if (world / 'holylois').is_dir() else []}

    shutil.copy2(LIVE / 'server.jar', TEST / 'server.jar')
    for name in ('mods', '.fabric', 'libraries', 'versions'): shutil.copytree(LIVE / name, TEST / name)
    (TEST / 'eula.txt').write_text('eula=true\n')
    (TEST / 'server.properties').write_text('server-ip=127.0.0.1\nserver-port=25566\nonline-mode=true\nenforce-secure-profile=false\n'
                                            'max-players=5\nview-distance=2\nsimulation-distance=2\nlevel-name=world\npause-when-empty-seconds=0\nmotd=Restore drill\n')
    config = TEST / 'config'; config.mkdir(); (config / 'voicechat').mkdir()
    (config / 'voicechat/voicechat-server.properties').write_text('port=24455\nbind_address=127.0.0.1\n')
    (config / 'justenoughbackups.json').write_text(json.dumps({'automaticBackupsEnabled': False}))
    (config / 'bluemap').mkdir(); (config / 'bluemap/webserver.conf').write_text('enabled: false\n'); (config / 'bluemap/webapp.conf').write_text('enabled: false\n')
    run('chown', '-R', 'minecraft:minecraft', str(TEST))

    log = out / 'restore-drill-console.log'; started = time.monotonic()
    with log.open('xb') as stream:
        process = subprocess.Popen(['systemd-run', '--pipe', '--wait', '--collect', '--unit=' + UNIT, '--uid=minecraft', '--gid=minecraft',
                                    '--property=WorkingDirectory=' + str(TEST), '--property=CPUQuota=60%', '--property=MemoryMax=3G',
                                    '--property=RuntimeMaxSec=1500', '--property=TimeoutStopSec=60', '/usr/lib/jvm/java-25-openjdk-arm64/bin/java',
                                    '-Xms256M', '-Xmx2200M', '-jar', 'server.jar', 'nogui'], stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None and time.monotonic() - started < 1200:
                time.sleep(3)
                text = log.read_text(errors='replace')
                if any(t in text for t in BAD): raise RuntimeError('boot failed: ' + next(t for t in BAD if t in text))
                if re.search(r'Done \([\d.]+s\)!', text): break
            else: raise RuntimeError('server did not start')
            time.sleep(10)
            status = None
            for attempt in range(12):
                try: status = ping(); break
                except (OSError, RuntimeError):
                    if attempt == 11: raise
                    time.sleep(5)
            process.stdin.write(b'list\n'); process.stdin.flush(); time.sleep(5)
            process.stdin.write(b'stop\n'); process.stdin.flush(); process.wait(timeout=240)
        finally:
            if process.poll() is None: subprocess.run(['systemctl', 'stop', UNIT], check=False, capture_output=True); process.wait(timeout=90)
    text = log.read_text(errors='replace')
    receipt['boot'] = {'seconds': round(time.monotonic() - started, 1), 'ready': bool(re.search(r'Done \([\d.]+s\)!', text)),
                       'status_version': (status or {}).get('version', {}).get('name'), 'list_ran': 'There are 0 of a max of' in text,
                       'errors': [t for t in BAD if t in text], 'data_warnings': [l[:240] for l in text.splitlines() if any(w in l for w in DATA_WARNINGS)][:20],
                       'error_lines': [l[:240] for l in text.splitlines() if '/ERROR]' in l][:25],
                       'live_pid_unchanged': run('systemctl', 'show', 'minecraft', '--property=MainPID', '--value').stdout.strip() == live_pid}
    receipt['passed'] = (all(f['drive_md5_match'] and f['local_jeb_md5_match'] is not False for f in files) and receipt['boot']['ready']
                         and receipt['boot']['list_ran'] and not receipt['boot']['errors'] and receipt['boot']['live_pid_unchanged']
                         and receipt['restore']['regions_restored'] > 0)
    receipt['finished'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=1))
    if not receipt['passed']: raise SystemExit('FAILED')
    print('PASSED')


if __name__ == '__main__': main()
