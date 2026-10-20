"""Reviewed reversible file actions. No default paths, CLI, account discovery or erasure completion.

Originals move into an outside-root private journal. Resume reconciles actual bytes, never a supplied success
receipt. Unknown changes refuse progress. Undo retains replacements and never releases guard requests.
"""
import contextlib
import ctypes
import fcntl
import json
import os
import stat
from pathlib import Path
from guard_snapshot import private_read
from guard_checkpoint import pair, verify_current
from privacy_review import STORES, cases_for, digest, sha
from privacy_exports import invalidate, gate_bytes, unique

LIMIT = 64 * 1024 * 1024
OBLIGATIONS = frozenset(('permissions', 'support-moderation', 'shared-ownership', 'external-copies'))


def canonical(path):
    path = Path(path).absolute()
    if path.resolve() != path: raise ValueError('Unlinked canonical action path required')
    return path


def relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(ord(c) < 32 for c in name) or Path(name).is_absolute()
            or '..' in Path(name).parts or Path(name).as_posix() != name or name == '.'):
        raise ValueError('Explicit portable relative action path required')
    return name


def file(path):
    path = canonical(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > LIMIT
                or stat.S_IMODE(before.st_mode) & 0o7000):
            raise ValueError('Bounded single-link regular action source required')
        raw = stream.read(LIMIT + 1); after = os.fstat(stream.fileno())
    fields = lambda s: (s.st_ino, s.st_size, s.st_mtime_ns, s.st_uid, s.st_gid, s.st_mode)
    if len(raw) != before.st_size or fields(before) != fields(after) or fields(path.stat()) != fields(after):
        raise ValueError('Action source changed during inspection')
    from hashlib import sha256
    return {'sha256': sha256(raw).hexdigest(), 'mode': stat.S_IMODE(before.st_mode),
            'uid': before.st_uid, 'gid': before.st_gid, 'bytes': len(raw), 'device': before.st_dev}


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def move(source, destination):
    """Linux atomic no-replace rename. Refuse unsupported systems instead of overwriting evidence."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    if rename is None: raise OSError('Atomic no-replace moves are required')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, 'Atomic no-replace move refused')


def private_directory(path):
    path = canonical(path); info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('Private operator-owned transaction directory required')
    return path


@contextlib.contextmanager
def locked(directory):
    fd = os.open(directory / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise ValueError('Private transaction lock required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally: os.close(fd)


class Plan:
    def __init__(self, root, actions, cases_sha256, runtime_sha256, backup_sha256, reviews):
        self.root = canonical(root)
        self.actions = []
        self.cases, self.runtime, self.backup = map(sha, (cases_sha256, runtime_sha256, backup_sha256))
        if not self.root.is_dir() or not isinstance(actions, list) or not 0 < len(actions) <= 1000:
            raise ValueError('Existing root and bounded explicit actions required')
        if not isinstance(reviews, dict) or set(reviews) != STORES | OBLIGATIONS:
            raise ValueError('Every store, permission, hold, shared ownership and external scope needs review')
        for value in reviews.values():
            if set(value) != {'decision', 'evidence_sha256'} or value['decision'] not in ('change', 'verify-only', 'held'):
                raise ValueError('Unknown scope review decision')
            sha(value['evidence_sha256'])
        self.reviews = json.loads(json.dumps(reviews))
        names = set(); budget = 0
        for action in actions:
            if set(action) != {'relative', 'store', 'before', 'replacement'} or action['store'] not in STORES:
                raise ValueError('Explicit reviewed file/store action required')
            name = relative(action['relative']); before = action['before']; replacement = action['replacement']
            if name in names or any(Path(name).is_relative_to(n) or Path(n).is_relative_to(name) for n in names):
                raise ValueError('Duplicate or overlapping action source')
            if (set(before) != {'sha256', 'mode', 'uid', 'gid', 'bytes', 'device'}
                    or any(type(before[k]) is not int or before[k] < 0 for k in ('mode', 'uid', 'gid', 'bytes', 'device'))
                    or before['bytes'] > LIMIT or before['mode'] > 0o777):
                raise ValueError('Exact original byte and ownership inventory required')
            sha(before['sha256'])
            if replacement is not None and (not isinstance(replacement, bytes) or len(replacement) > LIMIT):
                raise ValueError('Bounded reviewed replacement bytes required')
            if reviews[action['store']]['decision'] != 'change': raise ValueError('Action lacks store-change review')
            budget += before['bytes'] + (len(replacement) if replacement is not None else 0)
            if budget > 256 * 1024 * 1024: raise ValueError('Plan exceeds offline action budget')
            from hashlib import sha256
            if replacement is not None and sha256(replacement).hexdigest() == before['sha256']:
                raise ValueError('No-op replacement is not an account action')
            self.actions.append({'relative': name, 'store': action['store'], 'before': dict(before),
                                 'after': sha256(replacement).hexdigest() if replacement is not None else None,
                                 'replacement': replacement})
            names.add(name)
        changed = {a['store'] for a in self.actions}
        if any(v['decision'] == 'change' and k not in changed for k, v in reviews.items()):
            raise ValueError('Change review has no exact file actions')

    def description(self):
        return json.loads(json.dumps({'schema': 1, 'root': str(self.root), 'cases_sha256': self.cases, 'runtime_sha256': self.runtime,
                'backup_sha256': self.backup, 'reviews': json.loads(json.dumps(self.reviews)),
                'actions': [{k: v for k, v in a.items() if k != 'replacement'} for a in self.actions]}))

    def protection_manifest(self, cases):
        """Private payload index, never terminal/public output. Prepared byte objects need their own readback."""
        evidence = {c['identity_proof_sha256'] for c in cases}
        evidence.update(r['evidence_sha256'] for r in self.reviews.values())
        return {'schema': 1, 'kind': 'private-account-action-proposal', 'cases': json.loads(json.dumps(cases)),
                'plan': self.description(), 'evidence_sha256': sorted(evidence)}

    @classmethod
    def from_journal(cls, directory):
        directory = private_directory(directory)
        record = json.loads(private_read(directory / 'journal.json', 4_000_000), object_pairs_hook=unique)
        if set(record) != {'schema', 'plan', 'status'} or record['schema'] != 1:
            raise ValueError('Existing exact transaction required')
        description = record['plan']; actions = []
        for index, a in enumerate(description['actions']):
            replacement = private_read(directory / 'prepared' / str(index), LIMIT) if a['after'] is not None else None
            from hashlib import sha256
            if replacement is not None and sha256(replacement).hexdigest() != a['after']:
                raise ValueError('Durable prepared replacement differs from reviewed bytes')
            actions.append({'relative': a['relative'], 'store': a['store'], 'before': a['before'], 'replacement': replacement})
        result = cls(description['root'], actions, description['cases_sha256'], description['runtime_sha256'],
                     description['backup_sha256'], description['reviews'])
        if result.description() != description: raise ValueError('Unknown or changed durable action plan')
        return result

    def _temporary(self, action):
        source = self.root / action['relative']
        return canonical(source.with_name(source.name + '.privacy-' + digest(self.description())[:16] + '.pending'))

    def _sidecars(self):
        for action in self.actions:
            source = self.root / action['relative']
            if source.suffix in ('.db', '.sqlite', '.sqlite3') and any(
                    Path(str(source) + suffix).exists() or Path(str(source) + suffix).is_symlink()
                    for suffix in ('-wal', '-shm', '-journal')):
                raise ValueError('SQLite sidecars require a stopped native checkpoint review')

    def _check(self, path, expected):
        got = file(path)
        if got != expected: raise ValueError('File differs from exact reviewed bytes/ownership')

    def _kind(self, action, directory):
        source = canonical(self.root / action['relative']); saved = canonical(directory / 'originals' / action['relative'])
        exists = source.exists(); original = saved.exists()
        if original:
            self._check(saved, action['before'])
            if not exists: return 'moved'
            after = file(source)
            if action['after'] is not None and after['sha256'] == action['after'] and all(
                    after[k] == action['before'][k] for k in ('mode', 'uid', 'gid', 'device')):
                return 'applied'
            raise ValueError('Unexpected source beside retained original; preserve both copies')
        if exists:
            self._check(source, action['before'])
            if self._temporary(action).exists(): raise ValueError('Unbound replacement remnant beside untouched source')
            return 'untouched'
        raise ValueError('Original source and retained copy are both missing')

    def _preconditions(self, guard, cases, approval, lease, runtime_review, verified_backup):
        if approval != digest(self.description()) or lease() is not True:
            raise ValueError('Exact action approval and stopped writers required')
        if any(r['decision'] == 'held' for r in self.reviews.values()):
            raise ValueError('Unresolved hold prevents account actions')
        if not cases or guard.root != self.root or digest(cases) != self.cases:
            raise ValueError('Action root/private cases differ from review')
        before = pair(guard); cases_for(guard, json.loads(json.dumps(cases)))
        if pair(guard) != before or sha(runtime_review()) != self.runtime or verified_backup(self.backup) is not True:
            raise ValueError('Guard/source/stopped recovery proof changed')
        if guard.export_gate is None: raise ValueError('Serving invalidation must be installed')
        gate_bytes(guard.export_gate, os.geteuid())
        self._sidecars()
        return before

    def run(self, guard, cases, directory, approval, lease, runtime_review, verified_backup,
            checkpoint_base, provider, *, verified_case_plan, undo=False, boundary=lambda stage, index: None):
        """Trusted offline caller only. boundary is a fault-injection hook for generated tests."""
        before = self._preconditions(guard, cases, approval, lease, runtime_review, verified_backup)
        if verified_case_plan(self.protection_manifest(cases)) is not True:
            raise ValueError('Exact private cases, evidence and prepared byte objects need independent recovery protection')
        proof = verify_current(guard, checkpoint_base, provider)
        if proof['fingerprint'] != before: raise ValueError('Request state changed before action protection')
        directory = canonical(directory)
        for protected in (self.root, guard.directory, canonical(checkpoint_base)):
            if directory.is_relative_to(protected) or protected.is_relative_to(directory):
                raise ValueError('Transaction originals must remain outside restored and guard/checkpoint roots')
        private_directory(directory.parent)
        fresh = not directory.exists()
        if undo and fresh: raise ValueError('Undo requires an existing exact transaction')
        # Check every source before creating evidence or changing any account file.
        if fresh:
            for action in self.actions:
                self._check(self.root / action['relative'], action['before'])
                if action['before']['device'] != directory.parent.stat().st_dev:
                    raise ValueError('Move-only quarantine requires the same filesystem')
                if self._temporary(action).exists(): raise ValueError('Existing replacement remnant requires review')
            directory.mkdir(mode=0o700); sync(directory.parent)
        private_directory(directory)
        with locked(directory), guard.locked():
            from hashlib import sha256
            current = sha256(private_read(guard.directory / 'ledger.json', 1_000_000) + b'\0'
                             + private_read(guard.directory / 'subject-key.json', 1_000_000)).hexdigest()
            guard.state(); guard._anchor(guard.state())
            if current != before or lease() is not True or sha(runtime_review()) != self.runtime:
                raise ValueError('Guard, writer or runtime changed before transaction')
            journal = directory / 'journal.json'; description = self.description()
            if journal.exists():
                record = json.loads(private_read(journal, 4_000_000), object_pairs_hook=unique)
                if (set(record) != {'schema', 'plan', 'status'} or record.get('schema') != 1
                        or record.get('plan') != description or record.get('status') not in ('pending', 'actions-complete', 'reverting', 'reverted')):
                    raise ValueError('Existing transaction differs from exact plan')
            elif fresh:
                record = {'schema': 1, 'plan': description, 'status': 'pending'}
            else: raise ValueError('Unfinished transaction initialization requires review')
            if record['status'] in ('reverting', 'reverted') and not undo:
                raise ValueError('Do not reapply an undo journal; review a new transaction')
            if undo:
                self._undo_preflight(directory)
            else:
                for action in self.actions:
                    kind = self._kind(action, directory)
                    if record['status'] == 'actions-complete' and kind == 'untouched':
                        raise ValueError('Completed transaction changed; retain it and review a new journal')
            invalidate(guard)
            record['status'] = 'reverting' if undo else 'pending'; guard._atomic(journal, record)
            prepared = directory / 'prepared'; prepared.mkdir(mode=0o700, exist_ok=True)
            for index, action in enumerate(self.actions):
                if action['replacement'] is None: continue
                path = prepared / str(index)
                if path.exists():
                    if private_read(path, LIMIT) != action['replacement']:
                        raise ValueError('Prepared action evidence changed; preserve it for review')
                else:
                    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(action['replacement']); stream.flush(); os.fsync(stream.fileno())
                if private_read(path, LIMIT) != action['replacement']: raise ValueError('Prepared byte readback failed')
            sync(prepared); sync(directory)
            indices = reversed(range(len(self.actions))) if undo else range(len(self.actions))
            def step():
                if lease() is not True or sha(runtime_review()) != self.runtime:
                    raise ValueError('Writer/source changed; retain pending journal')
                self._sidecars()
            for index in indices:
                step()
                if undo: self._undo(self.actions[index], directory, index, boundary, step)
                else: self._apply(self.actions[index], directory, index, boundary, step)
                guard._atomic(journal, record); boundary('journal', index)
            step()
            if undo: self._undo_preflight(directory)
            else:
                if any(self._kind(a, directory) != ('applied' if a['after'] is not None else 'moved') for a in self.actions):
                    raise ValueError('Action disk verification incomplete')
            step()
            record['status'] = 'reverted' if undo else 'actions-complete'; guard._atomic(journal, record)
        return {'actions_checked': len(self.actions), 'reverted': undo, 'originals_retained': True,
                'final_erasure': False, 'allow_start': False, 'uploaded': False}

    def _apply(self, action, directory, index, boundary, step):
        source = self.root / action['relative']; saved = directory / 'originals' / action['relative']
        kind = self._kind(action, directory)
        if kind == 'untouched':
            saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            step()
            move(source, saved); sync(saved.parent); sync(source.parent)
            self._check(saved, action['before']); boundary('moved', index)
            kind = 'moved'
        if action['after'] is None or kind == 'applied': return
        temporary = self._temporary(action)
        step()
        if temporary.exists():
            # Do not guess whether a partial replacement was fully flushed. Keep it for review.
            file(temporary)
            remnants = directory / 'interrupted'; remnants.mkdir(mode=0o700, exist_ok=True)
            import uuid
            move(temporary, remnants / str(uuid.uuid4())); sync(remnants); sync(source.parent)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(action['replacement']); stream.flush(); os.fsync(stream.fileno())
            os.fchown(stream.fileno(), action['before']['uid'], action['before']['gid'])
            os.fchmod(stream.fileno(), action['before']['mode'])
            os.fsync(stream.fileno())
        boundary('replacement-ready', index)
        step()
        move(temporary, source); sync(source.parent); boundary('replaced', index)

    def _undo_preflight(self, directory):
        for index, action in enumerate(self.actions):
            source = canonical(self.root / action['relative']); saved = canonical(directory / 'originals' / action['relative'])
            retained = canonical(directory / 'replacements' / str(index))
            if retained.exists() and (action['after'] is None or file(retained)['sha256'] != action['after']):
                raise ValueError('Undo replacement evidence changed')
            if saved.exists():
                self._check(saved, action['before'])
                if source.exists():
                    after = file(source)
                    if (action['after'] is None or after['sha256'] != action['after']
                            or any(after[k] != action['before'][k] for k in ('mode', 'uid', 'gid', 'device'))):
                        raise ValueError('Undo refuses an unexpected active file')
            else: self._check(source, action['before'])

    def _undo(self, action, directory, index, boundary, step):
        source = self.root / action['relative']; saved = directory / 'originals' / action['relative']
        if not saved.exists(): return
        if source.exists():
            retained = directory / 'replacements' / str(index); retained.parent.mkdir(mode=0o700, exist_ok=True)
            if retained.exists(): raise ValueError('Undo evidence already exists beside active replacement')
            step()
            move(source, retained); sync(retained.parent); sync(source.parent)
            after = file(retained)
            if after['sha256'] != action['after'] or any(after[k] != action['before'][k] for k in ('mode', 'uid', 'gid', 'device')):
                raise ValueError('Active replacement changed during undo; retain both original and replacement')
            boundary('undo-replacement', index)
        step()
        self._check(saved, action['before'])
        move(saved, source); sync(saved.parent); sync(source.parent); boundary('undo-original', index)
