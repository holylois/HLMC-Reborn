"""Recheck reviewed public code and migration roots at each offline verification.

No account data is opened here. A hash supplied by an unreviewed restore is not a
review: keep this manifest and the ledger outside every restored server tree.
"""
import hashlib,re,os,stat
from pathlib import Path
from .restore_ledger import real,fingerprint

REQUIRED=frozenset(('auth','claims','economy','homes','holylois','extras','audio',
    'audit','terrain-cache','stats-exporter','weekly-exporter','stats-http'))

def migrations(root):
    root=real(root)
    for parent in (root/'world',root/'config'):
        if parent.is_dir():
            for p in parent.iterdir():
                if p.name=='economycraft_imported' or p.name.startswith('economycraft_backup_') or parent==root/'world' and p.name=='economycraft':
                    raise ValueError('Economy migration/backup folder requires explicit review')

class RuntimePins:
    def __init__(self,entries,mod_inventory=None):
        if set(entries)!=REQUIRED:raise ValueError('Complete reviewed runtime pins required')
        self.entries={};self.cache={}
        for key,row in entries.items():
            if set(row)!={'path','sha256'} or not re.fullmatch('[a-f0-9]{64}',row['sha256']):
                raise ValueError('Invalid runtime pin')
            self.entries[key]=(real(row['path']),row['sha256'])
        self.mod_inventory=mod_inventory
        if mod_inventory is not None:
            if set(mod_inventory)!={'directory','files'} or not mod_inventory['files']:
                raise ValueError('Complete reviewed mod inventory required')
            real(mod_inventory['directory'])
            for name,digest in mod_inventory['files'].items():
                if Path(name).name!=name or not name.endswith('.jar') or not re.fullmatch('[a-f0-9]{64}',digest):
                    raise ValueError('Invalid reviewed mod inventory')
    def check(self):
        evidence=[]
        items=dict(self.entries)
        if self.mod_inventory is not None:
            folder=real(self.mod_inventory['directory'])
            if {p.name for p in folder.glob('*.jar')}!=set(self.mod_inventory['files']):
                raise ValueError('Mod inventory changed; storage review required')
            items.update({'mod:'+name:(folder/name,digest) for name,digest in self.mod_inventory['files'].items()})
        for key,(p,expected) in sorted(items.items()):
            real(p);before=p.stat()
            metadata=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_gid,s.st_nlink)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>512*1024*1024:raise ValueError('Pinned code is missing, linked or oversized')
            if self.cache.get(p)==(metadata(before),expected):
                evidence.append((key,expected));continue
            h=hashlib.sha256()
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as f:
                if metadata(os.fstat(f.fileno()))!=metadata(before):raise ValueError('Code changed before open')
                count=0
                for block in iter(lambda:f.read(1024*1024),b''):
                    count+=len(block)
                    if count>512*1024*1024:raise ValueError('Code grew beyond review bound')
                    h.update(block)
            after=p.stat()
            if metadata(before)!=metadata(after) or h.hexdigest()!=expected:
                raise ValueError('Reviewed runtime code changed: '+key)
            self.cache[p]=(metadata(after),expected)
            evidence.append((key,expected))
        return fingerprint(evidence)

class Guarded:
    def __init__(self,adapter,check):self.adapter,self.check=adapter,check
    def verify(self,request):
        before=self.check();result=self.adapter.verify(request)
        if self.check()!=before:raise ValueError('Runtime review changed during verification')
        return {'absent':result.get('absent') is True,'fingerprint':fingerprint([before,result])}
