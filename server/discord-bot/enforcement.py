"""Bounded, reviewed expiry operations. No network, scheduler or service startup on import."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def when(value):
    if not isinstance(value, str):
        raise ValueError('Timezone-aware timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return result.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def private_json(path, value):
    path = Path(path)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('Unexpected private storage')
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


class Journal:
    """Root-private durable intents/completions. Contains opaque operation IDs, never bodies."""
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError('Unexpected journal path')

    def rows(self):
        if not self.path.exists():
            return []
        if self.path.stat().st_size > 20_000_000:
            raise ValueError('Journal needs rotation/review')
        return [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines() if line]

    def append(self, plan_hash, operation, state):
        with os.fdopen(os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND |
                              getattr(os, 'O_NOFOLLOW', 0), 0o600), 'a', encoding='utf-8') as stream:
            stream.write(json.dumps({'plan': plan_hash, 'operation': operation, 'state': state}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


async def apply(plan, reviewed_hash, now, provider, journal):
    fingerprint = digest(plan)
    if reviewed_hash != fingerprint or plan.get('schema') != 1 or plan.get('ready') is not True:
        raise ValueError('Exact reviewed ready plan required')
    age = when(now) - when(plan['as_of'])
    if not timedelta(0) <= age <= timedelta(hours=6):
        raise ValueError('Plan is stale or from the future')
    entries = plan['entries']
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError('Unexpected plan size')
    ids = [digest(entry) for entry in entries]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate operation')
    completed, intended = set(), set()
    for row in journal.rows():
        if row.get('plan') == fingerprint:
            if row.get('operation') not in ids or row.get('state') not in ('intent', 'complete'):
                raise ValueError('Unexpected audit entry')
            (completed if row['state'] == 'complete' else intended).add(row['operation'])
    # Verify all targets before the first mutation, including already-completed absence on retry.
    for entry, key in zip(entries, ids):
        present = await provider.validate(entry, now)
        if key in completed and present:
            raise ValueError('An expired object reappeared; review restore handling')
    removed, absent = 0, 0
    for entry, key in zip(entries, ids):
        if key in completed:
            continue
        if await provider.validate(entry, now):
            journal.append(fingerprint, key, 'intent')
            await provider.remove(entry, now)
            if await provider.validate(entry, now):
                raise ValueError('Provider still reports object present')
            removed += 1
        else:
            absent += 1
        journal.append(fingerprint, key, 'complete')
    return {'complete': True, 'operations': len(entries), 'removed_this_run': removed,
            'already_absent': absent, 'plan_sha256': fingerprint}


LOG_NAME = re.compile(r'(\d{4}-\d{2}-\d{2})-\d+\.log\.gz')


class ClosedLogs:
    def __init__(self, root, held_names, holds_reviewed=False):
        self.root = Path(root)
        if self.root.is_symlink() or self.root.resolve() != self.root.absolute() or not holds_reviewed:
            raise ValueError('Reviewed real log directory and holds required')
        self.held = set(held_names)
        self.root_identity = (self.root.stat().st_dev, self.root.stat().st_ino)
        if any(not LOG_NAME.fullmatch(name) for name in self.held):
            raise ValueError('Unknown held log name')

    def inspect(self, name, now):
        root = self.root.lstat()
        if not stat.S_ISDIR(root.st_mode) or (root.st_dev, root.st_ino) != self.root_identity:
            raise ValueError('Log directory changed')
        match = LOG_NAME.fullmatch(name)
        if not match or name in self.held:
            raise ValueError('Log is outside reviewed scope or held')
        path = self.root / name
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ValueError('Only single-link regular closed log files are eligible')
            end = when(match[1] + 'T00:00:00Z') + timedelta(days=1, hours=14)
            modified = datetime.fromtimestamp(before.st_mtime, timezone.utc)
            if max(end, modified) >= when(now) - timedelta(days=90):
                raise ValueError('Log is not older than the approved boundary')
            data = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                data.update(block)
            after = os.fstat(stream.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('Log changed during review')
        return {'kind': 'closed-log', 'name': name, 'inode': before.st_ino, 'device': before.st_dev,
                'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns, 'sha256': data.hexdigest()}

    def plan(self, now):
        entries, protected = [], 0
        for path in sorted(self.root.iterdir()):
            if not LOG_NAME.fullmatch(path.name) or path.name in self.held or path.is_symlink():
                protected += 1
                continue
            # An ineligible age is expected; structural errors still stop review.
            try:
                entries.append(self.inspect(path.name, now))
            except ValueError as error:
                if str(error) != 'Log is not older than the approved boundary':
                    raise
                protected += 1
        return {'schema': 1, 'kind': 'closed-logs', 'ready': True, 'as_of': now, 'entries': entries,
                'protected_count': protected, 'held_names': sorted(self.held)}

    async def validate(self, entry, now):
        if entry.get('kind') != 'closed-log' or not LOG_NAME.fullmatch(entry.get('name', '')):
            raise ValueError('Unexpected log entry')
        if entry['name'] in self.held:
            raise ValueError('New hold blocks expiry')
        path = self.root / entry['name']
        if not path.exists() and not path.is_symlink():
            return False
        if self.inspect(entry['name'], now) != entry:
            raise ValueError('Log changed since review')
        return True

    async def remove(self, entry, now):
        await self.validate(entry, now)
        fd = os.open(self.root, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        try:
            current = os.stat(entry['name'], dir_fd=fd, follow_symlinks=False)
            if (current.st_ino, current.st_dev, current.st_mtime_ns, current.st_size) != (
                    entry['inode'], entry['device'], entry['mtime_ns'], entry['bytes']):
                raise ValueError('Log replaced just before expiry')
            os.unlink(entry['name'], dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)
