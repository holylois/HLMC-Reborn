"""EasyAuth3.4.4 offline read-only SQLite identity verifier. No CLI or live invocation."""
import hashlib,json,re,sqlite3,uuid
from pathlib import Path
from .restore_ledger import fingerprint,real,uuid_text

COLUMNS=('id','username','username_lower','uuid','last_ip','data')
# Java UUID.nameUUIDFromBytes uses MD5 version3 directly, without an RFC namespace prefix.
def offline_uuid(name):
    if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_]{3,16}',name):raise ValueError('Invalid account identity')
    raw=bytearray(hashlib.md5(('OfflinePlayer:'+name).encode(),usedforsecurity=False).digest())
    raw[6]=(raw[6]&15)|48;raw[8]=(raw[8]&63)|128
    return str(uuid.UUID(bytes=bytes(raw)))
def effective(sql_uuid,forced,online,name):
    if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_]{3,16}',name):raise ValueError('Unsupported account name')
    if forced not in (None,''):
        if not isinstance(forced,str):raise ValueError('Unsupported forced identity')
        return str(uuid.UUID(forced))
    if online not in (None,'TRUE','FALSE','UNKNOWN'):raise ValueError('Unsupported account type')
    return str(uuid.UUID(sql_uuid)) if online=='TRUE' else offline_uuid(name)

class SQLiteAuth:
    def __init__(self,path,table,stopped):
        self.path=real(path)
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',table):raise ValueError('Reviewed table identifier required')
        self.table,self.stopped=table,stopped
    def verify(self,request):
        subject=uuid_text(request['subject']);aliases=sorted(set(request['aliases']))
        if not aliases or any(not re.fullmatch('[a-z0-9_]{3,16}',name) for name in aliases):raise ValueError('Verified lower-case aliases required')
        if self.stopped() is not True:raise ValueError('Offline verification lease required')
        if (self.path.is_symlink() or self.path.resolve()!=self.path.absolute() or not self.path.is_file()
                or self.path.stat().st_nlink!=1 or self.path.stat().st_size>256*1024*1024):
            raise ValueError('Expected reviewed existing database')
        if any(Path(str(self.path)+suffix).exists() or Path(str(self.path)+suffix).is_symlink() for suffix in ('-wal','-shm','-journal')):
            raise ValueError('Database has pending or ambiguous sidecars')
        before=self.path.stat()
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
            objects=list(db.execute('SELECT type FROM sqlite_master WHERE name=?',(self.table,)))
            columns=tuple(row[1] for row in db.execute('PRAGMA table_info("'+self.table+'")'))
            if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('Database integrity check failed')
            if objects!=[('table',)] or columns!=COLUMNS:raise ValueError('Unsupported EasyAuth SQLite schema')
            table='"'+self.table+'"'
            # Do not select secret JSON, passwords, IPs or authentication timestamps into application code.
            invalid=db.execute('SELECT COUNT(*) FROM '+table+' WHERE NOT json_valid(data) OR username_lower!=lower(username) OR username IS NULL OR username_lower IS NULL OR data IS NULL').fetchone()[0]
            if invalid:raise ValueError('Account schema/identity requires review')
            invalid=db.execute("SELECT COUNT(*) FROM "+table+" WHERE json_type(data)!='object' OR (json_type(data,'$.dataVersion') IS NOT NULL AND (json_type(data,'$.dataVersion')!='integer' OR json_extract(data,'$.dataVersion')!=1))").fetchone()[0]
            if invalid:raise ValueError('Unsupported account data version')
            duplicates=db.execute('SELECT COUNT(*) FROM (SELECT 1 FROM '+table+' a, json_tree(a.data) j WHERE j.key IS NOT NULL GROUP BY a.id,j.parent,j.key HAVING COUNT(*)>1)').fetchone()[0]
            if duplicates:raise ValueError('Ambiguous duplicate authentication fields')
            db.create_function('privacy_effective',4,effective,deterministic=True)
            expression="privacy_effective(uuid,json_extract(data,'$.forcedUuid'),json_extract(data,'$.onlineAccount'),username)"
            db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+expression+' IS NULL').fetchone()
            placeholders=','.join('?' for _ in aliases)
            count=db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+expression+'=? OR username_lower IN ('+placeholders+')',(subject,*aliases)).fetchone()[0]
        except sqlite3.Error:
            raise ValueError('Authentication verification failed; no absence proof') from None
        finally:db.close()
        after=self.path.stat()
        if self.stopped() is not True or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError('Authentication store changed during verification')
        return {'absent':count==0,'fingerprint':fingerprint({'schema':'EasyAuth3.4.4-SQLite','subject':subject,'matches':count,
                'size':after.st_size,'mtime_ns':after.st_mtime_ns})}
