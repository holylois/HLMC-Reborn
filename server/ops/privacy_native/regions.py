"""Bounded Anvil region identity review. Unsupported compression/external chunks block.

This never edits shared terrain, pets, item ownership or block entities.
"""
import struct,zlib,hashlib,os
from pathlib import Path
from .identity_codec import decode,contains_identity,LIMIT
from .scoped_stores import FileScope
from .restore_ledger import real,fingerprint

def file_chunks(path):
    """Read active Anvil records with bounded memory, not a whole region at once."""
    size=path.stat().st_size
    if size<8192 or size%4096:raise ValueError('Malformed Anvil sector layout')
    with path.open('rb') as stream:
        header=stream.read(8192);used={0,1}
        yield header,None
        for index in range(1024):
            location=int.from_bytes(header[index*4:index*4+4],'big');offset=location>>8;count=location&255
            if not offset and not count:continue
            if offset<2 or count==0 or (offset+count)*4096>size:raise ValueError('Invalid Anvil chunk location')
            sectors=set(range(offset,offset+count))
            if used&sectors:raise ValueError('Overlapping Anvil chunks')
            used.update(sectors);stream.seek(offset*4096);prefix=stream.read(5)
            if len(prefix)!=5:raise ValueError('Truncated Anvil record')
            length=int.from_bytes(prefix[:4],'big');kind=prefix[4]
            if length<1 or length+4>count*4096:raise ValueError('Invalid Anvil chunk length')
            raw=stream.read(length-1)
            if len(raw)!=length-1:raise ValueError('Truncated Anvil payload')
            payload=raw
            if kind==2:
                inflater=zlib.decompressobj();payload=inflater.decompress(raw,LIMIT+1)
                if len(payload)>LIMIT or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:raise ValueError('Invalid or oversized Anvil compressed data')
            elif kind not in (1,3):raise ValueError('External/LZ4/unknown Anvil chunk needs native review')
            yield index.to_bytes(4,'big')+prefix+raw,decode(payload,'.nbt')

def chunks(raw):
    if len(raw)<8192 or len(raw)%4096:raise ValueError('Malformed Anvil sector layout')
    used={0,1};result=[]
    for index in range(1024):
        location=int.from_bytes(raw[index*4:index*4+4],'big');offset=location>>8;count=location&255
        if not offset and not count:continue
        if offset<2 or count==0 or (offset+count)*4096>len(raw):raise ValueError('Invalid Anvil chunk location')
        sectors=set(range(offset,offset+count))
        if used&sectors:raise ValueError('Overlapping Anvil chunks')
        used.update(sectors);start=offset*4096;length=struct.unpack('>I',raw[start:start+4])[0]
        if length<1 or length+4>count*4096:raise ValueError('Invalid Anvil chunk length')
        kind=raw[start+4];payload=raw[start+5:start+4+length]
        if kind==2:
            stream=zlib.decompressobj();payload=stream.decompress(payload,LIMIT+1)
            if len(payload)>LIMIT or not stream.eof or stream.unused_data or stream.unconsumed_tail:raise ValueError('Invalid or oversized Anvil compressed data')
        elif kind not in (1,3):raise ValueError('External/LZ4/unknown Anvil chunk needs native review')
        result.append(decode(payload,'.nbt'))
    return result

class WorldScope(FileScope):
    def __init__(self,*args,cache_source=None,**kwargs):
        self.cache_source=cache_source
        super().__init__(*args,**kwargs)
    def inventory(self):
        rows=[];total=0
        def take(path):
            nonlocal total
            if real(path)!=path:raise ValueError('Linked world store')
            s=path.stat();name=path.relative_to(self.base).as_posix()
            cache=self.metadata_only(name)
            if not path.is_file() or s.st_nlink!=1:raise ValueError('Unsupported world entry')
            if not cache:
                limit=128*1024*1024 if path.suffix=='.mca' else LIMIT
                if s.st_size>limit:raise ValueError('World entry requires native case review')
                total+=s.st_size
            if total>80*1024**3 or len(rows)>=20000:raise ValueError('World review exceeds bounded maintenance budget')
            rows.append((name,s.st_ino,s.st_size,s.st_mtime_ns))
        for name in self.paths:
            p=self.base/name;real(p)
            if not p.exists():rows.append((name,None,None,None));continue
            if p.is_file():take(p);continue
            if not p.is_dir():raise ValueError('Unsupported world root')
            def denied(error):raise ValueError('Unreadable world subtree')
            for parent,dirs,files in os.walk(p,followlinks=False,onerror=denied):
                for child in dirs:real(Path(parent)/child)
                for child in files:take(Path(parent)/child)
        return sorted(rows)
    def verify(self,request):
        if self.stopped() is not True:raise ValueError('Offline world lease required')
        before=self.inventory();evidence=[];present=False
        for name,inode,size,mtime in before:
            if inode is None:evidence.append((name,'missing'));continue
            present=present or contains_identity(name,request)
            if name.endswith('.mca'):
                digest=hashlib.sha256()
                for raw,data in file_chunks(self.base/name):
                    digest.update(raw)
                    if data is not None:present=contains_identity(data,request) or present
                evidence.append((name,digest.hexdigest()))
            else:
                raw=self.raw(name,size);present=self.inspect(name,raw,request) or present
                evidence.append((name,hashlib.sha256(raw).hexdigest()))
        if before!=self.inventory() or self.stopped() is not True:raise ValueError('World changed during verification')
        return {'absent':not present,'fingerprint':fingerprint({'source':self.source,'scope':self.paths,'subject':request['subject'],'files':evidence})}
    def metadata_only(self,name):
        path=Path(name)
        terrain=path.parts[0]=='dimensions' and path.parent.name=='data' and path.name in (
            'DistantHorizons.sqlite','DistantHorizons.sqlite-wal','DistantHorizons.sqlite-shm','DistantHorizons.sqlite-journal')
        if not terrain:return False
        expected='ba3e5c85a765a109219831df99b99ef5cfcdee05b2dfa6796116993bd48d3947'
        if self.cache_source is None or hashlib.sha256(Path(self.cache_source).read_bytes()).hexdigest()!=expected:
            raise ValueError('Terrain-cache exclusion requires reviewed DistantHorizons3.3.4 code')
        # Reviewed FullDataSourceV1/V2, ChunkHash and BeaconBeam DTOs store terrain/blockstate/biome,
        # coordinate/color/checksum data. They are not an account/entity ownership database.
        # Pin cache metadata without reading its compressed terrain blobs. Shared terrain is retained.
        return True
    def inspect(self,name,raw,request):
        if self.metadata_only(name):return False
        if name.endswith('.mca'):
            return any(contains_identity(chunk,request) for chunk in chunks(raw)) or contains_identity(name,request)
        return super().inspect(name,raw,request)
