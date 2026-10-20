"""Explicit offline scope verification. Unknown data prevents completion; no deletion API.

Scope approval is a prerequisite, not something this library can manufacture from directory names.
All receipts are hashes. File contents, recovery secrets and message bodies are never returned.
"""
import hashlib,json,os,re
from pathlib import Path
from .restore_ledger import real,fingerprint,STORES
from .identity_codec import decode,contains_identity,LIMIT

def digest(raw):return hashlib.sha256(raw).hexdigest()
def fail(message):raise ValueError(message)

class FileScope:
    def __init__(self,base,paths,stopped,source_sha256):
        self.base=real(base);self.paths=tuple(sorted(paths));self.stopped=stopped
        if not self.base.is_dir() or not self.paths:fail('Existing base and reviewed paths required')
        self.source=source_sha256
        if not re.fullmatch('[0-9a-f]{64}',source_sha256):fail('Reviewed source fingerprint required')
        for name in self.paths:
            p=Path(name)
            if p.is_absolute() or '..' in p.parts or p.as_posix()!=name or name in ('','.'):fail('Invalid relative scope')
        if len(set(self.paths))!=len(self.paths):fail('Duplicate scope')
        if any(a!=b and Path(a).is_relative_to(b) for a in self.paths for b in self.paths):fail('Overlapping scope')
    def inventory(self):
        rows=[];total=0
        def take(path):
            nonlocal total
            if real(path)!=path:fail('Linked store path')
            stat=path.stat()
            metadata_only=self.metadata_only(path.relative_to(self.base).as_posix())
            if not path.is_file() or stat.st_nlink!=1 or not metadata_only and stat.st_size>LIMIT:fail('Unsupported store entry')
            if not metadata_only:total+=stat.st_size
            if total>256*1024*1024 or len(rows)>=20000:fail('Scope exceeds bounded review')
            rows.append((path.relative_to(self.base).as_posix(),stat.st_ino,stat.st_size,stat.st_mtime_ns))
        for name in self.paths:
            path=self.base/name
            real(path)
            if not path.exists():
                rows.append((name,None,None,None));continue
            if path.is_file():take(path);continue
            if not path.is_dir():fail('Unsupported scope root')
            def denied(error):fail('Store subtree is unreadable')
            for parent,dirs,files in os.walk(path,followlinks=False,onerror=denied):
                for child in dirs:real(Path(parent)/child)
                for child in files:take(Path(parent)/child)
        return sorted(rows)
    def metadata_only(self,name):return False
    def raw(self,name,size):
        if self.metadata_only(name):
            stat=(self.base/name).stat()
            return json.dumps([stat.st_ino,stat.st_size,stat.st_mtime_ns]).encode()
        with (self.base/name).open('rb') as stream:raw=stream.read(LIMIT+1)
        if len(raw)!=size:fail('Store changed while read')
        return raw
    def inspect(self,name,raw,request):
        suffix=Path(name).suffix.lower()
        if suffix=='.dat_old':suffix='.dat'
        data=decode(raw,suffix)
        return contains_identity(name,request) or contains_identity(data,request)
    def verify(self,request):
        if self.stopped() is not True:fail('Offline lease required')
        rows=self.inventory();evidence=[];found=False
        for name,inode,size,mtime in rows:
            if inode is None:evidence.append((name,'missing'));continue
            raw=self.raw(name,size);matched=self.inspect(name,raw,request)
            found=found or matched;evidence.append((name,digest(raw)))
        if rows!=self.inventory() or self.stopped() is not True:fail('Store changed during verification')
        return {'absent':not found,'fingerprint':fingerprint({'source':self.source,'scope':self.paths,'subject':request['subject'],'aliases':request['aliases'],'files':evidence})}

class RecoveryScope(FileScope):
    """Token bytes need not be read. Every token must map to a non-target durable grant.

    account-requests, identity cache and account snapshots are scanned separately by FileScope.
    Orphan/unrecognized token files block. No inferred ownership and no mass token revocation.
    """
    def __init__(self,base,stopped,source_sha256):
        super().__init__(base,['holylois/account-requests.json','holylois/account-profile-names.json',
            'holylois/private-recovery','holylois/private-account-backups'],stopped,source_sha256)
    def verify(self,request):
        if self.stopped() is not True:fail('Offline lease required')
        self.tokens={}
        path=self.base/'holylois/account-requests.json'
        if path.exists():
            real(path);raw=self.raw('holylois/account-requests.json',path.stat().st_size)
            data=decode(raw,'.json')
            if not isinstance(data,dict) or set(data)!={'aliases','grants'} or not all(isinstance(data[k],dict) for k in data):fail('Unknown account request schema')
            for key,grant in data['grants'].items():
                if not isinstance(grant,dict) or not {'id','uuid','kind'}<=set(grant):fail('Malformed recovery grant')
                import uuid
                identity=str(uuid.UUID(grant['id']));owner=str(uuid.UUID(grant['uuid']))
                if key!=owner+':'+str(grant['kind']) or identity in self.tokens:fail('Ambiguous recovery ownership')
                self.tokens[identity]=owner
        return super().verify(request)
    def inspect(self,name,raw,request):
        if name.startswith('holylois/private-recovery/'):
            path=Path(name)
            if path.parent.as_posix()!='holylois/private-recovery' or path.suffix!='.token':fail('Unknown recovery file')
            if path.stem not in self.tokens:fail('Orphan recovery token requires review')
            return self.tokens[path.stem]==request['subject']
        return super().inspect(name,raw,request)
    def raw(self,name,size):
        # Hashing a token is unnecessary for absence: pin its stat/association, not secret bytes.
        if name.startswith('holylois/private-recovery/'):
            stat=(self.base/name).stat()
            return json.dumps([stat.st_ino,stat.st_size,stat.st_mtime_ns]).encode()
        return super().raw(name,size)

def complete_registry(adapters):
    if set(adapters)!=STORES:fail('Every store must have a bound verifier')
    if any(not callable(getattr(adapter,'verify',None)) for adapter in adapters.values()):fail('Invalid store verifier')
    return adapters

class Group:
    def __init__(self,*parts):
        if not parts:fail('Empty verifier group')
        self.parts=parts
    def verify(self,request):
        results=[part.verify(request) for part in self.parts]
        return {'absent':all(row.get('absent') is True for row in results),'fingerprint':fingerprint(results)}
