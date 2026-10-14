"""Disabled-by-default routine expiry wiring. Private policy deployment is a separate approval."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from enforcement import ClosedLogs, Journal, apply, digest
from providers import support_plan, TrackedSupport

POLICY = Path('/var/lib/holylois/retention-policy.json')
AUDIT = Path('/var/lib/holylois/retention-audit')


def load_policy(path=POLICY):
    path = Path(path)
    if not path.exists():
        return {'schema': 1, 'logs_enabled': False, 'support_enabled': False}
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_nlink != 1:
        raise ValueError('Policy must be a private root-owned regular file')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or value.get('log_days') != 90 or value.get('support_days') != 180:
        raise ValueError('Policy periods differ from the approved design')
    for flag in ('logs_enabled','support_enabled','log_holds_reviewed'):
        if type(value.get(flag)) is not bool:
            raise ValueError('Policy flags must be explicit booleans')
    return value


def ensure_audit():
    AUDIT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if AUDIT.is_symlink() or AUDIT.stat().st_mode & 0o077:
        raise ValueError('Audit directory must remain private')


async def logs(policy, now=None, root=Path('/opt/minecraft/logs'), audit=None):
    if policy.get('logs_enabled') is not True:
        return {'enabled': False, 'removed': 0}
    provider = ClosedLogs(root, policy['held_log_names'], policy['log_holds_reviewed'])
    now = now or datetime.now(timezone.utc).isoformat()
    plan = provider.plan(now)
    # Enabled root policy is standing approval for this fixed log rule, never backups or player files.
    return await apply(plan, digest(plan), now, provider, Journal(audit or AUDIT/'logs.jsonl'))


async def support(registry, channel, bot_id, policy, now=None, audit=None):
    if policy.get('support_enabled') is not True:
        return {'enabled': False, 'removed': 0}
    if str(channel.id) != str(policy.get('support_channel')):
        raise ValueError('Support channel differs from the approved private scope')
    now = now or datetime.now(timezone.utc).isoformat()
    plan = support_plan(registry, channel.id, now)
    provider = TrackedSupport(registry, channel, bot_id)
    result = await apply(plan, digest(plan), now, provider, Journal(audit or AUDIT/'support.jsonl'))
    snapshots = {entry['request']: entry['snapshot'] for entry in plan['entries']}
    for request, snapshot in snapshots.items():
        if any([await provider.message(message) is not None for message in snapshot['messages']]):
            raise ValueError('Tracked support message remains')
        registry.forget(request, snapshot)
    return result


def main():
    if os.geteuid() != 0:
        raise ValueError('Run the scoped log runner as root')
    import fcntl
    with open('/run/holylois-log-retention.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        policy = load_policy()
        ensure_audit()
        print(json.dumps(asyncio.run(logs(policy)), sort_keys=True))


if __name__ == '__main__':
    main()
