"""Explicit stopped historical restore with retained HMAC requests. No CLI, service control or deletion.

Whole-root replacement retains the former root outside the server. Anchor reconciliation alone never proves
account erasure: retained requests still block the default start, and checked startup must inspect all stores.
Real restores require their own exact approval and independently protected private case/action recovery.
"""
import contextlib
import hashlib
import json
import os
import tarfile
from pathlib import Path
from guard_checkpoint import pair, verify_current
from guard_snapshot import private_read
from privacy_actions import canonical, private_directory, move, sync, relative
from privacy_backup import BoundedInfo, opened, CHUNK, stamp
from privacy_exports import invalidate, gate_bytes, unique
from privacy_review import cases_for, digest, sha
from recovery_guard import identity


class HistoricalRestore:
    def __init__(self, guard, backup, archive_sha256, directory, cases, lease, runtime_review,
                 checkpoint_base, provider):
        self.guard, self.backup, self.archive = guard, backup, sha(archive_sha256)
        self.directory = canonical(directory); private_directory(self.directory.parent)
        self.cases, self.lease, self.runtime = cases, lease, runtime_review
        self.base, self.provider = canonical(checkpoint_base), provider
        if backup.root != guard.root: raise ValueError('Restore source must bind the exact server root')
        for path in (guard.root, guard.directory, backup.directory, self.base):
            if self.directory.is_relative_to(path) or path.is_relative_to(self.directory):
                raise ValueError('Restore journal must be separate from protected originals')
        if self.directory.parent.stat().st_dev != guard.root.parent.stat().st_dev:
            raise ValueError('Retained whole-root replacement requires the same filesystem')

    def plan(self, restore_id):
        if self.lease() is not True: raise ValueError('Stopped writers required')
        identity(restore_id); before = pair(self.guard)
        cases_for(self.guard, json.loads(json.dumps(self.cases)))
        return {'schema': 1, 'kind': 'retained-request-restore', 'id': restore_id,
                'root': str(self.guard.root), 'directory': str(self.directory), 'archive_sha256': self.archive,
                'guard_pair_sha256': before, 'cases_sha256': digest(self.cases), 'runtime_sha256': sha(self.runtime())}

    def begin(self, restore_id, approval):
        manifest = self.plan(restore_id)
        if digest(manifest) != sha(approval): raise ValueError('Exact historical restore approval required')
        if self.backup.verify(self.archive) is not True: raise ValueError('Stopped recovery source required')
        if verify_current(self.guard, self.base, self.provider)['fingerprint'] != manifest['guard_pair_sha256']:
            raise ValueError('Latest guard protection changed')
        with self.guard.locked():
            state = self.guard.state(); self.guard._anchor(state)
            ledger = private_read(self.guard.directory / 'ledger.json', 1_000_000)
            key = private_read(self.guard.directory / 'subject-key.json', 1_000_000)
            if (hashlib.sha256(ledger + b'\0' + key).hexdigest() != manifest['guard_pair_sha256']
                    or digest(self.cases) != manifest['cases_sha256'] or sha(self.runtime()) != manifest['runtime_sha256']
                    or self.lease() is not True): raise ValueError('Restore binding changed before barrier')
            self.directory.mkdir(mode=0o700, exist_ok=False); sync(self.directory.parent)
            self.guard._atomic(self.directory / 'original-review.json', {'manifest': manifest, 'ledger': ledger.decode('utf-8')})
            invalidate(self.guard)
            self.guard._atomic(self.guard.directory / 'ledger.json', dict(state, pending_restore=restore_id))
        return {'restore_pending': True, 'requests_retained': len(state['requests']), 'deleted': 0}

    def _record(self, approval):
        private_directory(self.directory); private_directory(self.directory.parent)
        record = json.loads(private_read(self.directory / 'original-review.json', 2_000_000), object_pairs_hook=unique)
        if set(record) != {'manifest', 'ledger'}: raise ValueError('Unknown restore review')
        manifest = record['manifest']
        if (digest(manifest) != sha(approval) or manifest['root'] != str(self.guard.root)
                or manifest['directory'] != str(self.directory) or manifest['archive_sha256'] != self.archive
                or manifest['cases_sha256'] != digest(self.cases) or manifest['runtime_sha256'] != sha(self.runtime())
                or self.lease() is not True): raise ValueError('Restore approval, writer, cases or code changed')
        ledger = record['ledger'].encode('utf-8'); before = json.loads(ledger, object_pairs_hook=unique)
        key = private_read(self.guard.directory / 'subject-key.json', 1_000_000)
        if (hashlib.sha256(ledger + b'\0' + key).hexdigest() != manifest['guard_pair_sha256']
                or before['pending_restore'] is not None
                or self.guard.state() != dict(before, pending_restore=manifest['id'])):
            raise ValueError('Current external requests/key differ from protected pre-restore state')
        if gate_bytes(self.guard.export_gate, os.geteuid())[1]['ready']:
            raise ValueError('Public serving must remain blocked during restoration')
        return manifest, before

    @contextlib.contextmanager
    def _tar(self):
        with opened(self.backup.directory / 'backup.tar') as stream:
            with tarfile.open(fileobj=stream, mode='r|', tarinfo=BoundedInfo) as archive:
                yield archive

    def _relative(self, member):
        if member.name == self.guard.root.name:
            if not member.isdir(): raise ValueError('Archive root must be a directory')
            return Path('.')
        prefix = self.guard.root.name + '/'
        if not member.name.startswith(prefix) or not (member.isdir() or member.isfile()) or member.sparse is not None:
            raise ValueError('Unsupported historical archive path or type')
        return Path(relative(member.name[len(prefix):]))

    def extract(self, approval):
        self._record(approval)
        if self.backup.verify(self.archive) is not True: raise ValueError('Recovery source changed')
        target = self.directory / 'tree'; target.mkdir(mode=0o700, exist_ok=False)
        directories = []
        with self._tar() as archive:
            for member in archive:
                name = self._relative(member); path = canonical(target / name)
                if member.isdir():
                    if name != Path('.'): path.mkdir(mode=0o700, exist_ok=False)
                    directories.append((path, member))
                else:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'wb') as outgoing, archive.extractfile(member) as incoming:
                        copied = 0
                        for raw in iter(lambda: incoming.read(CHUNK), b''):
                            copied += len(raw); outgoing.write(raw)
                        if copied != member.size: raise ValueError('Truncated historical payload')
                        outgoing.flush(); os.fsync(outgoing.fileno())
                    self._metadata(path, member)
        for path, member in reversed(directories): self._metadata(path, member)
        sync(self.directory); self.compare(target, approval)
        return {'extracted': True, 'requests_retained': len(self.guard.state()['requests']), 'deleted': 0}

    @staticmethod
    def _metadata(path, member):
        os.chown(path, member.uid, member.gid); path.chmod(member.mode & 0o777)

    def compare(self, tree, approval):
        self._record(approval); tree = canonical(tree); seen = set()
        # backup.verify checks strict archive types/paths before this parser. Recheck around extraction/comparison.
        if self.backup.verify(self.archive) is not True: raise ValueError('Historical original changed')
        with self._tar() as archive:
            for member in archive:
                name = self._relative(member); seen.add(name.as_posix())
                path = canonical(tree / name); info = path.stat()
                if ((info.st_mode & 0o777) != (member.mode & 0o777) or info.st_uid != member.uid or info.st_gid != member.gid
                        or member.isdir() != path.is_dir()): raise ValueError('Restored metadata differs from original')
                if member.isfile():
                    if not path.is_file() or info.st_nlink != 1 or info.st_size != member.size:
                        raise ValueError('Restored file shape differs')
                    # Restored files use their original Minecraft ownership/mode, not private receipt permissions.
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, 'rb') as actual, archive.extractfile(member) as expected:
                        before = os.fstat(actual.fileno())
                        while True:
                            raw = expected.read(CHUNK)
                            if not raw: break
                            if actual.read(len(raw)) != raw: raise ValueError('Restored bytes differ from original')
                        if actual.read(1) or stamp(os.fstat(actual.fileno())) != stamp(before) or stamp(path.stat()) != stamp(before):
                            raise ValueError('Restored file changed while comparing')
        actual = {p.relative_to(tree).as_posix() for p in tree.rglob('*')} | {'.'}
        if actual != seen: raise ValueError('Restored file membership differs from original')
        self._record(approval)

    def install(self, approval):
        tree = self.directory / 'tree'; self.compare(tree, approval)
        with self.guard.locked():
            self._record(approval)
            move(self.guard.root, self.directory / 'original-root')
            sync(self.guard.root.parent); sync(self.directory)
            # A failure here keeps both copies and the external pending barrier. Never guess a resume.
            move(tree, self.guard.root); sync(self.guard.root.parent); sync(self.directory)
        self.compare(self.guard.root, approval)
        return {'installed': True, 'previous_root_retained': True, 'deleted': 0}

    def reconcile(self, approval):
        if not (self.directory / 'original-root').is_dir(): raise ValueError('Retained prior root required')
        self.compare(self.guard.root, approval)
        with self.guard.locked():
            _, before = self._record(approval)
            self.compare(self.guard.root, approval)
            # The outside ledger/key are NEVER restored from the archive. Keep every request.
            state = self.guard._rotate(dict(before, pending_restore=None))
        return {'reconciled': True, 'requests_retained': len(state['requests']), 'allow_start': False,
                'needs_fresh_checkpoint_and_store_review': True, 'deleted': 0}
