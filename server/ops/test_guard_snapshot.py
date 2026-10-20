"""Private recovery fixtures. Never touches production data, credentials or services."""
import io
import json
import os
import stat
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path
from recovery_guard import Guard
from guard_snapshot import snapshot, verify, sha, private_read


class GuardSnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve(); self.root = self.base / 'generated-server'
        (self.root / 'config').mkdir(parents=True)
        self.guard = Guard(self.root, self.base / 'guard'); self.guard.initialize()
        self.source = self.base / 'snapshot'; self.output = self.base / 'recovered'

    def make(self):
        self.receipt = snapshot(self.guard, self.source)
        self.archive = self.source / 'guard-state.tar'
        return self.receipt

    def test_exact_disk_restore_of_key_and_ledger(self):
        receipt = self.make(); result = verify(self.archive, receipt, self.output)
        self.assertTrue(result['passed'])
        self.assertFalse(result['production_restore_authorized'])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        for name in ('subject-key.json', 'ledger.json'):
            self.assertEqual((self.output / name).read_bytes(), (self.guard.directory / name).read_bytes())
            self.assertEqual(stat.S_IMODE((self.output / name).stat().st_mode), 0o600)

    def test_preserves_recorded_request_without_erasing_anything(self):
        self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        self.make(); result = verify(self.archive, self.receipt, self.output)
        self.assertEqual(result['request_count'], 1)
        self.assertEqual(len(self.guard.state()['requests']), 1)

    def test_old_snapshot_does_not_forget_new_request_or_release_barrier(self):
        self.make(); pending = str(uuid.uuid4()); self.guard.begin_restore(pending)
        self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        verify(self.archive, self.receipt, self.output)
        self.assertEqual(self.guard.state()['pending_restore'], pending)
        self.assertEqual(len(self.guard.state()['requests']), 1)
        with self.assertRaises(ValueError): self.guard.complete_restore(pending)

    def test_archive_corruption_rejected_before_extraction(self):
        self.make(); data = bytearray(self.archive.read_bytes()); data[1024] ^= 1; self.archive.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'original receipt'): verify(self.archive, self.receipt, self.output)
        self.assertFalse(self.output.exists())

    def test_independent_original_receipt_required(self):
        self.make()
        for receipt in ({}, dict(self.receipt, archive_sha256='0' * 64), dict(self.receipt, request_count=9)):
            with self.assertRaises((ValueError, KeyError)): verify(self.archive, receipt, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_destination_and_snapshot_evidence_preserved(self):
        self.make(); self.output.mkdir(); (self.output / 'kept').write_text('generated data')
        with self.assertRaises(FileExistsError): verify(self.archive, self.receipt, self.output)
        with self.assertRaises(FileExistsError): snapshot(self.guard, self.source)
        self.assertEqual((self.output / 'kept').read_text(), 'generated data')

    def test_active_guard_cannot_be_extraction_target(self):
        self.make()
        with self.assertRaises(FileExistsError): verify(self.archive, self.receipt, self.guard.directory)
        self.assertTrue(self.guard.start()['allow_start'])

    def test_pending_restore_cannot_create_checkpoint(self):
        self.guard.begin_restore(str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, 'Pending'): snapshot(self.guard, self.source)
        self.assertFalse(self.source.exists())

    def test_lock_contention_does_not_create_snapshot(self):
        with self.guard.locked(), self.assertRaises(BlockingIOError): snapshot(self.guard, self.source)
        self.assertFalse(self.source.exists())

    def test_snapshot_must_stay_outside_guard(self):
        with self.assertRaisesRegex(ValueError, 'separate'): snapshot(self.guard, self.guard.directory / 'backup')

    def test_linked_destination_and_archive_rejected(self):
        self.make(); linked = self.base / 'linked'; linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError): verify(self.archive, self.receipt, linked / 'recovered')
        file = self.base / 'linked.tar'; file.symlink_to(self.archive)
        with self.assertRaises(ValueError): verify(file, self.receipt, self.output)

    def test_public_permissions_or_hardlinks_rejected(self):
        self.make(); self.archive.chmod(0o644)
        with self.assertRaises(ValueError): verify(self.archive, self.receipt, self.output)
        self.archive.chmod(0o600); os.link(self.archive, self.base / 'hardlink.tar')
        with self.assertRaises(ValueError): verify(self.archive, self.receipt, self.output)

    def test_receipt_input_must_be_private_bounded_regular_file(self):
        self.make(); path = self.source / 'receipt.json'
        self.assertEqual(json.loads(private_read(path, 100_000)), self.receipt)
        with self.assertRaises(ValueError): private_read(path, 4)
        path.chmod(0o644)
        with self.assertRaises(ValueError): private_read(path, 100_000)
        path.chmod(0o600)
        link = self.base / 'receipt-link'; link.symlink_to(path)
        with self.assertRaises(ValueError): private_read(link, 100_000)
        fifo = self.base / 'fifo'; os.mkfifo(fifo, 0o600)
        with self.assertRaises(ValueError): private_read(fifo, 100_000)

    def crafted(self, members):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for name, content, kind in members:
                member = tarfile.TarInfo(name); member.type = kind
                if kind == tarfile.REGTYPE: member.size = len(content)
                else: member.linkname = '/generated-outside'
                archive.addfile(member, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
        data = buffer.getvalue(); file = self.base / (uuid.uuid4().hex + '.tar'); file.write_bytes(data); file.chmod(0o600)
        return file, {'schema': 1, 'kind': 'guard-state', 'archive_bytes': len(data), 'archive_sha256': sha(data)}

    def test_unexpected_traversal_symlink_and_special_members_rejected(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('ledger.json', tarfile.SYMTYPE),
                           ('ledger.json', tarfile.FIFOTYPE), ('private/ledger.json', tarfile.REGTYPE)):
            file, receipt = self.crafted([(name, b'generated', kind)])
            with self.assertRaises(ValueError): verify(file, receipt, self.output)
        self.assertFalse((self.base / 'escape').exists())

    def test_duplicate_or_incomplete_payload_rejected(self):
        for rows in ([('ledger.json', b'{}', tarfile.REGTYPE)] * 2,
                     [('ledger.json', b'{}', tarfile.REGTYPE)]):
            file, receipt = self.crafted(rows)
            with self.assertRaises(ValueError): verify(file, receipt, self.output)

    def test_missing_private_key_prevents_snapshot(self):
        (self.guard.directory / 'subject-key.json').unlink()
        with self.assertRaises(FileNotFoundError): snapshot(self.guard, self.source)
        self.assertFalse(self.source.exists())


if __name__ == '__main__': unittest.main()
