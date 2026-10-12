# -*- coding: utf-8 -*-
"""Adapter for "pipe style" providers (groups like 'US| ENTERTAINMENT', names like 'US| ESPN HD',
event slots like '... | 8K EXCLUSIVE | US: ESPN+ PPV 120').

It rewrites each entry's title and group into the vocabulary the main rules already understand,
so the same naming / grouping / guide / logo logic applies to every provider.
"""
import re

SUPERSCRIPT = [('ᴿᴬᵂ', ' '), ('⁶⁰ᶠᵖˢ', ' '), ('²⁵ᶠᵖˢ', ' '), ('⁵⁰ᶠᵖˢ', ' '), ('ᶜᶦᵗʸ', ' '), ('ᵁᴴᴰ', ' 4K '),
               ('ᴴᴰ', ' HD '), ('ᶠᴴᴰ', ' FHD '), ('[LIVE-EVENT]', ' '), ('3840P', ' 4K '), ('1920P', ' '),
               ('UHD/4K', ' 4K '), ('[EVENT]', ' '), ('[LIVE EVENT]', ' ')]

DROP = 'DROP'
US_STATE_CODES = ('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY '
                  'NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC').split()
# provider group -> synthetic source group understood by process.py
GROUP_MAP = {
    # ---- country channels
    'US| ENTERTAINMENT': 'US Entertainment', 'US| NEWS NETWORK': 'US News', 'US| MOVIES NETWORK': 'US Movies',
    'US| KIDS NETWORK': 'US Kids', 'US| SPORTS NETWORK': 'US Sports', 'US| MAX ESPN': 'US Sports',
    'US| NBC NETWORK': 'US NBC', 'US| FOX NETWORK': 'US FOX', 'US| CBS NETWORK': 'US CBS', 'US| ABC NETWORK': 'US ABC',
    'US| PBS NETWORK': 'US PBS', 'US| CW/MY NETWORK': 'US Locals & Regional', 'US| TV CITY': 'US Locals & Regional',
    'US| SPECTRUM NETWORK': 'United States', 'US| PRIME': 'United States', 'US| TUBI': 'Tubi TV (USA)',
    'US| TV': 'United States', 'US| PLUTO TV': 'United States', 'US| BIBLICAL/RELIGIOUS': 'United States',
    'US| NFL NETWORK HULU': 'United States',
    'UK| GENERAL': 'United Kingdom', 'UK| ENTERTAINMENT': 'UK Entertainment', 'UK| GENERAL HEVC': 'United Kingdom',
    'UK| ENTERTAINMENT HEVC': 'UK Entertainment', 'UK| DOCUMENTARY': 'United Kingdom',
    'UK| DOCUMENTARY HEVC': 'United Kingdom', 'UK| KIDS': 'UK Kids', 'UK| KIDS HEVC': 'UK Kids',
    'UK| BBCI': 'United Kingdom', 'UK| NOW TV': 'United Kingdom', 'UK| ITV X VIP': 'United Kingdom',
    'UK| DISCOVERY +': 'Discovery Plus', 'UK| PRIME': 'United Kingdom', 'UK| MOVIES': 'UK Movies',
    'UK| MOVIES HEVC': 'UK Movies', 'UK| NEWS': 'UK News', 'UK| SPORTS': 'UK Sports', 'UK| SPORTS HEVC': 'UK Sports',
    'UK| MUSIC': 'UK Music', 'UK| MC VIDEO': 'UK Music', 'MU| MUSIC CONCERTS': 'P2 Intl Music',
    'UK| WORLD SPORTS': 'P2 Intl Sports',
    'CA| ENGLISH': 'Canada', 'CA| LOCALS': 'Canada', 'CA| KIDS': 'Canada', 'CA| STINGRAY': 'Canada',
    'CA| PRIME': 'Canada', 'CA| SPORT': 'Canada Sports', 'CA| SPORTSNET': 'Canada Sports',
    'AU| AUSTRALIA': 'Australia', 'AU| 9NOW': 'Australia', 'NZ| NEW ZEALAND': 'Sky New Zealand',
    'NZ| SKY SPORTS NZ': 'Sky New Zealand', 'NZ| SKY SPORT': 'Sky New Zealand', 'IR| IRELAND': 'Irish TV',
    'HR| HORSE RACING': 'Betting TV', '4K UHD 3840P': 'P2 4K', '4K UHD': 'P2 4K',
    '18| FOR ADULTS': 'XXX',
    # ---- league / service events
    'US| FLO NETWORK': 'Flo Sports', 'US| FLO COLLEGE PPV': 'FloCollege', 'US| FLO RACING PPV': 'Flo Sports',
    'US| ESPN PLUS': 'ESPN Plus', 'US| ESPN+ PPV VIP': 'ESPN Plus', 'UK| ESPN+ PPV': 'ESPN Plus',
    'US| PARAMOUNT+ PPV': 'Paramount Plus', 'US| PEACOCK PPV': 'Peacock TV',
    'US| MAX PPV': '(US) HBO MAX', 'UK| MAX PPV': '(US) HBO MAX', 'UK| MAX PPV VIP': '(US) HBO MAX',
    'US| DAZN PPV': 'DAZN', 'UK| DAZN PPV': 'DAZN', 'CA| TSN+ PPV': 'TSN Plus',
    'CA| SN+ PPV': 'P2 Sportsnet+', 'CA| SPORTSNET PPV': 'P2 Sportsnet+', 'CA| ROGERS ROGERS SUPER SPORTS': 'P2 Sportsnet+',
    'US| NCAAB PACKAGE': 'NCAA Basketball', 'US| NCAAF PACKAGE': 'NCAAF', 'US| NFL PACKAGE': 'NFL',
    'US| NBA PACKAGE': 'NBA', 'US| NBA NETWORK VIP': 'NBA', 'US| NHL PACKAGE': 'NHL', 'US| VIAPLAY NHL PPV': 'NHL',
    'US| MLB PACKAGE': 'MLB Baseball league', 'US| MILB TV PPV': 'P2 MiLB', 'US| WNBA PACKAGE': 'WNBA League Pass',
    'US| MLS PPV VIP': 'MLS', 'US| MLS PPV': 'MLS', 'US| MLS NETWORK': 'MLS',
    'FORMULA 1 + MOTO GP': 'Formula One', 'UK| FORMULA 1 + MOTOGP': 'Formula One', 'FORMULA 1 ONBOARDS': 'F1 Formula',
    'US| APPLE TV F1 PPV': 'Formula One', 'UK| APPLE TV F1 PPV': 'Formula One',
    'NA| HOCKEY LEAGUE': 'P2 AHL', 'CA| AHL PPV': 'P2 AHL', 'CA| AHL TEAM': 'P2 AHL',
    'CA| OHL PPV': 'OHL', 'CA| WHL PPV': 'WHL', 'CA| QMJHL PPV': 'QMJHL',
    'UK| EPL PREMIER LEAGUE': 'EPL Premier League', 'UK| EPL PREMIER LEAGUE+ PPV': 'EPL Premier League',
    'UK| CHAMPIONSHIP': 'EFL iFOLLOW', 'UK| LEAGUE ONE': 'EFL iFOLLOW', 'UK| LEAGUE TWO': 'EFL iFOLLOW',
    'UK| SCOTTISH FOOTBALL': 'P2 SPFL', 'UK| SOCCER REPLAY': 'Football', 'UK| UEFA REPLAY': 'UEFA Championship',
    'UK| CUP GAMES & INTERNATIONAL': 'Football', 'UK| LA LIGA TEAM PPV': 'P2 La Liga',
    'UK| SERIE A TEAM PPV': 'P2 Serie A', 'UK| LIGUE 1 PPV': 'P2 Ligue 1', 'UK| NATIONAL LEAGUE': 'Football',
    'UK| FA PLAYER': 'Football', 'UK| WORLD CUP 2026 REPLAY': 'Football', 'IR| LOI PPV': 'Football',
    'IR| NIFL PPV': 'Football', 'UK| CYMRU FOOTBALL PPV': 'Football', 'UK| PSF PPV': 'Football',
    'US| SOCCER PPV': 'PPV Live Events', 'CA| SOCCER PPV': 'PPV Live Events', 'US| FIFA+ PPV': 'PPV Live Events',
    'US| NFHS PPV': 'PPV Live Events', 'US| BTN+ PPV': 'PPV Live Events', 'US| B1G+ PPV': 'PPV Live Events',
    'US| VICTORY+ PPV': 'PPV Live Events', 'US| STAN PPV': 'PPV Live Events', 'AU| STAN PPV': 'PPV Live Events',
    'US| TENNIS CHANNEL PLUS': 'P2 Tennis', 'US| TENNIS PPV': 'P2 Tennis',
    'US| ESPN PLAY': 'PPV Live Events', 'AU| ESPN PLAY PPV': 'PPV Live Events',
    'AU| NRL TV PPV': 'P2 Other', 'AU| AFL PPV': 'P2 Other', 'UK| RUGBY PPV': 'P2 Other',
    'UK| SUPER LEAGUE+ PPV': 'P2 Other', 'UK| GAA GO PPV': 'Others', 'UK| ULSTER GAA PPV': 'Others',
    'UK| PDC BOARD PPV': 'PDC DARTS', 'UK| TT RACE PPV': 'MOTOGP',
    'UK| SUPERCROSS PPV': 'PPV Live Events', 'UK| MXGP PPV': 'PPV Live Events', 'UK| RALLY TV PPV': 'PPV Live Events',
    'UK| VOLLEY BALL WORLD PPV': 'PPV Live Events', 'UK| ULTIMATE POOL PPV': 'PPV Live Events',
    'UK| MATCHROOM PPV': 'PPV Live Events', 'UK| PAY PER VIEW PPV': 'PPV Live Events',
    'UK| UFC/BOXING PPV': 'PPV Live Events', 'UK| PPV EVENTS': 'PPV Live Events', 'NA| PPV & LIVE EVENTS': 'PPV Live Events',
    'US| FITE TV PPV': 'PPV Live Events', 'US| NETFLIX PPV': 'PPV Live Events', 'UK| NETFLIX PPV': 'PPV Live Events',
    'US| B/R MAX SPORTS PPV': 'PPV Live Events', 'UK| HUB PREMIER PPV': 'PPV Live Events',
    'UK| TNT SPORTS EVENT': 'PPV Live Events', 'UK| BBC STREAM PPV': 'PPV Live Events',
    'UK| SKY SPORT+ VIP': 'PPV Live Events', 'UK| SKY SPORTS RED BUTTON': 'PPV Live Events',
    'UK| AMAZON PRIME +': 'PPV Live Events', 'UK| VIAPLAY PPV': 'PPV Live Events', 'US| DIRTVISION PPV': 'DIRTVision',
    'IR| CLUBBER PPV': 'Clubber', 'UK| EUROSPORT XTRA': 'PPV Live Events',
    # ---- non-English
    'UK| MONOMAX PPV': DROP, 'UK| MOLA PPV': DROP, 'UK| VIDIO EPL PPV': DROP, 'IR| SETANTA PPV': DROP,
    'NL| CLIPMYHORSE PPV': DROP, 'US| VIX+ DEPORTES': DROP, 'US| TELEMUNDO NETWORK': DROP,
    'CA| FRENCH': DROP, 'CA| FOREIGN': DROP,
}
# 24/7-style loops: any group starting with these, or VOD-like streaming "networks"
LOOP_GROUP_RE = re.compile(r'^(24/7|4K RELAX|UK\| 24/7|US\| CINEMANIA|US\| NETFLIX ON AIR|UK\| SKY STORE|'
                           r'UK\| NETFLIX ORIGINAL|US\| HULU NETWORK|US\| HBO MAX NETWORK|US\| DISNEY\+ NETWORK|'
                           r'US\| PEACOCK NETWORK|US\| PARAMOUNT\+$|UK\| APPLE TV\+ SERIES|UK\| PRIME VIDEO SERIES|'
                           r'UK\| BBCIPLAYER SERIES|UK\| SKYMIX|UK\| REALITY SHOW TV)|^$')

PREFIX_RE = re.compile(r'^(?:(?:US|UK|CA|AU|NZ|IR|EN|MU|HR|4K|4k|NA|TV|PRIME|TUBI|D\+|UK-[A-Z]+|IR)\s*\|\s*)+')
CC_OF_GROUP = {'US': 'US', 'UK': 'UK', 'CA': 'CA', 'AU': 'AU', 'NZ': 'NZ', 'IR': 'IRE', 'HR': 'INT', 'MU': 'INT'}
EVENT8K_A = re.compile(r'^(?P<ev>.*?)\|?\s*8K EXCLUSIVE\s*\|\s*(?:US|UK|CA|GB|NL):\s*(?P<svc>.+?)\s+(?P<n>\d+)\s*$')
EVENT8K_B = re.compile(r'^(?:US|UK|CA|GB|NL):\s*(?P<svc>.+?)\s+(?P<n>\d+)\s*-?\s*(?P<ev>.*?)\s*\|?\s*-?\s*8K EXCLUSIVE\s*$')
STATUS_RE = re.compile(r'^\s*(?:-\s*)?(?:NO EVENT STREAMING(?: NOW)?\s*-?|NEXT|ENDED|END|LIVE)\s*(?:\||-|$)\s*', re.I)


def canon_group(g):
    for a, b in SUPERSCRIPT:
        g = g.replace(a, ' ')
    g = re.sub(r'\s+', ' ', g).strip()
    g = re.sub(r'^US\| TV CITY.*', 'US| TV CITY', g) if 'TV' in g and 'ᶜᶦᵗʸ' in g else g
    return g


def is_pipe_style(entries):
    n = sum(1 for e in entries[:3000] if re.match(r'^[A-Z0-9+]{2,4}\| ', e['attrs'].get('group-title', '')))
    return n > 300


def clean_superscripts(t):
    for a, b in SUPERSCRIPT:
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t).strip()


LOCAL_A = re.compile(r"^(?P<city>[A-Z][A-Z .'/-]+?), (?P<st>[A-Z]{2})\s+(?P<call>[KW][A-Z]{2,3})(?:-D(?P<sub>\d))?\s+"
                     r"(?P<net>ABC|CBS|NBC|FOX|PBS|CW|MNT|MY|IND|ION)\s+(?P<num>\d+)\b")
LOCAL_B = re.compile(r'^A3 (?P<city>.+?) \d+ (?P<call>[KW][A-Z]{2,3}) (?P<net>ABC|CBS|NBC|FOX|PBS|CW|MNT) ')


def adapt_entry(e):
    raw_group = e['attrs'].get('group-title', '')
    raw_title = e['title']
    g = raw_group.replace('ᶜᶦᵗʸ', ' CITY ')
    g = canon_group(g)
    g = re.sub(r'^US\| TV CITY.*$', 'US| TV CITY', g)
    g = re.sub(r'^US\| MAX ESPN.*$', 'US| MAX ESPN', g)
    g = re.sub(r'^US\| PARAMOUNT\+ PPV.*$', 'US| PARAMOUNT+ PPV', g)
    t = clean_superscripts(raw_title)
    if re.fullmatch(r'[#\s]*[^#]*#{3,}\s*', t) or re.match(r'^#{3,}', t):
        return DROP, 'section divider'
    if LOOP_GROUP_RE.match(g):
        src = '24/7 Streams'
    else:
        src = GROUP_MAP.get(g)
    if src is None:
        src = 'United States' if g.startswith('US|') else 'United Kingdom' if g.startswith('UK|') else \
            'Canada' if g.startswith('CA|') else 'PPV Live Events'
    if src == DROP:
        return DROP, f'non-English ({raw_group})'
    if re.search(r'\bEQUIDIA\b|PRIMAFILA|\((?:ES|FR|PT|IT|DE|AR|NL|PL)\)|\bEN ESPA[NÑ]OL\b', t):
        return DROP, 'non-English (Equidia)'

    if src == '24/7 Streams':
        t = PREFIX_RE.sub('', t).strip()
        t = re.sub(r'^(?:24/7|24-7|247)\s*[:|\-]?\s*', '', t, flags=re.I)
        return src, t
    if src == 'XXX':
        t = PREFIX_RE.sub('', t).strip()
        t = re.sub(r'^(?:XXX|18\+?|ADULT)\s*[:|\-]\s*', '', t, flags=re.I)
        return src, t

    # ---- event slot formats
    m = EVENT8K_A.match(t) or EVENT8K_B.match(t)
    if m:
        svc = re.sub(r'\s+PPV$', '', m.group('svc').strip(), flags=re.I)
        ev = m.group('ev') or ''
        prev = None
        while prev != ev:
            prev = ev
            ev = STATUS_RE.sub('', ev).strip(' |-')
        ev = re.sub(r'\s*\|\s*all\s*\|', ' |', ev)
        t = f'{svc} {int(m.group("n"))}: {ev}' if ev else f'{svc} {int(m.group("n"))}:'
        return src, t

    if src not in ('24/7 Streams', 'XXX') and not src.startswith(('United', 'US ', 'UK ', 'Canada', 'Australia',
                                                                     'Sky New', 'Irish', 'Tubi', 'Discovery Plus',
                                                                     'P2 Intl', 'P2 4K', 'Betting')):
        # event/league groups: drop provider prefixes and normalise a few slot names
        t = PREFIX_RE.sub('', t)
        t = re.sub(r'^\(AU\)\s*', '', t)
        t = re.sub(r'^AU \((STAN \d+)\)', r'US (\1)', t)
        t = re.sub(r'^(?:CHAMP|L1|L2)\s*\|\s*', 'EFL: ', t)
        t = re.sub(r'^AHL-TEAM\|\s*', 'AHL: ', t)
        t = re.sub(r'^CA:\s*(?=[A-Z])', 'AHL: ', t) if src == 'P2 AHL' else t
        t = re.sub(r'^NA\|\s*', 'AHL: ' if src == 'P2 AHL' else '', t)
        t = re.sub(r'\s*\[[A-Z]{2,4}\]\s*$', '', t)
        t = re.sub(r'^SPFL\| ?SPFL REPLAY', 'SPFL REPLAY', t)
        t = re.sub(r'^SPFL \d+ ', 'SPFL: ', t)
        t = re.sub(r'^PL REPLAY', 'EPL REPLAY', t)
        t = re.sub(r'^EFL-(?:L[12]|CH) REPLAY', 'EFL REPLAY', t)
        t = re.sub(r'^LIGA\|\s*LALIGA REPLAY(?: ENGLISH)?', 'LALIGA REPLAY', t)
        t = re.sub(r'^SERIEA REPLAY', 'SERIE A REPLAY', t)
        t = re.sub(r'^KAYO\s*-\s*', '', t)
        t = re.sub(r'^US \(P\+\)\s*(.+?)\s+(\d{1,3})\s*$', r'P+ \2: \1', t)
        t = re.sub(r'\s*\((?:D|R|L|A|E)\)\s*$', '', t)
        t = re.sub(r'^(EUROPA LEAGUE|CHAMPIONS LEAGUE) REPLAY', r'UEFA \1 REPLAY', t)
        t = re.sub(r'^XTRA (\d+)', r'VIAPLAY XTRA \1', t)
        t = re.sub(r'^F1\|\s*', '', t)
        t = re.sub(r'^MG\|\s*', '', t)
        if re.search(r'MOVISTAR', t):
            return DROP, 'non-English (Movistar)'
        t = re.sub(r'^FORMULA 1\|\s*', '', t)
        t = re.sub(r'^NFL\s+\|\s*(\d+)\s*-\s*', r'NFL \1: ', t)
        t = re.sub(r'^(NHL|NBA)(?: LIVE)?\s*\|\s*(\d+)\s*-\s*', r'\1 \2: ', t)
        t = re.sub(r'^UEFA\s*\|\s*(\d+)\s*-\s*', r'UEFA \1: ', t)
        t = re.sub(r'^LIVE EVENT (\d+)\s*-\s*', r'LIVE EVENT \1: ', t)
        return src, t

    # ---- channel groups: turn provider prefixes into "CC: name"
    gcc = g.split('|')[0].strip() if '|' in g else ''
    cc = CC_OF_GROUP.get(gcc, 'US')
    if src == 'P2 Intl Sports':
        if re.search(r'NOW HK', t):
            return DROP, 'non-English (Hong Kong)'
        cc = 'INT'
    if src == 'P2 4K':
        if re.search(r'\b(FR|ES|RU|PL|IT|DE|PT|NM|AR)\b|PRIMAFILA|DECASA|COCINA|KINO|QUADRO|M\+|ELEVEN', t):
            return DROP, 'non-English (4K)'
        cc = 'CA' if re.search(r'\bCA\b', t) else 'UK' if re.search(r'SKY SPORTS', t) else 'US'
        t = re.sub(r'\bCA\b', ' ', t)
        src = {'CA': 'Canada', 'UK': 'United Kingdom', 'US': 'United States'}[cc]
    t = PREFIX_RE.sub('', t).strip()
    t = re.sub(r'^AU:\s*(?:9NOW\s+)?', '', t)
    t = re.sub(r'^9NOW\s+', '', t)
    t = re.sub(r'^KAYO\s*-\s*', '', t)
    t = re.sub(r'^MC-\s*', 'MUSIC CHOICE ', t)
    t = re.sub(r'\(N\d{3}\)\s*', '', t)             # NFL NETWORK (N570) MYRTLE BEACH
    lm = LOCAL_A.match(t)
    if lm:
        sub = f"-D{lm.group('sub')}" if lm.group('sub') else ''
        t = f"{lm.group('net')} {lm.group('num')} {lm.group('city').title()} {lm.group('st')} ({lm.group('call')}{sub})"
    else:
        lb = LOCAL_B.match(t)
        if lb:
            t = f"{lb.group('net')} {lb.group('city').title()} ({lb.group('call')})"
    # 'SIOUX FALLS SD (KSFY)' -> drop the state code so it isn't read as a quality tag
    t = re.sub(r'\s+(?:' + '|'.join(US_STATE_CODES) + r')\s+(?=\([KW][A-Z]{2,3}(?:-[A-Z0-9]+)?\))', ' ', t)
    if src == 'P2 Intl Music':
        src = 'UK Music'
        cc = 'INT'
    prefix = {'IRE': 'IRE', 'INT': 'INT'}.get(cc, cc)
    return src, f'{prefix}: {t}'


def adapt(entries):
    """Returns (entries_rewritten, dropped_reasons). Rewritten entries keep url/attrs; title/group replaced."""
    out = []
    drops = []
    for e in entries:
        src, t = adapt_entry(e)
        if src == DROP:
            drops.append(t)
            continue
        e2 = dict(e)
        e2['attrs'] = dict(e['attrs'])
        e2['attrs']['group-title'] = src
        e2['title'] = t
        e2['orig_title'] = e['title']
        e2['orig_group'] = e['attrs'].get('group-title', '')
        out.append(e2)
    return out, drops
