"""Finite empty-server Chunky 1.5.3 job. Never trims or deletes terrain.

Chunky saves cancelled=true on natural completion, before its last async chunk
callbacks finish. Its saved count can lag and those callbacks ignore failures.
Promotion therefore needs the owned completed task AND all expected on-disk
chunk NBT records with matching coordinates and Status=full, not MCA headers.
"""
from pathlib import Path
import json
import math
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import time
import zlib

ROOT = Path('/opt/minecraft')
JOB = Path('/opt/minecraft-backups/terrain-expansion')
STATE = JOB / 'job.json'
TASK = ROOT / 'config/chunky/tasks/minecraft/overworld.properties'
WORLD = 'minecraft:overworld'
TIMER = 'holylois-terrain-expansion.timer'
# The whole area inside the world border is pregenerated (border width / 2 from 0,0); /rtp then reaches RTP_RADIUS.
BORDER = 20000
GENERATION_RADIUS = BORDER // 2
RTP_RADIUS = 5000
MIN_FREE_BYTES = 6 * 1024**3
CHECKPOINT_TIMEOUT = 8
CHECKPOINT_DEADLINE = 120
COMPLETION_GRACE = 120
VERIFY_CHUNKS = 4096
VERIFY_SECONDS = 6
MAX_NBT_BYTES = 32 * 1024**2
# Pregeneration must never starve the server thread (the 2026-10-05 watchdog crash came after minutes of growing "ticks behind").
# Generation runs in slices: it pauses when the server reports lag, or after RUN_SECONDS, and rests before the next slice.
# The server is empty while it runs, so slices are long and the normal rest is short; lag still backs it off (2026-10-11).
LAG_TICKS = 100
RUN_SECONDS = 45 * 60
REST_SECONDS = 2 * 60
LAG_REST_SECONDS = 10 * 60


class ChunkNotFull(IOError):
    """The asynchronous writer has not stored a complete chunk yet."""


class CheckpointIncomplete(IOError):
    """TaskLoader may be in the middle of its non-atomic checkpoint write."""


def command(text):
    fifo = '/run/minecraft-console.fifo'
    if not stat.S_ISFIFO(os.stat(fifo, follow_symlinks=False).st_mode):
        raise RuntimeError('Minecraft console path is not a FIFO')
    fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    try:
        payload = (text + '\n').encode('utf-8')
        if os.write(fd, payload) != len(payload):
            raise IOError('Incomplete console command')
    finally:
        os.close(fd)


def varint(value):
    result = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
        if not value:
            return bytes(result)


def read_exact(stream, length):
    result = bytearray()
    while len(result) < length:
        data = stream.recv(length - len(result))
        if not data:
            raise IOError('Incomplete local status reply')
        result.extend(data)
    return bytes(result)


def read_varint(stream):
    value = 0
    for shift in range(0, 35, 7):
        byte = read_exact(stream, 1)[0]
        value |= (byte & 127) << shift
        if not byte & 128:
            return value
    raise IOError('Invalid status length')


def online_players():
    # Use only the count. Do not persist the status sample or player names.
    with socket.create_connection(('127.0.0.1', 25565), timeout=5) as stream:
        host = b'localhost'
        packet = (b'\x00' + varint(0) + varint(len(host)) + host
                  + struct.pack('>H', 25565) + b'\x01')
        stream.sendall(varint(len(packet)) + packet + b'\x01\x00')
        length = read_varint(stream)
        if not 2 < length < 1024**2:
            raise IOError('Invalid status packet size')
        if read_varint(stream) != 0:
            raise IOError('Unexpected status reply')
        count = read_varint(stream)
        if not 0 < count <= length - 2:
            raise IOError('Invalid status JSON length')
        result = json.loads(read_exact(stream, count))
        players = result['players']['online']
        if type(players) is not int or players < 0:
            raise IOError('Invalid online player count')
        return players


def atomic_text(path, text):
    if path.is_symlink():
        raise RuntimeError('Refusing to replace a symlink')
    info = path.stat() if path.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if info:
            if hasattr(os, 'chown'):
                os.chown(temporary, info.st_uid, info.st_gid)
            os.chmod(temporary, stat.S_IMODE(info.st_mode))
        else:
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(state):
    atomic_text(STATE, json.dumps(state, indent=2, sort_keys=True) + '\n')


def properties(path):
    # TaskLoader 1.5.3 writes literal key=value lines, without Java escaping.
    result = {}
    text = path.read_text(encoding='utf-8')
    if not text.endswith('\n'):
        raise CheckpointIncomplete('Chunky checkpoint write is incomplete')
    for line in text.splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            if key.strip() in result:
                raise ValueError('Duplicate Chunky checkpoint key')
            result[key.strip()] = value.strip()
    return result


def expected_chunks():
    # RegionChunkIterator and chunk-aligned Square in the exact 1.5.3 JAR.
    return (2 * math.ceil(GENERATION_RADIUS / 16) + 1)**2


def owned_task(task):
    try:
        return (task['world'] == WORLD and task['shape'] == 'square'
                and task['pattern'] == 'region'
                and float(task['center-x']) == float(task['center-z']) == 0
                and float(task['radius']) == GENERATION_RADIUS
                and task['cancelled'] in ('true', 'false')
                and 0 <= int(task['chunks']) <= expected_chunks()
                and int(task['time']) >= 0)
    except (KeyError, ValueError, OverflowError):
        return False


def task_snapshot():
    if TASK.is_symlink():
        raise RuntimeError('Unexpected Chunky checkpoint symlink')
    before = fingerprint(TASK)
    task = properties(TASK)
    if fingerprint(TASK) != before:
        raise CheckpointIncomplete('Chunky checkpoint changed while being read')
    required = ('world', 'shape', 'pattern', 'center-x', 'center-z',
                'radius', 'cancelled', 'chunks', 'time')
    if any(key not in task for key in required):
        raise CheckpointIncomplete('Chunky checkpoint write is incomplete')
    if not owned_task(task):
        raise RuntimeError('Chunky checkpoint is not the owned world, center, radius, shape and pattern')
    return task


def request_pause(state):
    if not state.get('started'):
        return
    # Never pause a different administrator task. Missing files are possible
    # before the first owned checkpoint. In-place writes are handled below.
    if TASK.exists():
        try:
            task_snapshot()
        except CheckpointIncomplete:
            pass
    if not state.get('running', True) and not state.get('pause_pending'):
        # Already paused and checkpointed: no console command every 15 seconds while players are online.
        return
    if not state.get('pause_pending'):
        state['pause_baseline'] = TASK.stat().st_mtime_ns if TASK.exists() else -1
        state['pause_requested_at'] = time.time()
        state['pause_pending'] = True
        save(state)
    command('chunky pause ' + WORLD)


def generation_allowed(state):
    try:
        players = online_players()
        free = shutil.disk_usage(ROOT).free
    except (OSError, ValueError, KeyError):
        request_pause(state)
        print('Generation held because local server status or storage is unavailable.')
        return False
    if players or free < MIN_FREE_BYTES:
        request_pause(state)
        print('Generation held while players are online or free space is below 6 GB.')
        return False
    return True


def recent_lag():
    """Largest "N ticks behind" warning in the last three minutes of the server log, 0 when quiet or unreadable."""
    try:
        done = subprocess.run(['journalctl', '-u', 'minecraft', '--since', '-3min', '-o', 'cat', '--no-pager'],
                              capture_output=True, text=True, timeout=30)
        return max([int(n) for n in re.findall(r'or (\d+) ticks behind', getattr(done, 'stdout', '') or '')] or [0])
    except (OSError, subprocess.SubprocessError):
        return 0


def rest_needed(state, now, lag):
    """Seconds to rest now, or 0: lag wins over the slice length. Only while generation is running."""
    if not state.get('running', True) or not state.get('started'):
        return 0
    if lag >= LAG_TICKS:
        return LAG_REST_SECONDS
    if now - state.get('resumed_at', now) >= RUN_SECONDS:
        return REST_SECONDS
    return 0


def server_started_at():
    """Wall-clock start of the current Minecraft process, 0 when unknown."""
    try:
        pid = subprocess.run(['systemctl', 'show', 'minecraft', '--property=MainPID', '--value'],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if not pid or pid == '0':
            return 0
        ticks = int(Path('/proc/%s/stat' % pid).read_text().rsplit(')', 1)[1].split()[19])
        boot = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
        return boot + ticks / os.sysconf('SC_CLK_TCK')
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, StopIteration):
        return 0


def chunky_idle_since(since):
    """True when Chunky answered "No tasks to pause" after the pause request. Nothing is running (for example after a
    server restart), so the checkpoint already on disk is final and will never be rewritten."""
    try:
        done = subprocess.run(['journalctl', '-u', 'minecraft', '--since', '@%d' % int(since), '-o', 'cat', '--no-pager'],
                              capture_output=True, text=True, timeout=30)
        return '[Chunky] No tasks to pause' in (getattr(done, 'stdout', '') or '')
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def checkpoint(state):
    # PauseCommand uses stop(false); it returns before the checkpoint is saved.
    # Wait for the changed file, rather than trusting an arbitrary one-second nap.
    if TASK.exists():
        try:
            task = task_snapshot()
        except CheckpointIncomplete:
            # TaskLoader writes in place. An empty/partial record may be transient.
            task = None
        if task and (task['cancelled'] == 'true' or
                     not state.get('running', True) and not state.get('pause_pending')):
            state.update(running=False, pause_pending=False)
            save(state)
            return task
    if not state.get('pause_pending'):
        # Do not call request_pause here: it rejects transient partial writes.
        state.update(pause_baseline=TASK.stat().st_mtime_ns if TASK.exists() else -1,
                     pause_requested_at=time.time(), pause_pending=True)
        save(state)
        command('chunky pause ' + WORLD)
    deadline = time.monotonic() + CHECKPOINT_TIMEOUT
    while time.monotonic() < deadline:
        if TASK.exists() and TASK.stat().st_mtime_ns > state['pause_baseline']:
            try:
                task = task_snapshot()
            except (OSError, ValueError):
                task = None
            if task:
                state.update(running=False, pause_pending=False)
                save(state)
                return task
        time.sleep(0.25)
    if TASK.exists() and chunky_idle_since(state['pause_requested_at']):
        try:
            task = task_snapshot()
        except (OSError, ValueError):
            task = None
        if task:
            state.update(running=False, pause_pending=False)
            save(state)
            return task
    if time.time() - state['pause_requested_at'] > CHECKPOINT_DEADLINE:
        if server_started_at() > state['pause_requested_at']:
            # The server restarted after the request: pause commands sent while it booted got no reply. Restart the clock.
            state['pause_requested_at'] = time.time()
            save(state)
            print('Generation held while waiting for the owned Chunky pause checkpoint.')
            return None
        raise RuntimeError('Owned Chunky pause was not checkpointed within 120 seconds; inspect the server log')
    print('Generation held while waiting for the owned Chunky pause checkpoint.')
    return None


class NbtReader:
    """Bounded parser for the few chunk fields needed for completion proof."""
    WIDTHS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}

    def __init__(self, data):
        self.data = memoryview(data)
        self.offset = 0
        self.fields = {}

    def take(self, count):
        if count < 0 or self.offset + count > len(self.data):
            raise IOError('Truncated chunk NBT')
        value = self.data[self.offset:self.offset + count]
        self.offset += count
        return value

    def byte(self):
        return self.take(1)[0]

    def integer(self):
        return struct.unpack('>i', self.take(4))[0]

    def string(self):
        count = struct.unpack('>H', self.take(2))[0]
        return bytes(self.take(count)).decode('utf-8', errors='replace')

    def compound(self, depth, capture=False):
        if depth > 64:
            raise IOError('Chunk NBT nesting exceeds the safety limit')
        while True:
            tag = self.byte()
            if tag == 0:
                return
            name = self.string()
            if capture and name in ('Status', 'xPos', 'zPos'):
                if name in self.fields or tag != (8 if name == 'Status' else 3):
                    raise IOError('Invalid chunk identity fields')
                self.fields[name] = self.string() if tag == 8 else self.integer()
            elif capture and name == 'Level' and tag == 10:
                self.compound(depth + 1, True)
            else:
                self.skip(tag, depth + 1)

    def skip(self, tag, depth):
        if depth > 64:
            raise IOError('Chunk NBT nesting exceeds the safety limit')
        if tag in self.WIDTHS:
            self.take(self.WIDTHS[tag])
        elif tag in (7, 11, 12):
            self.take(self.integer() * {7: 1, 11: 4, 12: 8}[tag])
        elif tag == 8:
            self.take(struct.unpack('>H', self.take(2))[0])
        elif tag == 9:
            kind, count = self.byte(), self.integer()
            if count < 0 or count > len(self.data) or kind == 0 and count:
                raise IOError('Invalid chunk NBT list')
            if kind in self.WIDTHS:
                self.take(count * self.WIDTHS[kind])
            else:
                for _ in range(count):
                    self.skip(kind, depth + 1)
        elif tag == 10:
            self.compound(depth + 1)
        else:
            raise IOError('Unknown chunk NBT tag')

    def identity(self):
        if self.byte() != 10:
            raise IOError('Chunk NBT root is not a compound')
        self.string()
        self.compound(0, True)
        if self.offset != len(self.data):
            raise IOError('Unexpected trailing chunk NBT')
        return self.fields


def full_chunk_nbt(payload, compression, cx, cz):
    if compression in (1, 2):
        decoder = zlib.decompressobj(31 if compression == 1 else 15)
        data = decoder.decompress(payload, MAX_NBT_BYTES + 1)
        if len(data) > MAX_NBT_BYTES or decoder.unconsumed_tail:
            raise IOError('Chunk NBT exceeds the safety limit')
        if not decoder.eof or decoder.unused_data:
            raise IOError('Incomplete or trailing compressed chunk NBT')
    elif compression == 3:
        if len(payload) > MAX_NBT_BYTES:
            raise IOError('Chunk NBT exceeds the safety limit')
        data = payload
    else:
        raise IOError('Unsupported chunk compression; use the server default deflate format')
    fields = NbtReader(data).identity()
    if fields.get('xPos') != cx or fields.get('zPos') != cz:
        raise IOError('Stored chunk coordinates do not match the requested region slot')
    if fields.get('Status') not in ('minecraft:full', 'full'):
        raise ChunkNotFull(f'Chunk {cx},{cz} is not stored with Status=full')


def region_directory():
    path = ROOT / 'world/dimensions/minecraft/overworld/region'
    if not path.is_dir():
        path = ROOT / 'world/region'
    if not path.is_dir() or not path.resolve().is_relative_to(ROOT):
        raise IOError('No safe overworld region directory')
    return path


def region_coordinates():
    limit = math.ceil(GENERATION_RADIUS / 16)
    for rx in range((-limit) // 32, limit // 32 + 1):
        for rz in range((-limit) // 32, limit // 32 + 1):
            coordinates = [(cx, cz)
                           for cx in range(max(-limit, rx * 32), min(limit, rx * 32 + 31) + 1)
                           for cz in range(max(-limit, rz * 32), min(limit, rz * 32 + 31) + 1)]
            yield f'{rx},{rz}', rx, rz, coordinates


def fingerprint(path):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise IOError('Terrain record is not a regular file')
    return [info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino]


def external_unchanged(directory, entry):
    for key, recorded in entry.get('external', {}).items():
        cx, cz = map(int, key.split(','))
        try:
            if fingerprint(directory / f'c.{cx}.{cz}.mcc') != recorded:
                return False
        except FileNotFoundError:
            return False
    return True


def read_full_chunk(stream, header, directory, cx, cz):
    index = 4 * ((cx % 32) + (cz % 32) * 32)
    location = int.from_bytes(header[index:index + 4], 'big')
    offset, sectors = location >> 8, location & 255
    if offset == 0 and sectors == 0:
        raise ChunkNotFull(f'Chunk {cx},{cz} has not been stored')
    if offset < 2 or sectors == 0:
        raise IOError('Invalid chunk sector allocation')
    stream.seek(offset * 4096)
    record = stream.read(5)
    if len(record) != 5:
        raise ChunkNotFull('Chunk sector has not been fully written')
    length, compression = struct.unpack('>IB', record)
    if length < 1 or length > sectors * 4096 - 4:
        raise IOError('Invalid chunk record size')
    external = None
    if compression & 128:
        if length != 1:
            raise IOError('Invalid external chunk marker')
        path = directory / f'c.{cx}.{cz}.mcc'
        try:
            before = fingerprint(path)
            if before[0] > MAX_NBT_BYTES:
                raise IOError('External compressed chunk exceeds the safety limit')
            payload = path.read_bytes()
            if fingerprint(path) != before:
                raise ChunkNotFull('External chunk changed while being read')
            external = (f'{cx},{cz}', before)
        except FileNotFoundError as error:
            raise ChunkNotFull('External chunk has not been stored') from error
        compression &= 127
    else:
        payload = stream.read(length - 1)
        if len(payload) != length - 1:
            raise ChunkNotFull('Chunk payload has not been fully written')
    full_chunk_nbt(payload, compression, cx, cz)
    return external


def coverage_complete(state, directory):
    entries = state.get('verified_regions', {})
    for key, rx, rz, coordinates in region_coordinates():
        entry = entries.get(key)
        try:
            if (not entry or entry['next'] != len(coordinates)
                    or entry['fingerprint'] != fingerprint(directory / f'r.{rx}.{rz}.mca')
                    or not external_unchanged(directory, entry)):
                return False
        except FileNotFoundError:
            return False
    return True


def verify_full_area(state, directory):
    start, verified = time.monotonic(), 0
    entries = state.setdefault('verified_regions', {})
    for key, rx, rz, coordinates in region_coordinates():
        path = directory / f'r.{rx}.{rz}.mca'
        try:
            before = fingerprint(path)
        except FileNotFoundError as error:
            raise ChunkNotFull(f'Region {rx},{rz} has not been stored') from error
        entry = entries.get(key)
        if (not entry or entry['fingerprint'] != before
                or not external_unchanged(directory, entry)):
            entry = entries[key] = {'fingerprint': before, 'next': 0, 'external': {}}
        if entry['next'] == len(coordinates):
            continue
        with path.open('rb') as stream:
            header = stream.read(4096)
            if len(header) != 4096:
                raise ChunkNotFull('Region location table has not been fully written')
            while entry['next'] < len(coordinates):
                if verified >= VERIFY_CHUNKS or time.monotonic() - start >= VERIFY_SECONDS:
                    if fingerprint(path) != before:
                        entries.pop(key, None)
                    save(state)
                    return False
                if verified % 128 == 0 and not generation_allowed(state):
                    if fingerprint(path) != before:
                        entries.pop(key, None)
                    save(state)
                    return False
                cx, cz = coordinates[entry['next']]
                external = read_full_chunk(stream, header, directory, cx, cz)
                if external:
                    entry['external'][external[0]] = external[1]
                entry['next'] += 1
                verified += 1
        if fingerprint(path) != before or not external_unchanged(directory, entry):
            entries.pop(key, None)
            save(state)
            return False
    save(state)
    return coverage_complete(state, directory)


def disable_timer():
    subprocess.run(['systemctl', 'disable', '--now', TIMER], check=True, timeout=15)


def finish(state, task, directory):
    # Recheck after all bounded reads and status waits, before any config write.
    if not owned_task(task) or task['cancelled'] != 'true':
        raise RuntimeError('RTP promotion requires the owned completed Chunky task')
    if not generation_allowed(state):
        return
    current = task_snapshot()
    if current['cancelled'] != 'true' or not coverage_complete(state, directory):
        raise RuntimeError('Terrain completion proof changed; RTP radius was not changed')
    cfg = ROOT / 'config/EssentialCommands.properties'
    rules = ROOT / 'config/holylois-server.json'
    if cfg.is_symlink() or rules.is_symlink():
        raise RuntimeError('Unexpected configuration symlink')
    # Since onboarding 1.7.0 the add-on owns /rtp (Essential Commands rtp is off); a legacy rtp_radius line is kept in step.
    source = cfg.read_text(encoding='utf-8') if cfg.exists() else None
    old_rules = rules.read_text(encoding='utf-8')
    pattern = r'(?m)^rtp_radius=\d+\s*$'
    matches = len(re.findall(pattern, source)) if source is not None else 0
    if matches > 1:
        raise IOError('Unexpected RTP configuration')
    essential = matches == 1
    values = json.loads(old_rules)
    if not isinstance(values, dict) or 'rtpRadius' not in values:
        raise IOError('Unexpected automatic placement configuration')
    for path, name in ((cfg, 'EssentialCommands-before.properties'), (rules, 'holylois-server-before.json')):
        if path == cfg and not essential:
            continue
        backup = JOB / name
        if backup.is_symlink():
            raise RuntimeError('Unexpected backup symlink')
        if not backup.exists():
            shutil.copy2(path, backup)
            backup.chmod(0o600)
    values['rtpRadius'] = RTP_RADIUS
    try:
        if essential:
            atomic_text(cfg, re.sub(pattern, f'rtp_radius={RTP_RADIUS}', source))
        atomic_text(rules, json.dumps(values, indent=2) + '\n')
        if essential:
            command('essentialcommands config reload')
        state.update(complete=True, phase='complete', rtp_radius=RTP_RADIUS,
                     full_chunks_verified=expected_chunks(), completed_at=time.time())
        save(state)
    except Exception:
        state.update(complete=False, phase='verifying')
        if essential:
            atomic_text(cfg, source)
        atomic_text(rules, old_rules)
        try:
            if essential:
                command('essentialcommands config reload')
        except OSError:
            pass
        raise
    disable_timer()
    print(f'Terrain complete: all {expected_chunks()} matching FULL chunks verified. '
          f'RTP radius {RTP_RADIUS} configured; reload queued and timer disabled.')


def run_job(state):
    if state.get('complete') or state.get('phase') == 'blocked':
        disable_timer()
        return
    if subprocess.run(['systemctl', 'is-active', '--quiet', 'minecraft'], timeout=10).returncode:
        print('Generation held because the Minecraft service is stopped.')
        return
    if (JOB / 'hold').exists():
        # Owner hold (e.g. waiting for structure mods, which only reach new chunks): pause through the normal
        # checkpointed path and start nothing. Delete the hold file to resume where Chunky stopped.
        if state.get('started') and state.get('running', True):
            request_pause(state)
            checkpoint(state)
        print('Generation held by the owner (hold file). Delete it to resume.')
        return
    if not generation_allowed(state):
        return
    if state.get('pause_pending') and checkpoint(state) is None:
        return
    if time.time() < state.get('rest_until', 0):
        print(f'Resting until {time.strftime("%H:%M", time.localtime(state["rest_until"]))} to let the server catch up.')
        return
    pause_for = rest_needed(state, time.time(), recent_lag())
    if pause_for:
        request_pause(state)
        checkpoint(state)
        state['rest_until'] = time.time() + pause_for
        save(state)
        print(f'Generation paused for {pause_for // 60} minutes (server lag or end of a slice).')
        return
    if not state.get('started'):
        if TASK.exists():
            raise RuntimeError('Archive the previous Chunky task while Minecraft is stopped, then restart before enabling this timer')
        state.update(started=True, running=True, phase='running', started_at=time.time(), resumed_at=time.time(),
                     generation_radius=GENERATION_RADIUS,
                     selection={'world': WORLD, 'center': [0, 0], 'shape': 'square', 'pattern': 'region'})
        save(state)
        # StartCommand otherwise asks to confirm replacement of a resumable task.
        # No cancel/confirm, checkpoint removal, or automatic task takeover here.
        command('chunky pattern region')
        command(f'chunky start {WORLD} square 0 0 {GENERATION_RADIUS}')
        print(f'Started owned {GENERATION_RADIUS}-block square generation. RTP radius is unchanged.')
        return
    if state.get('running') is True:
        try:
            active_task = task_snapshot()
        except CheckpointIncomplete:
            return
        if active_task['cancelled'] != 'true':
            return
    task = checkpoint(state)
    if task is None or not generation_allowed(state):
        return
    state['checkpoint_chunks'] = int(task['chunks'])
    if task['cancelled'] != 'true':
        if state.get('running') is True:
            return
        state.update(running=True, pause_pending=False, phase='running', resumed_at=time.time())
        save(state)
        command('chunky continue ' + WORLD)
        print(f'Generation resumed: saved {task["chunks"]}/{expected_chunks()} chunks. RTP radius is unchanged.')
        return
    if state.get('phase') != 'verifying':
        state.update(phase='verifying', completion_seen=time.time(), running=False)
        save(state)
        command('save-all flush')
        time.sleep(2)
        if not generation_allowed(state):
            return
    directory = region_directory()
    try:
        complete = verify_full_area(state, directory)
    except (OSError, zlib.error) as error:
        save(state)
        if time.time() - state['completion_seen'] > COMPLETION_GRACE:
            raise RuntimeError('Chunky ended without full stored coverage: ' + str(error)) from error
        if not generation_allowed(state):
            return
        command('save-all flush')
        print('Generation complete; waiting for remaining asynchronous chunks to reach storage: ' + str(error))
        return
    if complete:
        finish(state, task, directory)
    else:
        count = sum(entry['next'] for entry in state.get('verified_regions', {}).values())
        print(f'Verified {count}/{expected_chunks()} stored FULL chunks. RTP radius is unchanged.')


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Run as root')
    if (ROOT.resolve() != ROOT or JOB.resolve() != JOB or ROOT.is_symlink()
            or JOB.is_symlink() or STATE.is_symlink() or TASK.is_symlink()):
        raise RuntimeError('Unexpected server or job paths')
    JOB.mkdir(mode=0o700, parents=True, exist_ok=True)
    import fcntl
    fd = os.open(JOB / 'job.lock', os.O_WRONLY | os.O_CREAT | os.O_APPEND
                 | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another terrain job step is already running.')
            return
        try:
            state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {
                'version': 2, 'started': False, 'complete': False}
            if not isinstance(state, dict) or state.get('version') != 2:
                raise RuntimeError('Archive the old terrain job state while its timer is stopped before installing version 2')
            selection = {'world': WORLD, 'center': [0, 0], 'shape': 'square', 'pattern': 'region'}
            if state.get('started') and (state.get('generation_radius') != GENERATION_RADIUS
                                         or state.get('selection') != selection):
                raise RuntimeError('The stored job selection changed; archive its state before starting a new owned task')
        except Exception:
            disable_timer()
            raise
        try:
            run_job(state)
        except Exception as error:
            try:
                request_pause(state)
            except Exception:
                pass
            if not state.get('complete'):
                state.update(phase='blocked', error=str(error), blocked_at=time.time())
                save(state)
            disable_timer()
            raise


if __name__ == '__main__':
    main()
