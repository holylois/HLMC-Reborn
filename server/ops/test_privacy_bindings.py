"""Synthetic code pins and systemctl responses only. No real service calls or account reads."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from privacy_bindings import Bindings, SOURCES, SERVICES, TIMERS, service_lease
from privacy_review import STORES


class NativeBindings(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup); self.base = Path(t.name).resolve()
        self.root = self.base / 'server'; (self.root / 'mods').mkdir(parents=True)
        self.raw = b'generated public mod fixture'; (self.root / 'mods/fixture.jar').write_bytes(self.raw)
        self.mods = {'fixture.jar': hashlib.sha256(self.raw).hexdigest()}; self.sources = {}
        for label in SOURCES:
            p = self.base / (label + '.py'); p.write_bytes(('generated code ' + label).encode())
            self.sources[label] = {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
        self.adapters = {store: SimpleNamespace(verify=Mock()) for store in STORES}

    def bindings(self): return Bindings(self.root, self.mods, self.sources, self.adapters, 'a' * 64)

    def test_complete_inventory_checks_no_account_data_or_adapters(self):
        bound = self.bindings(); before = bound.check(); self.assertEqual(bound.check(), before)
        self.assertEqual(len(before), 64)
        for a in self.adapters.values(): a.verify.assert_not_called()

    def test_new_mod_and_changed_cached_code_require_review(self):
        bound = self.bindings(); bound.check()
        p = self.root / 'mods/unknown.jar'; p.write_bytes(b'new data store')
        with self.assertRaises(ValueError): bound.check()
        p.rename(self.base / 'held-new-code')
        Path(self.sources['support-registry']['path']).write_bytes(b'changed support schema')
        with self.assertRaises(ValueError): bound.check()

    def test_missing_required_source_or_verifier_is_not_complete_binding(self):
        self.sources.pop('exports')
        with self.assertRaises(ValueError): self.bindings()
        self.setUp(); self.adapters.pop('discord')
        with self.assertRaises(ValueError): self.bindings()

    def test_links_to_unreviewed_code_are_rejected(self):
        source = Path(self.sources['routine']['path']); source.rename(self.base / 'held-code')
        source.symlink_to(self.base / 'held-code')
        with self.assertRaises(ValueError): self.bindings()


class Leases(unittest.TestCase):
    def test_every_known_writer_and_trigger_must_be_loaded_and_stopped(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args[2]); return SimpleNamespace(stdout='LoadState=loaded\nActiveState=inactive\nMainPID=0\nControlPID=0\n')
        self.assertTrue(service_lease(run)); self.assertEqual(len(calls), len(SERVICES) + len(TIMERS))
        self.assertIn('holylois-weekly-recap.timer', calls); self.assertIn('holylois-discord-bot.service', calls)
        self.assertIn('holylois-thread-guard.timer', calls); self.assertIn('holylois-offsite-backup.service', calls)

    def test_enabled_timer_or_live_writer_or_missing_unit_refuses_lease(self):
        for unit, field in (('holylois-stats.timer', 'ActiveState=active'),
                            ('holylois-discord-bot.service', 'MainPID=1'),
                            ('holylois-weekly-recap.service', 'ControlPID=1'),
                            ('holylois-thread-guard.timer', 'ActiveState=active'),
                            ('holylois-thread-guard.service', 'ControlPID=1'),
                            ('holylois-offsite-backup.timer', 'ActiveState=active'),
                            ('holylois-offsite-backup.service', 'MainPID=1'),
                            ('holylois-log-retention.service', 'LoadState=not-found')):
            def run(args, **kwargs):
                values = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'MainPID': '0', 'ControlPID': '0'}
                if args[2] == unit:
                    key, value = field.split('='); values[key] = value
                return SimpleNamespace(stdout='\n'.join(k + '=' + v for k, v in values.items()))
            self.assertFalse(service_lease(run))


if __name__ == '__main__': unittest.main()
