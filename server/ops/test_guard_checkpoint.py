"""Generated checkpoint fixtures only. No real provider, credentials, services or account data."""
import hashlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
from guard_checkpoint import checkpoint, pair, locked, Drive, FILES
from recovery_guard import Guard


class Provider:
    def __init__(self): self.objects = {}; self.fail = False; self.change = None
    def ensure(self, path, fingerprint, name):
        key = (fingerprint, name); data = path.read_bytes()
        if key in self.objects and self.objects[key] != data: raise ValueError('Immutable remote conflict')
        self.objects[key] = data
        if self.change:
            action, self.change = self.change, None; action()
        if self.fail: raise OSError('Generated transfer failure')


class Checkpoints(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        game = self.root / 'game'; (game / 'config').mkdir(parents=True)
        self.guard = Guard(game, self.root / 'guard'); self.guard.initialize()
        self.base = self.root / 'checkpoints'; self.base.mkdir(mode=0o700)
        self.provider = Provider()

    def execute(self): return checkpoint(self.guard, self.base, self.provider)
    def directory(self): return self.base / pair(self.guard)

    def test_first_checkpoint_and_unchanged_pair_recheck(self):
        before = pair(self.guard)
        self.assertTrue(self.execute()['changed_state'])
        self.assertFalse(self.execute()['changed_state'])
        self.assertEqual(len(self.provider.objects), 3)
        self.assertEqual(len(list(self.directory().glob('proof-*'))), 1)
        self.assertEqual(pair(self.guard), before)
        self.assertFalse(json.loads((self.base / 'latest.json').read_text())['production_restore_authorized'])

    def test_new_generation_keeps_both_recovery_sets(self):
        self.execute(); old = self.directory(); self.guard.start()
        self.assertTrue(self.execute()['changed_state'])
        self.assertTrue(old.exists()); self.assertEqual(len(self.provider.objects), 6)

    def test_new_request_preserved_in_private_checkpoint(self):
        self.execute(); self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        self.execute(); self.assertEqual(len(self.guard.state()['requests']), 1)
        with self.assertRaises(ValueError): self.guard.start()

    def test_pending_restore_refuses_current_checkpoint(self):
        self.guard.begin_restore(str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.provider.objects)

    def test_missing_key_never_reinitializes(self):
        (self.guard.directory / 'subject-key.json').unlink()
        with self.assertRaises(FileNotFoundError): self.execute()
        self.assertFalse((self.guard.directory / 'subject-key.json').exists())

    def test_failed_upload_resumes_complete_checkpoint_without_duplicate_proof(self):
        self.provider.fail = True
        with self.assertRaises(OSError): self.execute()
        self.assertFalse((self.base / 'latest.json').exists())
        self.provider.fail = False; self.assertTrue(self.execute()['passed'])
        self.assertEqual(len(list(self.directory().glob('proof-*'))), 1)

    def test_newer_request_during_upload_prevents_current_index(self):
        self.provider.change = lambda: self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse((self.base / 'latest.json').exists())
        self.assertEqual(len(self.guard.state()['requests']), 1)
        self.assertTrue(self.execute()['passed'])

    def test_remote_conflict_does_not_overwrite_or_refresh_index(self):
        self.execute(); before = (self.base / 'latest.json').read_bytes()
        key = next(iter(self.provider.objects)); self.provider.objects[key] = b'generated conflict'
        with self.assertRaises(ValueError): self.execute()
        self.assertEqual((self.base / 'latest.json').read_bytes(), before)
        self.assertEqual(self.provider.objects[key], b'generated conflict')

    def test_corrupt_local_archive_rejected_before_network(self):
        self.execute(); path = self.directory() / 'guard-state.tar'; path.write_bytes(b'generated corrupt')
        self.provider = Provider()
        with self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.provider.objects)

    def test_incomplete_snapshot_is_retained_for_review(self):
        directory = self.directory(); directory.mkdir(mode=0o700)
        (directory / 'guard-state.tar').write_text('generated unfinished')
        with self.assertRaises(FileNotFoundError): self.execute()
        self.assertTrue((directory / 'guard-state.tar').exists())

    def test_linked_or_public_parent_rejected(self):
        linked = self.root / 'linked'; linked.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError): checkpoint(self.guard, linked, self.provider)
        self.base.chmod(0o755)
        with self.assertRaises(ValueError): self.execute()

    def test_job_lock_contention_prevents_provider_calls(self):
        with locked(self.base), self.assertRaises(BlockingIOError): self.execute()
        self.assertFalse(self.provider.objects)

    def test_guard_path_cannot_be_checkpoint_target(self):
        with self.assertRaises(ValueError): checkpoint(self.guard, self.guard.directory, self.provider)

    def test_changed_proof_location_and_key_rejected(self):
        self.execute(); path = self.directory() / 'local-proof.json'
        value = json.loads(path.read_text()); value['proof_directory'] = '../guard'
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.execute()

    def test_changed_recovered_key_is_not_a_valid_cached_proof(self):
        self.execute(); value = json.loads((self.directory() / 'local-proof.json').read_text())
        restored = Guard(self.guard.root, self.directory() / value['proof_directory'])
        restored._atomic(restored.directory / 'subject-key.json', {'key': uuid.uuid4().hex + uuid.uuid4().hex})
        with self.assertRaises(ValueError): self.execute()

    def test_generation_change_during_snapshot_does_not_get_uploaded_under_old_identity(self):
        from guard_snapshot import snapshot
        def changed(guard, destination):
            guard.start()
            return snapshot(guard, destination)
        with patch('guard_checkpoint.snapshot', changed), self.assertRaises(ValueError): self.execute()
        self.assertFalse(self.provider.objects)
        self.assertFalse((self.base / 'latest.json').exists())


class DriveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / FILES[0]
        self.data = b'generated private fixture'; self.path.write_bytes(self.data); self.path.chmod(0o600)
        self.fingerprint = 'a' * 64; self.drive = Drive()
        self.metadata = {'Name': FILES[0], 'IsDir': False, 'Size': len(self.data),
                         'Hashes': {'md5': hashlib.md5(self.data).hexdigest()}}

    def command(self, row=None, readback=None):
        self.drive.command = Mock(side_effect=[b'', json.dumps(self.metadata if row is None else row).encode(),
                                              self.data if readback is None else readback])

    def test_immutable_upload_and_actual_bounded_readback(self):
        self.command(); self.drive.ensure(self.path, self.fingerprint, FILES[0])
        first = self.drive.command.call_args_list[0].args
        self.assertIn('--immutable', first)
        self.assertIn('--count', self.drive.command.call_args_list[-1].args)

    def test_provider_hash_and_identity_must_match(self):
        for change in ({'Name': 'other'}, {'Size': 999}, {'IsDir': True}, {'Hashes': {'md5': '0' * 32}}):
            self.command(dict(self.metadata, **change))
            with self.assertRaises(ValueError): self.drive.ensure(self.path, self.fingerprint, FILES[0])

    def test_actual_readback_cannot_be_replaced_by_provider_checksum(self):
        self.command(readback=b'generated wrong bytes')
        with self.assertRaises(ValueError): self.drive.ensure(self.path, self.fingerprint, FILES[0])

    def test_unsafe_provider_paths_rejected(self):
        self.command()
        for fingerprint, name in (('../x', FILES[0]), (self.fingerprint, '../key')):
            with self.assertRaises(ValueError): self.drive.ensure(self.path, fingerprint, name)
        self.drive.command.assert_not_called()


if __name__ == '__main__': unittest.main()
