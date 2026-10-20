# -*- coding: utf-8 -*-
"""Map cleaned channel names to epgshare01 XMLTV channel ids."""
import html
import os
import re
import unicodedata

EPG_DIR = os.environ.get('EPG_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'epg'))
SOURCES = {  # country -> guide lists searched in order (real TV listings first, free streaming services after)
    'US': ['US2', 'US_SPORTS1', 'FANDUEL1', 'PLEX1', 'DISTROTV1', 'CA2', 'METV', 'PEACOCK1', 'TBNPLUS1',
           'SAMSUNG_US', 'PLUTO_US', 'ROKU', 'PLEX_US', 'WHALETVPLUS1'],
    'CA': ['CA2', 'US2', 'SAMSUNG_CA', 'PLUTO_CA', 'PLEX_CA', 'ROKU'],
    'UK': ['UK1', 'IE1', 'SAMSUNG_GB', 'PLUTO_GB', 'PLEX_GB', 'RAKUTEN1'],
    'IE': ['IE1', 'UK1', 'SAMSUNG_GB', 'PLUTO_GB'],
    'AU': ['AU1', 'FOXTEL', 'KAYO', 'PLEX_AU'],
    'NZ': ['NZ1'],
    'INT': ['BEIN1', 'UK1', 'US2', 'MUSICBOX1', 'DELUXEMUSIC1', 'SAMSUNG_US', 'PLUTO_US', 'ROKU'],
    'ZA': ['ZA1'],
}
_E = 'https://epgshare01.online/epgshare01/epg_ripper_%s.xml.gz'
_M = 'https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/%s.xml.gz'
EPG_URLS = {
    'US2': 'https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz',
    'US_LOCALS1': 'https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz',
    'US_SPORTS1': 'https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz',
    'CA2': 'https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz',
    'UK1': 'https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz',
    'IE1': 'https://epgshare01.online/epgshare01/epg_ripper_IE1.xml.gz',
    'AU1': 'https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz',
    'NZ1': 'https://epgshare01.online/epgshare01/epg_ripper_NZ1.xml.gz',
    'BEIN1': 'https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz',
    'PLEX1': 'https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz',
    'DISTROTV1': 'https://epgshare01.online/epgshare01/epg_ripper_DISTROTV1.xml.gz',
    'ZA1': 'https://epgshare01.online/epgshare01/epg_ripper_ZA1.xml.gz',
    **{k: _E % k for k in ('FANDUEL1', 'PEACOCK1', 'TBNPLUS1', 'WHALETVPLUS1', 'MUSICBOX1', 'DELUXEMUSIC1', 'RAKUTEN1')},
    **{k: _M % v for k, v in {'PLUTO_US': 'PlutoTV/us', 'PLUTO_CA': 'PlutoTV/ca', 'PLUTO_GB': 'PlutoTV/gb',
                              'SAMSUNG_US': 'SamsungTVPlus/us', 'SAMSUNG_CA': 'SamsungTVPlus/ca',
                              'SAMSUNG_GB': 'SamsungTVPlus/gb', 'ROKU': 'Roku/all', 'PLEX_US': 'Plex/us',
                              'PLEX_CA': 'Plex/ca', 'PLEX_GB': 'Plex/gb', 'PLEX_AU': 'Plex/au', 'PBS': 'PBS/all',
                              'METV': 'MeTV/epg', 'FOXTEL': 'Foxtel/epg', 'KAYO': 'Kayo/epg'}.items()},
}
# id -> source list, so the guide builder knows which files to download
NAMED_PREFIX = re.compile(r'^(?:pluto tv|samsung tv plus|samsung|roku|plex|the roku channel)\s+', re.I)

# words that carry no identity
DROP_WORDS = {'hd', 'fhd', 'uhd', 'sd', '4k', 'tv', 'channel', 'network', 'the', 'us', 'usa', 'uk', 'ca',
              'canada', 'feed', 'east', 'eastern', 'national', 'and', 'en', 'english', 'ch', 'live'}
FEED_WORDS = {'west', 'pacific', 'pac', 'western'}

ALIASES = {  # normalised clean name -> normalised epg key
    'fox news': 'fox news', 'fs1': 'fox sports 1', 'fs2': 'fox sports 2', 'fox sports 1': 'fox sports 1',
    'tbs': 'tbs', 'usa': 'usa', 'a&e': 'a e', 'ae': 'a e', 'e!': 'e entertainment television',
    'e': 'e entertainment television', 'msnbc': 'ms now', 'ms now': 'ms now', 'nat geo': 'national geographic',
    'nat geo wild': 'national geographic wild', 'natgeo wild': 'national geographic wild',
    'id': 'investigation discovery', 'tlc': 'tlc', 'amc': 'amc', 'fx': 'fx', 'fxx': 'fxx', 'fxm': 'fx movie',
    'tcm': 'turner classic movies', 'hln': 'hln', 'headline news': 'hln', 'cnbc': 'cnbc',
    'espn news': 'espnews', 'espnews': 'espnews', 'nfl redzone': 'nfl redzone', 'nfl red zone': 'nfl redzone',
    'gsn': 'game show', 'game show network': 'game show', 'own': 'oprah winfrey', 'oprah winfrey network': 'oprah winfrey',
    'lmn': 'lifetime movie', 'lifetime movies': 'lifetime movie', 'lifetime movie network': 'lifetime movie',
    'bbc america': 'bbc america', 'sec network': 'sec', 'acc network': 'acc', 'big ten network': 'big ten',
    'btn': 'big ten', 'cbs sports network': 'cbs sports', 'nbc sports network': 'nbcsn',
    'paramount network': 'paramount', 'trutv': 'trutv', 'tru tv': 'trutv', 'cspan': 'c span',
    'cspan 2': 'c span 2', 'cspan 3': 'c span 3', 'c span': 'c span', 'tv land': 'tv land',
    'sky sports main event': 'skyspmainev', 'sky sports premier league': 'skysppl',
    'sky sports football': 'skyspfootball', 'sky sports f1': 'skyspf1', 'sky sports news': 'skyspnews',
    'sky sports cricket': 'skyspcricket', 'sky sports golf': 'skyspgolf', 'sky sports mix': 'skyspmix',
    'sky sports racing': 'skyspracing', 'sky sports action': 'skyspaction', 'sky sports arena': 'skysparena',
    'sky sports tennis': 'skysptennis', 'sky sports+': 'skyspplus', 'sky sports plus': 'skyspplus',
    'sky sports box office': 'skyspboxoff', 'sky sports nfl': 'skyspnfl',
    'bbc 1': 'bbc one', 'bbc1': 'bbc one', 'bbc 2': 'bbc two', 'bbc2': 'bbc two', 'bbc 4': 'bbc four',
    'bbc 3': 'bbc three', 'itv': 'itv1', 'itv 1': 'itv1', 'itv 2': 'itv2', 'itv 3': 'itv3', 'itv 4': 'itv4',
    'channel 4': 'channel 4', 'channel 5': 'channel 5', 'film 4': 'film4', 'more 4': 'more4',
    'tsn 1': 'tsn1', 'tsn 2': 'tsn2', 'tsn 3': 'tsn3', 'tsn 4': 'tsn4', 'tsn 5': 'tsn5',
    'alibi': 'u and alibi', 'u and alibi': 'u and alibi', 'lfc': 'lfctv', 'liverpool': 'lfctv',
    'cp24': 'cable pulse 24 cp24', 'crime and investigation': 'crime plus inv', 'much': 'much music',
    'cbc montreal': 'cbmt cbc montreal', 'chch': 'chch dt', 'e4': 'e4', 'sky sci fi': 'sky sci fi',
    'sky cinema sci fi': 'sky sci fi', 'syfy uk': 'sky sci fi', 'discovery science': 'disc science',
    'msgsn': 'msg sportsnet zone 1', 'bbc world news': 'bbc news north america', 'nesn plus': 'nesn plus new england sports plus',
    'nesn': 'nesn plus new england sports plus', 'discovery science': 'science', 'hsn': 'hsn home shopping',
    'cbs news': 'cbs news national stream', 'cbsn': 'cbs news national stream', 'cheddar news': 'cheddar',
    'espn sec network': 'sec', 'lifetime movie network lmn': 'lmn', 'lifetime movie network': 'lmn',
    'lifetime movies': 'lmn', 'lifetime movies lnn': 'lmn', 'starz kids and family': 'starz kids',
    'bloomberg television': 'bloomberg', 'espnu college sports': 'espnu', 'masn2': 'masn2 mid atlantic sports 2',
    'masn 2': 'masn2 mid atlantic sports 2', 'nbc sports chicago': 'chsn chicago sports', 'chicago sports': 'chsn chicago sports',
    'thegrio': 'grio', 'the grio': 'grio', 'viceland': 'vice', 'oxygen': 'oxygen true crime', 'dateline 24 7': 'dateline',
    'wetv': 'we', 'c span 1': 'cspan', 'game plus': 'game plus game plus', 'tvontario tvo': 'tvo',
    'the shopping channel': 'tsc', 'crime inv': 'crime plus inv', 'yesterday': 'u and yesterday',
    'premier sports 1 irish version': 'premier sports 1', 'premier sports 2 irish version': 'premier sports 2',
    'premier sports 1 ireland': 'premier sports 1', 'premier sports 2 ireland': 'premier sports 2',
    'premier sports 1 uk version': 'premier sports 1', 'premier sports 2 uk version': 'premier sports 2',
    'bbc one scotland': 'bbc one scot', 'itv london': 'itv1', 'virgin 1': 'virgin media one', 'virgin one': 'virgin media one',
    'virgin 2': 'virgin media two', 'virgin two': 'virgin media two', 'rte 2': 'rte two', 'rte news': 'rte news now',
    'sportsnet new york sny': 'sny sportsnet new york', 'sny': 'sny sportsnet new york', 'willow cricket extra': 'willow 2 xtra',
    'tennis channel': 'tennis', 'golf channel': 'golf', 'nbc golf channel': 'golf', 'nbc golf': 'golf',
    'espn acc network': 'acc', 'epix': 'mgm plus', 'epix hits': 'mgm plus hits', 'oxygen true crime': 'oxygen true crime',
    'sky sports nfl action': 'sky sports nfl', 'sky sports action nfl': 'sky sports action', 'e entertainment': 'e entertainment television',
    'bbc news': 'bbc news north america', 'red bull tv extreme sports': 'red bull', 'big ten network alternate': 'big ten network overflow',
    'bbc one': 'bbc one lon', 'bbc 1 hd': 'bbc one lon', 'sky history': 'sky history', 'tcm movies': 'tcm movies',
    'rte one': 'rte one', 'rte 1': 'rte one', 'rte two': 'rte2', 'rte 2': 'rte2',
    'showtime': 'paramount plus with showtime', 'sho': 'paramount plus with showtime',
    'hgtv': 'home and garden television', 'fox sports 1': 'fs1', 'fox sports 2': 'fs2', 'fs1': 'fs1',
    'mtv': 'mtv music television', 'mtv2': 'mtv2 music television', 'mtv live': 'mtvlive', 'reelz': 'reelzchannel',
    'buzzr': 'buzzr stream', 'ion': 'ion television', 'ion tv': 'ion television', 'metv': 'me',
    'me tv': 'me', 'gac family': 'great american family', 'great american country': 'great american family',
    'hallmark movies and mysteries': 'hallmark mystery', 'hallmark movies mysteries': 'hallmark mystery',
    'sky cinema greats': 'sky greats', 'sky cinema action': 'sky action', 'sky cinema family': 'sky family',
    'sky cinema thriller': 'sky thriller', 'sky cinema drama': 'sky drama', 'sky cinema premiere': 'sky premiere',
    'sky cinema premier': 'sky premiere', 'sky cinema sci fi horror': 'sky scifi horror',
    'sky cinema scifi horror': 'sky scifi horror', 'sky cinema animation': 'sky animation',
    'gold': 'u and gold', 'u and gold': 'u and gold', 'dave': 'u and dave', 'u and dave': 'u and dave',
    'nick': 'nickelodeon', 'syfy': 'syfy', 'sky syfy': 'sky sci fi', 'baby': 'baby', 'seven': '7', 'nine': '9', 'ten': '10', 'channel 9': '9', 'channel 7': '7', 'channel 10': '10',
    'the weather': 'weather', 'weather': 'weather', 'masn': 'masn mid atlantic sports',
    'nesn': 'nesn new england sports', 'tbn': 'trinity broadcasting', 'mtv 2': 'mtv2 music television',
}
CA_PLACE_WORDS = re.compile(r'\b(alberta|ab|ontario|on|british columbia|bc|quebec|qc|manitoba|mb|saskatchewan|sk|'
                            r'nova scotia|ns|new brunswick|nb|newfoundland|nl|pei|dt|east|west)\b', re.I)


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    s = s.lower().replace('&', ' and ').replace('+1', ' plus1 ').replace('+', ' plus ')
    s = re.sub(r"[^a-z0-9]+", ' ', s)
    return ' '.join(s.split())


def key_of(s, keep_feed=True, cc='US'):
    words = [w for w in norm(s).split() if w not in DROP_WORDS]
    feed = ''
    if cc in ('US', 'CA') and words and words[0] != 'sportsnet' and any(w in FEED_WORDS for w in words):
        feed = 'west'
        words = [w for w in words if w not in FEED_WORDS]
    k = ' '.join(words)
    if not k:   # e.g. "USA Network" -> keep the identity words
        k = ' '.join(w for w in norm(s).split() if w not in FEED_WORDS and w not in ('hd', 'fhd', 'sd', 'east'))
    return (k, feed) if keep_feed else k


class EpgIndex:
    def __init__(self):
        self.lists = {}
        self.index = {}       # list -> {(key, feed): [ids]}
        self.locals = {}      # call -> {sub: id}
        self.fkeys = {}
        self.all_ids = set()
        self.source_of = {}   # id -> list name
        for f in sorted(os.listdir(EPG_DIR)):
            if f.endswith('.tsv'):
                self._load_named(f[:-4], os.path.join(EPG_DIR, f))
                continue
            if not f.endswith('.txt'):
                continue
            name = f[:-4]
            ids = [html.unescape(l.strip()) for l in open(os.path.join(EPG_DIR, f)) if l.strip()]
            self.lists[name] = ids
            self.all_ids.update(ids)
            for i in ids:
                self.source_of.setdefault(i, name)
            if name == 'US_LOCALS1':
                for i in ids:
                    m = re.match(r'^([KW][A-Z]{2,3})-(?:DT|TV|CD|LD|CA)(\d?)\.us_locals1$', i)
                    if m:
                        self.locals.setdefault(m.group(1), {})[m.group(2) or '1'] = i
                    m = re.search(r'\(([KW][A-Z]{2,3})(?:-[A-Z]{2})?(\d?)\)', i)
                    if m:
                        self.locals.setdefault(m.group(1), {}).setdefault(m.group(2) or '1', i)
                continue
            idx = {}
            for i in ids:
                base = re.sub(r'\.(us2|us|uk|ca2|au|nz|ie|bein|plex|distro|za|be|de|musicbox|PEACOCK)$', '', i)
                base = re.sub(r'^(?:\[[A-Z0-9]+\]\.|UK:\.)', '', base)
                base = re.sub(r'\.-\.Rakuten\.TV$', '', base)
                base = re.sub(r'^plex\.tv\.', '', base)
                base = re.sub(r'\.\[FAST\]$', '', base)
                if name == 'US_SPORTS1':
                    m = re.match(r'^(MILB|MLB|NBA|NFL|NHL|WNBA|UFL)-(.+)$', base)
                    if m:
                        team = re.sub(r'([a-z])([A-Z])', r'\1 \2', m.group(2)).replace('.', ' ')
                        idx.setdefault((norm(m.group(1) + ' ' + team), ''), []).append(i)
                    continue
                pretty = base.replace('.', ' ').replace('_', ' ')
                pretty = re.sub(r'([a-z])([A-Z0-9])', r'\1 \2', pretty)
                pretty = re.sub(r'([0-9])([A-Z][a-z])', r'\1 \2', pretty)
                pretty = re.sub(r'([A-Z]{2,})([A-Z][a-z])', r'\1 \2', pretty)
                pretty = re.sub(r'(?<=[a-z])HD\b', ' HD', pretty)
                for variant in {pretty, base.replace('.', ' ').replace('_', ' ')}:
                    k, feed = key_of(variant, cc='US' if name in ('US2', 'CA2') else 'XX')
                    for kk in {k, k.replace(' ', '')}:
                        lst = idx.setdefault((kk, feed), [])
                        if i not in lst:
                            lst.append(i)
            self.index[name] = idx

    def _load_named(self, name, path):
        """Lists whose ids are opaque (Pluto, Samsung, Roku, Plex...): one 'id<TAB>name|name' per line."""
        idx = {}
        ids = []
        for line in open(path, encoding='utf-8'):
            if '\t' not in line:
                continue
            i, names = line.rstrip('\n').split('\t', 1)
            ids.append(i)
            self.source_of.setdefault(i, name)
            if name == 'PBS':                      # PBS member stations are keyed by call sign
                m = re.match(r'^([KW][A-Z]{2,3})$', i)
                if m:
                    self.locals.setdefault(m.group(1), {}).setdefault('1', i)
                continue
            for nm in names.split('|')[:2]:
                if not nm or re.fullmatch(r'[\d.]+', nm):
                    continue
                for variant in {nm, NAMED_PREFIX.sub('', nm)}:
                    k, feed = key_of(variant, cc='XX')
                    for kk in {k, k.replace(' ', '')}:
                        if kk:
                            lst = idx.setdefault((kk, feed), [])
                            if i not in lst:
                                lst.append(i)
        self.lists[name] = ids
        self.all_ids.update(ids)
        self.index[name] = idx

    def local(self, call, sub=None):
        d = self.locals.get(call)
        if not d:
            return None
        return d.get(sub or '1') or (d.get('1') if not sub else None)

    def fuzzy(self, lst, k, feed):
        try:
            from rapidfuzz import fuzz, process
        except ImportError:          # optional dependency; exact matching still works
            return None
        keys = self.fkeys.get(lst)
        if keys is None:
            keys = sorted({kk for (kk, f) in self.index.get(lst, {})})
            self.fkeys[lst] = keys
        if not k or len(k) < 3:
            return None
        m = process.extractOne(k, keys, scorer=fuzz.ratio, score_cutoff=91)
        if not m:
            return None
        kk = m[0]
        # first word must agree, and numbers must match exactly
        nums = lambda x: [w for w in x.split() if w.isdigit() or w == 'plus1']
        if kk.split()[0] != k.split()[0] or nums(kk) != nums(k):
            return None
        return self.index[lst].get((kk, feed)) or (self.index[lst].get((kk, '')) if feed == '' else None)

    def lookup(self, cc, clean_name):
        """clean_name: name without country prefix / quality suffix."""
        hit = self._lookup(cc, clean_name)
        if hit or cc != 'CA':
            return hit
        # 'CTV Edmonton Alberta', 'CBC Calgary (CBRT DT)' -> 'CTV Edmonton', 'CBC Calgary'
        nm = re.sub(r'\s*\([^)]*\)', ' ', clean_name)
        nm = re.sub(r'\s+', ' ', CA_PLACE_WORDS.sub(' ', nm)).strip()
        return self._lookup(cc, nm) if nm and nm != clean_name else None

    def _lookup(self, cc, clean_name):
        nm = clean_name
        nm = re.sub(r'\s*\((?:[A-Z]{2,5})\)\s*$', '', nm)  # trailing (OAN) etc
        k, feed = key_of(nm, cc=cc)
        alias = ALIASES.get(norm(nm).replace(' west', '').replace(' east', '').strip())
        if alias:
            alias = key_of(alias, keep_feed=False)
        cands = []
        for lst in SOURCES.get(cc, []):
            idx = self.index.get(lst, {})
            extra = [(alias or k) + ' sydney', k + ' sydney'] if cc == 'AU' else []
            for kk in ([alias] if alias else []) + [k, k.replace(' ', '')] + extra:
                if not kk:
                    continue
                hit = idx.get((kk, feed)) or (idx.get((kk, '')) if feed == '' else None)
                if hit:
                    cands.extend(hit)
                    break
            if cands:
                break
        if not cands:
            for lst in SOURCES.get(cc, []):
                hit = self.fuzzy(lst, alias or k, feed)
                if hit:
                    cands.extend(hit)
                    break
        if not cands:
            return None
        # prefer the plain/HD variant, shortest id
        want_plus1 = 'plus1' in k
        cands = [c for c in set(cands) if ('+1' in c or 'plus1' in c.lower()) == want_plus1] or \
            ([] if want_plus1 else list(set(cands)))
        if not cands:
            return None
        cands = sorted(cands, key=lambda i: ('Alternate' in i, '4K' in i, '.SD.' in i, len(i)))
        return cands[0]
