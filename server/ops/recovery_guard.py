"""Private restore barrier. No account reads, erasure adapters or deletion approval.

The external state never travels inside a Minecraft backup. Any recorded request blocks
start/restore completion until a separately reviewed per-store erasure workflow exists.
"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import hmac
import json
import os
import stat
import uuid
from pathlib import Path

STATE = Path('/var/lib/holylois/recovery-guard')
ROOT = Path('/opt/minecraft')
EXPORT_GATE = Path('/var/lib/holylois-stats/privacy-gate.json')
ANCHOR = Path('config/.holylois-recovery-generation.json')


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Canonical request/generation identity required')
    return value


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class Guard:
    def __init__(self, root=ROOT, directory=None, *, export_gate=None):
        self.root, self.directory = Path(root).absolute(), Path(STATE if directory is None else directory).absolute()
        self.export_gate = Path(export_gate).absolute() if export_gate is not None else (
            EXPORT_GATE if self.root == ROOT and directory is None else None)
        if self.export_gate is not None and (self.export_gate.is_relative_to(self.root)
                or self.export_gate.is_relative_to(self.directory)):
            raise ValueError('Export serving gate must survive server restores')
        if (self.root.resolve() != self.root or self.directory.resolve() != self.directory
                or self.directory.is_relative_to(self.root) or self.root.is_relative_to(self.directory)):
            raise ValueError('Guard state must be separate from the unlinked server root')

    def _private(self, path, directory=False):
        info = path.lstat()
        kind = stat.S_ISDIR if directory else stat.S_ISREG
        if not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('Guard state ownership, type or private permissions invalid')
        if not directory and info.st_nlink != 1:
            raise ValueError('Linked guard state rejected')

    def _read(self, name):
        path = self.directory / name
        self._private(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError('Oversized guard state')
        return json.loads(data)

    def _atomic(self, path, value, mode=0o600):
        if path.parent.resolve() != path.parent or not path.parent.is_dir():
            raise ValueError('Linked or missing guard parent rejected')
        if path.exists() or path.is_symlink():
            if not stat.S_ISREG(path.lstat().st_mode) or path.lstat().st_nlink != 1:
                raise ValueError('Linked or special guard target rejected')
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        self._sync(path.parent)

    @staticmethod
    def _sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    @contextlib.contextmanager
    def locked(self):
        self._private(self.directory, directory=True)
        path = self.directory / 'lock'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            self._private(path)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def state(self):
        if (self.directory / 'transaction.json').exists() or (self.directory / 'transaction.json').is_symlink():
            raise ValueError('Incomplete generation transaction requires recovery review')
        secret = bytes.fromhex(self._read('subject-key.json')['key'])
        if len(secret) != 32:
            raise ValueError('Invalid private subject key')
        value = self._read('ledger.json')
        if value.get('schema') != 1 or value.get('root') != str(self.root):
            raise ValueError('Guard schema/root binding invalid')
        identity(value.get('generation'))
        requests = value.get('requests')
        if not isinstance(requests, list) or len(requests) > 10000:
            raise ValueError('Invalid request inventory')
        seen = set()
        for request in requests:
            key = identity(request.get('id'))
            if key in seen or not isinstance(request.get('subject_hmac'), str) or len(request['subject_hmac']) != 64:
                raise ValueError('Invalid or duplicate request')
            int(request['subject_hmac'], 16)
            date = datetime.datetime.fromisoformat(request['recorded_at'])
            if date.tzinfo is None:
                raise ValueError('Request time must have a timezone')
            seen.add(key)
        pending = value.get('pending_restore')
        if pending is not None:
            identity(pending)
        return value

    def _anchor(self, state):
        path = self.root / ANCHOR
        if path.parent.resolve() != path.parent or not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 4096:
            raise ValueError('Generation anchor missing, linked or invalid')
        with path.open() as stream:
            if json.load(stream) != {'schema': 1, 'generation': state['generation']}:
                raise ValueError('Backup generation differs from the external guard')

    @staticmethod
    def _clear_requests(state):
        if state['requests']:
            raise ValueError('Recorded deletion requests require per-store recovery review; start blocked')

    def _rotate(self, state):
        state = dict(state, generation=str(uuid.uuid4()), pending_restore=None)
        # A crash at either write leaves this external barrier intact. Never guess which half won.
        self._atomic(self.directory / 'transaction.json', {'schema': 1, 'started': stamp()})
        self._atomic(self.root / ANCHOR, {'schema': 1, 'generation': state['generation']}, 0o644)
        self._atomic(self.directory / 'ledger.json', state)
        (self.directory / 'transaction.json').unlink()
        self._sync(self.directory)
        return state

    def initialize(self):
        if not self.root.is_dir() or not (self.root / 'config').is_dir():
            raise ValueError('Existing server/config root required')
        if self.directory.exists() or self.directory.is_symlink():
            raise FileExistsError('Existing external guard evidence must be preserved')
        if (self.root / ANCHOR).exists() or (self.root / ANCHOR).is_symlink():
            raise ValueError('Existing backup generation forbids empty-ledger initialization')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        with self.locked():
            self._atomic(self.directory / 'subject-key.json', {'key': os.urandom(32).hex()})
            self._rotate({'schema': 1, 'root': str(self.root), 'generation': str(uuid.uuid4()),
                          'requests': [], 'pending_restore': None})

    def start(self):
        with self.locked():
            state = self.state()
            if state['pending_restore'] is not None:
                raise ValueError('Incomplete restore requires review; start blocked')
            self._clear_requests(state)
            self._anchor(state)
            self._rotate(state)
        return {'allow_start': True, 'requests': 0}

    def record_request(self, request_id, subject):
        identity(request_id); identity(subject)
        with self.locked():
            state = self.state()
            secret = bytes.fromhex(self._read('subject-key.json')['key'])
            if len(secret) != 32:
                raise ValueError('Invalid private subject key')
            digest = hmac.new(secret, subject.encode('ascii'), hashlib.sha256).hexdigest()
            prior = next((row for row in state['requests'] if row['id'] == request_id), None)
            if prior:
                if prior['subject_hmac'] != digest:
                    raise ValueError('Request identity already belongs to another subject')
                return
            from privacy_exports import invalidate
            invalidate(self)
            state['requests'].append({'id': request_id, 'subject_hmac': digest, 'recorded_at': stamp()})
            self._atomic(self.directory / 'ledger.json', state)

    def begin_restore(self, restore_id):
        identity(restore_id)
        with self.locked():
            state = self.state()
            if state['pending_restore'] is not None:
                raise ValueError('Another restore is already pending')
            self._clear_requests(state)
            self._anchor(state)
            from privacy_exports import invalidate
            invalidate(self)
            state['pending_restore'] = restore_id
            self._atomic(self.directory / 'ledger.json', state)

    def complete_restore(self, restore_id):
        """Only the trusted restore caller invokes this after successful extraction, never a supplied receipt."""
        identity(restore_id)
        with self.locked():
            state = self.state()
            if state['pending_restore'] != restore_id:
                raise ValueError('Restore identity differs from the pending barrier')
            self._clear_requests(state)
            self._rotate(state)


def configured(root=ROOT):
    guard = Guard(root)
    if guard.directory.exists() or guard.directory.is_symlink() or (guard.root / ANCHOR).exists():
        return guard
    # Compatibility for servers that have not deployed the systemd guard yet, not a start-gate fallback.
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--state-dir', type=Path, default=STATE)
    parser.add_argument('action', choices=['initialize', 'start', 'begin-restore', 'record-request'])
    parser.add_argument('--id'); parser.add_argument('--subject')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Privileged operator required')
    if args.action != 'start':
        from recovery_set import require_stopped
        require_stopped()
    guard = Guard(args.root, args.state_dir)
    if args.action == 'initialize': guard.initialize()
    elif args.action == 'start': guard.start()
    elif args.action == 'begin-restore': guard.begin_restore(args.id)
    else: guard.record_request(args.id, args.subject)
    print(json.dumps({'ok': True, 'action': args.action, 'player_data_changed': False}))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        raise SystemExit('Recovery guard blocked the operation; inspect the private state and operator guide.')
