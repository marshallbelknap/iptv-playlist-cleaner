# -*- coding: utf-8 -*-
"""Turn one raw playlist entry into (group, clean name, metadata) or a drop reason."""
import re
from rules import (ENGLISH_CC, FOREIGN_CC, SPANISH_CALLS, PLUTO_REGIONS, SOURCE_TAGS, basic_clean, extract_quality,
                   strip_tail_tags, smart_case, is_non_english, JUNK_RE, NEWS_RE, SPORTS_RE, MOVIES_RE,
                   MOVIES_NOT, MUSIC_RE, MUSIC_NOT, CALL_RE, NOT_CALLSIGNS, US_STATES, MONTHS,
                   country_group, sports_group, PPV_GROUP, G247, ADULT_GROUP)

# ---------------------------------------------------------------------------
# Source-group routing
# ---------------------------------------------------------------------------
CHANNEL_SRC = {
    'United States': 'US', 'US Entertainment': 'US', 'US Locals & Regional': 'US', 'US NBC': 'US',
    'US FOX': 'US', 'US CBS': 'US', 'US ABC': 'US', 'US PBS': 'US', 'US Roku & Free TV': 'US',
    'Tubi TV (USA)': 'US', 'US Movies': 'US', 'US Music': 'US', 'US News': 'US', 'USA Premium': 'US',
    'US Documentaries': 'US', 'US Kids': 'US', 'US Sports': 'US',
    'Canada': 'CA', 'Canada News': 'CA', 'Canada Sports': 'CA',
    'United Kingdom': 'UK', 'UK Entertainment': 'UK', 'UK Sports': 'UK', 'UK Movies': 'UK',
    'UK Kids': 'UK', 'UK News': 'UK', 'UK Music': 'UK', 'Discovery Plus': 'UK',
    'Irish TV': 'IE', 'Australia': 'AU', 'Australia Sports': 'AU', 'Sky New Zealand': 'NZ',
    'DSTV': 'ZA', 'beIN Sports': 'BEIN', 'Betting TV': 'RACING', 'P2 Intl Sports': 'INT',
}
# Category forced by the source group when the name gives no better signal
SRC_CATEGORY = {
    'US Movies': 'Movies', 'UK Movies': 'Movies', 'US Music': 'Music', 'UK Music': 'Music',
    'US News': 'News', 'UK News': 'News', 'Canada News': 'News', 'US Sports': 'Sports',
    'UK Sports': 'Sports', 'Canada Sports': 'Sports', 'Australia Sports': 'Sports', 'DSTV': 'Sports',
    'Sky New Zealand': None, 'P2 Intl Sports': 'Sports',
}
LOCAL_SRC = {'US Locals & Regional', 'US NBC', 'US FOX', 'US CBS', 'US ABC', 'US PBS'}

LEAGUE_SRC = {
    'NFL': 'NFL', 'NBA': 'NBA', 'NHL': 'NHL', 'WNBA League Pass': 'WNBA', 'MLS': 'MLS',
    'EPL Premier League': 'EPL', 'EFL iFOLLOW': 'EFL', 'UEFA Championship': 'UEFA',
    'Formula One': 'F1', 'F1 Formula': 'F1', 'MOTOGP': 'MotoGP', 'KHL Hockey': 'KHL', 'OHL': 'OHL',
    'WHL': 'WHL', 'QMJHL': 'QMJHL', 'SPHL Hockey': 'SPHL', 'PDC DARTS': 'PDC', 'Golf': 'Golf',
    'NCAAF': 'NCAAF', 'NCAA Basketball': 'NCAAB', 'NCAA': 'NCAA', 'MLB Baseball league': 'MLB',
    'Optus': 'EPL', 'Football': 'Soccer', 'Others': 'GAA',
    'P2 MiLB': 'MiLB', 'P2 AHL': 'AHL', 'P2 SPFL': 'SPFL', 'P2 La Liga': 'La Liga', 'P2 Serie A': 'Serie A',
    'P2 Ligue 1': 'Ligue 1', 'P2 Tennis': 'Tennis', 'P2 Other': 'Other',
}
SERVICE_SRC = {
    'ESPN Plus': 'ESPN+', 'DAZN': 'DAZN', 'TSN Plus': 'TSN+', 'Paramount Plus': 'Paramount+',
    '(US) HBO MAX': 'MAX', 'Peacock TV': 'Peacock', 'Flo Sports': 'FloSports', 'FloCollege': 'FloSports',
    'Fite TV': 'Triller TV', 'Clubber': 'Clubber TV', 'DIRTVision': 'DIRTVision',
    'P2 Sportsnet+': 'Sportsnet+',
}
DROP_SRC = {
    'Setanta Sports': 'non-English (Setanta Eurasia, Russian commentary)',
    'Arabic': 'non-English (Arabic)', 'Indonesia': 'non-English (Indonesia, Vidio)',
    'Thailand': 'non-English (Thailand, MonoMax)', 'Israel': 'non-English (Israel)',
    'NOW HK SPORTS': 'non-English (Hong Kong, Cantonese)',
    'Bundesliga': 'non-English (German Eurosport Xtra)',
}

# league/service label -> output group label (under "Sports | ...")
LEAGUE_GROUP = {
    'NFL': 'NFL', 'NBA': 'NBA', 'NBA G League': 'NBA', 'WNBA': 'WNBA', 'MLB': 'MLB', 'MiLB': 'MiLB',
    'NHL': 'NHL', 'NCAAF': 'NCAAF', 'NCAAB': 'NCAAB', 'NCAA': 'NCAA (Other)', 'MLS': 'MLS', 'EPL': 'EPL',
    'EFL': 'EFL', 'UEFA': 'UEFA', 'La Liga': 'La Liga', 'Serie A': 'Serie A', 'Ligue 1': 'Ligue 1',
    'Bundesliga': 'Soccer (Other)', 'SPFL': 'SPFL', 'Soccer': 'Soccer (Other)',
    'CONMEBOL': 'Soccer (Other)', 'F1': 'F1', 'MotoGP': 'MotoGP', 'OHL': 'CHL', 'WHL': 'CHL',
    'QMJHL': 'CHL', 'PWHL': 'Hockey (Other)', 'KHL': 'Hockey (Other)', 'SPHL': 'Hockey (Other)',
    'ECHL': 'Hockey (Other)', 'OJHL': 'Hockey (Other)', 'PDC': 'Darts', 'Golf': 'Golf', 'GAA': 'GAA',
    'Tennis': 'Tennis', 'OUA': 'Other', 'CEBL': 'Other', 'Super League': 'Other', 'AHL': 'Hockey (Other)',
    'Other': 'Other', 'Rugby': 'Other', 'NRL': 'Other', 'AFL': 'Other',
    'ESPN+': 'ESPN+', 'DAZN': 'DAZN', 'TSN+': 'TSN+', 'Sportsnet+': 'Sportsnet+',
    'Paramount+': 'Paramount+', 'MAX': 'MAX', 'Peacock': 'Peacock', 'FloSports': 'FloSports',
    'Prime Video': 'Prime Video',
}
# event families that are folded into PPV & Events instead of their own group
EVENTS_TO_PPV = {'Triller TV', 'Clubber TV', 'DIRTVision', 'CBC Sports', 'BBC Sport', 'TNT Sports',
                 'BIG10+', 'Fox Sports', 'Rally TV', 'Tennis TV', 'UFC', 'PPV', 'Live Events',
                 'Red Bull TV', 'Fubo Sports', 'Hub Sports'}

# Resolve a label from the start of an event/slot name.  Order matters.
LABEL_RULES = [
    (r'^(?:US\s*\()?ESPN ?(?:\+|PLUS)', 'ESPN+'),
    (r'^DAZN|^Event DAZN', 'DAZN'),
    (r'^(?:CA\s*\()?TSN ?\+|^:?TSN\+', 'TSN+'),
    (r'^(?:SN ?\+|:?Sportsnet ?\+)', 'Sportsnet+'),
    (r'^(?:US\s*\()?Paramount|^P\+(?:\s*\d|$)', 'Paramount+'),
    (r'^(?:US\s*\()?MAX\b|^:?MAX US|^HBO(?:\s*\d|$)', 'MAX'),
    (r'^Peacock', 'Peacock'),
    (r'^(?:\(?FLSP|Flo|FLOF|flosports)', 'FloSports'),
    (r'^Amazon UK|^Prime Video', 'Prime Video'),
    (r'^(?:Triller|Fite)', 'Triller TV'),
    (r'^Clubber', 'Clubber TV'),
    (r'^DIRT ?VISION', 'DIRTVision'),
    (r'^CBC(?:\s*\d|$)', 'CBC Sports'),
    (r'^BBC (?:Stream|Red Button)', 'BBC Sport'),
    (r'^TNT Sports? ?\|', 'TNT Sports'),
    (r'^BIG ?10\+', 'BIG10+'),
    (r'^FS(?:\s*\d|$)', 'Fox Sports'),
    (r'^Rally ?TV|^WRC', 'Rally TV'),
    (r'^Tennis TV', 'Tennis TV'),
    (r'^(?:US\s*\()?UFC', 'UFC'),
    (r'^Red ?Bull', 'Red Bull TV'),
    (r'^(?:CA \| )?Fubo', 'Fubo Sports'),
    (r'^Hub ', 'Hub Sports'),
    (r'^NFL', 'NFL'),
    (r'^NBA ?G\b|^NBAG', 'NBA G League'),
    (r'^\(?NBA', 'NBA'),
    (r'^\(?WNBA|^US \(WNBA', 'WNBA'),
    (r'^(?:US \()?:?MILB', 'MiLB'),
    (r'^\(?MLB|^US \(MLB', 'MLB'),
    (r'^Hub ', 'Hub Sports'),
    (r'^NHL', 'NHL'),
    (r'^NCAAF|^NCAA Football|^College Football', 'NCAAF'),
    (r'^:?NCAAB|^NCAAM|^NCAA Basketball', 'NCAAB'),
    (r'^\(Apple\) \(MLS\)|^MLS', 'MLS'),
    (r'^\(Apple\) \(F1\)|^\(?F1|^Formula ?(?:1|One)|^FORMULAONE', 'F1'),
    (r'^Super League', 'Super League'),
    (r'^EPL|^Premier League|^Optus', 'EPL'),
    (r'^EFL|^Carabao|^English Football League', 'EFL'),
    (r'^UEFA|^EUROPA|^Champions League', 'UEFA'),
    (r'^LA ?LIGA', 'La Liga'),
    (r'^Serie A', 'Serie A'),
    (r'^Ligue ?1?\b|^LIGUEONE', 'Ligue 1'),
    (r'^Bundesliga', 'Bundesliga'),
    (r'^SPFL|^Scottish', 'SPFL'),
    (r'^LIBERTADORES|^Copa', 'CONMEBOL'),
    (r'^Moto ?GP|^TT RACES', 'MotoGP'),
    (r'^OHL', 'OHL'), (r'^PWHL', 'PWHL'), (r'^WHL', 'WHL'), (r'^QMJHL', 'QMJHL'), (r'^KHL', 'KHL'),
    (r'^SPHL', 'SPHL'), (r'^ECHL', 'ECHL'), (r'^OJHL', 'OJHL'),
    (r'^PDC', 'PDC'),
    (r'^:?Golf|^PGA', 'Golf'),
    (r'^(?:ULSTER |Tyrone )?Gaa|^ARMAGH TV', 'GAA'),
    (r'^WTA|^ATP|^Tennis', 'Tennis'),
    (r'^OUA', 'OUA'), (r'^CEBL', 'CEBL'), (r'^AHL', 'AHL'), (r'^TC\+', 'Tennis'),
    (r'^NRL', 'NRL'), (r'^AFL', 'AFL'), (r'^Rugby', 'Rugby'), (r'^(?:US \()?(?:B1G|BTN)\+', 'BIG10+'),
    (r'^PPV|^LIVE EVENT|^PPV EVENT', 'PPV'),
    (r'^(?:Live )?Football|^Match(?:\s*\d|$)', 'Soccer'),
]
LABEL_RULES = [(re.compile(p, re.I), l) for p, l in LABEL_RULES]

# Slot prefixes we strip before reading the slot number
NO_EVENT_RE = re.compile(
    r'^(?:\d+\.\s*)?(?:no (?:live )?(?:event|events|game|games|match|matches)(?: scheduled| today)?|'
    r'no scheduled event|no live court|offline|zzz offline|no event today|event \d+|tbd|tba|'
    r'nothing (?:here|on) today|no stream|stream offline|upcoming|coming soon|n/?a|-+)$', re.I)


def fix_mojibake(t):
    if re.search(r'[ÃÅÄÂ][\x80-\xbf\u0152-\u2122]', t):
        for enc in ('cp1252', 'latin-1'):
            try:
                return t.encode(enc).decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return t


def resolve_label(t):
    for rx, lab in LABEL_RULES:
        if rx.search(t):
            return lab
    return None


# ---------------------------------------------------------------------------
# Event text normalisation
# ---------------------------------------------------------------------------
def _ampm(h, m, ap):
    h = int(h)
    if ap:
        ap = ap.upper()
        if h > 12:      # e.g. "13:30 PM"
            ap = 'PM'
            h -= 12
    else:
        ap = 'AM' if h < 12 else 'PM'
        h = h % 12 or 12
    return f'{h}:{m} {ap}'


def norm_dates(e):
    tz = r'(?:\s*(ET|EST|EDT|PT|CT|MT|UK|GMT|BST|UTC))?'
    # (10.11 6:00AM ET)  or  | 10.10 12:00PM |
    def d1(m):
        mo, d, h, mi, ap, z = m.groups()
        if not 1 <= int(mo) <= 12:
            return m.group(0)
        return f' ({MONTHS[int(mo)-1]} {int(d)} {_ampm(h, mi, ap)}{" " + z.upper() if z else ""}) '
    e = re.sub(r'[\(|]?\s*\b(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])' + tz + r'\s*[\)|]?', d1, e)
    # (2026 10 12 15:00:20)
    def d2(m):
        y, mo, d, h, mi = m.groups()
        if y in ('2098', '2099') or not 1 <= int(mo) <= 12:
            return ' '
        return f' ({MONTHS[int(mo)-1]} {int(d)} {_ampm(h, mi, None)}) '
    e = re.sub(r'\((20\d\d)[ -](\d\d)[ -](\d\d)[ T](\d\d):(\d\d)(?::\d\d)?\)', d2, e)
    e = re.sub(r'(?<![\d:])(20\d\d)-(\d\d)-(\d\d)[ T](\d\d):(\d\d)(?::\d\d)?(?![\d]|\s*[AaPp][Mm])', d2, e)
    # 2026-10-03 - 23:00 (GMT)
    def d4(m):
        y, mo, d, h, mi, z = m.groups()
        if y in ('2098', '2099') or not 1 <= int(mo) <= 12:
            return ' '
        return f' ({MONTHS[int(mo)-1]} {int(d)} {_ampm(h, mi, None)}{" " + z if z else ""}) '
    e = re.sub(r'(?<![\d:])(20\d\d)-(\d\d)-(\d\d)\s*[-|]\s*(\d\d):(\d\d)(?:\s*\((GMT|UTC|ET|BST)\))?', d4, e)
    # @ Oct 10 7:20 AM   /   Oct 10 2:30 PM
    def d3(m):
        mon, d, h, mi, ap = m.groups()
        return f' ({mon[:3].title()} {int(d)} {_ampm(h, mi, ap)}) '
    def d3b(m):
        mon, d, h, mi, ap, z = m.groups()
        return f' ({mon[:3].title()} {int(d)} {_ampm(h, mi, ap)}{" " + z.upper() if z else ""}) '
    e = re.sub(r'(?<!\()@?\s*\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?,? '
               r'(\d{1,2}):(\d{2})\s*([AaPp][Mm])?' + tz, d3b, e)
    return e


def dedupe_parens(e):
    """'Matt & Myron (Matt & Myron)' -> 'Matt & Myron'."""
    def repl(m):
        inner = m.group(1).strip().lower()
        before = e[:m.start()].lower()
        if inner and len(inner) > 3 and inner in before:
            return ''
        return m.group(0)
    return re.sub(r'\s*\(([^()]{4,})\)', repl, e)


def clean_event(e, label=None):
    e = basic_clean(fix_mojibake(e))
    e = re.sub(r'^\s*•\s*|\s*•\s*$', '', e).replace('_', ' ')
    e = re.sub(r'\((?:2098|2099)[^)]*\)', ' ', e)
    e = e.replace(' // ', ' | ')
    e = dedupe_parens(e)
    if label:
        e = re.sub(r'^(?:' + re.escape(label) + r'|English Football League|LaLiga|La Liga|Serie A|MLS on TSN)\s*:\s*', '', e, flags=re.I)
    e = norm_dates(e)
    e = re.sub(r'\s*\|\s*', ' | ', e)
    parts = [p.strip(' :-') for p in e.split(' | ')]
    parts = [p for p in parts if p and not NO_EVENT_RE.match(p)]
    # move "(date)" pieces to the end
    dates = []
    out = []
    for p in parts:
        found = re.findall(r'\((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [^)]*\)', p)
        dates += found
        for f in found:
            p = p.replace(f, ' ')
        p = re.sub(r'\s+', ' ', p).strip(' :-')
        if p and not NO_EVENT_RE.match(p):
            out.append(p)
    e = ' - '.join(out)
    e = re.sub(r'\s+ET\b(?=\s*$)', '', e) if dates else e
    e = re.sub(r'\s+', ' ', e).strip(' :-|')
    if NO_EVENT_RE.match(e):
        e = ''
    e = smart_case(e, aggressive=False)
    if dates:
        e = (e + ' ' + dates[0]).strip()
    return e


SLOT_PATTERNS = [
    # US (ESPN+ 279) | text      CA (TSN+ 044) | text     US (UFC INT 02) | text
    re.compile(r'^(?:US|CA|UK)\s*\((?P<p>[^)]*?)\s*(?P<n>\d{1,3})\)\s*\|?\s*(?P<e>.*)$'),
    # (Apple) (MLS) 001 | text
    re.compile(r'^\(Apple\)\s*\((?P<p>[^)]+)\)\s*(?P<n>\d{1,3})\s*\|\s*(?P<e>.*)$'),
    # (UK) Dazn 36: text
    re.compile(r'^\((?:UK|US|CA)\)\s*(?P<p>[A-Za-z+ ]+?)\s+(?P<n>\d{1,3})\s*[:|]\s*(?P<e>.*)$'),
    # (FLSP 366) | text    (F1TV 18) | text   (NBA 06)
    re.compile(r'^\((?P<p>[^)]*?)\s*(?P<n>\d{1,3})\)\s*\|?\s*(?P<e>.*)$'),
    # text @ Oct 10 ... :TSN+  40      :MAX US 38
    re.compile(r'^(?P<e>.*?)\s*:\s*(?P<p>TSN\+|Paramount\+|MAX US|Flo College|Flo Racing|MLS|Golf|NCAAB|Sportsnet\+|Milb|Tennis)'
               r'\s+(?P<n>\d{1,3})\s*$', re.I),
    # UEFA | 06   Crystal Palace vs ...      NFL  | 05   1pm Bengals at Dolphins
    re.compile(r'^(?P<p>[A-Za-z][A-Za-z+ .]*?)\s*\|\s*(?P<n>\d{1,3})\b\s*(?P<e>.*)$'),
    # NFL 02: text   ESPNPLUS 202 | text   PPV04 |   EFL10| text   DIRTVISION 05   Golf 18 :   DAZN UK | Event 1
    re.compile(r'^(?P<p>[A-Za-z][A-Za-z0-9+&. |]*?)\s*(?P<n>\d{1,3})\s*(?:[:|\-]\s*(?P<e>.*))?$'),
    # DAZN UK | Event 1 text / Paramount | Event 9
    re.compile(r'^(?P<p>.+?)\s*\|?\s*Event\s*(?P<n>\d{1,3})\s*(?:[:|]\s*(?P<e>.*))?$', re.I),
    # Event DAZN CA 1 HD
    re.compile(r'^Event\s+(?P<p>.+?)\s+(?P<n>\d{1,3})\b\s*(?P<e>.*)$', re.I),
]
PREFIX_NORMALISE = [(re.compile(r'^Ligue ?1\b'), 'LIGUEONE'), (re.compile(r'^Formula ?1\b'), 'FORMULAONE'),
                    (re.compile(r'^Big ?10\+', re.I), 'BIG10+'), (re.compile(r'^(?:USA?|CA|UK)\s*\|\s*'), '')]


def parse_slot(t):
    """Return (prefix, slot_number or None, event_text)."""
    for rx, rep in PREFIX_NORMALISE:
        t = rx.sub(rep, t)
    for rx in SLOT_PATTERNS:
        m = rx.match(t)
        if m:
            e = (m.group('e') or '').replace('FORMULAONE', 'Formula 1').replace('LIGUEONE', 'Ligue 1')
            p = re.sub(r'[\s|:]+$', '', m.group('p').strip())
            p = re.sub(r'\s*\|?\s*Event$', '', p, flags=re.I).strip()
            return p, int(m.group('n')), e
    t = t.replace('FORMULAONE', 'Formula 1').replace('LIGUEONE', 'Ligue 1')
    return None, None, t


DISPLAY_ALIAS = {
    'floh': 'FloHockey', 'flohockey': 'FloHockey', 'flow': 'FloWrestling', 'flor': 'FloRacing',
    'floracing': 'FloRacing', 'flofc': 'FloFC', 'flobb': 'FloHoops', 'flobase': 'FloBaseball',
    'flosb': 'FloSoftball', 'flof': 'FloFootball', 'florugby': 'FloRugby', 'flosports.tv': 'FloSports',
    'flocollege': 'FloCollege', 'flsp': 'FloSports', 'flo': 'FloSports', 'pga': 'PGA Tour',
    'ohltv': 'OHL TV', 'whltv': 'WHL TV', 'qmjhltv': 'QMJHL TV', 'ohltvfixtures': 'OHL TV',
    'gaago': 'GAAGO', 'gaagofixtures': 'GAAGO', 'gaatv': 'GAA TV', 'ulstergaa': 'Ulster GAA',
    'tyronegaa': 'Tyrone GAA', 'armaghtv': 'Armagh GAA TV', 'premierleague+': 'Premier League+', 'superleagueplus': 'Super League+',
    'superleague': 'Super League+', 'scottishcup': 'Scottish Cup', 'scottishpremiership': 'SPFL',
    'libertadores': 'Libertadores', 'nbag': 'NBA G League', 'pdcboard': 'PDC', 'f1tv': 'F1 TV',
    'uefael': 'UEFA Europa League', 'europaleague': 'UEFA Europa League', 'liveevent': 'Event', 'live': 'Event',
    'ppvevent': 'PPV', 'footballevent': 'Soccer', 'livefootball': 'Soccer', 'match': 'Soccer',
    'ttraces': 'TT Races', 'bbcstream': 'BBC Sport', 'bbcredbutton': 'BBC Red Button',
    'amazonuk': 'Prime Video', 'sn+': 'Sportsnet+', 'rallytv': 'Rally TV', 'tennistv': 'Tennis TV',
    'big10+': 'B1G+', 'fs': 'Fox Sports', 'p+': 'Paramount+', 'hbo': 'MAX', 'maxus': 'MAX', 'milb': 'MiLB',
    'ncaam': 'NCAAB', 'clubbertv': 'Clubber TV', 'clubber': 'Clubber TV', 'trillertv': 'Triller TV',
    'triller': 'Triller TV', 'ufcint': 'UFC Intl', 'motogp': 'MotoGP', 'nhlgame': 'NHL',
    'soccer': 'Soccer PPV', 'nfhs': 'NFHS', 'fifa+': 'FIFA+', 'nbapass': 'NBA', 'viaplay': 'Viaplay',
    'appletvf1': 'F1 Apple TV', 'rally': 'Rally TV', 'mxgp': 'MXGP', 'volley': 'Volleyball World',
    'ultimatepool': 'Ultimate Pool', 'netflix': 'Netflix', 'max': 'MAX', 'sportsnet': 'Sportsnet+',
    'rogerssupersportspack': 'Sportsnet+', 'viaplayxtra': 'Viaplay Xtra', 'skysportsredbutton': 'Sky Sports Red Button',
    'skysport+': 'Sky Sports+', 'eurosportxtra': 'Eurosport Xtra', 'espnplayevents': 'ESPN Play',
    'espnplay': 'ESPN Play', 'b/rmaxsportsevents': 'B/R Sports', 'payperview': 'PPV', 'matchroomevent': 'Matchroom',
    'matchroomevents': 'Matchroom', 'rugby': 'Rugby', 'nrltv': 'NRL', 'afltv': 'AFL', 'nationalleague': 'National League',
    'faplayer': 'FA Player', 'cymrufootball': 'Cymru Football', 'psf': 'Pre-Season Friendlies', 'loitv': 'LOI',
    'nifl': 'NIFL', 'supercross': 'Supercross', 'tc+': 'Tennis Channel+', 'victory+': 'Victory+', 'stan': 'Stan',
    'stanevent': 'Stan', 'btn+': 'B1G+', 'b1g+': 'B1G+', 'fitetv': 'Triller TV', 'hubpremier': 'Hub Premier',
    'bbcevents': 'BBC Sport', 'tnts': 'TNT Sports', 'tntsports': 'TNT Sports', 'ahl': 'AHL', 'florugby': 'FloRugby',
    'ufc': 'UFC', 'boxing': 'Boxing', 'premiereleague': 'EPL', 'epl|premiereleague': 'EPL', 'wnba': 'WNBA',
    'nbareplay': 'NBA Replay', 'nhlreplay': 'NHL Replay', 'eplreplay': 'EPL Replay', 'eflreplay': 'EFL Replay',
    'spflreplay': 'SPFL Replay', 'nationalleaguereplay': 'National League Replay',
    'uefaeuropaleaguereplay': 'UEFA Europa League Replay', 'uefachampionsleaguereplay': 'UEFA Champions League Replay',
    'worldcup2026replay': 'World Cup 2026 Replay', 'motogp': 'MotoGP', 'f1tv': 'F1 TV', 'formula1event': 'F1',
    'wnbaleaguepass': 'WNBA', 'ligue1': 'Ligue 1', 'ligueone': 'Ligue 1', 'formulaone': 'F1', 'laliga': 'LaLiga', 'goldenleague': 'Golf',
}


def display_label(label, p, t):
    if label == 'DAZN':
        m = re.search(r'\b(UK|CA|US)\b', t)
        return f'DAZN {m.group(1)}' if m else 'DAZN'
    key = re.sub(r'\s+', '', (p or '').lower())
    key = re.sub(r'(hd|fhd|sd)$', '', key)
    if key in DISPLAY_ALIAS:
        return DISPLAY_ALIAS[key]
    if key.endswith('replay'):
        return {'La Liga': 'LaLiga'}.get(label, label) + ' Replay'
    if label in ('Live Events', 'Other') and p and len(p) <= 30 and not re.search(r'\d', p):
        pretty = smart_case(re.sub(r'\s*\|\s*$', '', p.strip()))
        if pretty and pretty.lower() not in ('event', 'live event', 'ppv event', 'match', 'live football'):
            return pretty
    return {'La Liga': 'LaLiga', 'CONMEBOL': 'Libertadores', 'Live Events': 'Event'}.get(label, label)


def strip_slot_quality(t):
    """'ESPN Play Events 7 HD' -> ('ESPN Play Events 7', 'HD')."""
    m = re.search(r'(?<=\d)\s+(4K|UHD|FHD|HD|SD)\s*$', t)
    if not m:
        return t, None
    return t[:m.start()], {'UHD': '4K'}.get(m.group(1), m.group(1))


def slot_name(label, t, disp=None):
    disp = disp or label
    t, q0 = strip_slot_quality(t)
    p, n, e = parse_slot(t)
    if n is None:
        # team channels / feeds without a slot number -> "LABEL: text"
        e = t
        m = re.match(r'^\((?:Apple )?(F1(?: TV)? CAM|F1 TV)\)\s*(.*)$', e, re.I)
        if m:
            sub = 'Apple Cam' if e.lower().startswith('(apple') else 'F1 TV Cam'
            e = f'{sub}: {m.group(2)}'
        e = re.sub(r'^(?:NBALP|NFL Teams|NBA LP)\s*:\s*', '', e, flags=re.I)
        e = re.sub(r'^(?:US|USA|CA|UK)\s*[:|]?\s*\(?' + re.escape(label) + r'\)?\s*[:|]?\s*', '', e, flags=re.I)
        e = re.sub(r'^\(?' + re.escape(label) + r'\)?\s*(?:Teams?)?\s*[:|]?\s*', '', e, flags=re.I)
        e = re.sub(r'^(?:Scottish (?:Prem|Premiership|champ|Championship))\s*:\s*', '', e, flags=re.I)
        e = re.sub(r'^(?:US|USA)\s+(?=[A-Z])', '', e)
        e = re.sub(r'^\([A-Z]{2,4}\)\s*', '', e)            # (IND) Indiana Pacers
        e, q = extract_quality(strip_tail_tags(e))
        e = clean_event(e, label)
        name = f'{disp}: {e}' if e else disp
        return name, q or q0
    pq, q1 = extract_quality(p)
    e, q = extract_quality(e)
    ev = clean_event(e, label)
    if ev[:1].islower():
        ev = ev[:1].upper() + ev[1:]
    num = f'{n:02d}' if n < 100 else str(n)
    name = f'{disp} {num}'
    return (f'{name}: {ev}' if ev else name), (q or q1 or q0)


# ---------------------------------------------------------------------------
# Country-channel name parsing
# ---------------------------------------------------------------------------
WORD_PREFIX_RE = re.compile(
    r'^(?:NEW\s+)?(?:HEVC\s*(?:FHD|HD)?\s*:?\s*)?'
    r'(?P<cc>USA REG|USA|US|UK|CA|AUS|AU|NZ|IRE|ZA|SS|REG|INT)?'
    r'(?P<q>SD|HD|FHD|UHD)?'
    r'(?:\s*\+1)?'
    r'(?:\s+(?P<q2>SD|HD|FHD|UHD|FR|MOVIE|REG))?'
    r'\s*(?P<sep>[:|])?\s*')


def parse_country_name(t, default_cc):
    """Return dict(cc, name, tags, city_hint, foreign)."""
    info = {'cc': default_cc, 'tags': [], 'city': None, 'foreign': False, 'pluto': False}
    m = re.match(r'^\(PLUTO ([^)]+)\)\s*', t)
    if m:
        region = m.group(1).strip()
        info['pluto'] = True
        if region in PLUTO_REGIONS:
            info['cc'] = PLUTO_REGIONS[region]
        else:
            info['foreign'] = f'Pluto TV {region}'
        t = t[m.end():]
    m = re.match(r'^((?:\([^)]{1,40}\)\s*)+)', t)
    if m and not info['pluto']:
        toks = re.findall(r'\(([^)]*)\)', m.group(1))
        rest = t[m.end():]
        for i, tok in enumerate(toks):
            tk = tok.strip()
            up = tk.upper()
            if i == 0 and up in ENGLISH_CC:
                info['cc'] = ENGLISH_CC[up]
            elif up in FOREIGN_CC or tk in ('Latin', 'Asian', 'Arabic', 'Polish', 'Taiwanese', 'Carib'):
                info['foreign'] = tk
            elif tk in SOURCE_TAGS or up in SOURCE_TAGS or re.fullmatch(r'[A-Z0-9]{1,4}', tk):
                info['tags'].append(tk)
            elif tk in ('7Plus', '9Now', 'SBS', 'ABC', 'KAYO', 'Prime', 'TUBI', 'RK', 'GT', 'Rakuten'):
                info['tags'].append(tk)
            elif re.fullmatch(r"[A-Z][A-Za-z .'/-]+", tk) and len(tk) > 3:
                info['city'] = tk            # (Baton Rouge)
            else:
                info['tags'].append(tk)
        t = rest
    else:
        m = WORD_PREFIX_RE.match(t)
        if m and (m.group('cc') or m.group('q')) and m.end() < len(t):
            cc = m.group('cc')
            rest = t[m.end():]
            # do not eat "USA" in "USA Network" / "USA Today"
            if cc in ('USA', 'US') and not m.group('sep') and re.match(r'(Network|Today)\b', rest, re.I):
                rest = None
            if rest is not None:
                if cc and cc not in ('REG', 'SS', 'USA REG'):
                    info['cc'] = ENGLISH_CC.get(cc, info['cc'])
                if cc == 'SS':
                    info['cc'] = 'ZA'
                if m.group('q2') == 'FR':
                    info['foreign'] = 'French'
                q = m.group('q') or (m.group('q2') if m.group('q2') in ('SD', 'HD', 'FHD', 'UHD') else None)
                if q:
                    info['tags'].append('Q:' + q)
                t = rest
        # "CA (FR) xxx", "US (Arabic) xxx", "US (KPDX) xxx"
        m2 = re.match(r'^\(([^)]{1,20})\)\s*', t)
        if m2:
            tk = m2.group(1)
            if tk.upper() in FOREIGN_CC or tk in ('Latin', 'Asian', 'Arabic', 'Polish', 'Taiwanese', 'Carib'):
                info['foreign'] = tk
            elif tk in SOURCE_TAGS or re.fullmatch(r'[A-Z0-9]{1,4}', tk) or tk in ('Faith',):
                t = t[m2.end():]
        # "IN (TO) ...", "AR ...", foreign word prefixes in US Entertainment
        m3 = re.match(r'^([A-Z]{2})\s+\((TO|S|A|H|D|E|FL|HX)\)\s*', t)
        if m3 and m3.group(1) in FOREIGN_CC:
            info['foreign'] = m3.group(1)
    info['name'] = t.strip()
    return info


def classify_category(name, src):
    n = name
    if SPORTS_RE.search(n) and not re.search(r'\b(news ?12|cnn|fox news)\b', n, re.I):
        # "ESPNews", "Sky Sports News" stay sports; "Fox Sports Racing" too
        if not re.search(r'\b(motor ?trend|outdoor channel|pursuit|sportsman|wfn|world fishing|'
                         r'poker|chess|trackside)\b', n, re.I) or src in SRC_CATEGORY and SRC_CATEGORY[src] == 'Sports':
            return 'Sports'
    if NEWS_RE.search(n):
        return 'News'
    if MOVIES_RE.search(n) and not MOVIES_NOT.search(n):
        return 'Movies'
    if MUSIC_RE.search(n) and not MUSIC_NOT.search(n):
        return 'Music'
    forced = SRC_CATEGORY.get(src)
    if forced and not GENERAL_HINT.search(n):
        return forced
    return 'General'


GENERAL_HINT = re.compile(r"\b(adult swim|cartoon|disney|nick|kids|comedy|food|hgtv|tlc|history|discovery|"
                          r"bravo|lifetime|hallmark (?!movies)|bet her|e!|a&e|amc|syfy|usa network|tbs|tnt(?! sports)|"
                          r"\bfx\b|freeform|paramount network|oxygen|we tv|own|ion|cozi|metv|game show|gsn|"
                          r"travel|animal planet|nat ?geo|science|investigation|crime|court|reelz|ovation|"
                          r"magnolia|cooking|tastemade|shop|qvc|hsn|jewelry|religious|faith|church|gospel|"
                          r"tbn|daystar|ewtn|inspiration|insp)\b", re.I)


# ---------------------------------------------------------------------------
# US local stations
# ---------------------------------------------------------------------------
NET_RE = re.compile(r'\b(ABC|CBS|NBC|FOX|CW|PBS|MNT|MyNetworkTV|MyNet|MyTV|MY|IND|Telemundo|Univision|ION|'
                    r'ME ?TV|Independent)(?=\d|\b)', re.I)
NET_CANON = {'MYNETWORKTV': 'MyNetworkTV', 'MYTV': 'MyNetworkTV', 'MY': 'MyNetworkTV', 'MYNET': 'MyNetworkTV',
             'MNT': 'MyNetworkTV', 'IND': 'Independent', 'INDEPENDENT': 'Independent',
             'METV': 'MeTV', 'ME TV': 'MeTV'}


def find_callsign(name):
    for m in CALL_RE.finditer(name):
        cs = m.group(1)
        if cs in NOT_CALLSIGNS:
            continue
        return m
    return None


def parse_local(name, loose=False):
    """Try to read a US local station out of a name. Returns dict or None."""
    nm = re.sub(r'\s+', ' ', name).strip()
    cm = find_callsign(nm)
    netm = NET_RE.search(nm)
    if not cm:
        m = re.match(r'^(ABC|CBS|NBC|FOX|CW|PBS)\s*:\s*(.+)$', nm)
        if m:
            rest = re.sub(r'\b(' + m.group(1) + r')\s*(\d{1,2})\b', ' ', m.group(2), flags=re.I)
            num = re.search(r'\b' + m.group(1) + r'\s*(\d{1,2})\b', m.group(2), re.I)
            words = [w for w in rest.split() if not (w.isupper() and w in US_STATES)]
            return {'net': m.group(1), 'num': num.group(1) if num else None, 'call': None, 'sub': None,
                    'city': smart_case(' '.join(words).upper())}
        return None
    if not netm:
        # independent stations: only when the call sign is clearly marked
        if not loose and not re.search(r'\(' + cm.group(1) + r'(?:[- ]?(?:TV|DT\d?|LD|CD|D\d))?\)|^\[', nm):
            return None
        rest = nm.replace(cm.group(0), ' ')
        rest = re.sub(r'[()\[\]|:,]', ' ', rest)
        rest = re.sub(r'\b(US|USA|REG|HD|FHD|SD|DT\d?|D\d|LD)\b', ' ', rest)
        rest = ' '.join(rest.split())
        if rest.isupper():
            rest = smart_case(rest)
        return {'net': None, 'num': None, 'call': cm.group(1), 'sub': None, 'city': rest}
    call = cm.group(1)
    sub = re.search(r'\b' + call + r'[- ]?(?:DT|D|LD)(\d)\b', nm)
    sub = sub.group(1) if sub and sub.group(1) not in ('1',) else None
    after = re.search(r'\b' + call + r'\s+(\d{1,2})\b', nm)
    net = netm.group(1)
    net = NET_CANON.get(net.upper(), net.upper() if len(net) <= 4 else net.title())
    # channel number right after the network word: "FOX 5", "abc 25", "My 69"
    num = None
    nm2 = re.search(re.escape(netm.group(1)) + r'[:\s]*(\d{1,2})\b(?!\s*(?:Network|News))', nm, re.I)
    if nm2:
        num = nm2.group(1)
    elif after and not sub:
        num = after.group(1)
    city = nm
    if after and not sub:
        city = city.replace(after.group(0), call, 1)
    for rm in [cm.group(0)] + ([nm2.group(0)] if nm2 else []) + [netm.group(0)]:
        city = city.replace(rm, ' ', 1)
    city = re.sub(r'\b(?:D\d|DT\d?|LD|TV|HD|FHD|SD)\b', ' ', city)
    city = re.sub(r'\b(?:Telemundo|Local|News)\b', ' ', city, flags=re.I)
    city = re.sub(r'[()|:,]', ' ', city)
    city = re.sub(r'\b(US|USA|REG)\b', ' ', city)
    words = [w for w in city.split() if w]
    # drop leading state code ("FOX IA SIOUX CITY")
    if words and words[0].upper() in US_STATES and len(words) > 1 and words[0].isupper():
        words = words[1:]
    # drop trailing state code ("ST LOUIS MO")
    if len(words) > 1 and words[-1].upper() in US_STATES and words[-1].isupper():
        words = words[:-1]
    city = ' '.join(words).strip(' -/')
    if city.isupper() or city.islower():
        city = smart_case(city.upper()) if len(city) > 3 else city
    return {'net': net, 'num': num, 'call': call, 'sub': sub, 'city': city}


def local_display(loc, city_override=None):
    net = loc['net']
    if not net:
        return f"{city_override or loc['city'] or loc['call']} ({loc['call']})"
    if not loc['call']:
        return ' '.join(x for x in [net, loc['num'], loc['city']] if x)
    parts = [net]
    if loc['num']:
        parts.append(loc['num'])
    city = city_override or loc['city']
    if city:
        parts.append(city)
    call = loc['call'] + (f"-DT{loc['sub']}" if loc['sub'] else '')
    return ' '.join(parts) + f' ({call})'
