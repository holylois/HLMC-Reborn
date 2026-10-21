import asyncio
import unittest
from unittest.mock import AsyncMock

from support_delivery import deliver


class Delivery(unittest.TestCase):
    def test_success_never_duplicates_to_fallback(self):
        primary, fallback = AsyncMock(return_value='delivered'), AsyncMock()
        self.assertEqual(asyncio.run(deliver(primary, fallback, lambda message: None)), 'delivered')
        fallback.assert_not_awaited()

    def test_missing_or_forbidden_channel_uses_private_fallback(self):
        for primary in (None, AsyncMock(side_effect=PermissionError('private ticket must not enter logs'))):
            warnings, fallback = [], AsyncMock()
            self.assertIsNone(asyncio.run(deliver(primary, fallback, warnings.append)))
            fallback.assert_awaited_once()
            self.assertNotIn('private ticket', ' '.join(warnings))
            self.assertIn('manual staff review', warnings[-1])

    def test_total_failure_is_visible_without_ticket_contents(self):
        warnings = []
        with self.assertRaisesRegex(RuntimeError, 'either private destination'):
            asyncio.run(deliver(None, AsyncMock(side_effect=OSError('private secret')), warnings.append))
        self.assertNotIn('private secret', ' '.join(warnings))


if __name__ == '__main__':
    unittest.main()
