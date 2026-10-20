# -*- coding: utf-8 -*-
"""Serve freshly cleaned playlists over HTTP so TiviMate/UHF always get current event names.

Environment:
  PROVIDER_URL_<NAME>                  one per provider; the name becomes the playlist file name,
                                       e.g. PROVIDER_URL_PRIVATE_IPTV -> /private-iptv.m3u
                                       (PROVIDER_URL alone works as playlist 1)
  ACCESS_TOKEN                         optional; when set, playlists live under /<token>/
  CACHE_MINUTES                        rebuild playlists at most this often (default 30)
  GUIDE_MINUTES                        rebuild the guide this often (default 60)
  PORT                                 default 8765

Playlists:  http://<host>:<port>[/<token>]/<name>.m3u   (/playlist.m3u = the first one)
Guide:      http://<host>:<port>[/<token>]/guide.xml.gz   (also /guide.xml; every playlist points to it)
"""
import gzip
import os
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import main as build  # noqa: E402
import guide  # noqa: E402

TOKEN = os.environ.get('ACCESS_TOKEN', '').strip().strip('/')
TTL = int(os.environ.get('CACHE_MINUTES', '30')) * 60
CACHE_DIR = os.environ.get('CACHE_DIR', tempfile.gettempdir())
GUIDE_TTL = int(os.environ.get('GUIDE_MINUTES', '60')) * 60
GUIDE_PATH = os.path.join(CACHE_DIR, 'guide.xml.gz')
GUIDE_SRC_DIR = os.path.join(CACHE_DIR, 'guide_sources')


def slug(key):
    """'1' -> 'playlist1', 'PIA' -> 'pia', 'Four_X_OTT' -> 'four-x-ott'."""
    return f'playlist{int(key)}' if key.isdigit() else re.sub(r'[^a-z0-9]+', '-', key.lower()).strip('-')


def providers():
    out = {}
    if os.environ.get('PROVIDER_URL', '').strip():
        out['playlist1'] = os.environ['PROVIDER_URL'].strip()
    for k, v in sorted(os.environ.items()):
        m = re.fullmatch(r'PROVIDER_URL_([A-Za-z0-9_]+)', k)
        if m and v.strip() and slug(m.group(1)):
            out[slug(m.group(1))] = v.strip()
    return out


PROVIDERS = providers()


class Playlist:
    def __init__(self, n, src):
        self.n, self.src = n, src
        self.path = os.path.join(CACHE_DIR, f'{n}_clean.m3u')
        self.lock = threading.Lock()
        self.built = 0.0

    def fresh(self):
        with self.lock:
            if time.time() - self.built > TTL or not os.path.exists(self.path):
                try:
                    build(self.src, self.path, gen_prefix=self.n)
                    self.built = time.time()
                    print(f'playlist {self.n} rebuilt', flush=True)
                except Exception as e:        # keep serving the last good copy
                    print(f'playlist {self.n} rebuild failed: {e}', file=sys.stderr, flush=True)
        return self.path


LISTS = {n: Playlist(n, s) for n, s in PROVIDERS.items()}
FIRST = next(iter(LISTS), None)
_guide_lock = threading.Lock()
_guide_built = [0.0]


def refresh_guide(force=False):
    with _guide_lock:
        if not force and os.path.exists(GUIDE_PATH) and time.time() - _guide_built[0] < GUIDE_TTL:
            return
        try:
            guide.build(GUIDE_PATH, [pl.path for pl in LISTS.values()], cache_dir=GUIDE_SRC_DIR)
            _guide_built[0] = time.time()
        except Exception as e:                # keep serving the last good guide
            print(f'guide rebuild failed: {e}', file=sys.stderr, flush=True)


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):      # never log request paths (they may contain the token)
        pass

    def do_GET(self):
        p = self.path.split('?')[0].rstrip('/')
        if p == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
            return
        base = f'/{TOKEN}' if TOKEN else ''
        if not p.startswith(base + '/') and p != base:
            self.send_error(404)
            return
        rest = p[len(base):] or '/'
        if rest in ('/guide.xml.gz', '/guide.xml', '/epg.xml.gz', '/epg.xml'):
            return self.send_guide(rest.endswith('.gz'))
        m = re.fullmatch(r'/(?:([a-z0-9-]+)\.m3u)?', rest.lower())
        n = (m.group(1) or 'playlist') if m else None
        if n == 'playlist':
            n = FIRST
        if n not in LISTS:
            self.send_error(404)
            return
        path = LISTS[n].fresh()
        if not os.path.exists(path):
            self.send_error(503, 'playlist not available yet')
            return
        with open(path, 'rb') as f:
            data = f.read()
        # point the app at this server's guide (one small file instead of many large public ones)
        host = self.headers.get('Host') or f'127.0.0.1:{self.server.server_port}'
        url = f'http://{host}{base}/guide.xml.gz'
        nl = data.find(b'\n')
        if data.startswith(b'#EXTM3U') and nl > 0:
            data = f'#EXTM3U x-tvg-url="{url}" url-tvg="{url}"'.encode() + data[nl:]
        self.send_response(200)
        self.send_header('Content-Type', 'audio/x-mpegurl; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_guide(self, gz):
        if not os.path.exists(GUIDE_PATH):
            self.send_error(503, 'guide not built yet - try again in a few minutes')
            return
        self.send_response(200)
        if gz:
            self.send_header('Content-Type', 'application/gzip')
            self.send_header('Content-Length', str(os.path.getsize(GUIDE_PATH)))
            f = open(GUIDE_PATH, 'rb')
        else:
            self.send_header('Content-Type', 'application/xml; charset=utf-8')
            f = gzip.open(GUIDE_PATH, 'rb')
        self.end_headers()
        with f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                self.wfile.write(b)


def background():
    """Keep playlists and guide current even when no app is asking (event slots change all day)."""
    while True:
        for pl in LISTS.values():           # one at a time: some providers allow only 1 connection
            pl.fresh()
        refresh_guide()
        time.sleep(60)


if __name__ == '__main__':
    if not LISTS:
        sys.exit('Set PROVIDER_URL_<NAME> (one per provider) to your provider M3U links.')
    os.makedirs(GUIDE_SRC_DIR, exist_ok=True)
    threading.Thread(target=background, daemon=True).start()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', '8765'))
    base = f'/{TOKEN}' if TOKEN else ''
    for n in LISTS:
        print(f'serving playlist {n} on :{port}{"/<token>" if TOKEN else ""}/{n}.m3u', flush=True)
    print(f'serving guide on :{port}{"/<token>" if TOKEN else ""}/guide.xml.gz', flush=True)
    ThreadingHTTPServer(('0.0.0.0', port), H).serve_forever()
