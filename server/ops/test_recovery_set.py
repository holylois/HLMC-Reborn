import unittest
from types import SimpleNamespace
from unittest.mock import patch
import recovery_set


class StoppedWriters(unittest.TestCase):
    def test_inactive_processes_are_required(self):
        for state in ('ActiveState=active\nMainPID=123\nControlPID=0\n',
                      'ActiveState=inactive\nMainPID=0\nControlPID=123\n',
                      'ActiveState=deactivating\nMainPID=0\nControlPID=0\n', ''):
            with self.subTest(state=state), patch.object(recovery_set.subprocess, 'run', return_value=SimpleNamespace(stdout=state)):
                with self.assertRaisesRegex(RuntimeError, 'writers stopped'):
                    recovery_set.require_stopped()

    def test_every_known_writer_is_checked(self):
        with patch.object(recovery_set.subprocess, 'run', return_value=SimpleNamespace(stdout='ActiveState=inactive\nMainPID=0\nControlPID=0\n')) as run:
            recovery_set.require_stopped()
        self.assertEqual(len(run.call_args_list), len(recovery_set.WRITERS))
        self.assertEqual({call.args[0][2] for call in run.call_args_list}, set(recovery_set.WRITERS))


if __name__ == '__main__':
    unittest.main()
