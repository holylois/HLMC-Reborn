"""Explicit source/inventory bindings and read-only maintenance lease. No account reads or service control.

Code pins identify reviewed bytes; they do not establish account absence or turn a retention hold into approval.
Native adapters and scope decisions must come from the separately reviewed private case workflow.
"""
import hashlib
import os
import stat
import subprocess
from pathlib import Path
from privacy_actions import canonical
from privacy_review import STORES, digest, sha

VERIFIERS = frozenset(('__init__', 'auth_sqlite', 'store_adapters', 'scoped_stores', 'identity_codec', 'regions',
                       'audio_scope', 'audit_store', 'snbt', 'discord_scope', 'public_http',
                       'runtime_guard', 'bindings', 'restore_ledger'))
SOURCES = frozenset(('auth', 'claims', 'economy', 'homes', 'holylois', 'extras', 'audio', 'audit', 'terrain-cache',
                     'stats-exporter', 'weekly-exporter', 'stats-http', 'guard', 'snapshot', 'checkpoint',
                     'review', 'exports', 'actions', 'bindings', 'discord-bot', 'support-registry', 'routine', 'enforcement',
                     'deployment', 'thread-guard', 'offsite-backup', 'startup', 'evidence',
                     'backup-reader', 'backup-capture', 'backup-receipts', 'prestart', 'restore')) | {
                         'verifier:' + name for name in VERIFIERS}
SERVICES = ('minecraft', 'holylois-stats', 'holylois-botwall', 'holylois-terrain-expansion',
            'holylois-discord-bot', 'holylois-weekly-recap', 'holylois-log-retention', 'holylois-guard-checkpoint',
            'holylois-thread-guard', 'holylois-offsite-backup')
TIMERS = ('holylois-stats', 'holylois-botwall', 'holylois-terrain-expansion', 'holylois-weekly-recap',
          'holylois-log-retention', 'holylois-guard-checkpoint', 'holylois-thread-guard', 'holylois-offsite-backup')


def unit_states(units, run=subprocess.run):
    """One systemctl request per complete observation, with exact unit membership."""
    result = run(['systemctl', 'show', *units, '-p', 'Id', '-p', 'LoadState', '-p', 'ActiveState',
        '-p', 'SubState', '-p', 'MainPID', '-p', 'ControlPID', '-p', 'InvocationID'],
        check=True, capture_output=True, text=True, timeout=15)
    rows = {}
    for block in result.stdout.strip().split('\n\n'):
        values = {}
        for line in block.splitlines():
            key, separator, value = line.partition('=')
            if not separator or key in values: raise ValueError('Ambiguous unit observation')
            values[key] = value
        name = values.get('Id')
        if name not in units or name in rows: raise ValueError('Unknown or duplicate unit observation')
        rows[name] = values
    if set(rows) != set(units): raise ValueError('Incomplete unit observation')
    return rows


def current_prestart(row, pid, invocation):
    if (type(pid) is not int or pid <= 0 or not isinstance(invocation, str) or len(invocation) != 32
            or any(c not in '0123456789abcdef' for c in invocation)):
        return False
    return (row.get('LoadState') == 'loaded' and row.get('ActiveState') == 'activating'
            and row.get('SubState') == 'start-pre' and row.get('MainPID') == '0'
            and row.get('ControlPID') == str(pid) and row.get('InvocationID') == invocation)


def own_prestart(unit, pid, invocation, run=subprocess.run):
    """Only this process in the current start-pre invocation may represent the activating game unit."""
    return current_prestart(unit_states((unit,), run)[unit], pid, invocation)


def service_lease(run=subprocess.run, *, prestart=None):
    """Loaded stopped writers AND inactive timers. No stop/start operations, no cached observation.

    prestart is a trusted (unit, current PID, invocation) tuple, not permission to skip that unit.
    The fixed production entrypoint supplies minecraft.service and its own process identity.
    """
    units = tuple(n + '.service' for n in SERVICES) + tuple(n + '.timer' for n in TIMERS)
    rows = unit_states(units, run)
    if prestart is not None:
        unit, pid, invocation = prestart
        if unit != 'minecraft.service' or not current_prestart(rows[unit], pid, invocation): return False
    for name, row in rows.items():
        if prestart is not None and name == prestart[0]:
            if (row.get('LoadState') != 'loaded' or row.get('ActiveState') != 'activating'
                    or row.get('SubState') != 'start-pre' or row.get('MainPID') != '0'
                    or row.get('ControlPID') != str(prestart[1]) or row.get('InvocationID') != prestart[2]): return False
        else:
            if row.get('LoadState') != 'loaded' or row.get('ActiveState') not in ('inactive', 'failed'): return False
            if name.endswith('.service') and (row.get('MainPID') != '0' or row.get('ControlPID') != '0'): return False
    return True


class Bindings:
    def __init__(self, root, mods, sources, adapters, scope_review_sha256):
        self.root = canonical(root); self.scope_review = sha(scope_review_sha256)
        if not self.root.is_dir() or not isinstance(mods, dict) or not mods or set(sources) != SOURCES:
            raise ValueError('Complete explicitly reviewed mod/source inventory required')
        if set(adapters) != STORES or any(not callable(getattr(a, 'verify', None)) for a in adapters.values()):
            raise ValueError('Every native store requires its real verifier')
        self.adapters = dict(adapters); self.mods = {}; self.sources = {}; self.cache = {}
        for name, value in mods.items():
            if Path(name).name != name or not name.endswith('.jar') or '\\' in name:
                raise ValueError('Exact active mod filenames required')
            self.mods[name] = sha(value)
        for label, entry in sources.items():
            if set(entry) != {'path', 'sha256'}: raise ValueError('Unknown source binding')
            self.sources[label] = (canonical(entry['path']), sha(entry['sha256']))

    def _code(self, path, expected):
        canonical(path)
        info = path.stat()
        def metadata(s):
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
                    s.st_uid, s.st_gid, s.st_mode, s.st_nlink)
        stamp = metadata(info)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 512 * 1024 * 1024:
            raise ValueError('Pinned code is missing, linked or oversized')
        if self.cache.get(path) == (stamp, expected): return
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK); h = hashlib.sha256()
        with os.fdopen(fd, 'rb') as stream:
            size = 0
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(block)
                if size > 512 * 1024 * 1024: raise ValueError('Native code grew beyond review budget')
                h.update(block)
        if h.hexdigest() != expected or metadata(path.stat()) != stamp:
            raise ValueError('Reviewed native code changed')
        self.cache[path] = (stamp, expected)

    def check(self):
        folder = canonical(self.root / 'mods')
        if {p.name for p in folder.glob('*.jar')} != set(self.mods):
            raise ValueError('Active mod inventory changed; storage review required')
        for name, expected in self.mods.items(): self._code(folder / name, expected)
        for path, expected in self.sources.values(): self._code(path, expected)
        return digest({'root': str(self.root), 'mods': self.mods,
                       'sources': {k: {'path': str(p), 'sha256': h} for k, (p, h) in self.sources.items()},
                       'scope_review_sha256': self.scope_review})
