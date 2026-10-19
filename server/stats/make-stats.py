"""Public server stats for holylois.com, written as one JSON file (read-only on the world).

Sources: vanilla stats and advancement files, usercache.json, the Holy Lois datapack (titles), discoveries, daily
streaks, EconomyCraft balances and the published pack changelog. Only usernames and game numbers leave the server: no UUIDs, IPs or coordinates.
Names with slurs are masked (first letter + stars, the row stays); names listed in /etc/holylois/stats-hidden.txt never appear.
Usage: python3 make-stats.py [SERVER_ROOT] OUTPUT_JSON
"""
import datetime, json, os, re, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 2 else Path('/opt/minecraft')
OUT = Path(sys.argv[-1])
WORLD = ROOT / 'world'
HIDDEN_FILE = Path('/etc/holylois/stats-hidden.txt')
HIDDEN_CONFIG = ROOT / 'config/holylois-stats-hidden.json'
# Number and letter swaps count too (N1663R, owner 2026-10-19). Same pattern in onboarding StatsVisibility and extras PartySupport.
SLURS = re.compile(r'n[i1!|l][g6q9]{2}|f[a@4][g6q9]{1,2}[o0]t|f[a@4][g6q9]$|r[e3]t[a@4]rd|p[i1!]d[o0a]r|k[i1!]ke|ch[i1!]nk|tr[a@4]nn(?:y|ie)|п[иі]д[оа]р', re.I)
TOP = 5
PACK_FEED = 'https://github.com/holylois/HLMC-Reborn/releases/download/pack-stable/pack.json'


def read(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return default


def mask(name):
    """Keep the row but never the word: 'N*****'. Fixed length, so the mask does not hint at the original."""
    return name[0].upper() + '*****'


def hidden_names():
    hidden = {line.strip().lower() for line in HIDDEN_FILE.read_text().splitlines() if line.strip()} if HIDDEN_FILE.exists() else set()
    hidden.update({'pjampjam', 'pjamtest', 'pjanpjan'})
    hidden.update(name.lower() for name in read(HIDDEN_CONFIG, {}).get('names', []) if isinstance(name, str))
    return hidden


def names():
    hidden = hidden_names()
    profiles = read(WORLD / 'holylois' / 'account-profile-names.json', {})
    canonical = profiles.get('names', {})
    hidden_ids = {identity for alias, identity in profiles.get('aliases', {}).items() if alias.lower() in hidden}
    result, raw = {}, {}
    for entry in read(ROOT / 'usercache.json', []):
        original = entry.get('name', '')
        identity = entry.get('uuid', '')
        name = canonical.get(identity, original)
        if not name or name.lower() in hidden or original.lower() in hidden or identity in hidden_ids: continue
        if identity in result:
            raw[original] = result[identity]
            continue
        shown = mask(name) if SLURS.search(name) else name
        while shown in result.values(): shown += '*'
        result[identity] = shown; raw[original] = shown; raw[name] = shown
    return result, raw


def online_now():
    """Players online right now as the public sees them (staff hidden: the ping names play.holylois.com), None if no answer."""
    import socket, struct
    def varint(n):
        out = b''
        while True:
            byte, n = n & 0x7f, n >> 7
            out += bytes([byte | (0x80 if n else 0)])
            if not n: return out
    try:
        with socket.create_connection(('127.0.0.1', 25565), 5) as s:
            hello = b'\x00' + varint(770) + varint(17) + b'play.holylois.com' + struct.pack('>H', 25565) + varint(1)
            s.sendall(varint(len(hello)) + hello + b'\x01\x00')
            data = b''
            while chunk := s.recv(65536):
                data += chunk
                try: return json.loads(data[data.index(b'{'):].decode())['players']['online']
                except ValueError: continue
    except (OSError, KeyError):
        return None


def holylois_advancements():
    # Since 2.2.0 titles are {"translate": key, "fallback": English}: the site shows the English fallback.
    def plain(value, default):
        if isinstance(value, dict): return value.get('fallback') or value.get('text') or default
        return value if isinstance(value, str) else default
    base = WORLD / 'datapacks/holylois-advancements/data/holylois/advancement'
    found = {}
    for file in sorted(base.rglob('*.json')):
        data = read(file, {})
        display = data.get('display')
        path = file.relative_to(base).with_suffix('').as_posix()
        if display and path != 'root':
            found['holylois:' + path] = {'title': plain(display.get('title'), path), 'description': plain(display.get('description'), ''),
                                         'secret': bool(display.get('hidden')), 'frame': display.get('frame', 'task')}
    return found


def visible_advancements():
    """Ids of advancements that show in the advancement screen: definitions with a display block, read from the vanilla jar,
    the mod jars and the world datapacks. Many mods add display-less advancements as hidden triggers and every tab has a
    root that is granted on join; counting those made "All advancements" far higher than what players can see.
    Returns an empty set if no definitions were found, so the caller can fall back to counting everything."""
    import zipfile
    pattern = re.compile(r'^data/([a-z0-9_.-]+)/advancements?/(.+)\.json$')
    found = set()

    def take(name, load):
        match = pattern.match(name)
        if not match: return
        try: data = json.loads(load())
        except (ValueError, UnicodeDecodeError, OSError, KeyError): return
        if isinstance(data, dict) and isinstance(data.get('display'), dict): found.add(match.group(1) + ':' + match.group(2))

    packs = WORLD / 'datapacks'
    archives = [*(ROOT / 'mods').glob('*.jar'), *(ROOT / 'versions').rglob('*.jar'), *(packs.glob('*.zip') if packs.is_dir() else [])]
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist(): take(name, lambda n=name: z.read(n))
        except (OSError, zipfile.BadZipFile): continue
    for pack in (packs.iterdir() if packs.is_dir() else []):
        if pack.is_dir():
            for file in pack.rglob('*.json'): take(file.relative_to(pack).as_posix(), file.read_bytes)
    return found


def when(text):
    try: return datetime.datetime.strptime(text, '%Y-%m-%d %H:%M:%S %z').astimezone(datetime.timezone.utc)
    except (TypeError, ValueError): return None


def taken_names():
    """Every name the server already knows (joined names, renamed accounts' old and new names, staff), lower case. Written next to
    stats.json but never served whole: stats-web only answers "is this one name taken" for the launcher's name check."""
    profiles = read(WORLD / 'holylois' / 'account-profile-names.json', {})
    taken = {e.get('name', '').lower() for e in read(ROOT / 'usercache.json', []) if isinstance(e, dict)}
    taken.update(n.lower() for n in profiles.get('names', {}).values() if isinstance(n, str))
    taken.update(a.lower() for a in profiles.get('aliases', {}) if isinstance(a, str))
    taken.update(hidden_names())
    return sorted(n for n in taken if re.fullmatch(r'[a-z0-9_]{3,16}', n))


def main():
    people, shown_as = names()
    stats, done = {}, {}
    for file in (WORLD / 'players/stats').glob('*.json'):
        if file.stem in people: stats[file.stem] = read(file, {}).get('stats', {})
    # AFK time does not count as played (ledger of the onboarding add-on, 20 ticks per AFK second).
    afk = read(WORLD / 'holylois/afk.json', {}).get('seconds', {})
    for uuid, mine in stats.items():
        played = mine.get('minecraft:custom', {})
        if uuid in afk and 'minecraft:play_time' in played: played['minecraft:play_time'] = max(0, played['minecraft:play_time'] - afk[uuid] * 20)
    visible = visible_advancements()
    for file in (WORLD / 'players/advancements').glob('*.json'):
        if file.stem not in people: continue
        mine = {}
        for key, value in read(file, {}).items():
            if not (isinstance(value, dict) and value.get('done')): continue
            if (key in visible) if visible else (not key.startswith('minecraft:recipes/') and '/recipes/' not in key):
                times = [t for t in map(when, value.get('criteria', {}).values()) if t]
                mine[key] = max(times) if times else None
        done[file.stem] = mine

    custom = lambda uuid, key: stats.get(uuid, {}).get('minecraft:custom', {}).get('minecraft:' + key, 0)
    group = lambda uuid, kind: stats.get(uuid, {}).get('minecraft:' + kind, {})
    distance = lambda uuid: sum(v for k, v in group(uuid, 'custom').items() if k.endswith('_one_cm') and 'fall' not in k) / 100_000
    diamonds = lambda uuid: sum(v for k, v in group(uuid, 'mined').items() if k.endswith('diamond_ore'))
    defined = holylois_advancements()
    holy = lambda uuid: sum(1 for key in done.get(uuid, {}) if key in defined)
    daily = read(WORLD / 'holylois/daily.json', {}).get('players', {})
    coins = read(ROOT / 'config/economycraft/data/balances.json', {})

    boards = [
        ('playtime', 'Most time played', 'hours', lambda u: round(custom(u, 'play_time') / 72000, 1)),
        ('achievements', 'Holy Lois achievements', f'of {len(defined)}', holy),
        ('advancements', 'All advancements', 'done', lambda u: len(done.get(u, {}))),
        ('diamonds', 'Diamonds mined', 'ores', diamonds),
        ('distance', 'Distance travelled', 'km', lambda u: round(distance(u), 1)),
        ('mobs', 'Mobs defeated', 'mobs', lambda u: custom(u, 'mob_kills')),
        ('fish', 'Fish caught', 'fish', lambda u: custom(u, 'fish_caught')),
        ('blocks', 'Blocks mined', 'blocks', lambda u: sum(group(u, 'mined').values())),
        ('streak', 'Longest daily streak', 'days', lambda u: daily.get(u, {}).get('best', 0)),
        ('coins', 'Richest', 'coins', lambda u: coins.get(u, 0)),
        ('deaths', 'Most deaths', 'deaths', lambda u: custom(u, 'deaths')),
    ]
    leaderboards = []
    for key, title, unit, value in boards:
        rows = sorted(((people[u], value(u)) for u in people if u in stats or u in done or u in daily or u in coins), key=lambda r: (-r[1], r[0].lower()))
        rows = [{'name': n, 'value': v} for n, v in rows if v][:TOP]
        if rows: leaderboards.append({'id': key, 'title': title, 'unit': unit, 'entries': rows})

    achievements = []
    for key, info in defined.items():
        earners = sorted(((t, people[u]) for u, mine in done.items() if key in mine for t in [mine[key]]), key=lambda r: (r[0] is None, r[0] or 0))
        known = bool(earners) or not info['secret']
        achievements.append({'id': key, 'title': info['title'] if known else 'Secret achievement',
                             'description': info['description'] if known else 'Nobody has found this one yet.',
                             'frame': info['frame'], 'secret': info['secret'], 'earned_by': len(earners),
                             'first': {'name': earners[0][1], 'date': earners[0][0].date().isoformat() if earners[0][0] else None} if earners else None})
    achievements.sort(key=lambda a: (-a['earned_by'], a['title']))
    earned = [a for a in achievements if a['earned_by']]
    rarest = sorted(earned, key=lambda a: (a['earned_by'], a['first']['date'] or ''))[:3]

    # World firsts: the first find of each structure kind (onboarding Discoveries v2 marks it; v1 files: first by name and time)
    # with a BlueMap link, plus boss and Runeforged elite/level firsts.
    firsts = []
    hidden = hidden_names()
    discoveries = read(WORLD / 'holylois/discoveries.json', {})
    maps = {'minecraft:overworld': 'world', 'minecraft:the_nether': 'world_the_nether', 'minecraft:the_end': 'world_the_end'}
    def day(entry):
        return datetime.datetime.fromtimestamp(entry.get('time', 0), datetime.timezone.utc).date().isoformat()
    def link(entry):
        world = maps.get(entry.get('dim') or 'minecraft:overworld')
        return f"https://map.holylois.com/#{world}:{entry.get('x', 0)}:{entry.get('y', 64)}:{entry.get('z', 0)}:120:0:0:0:1:flat" if world else ''
    seen = set()
    for entry in sorted(discoveries.get('found', []), key=lambda e: e.get('time', 0)):
        kind = entry.get('name', '')
        first = entry['first'] if 'first' in entry else kind not in seen
        seen.add(kind)
        name = entry.get('player', '')
        if not first or name.lower() in hidden: continue
        firsts.append({'what': kind, 'player': shown_as.get(name, 'Someone'), 'date': day(entry), 'map': link(entry) if 'x' in entry or 'first' in entry else ''})
    for entry in discoveries.get('firsts', []):
        name = entry.get('player', '')
        if name.lower() in hidden: continue
        what = entry.get('what', '')
        firsts.append({'what': what[:1].upper() + what[1:], 'player': shown_as.get(name, 'Someone'), 'date': day(entry), 'map': ''})
    firsts.sort(key=lambda f: f['date'], reverse=True)

    # The live pack's own changelog, so the website's update list follows each release by itself.
    pack = (read(OUT, {}) or {}).get('pack')
    try:
        # Mutable release asset redirects can stay cached after a stable-channel move.
        fresh = PACK_FEED + '?check=' + str(int(datetime.datetime.now(datetime.timezone.utc).timestamp()))
        request = urllib.request.Request(fresh, headers={'Cache-Control': 'no-cache'})
        manifest = json.loads(urllib.request.urlopen(request, timeout=15).read())
        pack = {'version': manifest['version'], 'history': manifest.get('history', [])[:8]}
    except Exception:
        pass

    everyone = list(stats)
    skin_textures = read(WORLD / 'holylois/skin-textures.json', {})
    report = {
        'pack': pack,
        'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        # 'players' is everyone who has joined (kept for old readers); 'online' is a live ping at generation time.
        'server': {'address': 'play.holylois.com', 'players': len(people), 'registered_players': len(people), 'online': online_now(), 'world_day': read(WORLD / 'holylois/events.json', {}).get('lastDay')},
        'totals': {
            'hours_played': round(sum(custom(u, 'play_time') for u in everyone) / 72000),
            'km_travelled': round(sum(distance(u) for u in everyone)),
            'blocks_mined': sum(sum(group(u, 'mined').values()) for u in everyone),
            'mobs_defeated': sum(custom(u, 'mob_kills') for u in everyone),
            'diamonds': sum(diamonds(u) for u in everyone),
            'fish_caught': sum(custom(u, 'fish_caught') for u in everyone),
            'deaths': sum(custom(u, 'deaths') for u in everyone),
            'cake_slices': sum(custom(u, 'eat_cake_slice') for u in everyone),
            'achievements_earned': sum(a['earned_by'] for a in achievements),
        },
        'heads': {name: texture for uid, name in people.items()
                  for texture in [skin_textures.get(uid)]
                  if isinstance(texture, str) and re.fullmatch(r'https://textures\.minecraft\.net/texture/[a-fA-F0-9]{32,128}', texture) and not SLURS.search(name)},
        'leaderboards': leaderboards,
        'achievements': {'total': len(defined), 'rarest': rarest, 'list': achievements},
        'world_firsts': firsts[:20],
    }
    text = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    assert not SLURS.search(text), 'A filtered name reached the output'
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=OUT.parent, delete=False, encoding='utf-8') as temp: temp.write(text)
    os.chmod(temp.name, 0o644); os.replace(temp.name, OUT)
    taken = OUT.parent / 'taken-names.json'
    with tempfile.NamedTemporaryFile('w', dir=OUT.parent, delete=False, encoding='utf-8') as temp: json.dump({'names': taken_names()}, temp)
    os.chmod(temp.name, 0o644); os.replace(temp.name, taken)
    print(f'{OUT}: {len(people)} players, {len(leaderboards)} boards, {len(earned)}/{len(defined)} achievements earned, {len(firsts)} world firsts')


if __name__ == '__main__':
    main()
