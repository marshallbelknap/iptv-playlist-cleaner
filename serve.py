# -*- coding: utf-8 -*-
"""Serve a freshly cleaned playlist over HTTP so TiviMate/UHF always get current event names.

usage:  PROVIDER_URL='https://pia.cx/m3u/USER/PASS' python3 serve.py [port]
then point TiviMate / UHF at   http://<this-machine-ip>:<port>/playlist.m3u
The playlist is rebuilt from the provider at most once per CACHE_MINUTES (default 30).
"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import main as build  # noqa: E402

SRC = os.environ['PROVIDER_URL']
TOKEN = os.environ.get('ACCESS_TOKEN', '').strip('/')
TTL = int(os.environ.get('CACHE_MINUTES', '30')) * 60
OUT = os.path.join(tempfile.gettempdir(), 'playlist_clean.m3u')
_lock = threading.Lock()
_built = 0.0


def fresh():
    global _built
    with _lock:
        if time.time() - _built > TTL or not os.path.exists(OUT):
            try:
                build(SRC, OUT)
                _built = time.time()
            except Exception as e:           # keep serving the last good copy
                print('rebuild failed:', e, file=sys.stderr)
    return OUT


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):      # never log request paths (they contain the token)
        pass

    def do_GET(self):
        p = self.path.split('?')[0]
        if p == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            return
        want = {f'/{TOKEN}/playlist.m3u', f'/{TOKEN}'} if TOKEN else {'/', '/playlist.m3u'}
        if p not in want:
            self.send_error(404)
            return
        path = fresh()
        if not os.path.exists(path):
            self.send_error(503, 'playlist not available yet')
            return
        data = open(path, 'rb').read()
        self.send_response(200)
        self.send_header('Content-Type', 'audio/x-mpegurl; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    threading.Thread(target=fresh, daemon=True).start()   # warm the cache at boot
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', '8765'))
    print(f'serving on :{port}/playlist.m3u')
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
