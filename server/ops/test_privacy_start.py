"""Generated identities, stores and provider only. No native process or live service changes."""
import json
import os
import unittest
import uuid
from unittest.mock import Mock
from unittest.mock import patch
from guard_checkpoint import checkpoint
from privacy_exports import plan, publish, gate_bytes
from privacy_review import STORES, digest
from privacy_start import checked_start
from test_privacy_actions import Environment
from test_privacy_review import Store


class VerifiedStart(unittest.TestCase):
    def setUp(self):
        self.env = Environment(); self.addCleanup(self.env.close); e = self.env
        e.run()
        self.adapters = {s: Store() for s in STORES}
        self.policy = e.base / 'private-policy.json'
        publish(e.guard, e.cases, self.policy, e.checkpoints, e.provider,
                digest(plan(e.guard, e.cases)), lambda: True)
        self.scope = Mock(return_value=True); self.protection = Mock(return_value=True)
        self.backup = Mock(return_value=True)

    def execute(self):
        e = self.env
        return checked_start(e.guard, e.checkpoints, e.provider, e.cases, self.adapters,
            lambda: e.lease, lambda: e.runtime, policy_path=self.policy,
            scopes=e.reviews, backup_sha256='d' * 64, verified_stopped_backup=self.backup,
            verified_scope=self.scope, verified_private_recovery=self.protection)

    def test_checked_start_keeps_requests_and_does_not_activate_default_cli(self):
        e = self.env; old = e.guard.state(); result = self.execute(); current = e.guard.state()
        self.assertTrue(result['allow_start']); self.assertEqual(old['requests'], current['requests'])
        self.assertNotEqual(old['generation'], current['generation'])
        self.assertFalse(result['native_process_started']); self.assertFalse(result['erasure_authorized'])
        self.assertTrue(all(a.calls == 3 for a in self.adapters.values()))
        with self.assertRaises(ValueError): e.guard.start()
        self.assertNotIn(e.cases[0]['subject'], json.dumps(result))
        self.assertNotIn(e.cases[0]['id'], json.dumps(result))

    def test_every_next_start_rechecks_current_checkpoint(self):
        self.execute()
        with self.assertRaises((ValueError, OSError)): self.execute()
        e = self.env; checkpoint(e.guard, e.checkpoints, e.provider)
        self.assertTrue(self.execute()['allow_start'])

    def test_old_store_reintroduced_after_success_blocks_next_start(self):
        self.execute(); e = self.env; checkpoint(e.guard, e.checkpoints, e.provider)
        for store in STORES:
            with self.subTest(store=store):
                self.adapters[store].present = True
                before = (e.guard.directory / 'ledger.json').read_bytes()
                with self.assertRaises(ValueError): self.execute()
                self.assertEqual((e.guard.directory / 'ledger.json').read_bytes(), before)
                self.adapters[store].present = False

    def test_each_scope_hold_and_missing_decision_prevents_rotation(self):
        e = self.env; before = (e.guard.directory / 'ledger.json').read_bytes()
        for name in e.reviews:
            old = e.reviews[name]['decision']; e.reviews[name]['decision'] = 'held'
            with self.assertRaises(ValueError): self.execute()
            e.reviews[name]['decision'] = old
        saved = e.reviews.pop('support-moderation')
        with self.assertRaises(ValueError): self.execute()
        e.reviews['support-moderation'] = saved
        self.assertEqual((e.guard.directory / 'ledger.json').read_bytes(), before)

    def test_private_recovery_scope_or_backup_failure_blocks(self):
        for callback in (self.scope, self.protection, self.backup):
            callback.return_value = False
            with self.assertRaises(ValueError): self.execute()
            callback.return_value = True

    def test_gate_closure_or_wrong_identity_policy_blocks(self):
        e = self.env; old = self.policy.read_bytes()
        policy = json.loads(old); policy['ids'] = [str(uuid.uuid4())]
        e.guard._atomic(self.policy, policy)
        gate = gate_bytes(e.gate, os.geteuid())[1]
        import hashlib
        gate['policy_sha256'] = hashlib.sha256(self.policy.read_bytes()).hexdigest()
        e.guard._atomic(e.gate, gate, 0o644)
        with self.assertRaisesRegex(ValueError, 'identities'): self.execute()

    def test_policy_bytes_swapped_between_load_and_final_binding_are_rejected(self):
        from privacy_exports import load as original_load
        e = self.env; before = e.guard.state()['generation']
        def replaced(*args):
            result = original_load(*args)
            self.policy.write_bytes(self.policy.read_bytes() + b' ')
            return result
        with patch('privacy_start.load', side_effect=replaced):
            with self.assertRaisesRegex(ValueError, 'changed after loading'): self.execute()
        self.assertEqual(e.guard.state()['generation'], before)

    def test_all_linked_identities_are_checked_without_clearing_primary_request(self):
        e = self.env; e.cases[0]['related_subjects'].append(str(uuid.uuid4()))
        value = gate_bytes(e.gate, os.geteuid())[1]; value['ready'] = False
        e.guard._atomic(e.gate, value, 0o644)
        publish(e.guard, e.cases, self.policy, e.checkpoints, e.provider,
                digest(plan(e.guard, e.cases)), lambda: True)
        result = self.execute()
        self.assertEqual(result['identities_checked'], 2)
        self.assertEqual(result['requests_retained'], 1)
        self.assertTrue(all(a.calls == 6 for a in self.adapters.values()))

    def test_new_request_preserved_and_missing_case_refuses_scan(self):
        e = self.env; e.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(len(e.guard.state()['requests']), 2)
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_final_locked_pass_detects_data_returning_after_double_review(self):
        e = self.env; before = e.guard.state()['generation']; store = self.adapters['profiles']
        store.change = lambda case: {'absent': store.calls < 3, 'fingerprint': 'a' * 64}
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual(e.guard.state()['generation'], before)

    def test_final_pass_rejects_changed_evidence_even_when_target_still_absent(self):
        e = self.env; old = e.guard.state()['generation']; store = self.adapters['profiles']
        store.change = lambda case: {'absent': True, 'fingerprint': ('a' if store.calls < 3 else 'b') * 64}
        with self.assertRaisesRegex(ValueError, 'evidence changed'): self.execute()
        self.assertEqual(e.guard.state()['generation'], old)

    def test_private_evidence_changes_during_final_check_blocks(self):
        self.protection.side_effect = [True, True, False]
        with self.assertRaises(ValueError): self.execute()

    def test_writer_or_runtime_change_in_final_locked_pass_blocks(self):
        e = self.env
        def changed(case):
            if self.adapters['profiles'].calls == 3: e.lease = False
            return {'absent': True, 'fingerprint': 'a' * 64}
        self.adapters['profiles'].change = changed
        with self.assertRaises(ValueError): self.execute()

    def test_gate_closing_during_final_pass_blocks(self):
        e = self.env
        def close(case):
            if self.adapters['profiles'].calls == 3:
                value = gate_bytes(e.gate, os.geteuid())[1]; value['ready'] = False
                e.guard._atomic(e.gate, value, 0o644)
            return {'absent': True, 'fingerprint': 'a' * 64}
        self.adapters['profiles'].change = close
        with self.assertRaises(ValueError): self.execute()

    def test_changed_registry_during_double_review_blocks(self):
        def replace(case):
            self.adapters['profiles'] = Store()
            return {'absent': True, 'fingerprint': 'a' * 64}
        self.adapters['profiles'].change = replace
        with self.assertRaises(ValueError): self.execute()

    def test_readback_failure_never_scans_or_rotates(self):
        e = self.env; old = e.guard.state()['generation']; e.provider.fail = True
        with self.assertRaises(OSError): self.execute()
        self.assertEqual(e.guard.state()['generation'], old)
        self.assertFalse(any(a.calls for a in self.adapters.values()))

    def test_interrupted_generation_rotation_keeps_barrier_and_request(self):
        e = self.env; requests = e.guard.state()['requests']; original = e.guard._atomic
        def interrupt(path, *args, **kwargs):
            original(path, *args, **kwargs)
            if path.name == 'ledger.json': raise OSError('Generated rotation interruption')
        with patch.object(e.guard, '_atomic', side_effect=interrupt):
            with self.assertRaises(OSError): self.execute()
        self.assertTrue((e.guard.directory / 'transaction.json').exists())
        self.assertEqual(json.loads((e.guard.directory / 'ledger.json').read_bytes())['requests'], requests)
        with self.assertRaises(ValueError): e.guard.start()


if __name__ == '__main__': unittest.main()
