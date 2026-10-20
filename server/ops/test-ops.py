"""Tests for the deploy kit, the thread guard, the monitor lag watch and the off-site volatile-file handling (Linux: needs tar).

  python3 test-ops.py
"""
import importlib.util, json, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


kit = module('hl_deploy', 'hl-deploy.py')
alert = module('discord_alert', 'discord-alert.py')
offsite = module('offsite_backup', 'offsite-backup.py')
guard = module('thread_guard', 'thread-guard.py')
real_run = kit.run


class DeployKit(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.root = self.temp / 'minecraft'
        for name in ('mods', 'config', 'world', 'EasyAuth', 'bluemap'):
            (self.root / name).mkdir(parents=True)
        (self.root / 'mods/lib-1.jar').write_bytes(b'old library')
        (self.root / 'mods/keep.jar').write_bytes(b'kept')
        (self.root / 'config/a.json').write_text('{"old": true}')
        (self.root / 'world/level.dat').write_bytes(b'world')
        (self.root / 'bluemap/tile.png').write_bytes(b'tile')
        self.plan_dir = self.temp / 'kit'
        self.plan_dir.mkdir()
        (self.plan_dir / 'lib-2.jar').write_bytes(b'new library')
        (self.plan_dir / 'a.json').write_text('{"new": true}')
        self.plan = {'name': 'libs-test', 'reason': 'small mod updates', 'scope': 'jars', 'data_migration': False,
                     'swap': {'lib-1.jar': 'lib-2.jar'}, 'files': {'config/a.json': 'a.json'},
                     'expect_log': ['lib 2'], 'tested': {'lib-2.jar': kit.sha(self.plan_dir / 'lib-2.jar'),
                                                          'a.json': kit.sha(self.plan_dir / 'a.json')}}
        self.patches = [mock.patch.object(kit, 'ROOT', self.root), mock.patch.object(kit, 'BACKUPS', self.temp / 'backups'),
                        mock.patch.object(kit, 'MAINTENANCE', self.temp / 'maintenance'),
                        mock.patch.object(kit, 'HOLD', self.temp / 'hold'), mock.patch.object(kit, 'console'),
                        mock.patch.object(kit.recovery_set, 'require_stopped'),
                        mock.patch.object(kit.shutil, 'chown'), mock.patch.object(kit.time, 'sleep')]
        for patch in self.patches:
            patch.start()
        self.systemctl = []
        kit.run = self.fake_run

    def tearDown(self):
        kit.run = real_run
        for patch in self.patches:
            patch.stop()

    def fake_run(self, *args, **kw):
        if args[0] in ('systemctl', 'systemd-run'):
            self.systemctl.append(args)
            return SimpleNamespace(returncode=0)
        return real_run(*args, **kw)

    def write_plan(self, **changes):
        plan = dict(self.plan, **changes)
        path = self.plan_dir / 'plan.json'
        path.write_text(json.dumps(plan))
        return kit.load_plan(path)

    def base(self, log):
        return SimpleNamespace(online_players=lambda: 0, journal=lambda since: log)

    def deploy(self, plan, log):
        with mock.patch.object(kit.subprocess, 'run', side_effect=self.fake_subprocess):
            kit.deploy(self.base(log), plan)

    def fake_subprocess(self, args, **kw):
        if args[0] == 'systemctl':
            return SimpleNamespace(returncode=1, stdout='')
        return real_subprocess(args, **kw)

    def test_plan_rejects_untested_and_escaping_files(self):
        with self.assertRaisesRegex(ValueError, 'untested'):
            self.write_plan(tested={})
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.write_plan(files={'../etc/x': 'a.json'})
        with self.assertRaisesRegex(ValueError, 'only change mods'):
            self.write_plan(files={'world/level.dat': 'a.json'})

    def test_jar_deploy_swaps_and_keeps_the_old_jar(self):
        plan = self.write_plan()
        self.deploy(plan, 'Done (1.0s)! Holy Lois claims: ready for OPAC lib 2')
        self.assertFalse((self.root / 'mods/lib-1.jar').exists())
        self.assertEqual((self.root / 'mods/lib-2.jar').read_bytes(), b'new library')
        self.assertEqual((self.root / 'config/a.json').read_text(), '{"new": true}')
        folder = next((self.temp / 'backups').iterdir())
        self.assertTrue((folder / 'replaced-lib-1.jar').exists())
        receipt = json.loads((folder / 'receipt.json').read_text())
        self.assertEqual(receipt['backup']['scope'], 'jars')
        self.assertFalse(kit.MAINTENANCE.exists())

    def test_failed_start_restores_mods_and_config(self):
        plan = self.write_plan()
        with self.assertRaisesRegex(RuntimeError, 'Expected startup lines missing'):
            self.deploy(plan, 'Done (1.0s)! Holy Lois claims: ready for OPAC')
        self.assertEqual((self.root / 'mods/lib-1.jar').read_bytes(), b'old library')
        self.assertFalse((self.root / 'mods/lib-2.jar').exists())
        self.assertEqual((self.root / 'config/a.json').read_text(), '{"old": true}')
        self.assertTrue(any(a[1:3] == ('start', 'minecraft-console.socket') for a in self.systemctl))

    def test_world_scope_backup_skips_bluemap(self):
        plan = self.write_plan(scope='world')
        folder = self.temp / 'b'
        folder.mkdir()
        kit.backup(plan, folder)
        import tarfile
        with tarfile.open(folder / 'backup.tar') as tar:
            names = tar.getnames()
        self.assertIn('minecraft/world/level.dat', names)
        self.assertFalse(any('bluemap' in n for n in names))
        recovery = json.loads((folder / 'recovery-set.json').read_text())
        self.assertTrue(recovery['application_consistent'])
        self.assertFalse(recovery['offsite_verified'])

    def test_world_rollback_restores_root_file_and_quarantines_new_tree(self):
        (self.root / 'server.properties').write_text('old settings')
        plan = self.write_plan(scope='world', files={'server.properties': 'a.json', 'new-root/settings.json': 'a.json'})
        with self.assertRaisesRegex(RuntimeError, 'Expected startup lines missing'):
            self.deploy(plan, 'Done (1.0s)! Holy Lois claims: ready for OPAC')
        self.assertEqual((self.root / 'server.properties').read_text(), 'old settings')
        self.assertFalse((self.root / 'new-root').exists())
        folder = next((self.temp / 'backups').iterdir())
        self.assertTrue((folder / 'failed/new-root/settings.json').exists())

    def test_world_rollback_covers_unlisted_application_stores(self):
        (self.root / 'permissions').mkdir()
        (self.root / 'permissions/generated.db').write_bytes(b'old permissions')
        plan = self.write_plan(scope='world', data_migration=True)
        folder = self.temp / 'migration-backup'; folder.mkdir()
        kit.backup(plan, folder)
        (self.root / 'permissions/generated.db').write_bytes(b'migrated')
        (self.root / 'new-application-store').mkdir()
        (self.root / 'new-application-store/data.json').write_text('{}')
        kit.restore(plan, folder)
        self.assertEqual((self.root / 'permissions/generated.db').read_bytes(), b'old permissions')
        self.assertFalse((self.root / 'new-application-store').exists())
        self.assertTrue((folder / 'failed/new-application-store/data.json').exists())
        self.assertTrue((self.root / 'bluemap/tile.png').exists())

    def test_rollback_failure_keeps_maintenance_and_timers_paused(self):
        plan = self.write_plan()
        with mock.patch.object(kit, 'start', side_effect=RuntimeError('boot failed')):
            with self.assertRaisesRegex(RuntimeError, 'boot failed'):
                self.deploy(plan, '')
        self.assertTrue(kit.MAINTENANCE.exists())

    def test_guarded_rollback_rebinds_only_after_successful_extraction(self):
        directory = self.temp / 'guard'
        guard = kit.recovery_guard.Guard(self.root, directory)
        guard.initialize()
        plan = self.write_plan()
        folder = self.temp / 'guarded-backup'; folder.mkdir()
        kit.backup(plan, folder)
        (self.root / 'config/a.json').write_text('changed')
        with mock.patch.object(kit.recovery_guard, 'STATE', directory):
            kit.restore(plan, folder)
        self.assertEqual((self.root / 'config/a.json').read_text(), '{"old": true}')
        self.assertTrue(guard.start()['allow_start'])

    def test_guarded_failed_extraction_cannot_restart(self):
        directory = self.temp / 'guard'
        guard = kit.recovery_guard.Guard(self.root, directory)
        guard.initialize()
        plan = self.write_plan()
        folder = self.temp / 'failed-guarded-backup'; folder.mkdir()
        kit.backup(plan, folder)
        with mock.patch.object(kit.recovery_guard, 'STATE', directory), \
                mock.patch.object(kit, 'run', side_effect=OSError('Generated extraction failure')):
            with self.assertRaises(OSError): kit.restore(plan, folder)
        with self.assertRaisesRegex(ValueError, 'Incomplete restore'): guard.start()

    def test_migration_declaration_and_all_mod_paths_are_checked(self):
        for change in ({'data_migration': None}, {'data_migration': True},
                       {'swap': {'../outside.jar': 'lib-2.jar'}}, {'add': ['../outside.jar']},
                       {'files': {'config\\escape.json': 'a.json'}},
                       {'scope': 'world', 'files': {'world/a.json': 'a.json'}},
                       {'scope': 'world', 'files': {'bluemap/a.json': 'a.json'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.write_plan(**change)

    def test_symlinked_parent_is_blocked(self):
        outside = self.temp / 'outside'; outside.mkdir()
        (self.root / 'config/link').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'escape|Symlink'):
            kit.safe_target(self.root / 'config/link/settings.json')


real_subprocess = kit.subprocess.run


class LagWatch(unittest.TestCase):
    def test_backup_diagnostics_use_only_private_destination(self):
        with mock.patch.object(alert.sys, 'argv', ['discord-alert.py', 'staff-message', 'generated private fixture']), \
                mock.patch.object(alert, 'post_staff', return_value=True) as private, mock.patch.object(alert, 'post') as public:
            alert.main()
        private.assert_called_once(); public.assert_not_called()

    def test_missing_staff_webhook_never_publishes_private_details(self):
        with mock.patch.object(alert.Path, 'exists', return_value=False), mock.patch.object(alert, 'post') as public, \
                mock.patch.object(alert.urllib.request, 'urlopen') as request:
            self.assertFalse(alert.post_staff('Generated private diagnostic', 'generated private contents', alert.RED))
        public.assert_not_called(); request.assert_not_called()

    def run_watch(self, state, players, count, worst=3000, log='', started_ago=3600):
        posts = []
        with mock.patch.object(alert, 'stalls', return_value=(count, worst, log)), \
                mock.patch.object(alert, 'service_started', return_value=time.time() - started_ago), \
                mock.patch.object(alert, 'post_staff', side_effect=lambda *a, **k: posts.append(a)), \
                mock.patch.object(alert.os, 'open', return_value=3), mock.patch.object(alert.os, 'write') as write, \
                mock.patch.object(alert.os, 'close'), mock.patch.object(alert.Path, 'exists', return_value=True):
            alert.lag_watch(state, players)
        return posts, write

    def test_stalls_with_players_alert_and_start_one_profile(self):
        state = {}
        posts, write = self.run_watch(state, 3, 4)
        self.assertEqual(len(posts), 1)
        self.assertIn('4 lag spikes', posts[0][1])
        write.assert_called_once()
        self.assertEqual(write.call_args.args[1], b'spark profiler open\n')
        self.assertIn('lag_alert_at', state)
        self.assertFalse(state['spark_posted'])

    def test_empty_server_boot_and_quiet_hour_are_ignored(self):
        self.assertEqual(self.run_watch({}, 0, 9)[0], [])
        self.assertEqual(self.run_watch({}, 2, 9, started_ago=60)[0], [])
        self.assertEqual(self.run_watch({'lag_alert_at': time.time() - 600}, 2, 9)[0], [])
        self.assertEqual(self.run_watch({}, 2, 2)[0], [])

    def test_profile_link_is_posted_once(self):
        state = {'spark_at': time.time() - 200, 'spark_posted': False, 'lag_alert_at': time.time()}
        posts, _ = self.run_watch(state, 1, 0, log='[spark] https://spark.lucko.me/AbC123 done')
        self.assertEqual(len(posts), 1)
        self.assertIn('https://spark.lucko.me/AbC123', posts[0][1])
        self.assertTrue(state['spark_posted'])
        self.assertEqual(self.run_watch(state, 1, 0, log='https://spark.lucko.me/AbC123')[0], [])


class OffsiteVolatile(unittest.TestCase):
    def test_unfinished_and_held_non_release_folders_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); folder = root / 'generated-failed-deploy'; folder.mkdir()
            (folder / 'backup.tar').write_bytes(b'generated backup')
            with mock.patch.object(offsite, 'MAINTENANCE', root), mock.patch.object(offsite, 'rclone') as remote:
                self.assertEqual(offsite.offload_maintenance(), [])
                remote.assert_not_called()
                self.assertTrue((folder / 'backup.tar').exists())
                (folder / 'receipt.json').write_text(json.dumps({'live': True, 'backup': {'scope':'world', 'archive_bytes':16, 'archive_sha256':'a'*64}}))
                self.assertTrue(offsite.maintenance_ready(folder))
                (folder / 'hold').write_text('generated hold')
                self.assertFalse(offsite.maintenance_ready(folder))

    def test_archive_bytes_must_match_the_fingerprint_and_preexisting_temp_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary); root = parent / 'minecraft'; (root / 'config').mkdir(parents=True)
            path = root / 'config/settings.json'; path.write_text('original')
            with mock.patch.object(offsite, 'ROOT', root), mock.patch.object(offsite, 'SERVER_PATHS', ['config']), \
                    mock.patch.object(offsite, 'STATE', parent / 'state.json'), mock.patch.object(offsite, 'rclone') as remote:
                fingerprint, files = offsite.server_archive()
                path.write_text('changed after fingerprint')
                with self.assertRaisesRegex(ValueError, 'changed during'):
                    offsite.upload_server(files, 'fixture', fingerprint)
                remote.assert_not_called()
                pending = parent / 'server-fixture.tar.gz'; pending.write_bytes(b'previous evidence')
                with self.assertRaises(FileExistsError):
                    offsite.upload_server(files, 'fixture', fingerprint)
                self.assertEqual(pending.read_bytes(), b'previous evidence')

    def test_spark_temp_files_and_vanishing_files_are_skipped(self):
        root = Path(tempfile.mkdtemp()) / 'minecraft'
        (root / 'config/spark/tmp').mkdir(parents=True)
        (root / 'config/spark/tmp/profile.jfr.tmp').write_bytes(b'x')
        (root / 'config/real.json').write_text('{}')
        gone = root / 'config/gone.json'
        gone.write_text('{}')
        original = Path.read_bytes

        def read_bytes(path):
            if path == gone:
                raise FileNotFoundError(path)
            return original(path)

        with mock.patch.object(offsite, 'ROOT', root), mock.patch.object(offsite, 'SERVER_PATHS', ['config']), \
                mock.patch.object(Path, 'read_bytes', read_bytes):
            _, files = offsite.server_archive()
        names = [str(p.relative_to(root)) for p in files]
        self.assertEqual(names, ['config/real.json'])


class ThreadGuard(unittest.TestCase):
    def test_decisions(self):
        d, now = guard.decide, 10_000
        self.assertEqual(d(7900, 13008, 0, 0, now), 'restart-quiet')
        self.assertEqual(d(7700, 13008, 0, 0, now), 'ok')
        self.assertEqual(d(9000, 13008, 2, 0, now), 'ok')
        self.assertEqual(d(11100, 13008, 2, 0, now), 'restart-countdown')
        self.assertTrue(d(11100, 13008, 2, now - 60, now).startswith('wait'))
        self.assertTrue(d(11100, 13008, None, 0, now).startswith('wait'))
        self.assertTrue(d(None, None, 0, 0, now).startswith('wait'))

    def fake_kit(self, start_fails=False):
        temp = Path(tempfile.mkdtemp())
        calls = []
        def start(base, plan):
            calls.append('start')
            if start_fails:
                raise RuntimeError('Startup failure')
        hl = SimpleNamespace(MAINTENANCE=temp / 'maintenance', helper=lambda: None, start=start,
                             countdown=lambda base, plan: calls.append('countdown:' + plan['reason']),
                             console=lambda *c: calls.append('console:' + ' '.join(c)),
                             run=lambda *a: calls.append('run:' + ' '.join(a)))
        return hl, calls

    def test_quiet_restart_skips_the_countdown_and_resumes_the_pregen_timer(self):
        hl, calls = self.fake_kit()
        with mock.patch.object(guard.subprocess, 'run') as run, mock.patch.object(guard.time, 'sleep'):
            guard.restart(hl, countdown=False)
        self.assertFalse(any(c.startswith('countdown') for c in calls))
        self.assertIn('console:save-all flush', calls)
        self.assertIn('start', calls)
        self.assertFalse(hl.MAINTENANCE.exists())
        self.assertEqual(run.call_args_list[-1].args[0], ['systemctl', 'start', 'holylois-terrain-expansion.timer'])

    def test_countdown_with_players_and_cleanup_after_a_failed_start(self):
        hl, calls = self.fake_kit(start_fails=True)
        with mock.patch.object(guard.subprocess, 'run') as run, mock.patch.object(guard.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                guard.restart(hl, countdown=True)
        self.assertEqual(calls[0], 'countdown:' + guard.REASON)
        self.assertFalse(hl.MAINTENANCE.exists())
        self.assertEqual(run.call_args_list[-1].args[0], ['systemctl', 'start', 'holylois-terrain-expansion.timer'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
