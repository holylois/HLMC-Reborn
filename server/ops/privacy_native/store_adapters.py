"""Real file-shape verifiers and pure transforms. No authentication database access or live apply CLI."""
import copy,hashlib,json,os
from pathlib import Path
from .restore_ledger import fingerprint,real,uuid_text

MAPS={'holylois/afk.json':('seconds',1),'holylois/daily.json':('players',1),'holylois/claims.json':('bought',1)}
def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON identity')
        result[key]=value
    return result

def load(path,world):
    path=Path(path)
    if path.is_symlink() or path.resolve()!=path.absolute() or not path.is_relative_to(world):raise ValueError('Unexpected store path')
    if not path.exists():return None
    if not path.is_file() or path.stat().st_nlink!=1 or path.stat().st_size>32*1024*1024:raise ValueError('Unexpected store size or type')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)

def transform_map(data,relative,subject):
    uuid_text(subject)
    field,version=MAPS[relative]
    if not isinstance(data,dict) or set(data)!={'version',field} or data['version']!=version or not isinstance(data[field],dict):
        raise ValueError('Unsupported store schema')
    for key in data[field]:uuid_text(key)
    result=copy.deepcopy(data);result[field].pop(subject,None);return result

def transform_discoveries(data,subject,aliases,shared_decision=None):
    uuid_text(subject);aliases={a.lower() for a in aliases}
    if not isinstance(data,dict) or set(data)!={'version','journals','found','firsts'} or data['version']!=4:
        raise ValueError('Unsupported discovery schema')
    if not isinstance(data['journals'],dict) or not all(isinstance(data[k],list) for k in ('found','firsts')):
        raise ValueError('Malformed discovery maps')
    for key in data['journals']:uuid_text(key)
    result=copy.deepcopy(data);result['journals'].pop(subject,None)
    for field in ('found','firsts'):
        for row in result[field]:
            if not isinstance(row,dict):raise ValueError('Malformed shared discovery')
            owner=row.get('uuid');name=row.get('player')
            if owner is not None:uuid_text(owner)
            if owner is None and isinstance(name,str) and name.lower() in aliases:
                raise ValueError('Legacy name-only ownership needs review; never infer identity')
            if owner==subject:
                if shared_decision!='anonymize':raise ValueError('Shared first/discovery decision required')
                row['uuid']=None;row['player']='Former player'
    return result

class ProfileFiles:
    def __init__(self,world):self.world=real(world)
    def targets(self,request):
        subject=uuid_text(request['subject'])
        #26.3 stores records in players/*; also protect old-layout copies that a migration left behind.
        return [self.world/relative for relative in (
            f'players/data/{subject}.dat',f'players/data/{subject}.dat_old',
            f'players/stats/{subject}.json',f'players/advancements/{subject}.json',
            f'playerdata/{subject}.dat',f'playerdata/{subject}.dat_old',
            f'stats/{subject}.json',f'advancements/{subject}.json')]
    def verify(self,request):
        present=[]
        for path in self.targets(request):
            if path.is_symlink() or path.resolve()!=path.absolute():raise ValueError('Linked profile path needs review')
            if path.exists():present.append(path.relative_to(self.world).as_posix())
        return {'absent':not present,'fingerprint':fingerprint({'subject':request['subject'],'remaining_files':present})}
    def quarantine(self,request,destination,approved_plan_sha256,stopped):
        # Only an explicitly reviewed exact fixture/live plan may move files; never deletes their bytes.
        expected=self.plan(request)
        if approved_plan_sha256!=fingerprint(expected) or stopped() is not True:raise ValueError('Exact scope and stopped-service lease required')
        destination=real(destination)
        if destination.is_relative_to(self.world) or self.world.is_relative_to(destination):raise ValueError('Quarantine must be outside restored world')
        destination.mkdir(mode=0o700,parents=True,exist_ok=False)
        for row in expected:
            path=self.world/row['relative']
            if stopped() is not True or self.plan_one(path)!=row:raise ValueError('Profile changed during quarantine; keep service stopped')
            target=destination/row['relative'];target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.replace(path,target)
            if os.name=='posix':
                for parent in (path.parent,target.parent):
                    directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
                    try:os.fsync(directory)
                    finally:os.close(directory)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('Quarantine verification failed')
        if not self.verify(request)['absent']:raise ValueError('Profile remains after quarantine')
        return {'live_records_absent':True,'final_erasure':False,'quarantined_files':len(expected)}
    def plan_one(self,path):
        if path.is_symlink() or path.resolve()!=path.absolute() or not path.is_relative_to(self.world):raise ValueError('Unexpected profile path')
        before=path.stat()
        if not path.is_file() or before.st_nlink!=1 or before.st_size>64*1024*1024:raise ValueError('Unexpected profile file')
        digest=hashlib.sha256(path.read_bytes()).hexdigest();after=path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):raise ValueError('Profile changed')
        return {'relative':path.relative_to(self.world).as_posix(),'inode':before.st_ino,'size':before.st_size,'mtime':before.st_mtime_ns,'sha256':digest}
    def plan(self,request):
        self.verify(request)
        return [self.plan_one(path) for path in self.targets(request) if path.exists()]

class HolyLoisFiles:
    def __init__(self,world):self.world=real(world)
    def verify(self,request):
        observations=[];absent=True
        for relative in MAPS:
            data=load(self.world/relative,self.world)
            if data is None:observations.append((relative,None));continue
            cleaned=transform_map(data,relative,request['subject'])
            absent=absent and cleaned==data;observations.append((relative,fingerprint(data)))
        relative='holylois/discoveries.json';data=load(self.world/relative,self.world)
        if data is not None:
            # No shared decision is assumed by the verifier. Any owned shared row blocks service start.
            try: cleaned=transform_discoveries(data,request['subject'],request['aliases'])
            except ValueError as error:
                if str(error) in ('Shared first/discovery decision required','Legacy name-only ownership needs review; never infer identity'):
                    absent=False;cleaned=None
                else:raise
            absent=absent and cleaned==data;observations.append((relative,fingerprint(data)))
        return {'absent':absent,'fingerprint':fingerprint(observations)}


class HomesFiles(ProfileFiles):
    """Essential Commands0.42.0 uses world/modplayerdata/UUID.dat. No global reset command."""
    def targets(self,request):
        subject=uuid_text(request['subject'])
        return [self.world/f'{folder}/{subject}{suffix}' for folder in ('modplayerdata','ec_player_profiles')
                for suffix in ('.dat','.dat_old')]
