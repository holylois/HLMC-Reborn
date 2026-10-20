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


def states(args, changes=None):
    changes = {} if changes is None else changes
    rows = []
    for unit in args[2:args.index('-p')]:
        value = {'Id': unit, 'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead',
                 'MainPID': '0', 'ControlPID': '0', 'InvocationID': ''}
        value.update(changes.get(unit, {}))
        rows.append('\n'.join(k + '=' + v for k, v in value.items()))
    return SimpleNamespace(stdout='\n\n'.join(rows) + '\n')


class Leases(unittest.TestCase):
    def test_all_writers_and_timers_observed_in_one_call(self):
        calls = []
        def run(args, **kwargs): calls.append(args); return states(args)
        self.assertTrue(service_lease(run)); self.assertEqual(len(calls), 1)
        units = calls[0][2:calls[0].index('-p')]
        self.assertEqual(set(units), {u + '.service' for u in SERVICES} | {u + '.timer' for u in TIMERS})

    def test_each_enabled_timer_live_writer_or_missing_unit_refuses(self):
        for unit, change in [('holylois-stats.timer', {'ActiveState': 'active'}),
                ('holylois-discord-bot.service', {'MainPID': '1'}),
                ('holylois-weekly-recap.service', {'ControlPID': '1'}),
                ('holylois-thread-guard.timer', {'ActiveState': 'active'}),
                ('holylois-offsite-backup.service', {'MainPID': '1'}),
                ('holylois-log-retention.service', {'LoadState': 'not-found'})]:
            self.assertFalse(service_lease(lambda args, **kw: states(args, {unit: change})))

    def test_only_exact_own_activating_invocation_is_allowed(self):
        expected = {'ActiveState': 'activating', 'SubState': 'start-pre', 'ControlPID': '123', 'InvocationID': 'a' * 32}
        run = lambda args, **kw: states(args, {'minecraft.service': expected})
        self.assertFalse(service_lease(run))
        self.assertTrue(service_lease(run, prestart=('minecraft.service', 123, 'a' * 32)))
        for change in ({'SubState': 'start'}, {'MainPID': '12'}, {'ControlPID': '124'},
                       {'InvocationID': 'b' * 32}, {'ActiveState': 'active'}):
            run = lambda args, **kw: states(args, {'minecraft.service': dict(expected, **change)})
            self.assertFalse(service_lease(run, prestart=('minecraft.service', 123, 'a' * 32)))

    def test_missing_duplicate_and_unexpected_observation_blocks(self):
        for mode in ('missing', 'duplicate', 'unexpected'):
            def run(args, **kw):
                raw = states(args).stdout; blocks = raw.strip().split('\n\n')
                if mode == 'missing': blocks.pop()
                elif mode == 'duplicate': blocks.append(blocks[0])
                else: blocks[0] = blocks[0].replace('Id=minecraft.service', 'Id=other.service')
                return SimpleNamespace(stdout='\n\n'.join(blocks))
            with self.assertRaises(ValueError): service_lease(run)


if __name__ == '__main__': unittest.main()
