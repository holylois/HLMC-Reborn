"""AudioPlayer2.5.0 ownership checks. Unknown owners/uploads/orphans require case review.
Never decodes, plays, uploads or deletes audio. Metadata version2 is source-reviewed.
"""
import json,uuid
from pathlib import Path
from .scoped_stores import FileScope
from .identity_codec import decode,contains_identity

class AudioScope(FileScope):
    def __init__(self,root,stopped,source):
        super().__init__(root,['world/audio_player_data','audioplayer_uploads'],stopped,source)
    def verify(self,request):
        if self.stopped() is not True:raise ValueError('Audio ownership requires stopped lease')
        self.owners={}
        path=self.base/'world/audio_player_data/meta.json'
        if path.exists():
            data=decode(super().raw('world/audio_player_data/meta.json',path.stat().st_size),'.json')
            if not isinstance(data,dict) or set(data)!={'version','files'} or data['version']!=2 or not isinstance(data['files'],dict):raise ValueError('Unknown AudioPlayer metadata')
            for key,row in data['files'].items():
                identity=str(uuid.UUID(key))
                if not isinstance(row,dict) or not isinstance(row.get('owner'),dict) or not {'uuid','name'}<=set(row['owner']):raise ValueError('Audio ownership review required')
                self.owners[identity]=row['owner']
        return super().verify(request)
    def metadata_only(self,name):
        return name.startswith('world/audio_player_data/') and Path(name).suffix.lower() in ('.mp3','.wav','.ogg','.pcm')
    def raw(self,name,size):
        if name.startswith('audioplayer_uploads/'):
            raise ValueError('Unmapped incoming audio requires exact ownership review')
        return super().raw(name,size)
    def inspect(self,name,raw,request):
        if name.startswith('audioplayer_uploads/'):
            raise ValueError('Unmapped incoming audio requires exact ownership review')
        if self.metadata_only(name):
            path=Path(name)
            if path.parent.as_posix()!='world/audio_player_data' or path.stem not in self.owners:raise ValueError('Orphan audio requires review')
            return contains_identity(self.owners[path.stem],request)
        return super().inspect(name,raw,request)
