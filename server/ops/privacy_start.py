"""Verified nonempty-request startup library. No CLI, default activation or ledger clearing.

The trusted operator/pre-start integration supplies actual native verifiers and private evidence readers.
Callbacks are pinned read-only code, not a caller-provided success receipt. Default Guard.start stays blocked.
"""
import hashlib
import json
import os
from guard_checkpoint import pair
from guard_snapshot import private_read
from privacy_actions import OBLIGATIONS
from privacy_exports import load, gate_bytes, requests_digest, unique
from privacy_review import STORES, digest, sha, review


def checked_start(guard, base, provider, cases, adapters, lease, runtime_review, *, policy_path,
                  scopes, backup_sha256, verified_stopped_backup, verified_scope, verified_private_recovery):
    """Recheck current stores before one start, preserving all requests for every future restore/start.

    Evidence readers must revalidate actual private objects/holds. They run again under the guard lock and
    must not reacquire that lock. This library never starts Java, accepts a persisted permit or uploads data.
    Historical-anchor repair and extraction are deliberately outside this startup operation.
    """
    if lease() is not True or not cases:
        raise ValueError('Stopped writers and nonempty reviewed requests required')
    if not isinstance(scopes, dict) or set(scopes) != STORES | OBLIGATIONS:
        raise ValueError('Every store, permission, support, ownership and external copy needs review')
    for value in scopes.values():
        if (not isinstance(value, dict) or set(value) != {'decision', 'evidence_sha256'}
                or value['decision'] not in ('change', 'verify-only')):
            raise ValueError('Unresolved hold or unknown startup scope decision')
        sha(value['evidence_sha256'])
    original_cases, original_scopes = digest(cases), digest(scopes)
    frozen_cases = json.loads(json.dumps(cases)); frozen_scopes = json.loads(json.dumps(scopes))
    before = pair(guard); runtime = sha(runtime_review()); backup = sha(backup_sha256)
    policy, gate_raw = load(guard, policy_path)
    policy_raw = private_read(policy_path, 4_000_000)
    if (hashlib.sha256(policy_raw).hexdigest() != json.loads(gate_raw)['policy_sha256']
            or json.loads(policy_raw, object_pairs_hook=unique) != policy):
        raise ValueError('Suppression policy changed after loading')
    if (set(policy['ids']) != {s for c in frozen_cases for s in c['related_subjects']}
            or set(policy['names']) != {n for c in frozen_cases for n in c['aliases']}):
        raise ValueError('Suppression policy does not cover exact reviewed identities')
    manifest = {'schema': 1, 'kind': 'private-startup-review', 'root': str(guard.root),
                'guard_pair_sha256': before, 'cases': frozen_cases, 'scopes': frozen_scopes,
                'runtime_sha256': runtime, 'backup_sha256': backup, 'policy_sha256': digest(policy)}
    expected = digest(manifest)

    def evidence():
        # Each callback gets its own copy; none may alter later readers' reviewed identities.
        if (verified_stopped_backup(backup) is not True
                or verified_scope(json.loads(json.dumps(manifest))) is not True
                or verified_private_recovery(json.loads(json.dumps(manifest))) is not True):
            raise ValueError('Current stopped backup, scope evidence and private recovery proof required')
        if digest(manifest) != expected:
            raise ValueError('Private startup evidence changed')

    frozen_adapters = dict(adapters)
    evidence()
    checked = review(guard, base, provider, frozen_cases, adapters, lease, runtime_review)
    if (digest(cases) != original_cases or digest(scopes) != original_scopes
            or pair(guard) != before or sha(runtime_review()) != runtime or lease() is not True):
        raise ValueError('Cases, scope, guard, code or writer changed before startup')
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        current = hashlib.sha256(private_read(guard.directory / 'ledger.json', 1_000_000) + b'\0'
                  + private_read(guard.directory / 'subject-key.json', 1_000_000)).hexdigest()
        if current != before or state['pending_restore'] is not None or not state['requests']:
            raise ValueError('Current retained request inventory required')

        def stable():
            if (lease() is not True or sha(runtime_review()) != runtime
                    or digest(cases) != original_cases or digest(scopes) != original_scopes
                    or adapters != frozen_adapters):
                raise ValueError('Startup source, scope, registry or writer changed')
            if (private_read(policy_path, 4_000_000) != policy_raw
                    or gate_bytes(guard.export_gate, os.geteuid())[0] != gate_raw
                    or requests_digest(state) != policy['requests_digest']):
                raise ValueError('Suppression policy or public serving gate changed')

        stable(); evidence()
        # One final full pass under the actual guard lock closes the gap after the double review.
        evidence_rows = []
        for case in frozen_cases:
            for subject in case['related_subjects']:
                for store in sorted(STORES):
                    stable()
                    request = json.loads(json.dumps(case)); request['subject'] = subject
                    result = frozen_adapters[store].verify(request)
                    if not isinstance(result, dict) or result.get('absent') is not True:
                        raise ValueError('Restored or unresolved account data blocks startup')
                    evidence_rows.append((case['id'], subject, store, sha(result.get('fingerprint'))))
        if digest(evidence_rows) != checked['store_evidence_sha256']:
            raise ValueError('Store evidence changed after complete review')
        stable(); evidence(); stable()
        final_pair = hashlib.sha256(private_read(guard.directory / 'ledger.json', 1_000_000) + b'\0'
                     + private_read(guard.directory / 'subject-key.json', 1_000_000)).hexdigest()
        if final_pair != before or guard.state() != state:
            raise ValueError('Guard bytes changed before generation rotation')
        guard._anchor(state)
        requests = json.loads(json.dumps(state['requests']))
        guard._rotate(state)
        if guard.state()['requests'] != requests:
            raise ValueError('Request retention changed during startup rotation')
    return {'allow_start': True, 'requests_retained': len(requests), 'stores_per_identity': len(STORES),
            'identities_checked': checked['identities_checked'], 'erasure_authorized': False,
            'native_process_started': False, 'uploaded': False, 'deleted': 0}
