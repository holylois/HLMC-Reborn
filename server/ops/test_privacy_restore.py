"""Generated historical whole-root restore. No real account/backup read or service action."""
import json
import uuid
import unittest
from unittest.mock import patch
from guard_checkpoint import checkpoint, pair
from privacy_review import digest
from privacy_restore import HistoricalRestore
from test_privacy_actions import Environment
from test_privacy_backup import Fixture


class Historical(unittest.TestCase):
    def fresh(self):
        e = Environment(); self.addCleanup(e.close); f = Fixture(e.root, e.base)
        old = e.guard.state()['generation']
        with e.guard.locked(): e.guard._rotate(e.guard.state())
        self.assertNotEqual(e.guard.state()['generation'], old)
        checkpoint(e.guard, e.checkpoints, e.provider)
        h = HistoricalRestore(e.guard, f.reader, f.sha, e.base / 'restore-session', e.cases,
                              lambda: e.lease, lambda: e.runtime, e.checkpoints, e.provider)
        restore_id = str(uuid.uuid4()); approval = digest(h.plan(restore_id))
        return e, f, h, restore_id, approval

    def test_exact_historical_restore_reconciles_anchor_without_losing_requests(self):
        e, f, h, key, approval = self.fresh(); requests = e.guard.state()['requests']
        h.begin(key, approval)
        with self.assertRaises(ValueError): e.guard.start()
        h.extract(approval); h.install(approval)
        self.assertEqual((h.directory / 'original-root/profile.dat').read_bytes(), e.before['profile.dat'])
        with self.assertRaises(ValueError): pair(e.guard)
        result = h.reconcile(approval)
        self.assertFalse(result['allow_start']); self.assertEqual(e.guard.state()['requests'], requests)
        self.assertIsNone(e.guard.state()['pending_restore']); e.guard._anchor(e.guard.state())
        self.assertEqual((e.root / 'profile.dat').read_bytes(), e.before['profile.dat'])
        with self.assertRaises(ValueError): e.guard.start()
        with self.assertRaises(ValueError): h.reconcile(approval)

    def test_wrong_approval_or_provider_failure_cannot_arm_restore(self):
        for mode in ('approval', 'provider'):
            e, f, h, key, approval = self.fresh()
            if mode == 'provider': f.provider.corrupt = True
            with self.assertRaises(ValueError): h.begin(key, 'a' * 64 if mode == 'approval' else approval)
            self.assertIsNone(e.guard.state()['pending_restore']); self.assertFalse(h.directory.exists())

    def test_new_request_or_code_drift_after_barrier_keeps_restore_pending(self):
        for mode in ('request', 'runtime', 'writer'):
            e, f, h, key, approval = self.fresh(); h.begin(key, approval)
            if mode == 'request': e.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
            elif mode == 'runtime': e.runtime = 'a' * 64
            else: e.lease = False
            with self.assertRaises(ValueError): h.extract(approval)
            self.assertEqual(e.guard.state()['pending_restore'], key)

    def test_staged_damage_and_extra_files_cannot_replace_current_root(self):
        for mode in ('changed', 'extra'):
            e, f, h, key, approval = self.fresh(); h.begin(key, approval); h.extract(approval)
            target = h.directory / 'tree' / ('profile.dat' if mode == 'changed' else 'unknown')
            target.write_bytes(b'generated unexpected bytes')
            with self.assertRaises(ValueError): h.install(approval)
            self.assertFalse((h.directory / 'original-root').exists()); self.assertTrue(e.root.is_dir())

    def test_failure_between_root_moves_preserves_prior_root_and_pending_barrier(self):
        from privacy_actions import move
        e, f, h, key, approval = self.fresh(); h.begin(key, approval); h.extract(approval); count = 0
        def failed(source, target):
            nonlocal count
            count += 1
            if count == 2: raise OSError('Generated install interruption')
            move(source, target)
        with patch('privacy_restore.move', side_effect=failed):
            with self.assertRaises(OSError): h.install(approval)
        self.assertTrue((h.directory / 'original-root').is_dir()); self.assertTrue((h.directory / 'tree').is_dir())
        self.assertEqual(e.guard.state()['pending_restore'], key)
        with self.assertRaises((ValueError, FileNotFoundError)): e.guard.start()

    def test_original_review_or_key_change_cannot_reconcile(self):
        for mode in ('review', 'key'):
            e, f, h, key, approval = self.fresh(); h.begin(key, approval); h.extract(approval); h.install(approval)
            if mode == 'review':
                p = h.directory / 'original-review.json'; value = json.loads(p.read_bytes())
                value['manifest']['archive_sha256'] = 'a' * 64; p.write_text(json.dumps(value))
            else: e.guard._atomic(e.guard.directory / 'subject-key.json', {'key': 'ab' * 32})
            with self.assertRaises(ValueError): h.reconcile(approval)
            self.assertEqual(e.guard.state()['pending_restore'], key)


if __name__ == '__main__': unittest.main()
