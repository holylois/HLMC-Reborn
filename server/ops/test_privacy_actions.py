"""Generated files only. No actual accounts, auth databases, provider or service changes."""
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from privacy_actions import Plan, file, OBLIGATIONS
from privacy_review import STORES, digest
from privacy_exports import encoded, gate_bytes
from recovery_guard import Guard
from guard_checkpoint import checkpoint
from test_guard_checkpoint import Provider


class Environment:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'game'; (self.root / 'config').mkdir(parents=True)
        public = self.base / 'public'; public.mkdir(mode=0o755); self.gate = public / 'privacy-gate.json'
        self.gate.write_bytes(encoded({'schema': 1, 'epoch': str(uuid.uuid4()), 'ready': False, 'policy_sha256': None}))
        self.guard = Guard(self.root, self.base / 'guard', export_gate=self.gate); self.guard.initialize()
        subject, request = str(uuid.uuid4()), str(uuid.uuid4()); self.guard.record_request(request, subject)
        self.cases = [{'id': request, 'subject': subject, 'related_subjects': [subject], 'aliases': ['fixtureuser'],
                       'discord_ids': [], 'identity_proof_sha256': 'a' * 64}]
        self.checkpoints = self.base / 'checkpoints'; self.checkpoints.mkdir(mode=0o700)
        self.provider = Provider(); checkpoint(self.guard, self.checkpoints, self.provider)
        self.before = {'profile.dat': b'generated original profile', 'balances.json': b'{"target":5,"other":7}',
                       'fixture.db': b'generated stopped database fixture'}
        self.after = {'profile.dat': None, 'balances.json': b'{"other":7}', 'fixture.db': b'generated replacement database fixture'}
        stores = ['profiles', 'economy', 'authentication']; self.actions = []
        for (name, raw), store in zip(self.before.items(), stores):
            p = self.root / name; p.write_bytes(raw); p.chmod(0o640)
            self.actions.append({'relative': name, 'store': store, 'before': file(p), 'replacement': self.after[name]})
        self.reviews = {s: {'decision': 'verify-only', 'evidence_sha256': 'b' * 64} for s in STORES | OBLIGATIONS}
        for store in stores: self.reviews[store]['decision'] = 'change'
        self.lease = True; self.runtime = 'c' * 64; self.backup = True
        self.plan = self.make_plan(); self.approval = digest(self.plan.description()); self.directory = self.base / 'transaction'
        self.case_proof = True; self.protected_manifest = digest(self.plan.protection_manifest(self.cases))

    def close(self): self.temp.cleanup()
    def make_plan(self, reviews=None):
        return Plan(self.root, self.actions, digest(self.cases), 'c' * 64, 'd' * 64, reviews or self.reviews)
    def run(self, **options):
        return self.plan.run(self.guard, self.cases, self.directory, self.approval, lambda: self.lease,
                             lambda: self.runtime, lambda digest: self.backup and digest == 'd' * 64,
                             self.checkpoints, self.provider,
                             verified_case_plan=lambda manifest: self.case_proof and digest(manifest) == self.protected_manifest,
                             **options)
    def original_state(self):
        return {name: (self.root / name).read_bytes() if (self.root / name).exists() else None for name in self.before}


class Actions(unittest.TestCase):
    def fresh(self):
        e = Environment(); self.addCleanup(e.close); return e

    def test_exact_actions_retain_originals_and_never_release_guard(self):
        e = self.fresh(); result = e.run()
        self.assertEqual(e.original_state(), e.after)
        for name, raw in e.before.items(): self.assertEqual((e.directory / 'originals' / name).read_bytes(), raw)
        self.assertFalse(result['final_erasure']); self.assertFalse(result['allow_start'])
        self.assertFalse(gate_bytes(e.gate, os.geteuid())[1]['ready'])
        with self.assertRaises(ValueError): e.guard.start()

    def test_resume_after_every_durable_action_boundary(self):
        for stage in ('moved', 'replacement-ready', 'replaced', 'journal'):
            with self.subTest(stage=stage):
                e = self.fresh(); hit = []
                def crash(current, index):
                    if current == stage and not hit: hit.append(True); raise OSError('Generated crash')
                with self.assertRaises(OSError): e.run(boundary=crash)
                self.assertTrue(hit); self.assertEqual(json.loads((e.directory / 'journal.json').read_text())['status'], 'pending')
                e.plan = Plan.from_journal(e.directory)  # Reconstruct from disk, with no retained replacement bytes in memory.
                e.run(); self.assertEqual(e.original_state(), e.after)
                e.run(); self.assertEqual(e.original_state(), e.after)  # Idempotent completed readback.

    def test_undo_resumes_and_retains_replacements(self):
        for stage in ('undo-replacement', 'undo-original', 'journal'):
            with self.subTest(stage=stage):
                e = self.fresh(); e.run(); hit = []
                def crash(current, index):
                    if current == stage and not hit: hit.append(True); raise OSError('Generated undo crash')
                with self.assertRaises(OSError): e.run(undo=True, boundary=crash)
                e.run(undo=True); self.assertEqual(e.original_state(), e.before)
                for index, name in enumerate(e.before):
                    if e.after[name] is not None:
                        self.assertEqual((e.directory / 'replacements' / str(index)).read_bytes(), e.after[name])
                with self.assertRaises(ValueError): e.run()
                with self.assertRaises(ValueError): e.guard.start()

    def test_unexpected_change_before_resume_moves_nothing_further(self):
        e = self.fresh()
        def crash(stage, index):
            if stage == 'moved': raise OSError('Generated interruption')
        with self.assertRaises(OSError): e.run(boundary=crash)
        (e.root / 'fixture.db').write_bytes(b'new independent data')
        before = e.original_state()
        with self.assertRaises(ValueError): e.run()
        self.assertEqual(e.original_state(), before)
        self.assertEqual((e.directory / 'originals/profile.dat').read_bytes(), e.before['profile.dat'])

    def test_writer_resume_mid_action_stops_before_replacement_install(self):
        e = self.fresh()
        def resumed(stage, index):
            if stage == 'replacement-ready': e.lease = False
        with self.assertRaises(ValueError): e.run(boundary=resumed)
        self.assertFalse((e.root / 'balances.json').exists())
        e.lease = True; e.run(); self.assertEqual(e.original_state(), e.after)

    def test_writer_change_at_last_boundary_keeps_journal_pending(self):
        e = self.fresh()
        def resumed(stage, index):
            if stage == 'journal' and index == len(e.actions) - 1: e.lease = False
        with self.assertRaises(ValueError): e.run(boundary=resumed)
        self.assertEqual(json.loads((e.directory / 'journal.json').read_text())['status'], 'pending')
        e.lease = True; e.run(); self.assertEqual(e.original_state(), e.after)

    def test_new_request_during_offsite_proof_preserves_request_and_stops_actions(self):
        e = self.fresh()
        e.provider.change = lambda: e.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        with self.assertRaises(ValueError): e.run()
        self.assertFalse(e.directory.exists()); self.assertEqual(e.original_state(), e.before)
        self.assertEqual(len(e.guard.state()['requests']), 2)

    def test_required_approval_runtime_backup_lease_and_provider_proof(self):
        for kind in ('approval', 'runtime', 'backup', 'lease', 'provider', 'case-proof'):
            with self.subTest(kind=kind):
                e = self.fresh()
                if kind == 'approval': e.approval = '0' * 64
                if kind == 'runtime': e.runtime = 'e' * 64
                if kind == 'backup': e.backup = False
                if kind == 'lease': e.lease = False
                if kind == 'provider': e.provider.fail = True
                if kind == 'case-proof': e.case_proof = False
                with self.assertRaises((ValueError, OSError)): e.run()
                self.assertFalse(e.directory.exists()); self.assertEqual(e.original_state(), e.before)

    def test_every_review_and_resolved_hold_required(self):
        e = self.fresh()
        for scope in STORES | OBLIGATIONS:
            reviews = json.loads(json.dumps(e.reviews)); reviews.pop(scope)
            with self.assertRaises(ValueError): e.make_plan(reviews)
        reviews = json.loads(json.dumps(e.reviews)); reviews['support-moderation']['decision'] = 'held'
        e.plan = e.make_plan(reviews); e.approval = digest(e.plan.description())
        with self.assertRaises(ValueError): e.run()
        self.assertFalse(e.directory.exists())

    def test_sqlite_sidecar_blocks_all_actions(self):
        e = self.fresh(); (e.root / 'fixture.db-wal').write_bytes(b'generated unfinished writes')
        with self.assertRaises(ValueError): e.run()
        self.assertEqual(e.original_state(), e.before); self.assertFalse(e.directory.exists())

    def test_missing_original_and_changed_undo_replacement_refuse_guessing(self):
        e = self.fresh(); e.run()
        (e.root / 'balances.json').write_bytes(b'changed after application')
        before = e.original_state()
        with self.assertRaises(ValueError): e.run(undo=True)
        self.assertEqual(e.original_state(), before)

    def test_corrupt_prepared_bytes_cannot_reconstruct_or_resume(self):
        e = self.fresh(); e.run()
        (e.directory / 'prepared/1').write_bytes(b'changed durable proposal')
        with self.assertRaises(ValueError): Plan.from_journal(e.directory)
        before = e.original_state()
        with self.assertRaises(ValueError): e.run()
        self.assertEqual(e.original_state(), before)

    def test_missing_original_evidence_cannot_be_replaced_by_completion_flag(self):
        e = self.fresh(); e.run()
        (e.directory / 'originals/fixture.db').rename(e.base / 'held-original-evidence')
        with self.assertRaises(ValueError): e.run()
        self.assertEqual(e.original_state(), e.after)

    def test_path_escape_links_and_metadata_drift_are_rejected(self):
        e = self.fresh(); (e.root / 'balances.json').chmod(0o600)
        with self.assertRaises(ValueError): e.run()
        e.actions[0]['relative'] = '../escape'
        with self.assertRaises(ValueError): e.make_plan()
        linked = e.root / 'linked'; linked.symlink_to(e.root / 'fixture.db')
        with self.assertRaises(ValueError): file(linked)

    def test_unexpected_destination_is_never_overwritten_during_apply_or_undo(self):
        for undo in (False, True):
            with self.subTest(undo=undo):
                e = self.fresh()
                if undo: e.run()
                stage = 'undo-replacement' if undo else 'replacement-ready'
                created = []
                def appeared(current, index):
                    if current == stage and not created:
                        name = e.actions[index]['relative']; (e.root / name).write_bytes(b'independent new data')
                        created.append(name)
                with self.assertRaises(OSError): e.run(undo=undo, boundary=appeared)
                self.assertEqual((e.root / created[0]).read_bytes(), b'independent new data')
                self.assertEqual((e.directory / 'originals' / created[0]).read_bytes(), e.before[created[0]])


if __name__ == '__main__': unittest.main()
