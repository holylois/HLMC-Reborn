"""Release docs name the current versions: the newest release-notes/*.json pack version must appear in README.md,
PLAYER-GUIDE.md and CHANGELOG.md, and README and PLAYER-GUIDE must name the same launcher version.

  python scripts/check_versions.py
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def key(version):
    return tuple(int(part) for part in version.split('.'))


def main():
    notes = [json.loads(p.read_text(encoding='utf-8'))['version'] for p in (ROOT / 'release-notes').glob('*.json')]
    pack = max(notes, key=key)
    problems = []
    texts = {name: (ROOT / name).read_text(encoding='utf-8') for name in ('README.md', 'PLAYER-GUIDE.md', 'CHANGELOG.md')}
    for name, text in texts.items():
        if not re.search(r'\bpack ' + re.escape(pack) + r'\b', text, re.I):
            problems.append(f'{name} does not mention pack {pack}')
    launchers = {name: re.search(r'\blauncher (\d+\.\d+\.\d+)', texts[name][:600], re.I) for name in ('README.md', 'PLAYER-GUIDE.md')}
    found = {name: m.group(1) if m else None for name, m in launchers.items()}
    if None in found.values() or len(set(found.values())) != 1:
        problems.append(f'README.md and PLAYER-GUIDE.md name different launcher versions near the top: {found}')
    for problem in problems: print(problem)
    if problems: sys.exit(1)
    print(f'Release docs name pack {pack} and launcher {next(iter(found.values()))}.')


if __name__ == '__main__':
    main()
