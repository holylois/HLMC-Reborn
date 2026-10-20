"""Offline Ledger1.3.25 audit verification. No audit-row deletion or moderation-hold override."""
import hashlib,json,sqlite3,uuid
from pathlib import Path
from contextlib import closing
from .restore_ledger import real,fingerprint
from .identity_codec import contains_identity
from .snbt import decode as snbt_decode

SCHEMA={'players':('id','player_id','player_name','first_join','last_join'),
    'sqlite_sequence':('name','seq'),'ActionIdentifiers':('id','action_identifier'),'worlds':('id','identifier'),
    'ObjectIdentifiers':('id','identifier'),'sources':('id','name'),
    'actions':('id','action_id','time','x','y','z','world_id','object_id','old_object_id','block_state','old_block_state','source','player_id','extra_data','rolled_back')}
class AuditStore:
    def __init__(self,path,stopped):self.path=real(path);self.stopped=stopped
    def verify(self,request):
        if self.stopped() is not True:raise ValueError('Audit database requires stopped lease')
        if not self.path.exists():return {'absent':True,'fingerprint':fingerprint({'audit':'missing','subject':request['subject']})}
        real(self.path)
        if not self.path.is_file() or self.path.stat().st_nlink!=1:raise ValueError('Unexpected audit database')
        if any(Path(str(self.path)+suffix).exists() or Path(str(self.path)+suffix).is_symlink() for suffix in ('-wal','-shm','-journal')):raise ValueError('Pending audit database writes')
        before=self.path.stat();evidence=[];present=False;count=0;total=0;identity=uuid.UUID(request['subject'])
        try:
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
                db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
                if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Audit database integrity failed')
                tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables!=set(SCHEMA):raise ValueError('Unknown Ledger audit schema')
                for table,columns in SCHEMA.items():
                    if tuple(row[1] for row in db.execute('PRAGMA table_info("'+table+'")'))!=columns:raise ValueError('Unknown Ledger columns')
                    for row in db.execute('SELECT * FROM "'+table+'" ORDER BY 1'):
                        count+=1;total+=sum(len(value) for value in row if isinstance(value,(str,bytes)))
                        if count>100000 or total>64*1024*1024:raise ValueError('Audit case exceeds review budget')
                        inspected=[]
                        for column,value in zip(columns,row):
                            if isinstance(value,bytes):
                                if table!='players' or column!='player_id' or len(value)!=16:raise ValueError('Opaque audit record requires review')
                                present=present or value in (identity.bytes,identity.bytes_le);inspected.append(value.hex());continue
                            if isinstance(value,str):
                                present=present or contains_identity(value,request)
                                if column in ('block_state','old_block_state','extra_data') and value:
                                    present=present or contains_identity(snbt_decode(value),request)
                            elif value is not None and type(value) not in (int,float):raise ValueError('Unsupported audit value')
                            inspected.append(value)
                        evidence.append(fingerprint(inspected))
        except sqlite3.Error:raise ValueError('Audit verification failed; no absence proof') from None
        after=self.path.stat()
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns) or self.stopped() is not True:raise ValueError('Audit store changed')
        return {'absent':not present,'fingerprint':fingerprint({'schema':'Ledger1.3.25','subject':request['subject'],'rows':evidence})}
