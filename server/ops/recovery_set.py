"""Attest stopped, whole-server recovery sets. No service changes, uploads or deletion."""
import json
import subprocess
import tarfile

WRITERS = ('minecraft.service', 'holylois-stats.service', 'holylois-botwall.service', 'holylois-terrain-expansion.service')


def require_stopped():
    for unit in WRITERS:
        result = subprocess.run(['systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'MainPID', '-p', 'ControlPID'],
                                check=True, capture_output=True, text=True)
        state = dict(row.split('=', 1) for row in result.stdout.splitlines() if '=' in row)
        if state.get('ActiveState') not in ('inactive', 'failed') or state.get('MainPID') != '0' or state.get('ControlPID') != '0':
            raise RuntimeError('Recovery set requires all known game-data writers stopped')


def attest(archive, root, digest, size):
    """Called after tar comparison, while the deployment lock and stopped writers are still held."""
    require_stopped()
    with tarfile.open(archive) as tar:
        rows = tar.getmembers()
        names = {row.name for row in rows}
        for scope in ('world', 'config', 'mods', 'EasyAuth'):
            member = root.name + '/' + scope
            if member not in names or not tar.getmember(member).isdir():
                raise ValueError('Complete recovery scope is missing or linked')
        if any(row.name.startswith(root.name + '/backups/') or row.name.startswith(root.name + '/bluemap/') for row in rows):
            raise ValueError('Recovery archive includes excluded recursive/rebuildable data')
    return {'schema': 1, 'kind': 'stopped-server', 'archive_sha256': digest, 'archive_bytes': size,
            'application_consistent': True, 'writers_checked': list(WRITERS), 'comparison_verified': True,
            'world_and_external_account_config_same_stop': True,
            'includes': ['world and player progress', 'account database and sidecars', 'permissions and economy',
                         'configuration', 'mods and server software'],
            'excludes': ['recursive backup archives', 'rebuildable BlueMap tiles'],
            'offsite_verified': False, 'restore_boot_verified': False, 'expiry_eligible': False}


def save(folder, receipt):
    target = folder / 'recovery-set.json'
    with target.open('x', encoding='utf-8') as output:
        import os
        os.chmod(target, 0o600)
        json.dump(receipt, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
