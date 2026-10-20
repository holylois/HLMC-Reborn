"""Private changed-state guard checkpoint and readback. No erasure, pruning or live replacement.

Prepared scheduler: install/enable only after explicit deploy approval including automatic sensitive uploads.
Timer success does not authorize erasure. Future erasure workflows must synchronously verify the latest state.
"""
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from pathlib import Path
from recovery_guard import Guard, ROOT, STATE
from guard_snapshot import snapshot, verify, private_read, new_private_file

BASE = Path('/var/lib/holylois/guard-checkpoints')
REMOTE = 'gdrive:Holy Lois Backups/guard-state'
FILES = ('guard-state.tar', 'receipt.json', 'local-proof.json')


def digest(data): return hashlib.sha256(data).hexdigest()


def pair(guard):
    with guard.locked():
        value = guard.state(); guard._anchor(value)
        if value['pending_restore'] is not None: raise ValueError('Pending restore cannot be current protection')
        ledger = private_read(guard.directory / 'ledger.json', 1_000_000)
        key = private_read(guard.directory / 'subject-key.json', 1_000_000)
        if json.loads(ledger) != value: raise ValueError('Guard changed under lock')
        return digest(ledger + b'\0' + key)


def private_directory(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_relative_to(ROOT) or path.is_relative_to(STATE):
        raise ValueError('Unlinked private checkpoint directory required')
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('Private directory ownership/mode required')
    return path


@contextlib.contextmanager
def locked(base):
    base = private_directory(base)
    fd = os.open(base / 'job.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError('Private job lock required')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally: os.close(fd)


def prepared(guard, base, fingerprint):
    directory = base / fingerprint
    if not directory.exists():
        receipt = snapshot(guard, directory)
    else:
        private_directory(directory)
        receipt = json.loads(private_read(directory / 'receipt.json', 100_000))
    proof_record = directory / 'local-proof.json'
    if proof_record.exists():
        proof = json.loads(private_read(proof_record, 100_000))
        proof_name = proof.get('proof_directory', '')
        if not re.fullmatch(r'proof-[a-f0-9]{32}', proof_name): raise ValueError('Invalid proof location')
        restored = private_directory(directory / proof_name)
        recovered = Guard(guard.root, restored)
        with recovered.locked(): recovered.state()
        if (proof.get('archive_sha256') != receipt['archive_sha256'] or proof.get('passed') is not True
                or proof.get('fingerprint') != fingerprint): raise ValueError('Local proof changed')
    else:
        proof_name = 'proof-' + uuid.uuid4().hex
        proof = verify(directory / 'guard-state.tar', receipt, directory / proof_name)
        restored = directory / proof_name
        proof.update(proof_directory=proof_name, fingerprint=fingerprint)
        # An interrupted proof is retained, never trusted without its completed record.
        new_private_file(proof_record, (json.dumps(proof, sort_keys=True) + '\n').encode())
        Guard._sync(directory)
    restored_pair = digest(private_read(restored / 'ledger.json', 1_000_000) + b'\0'
                           + private_read(restored / 'subject-key.json', 1_000_000))
    if restored_pair != fingerprint or pair(guard) != fingerprint:
        raise ValueError('Guard changed during checkpoint preparation; preserve newer state')
    raw = private_read(directory / 'guard-state.tar', 2_000_000)
    if len(raw) != receipt['archive_bytes'] or digest(raw) != receipt['archive_sha256']:
        raise ValueError('Checkpoint archive changed')
    return directory, receipt


class Drive:
    """Immutable private uploads, provider hashes AND bounded full readback against local originals."""
    def command(self, *args):
        return subprocess.run(['rclone', *args, '--tpslimit', '2', '--retries', '2', '--low-level-retries', '2',
                               '--timeout', '30s', '--contimeout', '15s', '--buffer-size', '1M',
                               '--multi-thread-streams', '0'], check=True, capture_output=True, timeout=120).stdout

    def ensure(self, path, fingerprint, name):
        if not re.fullmatch('[a-f0-9]{64}', fingerprint) or name not in FILES:
            raise ValueError('Private provider target required')
        data = private_read(path, 2_000_000)
        remote = REMOTE + '/checkpoint-' + fingerprint + '/' + name
        self.command('copyto', str(path), remote, '--immutable', '--checksum')
        row = json.loads(self.command('lsjson', remote, '--stat', '--hash'))
        hashes = {str(k).lower(): str(v).lower() for k, v in row.get('Hashes', {}).items()}
        if row.get('IsDir') is not False or row.get('Name') != name or row.get('Size') != len(data):
            raise ValueError('Provider object identity/size differs')
        if hashes.get('md5') != hashlib.md5(data, usedforsecurity=False).hexdigest():
            raise ValueError('Provider differs from original checksum')
        if self.command('cat', remote, '--count', str(len(data) + 1)) != data:
            raise ValueError('Off-site readback differs from original bytes')


def checkpoint(guard, base, provider):
    base = private_directory(base)
    if (base.is_relative_to(guard.directory) or guard.directory.is_relative_to(base)
            or base.is_relative_to(guard.root) or guard.root.is_relative_to(base)):
        raise ValueError('Checkpoint must remain separate from active guard')
    with locked(base):
        fingerprint = pair(guard)
        prior = None
        if (base / 'latest.json').exists(): prior = json.loads(private_read(base / 'latest.json', 100_000))
        directory, receipt = prepared(guard, base, fingerprint)
        for name in FILES: provider.ensure(directory / name, fingerprint, name)
        if pair(guard) != fingerprint:
            raise ValueError('Newer guard state needs its own verified checkpoint')
        record = {'schema': 1, 'fingerprint': fingerprint, 'archive_sha256': receipt['archive_sha256'],
                  'ledger_sha256': receipt['ledger_sha256'], 'offsite_verified': True,
                  'verified_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'production_restore_authorized': False, 'expiry_eligible': False}
        guard._atomic(base / 'latest.json', record)
        return {'passed': True, 'changed_state': prior is None or prior.get('fingerprint') != fingerprint,
                'offsite_verified': True, 'archive_bytes': receipt['archive_bytes'],
                'live_state_changed': False, 'production_restore_authorized': False, 'deleted': 0}


def main():
    if os.geteuid() != 0: raise ValueError('Privileged checkpoint operator required')
    os.umask(0o077)
    print(json.dumps(checkpoint(Guard(), BASE, Drive())))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError):
        raise SystemExit('Private guard checkpoint failed; retain evidence and review. No erasure authority.')
