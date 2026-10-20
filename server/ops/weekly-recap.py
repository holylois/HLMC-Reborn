"""Sunday evening Discord recap of the Holy Lois week: who played most, best miners and fighters, discoveries.

Compares the vanilla stats files with last week's snapshot (/var/lib/holylois/weekly-stats.json). The first run
only saves the snapshot. A quiet week (nobody played) posts nothing. Uses the monitor's webhook.
"""
import importlib.util, json, time
from pathlib import Path
from privacy_exports import load as load_policy, excluded, require_same, POLICY
from recovery_guard import Guard

ROOT = Path("/opt/minecraft")
STATS = ROOT / "world/players/stats"
USERS = ROOT / "usercache.json"
DISCOVERIES = ROOT / "world/holylois/discoveries.json"
AFK = ROOT / "world/holylois/afk.json"  # AFK seconds per player (onboarding add-on): not counted as played time
SNAPSHOT = Path("/var/lib/holylois/weekly-stats.json")

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded)
    return loaded


def numbers(stats, afk_seconds=0):
    custom, mined = stats.get("minecraft:custom", {}), stats.get("minecraft:mined", {})
    return {
        "hours": max(0.0, custom.get("minecraft:play_time", 0) / 72000 - afk_seconds / 3600),
        "kills": custom.get("minecraft:mob_kills", 0),
        "deaths": custom.get("minecraft:deaths", 0),
        "diamonds": mined.get("minecraft:diamond_ore", 0) + mined.get("minecraft:deepslate_diamond_ore", 0),
        "debris": mined.get("minecraft:ancient_debris", 0),
        "blocks": sum(mined.values()),
        "km": sum(v for k, v in custom.items() if k.endswith("_one_cm") and "fall" not in k) / 100000,
    }


def current(policy):
    names = {u["uuid"]: u["name"] for u in json.loads(USERS.read_text())} if USERS.exists() else {}
    afk = {}
    try: afk = json.loads(AFK.read_text()).get("seconds", {}) if AFK.exists() else {}
    except ValueError: pass
    result = {}
    for file in STATS.glob("*.json"):
        if excluded(policy, file.stem, names.get(file.stem, '')): continue
        try:
            result[names.get(file.stem, file.stem[:8])] = numbers(json.loads(file.read_text()).get("stats", {}), afk.get(file.stem, 0))
        except ValueError:
            continue
    return result


def best(delta, key, unit, digits=0):
    ranked = sorted(((v[key], name) for name, v in delta.items() if v[key] > 0), reverse=True)[:3]
    if not ranked:
        return None
    return "\n".join(f"{['🥇', '🥈', '🥉'][i]} {name} - {value:,.{digits}f}{unit}" for i, (value, name) in enumerate(ranked))


def main():
    guard = Guard(); policy, gate_raw = load_policy(guard, POLICY)
    stats_names = module('stats', '/usr/local/lib/holylois/make-stats.py')
    now, last = current(policy), json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else None
    require_same(guard, POLICY, policy, gate_raw)
    SNAPSHOT.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    guard._atomic(SNAPSHOT, {"time": time.time(), "players": now})
    if last is None:
        print("First run: snapshot saved, the first recap comes next week.")
        return
    before = last["players"]
    delta = {name: {k: v - before.get(name, {}).get(k, 0) for k, v in stats.items()} for name, stats in now.items()}
    _, shown = stats_names.names(policy)  # raw name -> public name; hidden/suppressed accounts are missing
    delta = {shown[name]: d for name, d in delta.items() if d["hours"] >= 0.05 and name in shown}
    if not delta:
        print("Nobody played this week; no recap.")
        return
    found = []
    if DISCOVERIES.exists():
        found = [dict(f, player=shown[f.get("player")]) for f in json.loads(DISCOVERIES.read_text()).get("found", [])
                 if f.get("time", 0) >= last["time"] and f.get("player") in shown
                 and not excluded(policy, f.get('uuid'), f.get('player'))]
    fields = []
    for title, key, unit, digits in [("Most played", "hours", " h", 1), ("Diamonds mined", "diamonds", "", 0),
                                     ("Mob kills", "kills", "", 0), ("Blocks mined", "blocks", "", 0),
                                     ("Distance travelled", "km", " km", 1), ("Ancient debris", "debris", "", 0),
                                     ("Most deaths", "deaths", "", 0)]:
        text = best(delta, key, unit, digits)
        if text:
            fields.append((title, text))
    if found:
        lines = [f"{f['player']} found {'an' if f['name'][0] in 'AEIOU' else 'a'} {f['name']}" for f in found[-10:]]
        fields.append((f"Discoveries ({len(found)})", "\n".join(lines)))
    total = sum(d["hours"] for d in delta.values())
    assert not any(stats_names.SLURS.search(v) for _, v in fields), "A filtered name reached the recap"
    require_same(guard, POLICY, policy, gate_raw)
    alert = module('alert', '/usr/local/lib/holylois/discord-alert.py')
    alert.post("Holy Lois weekly recap", f"{len(delta)} player(s) played {total:.1f} hours this week.", alert.GOLD, fields)
    print("Recap posted.")


if __name__ == "__main__":
    main()
