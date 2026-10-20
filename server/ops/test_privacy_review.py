"""Generated identities and stores only. No account files, provider or service access."""
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock
from guard_checkpoint import checkpoint
from recovery_guard import Guard
from privacy_review import review, STORES
from test_guard_checkpoint import Provider


class Store:
    def __init__(self): self.present = False; self.change = None; self.calls = 0
    def verify(self, case):
        self.calls += 1
        if self.change: return self.change(case)
        return {'absent': not self.present, 'fingerprint': 'a' * 64}


class Review(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); game = self.root / 'game'
        (game / 'config').mkdir(parents=True)
        self.guard = Guard(game, self.root / 'guard'); self.guard.initialize()
        self.base = self.root / 'checkpoints'; self.base.mkdir(mode=0o700)
        self.provider = Provider(); self.adapters = {name: Store() for name in STORES}
        self.subject = str(uuid.uuid4()); self.request = str(uuid.uuid4())
        self.guard.record_request(self.request, self.subject)
        self.cases = [{'id': self.request, 'subject': self.subject, 'aliases': ['fixtureuser'],
                       'related_subjects': [self.subject],
                       'discord_ids': ['11111111111111111'], 'identity_proof_sha256': 'b' * 64}]
        checkpoint(self.guard, self.base, self.provider)
        self.lease = lambda: True; self.runtime = lambda: 'c' * 64

    def execute(self):
        return review(self.guard, self.base, self.provider, self.cases, self.adapters, self.lease, self.runtime)

    def test_complete_read_twice_review_never_releases_request_barrier(self):
        before = (self.guard.directory / 'ledger.json').read_bytes()
        result = self.execute()
        self.assertTrue(result['review_passed']); self.assertEqual(result['store_checks'], 10)
        self.assertTrue(all(a.calls == 2 for a in self.adapters.values()))
        self.assertFalse(result['allow_start']); self.assertFalse(result['erasure_authorized'])
        self.assertEqual((self.guard.directory / 'ledger.json').read_bytes(), before)
        with self.assertRaises(ValueError): self.guard.start()
        self.assertNotIn(self.subject, json.dumps(result)); self.assertNotIn(self.request, json.dumps(result))

    def test_missing_case_and_wrong_hmac_never_scan_stores(self):
        for cases in ([], [dict(self.cases[0], subject=str(uuid.uuid4()))]):
            self.cases = cases
            with self.assertRaises(ValueError): self.execute()
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_extra_and_duplicate_cases_block(self):
        original = self.cases[0]
        for cases in ([original, original], [dict(original, id=str(uuid.uuid4()))]):
            self.cases = cases
            with self.assertRaises(ValueError): self.execute()

    def test_missing_registry_and_each_unresolved_store_block(self):
        original = self.adapters
        for name in STORES:
            self.adapters = dict(original); self.adapters.pop(name)
            with self.assertRaises(ValueError): self.execute()
            self.adapters = original; self.adapters[name].present = True
            with self.assertRaises(ValueError): self.execute()
            self.adapters[name].present = False

    def test_stale_checkpoint_cannot_be_replaced_by_timer_success(self):
        self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_provider_failure_blocks_before_account_scan(self):
        self.provider.fail = True
        with self.assertRaises(OSError): self.execute()
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_fresh_checkpoint_of_new_request_cannot_hide_missing_bound_case(self):
        def newer():
            self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
            checkpoint(self.guard, self.base, self.provider)
            return 'c' * 64
        self.runtime = newer
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(any(a.calls for a in self.adapters.values()))
        self.assertEqual(len(self.guard.state()['requests']), 2)

    def test_writer_resume_stops_review(self):
        states = iter([True, False]); self.lease = lambda: next(states)
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_source_drift_and_incomplete_inventory_review_block(self):
        values = iter(['c' * 64, 'd' * 64]); self.runtime = lambda: next(values)
        with self.assertRaises(ValueError): self.execute()
        self.runtime = lambda: True
        with self.assertRaises(ValueError): self.execute()

    def test_request_arriving_during_store_scan_is_preserved_and_blocks(self):
        def concurrent(case):
            if len(self.guard.state()['requests']) == 1:
                self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
            return {'absent': True, 'fingerprint': 'a' * 64}
        self.adapters['profiles'].change = concurrent
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(len(self.guard.state()['requests']), 2)

    def test_whole_registry_change_between_passes_blocks(self):
        store = self.adapters['profiles']
        store.change = lambda case: {'absent': True, 'fingerprint': ('d' if store.calls == 1 else 'e') * 64}
        with self.assertRaises(ValueError): self.execute()

    def test_verifier_cannot_change_identity_for_later_stores(self):
        def mutate(case):
            case['subject'] = str(uuid.uuid4()); case['aliases'].clear()
            return {'absent': True, 'fingerprint': 'a' * 64}
        self.adapters['authentication'].change = mutate
        self.assertTrue(self.execute()['review_passed'])
        self.assertEqual(self.cases[0]['subject'], self.subject)

    def test_malformed_aliases_and_evidence_are_not_review(self):
        original = self.cases[0]
        for change in ({'aliases': []}, {'aliases': ['Uppercase']}, {'aliases': ['fixtureuser'] * 2},
                       {'related_subjects': []}, {'related_subjects': [str(uuid.uuid4())]},
                       {'related_subjects': [self.subject] * 2},
                       {'identity_proof_sha256': 'unknown'}, {'discord_ids': [11111111111111111]},
                       {'unreviewed': True}):
            self.cases = [dict(original, **change)]
            with self.assertRaises(ValueError): self.execute()

    def test_offline_check_is_required_before_guard_or_provider_calls(self):
        self.lease = lambda: False
        self.provider.verify = Mock(side_effect=AssertionError('Do not contact provider'))
        with self.assertRaises(ValueError): self.execute()
        self.provider.verify.assert_not_called()


if __name__ == '__main__': unittest.main()
