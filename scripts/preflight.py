"""One release preflight for the public repos: versions named in the docs, no private data, no em dash in tracked text,
and the newest release notes equal the copy embedded in the launcher (HLMC-Reborn-Packaging-Lab next to this repo).

  python scripts/preflight.py          exit 0 = all passed; each failing check is listed
Pack signatures, launcher builds and server rehearsals stay separate steps (RELEASE-CHECKLIST.md).
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT.parent / 'HLMC-Reborn-Packaging-Lab'
TEXT = {'.md', '.txt', '.json', '.py', '.toml', '.cs', '.xaml', '.java', '.ts', '.tsx', '.ps1', '.properties', '.conf', '.yml', '.yaml'}


def tracked(repo):
    out = subprocess.run(['git', '-C', str(repo), 'ls-files'], capture_output=True, text=True, check=True).stdout
    return [repo / line for line in out.splitlines() if Path(line).suffix.lower() in TEXT]


def run(name, args):
    result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)
    print(('PASS ' if result.returncode == 0 else 'FAIL ') + name)
    if result.returncode: print('   ' + (result.stdout + result.stderr).strip().replace('\n', '\n   ')[-1500:])
    return result.returncode == 0


def no_dash():
    bad = []
    for repo in (ROOT, LAB):
        if not repo.exists(): continue
        for path in tracked(repo):
            try:
                if chr(0x2014) in path.read_text(encoding='utf-8'): bad.append(str(path.relative_to(repo.parent)))
            except (UnicodeDecodeError, OSError):
                continue
    print(('PASS ' if not bad else 'FAIL ') + 'no em dash in tracked text')
    for path in bad[:20]: print('   ' + path)
    return not bad


def notes_embedded():
    notes = sorted((ROOT / 'release-notes').glob('*.json'), key=lambda p: tuple(int(x) for x in p.stem.split('.')))
    newest = json.loads(notes[-1].read_text(encoding='utf-8'))
    embedded = LAB / 'assets/player-notes.json'
    if not embedded.exists():
        print('SKIP launcher notes (no Lab checkout)')
        return True

    def find(node):
        if isinstance(node, dict):
            if node.get('version') == newest['version'] and 'locales' in node: return node
            node = list(node.values())
        if isinstance(node, list):
            for item in node:
                hit = find(item)
                if hit: return hit
        return None

    same = find(json.loads(embedded.read_text(encoding='utf-8'))) == newest
    print(('PASS ' if same else 'FAIL ') + f'launcher embeds release notes {newest["version"]}')
    return same


def main():
    results = [run('docs name the current versions', ['scripts/check_versions.py']),
               run('no private data in tracked files', ['scripts/check_public_data.py', *map(str, tracked(ROOT))]),
               no_dash(), notes_embedded()]
    print('preflight ' + ('passed' if all(results) else 'FAILED'))
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
