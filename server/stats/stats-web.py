"""Serves /stats.json (the public server stats) and /name/NAME (the launcher's name check) on 127.0.0.1:8101 for the Cloudflare
tunnel, readable by holylois.com. /name answers only {"taken": true|false} for one valid name, rate limited per visitor; the
list behind it (taken-names.json, written by make-stats.py) is never served."""
import json, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from privacy_exports import gate_bytes, sha, GATE, unique

FILE = Path('/var/lib/holylois-stats/stats.json')
TAKEN = Path('/var/lib/holylois-stats/taken-names.json')
CONTROL = Path('/var/lib/holylois-stats/privacy-control.json')
GATE_OWNER = 0
NAME = re.compile(r'/name/([A-Za-z0-9_]{3,16})')
LIMIT, WINDOW = 30, 60  # name checks per visitor per minute
_lock = threading.Lock()
_hits = {}


def protected_body(path, kind):
    """Serve only bytes produced for the currently open, operator-owned privacy epoch."""
    before, gate = gate_bytes(GATE, GATE_OWNER)
    if not gate['ready']: raise ValueError('Public exports are paused')
    raw = CONTROL.read_bytes()
    if len(raw) > 4096: raise ValueError('Oversized export control')
    control = json.loads(raw, object_pairs_hook=unique)
    if (set(control) != {'schema', 'epoch', 'stats_sha256', 'taken_sha256'} or control['schema'] != 1
            or control['epoch'] != gate['epoch']): raise ValueError('Stale export control')
    with path.open('rb') as stream: body = stream.read(16_000_001)
    if len(body) > 16_000_000 or sha(body) != control[kind + '_sha256']:
        raise ValueError('Export differs from reviewed output')
    if gate_bytes(GATE, GATE_OWNER)[0] != before or CONTROL.read_bytes() != raw:
        raise ValueError('Privacy state changed while reading output')
    return body


def allowed(visitor, now):
    with _lock:
        if len(_hits) > 10000: _hits.clear()
        recent = [t for t in _hits.get(visitor, []) if now - t < WINDOW]
        if len(recent) >= LIMIT: _hits[visitor] = recent; return False
        _hits[visitor] = recent + [now]
        return True


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, cache):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/stats.json', '/'):
            try: body = protected_body(FILE, 'stats')
            except (OSError, ValueError, KeyError, TypeError): self.reply(503, b'{"available":false}', 'no-store'); return
            self.reply(200, body, 'no-store'); return
        match = NAME.fullmatch(path)
        if not match: self.send_error(404); return
        if not allowed(self.headers.get('CF-Connecting-IP') or self.client_address[0], time.monotonic()): self.send_error(429); return
        try:
            data = json.loads(protected_body(TAKEN, 'taken'), object_pairs_hook=unique)
            if set(data) != {'names', 'withheld'}: raise ValueError('Unknown name-check schema')
            for values in data.values():
                if not isinstance(values, list) or any(not isinstance(n, str) or not re.fullmatch('[a-z0-9_]{3,16}', n) for n in values):
                    raise ValueError('Invalid taken names')
            names = data['names']
            if match.group(1).lower() in data['withheld']: raise ValueError('Name release needs separate account review')
        except (OSError, ValueError, KeyError, TypeError): self.reply(503, b'{"available":false}', 'no-store'); return
        self.reply(200, json.dumps({'taken': match.group(1).lower() in names}).encode(), 'no-store')

    def log_message(self, *args): pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8101), Handler).serve_forever()
