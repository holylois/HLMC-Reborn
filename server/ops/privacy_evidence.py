"""Read-only private case/recovery evidence. No CLI, upload, service control or erasure permission."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from guard_snapshot import private_read
from privacy_actions import Plan, private_directory, LIMIT, OBLIGATIONS
from privacy_exports import encoded, unique
from privacy_review import STORES, digest, sha

REMOTE = 'gdrive:Holy Lois Backups/privacy-cases'
TOTAL = 256 * 1024 * 1024


def hash_bytes(raw): return hashlib.sha256(raw).hexdigest()
def document(raw): return json.loads(raw, object_pairs_hook=unique)


class ReadOnlyDrive:
    """Immutable original comparison: provider metadata plus bounded actual readback. Never uploads."""
    def command(self, *args):
        if not args or args[0] not in ('lsjson', 'cat'): raise ValueError('Read-only evidence command required')
        return subprocess.run(['rclone', *args, '--tpslimit', '2', '--retries', '2', '--low-level-retries', '2',
            '--timeout', '30s', '--contimeout', '15s', '--buffer-size', '1M', '--multi-thread-streams', '0'],
            check=True, capture_output=True, timeout=120).stdout

    def verify(self, bundle, name, raw):
        sha(bundle)
        if name != 'index.json':
            if not name.startswith('objects/') or len(name.split('/')) != 2: raise ValueError('Exact private object required')
            if sha(name.split('/')[1]) != hash_bytes(raw): raise ValueError('Original object differs from its identity')
        elif hash_bytes(raw) != bundle: raise ValueError('Original index differs from reviewed pin')
        if len(raw) > LIMIT: raise ValueError('Bounded evidence object required')
        remote = REMOTE + '/bundle-' + bundle + '/' + name
        row = document(self.command('lsjson', remote, '--stat', '--hash'))
        hashes = {str(k).lower(): str(v).lower() for k, v in row.get('Hashes', {}).items()}
        if (row.get('IsDir') is not False or row.get('Name') != name.split('/')[-1]
                or row.get('Size') != len(raw)
                or hashes.get('md5') != hashlib.md5(raw, usedforsecurity=False).hexdigest()):
            raise ValueError('Provider metadata differs from independent original')
        if self.command('cat', remote, '--count', str(len(raw) + 1)) != raw:
            raise ValueError('Provider readback differs from independent original')


class Evidence:
    def __init__(self, directory, index, index_sha256, decisions, transactions, provider):
        self.directory = private_directory(directory)
        self.index, self.decisions = Path(index).absolute(), Path(decisions).absolute()
        self.pin = sha(index_sha256); self.provider = provider
        for path in (self.index, self.decisions):
            private_directory(path.parent)
            if path.is_relative_to(self.directory) or path == self.directory:
                raise ValueError('Independent reviewed index and current decisions must be outside bundle')
        if self.index == self.decisions: raise ValueError('Separate original index and current decisions required')
        if not isinstance(transactions, dict): raise ValueError('Explicit active transaction bindings required')
        self.transactions = {sha(k): private_directory(v) for k, v in transactions.items()}
        for directory in self.transactions.values():
            if directory.is_relative_to(self.directory) or self.directory.is_relative_to(directory):
                raise ValueError('Active transactions must be separate from independent recovery objects')

    def _load(self, manifest):
        private_directory(self.directory); private_directory(self.index.parent)
        if (set(manifest) != {'schema', 'kind', 'root', 'guard_pair_sha256', 'cases', 'scopes', 'runtime_sha256',
                             'backup_sha256', 'policy_sha256'}
                or manifest['schema'] != 1 or manifest['kind'] != 'private-startup-review'):
            raise ValueError('Exact private startup review binding required')
        sha(manifest['guard_pair_sha256'])
        raw = private_read(self.index, 1_000_000)
        if hash_bytes(raw) != self.pin: raise ValueError('Independent reviewed evidence index changed')
        value = document(raw)
        if (set(value) != {'schema', 'kind', 'binding', 'cases', 'scopes', 'transactions', 'objects'}
                or value['schema'] != 1 or value['kind'] != 'private-case-recovery'):
            raise ValueError('Unknown private recovery index')
        expected = {'root': manifest['root'], 'cases_sha256': digest(manifest['cases']),
            'scopes_sha256': digest(manifest['scopes']), 'runtime_sha256': sha(manifest['runtime_sha256']),
            'backup_sha256': sha(manifest['backup_sha256']), 'policy_sha256': sha(manifest['policy_sha256'])}
        if value['binding'] != expected: raise ValueError('Evidence belongs to a different private review')
        root = Path(manifest['root']).absolute()
        if root.resolve() != root or not root.is_dir(): raise ValueError('Current unlinked server root required')
        for path in (self.directory, self.index, self.decisions, *self.transactions.values()):
            if path.is_relative_to(root) or root.is_relative_to(path):
                raise ValueError('Private recovery evidence must survive server restoration')
        objects = value['objects']
        if not isinstance(objects, dict) or not 1 <= len(objects) <= 1000: raise ValueError('Bounded explicit object inventory required')
        folder = private_directory(self.directory / 'objects')
        if {p.name for p in folder.iterdir()} != set(objects): raise ValueError('Recovery object inventory differs')
        payload = {}; total = 0
        for name, metadata in objects.items():
            sha(name)
            if (not isinstance(metadata, dict) or set(metadata) != {'bytes'} or type(metadata['bytes']) is not int
                    or not 0 <= metadata['bytes'] <= LIMIT): raise ValueError('Unknown recovery object metadata')
            total += metadata['bytes']
            if total > TOTAL: raise ValueError('Private recovery evidence exceeds review budget')
            data = private_read(folder / name, LIMIT)
            if len(data) != metadata['bytes'] or hash_bytes(data) != name: raise ValueError('Original recovery object changed')
            payload[name] = data
        cases, scopes = sha(value['cases']), sha(value['scopes'])
        if document(payload[cases]) != manifest['cases'] or document(payload[scopes]) != manifest['scopes']:
            raise ValueError('Recovered cases/scopes differ from current review')
        if set(manifest['scopes']) != STORES | OBLIGATIONS: raise ValueError('Complete current scope review required')
        needed = {sha(c['identity_proof_sha256']) for c in manifest['cases']}
        for review in manifest['scopes'].values():
            if (set(review) != {'decision', 'evidence_sha256'} or review['decision'] not in ('change', 'verify-only')):
                raise ValueError('Held or unresolved scope blocks evidence verification')
            needed.add(sha(review['evidence_sha256']))
        if not needed <= set(payload): raise ValueError('Missing original identity or scope evidence')
        if not isinstance(value['transactions'], list) or len(value['transactions']) > 100:
            raise ValueError('Bounded explicit transaction recovery inventory required')
        plans = set(); required = needed | {cases, scopes}
        for item in value['transactions']:
            if set(item) != {'plan', 'journal'}: raise ValueError('Unknown transaction recovery reference')
            plan_hash, journal_hash = sha(item['plan']), sha(item['journal'])
            if plan_hash in plans: raise ValueError('Duplicate active transaction')
            plans.add(plan_hash); required.update((plan_hash, journal_hash))
            description = document(payload[plan_hash]); record = document(payload[journal_hash])
            if (set(record) != {'schema', 'plan', 'status'} or record['schema'] != 1
                    or record['status'] != 'actions-complete' or record['plan'] != description
                    or description['root'] != manifest['root'] or description['cases_sha256'] != digest(manifest['cases'])
                    or description['runtime_sha256'] != expected['runtime_sha256']
                    or description['backup_sha256'] != expected['backup_sha256']
                    or description['reviews'] != manifest['scopes']):
                raise ValueError('Incomplete or unrelated transaction recovery evidence')
            active = self.transactions[plan_hash]
            if private_read(active / 'journal.json', 4_000_000) != payload[journal_hash]:
                raise ValueError('Active journal changed after protected recovery copy')
            plan = Plan.from_journal(active)
            plan._sidecars()
            if encoded(plan.description()) != payload[plan_hash]: raise ValueError('Protected action plan differs from actual transaction')
            for action in plan.actions:
                # A metadata-only journal is insufficient to recover the move-only originals after host loss.
                # Protect the original bytes as well as replacements; do not infer coverage from an older tar.
                required.add(action['before']['sha256'])
                if len(payload[action['before']['sha256']]) != action['before']['bytes']:
                    raise ValueError('Protected original size differs from actual transaction')
                if action['after'] is not None:
                    required.add(action['after'])
                    if payload[action['after']] != action['replacement']: raise ValueError('Protected replacement object differs')
                if plan._kind(action, active) != ('applied' if action['after'] is not None else 'moved'):
                    raise ValueError('Actual action/original evidence is incomplete')
        if plans != set(self.transactions): raise ValueError('Unreviewed or missing active transaction binding')
        if any(r['decision'] == 'change' for r in manifest['scopes'].values()) and not plans:
            raise ValueError('Changed scope requires its completed protected action journal')
        if required != set(payload): raise ValueError('Unreferenced or missing recovery objects require review')
        return raw, value, payload

    def _decisions(self, manifest):
        private_directory(self.decisions.parent)
        raw = private_read(self.decisions, 1_000_000); value = document(raw)
        if (set(value) != {'schema', 'kind', 'root', 'cases_sha256', 'scopes'} or value['schema'] != 1
                or value['kind'] != 'current-private-scope-review' or value['root'] != manifest['root']
                or value['cases_sha256'] != digest(manifest['cases']) or value['scopes'] != manifest['scopes']):
            raise ValueError('Current private decisions/holds differ from protected review')
        return raw

    def verify_scope(self, manifest):
        original, _, payload = self._load(manifest); decisions = self._decisions(manifest)
        if self._load(manifest)[0] != original or self._decisions(manifest) != decisions:
            raise ValueError('Private evidence changed during scope verification')
        return bool(payload)

    def verify_recovery(self, manifest):
        original, _, payload = self._load(manifest); decisions = self._decisions(manifest)
        self.provider.verify(self.pin, 'index.json', original)
        for name, raw in payload.items(): self.provider.verify(self.pin, 'objects/' + name, raw)
        final, _, current = self._load(manifest)
        if final != original or current != payload or self._decisions(manifest) != decisions:
            raise ValueError('Private evidence changed during independent readback')
        return True


def materialize(guard, manifest, artifacts, transactions, destination, independent_index, decisions, lease, runtime_review):
    """Create a new local private recovery bundle from actual reviewed evidence and completed journals.

    No provider write. The owner must approve the concrete new sensitive upload scope separately. Current
    decisions must already exist independently; this helper cannot discover identity/support associations.
    """
    from guard_checkpoint import pair
    from privacy_actions import canonical, file as file_metadata
    from privacy_review import cases_for
    from guard_snapshot import new_private_file
    destination, independent_index = canonical(destination), canonical(independent_index)
    private_directory(destination.parent); private_directory(independent_index.parent)
    if (destination.is_relative_to(guard.root) or independent_index.is_relative_to(guard.root)
            or independent_index.is_relative_to(destination) or destination.is_relative_to(independent_index)):
        raise ValueError('Independent private artifact locations required')
    fingerprint = pair(guard); runtime = sha(runtime_review()); frozen = digest(manifest)
    cases_for(guard, manifest['cases'])
    def current():
        if (lease() is not True or pair(guard) != fingerprint or sha(runtime_review()) != runtime
                or manifest['root'] != str(guard.root) or manifest['guard_pair_sha256'] != fingerprint
                or manifest['runtime_sha256'] != runtime or digest(manifest) != frozen):
            raise ValueError('Private bundle binding changed')
    current(); destination.mkdir(mode=0o700, exist_ok=False)
    objects = destination / 'objects'; objects.mkdir(mode=0o700); inventory = {}; records = []; total = 0
    def add(raw):
        nonlocal total
        current(); name = hash_bytes(raw)
        if name in inventory: return name
        total += len(raw)
        if len(raw) > LIMIT or total > TOTAL or len(inventory) >= 1000: raise ValueError('Private bundle exceeds review budget')
        new_private_file(objects / name, raw); inventory[name] = {'bytes': len(raw)}
        return name
    cases, scopes = add(encoded(manifest['cases'])), add(encoded(manifest['scopes']))
    for expected, path in artifacts.items():
        sha(expected); raw = private_read(path, LIMIT)
        if add(raw) != expected: raise ValueError('Reviewed identity/scope artifact differs from its original')
    for expected, directory in transactions.items():
        plan = Plan.from_journal(directory); plan._sidecars()
        if add(encoded(plan.description())) != sha(expected): raise ValueError('Protected plan identity changed')
        journal = add(private_read(Path(directory) / 'journal.json', 4_000_000))
        records.append({'plan': expected, 'journal': journal})
        for action in plan.actions:
            if plan._kind(action, Path(directory)) != ('applied' if action['after'] is not None else 'moved'):
                raise ValueError('Actual completed original/replacement required')
            original = Path(directory) / 'originals' / action['relative']
            before = file_metadata(original)
            fd = os.open(original, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream: raw = stream.read(LIMIT + 1)
            if before != file_metadata(original) or add(raw) != action['before']['sha256']:
                raise ValueError('Original transaction bytes changed while protecting')
            if action['replacement'] is not None: add(action['replacement'])
    index = {'schema': 1, 'kind': 'private-case-recovery',
        'binding': {'root': manifest['root'], 'cases_sha256': digest(manifest['cases']),
                    'scopes_sha256': digest(manifest['scopes']), 'runtime_sha256': runtime,
                    'backup_sha256': manifest['backup_sha256'], 'policy_sha256': manifest['policy_sha256']},
        'cases': cases, 'scopes': scopes, 'transactions': records, 'objects': inventory}
    current(); raw = encoded(index); new_private_file(independent_index, raw)
    reader = Evidence(destination, independent_index, hash_bytes(raw), decisions, transactions, None)
    reader.verify_scope(manifest); current()
    return {'index_sha256': hash_bytes(raw), 'objects': len(inventory), 'bytes': total,
            'uploaded': False, 'allow_start': False, 'deleted': 0}
