"""Support routing with a private-only fallback. Never log ticket contents or credentials."""
import asyncio
import json
from pathlib import Path
import urllib.parse
import urllib.request


async def deliver(primary, fallback, warn):
    if primary is not None:
        try:
            return await primary()
        except Exception as error:
            warn('Support channel delivery failed (' + type(error).__name__ + '); trying private staff fallback.')
    else:
        warn('Support channel unavailable; trying private staff fallback.')
    try:
        await fallback()
    except Exception as error:
        warn('Support private fallback failed (' + type(error).__name__ + '). Original request remains in the Minecraft journal; staff review required.')
        raise RuntimeError('Support could not reach either private destination') from None
    warn('Support delivered to private staff fallback; replies and retention need manual staff review.')
    return None


async def private_webhook(embed):
    def send():
        url = Path('/etc/holylois/discord-webhook').read_text().strip()
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc not in ('discord.com', 'discordapp.com')
                or not parsed.path.startswith('/api/webhooks/') or parsed.query or parsed.fragment):
            raise ValueError('Private staff webhook unavailable')
        body = json.dumps({'embeds': [embed], 'allowed_mentions': {'parse': []}}).encode()
        request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json',
                                         'User-Agent': 'HolyLoisSupport/1.0'})
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status not in (200, 204):
                raise RuntimeError('Private staff delivery was not accepted')
    await asyncio.to_thread(send)
