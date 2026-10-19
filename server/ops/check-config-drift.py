#!/usr/bin/env python3
"""Live server config vs this repository: lists every tracked config whose live bytes differ, with a short diff.

A redeploy from git must never silently undo a live decision (the OPAC claim expiry drifted to 8760 h in git while live was
720 h). Read-only. Usage on the server, from an uploaded copy of HLMC-Reborn/server:
  sudo python3 ops/check-config-drift.py [SERVER_DIR]      exit 0 = in sync, 1 = drift (diff printed), 2 = missing files
"""
import difflib, sys
from pathlib import Path

HERE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
LIVE = Path('/opt/minecraft')
# repo file -> live candidates (first that exists is compared)
TRACKED = {
    'opac/openpartiesandclaims-server.toml': ['config/openpartiesandclaims-server.toml', 'world/serverconfig/openpartiesandclaims-server.toml'],
    'easy/easyanvils-server.toml': ['config/easyanvils-server.toml'],
    'easy/easymagic-server.toml': ['config/easymagic-server.toml'],
    'legends/holylois-fish.json': ['config/holylois-fish.json'],
    'legends/holylois-legends.json': ['config/holylois-legends.json'],
    'rules/rules.txt': ['config/essentialcommands/rules.txt'],
    'stats/holylois-quiet.json': ['config/holylois-quiet.json'],
    'stats/holylois-stats-hidden.json': ['config/holylois-stats-hidden.json'],
    'styledplayerlist/config.json': ['config/styledplayerlist/config.json'],
}


def lines(path):
    return path.read_bytes().decode('utf-8', 'replace').replace('\r\n', '\n').splitlines()


def main():
    drift = missing = 0
    for repo, candidates in TRACKED.items():
        source = HERE / repo
        live = next((LIVE / c for c in candidates if (LIVE / c).exists()), None)
        if not source.exists() or live is None:
            print(f'MISSING {repo}: repo={source.exists()} live={live is not None}')
            missing += 1
            continue
        a, b = lines(source), lines(live)
        if a == b:
            print(f'ok      {repo}')
            continue
        drift += 1
        print(f'DRIFT   {repo} <-> {live}')
        for line in list(difflib.unified_diff(a, b, 'git', 'live', n=0, lineterm=''))[2:42]:
            print('   ', line)
    print(f'{len(TRACKED)} tracked, {drift} drifted, {missing} missing')
    return 2 if missing else 1 if drift else 0


if __name__ == '__main__':
    sys.exit(main())
