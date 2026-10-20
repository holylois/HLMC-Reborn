"""Bounded GET-only Discord verification. Never posts, edits or deletes messages.

Requires an independently reviewed guild/channel inventory and a known nonempty message-content canary.
No claim about Discord's own retention, recipients' copies, deleted channels or unreviewed DMs.
"""
import hashlib,json,re,urllib.request,urllib.parse
from datetime import datetime
from .restore_ledger import fingerprint
from .identity_codec import contains_identity

def snowflake(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9]{17,20}',value):raise ValueError('Invalid Discord identifier')
    return value

class DiscordGET:
    def __init__(self,token):self.token=token
    def __call__(self,path):
        if not re.fullmatch(r'/[A-Za-z0-9_/?=&.%:-]+',path):raise ValueError('Unsupported Discord route')
        request=urllib.request.Request('https://discord.com/api/v10'+path,headers={'Authorization':'Bot '+self.token,'User-Agent':'HolyLoisPrivacyReview/1.0'})
        # Redirects must not forward the bot credential to another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
                raw=response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024:raise ValueError('Discord response exceeds budget')
                return json.loads(raw)
        except Exception:raise ValueError('Discord read failed; no absence proof') from None

class DiscordScope:
    def __init__(self,get,guild,channels,canary,content_sha256,stopped,max_pages=100):
        self.get,self.guild,self.stopped=get,snowflake(guild),stopped
        self.channels={snowflake(value) for value in channels}
        if not self.channels or max_pages<1 or max_pages>1000:raise ValueError('Reviewed bounded Discord scope required')
        self.canary=(snowflake(canary[0]),snowflake(canary[1]));self.canary_sha=content_sha256;self.max_pages=max_pages
    def verify(self,request):
        if self.stopped() is not True:raise ValueError('Bridge/exporters must be stopped')
        probe=self.get('/channels/'+self.canary[0]+'/messages/'+self.canary[1])
        content=probe.get('content')
        if not isinstance(content,str) or not content or hashlib.sha256(content.encode()).hexdigest()!=self.canary_sha:raise ValueError('Message-content visibility is unproven')
        def inventory():
            rows=self.get('/guilds/'+self.guild+'/channels')
            if not isinstance(rows,list):raise ValueError('Malformed channel inventory')
            if any(row.get('type') not in (0,2,4,5,13,15,16) for row in rows):raise ValueError('Unknown Discord channel type')
            parents={snowflake(row['id']):row for row in rows if row['type']!=4}
            if set(parents)!=self.channels:raise ValueError('Discord channel coverage changed')
            all_threads={}
            def take(thread):
                identity=snowflake(thread['id'])
                if thread.get('parent_id') not in parents or thread.get('type') not in (10,11,12):raise ValueError('Unreviewed thread parent/type')
                if identity in all_threads and all_threads[identity]!=thread:raise ValueError('Thread changed during inventory')
                all_threads[identity]=thread
                if len(all_threads)>10000:raise ValueError('Thread inventory budget exceeded')
            active=self.get('/guilds/'+self.guild+'/threads/active')
            if not isinstance(active,dict) or not isinstance(active.get('threads'),list):raise ValueError('Incomplete active threads')
            for thread in active['threads']:take(thread)
            for channel,row in sorted(parents.items()):
                if row['type'] not in (0,5,15,16):continue
                for kind in (('public','private') if row['type']==0 else ('public',)):
                    cursor=None
                    for page in range(self.max_pages):
                        route='/channels/'+channel+'/threads/archived/'+kind+'?limit=100'
                        if cursor:route+='&before='+urllib.parse.quote(cursor,safe='')
                        result=self.get(route)
                        if not isinstance(result,dict) or not isinstance(result.get('threads'),list) or type(result.get('has_more')) is not bool:raise ValueError('Incomplete archived threads')
                        timestamps=[]
                        for thread in result['threads']:
                            stamp=thread.get('thread_metadata',{}).get('archive_timestamp')
                            if not isinstance(stamp,str):raise ValueError('Archived timestamp missing')
                            instant=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                            if instant.tzinfo is None or cursor and instant>=datetime.fromisoformat(cursor.replace('Z','+00:00')):raise ValueError('Archived thread pagination stalled')
                            timestamps.append((instant,stamp));take(thread)
                        if not result['has_more']:break
                        if not timestamps:raise ValueError('Empty incomplete archive page')
                        cursor=min(timestamps)[1]
                    else:raise ValueError('Archived threads exceed review budget')
            message_channels={identity for identity,row in parents.items() if row['type'] not in (15,16)}|set(all_threads)
            metadata=rows+list(all_threads.values())
            return fingerprint(metadata),message_channels,metadata
        before,channels,metadata=inventory()
        identities={snowflake(value) for value in request.get('discord_ids',[])}
        if not identities:raise ValueError('Verified Discord account linkage or explicit separate case review required')
        def scan():
            evidence=[];present=contains_identity(metadata,request)
            for channel in sorted(channels):
                cursor=None;seen=set()
                for page in range(self.max_pages):
                    route='/channels/'+channel+'/messages?limit=100'+('&before='+cursor if cursor else '')
                    rows=self.get(route)
                    if not isinstance(rows,list) or len(rows)>100:raise ValueError('Malformed Discord message page')
                    if not rows:break
                    ids=[snowflake(row['id']) for row in rows]
                    if len(set(ids))!=len(ids) or any(value in seen or cursor and int(value)>=int(cursor) for value in ids):raise ValueError('Discord pagination is incomplete')
                    seen.update(ids);cursor=min(ids,key=int)
                    for row in rows:
                        if row.get('channel_id')!=channel:raise ValueError('Mismatched Discord channel')
                        # Files need individual content review; filename/URL scanning is not sufficient.
                        if row.get('attachments') or row.get('sticker_items'):raise ValueError('Discord attachment review required')
                        if not all(key in row for key in ('author','content','embeds','mentions')):raise ValueError('Incomplete Discord message')
                        if not isinstance(row['content'],str):raise ValueError('Unknown Discord content shape')
                        present=present or contains_identity(row,request) or any(value in json.dumps(row) for value in identities)
                        evidence.append(fingerprint(row))
                else:raise ValueError('Discord history exceeds review budget')
            return present,evidence
        present,evidence=scan()
        second_present,second_evidence=scan()
        if evidence!=second_evidence:raise ValueError('Discord message bodies changed during verification')
        present=present or second_present
        after,after_channels,after_metadata=inventory()
        if before!=after or channels!=after_channels or self.stopped() is not True:raise ValueError('Discord scope changed during verification')
        return {'absent':not present,'fingerprint':fingerprint({'guild':self.guild,'channels':sorted(self.channels),'request':request['id'],'messages':evidence})}
