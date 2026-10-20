import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from restore_payload import reconstruct

class Payload(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def archive(self,name,files,snapshot,kind='full',base=None):
        m={'manifestVersion':2,'id':name,'type':kind,'baseBackupId':base,'worldDirectoryName':'world','includedFiles':list(files),
            'snapshot':{n:{'size':len(raw),'modifiedTime':0,'sha256':hashlib.sha256(raw).hexdigest()} for n,raw in snapshot.items()}}
        data={'metadataVersion':1,'manifest':m,'status':{'completed':True,'brokenFiles':[],'type':kind,'backupId':name,'baseBackupId':base}}
        p=self.root/(name+'.zip')
        with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('justenoughbackups.data',json.dumps(data))
            for n,raw in files.items():z.writestr(n,raw)
        return p
    def test_full_and_delta_restore_only_final_snapshot(self):
        full=self.archive('base',{'level.dat':b'old','removed':b'gone','keep':b'kept'},{'level.dat':b'old','removed':b'gone','keep':b'kept'})
        diff=self.archive('diff',{'level.dat':b'new','added':b'new-file'},{'level.dat':b'new','keep':b'kept','added':b'new-file'},'differential','base')
        result=reconstruct(full,diff,self.root/'restored');self.assertTrue(result['disk_hashes_verified'])
        self.assertFalse((self.root/'restored/removed').exists());self.assertTrue(full.exists());self.assertEqual(result['deleted'],0)
    def test_wrong_base_blocks(self):
        full=self.archive('base',{'level.dat':b'old'},{'level.dat':b'old'})
        diff=self.archive('diff',{'level.dat':b'new'},{'level.dat':b'new'},'differential','other')
        with self.assertRaises(ValueError):reconstruct(full,diff,self.root/'nope')
        self.assertFalse((self.root/'nope').exists())
    def test_payload_hash_mismatch_blocks(self):
        p=self.archive('base',{'level.dat':b'evil'},{'level.dat':b'good'})
        with self.assertRaises(ValueError):reconstruct(p,None,self.root/'partial-preserved')
    def test_traversal_and_duplicate_members_block_before_extract(self):
        p=self.archive('base',{'level.dat':b'a','../escaped':b'b'},{'level.dat':b'a','../escaped':b'b'})
        with self.assertRaises(ValueError):reconstruct(p,None,self.root/'nope')
        self.assertFalse((self.root/'escaped').exists())
    def test_existing_destination_is_never_overwritten(self):
        p=self.archive('base',{'level.dat':b'a'},{'level.dat':b'a'});out=self.root/'existing';out.mkdir();(out/'keep').write_bytes(b'keep')
        with self.assertRaises(ValueError):reconstruct(p,None,out)
        self.assertEqual((out/'keep').read_bytes(),b'keep')
    def test_windows_drive_member_is_rejected(self):
        p=self.archive('base',{'level.dat':b'a','C:/outside.dat':b'b'},{'level.dat':b'a','C:/outside.dat':b'b'})
        with self.assertRaises(ValueError):reconstruct(p,None,self.root/'nope')
        self.assertFalse((self.root/'nope').exists())
    def test_duplicate_zip_member_is_rejected(self):
        import warnings
        p=self.archive('base',{'level.dat':b'a'},{'level.dat':b'a'})
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(p,'a') as archive:archive.writestr('level.dat',b'a')
        with self.assertRaises(ValueError):reconstruct(p,None,self.root/'nope')
        self.assertFalse((self.root/'nope').exists())
    def test_missing_unchanged_member_blocks(self):
        full=self.archive('base',{'level.dat':b'a'},{'level.dat':b'a'})
        diff=self.archive('diff',{'level.dat':b'b'},{'level.dat':b'b','missing':b'c'},'differential','base')
        with self.assertRaises(ValueError):reconstruct(full,diff,self.root/'nope')

if __name__=='__main__':unittest.main()
