"""Generated identities, mocked provider and real loopback HTTP. Never uses live accounts or Discord."""
import importlib.util
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import uuid
from pathlib import Path
from unittest.mock import Mock, patch
from recovery_guard import Guard
from guard_checkpoint import checkpoint
from privacy_exports import plan, publish, load, gate_bytes, encoded
from privacy_review import digest
from test_guard_checkpoint import Provider

HERE = Path(__file__).resolve().parent
NAME = 'FixtureUser'; RENAMED = 'RenamedFixture'; OTHER = 'OtherFixture'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


class Exports(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); self.game = self.root / 'game'
        (self.game / 'config').mkdir(parents=True)
        self.web = self.root / 'public'; self.web.mkdir(mode=0o755)
        self.gate = self.web / 'privacy-gate.json'
        self.gate.write_bytes(encoded({'schema': 1, 'epoch': str(uuid.uuid4()), 'ready': False, 'policy_sha256': None}))
        self.guard = Guard(self.game, self.root / 'guard', export_gate=self.gate); self.guard.initialize()
        self.base = self.root / 'checkpoints'; self.base.mkdir(mode=0o700)
        private = self.root / 'policy'; private.mkdir(mode=0o700); self.policy = private / 'policy.json'
        self.provider = Provider(); self.subject = str(uuid.uuid4()); self.other = str(uuid.uuid4()); self.request = str(uuid.uuid4())
        self.cases = []
        self.stats = module('generated_stats', HERE.parent / 'stats/make-stats.py')
        self.weekly = module('generated_weekly', HERE / 'weekly-recap.py')
        self.http = module('generated_stats_http', HERE.parent / 'stats/stats-web.py')
        self.http.GATE = self.gate; self.http.GATE_OWNER = os.geteuid()
        self.http.FILE = self.web / 'stats.json'; self.http.TAKEN = self.web / 'taken-names.json'
        self.http.CONTROL = self.web / 'privacy-control.json'
        for mod in (self.stats, self.weekly):
            mod.ROOT = self.game; mod.WORLD = self.game / 'world'; mod.POLICY = self.policy
            mod.Guard = lambda: self.guard
        self.stats.OUT = self.http.FILE; self.stats.HIDDEN_FILE = self.root / 'hidden'
        self.stats.HIDDEN_CONFIG = self.game / 'config/hidden.json'
        self.stats.online_now = lambda: 0
        self.weekly.STATS = self.game / 'world/players/stats'; self.weekly.USERS = self.game / 'usercache.json'
        self.weekly.AFK = self.game / 'world/holylois/afk.json'; self.weekly.DISCOVERIES = self.game / 'world/holylois/discoveries.json'
        self.weekly.SNAPSHOT = self.root / 'weekly.json'
        self.alert = Mock(); self.alert.GOLD = 0
        self.weekly.module = lambda name, path: self.stats if name == 'stats' else self.alert
        self.seed()

    def seed(self):
        self.write('usercache.json', [{'uuid': self.subject, 'name': RENAMED}, {'uuid': self.other, 'name': OTHER}])
        for subject in (self.subject, self.other):
            self.write('world/players/stats/' + subject + '.json', {'stats': {'minecraft:custom': {'minecraft:play_time': 720000, 'minecraft:mob_kills': 9}}})
        self.write('world/holylois/account-profile-names.json', {'names': {self.subject: RENAMED, self.other: OTHER},
                                                            'aliases': {NAME.lower(): self.subject, RENAMED.lower(): self.subject}})
        self.write('world/holylois/discoveries.json', {'found': [{'name': 'Fixture Tower', 'first': True, 'player': RENAMED,
                                                               'uuid': self.subject, 'time': 9999999999}], 'firsts': []})

    def write(self, name, value):
        p = self.game / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(value)); return p

    def record(self):
        self.guard.record_request(self.request, self.subject)
        self.cases = [{'id': self.request, 'subject': self.subject, 'related_subjects': [self.subject],
                       'aliases': [NAME.lower()], 'discord_ids': [], 'identity_proof_sha256': 'a' * 64}]

    def activate(self):
        checkpoint(self.guard, self.base, self.provider)
        approved = digest(plan(self.guard, self.cases))
        return publish(self.guard, self.cases, self.policy, self.base, self.provider, approved, lambda: True)

    def test_private_umask_preserves_public_gate_readability_and_private_state_modes(self):
        import stat
        prior = os.umask(0o077)
        try:
            self.activate()
            self.assertEqual(stat.S_IMODE(self.gate.stat().st_mode), 0o644)
            for path in (self.policy, self.guard.directory / 'ledger.json', self.guard.directory / 'subject-key.json'):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.record()
            self.assertEqual(stat.S_IMODE(self.gate.stat().st_mode), 0o644)
            self.assertFalse(gate_bytes(self.gate, os.geteuid())[1]['ready'])
        finally: os.umask(prior)

    def generate(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.stats.urllib.request, 'urlopen', side_effect=OSError('No external feed in generated proof')):
            self.stats.main()

    def test_actual_stats_and_taken_names_hide_renamed_uuid_after_old_data_restore(self):
        self.record(); result = self.activate(); self.generate()
        self.assertFalse(result['allow_start']); self.assertFalse(result['erasure_authorized'])
        text = self.http.FILE.read_text(); self.assertNotIn(NAME, text); self.assertNotIn(RENAMED.lower(), text.lower())
        self.assertIn(OTHER.lower(), text.lower())
        names = json.loads(self.http.TAKEN.read_text())
        self.assertNotIn(RENAMED.lower(), names['names']); self.assertIn(RENAMED.lower(), names['withheld'])
        self.seed(); self.generate()  # Old world files return; outside suppression remains.
        self.assertNotIn(RENAMED, self.http.FILE.read_text())
        self.assertEqual(json.loads(self.http.FILE.read_text())['server']['registered_players'], 1)
        with self.assertRaises(ValueError): self.guard.start()

    def test_legacy_discovery_name_is_filtered_from_current_uuid_alias_mapping(self):
        self.record(); self.activate()
        self.write('world/holylois/discoveries.json', {'found': [{'name': 'Legacy Tower', 'player': RENAMED,
                                                                'first': True, 'time': 9999999999}], 'firsts': []})
        self.generate()
        self.assertEqual(json.loads(self.http.FILE.read_text())['world_firsts'], [])

    def test_actual_weekly_snapshot_and_posts_do_not_reintroduce_suppressed_account(self):
        self.record(); self.activate()
        self.weekly.SNAPSHOT.write_text(json.dumps({'time': 0, 'players': {NAME: {'hours': 1}, RENAMED: {'hours': 1}}}))
        with contextlib.redirect_stdout(io.StringIO()): self.weekly.main()
        saved = self.weekly.SNAPSHOT.read_text(); self.assertNotIn(RENAMED, saved); self.assertNotIn(NAME, saved)
        self.assertEqual(self.weekly.SNAPSHOT.stat().st_mode & 0o777, 0o600)
        self.alert.post.assert_called_once()
        self.assertNotIn(RENAMED, str(self.alert.post.call_args)); self.assertNotIn('Fixture Tower', str(self.alert.post.call_args))

    def test_new_request_blocks_old_http_bytes_before_new_export_can_be_generated(self):
        self.activate(); self.generate(); self.assertTrue(gate_bytes(self.gate, os.geteuid())[1]['ready'])
        self.record()
        self.assertFalse(gate_bytes(self.gate, os.geteuid())[1]['ready'])
        with self.assertRaises(ValueError): self.http.protected_body(self.http.FILE, 'stats')
        before = self.http.FILE.read_bytes()
        with self.assertRaises(ValueError): self.generate()
        self.assertEqual(self.http.FILE.read_bytes(), before)
        with self.assertRaises(ValueError): self.weekly.main()
        self.alert.post.assert_not_called()

    def test_restoration_blocks_serving_and_old_epoch_stays_blocked_after_completion(self):
        self.activate(); self.generate(); self.guard.begin_restore(str(uuid.uuid4()))
        pending = self.guard.state()['pending_restore']
        with self.assertRaises(ValueError): self.http.protected_body(self.http.FILE, 'stats')
        self.guard.complete_restore(pending)
        with self.assertRaises(ValueError): load(self.guard, self.policy)
        self.activate()  # Trusted generated empty restore, then create output for new epoch.
        with self.assertRaises(ValueError): self.http.protected_body(self.http.FILE, 'stats')
        self.generate(); self.assertTrue(self.http.protected_body(self.http.FILE, 'stats'))

    def test_corrupt_missing_policy_and_gate_fail_closed(self):
        self.record(); self.activate(); self.generate()
        self.policy.write_text('{}')
        with self.assertRaises(ValueError): self.generate()
        self.gate.unlink()
        with self.assertRaises(FileNotFoundError): self.http.protected_body(self.http.FILE, 'stats')
        before = (self.guard.directory / 'ledger.json').read_bytes()
        with self.assertRaises(FileNotFoundError): self.guard.record_request(str(uuid.uuid4()), str(uuid.uuid4()))
        self.assertEqual((self.guard.directory / 'ledger.json').read_bytes(), before)

    def test_readback_failure_and_wrong_approval_cannot_open_gate(self):
        self.record(); checkpoint(self.guard, self.base, self.provider)
        for approval in ('b' * 64, digest(plan(self.guard, self.cases))):
            self.provider.fail = True
            with self.assertRaises((ValueError, OSError)):
                publish(self.guard, self.cases, self.policy, self.base, self.provider, approval, lambda: True)
            self.assertFalse(gate_bytes(self.gate, os.geteuid())[1]['ready'])
            self.assertFalse(self.policy.exists())

    def test_loopback_http_serves_only_current_bytes_and_refuses_stale_cache(self):
        self.record(); self.activate(); self.generate()
        server = self.http.ThreadingHTTPServer(('127.0.0.1', 0), self.http.Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            url = 'http://127.0.0.1:' + str(server.server_port)
            with urllib.request.urlopen(url + '/stats.json') as response:
                body = response.read(); self.assertNotIn(RENAMED.encode(), body)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
            with self.assertRaises(urllib.error.HTTPError) as held:
                urllib.request.urlopen(url + '/name/' + RENAMED)
            self.assertEqual(held.exception.code, 503); held.exception.close()
            with urllib.request.urlopen(url + '/name/' + OTHER) as response:
                self.assertTrue(json.loads(response.read())['taken'])
            self.guard.record_request(str(uuid.uuid4()), self.other)
            for suffix in ('/stats.json', '/name/' + OTHER):
                with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(url + suffix)
                self.assertEqual(caught.exception.code, 503); caught.exception.close()
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_changed_body_or_control_cannot_be_served_under_old_success(self):
        self.record(); self.activate(); self.generate()
        self.http.FILE.write_text('{"unreviewed":"FixtureUser"}')
        with self.assertRaises(ValueError): self.http.protected_body(self.http.FILE, 'stats')
        self.http.CONTROL.write_text('{}')
        with self.assertRaises(ValueError): self.http.protected_body(self.http.TAKEN, 'taken')

    def test_interrupted_request_write_leaves_serving_closed(self):
        self.activate(); self.generate()
        atomic = self.guard._atomic
        def fail_ledger(path, value, mode=0o600):
            if path.name == 'ledger.json': raise OSError('Generated interruption')
            atomic(path, value, mode)
        with patch.object(self.guard, '_atomic', fail_ledger), self.assertRaises(OSError): self.record()
        self.assertEqual(self.guard.state()['requests'], [])
        self.assertFalse(gate_bytes(self.gate, os.geteuid())[1]['ready'])
        with self.assertRaises(ValueError): self.http.protected_body(self.http.FILE, 'stats')

    def test_case_mismatch_and_active_writers_cannot_publish_policy(self):
        self.record(); checkpoint(self.guard, self.base, self.provider)
        approved = digest(plan(self.guard, self.cases))
        with self.assertRaises(ValueError):
            publish(self.guard, self.cases, self.policy, self.base, self.provider, approved, lambda: False)
        with self.assertRaises(ValueError): plan(self.guard, [])
        self.assertFalse(self.policy.exists()); self.assertFalse(gate_bytes(self.gate, os.geteuid())[1]['ready'])


if __name__ == '__main__': unittest.main()
