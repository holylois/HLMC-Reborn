"""Actual generated private files/journals and mocked provider transport. Never reads live evidence."""
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock
from guard_checkpoint import pair
from privacy_actions import Plan
from privacy_evidence import Evidence, ReadOnlyDrive, hash_bytes
from privacy_exports import encoded, plan, publish
from privacy_review import STORES, digest
from privacy_start import checked_start
from test_privacy_actions import Environment
from test_privacy_review import Store


class Provider:
    def __init__(self): self.objects = {}; self.calls = []; self.fail = False; self.change = None
    def verify(self, bundle, name, raw):
        self.calls.append(name)
        if self.fail: raise OSError('Generated provider failure')
        if self.objects[(bundle, name)] != raw: raise ValueError('Generated remote object differs')
        if self.change:
            action, self.change = self.change, None; action()


class Fixture:
    def __init__(self, env=None):
        self.env = Environment() if env is None else env; e = self.env
        backup = getattr(e, 'startup_backup_sha256', 'd' * 64)
        self.bundle = e.base / 'private-bundle'; self.bundle.mkdir(mode=0o700); (self.bundle / 'objects').mkdir(mode=0o700)
        self.objects = {}
        identity = self.add(b'generated identity review')
        e.cases[0]['identity_proof_sha256'] = identity
        for scope, value in e.reviews.items(): value['evidence_sha256'] = self.add(('generated evidence ' + scope).encode())
        if hasattr(e, 'refresh_bindings'): e.refresh_bindings()
        e.plan = e.make_plan(); e.approval = digest(e.plan.description())
        e.protected_manifest = digest(e.plan.protection_manifest(e.cases)); e.run()
        self.policy = e.base / 'startup-policy.json'
        publish(e.guard, e.cases, self.policy, e.checkpoints, e.provider,
                digest(plan(e.guard, e.cases)), lambda: True)
        self.manifest = {'schema': 1, 'kind': 'private-startup-review', 'root': str(e.root),
            'guard_pair_sha256': pair(e.guard), 'cases': e.cases, 'scopes': e.reviews,
            'runtime_sha256': e.runtime, 'backup_sha256': backup,
            'policy_sha256': digest(json.loads(self.policy.read_bytes()))}
        self.plan_hash = self.add(encoded(e.plan.description()))
        journal = self.add((e.directory / 'journal.json').read_bytes())
        for a in e.plan.actions:
            self.add((e.directory / 'originals' / a['relative']).read_bytes())
            if a['replacement'] is not None: self.add(a['replacement'])
        self.index_value = {'schema': 1, 'kind': 'private-case-recovery',
            'binding': {'root': str(e.root), 'cases_sha256': digest(e.cases), 'scopes_sha256': digest(e.reviews),
                'runtime_sha256': e.runtime, 'backup_sha256': backup, 'policy_sha256': self.manifest['policy_sha256']},
            'cases': self.add(encoded(e.cases)), 'scopes': self.add(encoded(e.reviews)),
            'transactions': [{'plan': self.plan_hash, 'journal': journal}],
            'objects': self.objects}
        self.index = e.base / 'independent-original.json'; self.index.write_bytes(encoded(self.index_value)); self.index.chmod(0o600)
        self.decisions = e.base / 'current-decisions.json'
        self.decisions.write_bytes(encoded({'schema': 1, 'kind': 'current-private-scope-review', 'root': str(e.root),
            'cases_sha256': digest(e.cases), 'scopes': e.reviews})); self.decisions.chmod(0o600)
        self.provider = Provider(); self.pin = hash_bytes(self.index.read_bytes())
        self.provider.objects[(self.pin, 'index.json')] = self.index.read_bytes()
        for name in self.objects: self.provider.objects[(self.pin, 'objects/' + name)] = (self.bundle / 'objects' / name).read_bytes()
        self.reader = self.make_reader()

    def add(self, raw):
        name = hash_bytes(raw); self.objects[name] = {'bytes': len(raw)}
        target = self.bundle / 'objects' / name; target.write_bytes(raw); target.chmod(0o600)
        return name

    def make_reader(self, **changes):
        args = dict(directory=self.bundle, index=self.index, index_sha256=self.pin, decisions=self.decisions,
                    transactions={self.plan_hash: self.env.directory}, provider=self.provider)
        args.update(changes); return Evidence(**args)

    def repin(self):
        self.index.write_bytes(encoded(self.index_value)); self.pin = hash_bytes(self.index.read_bytes())
        self.provider.objects[(self.pin, 'index.json')] = self.index.read_bytes()
        for name in self.objects: self.provider.objects[(self.pin, 'objects/' + name)] = (self.bundle / 'objects' / name).read_bytes()
        self.reader = self.make_reader()

    def close(self): self.env.close()


class EvidenceTests(unittest.TestCase):
    def fresh(self):
        f = Fixture(); self.addCleanup(f.close); return f

    def test_real_local_objects_journal_originals_and_remote_readback_pass(self):
        f = self.fresh(); before = set(f.env.base.rglob('*'))
        self.assertTrue(f.reader.verify_scope(f.manifest)); self.assertFalse(f.provider.calls)
        self.assertTrue(f.reader.verify_recovery(f.manifest))
        self.assertEqual(len(f.provider.calls), len(f.objects) + 1)
        self.assertEqual(set(f.env.base.rglob('*')), before)

    def test_materialize_protects_actual_originals_and_replacements_without_upload(self):
        from privacy_evidence import materialize
        f = self.fresh(); e = f.env
        names = {c['identity_proof_sha256'] for c in e.cases} | {v['evidence_sha256'] for v in e.reviews.values()}
        artifacts = {name: f.bundle / 'objects' / name for name in names}
        target = e.base / 'new-bundle'; index = e.base / 'new-independent-index.json'
        result = materialize(e.guard, f.manifest, artifacts, {f.plan_hash: e.directory}, target, index,
                             f.decisions, lambda: True, lambda: e.runtime)
        self.assertFalse(result['uploaded']); self.assertFalse(f.provider.calls)
        reader = f.make_reader(directory=target, index=index, index_sha256=result['index_sha256'])
        self.assertTrue(reader.verify_scope(f.manifest))
        for action in e.plan.actions:
            self.assertEqual((target / 'objects' / action['before']['sha256']).read_bytes(),
                             (e.directory / 'originals' / action['relative']).read_bytes())

    def test_checked_start_consumes_actual_readers_and_retains_request(self):
        f = self.fresh(); e = f.env
        result = checked_start(e.guard, e.checkpoints, e.provider, e.cases, {s: Store() for s in STORES},
            lambda: True, lambda: e.runtime, policy_path=f.policy, scopes=e.reviews, backup_sha256='d' * 64,
            verified_stopped_backup=lambda value: value == 'd' * 64,
            verified_scope=f.reader.verify_scope, verified_private_recovery=f.reader.verify_recovery)
        self.assertTrue(result['allow_start']); self.assertEqual(result['requests_retained'], 1)
        self.assertTrue(f.provider.calls)
        with self.assertRaises(ValueError): e.guard.start()

    def test_changed_index_or_wrong_pin_cannot_supply_its_own_receipt(self):
        f = self.fresh()
        with self.assertRaises(ValueError): f.make_reader(index_sha256='a' * 64).verify_recovery(f.manifest)
        f.index.write_bytes(f.index.read_bytes() + b' ')
        with self.assertRaises(ValueError): f.reader.verify_scope(f.manifest)

    def test_missing_corrupt_and_unreferenced_object_fail_closed(self):
        for kind in ('missing', 'corrupt', 'extra'):
            f = self.fresh(); name = next(iter(f.objects)); path = f.bundle / 'objects' / name
            if kind == 'missing': path.rename(f.env.base / 'retained-object')
            elif kind == 'corrupt': path.write_bytes(b'generated corruption')
            else: f.add(b'unreviewed extra object')
            with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_independent_index_and_current_decisions_cannot_be_inside_bundle(self):
        f = self.fresh()
        for key in ('index', 'decisions'):
            p = f.bundle / key; p.write_bytes(b'generated untrusted self receipt'); p.chmod(0o600)
            with self.assertRaises(ValueError): f.make_reader(**{key: p})

    def test_new_hold_or_missing_current_decisions_blocks_old_proof(self):
        f = self.fresh(); value = json.loads(f.decisions.read_bytes())
        value['scopes']['support-moderation']['decision'] = 'held'
        f.decisions.write_bytes(encoded(value))
        with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)
        f.decisions.rename(f.env.base / 'held-decisions')
        with self.assertRaises(FileNotFoundError): f.reader.verify_scope(f.manifest)

    def test_provider_corruption_missing_and_failure_cannot_be_success(self):
        for kind in ('corrupt', 'missing', 'failed'):
            f = self.fresh(); key = (f.pin, 'objects/' + next(iter(f.objects)))
            if kind == 'corrupt': f.provider.objects[key] = b'generated remote corruption'
            elif kind == 'missing': f.provider.objects.pop(key)
            else: f.provider.fail = True
            with self.assertRaises((ValueError, KeyError, OSError)): f.reader.verify_recovery(f.manifest)

    def test_new_hold_during_readback_blocks_final_verification(self):
        f = self.fresh()
        def hold():
            value = json.loads(f.decisions.read_bytes()); value['scopes']['permissions']['decision'] = 'held'
            f.decisions.write_bytes(encoded(value))
        f.provider.change = hold
        with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_undo_journal_or_missing_original_refuses_startup_evidence(self):
        for kind in ('undo', 'missing-original'):
            f = self.fresh(); e = f.env
            if kind == 'undo': e.run(undo=True)
            else: (e.directory / 'originals/profile.dat').rename(e.base / 'retained-original')
            with self.assertRaises((ValueError, FileNotFoundError)): f.reader.verify_scope(f.manifest)

    def test_foreign_case_runtime_policy_or_backup_requires_new_review(self):
        for field in ('runtime_sha256', 'policy_sha256', 'backup_sha256'):
            f = self.fresh(); value = dict(f.manifest, **{field: 'a' * 64})
            with self.assertRaises(ValueError): f.reader.verify_recovery(value)

    def test_links_or_public_object_permissions_are_rejected(self):
        for kind in ('symlink', 'hardlink', 'mode'):
            f = self.fresh(); path = f.bundle / 'objects' / next(iter(f.objects))
            if kind == 'mode': path.chmod(0o644)
            else:
                held = f.env.base / 'retained-object'; path.rename(held)
                if kind == 'symlink': path.symlink_to(held)
                else: os.link(held, path)
            with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_repinning_does_not_hide_unreferenced_or_missing_transaction_objects(self):
        for kind in ('extra', 'no-transaction'):
            f = self.fresh()
            if kind == 'extra': f.add(b'generated unreviewed object'); f.repin()
            else:
                f.index_value['transactions'] = []; f.repin(); f.reader = f.make_reader(transactions={})
            with self.assertRaises(ValueError): f.reader.verify_scope(f.manifest)

    def test_oversized_or_boolean_object_metadata_refused_before_provider(self):
        for size in (True, 64 * 1024 * 1024 + 1):
            f = self.fresh(); name = next(iter(f.objects)); f.objects[name]['bytes'] = size; f.repin()
            with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)
            self.assertFalse(f.provider.calls)

    def test_actual_prepared_bytes_or_original_metadata_drift_blocks(self):
        for kind in ('prepared', 'original-mode'):
            f = self.fresh(); e = f.env
            if kind == 'prepared': (e.directory / 'prepared/1').write_bytes(b'generated unexpected replacement')
            else: (e.directory / 'originals/profile.dat').chmod(0o600)
            with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_object_changed_during_remote_readback_is_not_verified(self):
        f = self.fresh(); path = f.bundle / 'objects' / next(iter(f.objects))
        f.provider.change = lambda: path.write_bytes(b'generated concurrent modification')
        with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_bundle_inside_restored_server_root_is_rejected(self):
        f = self.fresh(); inside = f.env.root / 'private-copy'; inside.mkdir(mode=0o700)
        reader = f.make_reader(directory=inside)
        with self.assertRaisesRegex(ValueError, 'survive server'): reader.verify_scope(f.manifest)

    def test_private_parent_permissions_are_rechecked_after_reader_construction(self):
        f = self.fresh(); f.env.base.chmod(0o755)
        with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)

    def test_sqlite_sidecar_reappearance_blocks_completed_journal_evidence(self):
        f = self.fresh(); (f.env.root / 'fixture.db-wal').write_bytes(b'generated pending database changes')
        with self.assertRaises(ValueError): f.reader.verify_recovery(f.manifest)


class ReadOnlyProvider(unittest.TestCase):
    def test_metadata_and_actual_bytes_required_without_any_write_command(self):
        provider = ReadOnlyDrive(); raw = b'generated recovery object'; name = hash_bytes(raw)
        row = {'Name': name, 'Size': len(raw), 'IsDir': False,
               'Hashes': {'MD5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}
        provider.command = Mock(side_effect=[encoded(row), raw])
        provider.verify('a' * 64, 'objects/' + name, raw)
        self.assertEqual([c.args[0] for c in provider.command.call_args_list], ['lsjson', 'cat'])
        provider.command = Mock(side_effect=[encoded(row), b'wrong'])
        with self.assertRaises(ValueError): provider.verify('a' * 64, 'objects/' + name, raw)

    def test_invalid_object_path_and_mutating_command_refused_before_subprocess(self):
        provider = ReadOnlyDrive()
        for name in ('../secret', 'objects/../secret', 'objects/not-a-hash'):
            with self.assertRaises(ValueError): provider.verify('a' * 64, name, b'generated')
        with self.assertRaises(ValueError): provider.command('copyto', 'anything', 'anything')

    def test_wrong_provider_metadata_is_rejected_before_content_request(self):
        raw = b'generated recovery object'; name = hash_bytes(raw)
        original = {'Name': name, 'Size': len(raw), 'IsDir': False,
                    'Hashes': {'MD5': hashlib.md5(raw, usedforsecurity=False).hexdigest()}}
        for change in ({'Size': 1}, {'IsDir': True}, {'Name': 'wrong'}, {'Hashes': {'MD5': '0' * 32}}):
            provider = ReadOnlyDrive(); provider.command = Mock(return_value=encoded(dict(original, **change)))
            with self.assertRaises(ValueError): provider.verify('a' * 64, 'objects/' + name, raw)
            self.assertEqual(provider.command.call_count, 1)


if __name__ == '__main__': unittest.main()
