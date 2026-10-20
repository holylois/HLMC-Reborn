"""Generated stopped archives, private receipts and fake read-only provider. No actual accounts or Drive."""
import contextlib
import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backup_receipts import tree_receipt
from privacy_backup import StoppedSet, ReadOnlyDrive, BoundedInfo, TOTAL, hashes
from privacy_exports import encoded
from recovery_set import attest, save


class Provider:
    def __init__(self): self.objects = {}; self.reads = []; self.lookups = []; self.change = None; self.corrupt = False
    def metadata(self, name):
        self.lookups.append(name); raw = self.objects[name]
        return {'Name': Path(name).name, 'IsDir': False, 'Size': len(raw),
                'Hashes': {'MD5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}
    @contextlib.contextmanager
    def stream(self, name, size):
        self.reads.append(name)
        if self.change:
            callback, self.change = self.change, None; callback()
        with io.BytesIO(self.objects[name] + (b'corrupt' if self.corrupt else b'')) as stream: yield stream


class Fixture:
    def __init__(self, root=None, base=None, populate=True):
        self.temp = tempfile.TemporaryDirectory() if base is None else None
        self.base = Path(self.temp.name).resolve() if base is None else base
        self.root = self.base / 'game' if root is None else root
        self.root.mkdir(exist_ok=True)
        if populate:
            for name in ('world', 'config', 'mods', 'EasyAuth'): (self.root / name).mkdir(exist_ok=True)
            for name in ('world/level.dat', 'config/fixture.json', 'mods/fixture.jar', 'EasyAuth/fixture.db', 'server.jar'):
                (self.root / name).write_bytes(b'generated stopped fixture ' + name.encode())
        self.directory = self.base / 'capture'; self.directory.mkdir(mode=0o700)
        self.archive = self.directory / 'backup.tar'; self.provider = Provider()
        self.original = self.base / 'independent-backup.json'
        self.capture()

    def capture(self, modify=None, format=tarfile.USTAR_FORMAT):
        with tarfile.open(self.archive, 'w', format=format) as archive:
            archive.add(self.root, arcname=self.root.name)
            if modify: modify(archive)
        self.archive.chmod(0o600); self.sha = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        with patch('recovery_set.require_stopped'):
            self.attestation = attest(self.archive, self.root, self.sha, self.archive.stat().st_size)
        path = self.directory / 'recovery-set.json'
        if path.exists(): path.write_bytes(encoded(self.attestation))
        else: save(self.directory, self.attestation)
        self.repin()

    def repin(self):
        listing = []
        self.provider.objects = {}
        for path in sorted(self.directory.rglob('*')):
            if not path.is_file(): continue
            relative = path.relative_to(self.directory).as_posix(); remote = 'maintenance/capture/' + relative
            raw = path.read_bytes(); self.provider.objects[remote] = raw
            listing.append(dict(self.provider.metadata(remote), Path=relative))
        self.record = tree_receipt(self.directory, listing, 'maintenance/capture')
        self.original.write_bytes(encoded(self.record)); self.original.chmod(0o600)
        self.pin = hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.provider.reads.clear(); self.provider.lookups.clear()
        self.reader = self.make_reader()

    def make_reader(self, **changes):
        args = dict(root=self.root, directory=self.directory, original=self.original,
                    original_sha256=self.pin, provider=self.provider)
        args.update(changes); return StoppedSet(**args)

    def close(self):
        if self.temp: self.temp.cleanup()


class StoppedBackups(unittest.TestCase):
    def fresh(self):
        f = Fixture(); self.addCleanup(f.close); return f

    def test_independent_complete_original_and_actual_streams_pass(self):
        f = self.fresh(); before = {p: p.read_bytes() for p in f.directory.iterdir()}
        self.assertTrue(f.reader.verify(f.sha)); self.assertEqual(len(f.provider.reads), 2)
        self.assertEqual(before, {p: p.read_bytes() for p in f.directory.iterdir()})
        self.assertTrue(f.reader.verify(f.sha)); self.assertEqual(len(f.provider.reads), 2)
        self.assertEqual(len(f.provider.lookups), 4)
        self.assertTrue(f.make_reader().verify(f.sha)); self.assertEqual(len(f.provider.reads), 4)

    def test_changed_local_bytes_even_after_cached_pass_refuse(self):
        for name in ('backup.tar', 'recovery-set.json'):
            f = self.fresh(); f.reader.verify(f.sha); path = f.directory / name
            raw = path.read_bytes(); path.write_bytes(b'X' + raw[1:])
            with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_provider_corruption_failure_and_missing_original_refuse(self):
        for kind in ('corrupt-stream', 'missing', 'bad-metadata', 'failure'):
            f = self.fresh()
            if kind == 'corrupt-stream': f.provider.corrupt = True
            elif kind == 'missing': f.provider.objects.pop('maintenance/capture/backup.tar')
            elif kind == 'bad-metadata': f.provider.objects['maintenance/capture/backup.tar'] = b'wrong'
            else: f.provider.metadata = lambda name: (_ for _ in ()).throw(OSError('Generated transport failure'))
            with self.assertRaises((ValueError, KeyError, OSError)): f.reader.verify(f.sha)
            self.assertIsNone(f.reader.cache)

    def test_cached_local_proof_still_checks_remote_checksum(self):
        f = self.fresh(); f.reader.verify(f.sha)
        f.provider.objects['maintenance/capture/backup.tar'] = b'wrong'
        with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_wrong_archive_pin_and_independent_receipt_drift_refuse(self):
        f = self.fresh()
        with self.assertRaises(ValueError): f.reader.verify('a' * 64)
        f.original.write_bytes(f.original.read_bytes() + b' ')
        with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_self_receipt_and_originals_inside_restored_root_refuse(self):
        f = self.fresh(); p = f.directory / 'self.json'; p.write_bytes(f.original.read_bytes()); p.chmod(0o600)
        with self.assertRaises(ValueError): f.make_reader(original=p)
        inside = f.root / 'inside'; inside.mkdir(mode=0o700)
        with self.assertRaises(ValueError): f.make_reader(directory=inside)

    def test_extra_missing_linked_or_public_member_refuses(self):
        for kind in ('extra', 'missing', 'symlink', 'hardlink', 'mode', 'parent-mode'):
            f = self.fresh(); p = f.archive
            if kind == 'extra': (f.directory / 'unknown').write_bytes(b'unreviewed')
            elif kind == 'missing': p.rename(f.base / 'held')
            elif kind == 'mode': p.chmod(0o644)
            elif kind == 'parent-mode': f.directory.chmod(0o755)
            else:
                p.rename(f.base / 'held')
                if kind == 'symlink': p.symlink_to(f.base / 'held')
                else: os.link(f.base / 'held', p)
            with self.assertRaises((ValueError, FileNotFoundError)): f.reader.verify(f.sha)

    def test_change_during_remote_readback_refuses_and_does_not_cache(self):
        f = self.fresh(); f.provider.change = lambda: f.archive.write_bytes(b'generated race')
        with self.assertRaises(ValueError): f.reader.verify(f.sha)
        self.assertIsNone(f.reader.cache)

    def test_flags_without_matching_capture_or_scope_never_pass(self):
        for change in ({'comparison_verified': False}, {'writers_checked': []}, {'archive_bytes': True},
                       {'archive_sha256': 'a' * 64}, {'kind': 'online-server'}):
            f = self.fresh(); (f.directory / 'recovery-set.json').write_bytes(encoded(dict(f.attestation, **change)))
            f.repin()
            with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_unsafe_duplicate_special_and_unknown_link_members_refuse(self):
        for kind in ('escape', 'duplicate', 'symlink', 'hardlink', 'fifo'):
            f = self.fresh()
            def added(archive):
                row = tarfile.TarInfo(f.root.name + ('/../escape' if kind == 'escape' else '/extra'))
                if kind == 'duplicate': row.name = f.root.name + '/server.jar'
                if kind in ('symlink', 'hardlink'):
                    row.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                    row.linkname = 'server.jar'
                if kind == 'fifo': row.type = tarfile.FIFOTYPE
                archive.addfile(row)
            f.capture(added)
            with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_missing_world_auth_config_or_software_payload_refuse_even_if_re_pinned(self):
        for name in ('world/level.dat', 'EasyAuth/fixture.db', 'config/fixture.json', 'mods/fixture.jar', 'server.jar'):
            f = self.fresh(); (f.root / name).rename(f.base / 'held-payload'); f.capture()
            with self.assertRaises(ValueError): f.reader.verify(f.sha)

    def test_bounded_stream_rejects_extra_bytes(self):
        with self.assertRaises(ValueError): hashes(io.BytesIO(b'xx'), 1)

    def test_bounded_pax_time_headers_pass_but_huge_metadata_and_sparse_refuse_before_read(self):
        f = self.fresh(); f.capture(format=tarfile.PAX_FORMAT)
        self.assertTrue(f.reader.verify(f.sha))
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE,
                     tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK, tarfile.GNUTYPE_SPARSE):
            row = BoundedInfo('generated-metadata'); row.type = kind; row.size = 65537; source = Mock()
            with self.assertRaises(ValueError): row._proc_member(source)
            source.fileobj.read.assert_not_called()

    def test_unrelated_or_duplicate_receipt_members_refuse(self):
        for kind in ('mixed', 'duplicate', 'boolean-size', 'oversized'):
            f = self.fresh(); rows = f.record['members']
            if kind == 'mixed': rows[0]['path'] = 'maintenance/other/backup.tar'
            elif kind == 'duplicate': rows.append(rows[0])
            else: rows[0]['size'] = True if kind == 'boolean-size' else TOTAL + 1
            f.record['backup']['id'] = 'maintenance-' + hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
            f.original.write_bytes(encoded(f.record)); f.pin = hashlib.sha256(f.original.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): f.make_reader().verify(f.sha)

    def test_real_checked_start_uses_reader_and_refuses_changed_backup_without_rotation(self):
        from test_privacy_start import VerifiedStart
        test = VerifiedStart('test_checked_start_keeps_requests_and_does_not_activate_default_cli')
        test.setUp(); self.addCleanup(test.doCleanups); e = test.env
        f = Fixture(e.root, e.base)
        test.backup = f.reader.verify
        from privacy_start import checked_start
        def execute():
            return checked_start(e.guard, e.checkpoints, e.provider, e.cases, test.adapters,
                lambda: e.lease, lambda: e.runtime, policy_path=test.policy, scopes=e.reviews,
                backup_sha256=f.sha, verified_stopped_backup=test.backup,
                verified_scope=test.scope, verified_private_recovery=test.protection)
        old = e.guard.state()['generation']; f.provider.corrupt = True
        with self.assertRaises(ValueError): execute()
        self.assertEqual(e.guard.state()['generation'], old)
        f.provider.corrupt = False
        self.assertTrue(execute()['allow_start']); self.assertEqual(len(e.guard.state()['requests']), 1)
        self.assertEqual(len(f.provider.reads), 3)  # One failed read plus exactly one full successful set.
        with self.assertRaises(ValueError): e.guard.start()


class ReadOnlyTransport(unittest.TestCase):
    def test_metadata_and_stream_transport_use_only_scoped_reads(self):
        drive = ReadOnlyDrive(); name = 'maintenance/capture/backup.tar'; raw = b'generated backup stream'
        row = {'Name': 'backup.tar', 'Size': len(raw), 'IsDir': False,
               'Hashes': {'MD5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}
        with patch('privacy_backup.subprocess.run', return_value=SimpleNamespace(stdout=encoded(row))) as run:
            self.assertEqual(drive.metadata(name), row)
            self.assertEqual(run.call_args.args[0][:3], ['rclone', 'lsjson', 'gdrive:Holy Lois Backups/' + name])
        process = Mock(stdout=io.BytesIO(raw)); process.wait.return_value = 0; process.poll.return_value = 0
        with patch('privacy_backup.subprocess.Popen', return_value=process) as start:
            with drive.stream(name, len(raw)) as stream: self.assertEqual(hashes(stream, len(raw))['size'], len(raw))
            self.assertEqual(start.call_args.args[0][:3], ['rclone', 'cat', 'gdrive:Holy Lois Backups/' + name])
            self.assertIn('--max-duration', start.call_args.args[0]); process.kill.assert_not_called()

    def test_nonzero_provider_exit_cannot_be_verified_even_with_matching_bytes(self):
        drive = ReadOnlyDrive(); process = Mock(stdout=io.BytesIO(b'x'))
        process.wait.return_value = 1; process.poll.return_value = 1
        with patch('privacy_backup.subprocess.Popen', return_value=process):
            with self.assertRaises(OSError):
                with drive.stream('maintenance/capture/backup.tar', 1) as stream: stream.read()

    def test_remote_scope_size_and_mutation_commands_not_exposed(self):
        drive = ReadOnlyDrive()
        for name in ('server/backup.tar', 'maintenance/../secret', '/secret', 'maintenance/set'):
            with self.assertRaises(ValueError): drive.metadata(name)
        with self.assertRaises(ValueError):
            with drive.stream('maintenance/capture/backup.tar', True): pass
        self.assertFalse(hasattr(drive, 'upload')); self.assertFalse(hasattr(drive, 'command'))


if __name__ == '__main__': unittest.main()
