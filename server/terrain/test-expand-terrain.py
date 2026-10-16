"""Synthetic terrain proof tests. Never contacts or changes a real server."""
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import gzip
import importlib.util
import json
import os
import struct
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location('terrain_job', Path(__file__).with_name('expand-terrain.py'))
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def name(value):
    data = value.encode('utf-8')
    return struct.pack('>H', len(data)) + data


def nbt(cx=0, cz=0, status='minecraft:full', legacy=False):
    identity = (b'\x03' + name('xPos') + struct.pack('>i', cx)
                + b'\x03' + name('zPos') + struct.pack('>i', cz)
                + b'\x08' + name('Status') + name(status))
    # Exercise skipping sections, numeric lists and array fields, not only tiny NBT.
    skipped = (b'\x09' + name('sections') + b'\x0a' + struct.pack('>i', 1)
               + b'\x0b' + name('packed') + struct.pack('>i', 2) + bytes(8) + b'\x00'
               + b'\x09' + name('numbers') + b'\x04' + struct.pack('>i', 2) + bytes(16))
    body = identity + skipped + b'\x00'
    if legacy:
        body = b'\x0a' + name('Level') + body + b'\x00'
    return b'\x0a\x00\x00' + body


def write_region(directory, rx, rz, coordinates, external=None, statuses=None):
    data = bytearray(8192)
    external, statuses = set(external or ()), statuses or {}
    for cx, cz in coordinates:
        payload = zlib.compress(nbt(cx, cz, statuses.get((cx, cz), 'minecraft:full')))
        if (cx, cz) in external:
            (directory / f'c.{cx}.{cz}.mcc').write_bytes(payload)
            record = struct.pack('>IB', 1, 130)
        else:
            record = struct.pack('>IB', len(payload) + 1, 2) + payload
        offset = len(data) // 4096
        sectors = (len(record) + 4095) // 4096
        index = 4 * ((cx % 32) + (cz % 32) * 32)
        data[index:index + 4] = ((offset << 8) + sectors).to_bytes(4, 'big')
        data.extend(record + bytes(sectors * 4096 - len(record)))
    path = directory / f'r.{rx}.{rz}.mca'
    path.write_bytes(data)
    return path


def task(cancelled='true', chunks=0, **changes):
    result = {'world': job.WORLD, 'shape': 'square', 'pattern': 'region',
              'center-x': '0.0', 'center-z': '0.0', 'radius': str(job.GENERATION_RADIUS),
              'cancelled': cancelled, 'chunks': str(chunks), 'time': '100'}
    result.update(changes)
    return result


def write_task(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf-8')


class NbtProofTests(unittest.TestCase):
    def test_full_records_all_supported_compressions_and_legacy(self):
        for legacy in (False, True):
            raw = nbt(-2, 35, legacy=legacy)
            for compression, payload in ((1, gzip.compress(raw)), (2, zlib.compress(raw)), (3, raw)):
                job.full_chunk_nbt(payload, compression, -2, 35)

    def test_non_full_and_wrong_coordinates_never_pass(self):
        with self.assertRaises(job.ChunkNotFull):
            job.full_chunk_nbt(zlib.compress(nbt(status='minecraft:noise')), 2, 0, 0)
        with self.assertRaisesRegex(IOError, 'coordinates'):
            job.full_chunk_nbt(zlib.compress(nbt(1, 0)), 2, 0, 0)

    def test_truncated_duplicate_and_decompression_bomb_rejected(self):
        with self.assertRaises(IOError):
            job.full_chunk_nbt(nbt()[:-1], 3, 0, 0)
        duplicate = nbt()[:-1] + b'\x08' + name('Status') + name('minecraft:full') + b'\x00'
        with self.assertRaisesRegex(IOError, 'identity'):
            job.full_chunk_nbt(duplicate, 3, 0, 0)
        with mock.patch.object(job, 'MAX_NBT_BYTES', 512):
            with self.assertRaisesRegex(IOError, 'safety limit'):
                job.full_chunk_nbt(zlib.compress(bytes(5000)), 2, 0, 0)

    def test_unsupported_compression_and_trailing_stream_fail_closed(self):
        with self.assertRaisesRegex(IOError, 'Unsupported chunk compression'):
            job.full_chunk_nbt(b'anything', 4, 0, 0)
        with self.assertRaisesRegex(IOError, 'trailing compressed'):
            job.full_chunk_nbt(zlib.compress(nbt()) + b'extra', 2, 0, 0)


class TerrainJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='holylois-terrain-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'server'
        self.job_directory = self.base / 'job'
        self.region = self.root / 'world/region'
        self.region.mkdir(parents=True)
        self.job_directory.mkdir()
        self.task_path = self.root / 'config/chunky/tasks/minecraft/overworld.properties'
        self.patches = mock.patch.multiple(job, ROOT=self.root, JOB=self.job_directory,
                                         STATE=self.job_directory / 'job.json', TASK=self.task_path,
                                         GENERATION_RADIUS=16, VERIFY_CHUNKS=2, VERIFY_SECONDS=60)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.allowed = mock.patch.object(job, 'generation_allowed', return_value=True)
        self.allowed.start()
        self.addCleanup(self.allowed.stop)

    def populated(self, external=None, statuses=None):
        for _, rx, rz, coordinates in job.region_coordinates():
            write_region(self.region, rx, rz, coordinates, external, statuses)

    def verified(self, state):
        for _ in range(10):
            if job.verify_full_area(state, self.region):
                return
        self.fail('Synthetic FULL coverage did not complete within its bounded batches')

    def test_exact_4000_square_has_251001_coordinates(self):
        with mock.patch.object(job, 'GENERATION_RADIUS', 4000):
            groups = list(job.region_coordinates())
            self.assertEqual(job.expected_chunks(), 251001)
            self.assertEqual(sum(len(group[3]) for group in groups), 251001)
            xs = [cx for group in groups for cx, _ in group[3]]
            zs = [cz for group in groups for _, cz in group[3]]
            self.assertEqual((min(xs), max(xs), min(zs), max(zs)), (-250, 250, -250, 250))

    def test_batched_coverage_resumes_and_detects_changed_region(self):
        self.populated()
        state = {}
        self.assertFalse(job.verify_full_area(state, self.region))
        self.assertEqual(sum(entry['next'] for entry in state['verified_regions'].values()), 2)
        self.verified(state)
        self.assertTrue(job.coverage_complete(state, self.region))
        path = self.region / 'r.0.0.mca'
        stamp = path.stat().st_mtime_ns
        os.utime(path, ns=(stamp + 100, stamp + 100))
        self.assertFalse(job.coverage_complete(state, self.region))
        self.verified(state)

    def test_present_headers_with_proto_chunk_do_not_prove_completion(self):
        self.populated(statuses={(-1, -1): 'minecraft:noise'})
        with self.assertRaises(job.ChunkNotFull):
            job.verify_full_area({}, self.region)

    def test_external_chunk_mutation_invalidates_cached_proof(self):
        self.populated(external={(-1, -1)})
        state = {}
        self.verified(state)
        path = self.region / 'c.-1.-1.mcc'
        path.write_bytes(zlib.compress(nbt(-1, -1, 'minecraft:noise')))
        self.assertFalse(job.coverage_complete(state, self.region))
        with self.assertRaises(job.ChunkNotFull):
            job.verify_full_area(state, self.region)

    def test_changed_region_during_read_does_not_cache_proof(self):
        self.populated()
        reader = job.read_full_chunk
        changed = False
        def mutate(*args):
            nonlocal changed
            result = reader(*args)
            if not changed:
                path = self.region / 'r.-1.-1.mca'
                stamp = path.stat().st_mtime_ns
                os.utime(path, ns=(stamp + 100, stamp + 100))
                changed = True
            return result
        state = {}
        with mock.patch.object(job, 'read_full_chunk', side_effect=mutate):
            self.assertFalse(job.verify_full_area(state, self.region))
        self.assertNotIn('-1,-1', state['verified_regions'])

    def test_owner_validation_and_foreign_task_never_paused(self):
        for key, value in (('world', 'minecraft:the_nether'), ('center-x', '16'),
                           ('radius', '32'), ('shape', 'circle'), ('pattern', 'spiral')):
            self.assertFalse(job.owned_task(task(**{key: value})))
        write_task(self.task_path, task(world='minecraft:the_nether'))
        with mock.patch.object(job, 'command') as command:
            with self.assertRaisesRegex(RuntimeError, 'not the owned'):
                job.checkpoint({'started': True, 'running': True})
            command.assert_not_called()

    def test_first_start_rejects_old_checkpoint_without_cancel_confirm(self):
        write_task(self.task_path, task(radius='2000'))
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            with mock.patch.object(job, 'command') as command:
                with self.assertRaisesRegex(RuntimeError, 'Archive the previous'):
                    job.run_job({'version': 2, 'started': False})
                command.assert_not_called()

    def test_first_start_queues_region_pattern_and_exact_selection(self):
        state = {'version': 2, 'started': False}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            with mock.patch.object(job, 'command') as command:
                job.run_job(state)
                self.assertEqual([call.args[0] for call in command.call_args_list],
                                 ['chunky pattern region', 'chunky start minecraft:overworld square 0 0 16'])
        self.assertTrue(state['started'])

    def test_pause_waits_for_new_complete_checkpoint(self):
        self.task_path.parent.mkdir(parents=True)
        self.task_path.write_text('world=minecraft:overworld\n', encoding='utf-8')
        before = self.task_path.stat().st_mtime_ns
        clock = SimpleNamespace(now=0)
        def sleep(seconds):
            clock.now += seconds
            write_task(self.task_path, task(cancelled='false', chunks=3))
            os.utime(self.task_path, ns=(before + 100, before + 100))
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now, sleep=sleep)
        state = {'started': True, 'running': True}
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'command') as command:
            actual = job.checkpoint(state)
            self.assertEqual(actual['chunks'], '3')
            command.assert_called_once_with('chunky pause minecraft:overworld')
        self.assertFalse(state['running'])
        self.assertFalse(state['pause_pending'])

    def test_pause_timeout_is_bounded_and_never_continues(self):
        write_task(self.task_path, task(cancelled='false'))
        clock = SimpleNamespace(now=0)
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now,
                                    sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'pause_baseline': self.task_path.stat().st_mtime_ns, 'pause_requested_at': 1000}
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'CHECKPOINT_TIMEOUT', 0.5), \
                mock.patch.object(job, 'chunky_idle_since', return_value=False), \
                mock.patch.object(job, 'server_started_at', return_value=100):
            with mock.patch.object(job, 'command') as command:
                self.assertIsNone(job.checkpoint(state))
                command.assert_not_called()
                state['pause_requested_at'] = 800
                with self.assertRaisesRegex(RuntimeError, 'within 120 seconds'):
                    job.checkpoint(state)

    def test_restart_after_pause_request_restarts_the_deadline(self):
        # Pause commands sent while the server booted got no reply; that is not a stuck task.
        write_task(self.task_path, task(cancelled='false'))
        clock = SimpleNamespace(now=0)
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now,
                                    sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'pause_baseline': self.task_path.stat().st_mtime_ns, 'pause_requested_at': 800}
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'CHECKPOINT_TIMEOUT', 0.5),                 mock.patch.object(job, 'chunky_idle_since', return_value=False),                 mock.patch.object(job, 'server_started_at', return_value=850),                 mock.patch.object(job, 'command'):
            self.assertIsNone(job.checkpoint(state))
        self.assertGreater(state['pause_deadline_from'], 850)
        self.assertEqual(state['pause_requested_at'], 800)
        self.assertTrue(state['pause_pending'])

    def test_pause_sent_during_boot_gets_one_extra_deadline(self):
        # 2026-10-16: needrestart restarted the server, the pause went out 5 s into the boot and was answered after it.
        write_task(self.task_path, task(cancelled='false'))
        clock = SimpleNamespace(now=0)
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now,
                                    sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'pause_baseline': self.task_path.stat().st_mtime_ns, 'pause_requested_at': 800}
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'CHECKPOINT_TIMEOUT', 0.5),                 mock.patch.object(job, 'chunky_idle_since', return_value=False),                 mock.patch.object(job, 'server_started_at', return_value=795),                 mock.patch.object(job, 'command'):
            self.assertIsNone(job.checkpoint(state))
            self.assertEqual(state['deadline_reset_for'], 795)
            clock.now = 200
            with self.assertRaisesRegex(RuntimeError, 'not checkpointed'):
                job.checkpoint(state)

    def test_old_boot_does_not_extend_the_deadline(self):
        write_task(self.task_path, task(cancelled='false'))
        clock = SimpleNamespace(now=0)
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now,
                                    sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'pause_baseline': self.task_path.stat().st_mtime_ns, 'pause_requested_at': 800}
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'CHECKPOINT_TIMEOUT', 0.5),                 mock.patch.object(job, 'chunky_idle_since', return_value=False),                 mock.patch.object(job, 'server_started_at', return_value=100),                 mock.patch.object(job, 'command'):
            with self.assertRaisesRegex(RuntimeError, 'not checkpointed'):
                job.checkpoint(state)

    def test_no_running_task_reply_accepts_the_saved_checkpoint(self):
        # After a restart Chunky has no task: "No tasks to pause" never rewrites the file, so the saved one is final.
        write_task(self.task_path, task(cancelled='false', chunks=3))
        clock = SimpleNamespace(now=0)
        fake_time = SimpleNamespace(monotonic=lambda: clock.now, time=lambda: 1000 + clock.now,
                                    sleep=lambda seconds: setattr(clock, 'now', clock.now + seconds))
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'pause_baseline': self.task_path.stat().st_mtime_ns, 'pause_requested_at': 800}
        log = '[03:27:51] [Server thread/INFO]: System chat: [Chunky] No tasks to pause.' + chr(10)
        with mock.patch.object(job, 'time', fake_time), mock.patch.object(job, 'CHECKPOINT_TIMEOUT', 0.5), \
                mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(stdout=log)), \
                mock.patch.object(job, 'command') as command:
            actual = job.checkpoint(state)
            command.assert_not_called()
        self.assertEqual(actual['chunks'], '3')
        self.assertFalse(state['running'])
        self.assertFalse(state['pause_pending'])

    def test_paused_job_sends_no_repeated_pause_commands(self):
        state = {'started': True, 'running': False, 'pause_pending': False}
        with mock.patch.object(job, 'command') as command:
            job.request_pause(state)
            command.assert_not_called()

    def test_completed_and_blocked_states_disable_timer(self):
        with mock.patch.object(job.subprocess, 'run') as process:
            for state in ({'complete': True}, {'phase': 'blocked'}):
                job.run_job(state)
            self.assertEqual(process.call_count, 2)
            for call in process.call_args_list:
                self.assertEqual(call.args[0], ['systemctl', 'disable', '--now', job.TIMER])

    def config_files(self):
        cfg = self.root / 'config/EssentialCommands.properties'
        rules = self.root / 'config/holylois-server.json'
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text('rtp_radius=1800\nother=true\n', encoding='utf-8')
        rules.write_text('{"rtpRadius": 1800, "other": true}\n', encoding='utf-8')
        return cfg, rules

    def test_lagging_saved_count_promotes_only_after_full_nbt_coverage(self):
        self.populated()
        state = {'started': True, 'running': False, 'phase': 'verifying'}
        self.verified(state)
        write_task(self.task_path, task(chunks=0))
        cfg, rules = self.config_files()
        with mock.patch.object(job, 'command') as command, mock.patch.object(job, 'disable_timer') as disable:
            job.finish(state, task(chunks=0), self.region)
            command.assert_called_once_with('essentialcommands config reload')
            disable.assert_called_once()
        self.assertEqual(cfg.read_text(), f'rtp_radius={job.RTP_RADIUS}\nother=true\n')
        self.assertEqual(json.loads(rules.read_text()), {'rtpRadius': job.RTP_RADIUS, 'other': True})
        self.assertEqual(state['full_chunks_verified'], 9)
        self.assertTrue(state['complete'])
        self.assertTrue((self.job_directory / 'holylois-server-before.json').exists())

    def test_promotion_without_essential_commands_rtp_updates_only_the_addon(self):
        self.populated()
        state = {'started': True, 'running': False, 'phase': 'verifying'}
        self.verified(state)
        write_task(self.task_path, task(chunks=0))
        cfg, rules = self.config_files()
        cfg.write_text('enable_rtp=false\nother=true\n', encoding='utf-8')
        with mock.patch.object(job, 'command') as command, mock.patch.object(job, 'disable_timer'):
            job.finish(state, task(chunks=0), self.region)
            command.assert_not_called()
        self.assertEqual(cfg.read_text(), 'enable_rtp=false\nother=true\n')
        self.assertEqual(json.loads(rules.read_text())['rtpRadius'], job.RTP_RADIUS)
        self.assertFalse((self.job_directory / 'EssentialCommands-before.properties').exists())
        self.assertTrue(state['complete'])

    def test_resume_or_incomplete_coverage_never_changes_radius(self):
        cfg, rules = self.config_files()
        before = cfg.read_text(), rules.read_text()
        write_task(self.task_path, task())
        with self.assertRaisesRegex(RuntimeError, 'completed Chunky'):
            job.finish({}, task(cancelled='false'), self.region)
        with self.assertRaisesRegex(RuntimeError, 'completion proof changed'):
            job.finish({}, task(), self.region)
        self.assertEqual((cfg.read_text(), rules.read_text()), before)

    def test_reload_queue_failure_rolls_back_both_configs(self):
        self.populated()
        state = {'started': True, 'running': False}
        self.verified(state)
        write_task(self.task_path, task())
        cfg, rules = self.config_files()
        before = cfg.read_text(), rules.read_text()
        with mock.patch.object(job, 'command', side_effect=OSError('No console reader')):
            with self.assertRaises(OSError):
                job.finish(state, task(), self.region)
        self.assertEqual((cfg.read_text(), rules.read_text()), before)
        self.assertFalse(state.get('complete'))

    def test_join_or_low_storage_after_wait_prevents_continue(self):
        state = {'started': True, 'running': False}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            with mock.patch.object(job, 'generation_allowed', side_effect=[True, False]):
                with mock.patch.object(job, 'checkpoint', return_value=task(cancelled='false')):
                    with mock.patch.object(job, 'command') as command:
                        job.run_job(state)
                        command.assert_not_called()

    def test_generation_guard_pauses_on_join_low_disk_or_status_failure(self):
        self.allowed.stop()
        with mock.patch.object(job, 'request_pause') as pause:
            for players, free in ((1, 100 * 1024**3), (0, 5 * 1024**3)):
                with mock.patch.object(job, 'online_players', return_value=players):
                    with mock.patch.object(job.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)):
                        self.assertFalse(job.generation_allowed({'started': True}))
            with mock.patch.object(job, 'online_players', side_effect=OSError('Unavailable')):
                self.assertFalse(job.generation_allowed({'started': True}))
            self.assertEqual(pause.call_count, 3)

    def test_rest_needed_after_lag_or_a_long_slice_only_while_running(self):
        now = 100000
        self.assertEqual(job.rest_needed({'started': True, 'running': True, 'resumed_at': now - 60}, now, 0), 0)
        self.assertEqual(job.rest_needed({'started': True, 'running': True, 'resumed_at': now - 60}, now, job.LAG_TICKS), job.LAG_REST_SECONDS)
        self.assertEqual(job.rest_needed({'started': True, 'running': True, 'resumed_at': now - job.RUN_SECONDS}, now, 0), job.REST_SECONDS)
        self.assertEqual(job.rest_needed({'started': True, 'running': False, 'resumed_at': now - 99999}, now, 999), 0)
        self.assertEqual(job.rest_needed({'started': False}, now, 999), 0)

    def test_lag_is_read_from_the_log_and_rest_holds_generation(self):
        log = "[01:50:07] Can't keep up! Is the server overloaded? Running 5733ms or 114 ticks behind" + chr(10) + "[01:50:28] Can't keep up! Running 5138ms or 102 ticks behind" + chr(10)
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(stdout=log)):
            self.assertEqual(job.recent_lag(), 114)
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(stdout='')):
            self.assertEqual(job.recent_lag(), 0)
        state = {'started': True, 'running': True, 'rest_until': job.time.time() + 600}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
            with mock.patch.object(job, 'generation_allowed', return_value=True):
                with mock.patch.object(job, 'command') as command:
                    job.run_job(state)
                    command.assert_not_called()

    def test_running_checks_preserve_slice_start_without_repeated_continue(self):
        state = {'started': True, 'running': True, 'resumed_at': 1000}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                mock.patch.object(job.time, 'time', return_value=1100), \
                mock.patch.object(job, 'recent_lag', return_value=0), \
                mock.patch.object(job, 'task_snapshot', return_value=task(cancelled='false')), \
                mock.patch.object(job, 'checkpoint') as checkpoint, \
                mock.patch.object(job, 'command') as command:
            job.run_job(state)
            self.assertEqual(state['resumed_at'], 1000)
            command.assert_not_called()
            checkpoint.assert_not_called()

    def test_long_running_slice_really_pauses(self):
        state = {'started': True, 'running': True, 'resumed_at': 1000}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                mock.patch.object(job.time, 'time', return_value=4000), \
                mock.patch.object(job, 'recent_lag', return_value=0), \
                mock.patch.object(job, 'request_pause') as pause, \
                mock.patch.object(job, 'checkpoint') as checkpoint, mock.patch.object(job, 'save'):
            job.run_job(state)
            pause.assert_called_once_with(state)
            checkpoint.assert_called_once_with(state)
            self.assertEqual(state['rest_until'], 4000 + job.REST_SECONDS)

    def test_pending_pause_is_finalized_before_rest(self):
        state = {'started': True, 'running': True, 'pause_pending': True,
                 'resumed_at': 1000, 'rest_until': 4000}
        def confirmed(_):
            state.update(running=False, pause_pending=False)
            return task(cancelled='false')
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                mock.patch.object(job.time, 'time', return_value=1100), \
                mock.patch.object(job, 'checkpoint', side_effect=confirmed) as checkpoint, \
                mock.patch.object(job, 'command') as command:
            job.run_job(state)
            checkpoint.assert_called_once_with(state)
            self.assertFalse(state['running'])
            command.assert_not_called()

    def test_finished_rest_resumes_existing_task_once(self):
        state = {'started': True, 'running': False, 'resumed_at': 100, 'rest_until': 1000}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                mock.patch.object(job.time, 'time', return_value=1100), \
                mock.patch.object(job, 'recent_lag', return_value=0), \
                mock.patch.object(job, 'checkpoint', return_value=task(cancelled='false')), \
                mock.patch.object(job, 'save'), mock.patch.object(job, 'command') as command:
            job.run_job(state)
            self.assertEqual(state['resumed_at'], 1100)
            self.assertTrue(state['running'])
            command.assert_called_once_with('chunky continue minecraft:overworld')

    def test_owner_hold_pauses_running_generation_and_starts_nothing(self):
        (self.job_directory / 'hold').touch()
        running = {'started': True, 'running': True}
        with mock.patch.object(job.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                mock.patch.object(job, 'command') as command, mock.patch.object(job, 'save'), \
                mock.patch.object(job, 'checkpoint', return_value={'chunks': '5'}) as checkpoint:
            job.run_job(running)
            command.assert_called_once_with('chunky pause minecraft:overworld')
            checkpoint.assert_called_once()
            command.reset_mock(); checkpoint.reset_mock()
            fresh = {'version': 2, 'started': False, 'complete': False}
            job.run_job(fresh)
            self.assertFalse(fresh['started'])
            paused = {'started': True, 'running': False}
            job.run_job(paused)
            command.assert_not_called(); checkpoint.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
