import importlib.util
import unittest
from pathlib import Path
from recovery_chain import select_chain


def meta(identity, kind='full', base=None, date='2026-10-20T08:00:00+00:00', stream='world-test'):
    return dict(id=identity, kind=kind, base_id=base, created_at=date, stream=stream)


class RecoveryChain(unittest.TestCase):
    def test_metadata_beats_names_and_upload_order(self):
        candidates = [('full-new-looking.zip', meta('old', date='2026-10-19T08:00:00Z')),
                      ('renamed.zip', meta('base')),
                      ('not-a-date.zip', meta('delta', 'differential', 'base', '2026-10-20T09:00:00Z'))]
        self.assertEqual(select_chain(candidates), ['renamed.zip', 'not-a-date.zip'])

    def test_missing_base_blocks_instead_of_silently_using_old_data(self):
        with self.assertRaisesRegex(ValueError, 'full base'):
            select_chain([('base', meta('old')), ('delta', meta('delta', 'differential', 'missing', '2026-10-20T09:00:00Z'))])

    def test_duplicate_identity_and_multiple_streams_block(self):
        for rows in ([('a', meta('same')), ('b', meta('same'))],
                     [('a', meta('a')), ('b', meta('b', stream='other'))]):
            with self.assertRaises(ValueError):
                select_chain(rows)

    def test_newer_full_needs_no_old_differentials(self):
        self.assertEqual(select_chain([('a', meta('a')), ('b', meta('b', date='2026-10-21T09:00:00Z'))]), ['b'])

    def test_drill_uses_receipted_identity_and_rejects_provider_drift(self):
        spec = importlib.util.spec_from_file_location('drill', Path(__file__).with_name('restore-drill.py'))
        drill = importlib.util.module_from_spec(spec); spec.loader.exec_module(drill)
        row = {'backup': dict(meta('a'), complete=True, verified=True),
               'members': [{'path': 'world/renamed.zip', 'md5': 'a' * 32}]}
        self.assertEqual(drill.chosen({'renamed.zip': 'a' * 32}, [row])[0], ['renamed.zip'])
        with self.assertRaisesRegex(ValueError, 'original upload'):
            drill.chosen({'renamed.zip': 'b' * 32}, [row])


if __name__ == '__main__':
    unittest.main()
