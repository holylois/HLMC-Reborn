"""Generated fixtures only. No live account reads, service changes or deletion."""
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock
from recovery_guard import Guard, ANCHOR


class RecoveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'minecraft'
        (self.root / 'config').mkdir(parents=True)
        self.guard = Guard(self.root, self.base / 'external')
        self.guard.initialize()

    def test_normal_start_rotates_and_keeps_pair(self):
        old = self.guard.state()['generation']
        self.assertTrue(self.guard.start()['allow_start'])
        current = self.guard.state()
        self.assertNotEqual(old, current['generation'])
        self.guard._anchor(current)

    def test_explicit_production_paths_keep_export_gate_like_cli_defaults(self):
        gate = self.base / 'serving-gate.json'
        with mock.patch('recovery_guard.ROOT', self.root), mock.patch('recovery_guard.STATE', self.guard.directory), \
                mock.patch('recovery_guard.EXPORT_GATE', gate):
            self.assertEqual(Guard(self.root).export_gate, gate)
            explicit = Guard(self.root, self.guard.directory)
            self.assertEqual(explicit.export_gate, gate)
            with self.assertRaises(FileNotFoundError):
                explicit.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
            self.assertEqual(explicit.state()['requests'], [])

    def test_recovered_alternate_state_does_not_use_production_gate(self):
        with mock.patch('recovery_guard.ROOT', self.root), mock.patch('recovery_guard.STATE', self.base / 'other-state'):
            self.assertIsNone(Guard(self.root, self.guard.directory).export_gate)

    def test_historical_anchor_blocks_start(self):
        old = (self.root / ANCHOR).read_bytes()
        self.guard.start()
        (self.root / ANCHOR).write_bytes(old)
        with self.assertRaisesRegex(ValueError, 'generation'): self.guard.start()

    def test_missing_anchor_blocks_start(self):
        (self.root / ANCHOR).unlink()
        with self.assertRaises(FileNotFoundError): self.guard.start()

    def test_absent_state_never_initializes_itself(self):
        (self.guard.directory / 'ledger.json').unlink()
        with self.assertRaises(FileNotFoundError): self.guard.start()
        self.assertFalse((self.guard.directory / 'ledger.json').exists())

    def test_restore_barrier_survives_process_and_releases_after_success(self):
        key = str(uuid.uuid4()); self.guard.begin_restore(key)
        another = Guard(self.root, self.guard.directory)
        with self.assertRaisesRegex(ValueError, 'Incomplete restore'): another.start()
        (self.root / ANCHOR).write_text('{"schema": 0}')
        another.complete_restore(key)
        self.assertTrue(another.start()['allow_start'])

    def test_wrong_or_duplicate_restore_identity(self):
        key = str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError, 'identity'): self.guard.complete_restore(key)
        self.guard.begin_restore(key)
        with self.assertRaisesRegex(ValueError, 'pending'): self.guard.begin_restore(str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, 'identity'): self.guard.complete_restore(str(uuid.uuid4()))

    def test_requests_block_start_and_restore_without_erasing_stores(self):
        player = self.root / 'generated-player.json'; player.write_text('{"inventory": 7}')
        subject, request = str(uuid.uuid4()), str(uuid.uuid4())
        self.guard.record_request(request, subject)
        state = self.guard.state()
        self.assertNotIn(subject, json.dumps(state))
        self.assertEqual(len(state['requests'][0]['subject_hmac']), 64)
        for action in (self.guard.start, lambda: self.guard.begin_restore(str(uuid.uuid4()))):
            with self.assertRaisesRegex(ValueError, 'per-store'): action()
        self.assertEqual(player.read_text(), '{"inventory": 7}')

    def test_request_during_restore_blocks_completion(self):
        key = str(uuid.uuid4()); self.guard.begin_restore(key)
        self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, 'per-store'): self.guard.complete_restore(key)
        self.assertEqual(self.guard.state()['pending_restore'], key)

    def test_idempotent_request_rejects_subject_change(self):
        subject, request = str(uuid.uuid4()), str(uuid.uuid4())
        self.guard.record_request(request, subject); self.guard.record_request(request, subject)
        self.assertEqual(len(self.guard.state()['requests']), 1)
        with self.assertRaisesRegex(ValueError, 'another subject'):
            self.guard.record_request(request, str(uuid.uuid4()))

    def test_interrupted_commit_blocks_start(self):
        real = self.guard._atomic
        def fail(path, data, *args):
            if path.name == 'ledger.json': raise OSError('Generated interruption')
            return real(path, data, *args)
        with mock.patch.object(self.guard, '_atomic', side_effect=fail), self.assertRaises(OSError):
            self.guard.start()
        self.assertTrue((self.guard.directory / 'transaction.json').exists())
        with self.assertRaisesRegex(ValueError, 'transaction'): self.guard.start()

    def test_symlink_and_hardlink_state_rejected(self):
        path = self.guard.directory / 'ledger.json'; original = path.read_bytes(); path.unlink()
        outside = self.base / 'generated.json'; outside.write_bytes(original); outside.chmod(0o600)
        path.symlink_to(outside)
        with self.assertRaises(ValueError): self.guard.start()
        path.unlink(); os.link(outside, path)
        with self.assertRaises(ValueError): self.guard.start()

    def test_private_permissions_required(self):
        (self.guard.directory / 'ledger.json').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'permissions'): self.guard.start()

    def test_state_must_stay_outside_restored_root(self):
        with self.assertRaisesRegex(ValueError, 'separate'): Guard(self.root, self.root / 'private')
        linked = self.base / 'link'; linked.symlink_to(self.guard.directory, target_is_directory=True)
        with self.assertRaises(ValueError): Guard(self.root, linked)

    def test_linked_config_parent_rejected(self):
        config = self.root / 'config'; config.rename(self.root / 'held-config')
        config.symlink_to(self.root / 'held-config', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'anchor'): self.guard.start()

    def test_corrupt_or_oversized_state_blocks_start(self):
        path = self.guard.directory / 'ledger.json'; path.write_text('invalid')
        with self.assertRaises(ValueError): self.guard.start()
        path.write_text(' ' * 1_000_001)
        with self.assertRaisesRegex(ValueError, 'Oversized'): self.guard.start()

    def test_root_binding_and_malformed_fields_block_start(self):
        good = self.guard.state()
        for value in (dict(good, root='/generated-other-root'), dict(good, requests=None),
                      dict(good, pending_restore='not-an-id'), dict(good, generation='bad')):
            self.guard._atomic(self.guard.directory / 'ledger.json', value)
            with self.assertRaises(ValueError): self.guard.start()

    def test_initialize_preserves_prior_evidence(self):
        with self.assertRaises(FileExistsError): self.guard.initialize()

    def test_existing_anchor_cannot_bootstrap_an_empty_ledger(self):
        replacement = Guard(self.root, self.base / 'replacement-external')
        with self.assertRaisesRegex(ValueError, 'empty-ledger'): replacement.initialize()
        self.assertFalse(replacement.directory.exists())

    def test_missing_subject_key_blocks_start(self):
        (self.guard.directory / 'subject-key.json').unlink()
        with self.assertRaises(FileNotFoundError): self.guard.start()


if __name__ == '__main__': unittest.main()
