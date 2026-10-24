# -*- coding: utf-8 -*-
"""One identity, one name per channel.

Providers spell the same channel many ways ('FOX News', 'FOX News Channel', 'FOX News (FNC)', 'Fox News HD').
`identity(cc, name)` reduces a cleaned name to a key that every spelling of that channel shares, and
`Namer` picks one display name per key (a hand-checked official name when we have one, otherwise the
spelling most copies use), so every copy of a channel - in both playlists - carries the same name, guide
and logo.
"""
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
QUALITY = re.compile(r' (4K|FHD|HD|SD)$')
NUM_WORDS = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7',
             'eight': '8', 'nine': '9', 'ten': '10'}
FILLER = {'channel', 'network', 'tv', 'television', 'the', 'hd', 'fhd', 'sd', 'uhd', '4k', 'hdtv', 'feed'}
REGIONAL = {'sportsnet', 'tsn', 'cbc', 'ctv', 'global', 'citytv', 'omni', 'cp24', 'atn', 'bbc', 'itv', 'stv', 'utv',
            'spectrum', 'news', 'fanduel', 'nbc', 'abc', 'cbs', 'fox'}   # 'Sportsnet East', 'BBC One East' are regions
# trailing '(XYZ)' tags that only repeat the name or mark a backup: 'FOX Business (FBN)', 'TNT (BK)'
TAIL_ABBR = re.compile(r'\s*\((?:[A-Z][A-Za-z0-9&+]{1,5}|[Bb][Kk]|ST|VCS|Backup|Alt|Event Only|event only)\)\s*$')
JUNK = re.compile(r'\s*(\?\?+|[●◉★•○◆■]|\*+)\s*')
# provider typos and leftovers that would otherwise become a second spelling of a channel
TYPOS = [(re.compile(r'^Religious\s+(?=3abn|3ABN)', re.I), ''), (re.compile(r'^Puto TV\b'), 'Pluto TV'),
         (re.compile(r'^erra Mater\b', re.I), 'Terra Mater'), (re.compile(r'\(St Loius\)'), ''),
         (re.compile(r'\bMonterial\b'), 'Montreal'), (re.compile(r"\bIdea's\b"), 'Ideas'),
         (re.compile(r'^Spectrum New 1\b'), 'Spectrum News 1'), (re.compile(r'\bCinemaxx More Maxx\b'), 'MoreMax'),
         (re.compile(r'^BBC BBC\b'), 'BBC'), (re.compile(r'^TBN TBN\b'), 'TBN'),
         (re.compile(r'\bNick\.JR\b', re.I), 'Nick Jr.'), (re.compile(r'\s*/\s*Peppa Pig$'), ''),
         (re.compile(r"\\'96"), '-'), (re.compile(r'^Comedy Cent Xtra\b'), 'Comedy Central Extra'),
         (re.compile(r'^Crime Inv\b(?!estigation)'), 'Crime & Investigation'),
         (re.compile(r'\bAnimal Plnt\b'), 'Animal Planet'), (re.compile(r'^Set Sports\b'), 'Sky Sports')]


def _ascii(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()


def _load_table(name):
    """data/<name>: 'cc<TAB>key<TAB>value' rows; cc '*' applies to every country."""
    out = {}
    p = os.path.join(_DATA, name)
    if os.path.exists(p):
        for line in open(p, encoding='utf-8'):
            if line.startswith('#') or not line.strip():
                continue
            f = line.rstrip('\n').split('\t')
            if len(f) >= 3:
                out[(f[0], f[1])] = f[2]
    return out


ALIASES = _load_table('channel_aliases.tsv')      # (cc, key) -> canonical key
NAMES = _load_table('channel_names.tsv')          # (cc, canonical key) -> official display name
CATEGORY = _load_table('channel_categories.tsv')  # (cc, canonical key) -> 'Sports' / 'Movies' / ...


def group_key(k):
    """('US', 'hbowest') -> ('US', 'hbo'): a channel's West, Pacific and +1 feeds sit in its group."""
    cc, key = k
    base = re.sub(r'(?<=.{3})(west|pacific|plus1)$', '', key)
    return (cc, ALIASES.get((cc, base)) or base)


def clean(name):
    """Tidy a name without changing which channel it is: stray marks, unbalanced brackets, backup tags,
    abbreviations repeated in brackets ('Game Show Network (GSN)', 'The Movie Channel (TMC) East')."""
    n = JUNK.sub(' ', name)
    for rx, rp in TYPOS:
        n = rx.sub(rp, n)
    n = re.sub(r'\(\s*(East|West|Pacific)\s*$', r'\1', n)          # 'Paramount+ With Showtime (East'
    n = re.sub(r'[,;/]+\s*$', '', n)                                # 'fyi,', 'NESN /'
    n = re.sub(r"\b(\d0)'(?=\s|$)", r'\1s', n)                       # "Hollywood Suite 70'" 
    n = ' '.join(n.split())
    feed = ''
    m = re.search(r'\s+\(?(East|West|Pacific)\)?$', n)
    if m and TAIL_ABBR.search(n[:m.start()]):
        feed, n = ' ' + m.group(1), n[:m.start()]
    while True:
        m = TAIL_ABBR.search(n)
        if not m or m.start() == 0:
            break
        n = n[:m.start()]
    m = re.fullmatch(r"([A-Za-z0-9+!']{2,7})\s*\(([^()]+)\)", n)       # 'FXM (FX Movie Channel)', 'LiveNow (LIVENOW)'
    if m and (len(m.group(2).split()) >= 2 or m.group(2).lower() == m.group(1).lower()):
        n = m.group(1)
    return (' '.join(n.split()).strip(' -|:') + feed).strip()


def _tv_suffix(w):
    """'GetTV' / 'Get TV', 'FaithTV' / 'Faith TV', 'UPtv' / 'Up TV' are one channel."""
    return w[:-2] if len(w) >= 4 and w.endswith('tv') else w


def raw_key(cc, base):
    """'FOX News Channel' -> 'foxnews';  'BBC Two' -> 'bbc2';  'Nickelodeon East' -> 'nickelodeon' (US)."""
    s = _ascii(clean(base)).lower()
    s = re.sub(r'^disc\.?\s*(?=history|science|turbo)', 'discovery ', s)      # 'Disc.History'
    s = re.sub(r'\bplnt\b', 'planet', s)
    if s.startswith('spectrum news'):                  # 'Spectrum News 1 (Carolinas) Charlotte' = '... 1 Charlotte'
        s = re.sub(r'\([^)]*\)', ' ', s)
    s = re.sub(r'\b([a-z])\s*&\s*([a-z])\b', r'\1n\2', s)          # 'A&E' -> 'ane', 'M&E' -> 'mne', 'R&B' -> 'rnb'
    s = s.replace('&', ' and ').replace('+', ' plus ')
    s = re.sub(r"[^a-z0-9]+", ' ', s)
    words = [NUM_WORDS.get(w, w) for w in s.split()]
    regional = words and words[0] in REGIONAL and (len(words) <= 2 or words[0] in ('bbc', 'itv', 'stv', 'utv',
                                                                                      'sportsnet', 'tsn'))
    if cc == 'US' or not regional:                     # East is just the default feed of a cable channel
        words = [w for w in words if w not in ('east', 'eastern')] or words
    words = [w for w in words if w != 'and'] or words
    if cc == 'AU' and len(words) > 1:                  # '7Two Sydney' / '7two', 'ABC Kids National' / 'ABC Kids'
        words = [w for w in words if w not in ('sydney', 'national')] or words
    core = [_tv_suffix(w) for w in words if w not in FILLER]
    if not core or (len(core) == 1 and core[0].isdigit()):   # 'TV One', 'Channel 4': keep the words
        core = [w for w in words if w not in ('hd', 'fhd', 'sd', 'uhd', '4k', 'hdtv', 'the')] or words
    return ''.join(core)


RSN_REGIONS = ('detroit', 'florida', 'sun', 'greatlakes', 'midwest', 'north', 'ohio', 'socal', 'sandiego', 'south',
               'southeast', 'southwest', 'wisconsin', 'kansascity', 'neworleans', 'oklahoma', 'tennessee', 'carolinas',
               'indiana', 'arizona', 'west', 'northcarolina', 'stlouis', 'cincinnati', 'cleveland')
RSN = re.compile(r'^(?:foxsports|ballysports|fanduelsportsnetwork|fanduelsports|fanduel|fsn)(' + '|'.join(RSN_REGIONS) +
                 r')((?:plus|extra|2|alt|alternate)?)$')


def _nz_key(k):
    k = re.sub(r'^skysportsnz', 'skysport', k)
    k = re.sub(r'^skysports(?=\d|select|popup|premier|pl\b)', 'skysport', k)
    k = k.replace('popup', 'popup').replace('skysportpl', 'skysportpremierleague')
    k = re.sub(r'^(?:tab)?trackside', 'tabtrackside', k)
    return k


def _family_key(cc, k):
    """Channel families with many old names: the regional sports networks ('FOX Sports Detroit', 'Bally Sports
    Detroit', 'Fanduel Detroit' are all FanDuel Sports Network Detroit) and Spectrum News ('Spectrum News Buffalo'
    = 'Spectrum News 1 Buffalo')."""
    if cc == 'NZ':
        return _nz_key(k)
    if cc == 'UK':                                      # 'ITV Granada', 'ITV 1 Granada', 'ITV +1 Granada'
        return re.sub(r'^itv1?(plus1)?(anglia|border|central|granada|meridian|tynetees|westcountry|yorkshire|wales|'
                      r'channelislands|london|utv)', r'itv1\1\2', k)
    if cc != 'US':
        return k
    m = RSN.match(k)
    if m:
        return 'fanduelsportsnetwork' + m.group(1) + m.group(2).replace('alternate', 'alt')
    m = re.match(r'^spectrumnews(?!1|ny1|13\b|9\b)([a-z].*)$', k)
    if m and not k.startswith('spectrumnewsny1'):
        return 'spectrumnews1' + m.group(1)
    return k


def identity(cc, base):
    k = _family_key(cc, raw_key(cc, base))
    return ALIASES.get((cc, k)) or ALIASES.get(('*', k)) or k


def split_name(name):
    """'US: FOX News HD' -> ('US', 'FOX News', 'HD')."""
    q = None
    m = QUALITY.search(name)
    if m:
        q = m.group(1)
        name = name[:m.start()]
    cc = None
    m = re.match(r'^([A-Z]{2,3}): ', name)
    if m:
        cc = m.group(1)
        name = name[m.end():]
    return cc, name, q


try:
    from rules import ACRONYMS
except Exception:                                  # canon.py also works on its own
    ACRONYMS = set()

DISPLAY_FIX = [(re.compile(r'^Music Choice:\s+'), 'Music Choice '),
               (re.compile(r'\bNews12\b'), 'News 12'),
               (re.compile(r'\bStarzencore\b'), 'Starz Encore'),
               (re.compile(r'\bNEW York\b'), 'New York'),
               (re.compile(r'^CBSN (?=[A-Z][a-z])'), 'CBS News '),       # 'CBSN Boston' is now 'CBS News Boston'
               (re.compile(r'\bUSANet\b'), 'SportsNet'),                # provider typo 'AT&T USANet Pittsburgh'
               (re.compile(r'^Spectrum News 1 \([^)]*\)\s*-?\s*'), 'Spectrum News 1 '),
               (re.compile(r'^Spectrum News (?!1\b|NY1\b|13\b|9\b)(?=[A-Z])'), 'Spectrum News 1 '),
               (re.compile(r'^(?:FOX Sports|Bally Sports|Fanduel Sports Network|FanDuel Sports Network|Fanduel Sports|'
                           r'FanDuel Sports|Fanduel|FanDuel)\s+(?=(?:' + '|'.join(['Detroit', 'Florida', 'Sun', 'Great Lakes',
                           'Midwest', 'North', 'Ohio', 'SoCal', 'San Diego', 'South', 'Southeast', 'Southwest', 'Wisconsin',
                           'Kansas City', 'New Orleans', 'Oklahoma', 'Tennessee', 'Carolinas', 'Indiana', 'Arizona',
                           'West', 'North Carolina']) + r')\b)'), 'FanDuel Sports Network '),
               (re.compile(r'\s+\|\s+'), ' - '),
               (re.compile(r"'(\d0)'?s\b"), r'\1s'),            # "'70's" / "'90s" -> '70s' / '90s'
               (re.compile(r"\b(\d0)'s\b"), r'\1s'),
               (re.compile(r'\s+-\s+(?=\()'), ' '),               # 'Spectrum News 1 - (Kentucky)'
               (re.compile(r'(?<=\w)\s+:\s+'), ': '),               # 'The Gaming Central : League of Legends'
               (re.compile(r'\(\s+|\s+\)'), lambda m: m.group(0).strip()),
               (re.compile(r'^ITV 1\b'), 'ITV1'),
               (re.compile(r'^ITV \+1 (.+)$'), r'ITV1 \1 +1'),             # 'ITV +1 Granada' -> 'ITV1 Granada +1'
               (re.compile(r'^ITV (?=(?:Anglia|Border|Central|Granada|Meridian|Tyne Tees|Wales|West Country|Yorkshire|'
                           r'Channel Islands|London)\b)'), 'ITV1 '),
               (re.compile(r'(?<!\+)\s*\+1$'), ' +1'),                      # 'E4+1' / 'E4 +1' -> 'E4 +1' (not 'ESPN+ 1')
               (re.compile(r'^(.+?) \+1 (.+)$'), r'\1 \2 +1'),
               (re.compile(r"\b[A-Z][a-z]+\b"), lambda m: TOKEN_CASE.get(m.group(0), m.group(0))),
               (re.compile(r'\b(?:WE|We) ?TV\b|\bWEtv\b|\bWeTV\b'), 'WE tv')]
# brand capitals a title-cased provider name loses ('Afv Family' -> 'AFV Family', 'Xite Hits' -> 'XITE Hits')
TOKEN_CASE = {'Afv': 'AFV', 'Allblk': 'ALLBLK', 'Amg': 'AMG', 'Awe': 'AWE', 'Bek': 'BEK', 'Awsn': 'AWSN',
              'Xite': 'XITE', 'Mgm': 'MGM', 'Edm': 'EDM', 'Pd': 'PD', 'Oln': 'OLN', 'Aaa': 'AAA', 'Hidive': 'HIDIVE',
              'Lego': 'LEGO', 'Rvtv': 'RVTV', 'Tvoai': 'TVOAI', 'Twn': 'TWN', 'Mhz': 'MHz', 'Bnp': 'BNP',
              'Fifa': 'FIFA', 'Nxt': 'NXT', 'Hbcu': 'HBCU', 'Pll': 'PLL', 'Tmz': 'TMZ', 'Tyt': 'TYT', 'Ntd': 'NTD',
              'Cgtn': 'CGTN', 'Ndtv': 'NDTV', 'Crmz': 'CRMZ', 'Rtl': 'RTL', 'Ufc': 'UFC', 'Wwe': 'WWE', 'Aew': 'AEW',
              'Pga': 'PGA', 'Nhra': 'NHRA', 'Pbr': 'PBR', 'Lpga': 'LPGA', 'Atp': 'ATP', 'Wta': 'WTA', 'Mls': 'MLS',
              'Nfl': 'NFL', 'Nba': 'NBA', 'Nhl': 'NHL', 'Mlb': 'MLB', 'Espn': 'ESPN', 'Hbo': 'HBO', 'Bbc': 'BBC',
              'Itv': 'ITV', 'Cnn': 'CNN', 'Cnbc': 'CNBC', 'Msnbc': 'MSNBC', 'Abc': 'ABC', 'Cbs': 'CBS', 'Nbc': 'NBC',
              'Pbs': 'PBS', 'Bet': 'BET', 'Cmt': 'CMT', 'Mtv': 'MTV', 'Tbn': 'TBN', 'Ewtn': 'EWTN', 'Tlc': 'TLC',
              'Amc': 'AMC', 'Ifc': 'IFC', 'Tcm': 'TCM', 'Gsn': 'GSN', 'Hgtv': 'HGTV', 'Cbc': 'CBC', 'Ctv': 'CTV',
              'Tsn': 'TSN', 'Rds': 'RDS', 'Rte': 'RTE', 'Fxx': 'FXX', 'Fxm': 'FXM', 'Wfn': 'WFN', 'Vsin': 'VSiN',
              'Dtour': 'DTour', 'Djazz': 'DJAZZ', 'Hollywire': 'HollyWire', 'Floracing': 'FloRacing',
              'Shortstv': 'ShortsTV', 'Talksport': 'talkSPORT', 'Mavtv': 'MAVTV', 'Speedvision': 'SPEEDVISION',
              'Fm': 'FM', 'Wm': 'WM', 'Dj': 'DJ', 'Mx': 'MX', 'Mtm': 'MTM', 'Pmc': 'PMC', 'Nbt': 'NBT', 'Ptvn': 'PTVN',
              'Prc': 'PRC', 'Gv': 'GV', 'Tci': 'TCI', 'Enm': 'ENM', 'Chrgd': 'CHRGD', 'Yrf': 'YRF', 'Vvs': 'VVS',
              'Trublu': 'TruBlu', 'Foodxp': 'FoodXP', 'Eastenders': 'EastEnders', 'Ntv': 'NTV', 'Au': 'AU', 'Uk': 'UK'}


def tidy_display(s):
    for rx, rep in DISPLAY_FIX:
        s = rx.sub(rep, s)
    return ' '.join(s.split())


def _score(variant):
    """Tie-break between spellings of one channel: proper case, brand capitals ('FanDuel', 'PickleTV'),
    no SHOUTED words ('GOLD Coast'), no leftover brackets or feed/quality words."""
    s = 0
    letters = [c for c in variant if c.isalpha()]
    if letters and (variant == variant.lower() or (variant == variant.upper() and len(letters) > 4)):
        s -= 3
    for w in re.findall(r"[A-Za-z][A-Za-z'!.]*", variant):
        core = w.strip("'!.")
        if re.search(r'[a-z][A-Z]', core):
            s += 1                                   # camel-cased brand
        if len(core) >= 3 and core.isupper() and core not in ACRONYMS and not re.fullmatch(r'[A-Z]{2,4}', core):
            s -= 1                                   # 'GOLD', 'NEW York'
        if len(core) >= 3 and core.islower() and core not in ('and', 'the', 'of', 'by', 'with', 'for', 'from', 'in', 'on', 'to', 'at'):
            s -= 1                                   # 'Pickletv', 'nosey'
    if '(' in variant or ')' in variant:
        s -= 1
    if re.search(r'\b(East|HD|FHD|SD)\b', variant):
        s -= 2
    return s


EAST = re.compile(r'\s*\(?\bEast(ern)?\b\)?')


class Namer:
    """Collects every spelling of every channel (this playlist and, through the cache, the others) and
    picks one display name per identity."""

    def __init__(self, cache_dir=None, playlist='gen'):
        self.path = os.path.join(cache_dir, 'channel_names.json') if cache_dir else None
        self.playlist = playlist
        self.seen = defaultdict(Counter)              # (cc, key) -> spelling -> copies (this playlist)
        self.other = defaultdict(Counter)             # the same, from the other playlists' last build
        self.groups = defaultdict(Counter)            # (cc, key) -> playlist group -> copies (both playlists)
        self.my_groups = defaultdict(Counter)
        if self.path and os.path.exists(self.path):
            try:
                data = json.load(open(self.path, encoding='utf-8'))
            except ValueError:
                data = {}
            for pl, keys in data.items():
                if pl.split('#')[0] == playlist:
                    continue
                for k, spell in keys.items():
                    cc, _, key = k.partition('|')
                    (self.groups if pl.endswith('#groups') else self.other)[(cc, key)].update(spell)

    def add(self, cc, base):
        k = (cc, identity(cc, base))
        spelling = clean(base)
        if 'east' not in k[1] and re.search(r'\bEast(ern)?\b', spelling):    # East is just the default feed
            spelling = ' '.join(EAST.sub(' ', spelling).split()) or spelling
        self.seen[k][spelling] += 1
        return k

    def vote_group(self, k, group):
        self.my_groups[group_key(k)][group] += 1

    def group(self, k):
        """The group most copies of this channel are in (a channel sits in one group, not 'News' here and
        'Sports' there; its West and +1 feeds with it); a specific category beats General when the votes tie."""
        gk = group_key(k)
        if gk in CATEGORY:                            # hand-checked: 'MLS on Apple TV' is sport, not General
            return f'{k[0]} | {CATEGORY[gk]}'
        votes = Counter(self.my_groups.get(gk, {})) + self.groups.get(gk, Counter())
        if not votes:
            return None
        return max(votes.items(), key=lambda kv: (kv[1], not kv[0].endswith('General'), kv[0]))[0]

    def name(self, k):
        if k in NAMES:
            return NAMES[k]
        if ('*', k[1]) in NAMES:
            return NAMES[('*', k[1])]
        votes = Counter()
        for c in (self.seen.get(k, {}), self.other.get(k, {})):
            for v, n in c.items():
                votes[tidy_display(v)] += n
        if not votes:
            return None
        return max(votes.items(), key=lambda kv: (kv[1] + _score(kv[0]), _score(kv[0]), -len(kv[0]), kv[0]))[0]

    def save(self):
        if not self.path:
            return
        try:
            data = json.load(open(self.path, encoding='utf-8')) if os.path.exists(self.path) else {}
        except ValueError:
            data = {}
        data[self.playlist] = {f'{cc}|{key}': dict(c) for (cc, key), c in self.seen.items()}
        data[self.playlist + '#groups'] = {f'{cc}|{key}': dict(c) for (cc, key), c in self.my_groups.items()}
        tmp = self.path + '.tmp'
        json.dump(data, open(tmp, 'w', encoding='utf-8'))
        os.replace(tmp, self.path)
