"""Bounded JSON/TOML/NBT identity inspection for reviewed store roots. No mutation functions."""
import gzip,io,json,re,struct,tomllib,uuid
from .restore_ledger import uuid_text
from .store_adapters import unique

LIMIT=16*1024*1024
class IntArray(list):pass
class LongArray(list):pass
class NBT:
    def __init__(self,raw):self.stream=io.BytesIO(raw);self.nodes=0
    def take(self,count):
        if count<0 or count>LIMIT:raise ValueError('NBT read limit')
        value=self.stream.read(count)
        if len(value)!=count:raise ValueError('Truncated NBT')
        return value
    def number(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
    def text(self):
        raw=self.take(self.number('H')).replace(b'\xc0\x80',b'\x00')
        return raw.decode('utf-8',errors='surrogatepass').encode('utf-16-le',errors='surrogatepass').decode('utf-16-le')
    def count(self):
        count=self.number('i')
        if count<0 or count>500000:raise ValueError('NBT collection limit')
        self.nodes+=count
        if self.nodes>500000:raise ValueError('NBT node limit')
        return count
    def payload(self,tag,depth=0,field=None):
        self.nodes+=1
        if depth>64 or self.nodes>500000:raise ValueError('NBT nesting limit')
        if tag in (1,2,3,4,5,6):return self.number({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[tag])
        if tag==7:
            count=self.count()
            if count==2048 and field in ('BlockLight','SkyLight'):
                self.take(count);return None  # Minecraft lighting nibble arrays, not identity records.
            if count:raise ValueError('Opaque NBT byte array requires schema review')
            return []
        if tag==8:return self.text()
        if tag==9:
            kind=self.number('B');count=self.count()
            if kind==0 and count:raise ValueError('Invalid NBT list')
            return [self.payload(kind,depth+1) for _ in range(count)]
        if tag==10:
            result={}
            while True:
                kind=self.number('B')
                if kind==0:return result
                name=self.text()
                if name in result:raise ValueError('Duplicate NBT field')
                result[name]=self.payload(kind,depth+1,name)
        if tag in (11,12):
            count=self.count();cls,fmt=(IntArray,'i') if tag==11 else (LongArray,'q')
            return cls(self.number(fmt) for _ in range(count))
        raise ValueError('Unsupported NBT tag')
    def read(self):
        if self.number('B')!=10:raise ValueError('Expected compound NBT root')
        self.text();result=self.payload(10)
        if self.stream.read(1):raise ValueError('Trailing NBT data')
        return result

def decode(raw,suffix):
    if len(raw)>LIMIT:raise ValueError('Store file exceeds budget')
    if raw[:2]==b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:raw=stream.read(LIMIT+1)
        if len(raw)>LIMIT:raise ValueError('Expanded store exceeds budget')
    if suffix=='.json':return json.loads(raw.decode('utf-8'),object_pairs_hook=unique)
    if suffix in ('.jsonl','.log'):
        return [json.loads(line,object_pairs_hook=unique) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if suffix=='.toml':return tomllib.loads(raw.decode('utf-8'))
    if suffix=='.snbt':
        from .snbt import decode as read_snbt
        return read_snbt(raw.decode('utf-8'))
    if suffix in ('.dat','.nbt'):return NBT(raw).read()
    raise ValueError('Unknown store format requires review')

def contains_identity(data,request):
    subject=uuid_text(request['subject']);hexid=subject.replace('-','')
    aliases=request['aliases']
    if not aliases or any(not re.fullmatch('[a-z0-9_]{3,16}',name) for name in aliases):raise ValueError('Reviewed aliases required')
    names=re.compile(r'(?<![a-z0-9_])(?:'+'|'.join(re.escape(name) for name in aliases)+r')(?![a-z0-9_])',re.I)
    def text(value):
        lowered=value.lower()
        return subject in lowered or hexid in lowered or bool(names.search(value))
    def visit(value,depth=0):
        if depth>128:raise ValueError('Nested identity data exceeds limit')
        if isinstance(value,str):return text(value)
        if isinstance(value,IntArray) and len(value)==4:
            identity=uuid.UUID(bytes=b''.join(struct.pack('>I',part&0xffffffff) for part in value))
            if str(identity)==subject:return True
        if isinstance(value,LongArray) and len(value)==2:
            identity=uuid.UUID(bytes=b''.join(struct.pack('>Q',part&0xffffffffffffffff) for part in value))
            if str(identity)==subject:return True
        if isinstance(value,dict):
            for most,least in (('UUIDMost','UUIDLeast'),('Most','Least')):
                if type(value.get(most)) is int and type(value.get(least)) is int:
                    if str(uuid.UUID(bytes=struct.pack('>QQ',value[most]&0xffffffffffffffff,value[least]&0xffffffffffffffff)))==subject:return True
            return any(text(str(key)) or visit(child,depth+1) for key,child in value.items())
        if isinstance(value,list):return any(visit(child,depth+1) for child in value)
        if value is None or type(value) in (int,float,bool):return False
        # TOML datetime values are metadata, never an account identifier.
        import datetime
        if isinstance(value,(datetime.datetime,datetime.date,datetime.time)):return False
        raise ValueError('Unknown identity value type')
    return visit(data)
