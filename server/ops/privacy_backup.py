"""Read-only stopped recovery-set verification. No extraction, upload, service control or startup permit.

The original maintenance receipt and its pin must come from the trusted capture/upload workflow, separately
from the backup folder. Flags alone cannot prove stopped capture. Unknown or linked archive formats require
separate review. One reader may reuse unchanged byte checks within a single stopped operation, never across
processes. Provider metadata and all local metadata are rechecked on every call.
"""
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from backup_receipts import safe_remote, remote_md5
from guard_snapshot import private_read
from privacy_actions import canonical, private_directory
from privacy_exports import unique
from privacy_review import sha
from recovery_set import WRITERS

TOTAL = 64 * 1024 ** 3
CHUNK = 1024 * 1024
REMOTE = 'gdrive:Holy Lois Backups/'


class BoundedInfo(tarfile.TarInfo):
    def _proc_member(self, archive):
        # tarfile parses extended headers before yielding a member. Bound them before that allocation.
        extended = (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE,
                    tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK)
        if self.type == tarfile.GNUTYPE_SPARSE or (self.type in extended and not 0 <= self.size <= 64 * 1024):
            raise ValueError('Sparse or oversized archive metadata requires separate review')
        return super()._proc_member(archive)


def stamp(info):
    return tuple(getattr(info, k) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns',
                                          'st_uid', 'st_gid', 'st_mode', 'st_nlink'))


def inspect(path):
    info = canonical(path).stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
            or info.st_mode & 0o7077 or not 0 <= info.st_size <= TOTAL):
        raise ValueError('Private bounded single-link backup original required')
    return stamp(info)


@contextlib.contextmanager
def opened(path):
    before = inspect(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if stamp(os.fstat(stream.fileno())) != before: raise ValueError('Backup source changed before opening')
        yield stream
        if stamp(os.fstat(stream.fileno())) != before or inspect(path) != before:
            raise ValueError('Backup source changed while reading')


def hashes(stream, limit):
    size = 0; h = hashlib.sha256(); md5 = hashlib.md5(usedforsecurity=False)
    while True:
        raw = stream.read(min(CHUNK, limit - size + 1))
        if not raw: break
        size += len(raw)
        if size > limit: raise ValueError('Recovery object exceeds original size')
        h.update(raw); md5.update(raw)
    return {'size': size, 'sha256': h.hexdigest(), 'md5': md5.hexdigest()}


def remote_name(name):
    value = safe_remote(name)
    if not value.startswith('maintenance/') or len(PurePosixPath(value).parts) < 3:
        raise ValueError('Complete stopped maintenance scope required')
    return REMOTE + value


class ReadOnlyDrive:
    def metadata(self, name):
        result = subprocess.run(['rclone', 'lsjson', remote_name(name), '--stat', '--hash', '--tpslimit', '2',
            '--retries', '2', '--low-level-retries', '2', '--timeout', '30s', '--contimeout', '15s'],
            check=True, capture_output=True, timeout=120)
        if len(result.stdout) > 100_000: raise ValueError('Oversized provider metadata')
        return json.loads(result.stdout, object_pairs_hook=unique)

    @contextlib.contextmanager
    def stream(self, name, size):
        if type(size) is not int or not 0 <= size <= TOTAL: raise ValueError('Bounded readback required')
        process = subprocess.Popen(['rclone', 'cat', remote_name(name), '--count', str(size + 1),
            '--bwlimit', '48M', '--tpslimit', '2', '--retries', '1', '--low-level-retries', '1',
            '--timeout', '30s', '--contimeout', '15s', '--max-duration', '30m', '--buffer-size', '1M',
            '--multi-thread-streams', '0'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            yield process.stdout
            if process.wait(timeout=15) != 0: raise OSError('Private backup readback failed')
        finally:
            process.stdout.close()
            if process.poll() is None: process.kill()
            process.wait(timeout=15)


class StoppedSet:
    def __init__(self, root, directory, original, original_sha256, provider):
        self.root = canonical(root); self.directory = private_directory(directory)
        if not self.root.is_dir(): raise ValueError('Explicit current server root required')
        self.original = canonical(original); self.pin = sha(original_sha256); self.provider = provider
        private_directory(self.original.parent)
        for path in (self.directory, self.original):
            if path.is_relative_to(self.root) or self.root.is_relative_to(path):
                raise ValueError('Recovery originals must survive restoration')
        if self.original.is_relative_to(self.directory): raise ValueError('Independent original receipt required')
        self.cache = None

    def _inventory(self):
        private_directory(self.directory); private_directory(self.original.parent)
        raw = private_read(self.original, 2_000_000)
        if hashlib.sha256(raw).hexdigest() != self.pin: raise ValueError('Independent backup receipt changed')
        value = json.loads(raw, object_pairs_hook=unique)
        if set(value) != {'schema', 'verified_at', 'backup', 'members'} or value['schema'] != 1:
            raise ValueError('Unknown original maintenance receipt')
        backup = value['backup']; rows = value['members']
        if (backup.get('kind') != 'maintenance' or backup.get('stream') != 'maintenance'
                or backup.get('base_id') is not None
                or any(backup.get(k) is not True for k in ('whole_set', 'complete', 'verified'))
                or not isinstance(rows, list) or not 2 <= len(rows) <= 1000):
            raise ValueError('Whole independently verified maintenance set required')
        fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        if backup.get('id') != 'maintenance-' + fingerprint: raise ValueError('Original set identity differs')
        members = {}; prefix = 'maintenance/' + self.directory.name + '/'; total = 0
        for row in rows:
            if set(row) != {'path', 'size', 'sha256', 'md5'}: raise ValueError('Exact original object metadata required')
            name = safe_remote(row['path'])
            if not name.startswith(prefix): raise ValueError('Mixed recovery sets refused')
            relative = name[len(prefix):]
            if relative in members: raise ValueError('Duplicate original recovery object')
            if (type(row['size']) is not int or not 0 <= row['size'] <= TOTAL
                    or not re.fullmatch('[a-f0-9]{32}', row['md5'])): raise ValueError('Invalid object size/checksum')
            sha(row['sha256']); total += row['size']; members[relative] = row
        if total > TOTAL or not {'backup.tar', 'recovery-set.json'} <= set(members):
            raise ValueError('Stopped archive/attestation missing or oversized')
        actual = {}; directories = {'.': stamp(self.directory.stat())}
        for path in self.directory.rglob('*'):
            canonical(path)
            if path.is_dir():
                private_directory(path); directories[path.relative_to(self.directory).as_posix()] = stamp(path.stat())
            else: actual[path.relative_to(self.directory).as_posix()] = inspect(path)
        if set(actual) != set(members): raise ValueError('Recovery membership differs from independent original')
        for name, row in members.items():
            if (self.directory / name).stat().st_size != row['size']: raise ValueError('Original object size changed')
        return raw, members, (actual, directories)

    def _archive(self):
        required = {self.root.name, *(self.root.name + '/' + k for k in ('world', 'config', 'mods', 'EasyAuth'))}
        seen = {}; files = set(); payload = 0
        with opened(self.directory / 'backup.tar') as original, tarfile.open(fileobj=original, mode='r|', tarinfo=BoundedInfo) as archive:
            for member in archive:
                name = member.name; path = PurePosixPath(name)
                if (path.as_posix() != name or path.is_absolute() or '\\' in name or ':' in name
                        or any(ord(c) < 32 for c in name) or any(p in ('', '.', '..') for p in name.split('/'))
                        or path.parts[0] != self.root.name or name in seen or len(seen) >= 500_000
                        or not (member.isdir() or member.isfile()) or member.sparse is not None
                        or member.mode & 0o7000 or member.size < 0
                        or any(k not in ('mtime', 'atime', 'ctime', 'path') for k in member.pax_headers)):
                    raise ValueError('Unknown, linked, duplicate or unsafe stopped archive member')
                if len(path.parts) > 1 and path.parts[1].lower() in ('bluemap', 'backups'):
                    raise ValueError('Excluded recursive/rebuildable payload')
                for parent in path.parents:
                    if str(parent) != '.' and seen.get(str(parent)) is not True:
                        raise ValueError('Missing or non-directory archive parent')
                seen[name] = member.isdir()
                if member.isfile():
                    payload += member.size
                    if payload > TOTAL: raise ValueError('Archive payload exceeds review budget')
                    with archive.extractfile(member) as stream:
                        if hashes(stream, member.size)['size'] != member.size: raise ValueError('Truncated payload')
                    files.add(name)
        if (not required <= {n for n, directory in seen.items() if directory}
                or self.root.name + '/server.jar' not in files
                or not any(n.startswith(self.root.name + '/mods/') and n.endswith('.jar') for n in files)
                or not any(n.startswith(self.root.name + '/EasyAuth/') for n in files)
                or not any(n.startswith(self.root.name + '/world/') for n in files)
                or not any(n.startswith(self.root.name + '/config/') for n in files)):
            raise ValueError('Stopped world/account/configuration/software scope missing')

    def verify(self, archive_sha256):
        """Suitable for verified_stopped_backup, with a separately reviewed original receipt pin.

        Reuse is only in memory while original file metadata remains identical. It is not a saved success flag.
        The caller still needs its current stopped-writer lease and separately protected case/guard evidence.
        """
        expected = sha(archive_sha256); raw, members, before = self._inventory()
        if members['backup.tar']['sha256'] != expected: raise ValueError('Wrong stopped archive binding')
        cached = self.cache == (raw, before)
        for name, row in members.items():
            path = self.directory / name
            wanted = {k: row[k] for k in ('size', 'sha256', 'md5')}
            if not cached:
                with opened(path) as stream:
                    if hashes(stream, row['size']) != wanted: raise ValueError('Local backup differs from independent original')
            remote = self.provider.metadata(row['path'])
            if (remote.get('IsDir') is not False or remote.get('Name') != Path(name).name
                    or type(remote.get('Size')) is not int or remote['Size'] != row['size']
                    or remote_md5(remote) != row['md5']): raise ValueError('Provider differs from independent original')
            if not cached:
                with self.provider.stream(row['path'], row['size']) as stream:
                    if hashes(stream, row['size']) != wanted: raise ValueError('Remote readback differs from independent original')
        if self._inventory() != (raw, members, before): raise ValueError('Original recovery set changed during readback')
        attestation = json.loads(private_read(self.directory / 'recovery-set.json', 100_000), object_pairs_hook=unique)
        if (attestation.get('schema') != 1 or attestation.get('kind') != 'stopped-server'
                or attestation.get('archive_sha256') != expected
                or type(attestation.get('archive_bytes')) is not int
                or attestation['archive_bytes'] != members['backup.tar']['size']
                or attestation.get('writers_checked') != list(WRITERS)
                or any(attestation.get(k) is not True for k in ('application_consistent', 'comparison_verified',
                                                              'world_and_external_account_config_same_stop'))):
            raise ValueError('Missing independently bound stopped capture attestation')
        if not cached: self._archive()
        if self._inventory() != (raw, members, before): raise ValueError('Original recovery set changed during verification')
        self.cache = (raw, before)
        return True
