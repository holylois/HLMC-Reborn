"""Fixed production pre-start entrypoint. Prepared only, no installation or service control.

Empty ledgers keep the conservative normal path. Nonempty ledgers require a separately pinned complete private
review, actual native verifiers, exact current checkpoints and original backup/case objects. No dynamic plugin,
arbitrary command, config path flag, clear-request operation or persisted success permit.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from guard_checkpoint import Drive
from guard_snapshot import private_read
from privacy_actions import private_directory
from privacy_backup import StoppedSet, ReadOnlyDrive as BackupDrive
from privacy_bindings import Bindings, VERIFIERS, service_lease, own_prestart
from privacy_evidence import Evidence, ReadOnlyDrive as EvidenceDrive
from privacy_exports import unique
from privacy_review import digest, sha
from privacy_start import checked_start
from recovery_guard import Guard

CONFIG = Path('/var/lib/holylois/privacy-startup/review.json')
PIN = Path('/etc/holylois/privacy-startup.sha256')
TOKEN = Path('/etc/holylois/discord-bot-token')
KEYS = {'schema', 'root', 'guard', 'cases', 'scopes', 'mods', 'sources', 'native', 'policy', 'checkpoints', 'backup', 'evidence'}
NATIVE = {'auth_path', 'auth_table', 'public_paths', 'world_paths', 'outside_exports', 'http_urls', 'audit_path', 'discord'}


def registry(cfg, lease, *, discord_get=None, http_get=None):
    from privacy_native.runtime_guard import RuntimePins, REQUIRED
    from privacy_native.bindings import bind_native
    from privacy_native.discord_scope import DiscordGET, DiscordScope
    from privacy_native.public_http import HTTPExports
    n = cfg['native']; d = n['discord']
    if set(n) != NATIVE or set(d) != {'guild', 'channels', 'canary', 'content_sha256', 'max_pages'}:
        raise ValueError('Exact native storage and Discord coverage required')
    sha(d['content_sha256'])
    if discord_get is None:
        def discord_get(path):
            token = private_read(TOKEN, 16384).decode('utf-8').strip()
            if not token or any(c.isspace() for c in token): raise ValueError('Protected bot credential required')
            return DiscordGET(token)(path)
    scope = DiscordScope(discord_get, d['guild'], d['channels'], tuple(d['canary']), d['content_sha256'], lease, d['max_pages'])
    pins = RuntimePins({k: cfg['sources'][k] for k in REQUIRED},
                       {'directory': str(Path(cfg['root']) / 'mods'), 'files': cfg['mods']})
    http = HTTPExports(n['http_urls']) if http_get is None else HTTPExports(n['http_urls'], get=http_get)
    return bind_native(cfg['root'], n['auth_path'], n['auth_table'], lease, pins, n['public_paths'], scope,
                       n['world_paths'], n['outside_exports'], http, n['audit_path'])


def reviewed_start(guard, config, pin, lease, *, guard_provider=None, backup_provider=None, evidence_provider=None,
                   discord_get=None, http_get=None):
    """Explicit library paths for isolated tests; the actual CLI below accepts no overrides."""
    config, pin = Path(config).absolute(), Path(pin).absolute()
    private_directory(config.parent); private_directory(pin.parent)
    if config.is_relative_to(guard.root) or pin.is_relative_to(guard.root) or config == pin:
        raise ValueError('Independent review and pin must survive server restoration')
    raw = private_read(config, 4_000_000); pin_raw = private_read(pin, 100)
    if hashlib.sha256(raw).hexdigest() != sha(pin_raw.decode('ascii').strip()):
        raise ValueError('Private startup review differs from independent approved pin')
    cfg = json.loads(raw, object_pairs_hook=unique)
    if (set(cfg) != KEYS or cfg['schema'] != 1 or cfg['root'] != str(guard.root)
            or cfg['guard'] != str(guard.directory) or lease() is not True):
        raise ValueError('Exact current production binding and maintenance lease required')
    actual = Path(__file__).resolve().parent
    for name in VERIFIERS:
        if Path(cfg['sources']['verifier:' + name]['path']) != actual / 'privacy_native' / (name + '.py'):
            raise ValueError('Native verifier binding must identify the code actually executed')
    for role, filename in (('prestart', 'privacy_prestart.py'), ('restore', 'privacy_restore.py'),
                           ('bindings', 'privacy_bindings.py'), ('startup', 'privacy_start.py'),
                           ('evidence', 'privacy_evidence.py'), ('backup-reader', 'privacy_backup.py')):
        if Path(cfg['sources'][role]['path']) != actual / filename:
            raise ValueError('Startup source binding must identify the code actually executed')
    gp = Drive() if guard_provider is None else guard_provider
    bp = BackupDrive() if backup_provider is None else backup_provider
    ep = EvidenceDrive() if evidence_provider is None else evidence_provider
    adapters = registry(cfg, lease, discord_get=discord_get, http_get=http_get)
    bindings = Bindings(guard.root, cfg['mods'], cfg['sources'], adapters, digest(cfg['scopes']))
    # Config, independent pin and lease are included in every current code observation.
    def current():
        if (private_read(config, 4_000_000) != raw or private_read(pin, 100) != pin_raw or lease() is not True):
            raise ValueError('Current private startup binding changed')
        return bindings.check()
    current()
    b = cfg['backup']; e = cfg['evidence']
    if set(b) != {'directory', 'original', 'original_sha256', 'archive_sha256'} or set(e) != {
            'directory', 'index', 'index_sha256', 'decisions', 'transactions'}:
        raise ValueError('Exact independent recovery bindings required')
    backup = StoppedSet(guard.root, b['directory'], b['original'], b['original_sha256'], bp)
    evidence = Evidence(e['directory'], e['index'], e['index_sha256'], e['decisions'], e['transactions'], ep)
    result = checked_start(guard, cfg['checkpoints'], gp, cfg['cases'], adapters, lease, current,
        policy_path=cfg['policy'], scopes=cfg['scopes'], backup_sha256=b['archive_sha256'],
        verified_stopped_backup=backup.verify, verified_scope=evidence.verify_scope,
        verified_private_recovery=evidence.verify_recovery)
    return result


def dispatch(guard, config, pin, *, unit='minecraft.service', pid=None, invocation=None, run=subprocess.run):
    pid = os.getpid() if pid is None else pid
    invocation = os.environ.get('INVOCATION_ID', '') if invocation is None else invocation
    if not own_prestart(unit, pid, invocation, run): raise ValueError('Actual current systemd pre-start context required')
    with guard.locked(): state = guard.state()
    if not state['requests']: return guard.start()
    if unit != 'minecraft.service': raise ValueError('Production review is bound to the game unit')
    lease = lambda: service_lease(run, prestart=(unit, pid, invocation))
    return reviewed_start(guard, config, pin, lease)


def main():
    if os.geteuid() != 0 or len(sys.argv) != 1: raise ValueError('Fixed privileged entrypoint accepts no overrides')
    return dispatch(Guard(), CONFIG, PIN)


if __name__ == '__main__':
    try:
        main(); print(json.dumps({'allow_start': True, 'requests_cleared': 0, 'uploaded': False}))
    except Exception:
        raise SystemExit('Privacy startup blocked; preserve private state and review the operator guide.') from None
