# -*- coding: utf-8 -*-
"""Choose a proper, high-quality logo for every channel.

  Sports | <league/service>   -> that league's / service's logo (event label first, e.g. 'AHL' in Hockey (Other))
  PPV & Events                -> the event service's logo (UFC, DAZN, Peacock ...) or a PPV / sport tile
  24/7 | ...                  -> 24/7 tile for that group
  Adult                       -> the provider's logo when it is big enough, else an 18+ tile
  everything else             -> tv-logos repo  ->  official logo from the matched guide (upsized)
                                 -> iptv-org database (>= 256 px)  ->  provider logo (if big enough)
                                 -> network logo (locals)  ->  a clean name tile

'Big enough' = at least MIN_SIDE px on its long side and not portrait (posters are not logos). Sizes come from
data/logo_dims.tsv (checked when this was built) plus a cache the server fills by checking new logos itself.
"""
import csv
import json
import os
import re
import threading
import urllib.parse
import urllib.request

from epgmap import norm
from logos import LogoIndex, TVLOGOS_RAW, NETWORK_LOGOS

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
REPO_LOGOS = os.environ.get('LOGO_BASE', 'https://raw.githubusercontent.com/marshallbelknap/iptv-playlist-cleaner/main/logos/')
MIN_SIDE = 256
TV = TVLOGOS_RAW + 'countries/'


def repo(name):
    return REPO_LOGOS + name + '.png'


# ---- league / service logos --------------------------------------------------------------------------
BRANDS = {
    'nfl': repo('nfl'), 'nba': repo('nba'), 'mlb': repo('mlb'), 'nhl': repo('nhl'), 'wnba': repo('wnba'),
    'mls': repo('mls'), 'milb': repo('milb'), 'ncaa': repo('ncaa'), 'ncaab': repo('ncaa'), 'ncaaf': repo('ncaa'),
    'epl': repo('epl'), 'premier league': repo('epl'), 'efl': repo('efl'), 'laliga': repo('laliga'),
    'la liga': repo('laliga'), 'serie a': repo('seriea'), 'ligue 1': repo('ligue1'), 'spfl': repo('spfl'),
    'uefa': repo('ucl'), 'ucl': repo('ucl'), 'uefa champions league': repo('ucl'), 'uel': repo('uel'),
    'uefa europa league': repo('uel'), 'europa league': repo('uel'), 'gaa': repo('gaa'), 'gaa tv': repo('gaa'),
    'ulster gaa': repo('gaa'), 'gaago': repo('gaa'), 'darts': repo('pdc'), 'pdc': repo('pdc'), 'golf': repo('pga'),
    'pga tour': repo('pga'), 'pga': repo('pga'), 'chl': repo('chl'), 'ohl': repo('ohl'), 'whl': repo('whl'),
    'qmjhl': repo('qmjhl'), 'ahl': repo('ahl'), 'echl': repo('echl'), 'pwhl': repo('pwhl'),
    'peacock': repo('peacock'), 'max': repo('max'), 'prime video': repo('primevideo'), 'amazon': repo('primevideo'),
    'flosports': repo('flosports'), 'flohockey': repo('flosports'), 'flowrestling': repo('flosports'),
    'floracing': repo('flosports'), 'flofc': repo('flosports'), 'flohoops': repo('flosports'),
    'flobaseball': repo('flosports'), 'flosoftball': repo('flosports'), 'flofootball': repo('flosports'),
    'florugby': repo('flosports'), 'flocollege': repo('flosports'), 'kayo': repo('kayo'), 'fox sports': repo('foxsports'),
    'bbc sport': repo('bbcsport'), 'bbc red button': repo('bbcsport'), 'ufc': repo('ufc'), 'ufc intl': repo('ufc'),
    'fifa': repo('fifa'), 'fifa+': repo('fifa'), 'victory+': repo('victoryplus'), 'b/r sports': repo('bleacherreport'),
    'bleacher report': repo('bleacherreport'), 'triller tv': repo('trillertv'), 'supercross': repo('supercross'),
    'lmp': repo('lmp'), 'sudamericana': repo('sudamericana'), 'libertadores': repo('libertadores'),
    'conmebol': repo('conmebol'), 'nrl': repo('nrl'), 'afl': repo('afl'), 'super league': repo('superleague'),
    'super league+': repo('superleague'), 'atp': repo('atp'), 'wta': repo('wta'), 'cymru football': repo('cymru'),
    'loi': repo('loi'), 'nifl': repo('nifl'), 'fa cup': repo('facup'), 'fa player': repo('facup'), 'wwe': repo('wwe'),
    'aew': repo('aew'), 'pfl': repo('pfl'), 'indycar': repo('indycar'), 'nascar': repo('nascar'), 'cricket': repo('icc'),
    'cbc sports': repo('cbcsports'), 'mxgp': repo('mxgp'), 'bundesliga': repo('bundesliga'),
    'nba g league': repo('gleague'), 'nwsl': repo('nwsl'), 'motogp': repo('motogp'), 'tt races': repo('motogp'),
    'rally tv': repo('rally-tv'), 'volleyball world': repo('volleyball-world'), 'clubber tv': repo('clubber-tv'),
    'dirtvision': repo('dirtvision'), 'nfhs': repo('nfhs'), 'matchroom': repo('matchroom'), 'tennis tv': repo('tennis-tv'),
    'ultimate pool': repo('ultimate-pool'), 'national league': repo('national-league'), 'scottish cup': repo('scottish-cup'),
    'espn play': repo('espn-play'), 'soccer': repo('soccer'), 'soccer ppv': repo('soccer'), 'boxing': repo('boxing'),
    'ppv': repo('ppv'), 'event': repo('live-event'), 'rugby': repo('rugby'), 'hockey': repo('hockey'),
    'tennis': repo('tennis'),
    # tv-logos repo (designed for dark screens)
    'espn+': TV + 'united-states/espn-plus-us.png', 'paramount+': TV + 'united-states/paramount-plus-us.png',
    'dazn': TV + 'international/dazn-int.png', 'dazn uk': TV + 'international/dazn-int.png',
    'dazn ca': TV + 'canada/dazn-ca.png', 'dazn us': TV + 'international/dazn-int.png',
    'tsn+': TV + 'canada/tsn-ca.png', 'sportsnet+': TV + 'canada/sportsnet-ca.png', 'stan': TV + 'australia/stan-sport-au.png',
    'netflix': TV + 'international/netflix-int.png', 'red bull tv': TV + 'international/red-bull-tv-int.png',
    'fubo sports': TV + 'united-states/fubo-sports-network-us.png', 'f1': TV + 'international/f1-tv-int.png',
    'f1 tv': TV + 'international/f1-tv-int.png', 'f1 apple tv': TV + 'international/f1-tv-int.png',
    'b1g+': TV + 'united-states/big-ten-network-us.png', 'btn+': TV + 'united-states/big-ten-network-us.png',
    'big10+': TV + 'united-states/big-ten-network-us.png', 'tennis channel+': TV + 'united-states/tennis-channel-us.png',
    'eurosport xtra': TV + 'united-kingdom/eurosport-1-uk.png', 'eurosport': TV + 'united-kingdom/eurosport-1-uk.png',
    'sky sports+': TV + 'united-kingdom/sky-sports-plus-icon-uk.png',
    'sky sports red button': TV + 'united-kingdom/sky-sports-main-event-uk.png',
    'tnt sports': TV + 'united-kingdom/tnt-sports-1-uk.png', 'viaplay xtra': TV + 'united-kingdom/viaplay-sports-1-uk.png',
    'viaplay': TV + 'united-kingdom/viaplay-sports-1-uk.png', 'world cup': repo('fifa'), 'world cup 2026': repo('fifa'),
    'cebl': repo('basketball'), 'khl': repo('hockey'), 'ojhl': repo('hockey'), 'sphl': repo('hockey'),
    'oua': repo('sports'), 'pay per view': repo('ppv'), 'live event': repo('live-event'),
}
CA_NETWORK_LOGOS = {'CTV': 'canada/ctv-ca.png', 'CTV2': 'canada/ctv-2-ca.png', 'CBC': 'canada/cbc-ca.png',
                    'Global': 'canada/global-ca.png', 'Citytv': 'canada/city-tv-ca.png', 'CHCH': 'canada/chch-ca.png',
                    'Omni': 'canada/omni-television-ca.png', 'NTV': 'canada/ntv-cjon-dt-ca.png'}
SPORTS_GROUP = {   # 'Sports | X' -> brand key (used when the event label has no logo of its own)
    'FloSports': 'flosports', 'ESPN+': 'espn+', 'Paramount+': 'paramount+', 'DAZN': 'dazn', 'NCAAB': 'ncaa',
    'NCAAF': 'ncaa', 'F1': 'f1', 'NBA': 'nba', 'TSN+': 'tsn+', 'MAX': 'max', 'NFL': 'nfl', 'MiLB': 'milb',
    'Soccer (Other)': 'soccer', 'NHL': 'nhl', 'Sportsnet+': 'sportsnet+', 'MLB': 'mlb', 'EFL': 'efl', 'MLS': 'mls',
    'Hockey (Other)': 'hockey', 'UEFA': 'uefa', 'Peacock': 'peacock', 'Tennis': 'tennis', 'CHL': 'chl', 'EPL': 'epl',
    'Other': None, 'WNBA': 'wnba', 'Prime Video': 'prime video', 'La Liga': 'laliga', 'GAA': 'gaa', 'Serie A': 'serie a',
    'SPFL': 'spfl', 'MotoGP': 'motogp', 'Darts': 'darts', 'Ligue 1': 'ligue 1', 'Golf': 'golf',
}
LOOP_TILES = {'24/7 | TV Shows': repo('247-tv-shows'), '24/7 | Movies': repo('247-movies'),
              '24/7 | Actors & Directors': repo('247-actors'), '24/7 | Kids & Animation': repo('247-kids')}
SPORT_WORDS = [(r'soccer|football|futbol|fútbol|\bfc\b|\bvs?\.? ', 'soccer'), (r'hockey', 'hockey'),
               (r'tennis', 'tennis'), (r'rugby', 'rugby'), (r'boxing|fight|ufc|mma', 'boxing'), (r'golf', 'golf')]
TRUSTED = re.compile(r'^https?://(raw\.githubusercontent\.com/(tv-logo|marshallbelknap)/|dtil\.tmsimg\.com/|'
                     r'd2n0069hmnqmmx\.cloudfront\.net/epgdata/1\.0/newchanlogos/600/|images\.pluto\.tv/)')


def bkey(s):
    return re.sub(r'\s+', ' ', (s or '').lower().replace('&', 'and')).strip()


def brand_of(name):
    """'NFL 02: Jaguars vs Eagles' -> 'nfl';  'ESPN+ 46: ...' -> 'espn+';  'DAZN UK 35' -> 'dazn uk';
    'Event: B/R MAX Sports Events 3' -> 'b/r max sports events'."""
    name = re.sub(r'^(?:event|ppv|live event)\s*:\s*', '', name, flags=re.I) or name
    m = re.match(r'^(.+?)\s+\d{1,3}(?::|\s|$)', name) or re.match(r'^([^:]+):', name)
    b = bkey(m.group(1)) if m else bkey(name)
    return re.sub(r'\s+(replay|events?|ppv)$', '', b)


def upgrade(url):
    """Ask the logo server for a large version where it supports sizes."""
    if not url:
        return url
    url = url.replace('&amp;', '&')
    if 'tmsimg.com/' in url:
        return url.split('?')[0] + '?w=720&h=540'
    url = re.sub(r'(newchanlogos/)\d+/\d+/', r'\g<1>600/600/', url)
    url = re.sub(r'(tvpassport\.com/image/station/)\d+x\d+/', r'\g<1>480x270/', url)
    url = re.sub(r'(image\.xumo\.com/v1/channels/channel/\d+/)\d+x\d+(\.\w+)', r'\g<1>512x512\2', url)
    url = re.sub(r'([?&]w=)\d+', r'\g<1>600', url) if 'foxtel.com.au' in url else url
    url = re.sub(r'([?&]imwidth=)\d+', r'\g<1>600', url) if 'kayosports' in url else url
    return url


class Dims:
    """Known logo sizes: bundled table + cache the server keeps up to date."""

    def __init__(self, cache_path=None):
        self.d = {}
        p = os.path.join(DATA, 'logo_dims.tsv')
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                parts = line.rstrip('\n').split('\t')
                if len(parts) == 2 and not line.startswith('#'):
                    self.d[parts[0]] = parts[1]
        self.cache_path = cache_path
        if cache_path and os.path.exists(cache_path):
            try:
                self.d.update(json.load(open(cache_path)))
            except ValueError:
                pass
        self.unknown = set()

    def ok(self, url):
        if not url:
            return False
        if TRUSTED.match(url):
            return True
        v = self.d.get(url)
        if v is None:
            self.unknown.add(url)
            return False
        m = re.match(r'(\d+)x(\d+)', v)
        if not m:
            return False
        w, h = int(m.group(1)), int(m.group(2))
        return max(w, h) >= MIN_SIDE and h <= w * 1.25


class Picker:
    def __init__(self, cache_dir=None, server_base=None):
        self.idx = LogoIndex(os.path.join(DATA, 'tvlogos_files.txt'), os.path.join(DATA, 'iptvorg'))
        self.dims = Dims(os.path.join(cache_dir, 'logo_dims.json') if cache_dir else None)
        self.server_base = server_base        # e.g. 'http://192.168.1.6:8765/TOKEN' -> name tiles from the NAS
        self.guide_icons = {}
        self._load_icons(os.path.join(DATA, 'guide_icons.tsv'))
        lists = os.environ.get('EPG_LIST_DIR')
        if lists and os.path.isdir(lists):
            for f in os.listdir(lists):
                if f.endswith('.icons.tsv'):
                    self._load_icons(os.path.join(lists, f))
        self.iptv = self._iptv_sizes()

    def _load_icons(self, path):
        if not os.path.exists(path):
            return
        for line in open(path, encoding='utf-8'):
            p = line.rstrip('\n').split('\t')
            if len(p) == 3 and p[2] and not line.startswith('#'):
                self.guide_icons[p[1]] = p[2]

    @staticmethod
    def _iptv_sizes():
        """iptv-org logo url -> 'WxH' (the database records sizes)."""
        out = {}
        p = os.path.join(DATA, 'iptvorg', 'logos.csv')
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding='utf-8')):
                if r.get('width') and r.get('height') and r.get('format', '').upper() in ('PNG', 'JPEG', 'WEBP'):
                    out[r['url']] = f"{r['width']}x{r['height']}"
        return out

    def ok(self, url):
        if url in self.iptv:
            self.dims.d.setdefault(url, self.iptv[url])
        return self.dims.ok(url)

    def tvlogos(self, cc, name):
        k = __import__('logos').lkey(name)
        for f in [__import__('logos').FOLDERS.get(cc), 'international']:
            hit = self.idx.repo.get(f, {}).get(k) if f else None
            if hit:
                return TVLOGOS_RAW + hit[0]
        return None

    def iptv_logo(self, cc, name):
        k = __import__('logos').lkey(name)
        country = __import__('logos').IPTV_CC.get(cc)
        u = self.idx.iptv.get((country, k)) if country else self.idx.iptv.get((None, k))
        return u if u and self.ok(u) else None

    def brand_prefix(self, cc, name):
        words = re.sub(r'[:|(\[].*$', '', name).split()
        for n in range(len(words) - 1, 0, -1):
            head = ' '.join(words[:n])
            if len(head) < 3 or head.lower() in ('the', 'us', 'uk', 'my', 'new', 'best', 'true', 'real', 'great'):
                continue
            hit = self.tvlogos(cc, head) or self.iptv_logo(cc, head)
            if hit:
                return hit
        return None

    def name_tile(self, name):
        title = re.sub(r'^[A-Z]{2,3}: ', '', name)
        title = re.sub(r'\s+(4K|FHD|HD|SD)$', '', title)
        if self.server_base:
            return f'{self.server_base}/logo/{urllib.parse.quote(title)}.png'
        return repo('tv')

    def pick(self, r, cc, lookup_name, tvg_id, provider_logo):
        g, name, kind = r['group'], r['name'], r['kind']
        if g in LOOP_TILES:
            return LOOP_TILES[g]
        if g == 'Adult':
            return provider_logo if self.ok(provider_logo) else repo('adult')
        if g.startswith('Sports | ') or g == 'PPV & Events':
            b = brand_of(name)
            for k in (b, bkey(r.get('label')), re.sub(r'\s+(uk|us|ca|au|intl)$', '', b)):
                if k in BRANDS:
                    return BRANDS[k]
            for k in ('b/r', 'netflix', 'espn play', 'btn+', 'big10+', 'pay per view', 'world cup', 'national league'):
                if k in b:
                    return BRANDS.get(k) or BRANDS.get('bleacher report')
            if g.startswith('Sports | '):
                k = SPORTS_GROUP.get(g[9:])
                if k and k in BRANDS:
                    return BRANDS[k]
            for rx, k in SPORT_WORDS:
                if re.search(rx, name, re.I):
                    return BRANDS[k]
            return BRANDS['ppv'] if g == 'PPV & Events' else repo('sports')
        # channels, locals, everything else
        if kind != 'local':
            hit = self.tvlogos(cc, lookup_name)
            if hit:
                return hit
        icon = upgrade(self.guide_icons.get((tvg_id or '').split('~')[0], ''))
        if icon and self.ok(icon):
            return icon
        hit = self.iptv_logo(cc, lookup_name)
        if hit:
            return hit
        if provider_logo and self.ok(provider_logo):
            return provider_logo
        hit = self.brand_prefix(cc, lookup_name)         # 'Music Choice 44' -> Music Choice, 'FOX 5 New York' -> FOX
        if hit:
            return hit
        if kind == 'local' and r.get('local') and r['local'].get('net') in NETWORK_LOGOS:
            return TVLOGOS_RAW + NETWORK_LOGOS[r['local']['net']]
        if kind == 'ca-local':                                    # 'CA: Kitchener - CTV - CKCO - 13'
            parts = name.split(' - ')
            net = parts[1].split()[0] if len(parts) > 1 else ''
            if net in CA_NETWORK_LOGOS:
                return TV + CA_NETWORK_LOGOS[net]
            if net in NETWORK_LOGOS:
                return TVLOGOS_RAW + NETWORK_LOGOS[net]
        return self.name_tile(name)


# ---- checking new logos (used by the server, in the background) ---------------------------------------
def image_size(data):
    """(w, h) from the first bytes of a PNG / JPEG / GIF / WebP, or None."""
    import struct
    if data[:8] == b'\x89PNG\r\n\x1a\n' and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return struct.unpack('<HH', data[6:10])
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        if data[12:16] == b'VP8X':
            return 1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little')
        if data[12:16] == b'VP8 ':
            w, h = struct.unpack('<HH', data[26:30])
            return w & 0x3fff, h & 0x3fff
        if data[12:16] == b'VP8L':
            b = data[21:25]
            return 1 + (((b[1] & 0x3f) << 8) | b[0]), 1 + (((b[3] & 0xf) << 10) | (b[2] << 2) | ((b[1] & 0xc0) >> 6))
    if data[:2] == b'\xff\xd8':
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xff:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return w, h
            seg = struct.unpack('>H', data[i + 2:i + 4])[0]
            i += 2 + seg
    return None


def probe(urls, cache_path, limit=400):
    """Check the size of logos we have not seen before; results go to the cache for the next rebuild."""
    try:
        cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    except ValueError:
        cache = {}
    n = 0
    for u in list(urls)[:limit]:
        if u in cache:
            continue
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0', 'Range': 'bytes=0-131071'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read(131072)
            size = image_size(data)
            cache[u] = f'{size[0]}x{size[1]}' if size else 'bad'
        except Exception:
            cache[u] = 'error'
        n += 1
    tmp = cache_path + '.tmp'
    json.dump(cache, open(tmp, 'w'))
    os.replace(tmp, cache_path)
    return n


def probe_async(urls, cache_path):
    if urls:
        threading.Thread(target=probe, args=(set(urls), cache_path), daemon=True).start()
