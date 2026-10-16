"""Serves /stats.json (the public server stats) and /name/NAME (the launcher's name check) on 127.0.0.1:8101 for the Cloudflare
tunnel, readable by holylois.com. /name answers only {"taken": true|false} for one valid name, rate limited per visitor; the
list behind it (taken-names.json, written by make-stats.py) is never served."""
import json, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FILE = Path('/var/lib/holylois-stats/stats.json')
TAKEN = Path('/var/lib/holylois-stats/taken-names.json')
NAME = re.compile(r'/name/([A-Za-z0-9_]{3,16})')
LIMIT, WINDOW = 30, 60  # name checks per visitor per minute
_lock = threading.Lock()
_hits, _taken = {}, {'stamp': None, 'names': frozenset()}


def taken_names():
    try: stamp = TAKEN.stat().st_mtime_ns
    except OSError: return None
    with _lock:
        if stamp != _taken['stamp']:
            try: _taken.update(stamp=stamp, names=frozenset(json.loads(TAKEN.read_text(encoding='utf-8'))['names']))
            except (OSError, ValueError, KeyError, TypeError): return None
        return _taken['names']


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
            try: body = FILE.read_bytes()
            except OSError: self.send_error(503); return
            self.reply(200, body, 'public, max-age=120'); return
        match = NAME.fullmatch(path)
        if not match: self.send_error(404); return
        if not allowed(self.headers.get('CF-Connecting-IP') or self.client_address[0], time.monotonic()): self.send_error(429); return
        names = taken_names()
        if names is None: self.send_error(503); return
        self.reply(200, json.dumps({'taken': match.group(1).lower() in names}).encode(), 'no-store')

    def log_message(self, *args): pass


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8101), Handler).serve_forever()
