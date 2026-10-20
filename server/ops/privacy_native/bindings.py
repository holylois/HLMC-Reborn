"""Source-bound offline registry. Reviewed runtime inventory is still required before live use."""
from pathlib import Path
from .auth_sqlite import SQLiteAuth
from .store_adapters import ProfileFiles,HomesFiles
from .scoped_stores import FileScope,RecoveryScope,Group,complete_registry
from .regions import WorldScope

AUTH='400309e547555dcdaddbdd925bf106dbc3f94b4f678cc575d30e3c99b6521ee4'
OPAC='809a1f378397d7a6986597f1fb278b8b069bb7588722ea5204b0a222076ad6a8'
ECONOMY='042e922dc37353c1b25fb05dfab702935ef629f939e161fdc38304da5e8da69f'
HOLY=['afk.json','daily.json','claims.json','fun-time.json','discoveries.json','onboarding.json','redeem.json',
      'events.json','death-loot.json','skin-textures.json','audio-urls.log','boomboxes.json']
RECOVERY=['account-requests.json','account-profile-names.json','private-recovery','private-account-backups']

class EconomyScope(FileScope):
    def inventory(self):
        from .runtime_guard import migrations
        migrations(self.base)
        return super().inventory()

class HolyScope(FileScope):
    def __init__(self,world,stopped,source):
        super().__init__(world,['holylois/'+name for name in HOLY],stopped,source)
    def inventory(self):
        folder=self.base/'holylois'
        if folder.exists():
            unknown={p.name for p in folder.iterdir()}-set(HOLY+RECOVERY)
            if unknown:raise ValueError('New HolyLois store requires inventory review')
        return super().inventory()
    def inspect(self,name,raw,request):
        if name=='holylois/audio-urls.log':
            from .identity_codec import contains_identity
            return contains_identity(raw.decode('utf-8'),request)
        return super().inspect(name,raw,request)

def bind(root,auth_path,auth_table,stopped,onboarding_source,public_paths,discord,reviewed_world_paths):
    root=Path(root);world=root/'world'
    # Whole OPAC data tree includes player claims, parties, region state, player/sub-configs and
    # extra supported data. Unknown formats block, instead of treating zero claims as erasure.
    claims=FileScope(world,['data/openpartiesandclaims','serverconfig'],stopped,OPAC)
    economy_paths=['config/economycraft/data','config/economycraft/logs']
    # Legacy root-level records are not silently excluded by the current directory layout.
    for name in ('balances','daily','daily_sells','deliveries','auctions','shop','orders','notifications','player_activity','stats'):
        economy_paths.append('config/economycraft/'+name+'.json')
    for parent in (root/'world',root/'config'):
        if parent.is_dir():
            for path in parent.iterdir():
                if path.name=='economycraft_imported' or path.name.startswith('economycraft_backup_') or parent==world and path.name=='economycraft':
                    # Imported/settings copies can contain credentials. Do not auto-read them:
                    # the reviewer must split data scope from necessary settings protection.
                    raise ValueError('Economy migration/backup folder requires explicit review')
    public=FileScope(root,public_paths,stopped,onboarding_source)
    return complete_registry({
        'profiles':Group(ProfileFiles(world),FileScope(root,['usercache.json','ops.json','whitelist.json','banned-players.json'],stopped,onboarding_source)),
        'homes':Group(HomesFiles(world),FileScope(world,['essentialcommands','world_data.dat','world_data.dat_old'],stopped,onboarding_source)),
        'holylois':HolyScope(world,stopped,onboarding_source),
        'authentication':SQLiteAuth(auth_path,auth_table,stopped),
        'claims':claims,'economy':EconomyScope(root,economy_paths,stopped,ECONOMY),
        'private-recovery':RecoveryScope(world,stopped,onboarding_source),
        'public-exports':public,'discord':discord,
        'world-ownership':WorldScope(world,reviewed_world_paths,stopped,onboarding_source)})

def bind_native(root,auth_path,auth_table,stopped,pins,public_paths,discord,
        reviewed_world_paths,outside_exports,http_exports,audit_path):
    """Complete offline registry. Callers must use this entry point for a real rollout.

    External exports include stats.json, weekly-stats.json and any independently
    reviewed cache. Explicit paths only; never scan a parent containing credentials.
    """
    from .runtime_guard import RuntimePins,Guarded,migrations
    from .audit_store import AuditStore
    from .audio_scope import AudioScope
    from .public_http import HTTPExports
    if not isinstance(pins,RuntimePins) or pins.mod_inventory is None or not isinstance(http_exports,HTTPExports):
        raise ValueError('Native runtime and controlled HTTP inventory required')
    root=Path(root)
    def check():
        if stopped() is not True:raise ValueError('Complete stopped-service lease required')
        migrations(root)
        return pins.check()
    check()
    if not {'stats','weekly'}<=set(outside_exports):raise ValueError('Stats and weekly cache bindings required')
    external=[]
    for key,p in sorted(outside_exports.items()):
        p=Path(p).absolute()
        if p.is_relative_to(root):raise ValueError('Outside export scope overlaps server root')
        external.append(FileScope(p.parent,[p.name],stopped,pins.entries['stats-exporter'][1]))
    adapters=bind(root,auth_path,auth_table,stopped,pins.entries['holylois'][1],public_paths,discord,reviewed_world_paths)
    adapters['homes']=Group(HomesFiles(root/'world'),FileScope(root/'world',['essentialcommands','world_data.dat','world_data.dat_old'],stopped,pins.entries['homes'][1]))
    adapters['world-ownership']=Group(
        WorldScope(root/'world',reviewed_world_paths,stopped,pins.entries['holylois'][1],cache_source=pins.entries['terrain-cache'][0]),
        AudioScope(root,stopped,pins.entries['audio'][1]),AuditStore(audit_path,stopped))
    adapters['public-exports']=Group(adapters['public-exports'],*external,http_exports)
    return complete_registry({name:Guarded(adapter,check) for name,adapter in adapters.items()})
