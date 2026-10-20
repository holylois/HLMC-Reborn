"""Generated startup contexts only. Actual complete native registry is also checked in the combined harness."""
import os
import hashlib
import sqlite3
from contextlib import closing
import unittest
from unittest.mock import patch
from privacy_prestart import dispatch, reviewed_start
from test_privacy_actions import Environment
from test_privacy_bindings import states


class FixedStartup(unittest.TestCase):
    def fresh(self):
        e = Environment(); self.addCleanup(e.close); return e

    def test_empty_ledger_does_not_require_config_or_provider(self):
        from recovery_guard import Guard
        e = self.fresh(); root = e.base / 'empty'; (root / 'config').mkdir(parents=True)
        g = Guard(root, e.base / 'empty-guard'); g.initialize()
        run = lambda args, **kw: states(args, {'minecraft.service': {'ActiveState': 'activating',
            'SubState': 'start-pre', 'ControlPID': str(os.getpid()), 'InvocationID': 'a' * 32}})
        self.assertTrue(dispatch(g, e.base / 'missing', e.base / 'missing-pin', pid=os.getpid(),
                                 invocation='a' * 32, run=run)['allow_start'])

    def test_direct_invocation_or_wrong_control_process_is_not_prestart(self):
        e = self.fresh()
        for pid, invocation in ((0, ''), (os.getpid(), 'a' * 32)):
            with self.assertRaises(ValueError):
                dispatch(e.guard, e.base / 'missing', e.base / 'missing-pin', pid=pid, invocation=invocation,
                         run=lambda args, **kw: states(args))

    def test_nonempty_request_missing_pin_blocks_before_native_or_credential_reads(self):
        e = self.fresh(); before = e.guard.state()['generation']
        config = e.base / 'review.json'; config.write_bytes(b'{}'); config.chmod(0o600)
        pin = e.base / 'pin'; pin.write_bytes(b'a' * 64); pin.chmod(0o600)
        with patch('privacy_prestart.registry') as registry:
            with self.assertRaises(ValueError): reviewed_start(e.guard, config, pin, lambda: True)
            registry.assert_not_called()
        self.assertEqual(e.guard.state()['generation'], before)

    def test_nonempty_active_writer_never_enters_review(self):
        e = self.fresh()
        changes = {'minecraft.service': {'ActiveState': 'activating', 'SubState': 'start-pre',
            'ControlPID': str(os.getpid()), 'InvocationID': 'a' * 32},
            'holylois-discord-bot.service': {'ActiveState': 'active', 'MainPID': '42'}}
        with patch('privacy_prestart.reviewed_start') as start:
            # Exercise the same complete lease passed by dispatch, without accessing actual services.
            def check(*args, **kwargs):
                self.assertFalse(args[3]()); raise ValueError('Generated active writer')
            start.side_effect = check
            with self.assertRaises(ValueError):
                dispatch(e.guard, e.base / 'missing', e.base / 'missing-pin', pid=os.getpid(),
                         invocation='a' * 32, run=lambda args, **kw: states(args, changes))

    def test_vendored_helpers_exclude_historical_sqlite_ledger(self):
        from privacy_native import restore_ledger
        self.assertFalse(hasattr(restore_ledger, 'Ledger'))

    def test_actual_packaged_native_registry_reads_generated_auth_and_refuses_returned_account(self):
        from privacy_prestart import registry
        from privacy_native.runtime_guard import REQUIRED, RuntimePins
        from privacy_review import STORES
        e = self.fresh(); (e.root / 'world').mkdir(); (e.root / 'mods').mkdir()
        mod = e.root / 'mods/fixture.jar'; mod.write_bytes(b'generated mod')
        code = e.base / 'public-source'; code.write_bytes(b'generated public source')
        sources = {k: {'path': str(code), 'sha256': hashlib.sha256(code.read_bytes()).hexdigest()} for k in REQUIRED}
        database = e.root / 'generated-native.db'
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('CREATE TABLE accounts(id INTEGER PRIMARY KEY,username TEXT,username_lower TEXT,uuid TEXT,last_ip TEXT,data TEXT)')
        channel, guild, message = '12345678901234567', '22345678901234567', '32345678901234567'
        visible = 'generated visibility probe'
        def get(path):
            if path == '/channels/' + channel + '/messages/' + message: return {'content': visible}
            if path == '/guilds/' + guild + '/channels': return [{'id': channel, 'type': 0}]
            if path.endswith('/threads/active'): return {'threads': []}
            if '/threads/archived/' in path: return {'threads': [], 'has_more': False}
            if '/messages?' in path: return []
            raise ValueError('Unknown generated route')
        outside = {}
        for name in ('stats', 'weekly'):
            path = e.base / (name + '.json'); path.write_bytes(b'{"players":[]}'); outside[name] = str(path)
        cfg = {'root': str(e.root), 'sources': sources, 'mods': {mod.name: hashlib.sha256(mod.read_bytes()).hexdigest()},
            'native': {'auth_path': str(database), 'auth_table': 'accounts', 'public_paths': ['exports'],
                'world_paths': ['dimensions'], 'outside_exports': outside,
                'http_urls': ['https://stats.holylois.com/stats.json'], 'audit_path': str(e.root / 'missing-audit.db'),
                'discord': {'guild': guild, 'channels': [channel], 'canary': [channel, message],
                            'content_sha256': hashlib.sha256(visible.encode()).hexdigest(), 'max_pages': 2}}}
        adapters = registry(cfg, lambda: True, discord_get=get, http_get=lambda url: b'{"players":[]}')
        request = dict(e.cases[0], discord_ids=['42345678901234567'])
        self.assertEqual(set(adapters), STORES)
        self.assertTrue(all(a.verify(request)['absent'] for a in adapters.values()))
        with closing(sqlite3.connect(database)) as db, db:
            db.execute('INSERT INTO accounts VALUES(1,?,?,?,?,?)',
                       ('FixtureUser', 'fixtureuser', request['subject'], None, '{"onlineAccount":"TRUE"}'))
        self.assertFalse(adapters['authentication'].verify(request)['absent'])
        pins = RuntimePins(sources, {'directory': str(mod.parent), 'files': cfg['mods']})
        pins.check(); self.assertEqual(len(pins.cache), 2)
        code.write_bytes(b'changed generated code')
        with self.assertRaises(ValueError): pins.check()


if __name__ == '__main__': unittest.main()
