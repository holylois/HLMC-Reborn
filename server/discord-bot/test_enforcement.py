import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace as NS
import unittest
from enforcement import ClosedLogs, Journal, apply, digest
from providers import support_plan, TrackedSupport
from routine import logs, support, load_policy
from support_registry import Registry

NOW = '2026-10-14T16:00:00+00:00'
OLD = '2026-01-01T00:00:00+00:00'
RECENT = '2026-10-13T00:00:00+00:00'

class Fixture(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name).resolve()
        self.registry = Registry(self.root/'registry.sqlite')
        self.audit = self.root/'audit.jsonl'
    def tearDown(self): self.temp.cleanup()
    def request(self, key='10', category='routine', resolved=OLD):
        self.registry.received(key, '20', OLD, category)
        if resolved: self.registry.resolve(key, '20', resolved)
    def channel(self, replies=()):
        messages = {}
        for key in ('10', *replies):
            messages[int(key)] = NS(id=int(key), channel=NS(id=20), author=NS(id=30),
                                   reference=NS(message_id=10), edited_at=None)
        channel = NS(id=20)
        async def fetch(key):
            if key not in messages:
                error = RuntimeError('synthetic absent'); error.status=404; raise error
            return messages[key]
        channel.fetch_message = fetch
        for key, message in list(messages.items()):
            async def delete(key=key): messages.pop(key)
            message.delete = delete
        return channel, messages
    async def test_default_policy_and_runner_do_nothing(self):
        self.assertFalse(load_policy(self.root/'missing')['logs_enabled'])
        self.assertEqual(await logs({}, root=self.root), {'enabled':False,'removed':0})
    async def test_support_expiry_verifies_absence_then_removes_metadata(self):
        self.request(); self.registry.reply('11','20','10',OLD)
        channel, messages = self.channel(('11',))
        result = await support(self.registry,channel,30,{'support_enabled':True,'support_channel':'20'},NOW,self.audit)
        self.assertEqual(result['removed_this_run'],2)
        self.assertFalse(messages); self.assertIsNone(self.registry.snapshot('10'))
        self.assertNotIn('10', self.audit.read_text().split('operation')[0])
    async def test_reports_legacy_unresolved_recent_and_holds_protected(self):
        self.request('1','case'); self.request('2','legacy-review'); self.request('3',resolved=None)
        self.request('4',resolved=RECENT); self.request('5'); self.registry.hold('5','20',True)
        self.assertEqual(support_plan(self.registry,20,NOW)['entries'],[])
    async def test_new_reply_invalidates_whole_plan_before_removal(self):
        self.request(); channel,messages=self.channel()
        plan=support_plan(self.registry,20,NOW)
        self.registry.reply('12','20','10',RECENT)
        with self.assertRaises(ValueError): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
        self.assertIn(10,messages)
    async def test_edit_and_hold_invalidate_plan(self):
        for change in ('edit','hold'):
            self.registry = Registry(self.root/(change+'.sqlite')); self.request()
            plan=support_plan(self.registry,20,NOW); channel,_=self.channel()
            if change=='edit': self.registry.touch_message('10','20',RECENT)
            else: self.registry.hold('10','20',True)
            with self.assertRaises(ValueError): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
    async def test_untracked_provider_edit_foreign_root_and_permission_failure(self):
        self.request(); plan=support_plan(self.registry,20,NOW)
        for cause in ('edit','author','permission'):
            channel,messages=self.channel()
            if cause=='edit': messages[10].edited_at=datetime.fromisoformat(RECENT)
            elif cause=='author': messages[10].author.id=999
            else:
                async def forbidden(key):
                    error=RuntimeError('synthetic forbidden'); error.status=403; raise error
                channel.fetch_message=forbidden
            with self.assertRaises((ValueError,RuntimeError)): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
            self.assertIn(10,messages)
    async def test_wrong_channel_refused(self):
        self.request(); channel,_=self.channel()
        with self.assertRaises(ValueError): await support(self.registry,channel,30,{'support_enabled':True,'support_channel':'999'},NOW,self.audit)
    async def test_registry_migration_holds_existing_rows(self):
        file=self.root/'old.sqlite'
        with sqlite3.connect(file) as db:
            db.executescript("CREATE TABLE requests(id TEXT PRIMARY KEY,channel TEXT NOT NULL,created TEXT NOT NULL,resolved TEXT,activity TEXT NOT NULL,held INTEGER NOT NULL DEFAULT 0); CREATE TABLE messages(id TEXT PRIMARY KEY,request TEXT NOT NULL,channel TEXT NOT NULL);")
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,0)',('10','20',OLD,OLD,OLD))
            db.execute('INSERT INTO messages VALUES(?,?,?)',('10','10','20'))
        snapshot=Registry(file).snapshot('10')
        self.assertTrue(snapshot['held']); self.assertEqual(snapshot['retention_class'],'legacy-review')
    def old_log(self,name='2026-01-01-1.log.gz'):
        path=self.root/name; path.write_bytes(b'synthetic compressed archive')
        stamp=datetime.fromisoformat(OLD).timestamp(); os.utime(path,(stamp,stamp)); return path
    async def test_log_scope_preserves_latest_unknown_recent_and_hold(self):
        self.old_log(); self.old_log('2026-01-02-1.log.gz'); self.old_log('latest.log')
        self.old_log('2026-10-13-1.log.gz'); self.old_log('unknown.gz')
        plan=ClosedLogs(self.root,['2026-01-02-1.log.gz'],True).plan(NOW)
        self.assertEqual([e['name'] for e in plan['entries']],['2026-01-01-1.log.gz'])
    @unittest.skipUnless(os.name=='posix','Linux dir_fd verification')
    async def test_log_delete_and_idempotent_resume(self):
        path=self.old_log(); provider=ClosedLogs(self.root,[],True); plan=provider.plan(NOW)
        result=await apply(plan,digest(plan),NOW,provider,Journal(self.audit))
        self.assertFalse(path.exists()); self.assertEqual(result['removed_this_run'],1)
        result=await apply(plan,digest(plan),NOW,provider,Journal(self.audit))
        self.assertEqual(result['removed_this_run'],0)
    async def test_changed_log_aborts_before_other_delete(self):
        path=self.old_log(); self.old_log('2026-01-02-1.log.gz')
        provider=ClosedLogs(self.root,[],True); plan=provider.plan(NOW); path.write_bytes(b'changed')
        with self.assertRaises(ValueError): await apply(plan,digest(plan),NOW,provider,Journal(self.audit))
        self.assertTrue((self.root/'2026-01-02-1.log.gz').exists())
    async def test_stale_and_wrong_hash_refused(self):
        self.old_log(); provider=ClosedLogs(self.root,[],True); plan=provider.plan(NOW)
        for fingerprint,now in [('wrong',NOW),(digest(plan),'2026-10-15T16:00:00Z')]:
            with self.assertRaises(ValueError): await apply(plan,fingerprint,now,provider,Journal(self.audit))
    @unittest.skipUnless(os.name=='posix','Linux symlinks')
    async def test_symlink_and_hardlink_never_deleted(self):
        target=self.old_log('other.gz'); (self.root/'2026-01-01-1.log.gz').symlink_to(target)
        self.assertEqual(ClosedLogs(self.root,[],True).plan(NOW)['entries'],[])
        (self.root/'2026-01-01-1.log.gz').unlink(); os.link(target,self.root/'2026-01-01-1.log.gz')
        with self.assertRaises(ValueError): ClosedLogs(self.root,[],True).plan(NOW)
    async def test_partial_support_retry(self):
        self.request(); self.registry.reply('11','20','10',OLD); channel,messages=self.channel(('11',))
        plan=support_plan(self.registry,20,NOW); original=messages[10].delete
        async def fail(): raise RuntimeError('synthetic interruption')
        messages[10].delete=fail
        with self.assertRaises(RuntimeError): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
        self.assertNotIn(11,messages); self.assertIn(10,messages)
        messages[10].delete=original
        result=await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
        self.assertTrue(result['complete']); self.assertFalse(messages)

    async def test_disconnect_holds_records_until_explicit_review(self):
        self.request(); self.assertEqual(self.registry.protect_after_gap(),1)
        self.assertEqual(support_plan(self.registry,20,NOW)['entries'],[])
        self.registry.hold('10','20',False)
        self.assertEqual(len(support_plan(self.registry,20,NOW)['entries']),1)
    async def test_support_boundary_and_recent_reply_protected(self):
        self.request(resolved='2026-04-17T16:00:00+00:00')
        self.assertEqual(support_plan(self.registry,20,NOW)['entries'],[])
        self.registry.reply('11','20','10',RECENT)
        self.assertEqual(support_plan(self.registry,20,NOW)['entries'],[])
    async def test_corrupt_journal_blocks_before_mutation(self):
        self.request(); channel,messages=self.channel(); plan=support_plan(self.registry,20,NOW)
        self.audit.write_text('{truncated')
        with self.assertRaises(ValueError): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
        self.assertIn(10,messages)
    async def test_completed_object_reappearance_blocks_retry(self):
        self.request(); channel,messages=self.channel(); plan=support_plan(self.registry,20,NOW)
        message=messages[10]
        await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))
        messages[10]=message
        with self.assertRaises(ValueError): await apply(plan,digest(plan),NOW,TrackedSupport(self.registry,channel,30),Journal(self.audit))

if __name__=='__main__': unittest.main()
