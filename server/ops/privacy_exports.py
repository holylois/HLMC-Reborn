"""Private suppression policy for root exporters and an identity-free public serving gate.

Prepared only. No default invocation, real identity discovery, erasure or startup override.
A new request/restore blocks the gate before the guard changes. Missing policy never means empty.
"""
import hashlib
import json
import os
import stat
import uuid
from pathlib import Path
from recovery_guard import identity
from privacy_review import cases_for, digest
from guard_checkpoint import pair, verify_current
from guard_snapshot import private_read

POLICY = Path('/var/lib/holylois/privacy-exports/policy.json')
GATE = Path('/var/lib/holylois-stats/privacy-gate.json')


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate privacy field')
        result[key] = value
    return result


def encoded(value): return (json.dumps(value, sort_keys=True) + '\n').encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()
def requests_digest(state): return digest(state['requests'])


def gate_bytes(path=GATE, owner=0):
    path = Path(path).absolute()
    if path.resolve() != path or path.parent.resolve() != path.parent:
        raise ValueError('Unlinked serving gate required')
    parent = path.parent.stat()
    if parent.st_uid != owner or parent.st_mode & 0o022:
        raise ValueError('Serving gate parent must be operator-owned and not publicly writable')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno()); raw = stream.read(4097)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_nlink != 1
            or info.st_mode & 0o022 or len(raw) > 4096):
        raise ValueError('Bounded operator-owned serving gate required')
    value = json.loads(raw, object_pairs_hook=unique)
    if (set(value) != {'schema', 'epoch', 'ready', 'policy_sha256'} or value['schema'] != 1
            or type(value['ready']) is not bool):
        raise ValueError('Unknown serving gate schema')
    identity(value['epoch'])
    if value['policy_sha256'] is not None:
        from privacy_review import sha as evidence_sha
        evidence_sha(value['policy_sha256'])
    if value['ready'] and value['policy_sha256'] is None:
        raise ValueError('Serving gate has no reviewed policy')
    return raw, value


def invalidate(guard):
    if guard.export_gate is None: return
    gate_bytes(guard.export_gate, os.geteuid())  # Do not silently create a missing protection file.
    guard._atomic(guard.export_gate, {'schema': 1, 'epoch': str(uuid.uuid4()), 'ready': False,
                                    'policy_sha256': None}, 0o644)


def plan(guard, cases):
    if guard.export_gate is None: raise ValueError('Guard export invalidation must be bound')
    before = pair(guard)
    bound = cases_for(guard, json.loads(json.dumps(cases)))
    _, gate = gate_bytes(guard.export_gate, os.geteuid())
    if gate['ready']: raise ValueError('Block serving before planning a new policy')
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        request_revision = requests_digest(state)
    if pair(guard) != before: raise ValueError('Guard changed during suppression planning')
    return {'schema': 1, 'epoch': gate['epoch'], 'requests_digest': request_revision,
            'ids': sorted({s for c in bound for s in c['related_subjects']}),
            'names': sorted({n for c in bound for n in c['aliases']})}


def publish(guard, cases, destination, base, provider, approved_sha256, lease):
    """Trusted offline workflow only. No provider upload or permission to erase accounts."""
    if lease() is not True: raise ValueError('Stopped writers required before policy activation')
    before = pair(guard); policy = plan(guard, cases)
    if digest(policy) != approved_sha256: raise ValueError('Exact suppression policy review required')
    proof = verify_current(guard, base, provider)
    if proof['fingerprint'] != before: raise ValueError('Guard changed before policy protection')
    destination = Path(destination).absolute()
    if (destination.resolve() != destination or destination.is_relative_to(guard.root)
            or destination.is_relative_to(guard.directory)):
        raise ValueError('Suppression policy must remain outside restored server and guard state')
    parent = destination.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
        raise ValueError('Private operator-owned policy directory required')
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        _, gate = gate_bytes(guard.export_gate, os.geteuid())
        current_pair = sha(private_read(guard.directory / 'ledger.json', 1_000_000) + b'\0'
                           + private_read(guard.directory / 'subject-key.json', 1_000_000))
        if (requests_digest(state) != policy['requests_digest'] or state['pending_restore'] is not None
                or current_pair != proof['fingerprint'] or gate['epoch'] != policy['epoch']
                or gate['ready'] or lease() is not True):
            raise ValueError('Guard, serving epoch or stopped lease changed before activation')
        raw = encoded(policy)
        guard._atomic(destination, policy)
        if private_read(destination, 4_000_000) != raw: raise ValueError('Policy disk readback differs')
        guard._atomic(guard.export_gate, {'schema': 1, 'epoch': policy['epoch'], 'ready': True,
                                        'policy_sha256': sha(raw)}, 0o644)
    return {'policy_published': True, 'identities_suppressed': len(policy['ids']),
            'erasure_authorized': False, 'allow_start': False, 'uploaded': False}


def load(guard, path=POLICY):
    raw = private_read(path, 4_000_000)
    value = json.loads(raw, object_pairs_hook=unique)
    if set(value) != {'schema', 'epoch', 'requests_digest', 'ids', 'names'} or value['schema'] != 1:
        raise ValueError('Unknown suppression policy schema')
    identity(value['epoch'])
    from privacy_review import sha as evidence_sha
    evidence_sha(value['requests_digest'])
    if not isinstance(value['ids'], list) or not isinstance(value['names'], list):
        raise ValueError('Explicit identity suppression required')
    for subject in value['ids']: identity(subject)
    import re
    if (len(set(value['ids'])) != len(value['ids']) or len(set(value['names'])) != len(value['names'])
            or any(not isinstance(n, str) or not re.fullmatch('[a-z0-9_]{3,16}', n) for n in value['names'])):
        raise ValueError('Invalid suppression identity inventory')
    gate_raw, gate = gate_bytes(guard.export_gate, os.geteuid())
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        if state['pending_restore'] is not None or requests_digest(state) != value['requests_digest']:
            raise ValueError('Policy does not cover current request state')
    if not gate['ready'] or gate['epoch'] != value['epoch'] or gate['policy_sha256'] != sha(raw):
        raise ValueError('Serving is blocked or suppression policy changed')
    return value, gate_raw


def excluded(policy, subject='', name=''):
    return subject in policy['ids'] or str(name).lower() in policy['names']


def require_same(guard, path, policy, gate_raw):
    current, current_gate = load(guard, path)
    if current != policy or current_gate != gate_raw: raise ValueError('Policy changed while producing output')


def envelope(policy, stats, taken):
    return {'schema': 1, 'epoch': policy['epoch'], 'stats_sha256': sha(stats), 'taken_sha256': sha(taken)}
