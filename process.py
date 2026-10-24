# -*- coding: utf-8 -*-
"""Apply the rules to every entry. Two passes so local stations can share city names."""
import os
import re
import collections
from origin import home_country, iptv_category
from loops import loop_type, country_label, GROUPS as LOOP_GROUPS
from rules import (SPANISH_CALLS, NOT_CALLSIGNS, US_STATES, basic_clean, extract_quality, strip_tail_tags, smart_case, is_non_english, JUNK_RE,
                   country_group, sports_group, PPV_GROUP, G247, ADULT_GROUP, COUNTRY_ORDER)
from classify import (strip_slot_quality, CHANNEL_SRC, SRC_CATEGORY, LOCAL_SRC, LEAGUE_SRC, SERVICE_SRC, DROP_SRC, LEAGUE_GROUP,
                      EVENTS_TO_PPV, resolve_label, parse_slot, slot_name, parse_country_name, display_label,
                      classify_category, parse_local, local_display, fix_mojibake, clean_event,
                      format_local, clean_city, STATE_NAMES, find_callsign, known_calls)

CHANNEL_LIKE_LABELS = {'NFL', 'NBA', 'MLB', 'NHL', 'WNBA', 'MLS', 'F1', 'EPL', 'UFC', 'Red Bull TV',
                       'Tennis', 'Golf', 'Soccer', 'PPV', 'Fubo Sports', 'GAA'}
LEAGUE_CHANNEL_RE = re.compile(r'^(NFL|NBA|MLB|NHL|WNBA)\b(?! ?G\b)')

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


def _load_tsv(name):
    rows = []
    path = os.path.join(_DATA, name)
    if os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            if line.strip() and not line.startswith('#'):
                rows.append(line.rstrip('\n').split('\t'))
    return rows


def _station(r):
    r = r + [''] * (8 - len(r))
    subs = {}
    for kv in r[4].split(';'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            subs.setdefault(k, v)
    return {'city': r[1], 'net': r[2], 'num': r[3], 'subs': subs, 'logo': r[5].split(' ')[0],
            'places': {p.lower() for p in [r[1]] + r[7].split('|') if p}}


US_STATIONS = {r[0]: _station(r) for r in _load_tsv('us_stations.tsv') if len(r) >= 4}
RENAMED_CALLS = {'WSBE': 'WPVD', 'WFIU': 'WTIU', 'WKU': 'WKYU', 'WKAS': 'WKAS'}   # old call -> current one
SPANISH_NETS = {'Telemundo', 'Univision', 'UniMás', 'Estrella TV', 'LATV', 'Azteca América', 'TeleXitos', 'Canal de la Fe'}
NET_ALIASES = {'IND': 'Independent', 'MNT': 'MyNetworkTV', 'MY': 'MyNetworkTV', 'ION': 'ION', 'CW': 'CW'}


CITY_ALIASES = {'tampabay': 'tampa', 'bayarea': 'sanfrancisco', 'southflorida': 'miami', 'twincities': 'minneapolis',
                'dc': 'washington', 'washingtondc': 'washington', 'dallasfortworth': 'dallas', 'dallasftworth': 'dallas',
                'minneapolisstpaul': 'minneapolis', 'minnesota': 'minneapolis', 'nyc': 'newyork', 'ny': 'newyork',
                'la': 'losangeles', 'philly': 'philadelphia', 'saltlake': 'saltlakecity', 'westpalmbeach': 'westpalmbeach'}


def _pl(s):
    k = re.sub(r'[^a-z]', '', (s or '').lower().replace('saint ', 'st '))
    return CITY_ALIASES.get(k, k)


def resolve_local(loc, city):
    """Complete a US local from the station table: (city, network, call, number) or None to drop (Spanish)."""
    call, net = loc.get('call'), loc.get('net')
    net = NET_ALIASES.get((net or '').upper(), net)
    city = clean_city(city) or clean_city(loc.get('city'))
    if city:                                   # 'Albany ABC' / 'Seattle King' / 'Miami Chd' -> drop network-ish words
        city = re.sub(r'\b(ABC|CBS|NBC|FOX|CW|PBS|King|Chd|Foxnet|Alaska|Montana|Texas)\b', ' ', city).strip()
        city = ' '.join(city.split()) or None
    if not call and net and city:              # 'Buffalo - ABC' -> WKBW
        key = _pl(city)
        hits = [c for c, v in US_STATIONS.items() if v['net'] == net and key in {_pl(p) for p in v['places']}]
        if len(hits) > 1:                      # several: same channel number, then the market's main station
            hits = [c for c in hits if US_STATIONS[c]['num'] == loc.get('num')] or \
                [c for c in hits if _pl(US_STATIONS[c]['city']) == key and US_STATIONS[c]['logo']] or hits
        if len(hits) > 1:
            hits = [c for c in hits if c in known_calls()] or hits
        if not hits and loc.get('num'):        # network changed since the provider named it: same city + number
            hits = [c for c, v in US_STATIONS.items() if v['num'] == loc['num'] and key in {_pl(p) for p in v['places']}]
            if len(hits) == 1:
                net = None
        if len(hits) == 1:
            call = hits[0]
    call = RENAMED_CALLS.get(call, call)
    st = US_STATIONS.get(call or '')
    if not st:
        return city, net, (f"{call}-DT{loc['sub']}" if call and loc.get('sub') else call), loc.get('num')
    num = loc.get('num')
    sub = loc.get('sub')
    if sub:                                    # 'WLOS-DT2' -> its network and 13.2
        x = next((f'{v}' for k, v in st['subs'].items() if v.endswith('.' + sub)), None)
        num = x or (f"{st['num']}.{sub}" if st['num'] else None)
        if not net:
            net = next((k for k, v in st['subs'].items() if v.endswith('.' + sub)), None)
    elif net and net in st['subs'] and not st['subs'][net].endswith('.1') and net != st['net']:
        num = st['subs'][net]                  # 'KXMB CW' is the CW subchannel
    else:
        if not net and st['net'] in SPANISH_NETS:
            return None
        net = st['net'] or net
        num = st['num'] or num
    if not city or _pl(city) not in {_pl(p) for p in st['places']}:
        city = st['city'] or city
    return city, net, call, num
CA_STATIONS = {}
for _r in _load_tsv('ca_stations.tsv'):
    if len(_r) >= 4:
        CA_STATIONS[(_r[0].lower(), _r[1].lower().replace('.', ''))] = {'net': _r[0], 'city': _r[1], 'call': _r[2],
                                                                        'num': _r[3]}
CA_REGIONS = {'BC', 'Maritimes', 'Ontario', 'Atlantic', 'Newfoundland', 'Saskatchewan', 'Vancouver Island'}
CA_CALL_INFO = {v['call']: v for v in CA_STATIONS.values()}
CA_NET_CANON = {'ctv2': 'CTV2', 'ctv 2': 'CTV2', 'ctv': 'CTV', 'cbc': 'CBC', 'global': 'Global', 'citytv': 'Citytv',
                'city tv': 'Citytv', 'city': 'Citytv', 'chch': 'CHCH', 'ntv': 'NTV', 'cjon': 'NTV', 'chek': 'CHEK',
                'ckws': 'Global', 'chex': 'Global', 'omni': 'Omni', 'abc': 'ABC', 'cbs': 'CBS', 'nbc': 'NBC',
                'fox': 'FOX', 'pbs': 'PBS', 'cw': 'CW'}
CA_PROVINCE_WORDS = re.compile(r'\b(AB|BC|MB|NB|NL|NS|ON|PE|QC|SK|YT|NT|Alberta|British Columbia|Manitoba|'
                               r'Ontario|Quebec|Québec|Saskatchewan|Nova Scotia|New Brunswick|Newfoundland|'
                               r'Prince Edward Island|PEI|DT|HD|FHD|SD|Canada)\b', re.I)


def _ca_fmt(city, net, call, num):
    if net in ('CHCH', 'CHEK', 'CJON', 'NTV') and (not call or call == net):
        call = {'NTV': 'CJON'}.get(net, net)
        net = 'NTV' if net in ('NTV', 'CJON') else 'Independent'
    return format_local('CA', city, net, call, num)


def ca_local(name):
    """'CBC Calgary (CBRT DT)', 'CTV Edmonton Alberta HD', 'CBC New Brunswick / Fredericton NB'
    -> 'Calgary - CBC - CBRT - 9'. Returns None when no place can be found."""
    m = CA_LOCAL_RE.match(name)
    if not m:
        return None
    net = CA_NET_CANON.get(re.sub(r'\s+', ' ', m.group(1).lower()), m.group(1))
    rest = name[m.end():]
    if net == 'CBC':                                   # provincial CBC feeds = the province's main station
        rest = re.sub(r'\b(TV\s*)?\(?(Ontario)\)?', ' Toronto ', rest)
        rest = re.sub(r'\b(TV\s*)?\(?(Quebec|Québec)\)?', ' Montreal ', rest)
    call = None
    cm = re.search(r'\(([CKW][A-Z]{2,3})(?:[- ](?:DT|TV|HD))?\)', rest) or re.search(r'\b(C[BFHIJK][A-Z]{2})\b', rest)
    if cm:
        call = cm.group(1)
        rest = rest.replace(cm.group(0), ' ')
    rest = re.sub(r'\(([^)]*)\)', r' \1 ', rest)
    rest = re.sub(r'^\s*\d{1,2}\b', ' ', rest)               # 'ABC 4 Seattle'
    raw = [' '.join(x.split()).strip(' -,') for x in re.split(r'\s*/\s*', rest)]
    for seg in raw:                                              # 'Global BC', 'NTV Newfoundland' are in the table
        hit = CA_STATIONS.get((net.lower(), seg.lower().replace('.', '')))
        if hit:
            city = hit['city']
            if city in CA_REGIONS:                               # 'Global BC' -> the station's home city
                city = next((v['city'] for v in CA_STATIONS.values()
                             if v['call'] == hit['call'] and v['city'] not in CA_REGIONS), city)
            return _ca_fmt(city, net, call or (hit['call'] if hit['call'] != net else None), hit['num'])
    segs = [CA_PROVINCE_WORDS.sub(' ', x) for x in re.split(r'\s*/\s*', rest)]
    segs = [' '.join(x.split()).strip(' -,') for x in segs]
    segs = [x for x in segs if x]
    city = None
    for seg in segs:                                            # prefer a place we know for this network
        if (net.lower(), seg.lower()) in CA_STATIONS:
            city = seg
            break
    if not city and segs:
        city = segs[-1] if len(segs) > 1 else segs[0]
    if city:
        city = city.replace('St Johns', "St. John's").replace("St John's", "St. John's").replace('Montréal', 'Montreal')
    if not city and not call:
        return None
    if not city:                                                 # 'NTV Newfoundland': the network's only station
        only = [v for (n, c), v in CA_STATIONS.items() if n == net.lower()]
        if len(only) == 1:
            city = only[0]['city']
    info = CA_STATIONS.get((net.lower(), (city or '').lower().replace('.', ''))) or CA_CALL_INFO.get(call or '') or \
        US_STATIONS.get(call or '') or {}
    call = call or info.get('call')
    return _ca_fmt(city or info.get('city'), net, call if call != net else None, info.get('num'))


CA_LOCAL_RE = re.compile(r'^(CBC|CTV ?2|CTV|Global|Citytv|City ?TV|City|CHCH|NTV|CJON|CHEK|CKWS|CHEX|'
                         r'ABC|CBS|NBC|FOX|PBS|CW)\b(?!\s*(News Network|News Channel|Kids|Comedy|Drama|'
                         r'Life|Sci-?Fi|Nature|Speed|Wild|Movies|Much|Sports|Gem|Explore|Docs|First|'
                         r'News National|National|News$))', re.I)
CA_PLACES = re.compile(r'\b(Toronto|Ottawa|Montreal|Vancouver|Calgary|Edmonton|Winnipeg|Regina|Saskatoon|'
                       r'Halifax|Fredericton|Moncton|Charlottetown|St\.? John\'?s|Newfoundland|Windsor|London|'
                       r'Kitchener|Barrie|Sudbury|Timmins|Sault|North Bay|Peterborough|Kingston|Hamilton|'
                       r'Lethbridge|Red Deer|Kelowna|Okanagan|Prince George|Yellowknife|Yukon|Atlantic|'
                       r'Maritimes|Alberta|Saskatchewan|Manitoba|Ontario|Quebec|Québec|British Columbia|BC|'
                       r'Sherbrooke|Victoria|Vancouver Island|Buffalo|Detroit|Seattle|Boston|Bellingham|'
                       r'Pembroke|Prairies|Pacific|East|West|Sydney|Thunder Bay|Brandon|Dawson Creek|'
                       r'Medicine Hat|Kamloops|Lloydminster|Prince Albert|Swift Current|Yorkton|Montréal|'
                       r'Northern Ontario|Southwestern Ontario|Niagara|Kenora|Rimouski|Saguenay|Trois-Rivières)\b',
                       re.I)


def norm_feed_words(name):
    name = re.sub(r'\((East|West|Pacific|Atlantic|Central|Mountain|Eastern|Western)\)', r' \1', name, flags=re.I)
    name = re.sub(r'\b(EAST|WEST|PACIFIC|ATLANTIC)\b', lambda m: m.group(1).title(), name)
    name = re.sub(r'\bEastern\b', 'East', name)
    name = re.sub(r'\bWestern\b', 'West', name)
    name = re.sub(r'\b(East|West|Pacific)( \1\b)+', r'\1', name)
    return re.sub(r'\s+', ' ', name).strip()


def tidy(name):
    name = re.sub(r'\s*\[(?:VIP|NEW|BACKUP|HQ|LQ|MULTI|EN|ENG)\]\s*', ' ', name, flags=re.I)
    name = re.sub(r'\s*\((?:English|EN|ENG)\)\s*', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' -|:•')
    name = re.sub(r'\s*:\s*$', '', name)
    name = re.sub(r'\(\s*\)', '', name)
    return re.sub(r'\s+', ' ', name).strip()


def finish(rec, name, q=None):
    name = tidy(name)
    if q:
        name = f'{name} {q}'
    rec['name'] = name
    rec['quality'] = q
    return rec


def event_record(rec, label, t):
    grp_label = LEAGUE_GROUP.get(label)
    if label in EVENTS_TO_PPV or grp_label is None:
        rec['group'] = PPV_GROUP
    else:
        rec['group'] = sports_group(grp_label)
    rec['kind'] = 'event'
    if LEAGUE_CHANNEL_KEEP.match(t) and parse_slot(strip_slot_quality(t)[0])[1] is None:
        nm, q = extract_quality(strip_tail_tags(t))
        rec['kind'] = 'league-channel'
        rec['label'] = label
        return finish(rec, norm_feed_words(smart_case(nm)), q)
    p = parse_slot(strip_slot_quality(t)[0])[0]
    disp = display_label(label, p, t)
    name, q = slot_name(label, t, disp)
    rec['label'] = label
    return finish(rec, name, q)


def event_label(t, default=None):
    """The slot prefix decides the group (it is stable); event text is only a fallback."""
    p, n, e = parse_slot(t)
    lab = resolve_label(p) if p else None
    if lab is None and n is None:
        lab = resolve_label(t)
    return lab or default, p, n


LEAGUE_CHANNEL_KEEP = re.compile(r'^(NFL|NBA|MLB|NHL|WNBA)\s*(Network|TV|RedZone|Red ?Zone|Strike ?Zone|Big Inning|'
                                 r'FAST|Zone|Game ?Pass|League Pass|Now|Plus|Films|Alternate|Alt|Channel|Mobile)', re.I)


US_NET_START = re.compile(r'^(ABC|CBS|NBC|FOX|PBS|CW|The CW|MyNetworkTV)\b(?!\s*(Spark|Sports|News|Business|Kids))', re.I)


# the mixed-country 4K packages: Russian, Spanish, French, Polish, Dutch, Nordic, Italian, Iranian channels
FOREIGN_4K = re.compile(r'\b(RU|ES|FR|PL|NL|IT)\b(?=.*(UHD|4K))|\b(Our Siberia|Kino|Quadro|Ultra Cinema|Ultra Rex|Museum|'
                        r'Through the Eyes of a Tourist|LA 1|TF1|France 2|IRIB|Rai 1|Ziggo|Eleven (PL|Sports PL)|Digi|Odisea|'
                        r'Decasa|Slow|Movistar|M\+ LaLiga|V Sport)\b', re.I)


def branded_local(name):
    """'ABC7 Chicago', 'KIRO 7 Seattle', 'WCPO 9 Cincinnati', 'Boston 25', 'FOX 29 Philadelphia' -> a local record,
    but only when the station table confirms which station it is."""
    nm = re.sub(r'\((?:[A-Z])\)|\s+Very\s+|\s+', ' ', name).strip()
    if re.search(r'\bLocal\b|\bNews$|^(CBSN|Spectrum)\b|\bPlus\b|\bXtra\b', nm):
        return None
    cands = []
    cm = find_callsign(nm)
    if not (cm and cm.group(1) in US_STATIONS):           # 'WOOD' is also a word, so the finder skips it
        cm = next((t for t in re.finditer(r'\b([KW][A-Z]{2,3})(?:-(?:TV|DT|CD|LD|LP))?\b', nm) if t.group(1) in US_STATIONS), None)
    if cm and cm.group(1) in US_STATIONS:
        rest = nm.replace(cm.group(0), ' ')
        num = re.search(r'\b(\d{1,2})\b', rest)
        cands.append({'net': None, 'num': num.group(1) if num else None, 'call': cm.group(1), 'sub': None,
                      'city': ' '.join(re.sub(r'\d+|[()/+]|\bNews\b|\bAction\b|\bTV\b', ' ', rest).split())})
    m = re.match(r'^(?:(ABC|CBS|NBC|FOX|CW|PBS|My)\s?(\d{1,2})|(\d{1,2})\s?(ABC|NBC|CBS))\b\s*(.*)$', nm)
    if m and not cands:
        net = (m.group(1) or m.group(4)).upper().replace('MY', 'MyNetworkTV')
        rest = re.sub(r'\([^)]*\)|\bNews\b', ' ', m.group(5))
        cands.append({'net': net, 'num': m.group(2) or m.group(3), 'call': None, 'sub': None,
                      'city': ' '.join(rest.replace('/', ' ').split()) or None})
    m = re.match(r'^([A-Z][A-Za-z.]+(?: [A-Z][A-Za-z.]+)?) (\d{1,2})(?: News)?$', nm)
    if m and not cands:
        cands.append({'net': None, 'num': m.group(2), 'call': None, 'sub': None, 'city': m.group(1)})
    for loc in cands:
        if loc['call']:
            return loc
        key = _pl(clean_city(loc['city']) or '')
        if not key:
            continue
        hits = [c for c, v in US_STATIONS.items() if v['num'] == loc['num'] and key in {_pl(p) for p in v['places']}
                and (not loc['net'] or v['net'] == loc['net'] or loc['net'] in v['subs'])]
        if not hits and loc['net']:                      # 'PBS 65 (Virtual) Wheeling': number is not the real one
            hits = [c for c, v in US_STATIONS.items() if v['net'] == loc['net'] and _pl(v['city']) == key]
            if len(hits) == 1:
                loc['num'] = None
        if len(hits) > 1:
            hits = [c for c in hits if c in known_calls()] or hits
        if len(hits) == 1:
            loc['call'] = hits[0]
            return loc
    return None


def us_station_in_ca(name):
    if re.match(r'^(CBC|CTV|Global|Citytv|City|CHCH|NTV|CHEK|Omni)\b', name, re.I):
        return False
    m = find_callsign(name)
    if m and m.group(1) in US_STATIONS:
        return True
    return bool(US_NET_START.match(name))


def process_entry(c):
    src = c['attrs'].get('group-title', '')
    url = c.get('url', '')
    raw = c['title']
    rec = {'src': c.get('orig_group', src), 'orig': c.get('orig_title', raw), 'drop': None, 'group': None, 'name': None, 'cc': None,
           'kind': None, 'quality': None, 'local': None}
    if '/series/' in url or '/movie/' in url:
        rec['drop'] = 'VOD episode' if '/series/' in url else 'VOD movie'
        return rec
    t = basic_clean(fix_mojibake(raw))
    pm = re.search(r'\((RK|TUBI|7Plus|9Now|10Play|SBS)\)', raw, re.I) or \
        (re.search(r'\((ABC)\)', raw) if re.match(r'^\(?AU\b', raw) else None)
    rec['platform'] = pm.group(1).upper() if pm else None        # free service the channel streams from
    if src in DROP_SRC:
        rec['drop'] = DROP_SRC[src]
        return rec
    if src == 'XXX':
        rec['group'] = ADULT_GROUP
        rec['kind'] = 'adult'
        n = re.sub(r'^(\|\+18\||\[XXX\]|\*xxx:|\(Adult\)|\(18\+\)|Adult\s*:?)\s*', '', t, flags=re.I)
        n, q = extract_quality(strip_tail_tags(n))
        return finish(rec, smart_case(n), q)
    if JUNK_RE.search(t) or re.fullmatch(r'[\W\d_]*', t):
        rec['drop'] = 'test / placeholder feed'
        return rec
    mc = re.match(r"^MC\s+(.+?)\s*\((?:M)\)\s*$", t)
    if src == '24/7 Streams' and mc:                          # 'MC '80s (M)' = Music Choice radio channel
        rec['cc'] = 'US'
        rec['kind'] = 'channel'
        rec['group'] = country_group('US', 'Music')
        return finish(rec, 'US: Music Choice: ' + smart_case(mc.group(1)).replace("'", "'"))
    if src == '24/7 Streams':
        rec['group'] = G247
        rec['kind'] = '247'
        if is_non_english(t) or re.match(r'^(MX|ES|AR|IN|FR)\b', t) or re.search(r'\((FR|ES|DE|IT|PT|NL)\)\s*$', t):
            rec['drop'] = 'non-English'
            return rec
        if re.match(r'^(24/7\s*:?\s*)?Oneplay\b', t, re.I):        # Czech streaming service channels
            rec['drop'] = 'non-English (Oneplay, Czech)'
            return rec
        n = re.sub(r'^24/7\s*:?\s*', '', t)
        n = re.sub(r'^(?:M\d|VIBE|MC|US)\s*[:|]?\s*', '', n)
        n = strip_tail_tags(n)
        n = re.sub(r'\bSeason (\d+)\b', lambda m: f'S{int(m.group(1)):02d}', n)
        n = re.sub(r'\bS(\d)\b', r'S0\1', n)
        n, q = extract_quality(n)
        n = re.sub(r"\b([A-Za-z]{3,}) S (?=[A-Za-z])", r"\1's ", n)      # 'RUPAUL S DRAG RACE'
        title = smart_case(tidy(n))
        rec['group'] = LOOP_GROUPS[loop_type(title, rec['src'])]
        return finish(rec, '24/7 ' + title, q)

    is_event_src = src in LEAGUE_SRC or src in SERVICE_SRC or src == 'PPV Live Events'
    if is_event_src:
        pre = parse_slot(t)[0] or ''
        if is_non_english(pre) or re.match(r'^(VIX|FNTZ|MOLA)', t, re.I) or \
                re.search(r'\bSpanish\b|ESPAÑOL|\(ES\)|\bFrench\)', t):
            rec['drop'] = 'non-English'
            return rec
        t2 = re.sub(r'^US \(S\)\s*', '', t)
        default = SERVICE_SRC.get(src) or LEAGUE_SRC.get(src) or 'Live Events'
        if src == 'NCAA':
            default = 'NCAAF' if re.search(r'football|ncaaf', t, re.I) else 'NCAA'
        label, pfx, n = event_label(t2, default)
        if n is None and is_non_english(t2):
            rec['drop'] = 'non-English'
            return rec
        if label == 'DAZN' and re.search(r'DAZN (IT|ES|DE|PT|FR)\b|^\((IT|ES|DE|PT|FR)\)', t):
            rec['drop'] = 'non-English (DAZN Europe)'
            return rec
        return event_record(rec, label, t2)

    if is_non_english(t) or (re.search(r'4K|UHD', src + ' ' + rec['src'] + ' ' + raw) and FOREIGN_4K.search(t)):
        rec['drop'] = 'non-English'
        return rec
    # --- channel sources: some carry event slots too ------------------------------
    # 'NCAAF 04 UCF @ Oklahoma State 12PM' / '(UK) (PRIME 002) | Rockies at Astros (...)' -> slot form
    m_ev = re.match(r'^(NCAAF|NCAAB|NFL|NBA|NHL|MLB|MLS|WNBA)\s+(\d{1,3})\s+(.+\s(?:@|vs\.?|at)\s.+)$', t)
    if m_ev:
        t = f'{m_ev.group(1)} {m_ev.group(2)}: {m_ev.group(3)}'
    m_ev = re.match(r'^\((?:UK|US|CA)\)\s*\((PRIME|PEACOCK|DAZN|MAX|PARAMOUNT\+?|ESPN\+?)\s*(\d{1,3})\)\s*\|\s*(.+)$', t, re.I)
    if m_ev:
        svc = {'PRIME': 'Prime Video', 'PEACOCK': 'Peacock', 'MAX': 'MAX'}.get(m_ev.group(1).upper(), m_ev.group(1))
        t = f'{svc} {int(m_ev.group(2)):02d}: {m_ev.group(3)}'
    t = re.sub(r'^\(MC Radio\)\s*', 'Music Choice: ', t)
    if not re.match(r'^(US|USA|CA|UK|AU|AUS|NZ|IRE)\s*:', t):
        t2 = re.sub(r'^\(US\) \(DZ\)\s*', '', t)
        label, pfx, n = event_label(t2)
        if label and n is not None and (label not in CHANNEL_LIKE_LABELS or re.search(r'\d\s*[:|]|[:|]\s*\d', t2)):
            if label == 'DAZN' and re.search(r'^\((IT|ES|DE|PT|FR)\)|DAZN (IT|ES|DE|PT|FR)\b', t):
                rec['drop'] = 'non-English (DAZN Europe)'
                return rec
            if label != 'Hub Sports':
                return event_record(rec, label, t2)

    default_cc = CHANNEL_SRC.get(src, 'US')
    info = parse_country_name(t, default_cc)
    if info['foreign']:
        rec['drop'] = f"non-English ({info['foreign']})"
        return rec
    cc = info['cc']
    name = strip_tail_tags(info['name'])
    qtag = next((x[2:] for x in info['tags'] if x.startswith('Q:')), None)
    name, q = extract_quality(name)
    q = q or {'UHD': '4K'}.get(qtag, qtag)
    name = strip_tail_tags(name)
    name = re.sub(r'\((?:2098|2099)[^)]*\)', '', name).strip(' |:')
    name = re.sub(r'^MC(\d{2})H:\s*Music Choice$', lambda m: f'Music Choice {int(m.group(1))}', name)
    name = re.sub(r'^\(?(?:9Now|7Plus|KAYO|ABC|SBS)\)\s*', '', name) if cc == 'AU' else name
    if not name or re.fullmatch(r'[\W\d_]*', name):
        rec['drop'] = 'empty / placeholder name'
        return rec
    if re.match(r'^Hub ', name):
        cc = 'INT'
    if is_non_english(name):
        rec['drop'] = 'non-English'
        return rec

    if cc == 'BEIN':
        if re.search(r'\b(XTRA|EN \d|NBA)\b', name, re.I):
            cc = 'INT'
        elif re.search(r'^(beIN (MOVIES|SERIES|DRAMA)|Star (World|Movies|Action))', name, re.I):
            cc = 'INT'
            src = 'beIN Ent'
        else:
            rec['drop'] = 'non-English (beIN MENA Arabic feeds)'
            return rec
    if cc == 'RACING':
        if re.search(r'Equidia|ATG', name, re.I):
            rec['drop'] = 'non-English (French/Swedish racing)'
            return rec
        cc = 'AU' if re.search(r'racing\.com', name, re.I) else ('UK' if re.search(r'greyhound', name, re.I) else 'INT')
        rec['cc'] = cc
        rec['group'] = country_group(cc, 'Sports')
        rec['kind'] = 'channel'
        return finish(rec, f'{cc}: {smart_case(name)}', q)

    rec['cc'] = cc
    rec['kind'] = 'channel'
    # league-owned channels go to the league group
    lm = LEAGUE_CHANNEL_RE.match(name)
    if lm:
        lg = lm.group(1).upper()
        rec['group'] = sports_group(LEAGUE_GROUP[lg])
        rec['kind'] = 'league-channel'
        nm = norm_feed_words(smart_case(name))
        nm = re.sub(r'^(NFL|NBA|MLB|NHL|WNBA)\b', lg, nm, flags=re.I)
        if not LEAGUE_CHANNEL_KEEP.match(nm):
            nm = re.sub(r'^(NFL|NBA|MLB|NHL|WNBA)\s*:?\s*(?:\([A-Z]{2,4}\)\s*)?', r'\1: ', nm)
        return finish(rec, nm, q)

    if cc == 'CA' and us_station_in_ca(name):      # Buffalo / Seattle / Detroit stations carried in Canada
        cc = rec['cc'] = 'US'
        src = 'US Locals & Regional'
    if cc == 'US':
        mc = re.match(r"^([A-Z][\w .'-]+), ([A-Z]{2}) (.+?)(?:\s*\((?:Virtual|A\d?[^)]*)\))?$", name)
        if mc and mc.group(2) in US_STATES:          # 'Grand Rapids, MI WOOD NBC 8' -> 'WOOD NBC 8 Grand Rapids'
            body = re.sub(r'\b([KW][A-Z]{2,3})(CD|LP|LD|DT|TV)\b', r'\1-\2', mc.group(3), flags=re.I)
            body = re.sub(r'\b([KW][A-Za-z]{2,3})-(Cd|Lp|Ld|Dt|Tv)\b', lambda x: x.group(0).upper(), body)
            name = f'{body} {mc.group(1)}'
            src = 'US Locals & Regional'
        bracket = re.match(r'^\[([^\]]+)\]\s*(.*)$', name)
        if bracket:
            # "[Miami] Oxygen True Crime (OXYGEN)" -> national feed; "[Arlington] WFAA" -> local
            inner = re.sub(r'\s*\(([A-Z0-9]{4,})\)\s*$', '', bracket.group(2)).strip()
            if re.fullmatch(r'[KW][A-Z]{2,3}', inner) or re.fullmatch(r'[A-Z]{2,4}\d*', inner):
                name = f'{inner} {bracket.group(1)}' if not re.fullmatch(r'[KW][A-Z]{2,3}', inner) else f'{bracket.group(1)} ({inner})'
            else:
                name = inner
        if re.match(r'^(?:FOX|NBC|CBS|ABC)(?: \d+)? Local\b|^FOX LOCAL\b', name, re.I):
            rec['group'] = country_group('US', 'News')
            return finish(rec, f'US: {norm_feed_words(smart_case(name))}', q)
        m_cw = re.match(r'^(ABC|CBS|NBC|FOX|CW|PBS|MyNetworkTV|MNT)\s+([A-Z][A-Za-z .\'-]+),\s*([A-Z]{2})$', name)
        if m_cw and m_cw.group(3) in US_STATES:
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'local'
            rec['local'] = {'net': m_cw.group(1), 'num': None, 'call': None, 'sub': None, 'city': m_cw.group(2)}
            rec['q_pending'] = q
            return finish(rec, format_local('US', m_cw.group(2), m_cw.group(1)), q)
        m_call = re.match(r'^([KW][A-Z]{2,3})(?:-(?:TV|DT|LD|CD))?\s+([A-Z][A-Za-z .\'/-]+)$', name)
        if m_call and m_call.group(1) not in NOT_CALLSIGNS and not re.search(r'\bNews\b', name) \
                and not re.match(r'^(World|Wild|West|Women|Kids|King|Kitchen)\b', name, re.I):
            name = f'{m_call.group(2)} ({m_call.group(1)})'
        elif re.fullmatch(r'[KW][A-Z]{2,3}', name) and name not in NOT_CALLSIGNS and src in LOCAL_SRC | {'United States', 'US Entertainment'}:
            name = f'({name})'
        loc = parse_local(name, loose=src in LOCAL_SRC or bool(bracket) or bool(m_call) or name.startswith('(')) or \
            branded_local(name)
        if loc and loc.get('call') in SPANISH_CALLS:
            rec['drop'] = 'non-English (Spanish-language local station)'
            return rec
        if loc and not re.search(r'\b(News Live|Localish|Telemundo|Univision)\b', name, re.I):
            rec['local'] = loc
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'local'
            rec['q_pending'] = q
            return rec
    if cc == 'CA' and re.match(r'^(?:CBC|CTV|Global|Citytv|City)\b.*\bNews\b', name, re.I):
        rec['group'] = country_group('CA', 'News')
        return finish(rec, f'CA: {norm_feed_words(smart_case(name))}', q)
    if cc == 'CA' and CA_LOCAL_RE.match(name) and CA_PLACES.search(name):
        rec['group'] = country_group('CA', 'Locals')
        nm = norm_feed_words(smart_case(name))
        if re.fullmatch(r'(CBC|CTV|Global|Citytv|CTV2)( (East|West|Pacific|Central|Mountain))?', nm):
            rec['group'] = country_group('CA', 'General')          # national network feeds, not a station
        loc = ca_local(nm)
        if loc and not re.match(r'^CA: (East|West|Pacific|Central|Mountain|TV)\b', loc):
            rec['kind'] = 'ca-local'
            rec['lookup'] = nm                 # guide/logo matching still uses 'CBC Calgary'
            return finish(rec, loc, q)
        return finish(rec, f'CA: {nm}', q)

    # channels that are really one show / film series / actor on loop belong with the 24/7 channels
    title = norm_feed_words(smart_case(name)).replace(' | ', ' - ')
    lab = country_label(title)
    if lab is None and re.search(r'\b24/7\b', title):          # 'Dance Moms 24/7', 'Comedy 24/7'
        title = ' '.join(re.sub(r'\b24/7\b', ' ', title).split())
        lab = loop_type(title, rec['src'])
    if lab == 'X':
        rec['drop'] = 'non-English'
        return rec
    if lab in LOOP_GROUPS:
        rec['group'] = LOOP_GROUPS[lab]
        rec['kind'] = '247'
        rec['lookup'] = title                 # keep the guide match ('Blue Bloods' on Pluto has real listings)
        return finish(rec, '24/7 ' + title, q)
    cat = classify_category(name, src)
    home = home_country(title, cc)               # CNN in a Canada group -> US, RTE in a UK group -> IE
    if home != cc:
        cc = rec['cc'] = home
        if cc == 'INT' and cat == 'Locals':
            cat = 'General'
    ic = iptv_category(title, cc)
    if ic and (cat == 'General' and ic != 'General' or cat == 'Sports' and ic != 'Sports'):
        cat = ic                                  # 'Adult Swim' is not sport
    if cc == 'INT' and cat not in ('Sports', 'News', 'Music'):
        cat = 'General'
    rec['group'] = country_group(cc, cat)
    return finish(rec, f'{cc}: {norm_feed_words(smart_case(name)).replace(" | ", " - ")}', q)


def process_all(entries):
    recs = [process_entry(c) for c in entries]
    # pass 2: give every local station a consistent city
    cities = collections.defaultdict(collections.Counter)
    for r in recs:
        loc = r.get('local')
        if loc and loc['city']:
            c = clean_city(loc['city'])
            if not c:
                continue
            score = 2 if not c.isupper() else 1
            if c.lower() in STATE_NAMES or len(c.split()) > 3:      # 'Arizona', 'Arizona's Family Sports Phoenix'
                score -= 1.5
            cities[loc['call']][c] += score
    for r in recs:
        loc = r.get('local')
        if not loc or r.get('kind') != 'local':
            continue
        city = None
        if loc.get('call') and cities.get(loc['call']):
            city = cities[loc['call']].most_common(1)[0][0]
        # fill gaps (city / network / call / channel number) from the station table (Wikipedia + providers)
        res = resolve_local(loc, city or loc.get('city'))
        if res is None:
            r['drop'] = 'non-English (Spanish-language local station)'
            r['group'] = None
            continue
        c_, n_, k_, num_ = res
        loc['call'] = k_.split('-')[0] if k_ else None
        finish(r, format_local('US', c_, n_, k_, num_), r.pop('q_pending', None))
        if not (c_ and n_ and k_ and num_):
            r['local_incomplete'] = True
    return recs
