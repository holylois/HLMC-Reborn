"""Bounded private ledger/key snapshot and isolated verification. No upload, pruning or service changes.

The independent original receipt must be trusted. Restoring bytes is not authority to replace the live ledger
with an older copy, release a restore barrier or approve erasure.
"""
import argparse
import datetime
import hashlib
import io
import json
import os
import stat
import tarfile
from pathlib import Path
from recovery_guard import Guard, ROOT, STATE

LIMIT = 2_000_000
FILES = ('ledger.json', 'subject-key.json')


def sha(data): return hashlib.sha256(data).hexdigest()


def private_read(path, limit):
    path = Path(path)
    if path.resolve() != path.absolute(): raise ValueError('Linked private input rejected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError('Regular bounded private input required')
        data = stream.read(limit + 1)
    if len(data) > limit: raise ValueError('Oversized private input')
    return data


def new_private_file(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def new_directory(path, source=None):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_relative_to(ROOT) or path.is_relative_to(STATE):
        raise ValueError('Isolated, unlinked destination outside production data required')
    if source is not None and (path.is_relative_to(source) or source.is_relative_to(path)):
        raise ValueError('Snapshot and active guard must be separate')
    path.mkdir(mode=0o700, exist_ok=False)
    return path


def snapshot(guard, destination):
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        if state['pending_restore'] is not None:
            raise ValueError('Pending restore cannot become a current recovery checkpoint')
        payload = {}
        for name in FILES:
            payload[name] = private_read(guard.directory / name, 1_000_000)
        if json.loads(payload['ledger.json']) != state:
            raise ValueError('Guard changed while snapshot lock held')
        manifest = {'schema': 1, 'kind': 'guard-state', 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'request_count': len(state['requests']), 'generation_sha256': sha(state['generation'].encode('ascii')),
                    'files': {name: {'size': len(data), 'sha256': sha(data)} for name, data in payload.items()}}
        payload['manifest.json'] = (json.dumps(manifest, sort_keys=True) + '\n').encode()
        directory = new_directory(destination, guard.directory)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name, data in payload.items():
                member = tarfile.TarInfo(name); member.size = len(data); member.mode = 0o600
                archive.addfile(member, io.BytesIO(data))
        data = buffer.getvalue()
        if len(data) > LIMIT: raise ValueError('Oversized guard archive')
        new_private_file(directory / 'guard-state.tar', data)
        receipt = {'schema': 1, 'kind': 'guard-state', 'archive_bytes': len(data), 'archive_sha256': sha(data),
                   'ledger_sha256': sha(payload['ledger.json']), 'created_at': manifest['created_at'],
                   'request_count': manifest['request_count'], 'generation_sha256': manifest['generation_sha256'],
                   'offsite_verified': False, 'production_restore_authorized': False, 'expiry_eligible': False}
        new_private_file(directory / 'receipt.json', (json.dumps(receipt, sort_keys=True) + '\n').encode())
        Guard._sync(directory)
        Guard._sync(directory.parent)
        return receipt


def verify(archive_path, trusted_receipt, destination):
    if (trusted_receipt.get('schema') != 1 or trusted_receipt.get('kind') != 'guard-state'
            or type(trusted_receipt.get('archive_bytes')) is not int):
        raise ValueError('Independent original receipt required')
    data = private_read(archive_path, LIMIT)
    if len(data) != trusted_receipt['archive_bytes'] or sha(data) != trusted_receipt['archive_sha256']:
        raise ValueError('Snapshot differs from original receipt')
    contents = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        for member in archive:
            if member.name not in (*FILES, 'manifest.json') or member.name in contents or not member.isfile():
                raise ValueError('Unexpected, linked, duplicate or special archive member')
            if member.pax_headers or member.size > 1_000_000 or member.size < 0:
                raise ValueError('Unsupported snapshot metadata')
            stream = archive.extractfile(member)
            with stream: contents[member.name] = stream.read(1_000_001)
            if len(contents[member.name]) != member.size: raise ValueError('Truncated snapshot member')
    if set(contents) != {*FILES, 'manifest.json'}:
        raise ValueError('Incomplete ledger/key recovery set')
    manifest = json.loads(contents['manifest.json'])
    if manifest.get('schema') != 1 or manifest.get('kind') != 'guard-state' or set(manifest.get('files', {})) != set(FILES):
        raise ValueError('Invalid snapshot manifest')
    for name in FILES:
        if manifest['files'][name] != {'size': len(contents[name]), 'sha256': sha(contents[name])}:
            raise ValueError('Snapshot file differs from original manifest')
    ledger = json.loads(contents['ledger.json'])
    if (sha(contents['ledger.json']) != trusted_receipt['ledger_sha256']
            or sha(ledger['generation'].encode('ascii')) != trusted_receipt['generation_sha256']
            or manifest['generation_sha256'] != trusted_receipt['generation_sha256']
            or len(ledger['requests']) != trusted_receipt['request_count']
            or manifest['request_count'] != trusted_receipt['request_count']):
        raise ValueError('Ledger identity/count differs from trusted snapshot')
    directory = new_directory(destination)
    for name in FILES: new_private_file(directory / name, contents[name])
    for name in FILES:
        if private_read(directory / name, 1_000_000) != contents[name]:
            raise ValueError('Recovered disk bytes differ')
    restored = Guard(Path(ledger['root']), directory)
    with restored.locked(): restored.state()  # Validate actual recovered key/schema/requests, never start or rebind.
    Guard._sync(directory)
    Guard._sync(directory.parent)
    return {'passed': True, 'files_verified': 2, 'request_count': len(ledger['requests']),
            'archive_bytes': len(data), 'archive_sha256': sha(data), 'live_state_replaced': False,
            'production_restore_authorized': False, 'secret_values_printed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'verify'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archive', type=Path); parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0: raise ValueError('Privileged operator required')
    if args.action == 'snapshot':
        record = snapshot(Guard(), args.output)
        result = {'snapshot_created': True, 'archive_bytes': record['archive_bytes'],
                  'request_count': record['request_count'], 'uploaded': False, 'live_state_changed': False}
    else:
        if args.archive is None or args.receipt is None: parser.error('Original archive and independent receipt required')
        result = verify(args.archive, json.loads(private_read(args.receipt, 100_000)), args.output)
    print(json.dumps(result))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError, TypeError, tarfile.TarError):
        raise SystemExit('Private guard snapshot check failed; retained evidence needs operator review.')
