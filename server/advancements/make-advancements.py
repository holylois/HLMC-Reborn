"""Generate the Holy Lois advancement tab (world datapack holylois-advancements).

Vanilla triggers cover structures, food and holiday blocks. Seats, distance, playtime, streaks, lootboxes and
first discoveries use "minecraft:impossible" criteria that the onboarding add-on awards. Legend items, bottle messages and fish
trophies (Holy Lois Extras 1.6.0) are found by their custom_data; the legends come from ../legends/holylois-legends.json.
Usage: python make-advancements.py OUTPUT_DIR
"""
import json, shutil, sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "holylois-advancements")
WOODS = ["oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak", "crimson", "warped", "poplar"]
NS = "nova_structures"

# Grand Tour: every notable Dungeons and Taverns site, grouped so variants count once.
TOUR = {
    "tavern": [f"{NS}:tavern_{w}" for w in ["acacia", "birch", "cherry", "dappled", "dark_oak", "desert", "jungle", "mangrove", "oak", "pale", "snowy", "spruce", "swamp"]],
    "undead_crypt": [f"{NS}:undead_crypt", f"{NS}:small_undead_crypt"],
    "creeping_crypt": [f"{NS}:creeping_crypt", f"{NS}:small_creeping_crypt"],
    "catacomb": [f"{NS}:catacomb"], "sealing_halls": [f"{NS}:sealing_halls"], "toxic_lair": [f"{NS}:toxic_lair"],
    "illager_manor": [f"{NS}:illager_manor"], "illager_hideout": [f"{NS}:illager_hideout"],
    "illager_barracks": [f"{NS}:illager_barracks"], "illager_treehouse": [f"{NS}:illager_treehouse"],
    "lone_citadel": [f"{NS}:lone_citadel"], "witch_villa": [f"{NS}:witch_villa"], "bunker": [f"{NS}:bunker"],
    "trial_dungeon": [f"{NS}:trial_dungeon"] + [f"{NS}:surface_trial_dungeon_{b}" for b in ["default", "desert", "snowy", "swamp"]],
    "combat_shrine": [f"{NS}:shrine_combat_tier_{i}" for i in range(1, 7)],
    "biome_shrine": [f"{NS}:shrine_biome_tier_{i}" for i in range(1, 6)] + [f"{NS}:shrine_tower"],
    "cave_chamber": [f"{NS}:cave_chamber", f"{NS}:cave_chamber_archeology_ruins", f"{NS}:cave_chamber_colony", f"{NS}:cave_chamber_dungeon_colony"],
    "stray_fort": [f"{NS}:stray_fort", f"{NS}:stray_outlook"], "pale_residence": [f"{NS}:pale_residence"],
    "ruin_town": [f"{NS}:ruin_town"], "miner_outpost": [f"{NS}:badlands_miner_outpost"],
    "nether_keep": [f"{NS}:nether_keep"], "piglin_donjon": [f"{NS}:piglin_donjon"], "nether_port": [f"{NS}:nether_port"],
    "end_castle": [f"{NS}:end_castle"], "end_ship": [f"{NS}:end_ship"],
}
# Epic Dungeons: underground dungeons in three biome styles and three sizes, plus the surface obelisks.
EPIC = {size: [f"epic:{size}_{style}_dungeon" if size != "large" or style != "plains" else "epic:large_dungeon" for style in ["plains", "ice", "sand"]] for size in ["small", "medium", "large"]}
EPIC_ALL = [s for group in EPIC.values() for s in group]
OBELISKS = [f"epic:{style}_obelisk" for style in ["plains", "ice", "sand"]]
FD = "farmersdelight"
MEALS = ["apple_cider", "apple_pie_slice", "bacon_and_eggs", "bacon_sandwich", "baked_cod_stew", "beef_stew", "cabbage_rolls",
         "chicken_sandwich", "chicken_soup", "chocolate_pie_slice", "cod_roll", "dumplings", "egg_sandwich", "fish_stew", "fried_egg",
         "fried_rice", "fruit_salad", "hamburger", "honey_cookie", "honey_glazed_ham", "hot_cocoa", "kelp_roll_slice", "melon_juice",
         "melon_popsicle", "mixed_salad", "mushroom_rice", "mutton_wrap", "nether_salad", "noodle_soup", "onion_soup",
         "pasta_with_meatballs", "pasta_with_mutton_chop", "pumpkin_pie_slice", "pumpkin_soup", "ratatouille", "roast_chicken",
         "salmon_roll", "shepherds_pie", "squid_ink_pasta", "steak_and_potatoes", "stuffed_potato", "stuffed_pumpkin",
         "sweet_berry_cheesecake_slice", "sweet_berry_cookie", "vegetable_noodles", "vegetable_soup"]
CHAIRS = ["chair", "modern_chair", "stool_chair", "striped_chair", "couch"]
TREE_TOPS = ["mcwholidays:christmas_tree_top"] + [f"mcwholidays:{c}_decorated_christmas_tree_top" for c in ["blue", "colorful", "green", "purple", "red", "yellow"]]


def location(structures):
    # Minecraft 26.3 format: typed predicates, as in the vanilla nether/find_fortress advancement.
    return {"trigger": "minecraft:location", "conditions": {"player": {"type": "minecraft:entity_properties", "entity": "this",
            "predicate": {"minecraft:location": {"structures": structures}}}}}


def eat(item):
    return {"trigger": "minecraft:consume_item", "conditions": {"item": {"items": item}}}


def impossible():
    return {"trigger": "minecraft:impossible"}


ADV = {}


def adv(path, parent, icon, title, description, criteria, frame="task", hidden=False, any_of=False, xp=0, toast=True):
    data = {"display": {"icon": {"id": icon}, "title": title, "description": description, "frame": frame,
                        "show_toast": toast, "announce_to_chat": toast, "hidden": hidden}, "criteria": criteria}
    if parent: data["parent"] = "holylois:" + parent
    if any_of: data["requirements"] = [list(criteria)]
    if xp: data["rewards"] = {"experience": xp}
    ADV[path] = data


root = {"display": {"icon": {"id": "minecraft:golden_helmet"}, "title": "Holy Lois: Reborn", "description": "Welcome home. Small goals and secret challenges.",
                    "frame": "task", "show_toast": False, "announce_to_chat": False, "hidden": False, "background": "minecraft:block/gilded_blackstone"},
        "criteria": {"joined": {"trigger": "minecraft:tick"}}}
ADV["root"] = root

all_sites = sorted({s for group in TOUR.values() for s in group})
adv("explore/off_the_map", "root", "minecraft:compass", "Off the Map", "Step into a dungeon, tavern or ruin from Dungeons and Taverns", {"any": location(all_sites)})
adv("explore/discoverer", "explore/off_the_map", "minecraft:spyglass", "Discoverer", "Be the first on the server to walk into a structure, and everyone hears your name", {"done": impossible()})
adv("explore/last_call", "explore/off_the_map", "minecraft:honey_bottle", "Last Call", "Walk into a tavern", {"any": location(TOUR["tavern"])})
adv("explore/crypt_keeper", "explore/off_the_map", "minecraft:skeleton_skull", "Crypt Keeper", "Enter a crypt or the catacombs",
    {"any": location(TOUR["undead_crypt"] + TOUR["creeping_crypt"] + TOUR["catacomb"])})
adv("explore/lord_of_the_manor", "explore/off_the_map", "minecraft:totem_of_undying", "Lord of the Manor", "Find an illager manor", {"any": location(TOUR["illager_manor"])}, frame="goal")
adv("explore/grand_tour", "explore/lord_of_the_manor", "minecraft:filled_map", "Grand Tour", "Visit every kind of dungeon, tavern and keep, in all three dimensions",
    {name: location(sites) for name, sites in TOUR.items()}, frame="challenge", hidden=True, xp=500)

adv("explore/dungeon_delver", "explore/off_the_map", "minecraft:iron_sword", "Dungeon Delver", "Step inside an underground dungeon, mossy, icy or sandy", {"any": location(EPIC_ALL)})
adv("explore/deeper_still", "explore/dungeon_delver", "minecraft:deepslate_bricks", "Deeper Still", "Find a large dungeon, a maze of many rooms", {"any": location(EPIC["large"])}, frame="goal")
adv("explore/dungeon_master", "explore/deeper_still", "minecraft:totem_of_undying", "Dungeon Master", "Enter every dungeon: plains, ice and sand, small, medium and large",
    {s.split(":")[1]: location([s]) for s in EPIC_ALL}, frame="challenge", hidden=True, xp=500)
adv("explore/odd_pillar", "explore/dungeon_delver", "minecraft:chiseled_stone_bricks", "Odd Pillar", "Find a lone obelisk standing in the wild", {"any": location(OBELISKS)})

adv("food/burger_time", "root", f"{FD}:hamburger", "Burger Time", "Eat a hamburger", {"ate": eat(f"{FD}:hamburger")})
adv("food/sushi_night", "food/burger_time", f"{FD}:salmon_roll", "Sushi Night", "Eat a salmon, cod or kelp roll",
    {r: eat(f"{FD}:{r}") for r in ["salmon_roll", "cod_roll", "kelp_roll_slice"]}, any_of=True)
adv("food/feast_mode", "food/burger_time", f"{FD}:roast_chicken", "Feast Mode", "Eat a serving from a feast",
    {f: eat(f"{FD}:{f}") for f in ["roast_chicken", "honey_glazed_ham", "shepherds_pie", "stuffed_pumpkin"]}, any_of=True, frame="goal")
adv("food/five_star_chef", "food/feast_mode", f"{FD}:cooking_pot", "Five-Star Chef", "Eat every Farmer's Delight meal at least once",
    {m: eat(f"{FD}:{m}") for m in MEALS}, frame="challenge", hidden=True, xp=500)

adv("furniture/take_a_seat", "root", "mcwfurnitures:oak_chair", "Take a Seat", "Sit on a chair or couch", {"sat": impossible()})
adv("furniture/musical_chairs", "furniture/take_a_seat", "mcwfurnitures:red_couch", "Musical Chairs", "Sit in every style of chair and a couch",
    {c: impossible() for c in CHAIRS}, frame="challenge", hidden=True, xp=200)
adv("holiday/deck_the_halls", "furniture/take_a_seat", "mcwholidays:christmas_tree_top", "Deck the Halls", "Top off a Christmas tree",
    {"placed": {"trigger": "minecraft:placed_block", "conditions": {"location": {"type": "minecraft:match_block", "blocks": TREE_TOPS}}}})

adv("travel/long_way_home", "root", "minecraft:leather_boots", "Long Way Home", "Travel 100 km in total", {"done": impossible()})
adv("travel/around_the_world", "travel/long_way_home", "minecraft:elytra", "Around the World", "Travel 1,000 km in total",
    {"done": impossible()}, frame="challenge", hidden=True, xp=300)
adv("time/regular", "root", "minecraft:clock", "Regular", "Play for 24 hours on Holy Lois", {"done": impossible()})
adv("time/resident", "time/regular", "minecraft:red_bed", "Resident", "Play for 100 hours on Holy Lois", {"done": impossible()}, frame="goal", hidden=True)
adv("daily/pocket_money", "root", "minecraft:gold_nugget", "Pocket Money", "Get your daily coins (they arrive when you join)", {"done": impossible()})
adv("daily/seven_days", "daily/pocket_money", "mcwholidays:yellow_present", "Seven Days of Lois", "Log in seven days in a row", {"done": impossible()})
adv("daily/unboxed", "daily/seven_days", "minecraft:chest", "Unboxed", "Open a Holy Lootbox", {"done": impossible()})
adv("daily/jackpot", "daily/unboxed", "minecraft:golden_pickaxe", "Jackpot!", "Find a named tool in a Holy Lootbox", {"done": impossible()}, frame="goal", hidden=True)
adv("daily/devoted", "daily/unboxed", "minecraft:nether_star", "Devoted", "Log in 28 days in a row", {"done": impossible()}, frame="challenge", hidden=True, xp=300)
adv("music/pocket_speaker", "root", "holylois:boombox", "Pocket Speaker", "Craft a boombox",
    {"crafted": {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": "holylois:boombox"}]}}})
adv("music/dj_lois", "music/pocket_speaker", "minecraft:jukebox", "DJ Lois", "Play music for your friends with the boombox", {"done": impossible()})
adv("music/house_party", "music/dj_lois", "minecraft:note_block", "House Party", "Set a boombox down somewhere",
    {"placed": {"trigger": "minecraft:placed_block", "conditions": {"location": {"type": "minecraft:match_block", "blocks": "holylois:boombox"}}}})
adv("music/surround_sound", "music/house_party", "minecraft:amethyst_shard", "Surround Sound", "Stand where two boomboxes play at once",
    {"done": impossible()}, frame="goal", hidden=True)
adv("fun/night_owl", "root", "minecraft:phantom_membrane", "Night Owl", "Still playing at 3 in the morning (Riga time)", {"done": impossible()}, hidden=True)
adv("fun/name_day", "root", "minecraft:cake", "Vārda diena", "Log in on your Latvian name day", {"done": impossible()}, hidden=True)



def holding(snbt):
    """Any item whose custom_data contains this SNBT (partial match, as vanilla does)."""
    return {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"predicates": {"minecraft:custom_data": snbt}}]}}


LEGENDS = json.loads((Path(__file__).resolve().parent.parent / "legends" / "holylois-legends.json").read_text(encoding="utf-8"))
PIECES = [(legend, piece) for legend in LEGENDS["legends"] for piece in legend["items"]]


def icon_of(piece):
    return "minecraft:filled_map" if piece["item"] == "treasure_map" else piece["item"]


adv("legends/touched_by_legend", "root", "minecraft:bell", "Touched by Legend",
    "Find an item that once belonged to a legend. More of its kind are out there", {p["id"]: holding("{holylois_legend:%s}" % json.dumps(p["id"])) for _, p in PIECES},
    frame="goal", any_of=True)
for legend in LEGENDS["legends"]:
    count = len(legend["items"])
    adv("legends/" + legend["id"], "legends/touched_by_legend", icon_of(legend["items"][0]), legend["name"],
        f"Find all {count} pieces of the legend of {legend['name']}", {p["id"]: holding("{holylois_legend:%s}" % json.dumps(p["id"])) for p in legend["items"]},
        frame="challenge", hidden=True, xp=300)
adv("fishing/message_in_a_bottle", "root", "minecraft:paper", "Message in a Bottle", "Fish up a message someone sent to sea", {"found": holding("{holylois_bottle:1b}")})
adv("fishing/fish_story", "root", "minecraft:cod", "Fish Story", "Catch a Rare fish or better: it keeps its weight forever",
    {r: holding("{holylois_fish:{rarity:%s}}" % json.dumps(r)) for r in ["rare", "epic", "legendary"]}, any_of=True)
adv("fishing/the_big_one", "fishing/fish_story", "minecraft:salmon", "The One That Didn't Get Away", "Catch a Legendary fish",
    {"caught": holding('{holylois_fish:{rarity:"legendary"}}')}, frame="challenge", hidden=True, xp=300)
adv("fishing/mythic", "fishing/fish_story", "minecraft:tropical_fish", "A Myth on the Line", "Catch your first Mythic fish", {"caught": impossible()}, frame="challenge", hidden=True)
adv("fishing/shiny_legendary", "fishing/the_big_one", "minecraft:salmon", "A Shining Legend", "Catch your first Shiny Legendary fish", {"caught": impossible()}, frame="challenge", hidden=True)
adv("fishing/shiny_mythic", "fishing/mythic", "minecraft:tropical_fish", "A Shining Myth", "Catch your first Shiny Mythic fish", {"caught": impossible()}, frame="challenge", hidden=True)

if out.exists(): shutil.rmtree(out)
(out / "data/holylois/advancement").mkdir(parents=True)
(out / "pack.mcmeta").write_text(json.dumps({"pack": {"description": "Holy Lois advancements", "min_format": [121, 0], "max_format": [121, 0]}}, indent=2) + "\n")
logo = Path(__file__).with_name("pack.png")  # shown in the datapack list
if logo.exists(): shutil.copy2(logo, out / "pack.png")
for path, data in ADV.items():
    target = out / "data/holylois/advancement" / (path + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    assert "\u2014" not in text
    target.write_text(text, encoding="utf-8")
print(len(ADV), "advancements,", len(TOUR), "Grand Tour sites,", len(MEALS), "meals,", len(LEGENDS["legends"]), "legends")
