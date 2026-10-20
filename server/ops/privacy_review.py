"""Offline per-store review bound to guard224 and exact-current off-site protection.

Library only: no live paths, account discovery, executor, service control or startup override.
Private cases and reviewed native adapters must be supplied by an operator workflow.
The historical SQLite pilot ledger must never replace the deployed HMAC guard.
"""
import hashlib
import hmac
import json
import re
from guard_checkpoint import verify_current, pair
from recovery_guard import identity

STORES = frozenset(('profiles', 'holylois', 'authentication', 'claims', 'homes', 'economy',
                    'public-exports', 'discord', 'private-recovery', 'world-ownership'))
CASE_KEYS = {'id', 'subject', 'related_subjects', 'aliases', 'discord_ids', 'identity_proof_sha256'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def sha(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Reviewed evidence fingerprint required')
    return value


def cases_for(guard, cases):
    """Bind every private case to an existing pseudonymous request, with no omissions or extras."""
    if not isinstance(cases, list) or len(cases) > 10000:
        raise ValueError('Bounded private case inventory required')
    with guard.locked():
        state = guard.state(); guard._anchor(state)
        if state['pending_restore'] is not None:
            raise ValueError('Pending restoration needs its own trusted workflow')
        key = bytes.fromhex(guard._read('subject-key.json')['key'])
        requests = {row['id']: row for row in state['requests']}
        seen = set()
        for case in cases:
            if not isinstance(case, dict) or set(case) != CASE_KEYS:
                raise ValueError('Unknown private case schema')
            request_id, subject = identity(case['id']), identity(case['subject'])
            subjects = case['related_subjects']
            if (not isinstance(subjects, list) or not subjects or len(subjects) > 100
                    or any(identity(s) != s for s in subjects) or len(set(subjects)) != len(subjects)
                    or subject not in subjects):
                raise ValueError('Explicit verified online/offline/forced UUID inventory required')
            aliases, discord = case['aliases'], case['discord_ids']
            if (not isinstance(aliases, list) or not aliases or len(aliases) > 100
                    or any(not isinstance(a, str) or not re.fullmatch('[a-z0-9_]{3,16}', a) for a in aliases)
                    or len(set(aliases)) != len(aliases)):
                raise ValueError('Explicit verified lowercase aliases required')
            if (not isinstance(discord, list) or len(discord) > 100
                    or any(not isinstance(d, str) or not re.fullmatch('[0-9]{17,20}', d) for d in discord)
                    or len(set(discord)) != len(discord)):
                raise ValueError('Explicit reviewed Discord identifiers required')
            sha(case['identity_proof_sha256'])
            subject_hmac = hmac.new(key, subject.encode('ascii'), hashlib.sha256).hexdigest()
            if (request_id in seen or request_id not in requests
                    or not hmac.compare_digest(subject_hmac, requests[request_id]['subject_hmac'])):
                raise ValueError('Private case does not match the external request ledger')
            seen.add(request_id)
        if seen != set(requests):
            raise ValueError('Every external request requires its own reviewed private case')
    return cases


def review(guard, base, provider, cases, adapters, lease, runtime_review):
    """Read twice, refuse drift, return aggregate review only. Never release the live barrier.

    runtime_review is the trusted code/inventory verifier, not a supplied success receipt.
    Its digest must cover reviewed source, mod inventory, scope and backend bindings.
    Adapters need stopped writers and strict schema/path/identity verifiers.
    """
    if lease() is not True:
        raise ValueError('Stopped game and data-writer lease required')
    if not isinstance(adapters, dict) or set(adapters) != STORES or any(
            not callable(getattr(a, 'verify', None)) for a in adapters.values()):
        raise ValueError('Complete reviewed per-store verifier registry required')
    original_cases = digest(cases)
    bound_pair = pair(guard)
    bound = cases_for(guard, json.loads(json.dumps(cases)))
    code_review = sha(runtime_review())
    protection = verify_current(guard, base, provider)
    if protection['fingerprint'] != bound_pair:
        raise ValueError('Request inventory changed after private case binding')

    def inspect():
        evidence = []
        for case in bound:
            for subject in case['related_subjects']:
                for store in sorted(STORES):
                    if lease() is not True:
                        raise ValueError('Writer resumed during private review')
                    # A verifier cannot alter the reviewed identity given to subsequent stores.
                    request = json.loads(json.dumps(case)); request['subject'] = subject
                    result = adapters[store].verify(request)
                    if not isinstance(result, dict) or result.get('absent') is not True:
                        raise ValueError('Unresolved store data; review remains incomplete')
                    evidence.append((case['id'], subject, store, sha(result.get('fingerprint'))))
        return evidence

    first = inspect()
    if first != inspect():
        raise ValueError('Store evidence changed between complete passes')
    if (sha(runtime_review()) != code_review or digest(cases) != original_cases
            or pair(guard) != protection['fingerprint'] or lease() is not True):
        raise ValueError('Case, source, writer or guard changed during private review')
    return {'review_passed': True, 'requests_checked': len(bound), 'stores_per_request': len(STORES),
            'identities_checked': sum(len(case['related_subjects']) for case in bound),
            'store_checks': len(first), 'store_evidence_sha256': digest(first), 'synchronous_offsite_readback': True,
            'allow_start': False, 'erasure_authorized': False, 'live_state_changed': False, 'deleted': 0}
