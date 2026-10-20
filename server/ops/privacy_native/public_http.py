"""Read-only current controlled public JSON export check. Not provider-wide historical erasure."""
import hashlib,json,urllib.request,urllib.parse
from .restore_ledger import fingerprint
from .identity_codec import contains_identity
from .store_adapters import unique

HOSTS={'holylois.com','stats.holylois.com','map.holylois.com'}
def read(url):
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('Reviewed public export URL required')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    request=urllib.request.Request(url,headers={'Cache-Control':'no-cache','Pragma':'no-cache','Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            if response.headers.get_content_type()!='application/json':raise ValueError('Export response is not JSON')
            raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:raise ValueError('Export response exceeds budget')
            return raw
    except Exception:raise ValueError('Public export fetch failed; no absence proof') from None

class HTTPExports:
    def __init__(self,urls,get=read):
        self.urls=tuple(urls);self.get=get
        if not self.urls:raise ValueError('Complete reviewed controlled-export URL inventory required')
    def verify(self,request):
        evidence=[];present=False
        for url in self.urls:
            raw=self.get(url)
            if self.get(url)!=raw:raise ValueError('Controlled export changed during verification')
            data=json.loads(raw.decode('utf-8'),object_pairs_hook=unique)
            present=present or contains_identity(data,request)
            evidence.append((url,hashlib.sha256(raw).hexdigest()))
        return {'absent':not present,'fingerprint':fingerprint(evidence)}
