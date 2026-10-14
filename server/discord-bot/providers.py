"""Exact-ID support and whole-recovery-set adapters. No credentials are stored here."""
from datetime import timedelta
from enforcement import when


def support_plan(registry, channel, now):
    entries, protected = [], 0
    channel = registry.identifier(channel)
    for row in registry.inventory():
        snapshot = registry.snapshot(row['id'].removeprefix('support-'))
        if (snapshot['channel'] != channel or snapshot['held'] or snapshot['retention_class'] != 'routine'
                or not snapshot['resolved'] or max(when(snapshot['resolved']), when(snapshot['activity']))
                >= when(now) - timedelta(days=180)):
            protected += 1
            continue
        # Keep the root until all old replies have been handled; a new reply can then block its removal.
        messages = [x for x in snapshot['messages'] if x != snapshot['id']] + [snapshot['id']]
        for message in messages:
            entries.append({'kind': 'support-message', 'request': snapshot['id'], 'channel': channel,
                            'message': message, 'snapshot': snapshot})
    return {'schema': 1, 'kind': 'tracked-support', 'as_of': now, 'ready': True,
            'entries': entries, 'protected_requests': protected}


class TrackedSupport:
    """Channel is the existing private staff channel, using the bot's existing SDK session."""
    def __init__(self, registry, channel, bot_id):
        self.registry, self.channel, self.bot_id = registry, channel, str(bot_id)

    async def message(self, message_id):
        try:
            return await self.channel.fetch_message(int(message_id))
        except Exception as error:
            if getattr(error, 'status', None) == 404:
                return None
            raise  # Permissions/rate limits/network failures are never treated as successful erasure.

    async def validate(self, entry, now):
        if entry.get('kind') != 'support-message' or entry['channel'] != str(self.channel.id):
            raise ValueError('Unexpected support channel or target')
        current = self.registry.snapshot(entry['request'])
        if current != entry['snapshot'] or current is None or current['held']:
            raise ValueError('Support activity, classification or hold changed')
        if (current['retention_class'] != 'routine' or not current['resolved']
                or max(when(current['resolved']), when(current['activity'])) >= when(now) - timedelta(days=180)):
            raise ValueError('Support request is not eligible')
        if entry['message'] not in current['messages']:
            raise ValueError('Message is not explicitly tracked')
        message = await self.message(entry['message'])
        if message is None:
            return False
        if str(message.channel.id) != entry['channel'] or str(message.id) != entry['message']:
            raise ValueError('Discord returned another message')
        if entry['message'] == current['id']:
            if str(message.author.id) != self.bot_id:
                raise ValueError('Root is not authored by this bot')
        elif str(getattr(message.reference, 'message_id', '')) not in current['messages']:
            raise ValueError('Reply no longer belongs to the tracked request')
        edited = getattr(message, 'edited_at', None)
        if edited is not None and when(edited.isoformat()) > when(current['activity']):
            raise ValueError('Untracked edit requires retention review')
        return True

    async def remove(self, entry, now):
        if not await self.validate(entry, now):
            return
        message = await self.message(entry['message'])
        if message is not None:
            await message.delete()

