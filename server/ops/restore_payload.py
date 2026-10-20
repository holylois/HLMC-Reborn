"""JEB recovery reconstruction into a NEW directory. Never edits a live tree.

Streams every ZIP member for CRC/hash validation, then materializes only the final
snapshot. Full plus differential is selected by explicit base identity. Removed
files never enter the new tree; originals and archives are never deleted.
"""
import hashlib,json,os,re,stat,zipfile
from pathlib import Path,PurePosixPath

def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate recovery metadata key')
        result[k]=v
    return result

def safe(name):
    p=PurePosixPath(name)
    if not name or p.is_absolute() or p.as_posix()!=name or '..' in p.parts or ':' in name or '\\' in name or any(ord(c)<32 for c in name):
        raise ValueError('Unsafe snapshot member')
    return name

def header(archive):
    rows=archive.infolist();names=set()
    if not rows or len(rows)>100000:raise ValueError('Archive member budget exceeded')
    if sum(row.file_size for row in rows)>80*1024**3:raise ValueError('Archive expansion budget exceeded')
    for row in rows:
        safe(row.filename)
        if row.filename in names or row.is_dir() or stat.S_ISLNK(row.external_attr>>16) or row.flag_bits&1:
            raise ValueError('Ambiguous/encrypted/linked recovery member')
        names.add(row.filename)
    info=archive.getinfo('justenoughbackups.data')
    if info.file_size>8*1024*1024:raise ValueError('Recovery metadata too large')
    data=json.loads(archive.read(info),object_pairs_hook=unique);m,s=data['manifest'],data['status']
    if data.get('metadataVersion')!=1 or m.get('manifestVersion')!=2 or s.get('completed') is not True or s.get('brokenFiles'):
        raise ValueError('Incomplete or unknown recovery metadata')
    if not isinstance(m.get('id'),str) or not m['id'] or not isinstance(m.get('worldDirectoryName'),str) or not m['worldDirectoryName']:
        raise ValueError('Missing recovery identity or stream')
    kind=str(m.get('type')).lower()
    if kind not in ('full','differential') or str(s.get('type')).lower()!=kind or s.get('backupId')!=m.get('id') or s.get('baseBackupId')!=m.get('baseBackupId'):
        raise ValueError('Conflicting recovery identity')
    if not isinstance(m.get('snapshot'),dict) or not isinstance(m.get('includedFiles'),list):raise ValueError('Missing complete snapshot')
    if set(m['includedFiles'])!=names-{'justenoughbackups.data'} or len(m['includedFiles'])!=len(set(m['includedFiles'])):
        raise ValueError('Archive/manifest member mismatch')
    for name,row in m['snapshot'].items():
        safe(name)
        if not isinstance(row,dict) or type(row.get('size')) is not int or row['size']<0 or row['size']>40*1024**3:
            raise ValueError('Unsupported snapshot file size')
        if row.get('sha256') not in (None,'') and not re.fullmatch('[a-fA-F0-9]{64}',row['sha256']):raise ValueError('Invalid snapshot hash')
    return m

def reconstruct(full,differential,destination):
    destination=Path(destination).absolute()
    if destination.resolve()!=destination or destination.exists():raise ValueError('New canonical private destination required')
    sources=[Path(full)]+([Path(differential)] if differential else [])
    archives=[]
    try:
        archives=[zipfile.ZipFile(p) for p in sources];manifests=[header(z) for z in archives]
        base=manifests[0];latest=manifests[-1]
        if str(base['type']).lower()!='full' or base.get('baseBackupId'):raise ValueError('Full base required')
        if differential and (str(latest['type']).lower()!='differential' or latest.get('baseBackupId')!=base['id'] or latest.get('worldDirectoryName')!=base.get('worldDirectoryName')):
            raise ValueError('Wrong differential base or stream')
        snapshot=latest['snapshot']
        if 'level.dat' not in snapshot:raise ValueError('World level.dat missing from final snapshot')
        owners={}
        for i,m in enumerate(manifests):
            for name in m['includedFiles']:owners[name]=i
        if not set(snapshot)<=set(owners):raise ValueError('Recovery chain lacks required files')
        total=sum(row['size'] for row in snapshot.values())
        if total>80*1024**3:raise ValueError('Recovery expansion exceeds reviewed budget')
        destination.mkdir(mode=0o700)
        checks={};crc_files=0;hashed_files=0
        for i,(archive,m) in enumerate(zip(archives,manifests)):
            for name in m['includedFiles']:
                row=m['snapshot'].get(name)
                if row is None or archive.getinfo(name).file_size!=row['size']:raise ValueError('Archive size disagrees with snapshot')
                selected=name in snapshot and owners[name]==i;out=None;digest=hashlib.sha256();size=0
                try:
                    if selected:
                        path=destination/name;path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);out=path.open('xb')
                    with archive.open(name) as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):
                            size+=len(block);digest.update(block)
                            if out:out.write(block)
                    if size!=row['size'] or row.get('sha256') and digest.hexdigest()!=row['sha256'].lower():raise ValueError('Historical payload integrity failed')
                    crc_files+=1;hashed_files+=bool(row.get('sha256'))
                    if selected:
                        final=snapshot[name]
                        if size!=final['size'] or final.get('sha256') and digest.hexdigest()!=final['sha256'].lower():raise ValueError('Final snapshot content mismatch')
                        out.flush();os.fsync(out.fileno());checks[name]=digest.hexdigest()
                finally:
                    if out:out.close()
        if {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}!=set(snapshot):raise ValueError('Restored file inventory mismatch')
        for name,expected in checks.items():
            h=hashlib.sha256()
            with (destination/name).open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=expected:raise ValueError('Restored disk copy differs')
        return {'full_payload_crc_verified':True,'archive_payload_members':crc_files,'manifest_hashes_checked':hashed_files,
                'restored_files':len(checks),'restored_bytes':total,'disk_hashes_verified':True,
                'original_upload_verified':False,'expiry_eligible':False,'provider_writes':False,'deleted':0}
    finally:
        for archive in archives:archive.close()
