# -*- coding: utf-8 -*-
"""Apply the rules to every entry. Two passes so local stations can share city names."""
import os
import re
import collections
from origin import home_country, iptv_category
from loops import loop_type, country_label, GROUPS as LOOP_GROUPS
from rules import (SPANISH_CALLS, NOT_CALLSIGNS, US_STATES, basic_clean, extract_quality, strip_tail_tags, smart_case, is_non_english, JUNK_RE,
                   country_group, sports_group, PPV_GROUP, G247, ADULT_GROUP, COUNTRY_ORDER)
from classify import US_CITY_STATE as CLASSIFY_US_CITY_STATE
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


LOGO_NOISE = {'logo', 'logos', 'svg', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'px', 'tv', 'dt', 'the', 'legal', 'new',
              'vector', 'cropped', 'current', 'wordmark', 'icon', 'official', 'station', 'id', 'hd', 'and', 'of'}


def _brand_words(call, logo):
    """Words of a station's logo file name ('KOCE_PBS_SoCal_logo_2024.svg' -> {'pbs', 'socal'}): its branding."""
    from urllib.parse import unquote
    fn = re.sub(r'^\d+px-', '', unquote((logo or '').rsplit('/', 1)[-1]))
    fn = re.sub(r'([a-z])([A-Z])|([A-Z])([A-Z][a-z])', lambda m: ' '.join(x for x in m.groups() if x), fn)
    words = [w for w in re.findall(r'[a-z]+|\d+', fn.lower())
             if w not in LOGO_NOISE and w != call.lower() and not re.fullmatch(r'(19|20)\d\d|\d{3,}', w)]
    return set(words) | {a + b for a, b in zip(words, words[1:])}       # 'So Cal' also as 'socal'


def _station(r, call=''):
    r = r + [''] * (8 - len(r))
    subs = {}
    for kv in r[4].split(';'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            subs.setdefault(k, v)
    logo = r[5].split(' ')[0]
    return {'city': r[1], 'net': r[2], 'num': r[3], 'subs': subs, 'logo': logo, 'state': r[6],
            'brand': _brand_words(call, logo), 'places': {p.lower() for p in [r[1]] + r[7].split('|') if p}}


US_STATIONS = {r[0]: _station(r, r[0]) for r in _load_tsv('us_stations.tsv') if len(r) >= 4}
STATE_NAMES_TITLE = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware',
                     'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
                     'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
                     'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico',
                     'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania',
                     'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont',
                     'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming', 'Hi']
RENAMED_CALLS = {'WSBE': 'WPVD', 'WFIU': 'WTIU', 'WKU': 'WKYU', 'WPCW': 'WPKD', 'WCGV': 'WVTV', 'KET': 'WKLE',
                 'WCLP': 'WNGH', 'WFRN': 'WFRV'}   # old call / provider shorthand or typo -> the station today
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
        if not hits:                           # 'NBC: IN FORT WAYNE' -> WPTA's NBC subchannel
            hits = [c for c, v in US_STATIONS.items() if net in v['subs'] and key in {_pl(p) for p in v['places']}]
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
    elif net and net in st['subs'] and st['subs'][net] != f"{st['num']}.1" and net not in _nets(st):
        num = st['subs'][net]                  # 'KXMB CW' is the CW subchannel
    else:
        if not net and st['net'] in SPANISH_NETS:
            return None
        net = st['net'] or net
        num = st['num'] or num
    city = st['city'] or city                  # one station, one name: always its own city
    return city, net, call, num
CA_STATIONS = {}
CA_HOME = {}                                   # call -> the station's own row (city of licence, network, channel)
for _r in _load_tsv('ca_stations.tsv'):
    if len(_r) >= 4:
        _v = {'net': _r[0], 'city': _r[1], 'call': _r[2], 'num': _r[3]}
        CA_STATIONS[(_r[0].lower(), _r[1].lower().replace('.', ''))] = _v
        if not (len(_r) > 4 and _r[4] == 'alias'):
            CA_HOME.setdefault(_r[2], _v)
CA_REGIONS = {'BC', 'Maritimes', 'Ontario', 'Atlantic', 'Newfoundland', 'Saskatchewan', 'Vancouver Island', 'North',
              'Nova Scotia', 'Durham', 'Yellowknife North', 'Okanagan'}
CA_CALL_INFO = CA_HOME
# regional services carried on cable only - no transmitter, so no call sign or channel number
CA_REGIONAL = {('ctv2', 'alberta'): 'Alberta', ('ctv2', 'atlantic'): 'Atlantic', ('ctv2', 'halifax'): 'Atlantic',
               ('ctv2', 'nova scotia'): 'Atlantic', ('citytv', 'saskatchewan'): 'Saskatchewan'}
CA_NET_CANON = {'ctv2': 'CTV2', 'ctv 2': 'CTV2', 'ctv': 'CTV', 'cbc': 'CBC', 'global': 'Global', 'citytv': 'Citytv',
                'city tv': 'Citytv', 'city': 'Citytv', 'chch': 'CHCH', 'ntv': 'NTV', 'cjon': 'NTV', 'chek': 'CHEK',
                'ckws': 'Global', 'chex': 'Global', 'omni': 'Omni', 'abc': 'ABC', 'cbs': 'CBS', 'nbc': 'NBC',
                'fox': 'FOX', 'pbs': 'PBS', 'cw': 'CW', 'yes tv': 'Yes TV', 'yes': 'Yes TV'}
CA_PROVINCE_WORDS = re.compile(r'\b(AB|BC|MB|NB|NL|NS|ON|PE|QC|SK|YT|NT|Alberta|British Columbia|Manitoba|'
                               r'Ontario|Quebec|Québec|Saskatchewan|Nova Scotia|New Brunswick|Newfoundland|'
                               r'Prince Edward Island|PEI|DT|HD|FHD|SD|Canada)\b', re.I)


def _ca_fmt(city, net, call, num):
    if net in ('CHCH', 'CHEK', 'CJON', 'NTV') and (not call or call == net):
        call = {'NTV': 'CJON'}.get(net, net)
        net = 'NTV' if net in ('NTV', 'CJON') else 'Independent'
    home = CA_HOME.get(call or '')
    if home:                                   # one station, one name: its own city, network and channel
        city, net, num = home['city'], home['net'], home['num']
        if net in ('CHCH', 'CHEK'):
            net = 'Independent'
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
    place = ' '.join(re.sub(r'\b(HD|FHD|SD|DT)\b', ' ', rest).split()).strip(' -,').lower()
    if (net.lower(), place) in CA_REGIONAL and not call:      # 'CTV2 Alberta' is a cable channel, not CKAL
        return f'CA: {CA_REGIONAL[(net.lower(), place)]} - {net}'
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
    if not city:                                                 # 'CHCH', 'Yes TV': the network's only station
        only = {v['call'] for v in CA_HOME.values() if v['net'].lower() == net.lower()}
        if len(only) == 1:
            call = call or only.pop()
            city = CA_HOME[call]['city']
    if not city and not call:
        return None
    info = CA_STATIONS.get((net.lower(), (city or '').lower().replace('.', ''))) or CA_CALL_INFO.get(call or '') or \
        US_STATIONS.get(call or '') or {}
    call = call or info.get('call')
    return _ca_fmt(city or info.get('city'), net, call if call != net else None, info.get('num'))


def ca_id_hint(name, tvg_id):
    """A bare network name ('CTV 2', 'Global East') or bare area ('Vancouver Island') whose provider guide id names
    the station: 'ca.CTV2 Vancouver Island. BC DV' -> CIVI, 'ca.Global (CIII-DT-41) Toronto' -> CIII."""
    nm = re.sub(r'\s*\b(HD|FHD|SD)$', '', name).strip()
    m = re.fullmatch(r'(?:(CTV ?2|CTV|Global|Citytv|City ?TV|CBC|CHEK)(?: (?:East|West))?|(Vancouver Island))', nm, re.I)
    if not m or not tvg_id:
        return None
    ids = re.sub(r'([a-z])([A-Z])', r'\1 \2', tvg_id)          # 'ChekVancouverIsland.ca' -> 'Chek Vancouver Island.ca'
    if m[1]:
        net = CA_NET_CANON.get(re.sub(r'\s+', ' ', m[1].lower()))
        if not re.search(r'\b' + re.escape(net).replace('CTV2', r'CTV ?2') + r'\b', ids, re.I):
            return None                         # the id must be for the same network
    else:
        mn = re.match(r'^(?:ca\.)?(CTV ?2|CTV|Global|Citytv|CBC|CHEK)\b', ids, re.I)
        if not mn:
            return None
        net = CA_NET_CANON.get(re.sub(r'\s+', ' ', mn[1].lower()))
    for call in re.findall(r'\b(C[A-Z]{3})(?:-DT)?\b', ids):
        if call in CA_HOME and CA_HOME[call]['net'] == net:
            return _ca_fmt(None, net, call, None)
    low = ids.lower().replace('.', ' ')
    places = [p for (n, p) in CA_STATIONS if n == net.lower() and re.search(r'\b' + re.escape(p) + r'\b', low)]
    if places:
        hit = CA_STATIONS[(net.lower(), max(places, key=len))]
        return _ca_fmt(None, net, hit['call'], None)
    return None


CA_LOCAL_RE = re.compile(r'^(CBC|CTV ?2|CTV|Global|Citytv|City ?TV|City|CHCH|NTV|CJON|CHEK|CKWS|CHEX|Yes TV|Yes|'
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
                       r'Northern Ontario|Southwestern Ontario|Niagara|Kenora|Rimouski|Saguenay|Trois-Rivières|'
                       r'Burlington|Durham|Oshawa|Saint John\'?s|Kamloops)\b',
                       re.I)


CA_FRENCH_RE = re.compile(r'^(?:Addik ?TV|Canal M|Elle Fictions|La Cha[iî]ne Disney|T[ée]moin|[ÚU]n ?TV|Unis ?TV|V Montr[ée]al|'
                          r'Noovo|Z|Z NTV|Z T[ée]l[ée]|Zeste|RDS ?\d?|RDS ?Info|Radio[- ]Canada(?: Info)?|ICI\b.*|AMI[- ]?t[ée]l[ée]|Ami t|'
                          r'TVA\b.*|T[ée]l[ée]-Qu[ée]bec|Savoir M[ée]dia|S[ée]ries\+|Canal Vie|Canal D|Historia|Moi ?& ?Cie|'
                          r'Prise 2|Evasion|[ÉE]vasion|Max(?:\s+TV)?$|TV5(?: Unis)?|Yoopa|T[ée]l[ée]toon(?: Fr)?|Vrak|Casa|Planete\+|'
                          r'Investigation$|Super [ÉE]cran.*|Cin[ée]pop|LCN|RDI|Explora|ARTV|Télé Mag)\s*(?:HD|FHD|SD)?$', re.I)
CA_STREAM_RES = [                               # (brand, place) of station-run local news streams
    re.compile(r'^(?P<net>CBC) News (?P<place>(?!Network\b|Channel$|Now\b|Explore\b)[A-Z][\w .\'-]*?)(?: Channel)?$'),
    re.compile(r'^(?P<net>Global) News (?P<place>(?!National\b)[A-Z][\w .\'-]*?)$'),
    re.compile(r'^(?P<net>Global) (?P<place>(?!News\b|National\b)[A-Z][\w .\'-]*?) News$'),
    re.compile(r'^(?P<net>CTV) News (?P<place>(?!Channel\b|National\b|Network\b)[A-Z][\w .\'-]*?)$'),
    re.compile(r'^(?P<net>City ?News) (?P<place>(?!24/7)[A-Z][\w .\'-]*?)(?: ON| AB| BC)?$'),
]
CA_STREAM_PLACE = {'bc': 'British Columbia', 'nl': 'Newfoundland and Labrador', 'pei': 'PEI', 'monterial': 'Montreal',
                   'british columbia': 'British Columbia'}
CA_PROVINCE_CITY = {'British Columbia': 'Vancouver', 'Manitoba': 'Winnipeg', 'Newfoundland and Labrador': "St. John's",
                    'New Brunswick': 'Fredericton', 'Nova Scotia': 'Halifax', 'PEI': 'Charlottetown', 'Quebec': 'Montreal',
                    'Saskatchewan': 'Regina', 'North': 'Yellowknife', 'Okanagan': 'Kelowna', 'Alberta': 'Calgary',
                    'Montreal': 'Montreal', 'Toronto': 'Toronto'}


def ca_stream(name):
    """'CBC News Calgary Channel' -> ('Calgary', 'CBC News Calgary'), 'Global BC News' -> ('Vancouver',
    'Global News BC'), 'City News Toronto ON' -> ('Toronto', 'CityNews Toronto')."""
    nm = re.sub(r'\s*\b(HD|FHD|SD)$', '', name)
    for rx in CA_STREAM_RES:
        m = rx.match(nm)
        if not m:
            continue
        net = 'CityNews' if m['net'].replace(' ', '').lower() == 'citynews' else m['net']
        place = CA_STREAM_PLACE.get(m['place'].lower(), m['place'])
        if place.lower() in ('pei', 'nl'):
            place = place.upper()
        city = CA_PROVINCE_CITY.get(place) or (place if CA_PLACES.fullmatch(place) else None)
        if not city:
            return None
        brand_place = {'British Columbia': 'BC'}.get(place, place) if net == 'Global' else place
        return city, f'{net} News {brand_place}' if net != 'CityNews' else f'CityNews {place}', nm
    return None


def norm_feed_words(name):
    name = re.sub(r'\((East|West|Pacific|Atlantic|Central|Mountain|Eastern|Western)\)', r' \1', name, flags=re.I)
    name = re.sub(r'\b(EAST|WEST|PACIFIC|ATLANTIC)\b', lambda m: m.group(1).title(), name)
    name = re.sub(r'\bEastern$', 'East', name)              # a feed word only at the end ('Outlaw Western' stays)
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


NET_WORDS = r'(?:ABC|CBS|NBC|FOX|CW|PBS|MY|MyNetworkTV)'


def context_call(nm):
    """A call sign that is also a word ('WOOD', 'WRC', 'WAPA') counts when the name shows it is a station:
    in brackets, or next to a network name / channel number ('WOOD NBC 8', 'NBC 4 (WRC)')."""
    for m in re.finditer(r'\b([KW][A-Z]{2,3})\b', nm):
        c = m.group(1)
        st = US_STATIONS.get(c)
        if not st or not st['city'] or not st['num']:
            continue
        before, after = nm[:m.start()], nm[m.end():]
        if re.search(r'\(\s*$', before) and re.match(r'\s*\)', after) or \
                re.match(r'\s+' + NET_WORDS + r'\b', after) or re.search(r'\b' + NET_WORDS + r'\s*\d*\s*\(?\s*$', before):
            return m
    return None


def branded_local(name):
    """'ABC7 Chicago', 'KIRO 7 Seattle', 'WCPO 9 Cincinnati', 'Boston 25', 'FOX 29 Philadelphia' -> a local record,
    but only when the station table confirms which station it is."""
    nm = re.sub(r'\((?:[A-Z])\)|\s+Very\s+|\s+', ' ', name).strip()
    if re.search(r'\bLocal\b|\bNews$|^(CBSN|Spectrum)\b|\bPlus\b|\bXtra\b', nm):
        return None
    cands = []
    cm = find_callsign(nm) or context_call(nm)
    if not (cm and cm.group(1) in US_STATIONS):           # 'WOOD' is also a word, so the finder skips it
        cm = next((t for t in re.finditer(r'\b([KW][A-Z]{2,3})(?:-(?:TV|DT|CD|LD|LP))?\b', nm)
                   if t.group(1) in US_STATIONS and t.group(1) not in NOT_CALLSIGNS), None)
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


STATION_NETS = {'abc': 'ABC', 'cbs': 'CBS', 'nbc': 'NBC', 'fox': 'FOX', 'cw': 'CW', 'cwtv': 'CW', 'pbs': 'PBS',
                'gpb': 'PBS', 'mynetworktv': 'MyNetworkTV', 'mntv': 'MyNetworkTV', 'mytv': 'MyNetworkTV'}
STATION_NOISE = {'news', 'local', 'tv', 'network', 'virtual', 'channel', 'the', 'action', 'live', 'hd', 'fhd', 'sd',
                 'a', 'and', 'of', 'h', 'd', 'uhd', 'east', 'raw'}
BRAND_GENERIC = {'pbs', 'fox', 'abc', 'cbs', 'nbc', 'cw', 'my', 'public', 'media', 'broadcasting', 'television',
                 'network', 'news', 'channel', 'tv', 'state', 'the', 'and', 'of', 'educational', 'authority'}
NOT_STATION_RE = re.compile(r'\b(Sports?|Kids|Soul|Business|Weather|Comedy|Dateline|20/20|Forever|Gold|Justice|Localish|'
                            r'Vault|Retro|Drama|Documentar(?:y|ies)|Food|Genealogy|Nature|Travel|Antiques|Classics?|'
                            r'Movies?|Mystery|Plus|Now|LX|Life|Spark|Soccer|Racing|Golazo|Reality|Crime|Presents|'
                            r'Wild|Animals|History|Xtra|Extra|Reserve Channel|Roadshow|24/7)\b', re.I)
PLACE_INDEX = collections.defaultdict(set)
STATE_INDEX = collections.defaultdict(set)
for _c, _v in US_STATIONS.items():
    for _p in _v['places']:
        PLACE_INDEX[_pl(_p)].add(_c)
    if _v['state']:
        STATE_INDEX[re.sub(r'\s*\((?:U\.S\. )?state\)', '', _v['state']).lower()].add(_c)


# brands a station table cannot tell apart on its own (statewide PBS networks, call-sign nicknames)
BRAND_STATIONS = [
    (r'\bpbs ?12\b', 'KBDI'), (r'\bpbs ?39\b|\bpbs pa\b', 'WLVT'), (r'\bthirteen\b', 'WNET'), (r'\bnj ?pbs\b|\bpbs nj\b', 'WNJT'),
    (r'\bgbh\b', 'WGBH'), (r'\bsdpb\b', 'KUSD'), (r'\bapt\b', 'WBIQ'), (r'\bcet\b', 'WCET'), (r'\bbtpm\b', 'WNED'),
    (r'\bthink ?tv 14\b', 'WPTO'), (r'\bthink ?tv 16\b', 'WPTD'), (r'\bwest(?:ern)? reserve\b', 'WNEO'),
    (r'\btwin cities\b|\btpt\b', 'KTCA'), (r'\bpbs wisconsin\b(?!.*green bay)', 'WHA'), (r'\bcascade\b', 'KCTS'),
    (r'\barizona pbs\b|\bpbs phoenix\b', 'KAET'), (r'\barizona public media\b', 'KUAT'), (r'\balaska public\b', 'KAKM'),
    (r'\bmaine public\b', 'WMEB'), (r'\bvermont public\b', 'WETK'), (r'\bprairie public\b', 'KFME'),
    (r'\bpbs montana\b|\bmontana pbs\b', 'KUSM'), (r'\bwyoming pbs\b|\bpbs wyoming\b', 'KCWC'), (r'\bpbs utah\b', 'KUED'),
    (r'\bidaho public\b', 'KAID'), (r'\boregon public\b', 'KOPB'), (r'\boklahoma educational\b|\boeta\b', 'KETA'),
    (r'\bnebraska public\b', 'KUON'), (r'\bpbs arkansas\b|\barkansas pbs\b', 'KETS'), (r'\bmountain lake\b', 'WCFE'),
    (r'\bnashville public\b|\bnashville pbs\b', 'WNPT'), (r'\bnew england public\b', 'WGBY'),
    (r'\bpbs north carolina\b|\bpbs nc\b|\bunc-?tv\b', 'WUNC'), (r'\bozarks\b', 'KOZK'), (r'\bpanhandle\b', 'KACV'),
    (r'\brocky mountain\b', 'KRMA'), (r'\bscetv\b|\bsc etv\b', 'WRLK'), (r'\bvpm\b', 'WCVE'),
    (r'\bwest virginia public\b', 'WSWP'), (r'\bmississippi public\b|\bmpb\b', 'WMPN'),
    (r'\bmaryland public\b|\bmpt\b', 'WMPT'), (r'\b(?:lpb|louisiana public)\b.*\blafayette\b', 'KLPB'),
    (r'\blpb\b|\blouisiana public\b', 'WLPB'), (r'\bconnecticut public\b', 'WEDH'),
    (r'\bkansas public\b', 'KPTS'), (r'\bgeorgia public\b', 'WGTV'), (r'\bnorthern california public\b', 'KRCB'),
    (r'\bpbs albuquerque\b|\bnew mexico pbs\b', 'KNME'), (r'\bocean state media\b|\brhode island pbs\b|\bpbs rhode island\b', 'WPVD'),
    (r'\bgpb\b.*\balbany\b|\bgpb\b.*\btallahassee\b', 'WABW'), (r'\bgpb\b.*\baugusta\b', 'WCES'),
    (r'\bgpb\b.*\bchattanooga\b', 'WNGH'), (r'\bgpb\b.*\bcolumbus\b', 'WJSP'), (r'\bgpb\b.*\bmacon\b', 'WMUM'),
    (r'\bgpb\b.*\bsavannah\b', 'WVAN'), (r'\bgpb\b', 'WGTV'), (r'\bpeach ?tree\b', 'WPCH'), (r'\bpix ?11\b', 'WPIX'),
    (r'\bfox up\b', 'WLUC'), (r'\b(?:east )?tennessee pbs\b', 'WKOP'), (r'\bsouthern oregon pbs\b', 'KSYS'),
    (r'\bpioneer pbs\b', 'KWCM'), (r'\biowa pbs\b.*\bsioux city\b', 'KSIN'), (r'\biowa pbs\b', 'KDIN'),
    (r'\bfox kansas\b', 'KSAS'), (r'\bfox michiana\b', 'WSBT'), (r'\bmy ?24\b', 'WVTV'),
    (r'\bkentucky educational\b|\bket\b(?! ?2)', 'WKLE'), (r'\bnbc wash\b', 'WRC'), (r'\bcbs wash\b', 'WUSA'),
    (r'\babc wash\b', 'WJLA'), (r'\bfox wash\b', 'WTTG'), (r'^my ?9$', 'WWOR'),
]
BRAND_STATION_RES = [(re.compile(rx, re.I), c) for rx, c in BRAND_STATIONS]
CITY_CODES = {'NY': 'New York', 'LA': 'Los Angeles', 'DC': 'Washington', 'SF': 'San Francisco', 'NYC': 'New York',
              'WASH': 'Washington'}
STATE_CODES = {'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
               'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
               'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky', 'ME': 'Maine',
               'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
               'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire',
               'NJ': 'New Jersey', 'NM': 'New Mexico', 'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio',
               'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
               'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia',
               'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'}
STATE_ABBR = {**{v: k for k, v in STATE_CODES.items()}, 'Louisiana': 'LA', 'New York': 'NY'}  # not read as states
# market names used in two states: the state is added ('Portland, ME' / 'Portland, OR'). Markets that simply
# cross a state line (Cincinnati, Kansas City ...) keep the plain name.
CROSS_STATE_MARKETS = {'Cincinnati', 'Kansas City', 'Memphis', 'Nashville', 'Philadelphia', 'Providence', 'St. Louis',
                       'Washington DC'}
_city_states = collections.defaultdict(set)
for _c, _v in US_STATIONS.items():
    if _v.get('city') and _v.get('state'):
        _city_states[_v['city']].add(re.sub(r'\s*\((?:U\.S\. )?state\)', '', _v['state']).strip())
AMBIGUOUS_CITIES = {c for c, s in _city_states.items() if len(s) > 1 and c not in CROSS_STATE_MARKETS}


def us_city(call, fallback=None):
    """The station's market for display: 'Portland, ME' when another state has a Portland market too."""
    st = US_STATIONS.get(call or '') or {}
    city = st.get('city') or fallback
    state = re.sub(r'\s*\((?:U\.S\. )?state\)', '', st.get('state') or '').strip()
    if city in AMBIGUOUS_CITIES and STATE_ABBR.get(state):
        return f'{city}, {STATE_ABBR[state]}'
    return city


CLASSIFY_US_CITY_STATE.update({c: us_city(c) for c, v in US_STATIONS.items() if v.get('city') in AMBIGUOUS_CITIES})


def _nets(v):
    return {x.strip().replace('The CW', 'CW') for x in re.split(r'\s*/\s*', v['net'] or '') if x.strip()}


def _state_of(v):
    return re.sub(r'\s*\((?:U\.S\. )?state\)', '', v['state'] or '').lower()


def _place_hits(words):
    """Longest run of words that names a place ('Sioux City', 'Bay Area') -> (calls, the other words, states named)."""
    states = set()
    in_state = set()
    n = len(words)
    for size in range(min(n, 4), 0, -1):          # states first, so 'Iowa PBS Sioux City' keeps both
        for i in range(n - size + 1):
            span = ' '.join(words[i:i + size])
            if span in STATE_INDEX and span not in ('new york', 'washington'):    # those two are cities too
                states.add(span)
                in_state.update(range(i, i + size))
    for size in range(min(n, 4), 0, -1):
        for i in range(n - size + 1):
            if in_state & set(range(i, i + size)):                 # 'Carolina' inside 'North Carolina'
                continue
            span = ' '.join(words[i:i + size])
            key = _pl(span)
            if len(key) >= 3 and key in PLACE_INDEX:
                return PLACE_INDEX[key], words[:i] + words[i + size:], states
    try:                                       # 'CBS Savanna' (typo for Savannah)
        from rapidfuzz import process as rf, fuzz
        state_words = {w for i, w in enumerate(words) if i in in_state}
        for w in sorted(words, key=len, reverse=True):
            if len(w) >= 6 and w not in state_words:
                hit = rf.extractOne(_pl(w), list(PLACE_INDEX), scorer=fuzz.ratio, score_cutoff=92)
                if hit:
                    return PLACE_INDEX[hit[0]], [x for x in words if x != w], states
    except ImportError:
        pass
    return None, words, states


def find_station(name):
    """Which station a branded name means: 'FOX 10 Phoenix' -> KSAZ, 'Valley PBS Fresno' -> KVPT, 'PBS Thirteen' ->
    WNET, 'CBS Savanna' -> WTOC, 'Ocean State Media' -> WPVD. None unless one station clearly fits."""
    if NOT_STATION_RE.search(name):
        return None
    nm = re.sub(r'\((?:Virtual|A\d?|H|D|S|PM|PC|RK|TUBI|Prime)\)', ' ', name, flags=re.I)
    low = ' '.join(re.sub(r'[^a-z0-9 ]', ' ', nm.lower()).split())
    for rx, call in BRAND_STATION_RES:
        if rx.search(low):
            return call
    nm = re.sub(r'\b(ABC|CBS|NBC|FOX|PBS|CW|MY|My)(\d{1,2})\b', r'\1 \2', nm)
    nm = re.sub(r'\bThe CW\b', 'CW', nm).replace('/', ' ').replace('|', ' ').replace('-', ' ')
    toks = re.findall(r"[A-Za-z][A-Za-z.'&]*|\d{1,2}(?:\.\d)?\b", nm)
    net = num = None
    words, states = [], set()
    for i, t in enumerate(toks):
        tl = t.lower().strip(".'")
        if net is None and (tl in STATION_NETS or tl == 'my' and i + 1 < len(toks) and toks[i + 1][0].isdigit()):
            net = STATION_NETS.get(tl, 'MyNetworkTV')
            continue
        if num is None and re.fullmatch(r'\d{1,2}(?:\.\d)?', t):
            num = t
            continue
        if t in CITY_CODES:
            words.extend(CITY_CODES[t].lower().split())
            continue
        if t.isupper() and t in STATE_CODES:
            states.add(STATE_CODES[t].lower())
            continue
        if re.fullmatch(r'\d+', t) or tl in STATION_NOISE:
            continue
        words.append(tl.replace("'s", '').replace("'", ''))
    calls, rest, st2 = _place_hits(words)
    states |= st2
    if not net and calls is None:              # no network word and no place: not enough to call it a station
        return None
    allw = [w for w in words if w not in BRAND_GENERIC]
    bset = set(allw) | {a + b for a, b in zip(allw, allw[1:])}

    def net_ok(c):
        return not net or net in _nets(US_STATIONS[c])

    brand_cands = [c for c, v in US_STATIONS.items() if bset & v['brand'] and net_ok(c)]
    if calls is None:
        if not states and not bset:
            return None
        calls = [c for c, v in US_STATIONS.items() if _state_of(v) in states] if states else brand_cands
    cands = [c for c in calls if net_ok(c)] or \
        [c for c in calls if net and net != 'PBS' and net in US_STATIONS[c]['subs']]
    if states:
        cands = [c for c in cands if _state_of(US_STATIONS[c]) in states] or cands
    if num:
        with_num = [c for c in cands if US_STATIONS[c]['num'] == num or US_STATIONS[c]['num'].startswith(num + '.')
                    or (US_STATIONS[c]['subs'].get(net or '', '') or 'x').split('.')[0] == num]
        if not with_num and net and calls:        # 'MY24 Milwaukee': the table lost the station's network
            with_num = [c for c in calls if not US_STATIONS[c]['net'] and US_STATIONS[c]['num'] == num]
        cands = with_num or (cands if len(cands) == 1 and net else [])
    if not cands:
        cands = [c for c in brand_cands if len(bset & US_STATIONS[c]['brand']) >= (1 if net else 2)
                 and (not num or US_STATIONS[c]['num'].split('.')[0] == num)]

    def score(c):
        v = US_STATIONS[c]
        hit = len(bset & v['brand'])
        return (hit, -len(v['brand'] - bset) if hit else 0, _pl(v['city']) in {_pl(w) for w in words},
                bool(v['city']), c in known_calls(), bool(v['logo']))
    if cands and brand_cands and not any(score(c)[0] for c in cands):
        strong = [c for c in brand_cands if score(c)[0] >= 1 and (not num or US_STATIONS[c]['num'].split('.')[0] == num)]
        if len(strong) == 1:                     # 'Pioneer PBS Sioux Falls': the branding beats a loose place
            cands = strong
    if not cands:
        return None
    cands.sort(key=score, reverse=True)
    best = score(cands[0])
    if not net and best[0] < 2 and not (num and best[0] >= 1):     # no network word: the branding has to say it
        return None
    if len(cands) > 1 and best == score(cands[1]):
        return None
    return cands[0]


STREAM_SRC_RE = re.compile(r'\b(RK|TUBI|PLUTO|Prime|PRIME|PC|PM|S|Samsung|Roku|Free TV|Plex|Xumo)\b|Tubi TV', re.I)
STREAM_RES = [
    (re.compile(r'^(?:CBS News|CBSN)\s+(?P<place>(?!24/7|Local$|Now$|Live$)[A-Z][\w .\'-]*?)$', re.I), 'CBS', False),
    (re.compile(r'^NBC\s*(?P<num>\d{1,2})?\s+(?P<place>(?!News\b|LX\b|Sports\b)[A-Z][\w .\'/-]*?)\s+News$', re.I), 'NBC', False),
    (re.compile(r'^FOX\s*(?P<num>\d{1,2})?\s+Local\s+(?P<place>[A-Z][\w .\'/-]*?)$', re.I), 'FOX', False),
    (re.compile(r'^FOX\s*LOCAL\s+(?P<place>[A-Z][\w .\'/-]*?)$', re.I), 'FOX', False),
    (re.compile(r'^(?P<net>FOX|ABC|NBC|CBS)\s+(?P<place>[A-Z][\w .\'-]*?)\s+News\s*\((?P<call>[KW][A-Z]{2,3})\)$', re.I), None, False),
    (re.compile(r'^(?P<call>[KW][A-Z]{2,3})\s+(?:(?P<place>[A-Z][a-z][\w .\']*?)\s+)?(?P<num>\d{1,2})\+?\s+(?:Action\s+)?News$'), None, False),
    (re.compile(r'^(?P<call>[KW][A-Z]{2,3})\s+(?P<num>\d{1,2})\s+(?P<place>[A-Z][\w .\']+?)\s+News$'), None, False),
    (re.compile(r'^(?P<net>ABC|FOX|NBC|CBS)\s*(?P<num>\d{1,2})\s+(?P<place>[A-Z][\w .\'/-]*?)(?:\s+News)?$', re.I), None, True),
    (re.compile(r'^(?P<brand>Arizona\'s Family|First Alert 4|Channel 3 Eyewitness News|Atlanta News First|Boston 25 News|'
                r'Cleveland 19 News(?: Plus)?|Action News Jax)(?:\s+(?P<place>(?!News)[A-Z][\w .\']*))?(?:\s*\([^)]*\))?$', re.I),
     None, True),
]
NBC_OWNED = {'WNBC', 'KNBC', 'WMAQ', 'WCAU', 'WRC', 'KXAS', 'WTVJ', 'KNSD', 'KNTV', 'WBTS', 'WVIT', 'KNBC', 'WJAR',
             'KSNV', 'WNCN', 'KTVU'}
STREAM_STATIONS = {('CBS', 'texas'): 'KTVT', ('CBS', 'dallas'): 'KTVT', ('CBS', 'colorado'): 'KCNC',
                   ('CBS', 'denver'): 'KCNC', ('CBS', 'minnesota'): 'WCCO', ('CBS', 'bay area'): 'KPIX',
                   ('NBC', 'connecticut'): 'WVIT', ('NBC', 'bay area'): 'KNTV', ('NBC', 'sf bay area'): 'KNTV',
                   ('NBC', 'south florida'): 'WTVJ', ('NBC', 'la'): 'KNBC', ('FOX', 'minnesota'): 'KMSP',
                   ('ABC', 'north carolina'): 'WTVD', ('ABC', 'bay area'): 'KGO', ('', "arizona's family"): 'KTVK',
                   ('', 'first alert 4'): 'KMOV', ('', 'channel 3 eyewitness news'): 'WFSB',
                   ('', 'atlanta news first'): 'WANF', ('', 'boston 25 news'): 'WFXT', ('', 'cleveland 19 news'): 'WOIO',
                   ('', 'cleveland 19 news plus'): 'WOIO', ('', 'action news jax'): 'WJAX'}


def local_stream(name, rec):
    """A station's own 24/7 news stream on a free service ('CBS News Boston', 'NBC 4 New York News',
    'FOX 5 Local New York', 'KGUN 9 Tucson News'): not the broadcast channel, but it belongs with the locals."""
    nm = ' '.join(re.sub(r'\s*\|\s*', ' - ', name).split())
    fast = bool(STREAM_SRC_RE.search(rec.get('src', '') + ' ' + rec.get('orig', '')))
    for i, (rx, net, need_fast) in enumerate(STREAM_RES):
        m = rx.match(nm)
        if not m or (need_fast and not fast):
            continue
        g = m.groupdict()
        kind = net if i <= 3 else 'other'
        net = (net or g.get('net') or '').upper() or None
        place = ' '.join((g.get('place') or '').replace(' - ', ' ').split()) or None
        if place and NOT_STATION_RE.search(place):
            return None
        call = g.get('call')
        if place:
            place = re.sub(r'^SF\s+', '', place)                        # 'NBC SF Bay Area News'
            pc = re.match(r'^(.*?)\s*\b([KW][A-Z]{2,3})$', place)          # 'CBS News Richmond WTVR', 'ABC7 WWSB'
            if pc and pc.group(2) in US_STATIONS:
                call = call or pc.group(2)
                place = pc.group(1) or None
        brand = g.get('brand')
        key = (net or '', (place or brand or '').lower())
        call = call or STREAM_STATIONS.get(key) or STREAM_STATIONS.get(('', (brand or '').lower()))
        if not call:
            call = find_station(' '.join(x for x in (net, g.get('num'), place) if x))
        st = US_STATIONS.get(call or '')
        if not st and not place:
            return None
        if kind == 'NBC' and call not in NBC_OWNED:
            kind = 'other'
        if kind == 'other' and net == 'FOX' and call in FOX_LOCAL_PLACE:     # 'FOX 5 New York' on Roku = FOX LOCAL
            kind = 'FOX'
        if kind == 'other' and net == 'NBC' and call in NBC_OWNED and nm.endswith('News'):
            kind = 'NBC'
        given = re.sub(r'^CBSN\b', 'CBS News', nm) if not g.get('brand') else \
            ' '.join(x for x in (g['brand'], g.get('place')) if x)
        given = re.sub(r'\s*\([KW][A-Z]{2,3}\)\s*$', '', given)            # 'FOX Memphis News (WHBQ)'
        if len(given.split()) > 2:
            given = re.sub(r'\s+\b[KW][A-Z]{2,3}$', '', given)              # 'CBS 6 Richmond WTVR'
        given = re.sub(r'\b(\w+(?: \w+)?) \1\b', r'\1', given)            # 'ABC7 New York New York'
        given = re.sub(r'\s*-\s*', ' - ', given) if ' - ' in given else given
        return {'net': net or (st or {}).get('net'), 'call': call, 'num': g.get('num') or None,
                'st_num': (st or {}).get('num'), 'place': place, 'city': us_city(call, place) if st else place,
                'given': given, 'kind': kind, 'brand': g.get('brand')}
    return None


DIGINET_RE = re.compile(r'^(?:Retro TV|LMN|MeTV(?: Toons| Plus)?|Cozi(?: TV)?|Grit(?: TV)?|Laff|Bounce(?: TV)?|ION(?: TV| Plus| Mystery)?|'
                        r'Court TV|Antenna TV|Comet(?: TV)?|Charge!?|TBD|Dabl|Start TV|Heroes (?:&|and) Icons|H&I|Movies!|'
                        r'Catchy Comedy|Decades|Story Television|Quest|Get ?TV|Buzzr|Rewind TV|Defy(?: TV)?|TrueReal|'
                        r'Scripps News|Newsy|Merit Street|NewsNation|Ion Mystery|Bounce XL|Circle|Shop LC|Jewelry TV|'
                        r'QVC|HSN|Daystar|TBN|3ABN|Light TV|MeTV\+|Oxygen|Univision|Telemundo|UniMas|Estrella|AHC|MAV ?TV)$',
                        re.I)
BORDER_MARKETS = {'buffalo', 'detroit', 'seattle', 'bellingham', 'burlington', 'plattsburgh', 'spokane', 'great falls',
                  'minot', 'fargo', 'grand forks', 'watertown', 'presque isle', 'bangor', 'erie', 'cleveland'}


def brand_local(name, from_ca=False):
    """A local station named by brand ('FOX 10 Phoenix', 'Valley PBS Fresno', 'CBS NY', 'FOX 42') -> local record."""
    call = find_station(name)
    m = re.match(r'^(ABC|CBS|NBC|FOX|CW|The CW|PBS|My)\s?(\d{1,2})$', name.strip(), re.I)
    if not call and m:                         # 'FOX 42' alone: only when one station has that brand
        net = STATION_NETS.get(m.group(1).lower().replace('the ', ''), 'MyNetworkTV')
        hits = [c for c, v in US_STATIONS.items() if net in _nets(v) and v['num'].split('.')[0] == m.group(2)]
        if from_ca:                            # carried by a Canadian provider: the border-market station
            hits = [c for c in hits if _pl(US_STATIONS[c]['city']) in {_pl(b) for b in BORDER_MARKETS}] or hits
        if len(hits) == 1:
            call = hits[0]
    if not call or call in SPANISH_CALLS:
        return None
    net = None
    nm = re.search(r'\b(ABC|CBS|NBC|FOX|CW|PBS|MyNetworkTV|My)(?=\d|\b)', name, re.I)
    if nm:
        net = STATION_NETS.get(nm.group(1).lower(), 'MyNetworkTV')
    st = US_STATIONS.get(call) or {}
    if net and net != st.get('net') and net not in st.get('subs', {}) and net not in _nets(st or {'net': ''}):
        net = None                             # the table knows the station's network better
    return {'net': net, 'num': None, 'call': call, 'sub': None, 'city': st.get('city')}


def partial_local(name):
    """'FOX Virginia' -> 'US: Virginia - FOX', 'Cwtv Bozeman MT' -> 'US: Bozeman - CW', 'FOX 15' -> 'US: FOX 15':
    clearly a station, but the table cannot say which one."""
    nm = re.sub(r'\((?:Virtual|A\d?|H)\)', ' ', name, flags=re.I)
    nm = re.sub(r'\b(ABC|CBS|NBC|FOX|PBS|CW|MY|My)(\d{1,2})\b', r'\1 \2', nm)
    m = re.match(r'^(?:(?:A\d|The)\s+)?(?P<pre>[A-Z][\w .\'-]*?\s+)?(?P<net>ABC|CBS|NBC|FOX|CW|CWTV|PBS)\b\s*'
                 r'(?P<num>\d{1,2}(?:/\d{1,2})?)?\s*(?P<rest>[A-Z][\w .\'/-]*?)?\s*$', nm.strip(), re.I)
    if not m:
        return None
    net = STATION_NETS[m.group('net').lower()]
    words = ' '.join(x for x in (m.group('pre'), m.group('rest')) if x)
    words = re.sub(r'\s*\b(East|West|Pacific)$|^My\b', ' ', words.strip(), flags=re.I)  # 'NBC 10 East', 'My FOX 10'
    words = re.sub(r'\b(Network|TV|Channel|Virtual|Local|News)\b|^A\d\b|\b\d+\b', ' ', words)
    states = [STATE_CODES[w] for w in re.findall(r'\b([A-Z]{2})\b', words) if w in STATE_CODES]
    words = ' '.join(re.sub(r'\b[A-Z]{2}\b', ' ', words).split())
    place = None
    if words:
        key = _pl(words)
        if key in PLACE_INDEX or words.lower() in STATE_INDEX:
            place = words
        else:
            for w in words.split(' / ') + words.split():
                if _pl(w) in PLACE_INDEX and len(w) > 3:
                    place = w
                    break
        if not place:
            return None
    if place:
        place = smart_case(place) if place.isupper() else place
        if place in AMBIGUOUS_CITIES and states and STATE_ABBR.get(states[0]):
            place = f'{place}, {STATE_ABBR[states[0]]}'          # 'Lafayette, IN PBS 65' -> 'Lafayette, IN'
        return format_local('US', place, net)
    if m.group('num'):
        return f"US: {net} {m.group('num')}"
    return None


def us_station_in_ca(name):
    if re.match(r'^(CBC|CTV|Global|Citytv|City|CHCH|NTV|CHEK|Omni)\b', name, re.I):
        return False
    low = ' '.join(re.sub(r'[^a-z0-9 ]', ' ', name.lower()).split())
    if any(rx.search(low) for rx, _c in BRAND_STATION_RES):     # 'Peachtree TV' is WPCH Atlanta
        return True
    m = find_callsign(name)
    if m and m.group(1) in US_STATIONS:
        return True
    return bool(US_NET_START.match(name))


def _in_guide(cc, name):
    try:
        from epgmap import shared_index
        e = shared_index()
        from origin import FORCE, norm as onorm
        if onorm(name) in FORCE:                  # 'CNN International', 'Al Jazeera': international on purpose
            return False
        return any(e.trusted(i, h, name, cc) for i, h in e.lookup_all(cc, name, how=True)
                   if e.source_of.get(i) == 'US2' or (e.source_of.get(i) or '').startswith('OE_US'))
    except Exception:
        return False


def _forced(name):
    from origin import FORCE, norm as onorm
    return onorm(name) in FORCE


CA_BRAND_RE = re.compile(r'^(Sportsnet|TSN|CBC|CTV|Global|Citytv|RDS|Crave|Super Channel|Fight Network|Star$|'
                         r'The Shopping Channel|TSC$|'
                         r'Much|Bravo Canada|Teletoon|YTV|Treehouse|APTN|OMNI|CHCH|CP24|BNN)', re.I)
# channels in other languages that slip past the language rules (Sling's Desi/Arabic/Filipino/Chinese packs etc.)
NON_ENGLISH_NAMES = re.compile(r'^(?:SET Max|Sony KAL|Formosa TV|GMA Life(?: TV)?|PH GMA Life TV|BRTV International|MTV Beirut|'
                               r'JUS (?:Now|Punjabi|One|Hindi|24x7)|LB2(?: International)?|SBC(?: F)?|ON|TBN Nejat|N\+ ?foro|'
                               r'Spark TV Luz (?:&|and) Amor|Almajd.*|Charity TV|Dubai TV|Jordan TV|Roya TV|Sharjah TV|On Sports|'
                               r'Colors ?Cineplex|Colors ?Rishtey|India TV|Qtv|Record News|America TV|Top Bar[cç]a|'
                               r'Trace Brazuca|Johnny Hallyday|M2O Radio|MTV Norge|Stingray Adisq|Stingray Nostalgie|'
                               r'MC Tropicales|Music Choice Tropicales|Music Choice Mexicana|Music Choice Romances|'
                               r'Music Choice Rock Latino|Music Choice Today\'s Latin Hits|Music Choice Romantic Latin Pop|'
                               r'Music Choice Musica Urbana|Music Choice Vietnamese|Music Choice Filipino|Music Choice Brazilian Pop|'
                               r'Music Choice Italian Favorites|Music Choice Taste Of Italy|Vevo Regional Mexicano|'
                               r'[ÚU]n ?TV|Unis ?TV|TV5 ?Unis|NTV National|Kanshi TV|Radio Panjab|Mirchi Radio|Radio Sabras|'
                               r'Radio Spice Fm|Radio Sunrise|Sunrise Fm London|Asia Fm|Tropicales - Direct|'
                               r'BBC Radio Cymru(?: 2)?|BBC Radio Nan Gaidheal)\s*(?:\((?:[A-Z]{1,3}|[A-Z][a-z]+)\))?$', re.I)


US_STREAM_TAG = re.compile(r'\((?:S|RK|TUBI|Rakuten|PLUTO USA|FD|Prime|PM|PC|X|SP|A|D|H)\)|^US \(S\)|^TUBI\||^PRIME\|(?!.*UK)')


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
    if JUNK_RE.search(t) or re.fullmatch(r'[\W\d_]*', t) or re.search(r'(?:^|[:|]\s*)#{2,}.*#{2,}\s*$', t):
        rec['drop'] = 'test / placeholder feed'
        return rec
    mc = re.match(r"^MC\s+(.+?)\s*\((?:M)\)\s*$", t)
    if re.search(r'\bMC VIDEO\b', rec['src']):                # 'UK| MC VIDEO': Music Choice's video channels
        n, q = extract_quality(strip_tail_tags(re.sub(r'^UK\s*[:|]\s*', '', t)))
        n = re.sub(r'\s*-\s*Direct\s*$', '', n, flags=re.I)
        rec['cc'] = 'US'
        rec['kind'] = 'channel'
        rec['group'] = country_group('US', 'Music')
        n = re.sub(r'^Music Choice\s+', '', smart_case(n).replace("'S", "'s"))
        return finish(rec, 'US: Music Choice ' + n, q)
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
        if re.match(r'^(24/7\s*:?\s*)?(?:En Tout Cas|Les |La Petite Vie|Lance et Compte|Tout le monde en parle)\b', t, re.I):
            rec['drop'] = 'non-English (French series)'
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

    if re.search(r'\b(en\s+)?espa(?:n|ñ|)ol\b|\bSpanish\b|\bLatinos?\b|\bDeportes\b|\bEchorouk\b|\bEchourouk\b|'
                 r'^(?:US|USA)\s*:?\s*Mega TV\b|\bCanela\.?TV\b|\bTelediario\b|\bTeleCentro\b|\bTarima\b|'
                 r'\bNuestra Vision\b|\bCentroamerica\b|\bZona Futbol\b|\bTV Amor\b|\bAmor Real\b|\bPitufo\b|'
                 r'\bLaM[uú]sica\b|\bRemezcla\b|\bVas O No Vas\b|\bSony One Competencias\b|\bNat Geo Mundo\b|'
                 r'\bCin[eé]polis\b|\bTC Internacional\b|\bOro TV\b|\bPrimo TV\b|\bFOX en Tubi\b', t, re.I):
        rec['drop'] = 'non-English (Spanish version)'
        return rec
    if NON_ENGLISH_NAMES.match(re.sub(r'^(?:[A-Z]{2,4}\s*[:|]\s*|\((?:US|USA|UK)\)\s*(?:\([^)]*\)\s*)*|'
                                      r'(?:US|USA|UK|UKSD|UKFHD|INT)\s+(?:\([^)]*\)\s*)?)', '', strip_tail_tags(t)).strip()):
        rec['drop'] = 'non-English'
        return rec
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
    t = re.sub(r'^PEA\s*(\d{1,3})\s*:\s*', lambda x: f'Peacock {int(x.group(1)):02d}: ', t)   # 'PEA 01: Game 3 ...'
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
    name = re.sub(r'^(?:\+1s|s)\s*:\s*', '', name)                 # 'UK +1s : Channel 4+1'
    qtag = next((x[2:] for x in info['tags'] if x.startswith('Q:')), None)
    name = re.sub(r'\b(4K|UHD)\s*\+', r'\1', name)       # 'FOX UHD/4K+ (EVENT ONLY)': not 'FOX+'
    name = re.sub(r'\s*\(event only\)', '', name, flags=re.I).strip()
    if re.search(r'\b(?:4K|UHD)\s*\+', raw):
        name = re.sub(r'\s*\+$', '', name)
    if re.fullmatch(r'West\s+IPLL? Only', name, re.I):     # a provider's placeholder line, not a channel
        rec['drop'] = 'test / placeholder feed'
        return rec
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

    from_ca = False
    if cc == 'CA' and us_station_in_ca(name):      # Buffalo / Seattle / Detroit stations carried in Canada
        cc = rec['cc'] = 'US'
        src = 'US Locals & Regional'
        from_ca = True
    if cc == 'US':
        name = re.sub(r'\b([KW][A-Z]{3})(TV|DT|LD|CD)\b', r'\1-\2', name)     # 'KDKATV' -> 'KDKA-TV'
        # 'CBS (KRQE Albuquerque NM)', 'CBS (WJZ– Baltimore MD)', 'FOX (MY WZDX Huntsville AL)' -> 'Albuquerque (KRQE)'
        m_cc = re.match(r"^(?:ABC|CBS|NBC|FOX|CW|PBS|MY|MyNetworkTV)\s*\(\s*(?:MY\s+)?([KW][A-Z]{2,3})(?:-?(?:TV|DT|LD|CD))?"
                        r"\s*[–—-]?\s*(?:TV\s*[–—-]\s*)?([A-Za-z][A-Za-z .'/-]+?)\s*\)$", name)
        if m_cc and m_cc.group(1) in US_STATIONS:
            city = re.sub(r'\s+(?:[A-Z]{2}|' + '|'.join(STATE_NAMES_TITLE) + r')$', '', m_cc.group(2).strip())
            name = f'{city.title() if city.isupper() else city} ({m_cc.group(1)})'
        name = re.sub(r'\(([KW][A-Z]{3})D\)', lambda x: f'({x.group(1)})' if x.group(1) in US_STATIONS else x.group(0),
                      name)                                           # 'CBS (KDKAD)' -> 'CBS (KDKA)'
        m_pc = re.match(r"^(ABC|CBS|NBC|FOX|CW|PBS)\s*\(([A-Z][A-Za-z .'-]+)\)$", name)
        if m_pc and m_pc.group(2) not in ('East', 'West', 'Pacific', 'National') and \
                not re.fullmatch(r'[KW][A-Z]{2,3}(-[A-Z]{2})?', m_pc.group(2)):   # 'CBS (Buffalo)', not 'CBS (KBOI)'
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'local'
            rec['local'] = {'net': m_pc.group(1), 'num': None, 'call': None, 'sub': None, 'city': m_pc.group(2)}
            rec['q_pending'] = q
            return finish(rec, format_local('US', m_pc.group(2), m_pc.group(1)), q)
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
        ls = local_stream(norm_feed_words(smart_case(name)), rec)
        if ls:                                 # a station's 24/7 news stream: with the locals, city first
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'channel'
            rec['stream'] = ls
            rec['lookup'] = ls['given']
            return finish(rec, f"US: {ls['city']} - {ls['given']}" if ls['city'] else f"US: {ls['given']}", q)
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
        elif re.fullmatch(r'[KW][A-Z]{2,3}', name) and src in LOCAL_SRC | {'United States', 'US Entertainment'} and \
                (name not in NOT_CALLSIGNS or (US_STATIONS.get(name) or {}).get('num')):
            name = f'({name})'
        diginet = DIGINET_RE.match(re.sub(r'\s*\([KW]?[A-Z]{2,4}(?:-[A-Z]{2})?\)\s*$', '', name))
        loc = None if diginet else \
            parse_local(name, loose=src in LOCAL_SRC or bool(bracket) or bool(m_call) or name.startswith('(')) or \
            branded_local(name) or brand_local(name, from_ca)
        if diginet:                            # 'Retro TV (KBEH)', 'LMN (LMS)': the network, carried by some station
            name = re.sub(r'\s*\([KW]?[A-Z]{2,4}(?:-[A-Z]{2})?\)\s*$', '', name)
        if not loc and not NOT_STATION_RE.search(name):
            part = partial_local(name)
            hint = re.match(r'^([KW][A-Z]{2,3})(?:-(?:TV|DT|LD|CD))?\.us\d?$', c['attrs'].get('tvg-id', ''))
            pnet = re.search(r'\b(ABC|CBS|NBC|FOX|CW|PBS)\b', name, re.I)
            if part and hint and pnet and hint.group(1) in US_STATIONS and \
                    STATION_NETS.get(pnet.group(1).lower()) in _nets(US_STATIONS[hint.group(1)]):
                st_h = US_STATIONS[hint.group(1)]         # 'FOX 29' whose guide id is WFLX.us: that station
                num_h = re.search(r'\b(\d{1,2})\b', name)
                if not num_h or st_h['num'].split('.')[0] == num_h.group(1):
                    loc = {'net': STATION_NETS.get(pnet.group(1).lower()), 'num': None, 'call': hint.group(1),
                           'sub': None, 'city': st_h['city']}
                    part = None
            if part:                           # 'FOX Virginia', 'PBS 65 Wheeling': a station, but which one is unknown
                rec['group'] = country_group('US', 'Locals')
                rec['kind'] = 'channel'
                return finish(rec, part, q)
        if loc and loc.get('call') in SPANISH_CALLS:
            rec['drop'] = 'non-English (Spanish-language local station)'
            return rec
        if loc and not re.search(r'\b(News Live|Localish|Telemundo|Univision)\b', name, re.I):
            rec['local'] = loc
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'local'
            rec['q_pending'] = q
            return rec
    if cc == 'CA' and CA_FRENCH_RE.search(name):
        rec['drop'] = 'non-English (French-language Canadian channel)'
        return rec
    if cc == 'CA':
        cs = ca_stream(norm_feed_words(smart_case(name)))
        if cs:                                 # a station's local news stream: with the locals, city first
            rec['group'] = country_group('CA', 'Locals')
            rec['kind'] = 'channel'
            rec['lookup'] = cs[2]
            return finish(rec, f'CA: {cs[0]} - {cs[1]}', q)
    if cc == 'CA' and re.match(r'^(?:CBC|CTV|Global|Citytv|City)\b.*\bNews\b', name, re.I):
        rec['group'] = country_group('CA', 'News')
        return finish(rec, f'CA: {norm_feed_words(smart_case(name))}', q)
    if cc == 'CA' and re.sub(r'[\s.-]+', '', re.sub(r'\s*\b(HD|FHD|SD)$', '', name)).upper() in CA_HOME:   # 'CF JC'
        call = re.sub(r'[\s.-]+', '', re.sub(r'\s*\b(HD|FHD|SD)$', '', name)).upper()
        rec['group'] = country_group('CA', 'Locals')
        rec['kind'] = 'ca-local'
        h = CA_HOME[call]
        return finish(rec, _ca_fmt(h['city'], h['net'], call, h['num']), q)
    if cc == 'CA':
        hint = ca_id_hint(name, c['attrs'].get('tvg-id', ''))
        if hint:                               # 'CTV 2 HD' whose guide id says 'CTV2 Vancouver Island' -> CIVI
            rec['group'] = country_group('CA', 'Locals')
            rec['kind'] = 'ca-local'
            return finish(rec, hint, q)
    if cc == 'CA' and CA_LOCAL_RE.match(name) and (CA_PLACES.search(name) or
                                                   re.match(r'^(CHCH|CHEK|NTV|Yes TV|Yes)\b(?!\s*\+|\+)', name, re.I)):
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

    if cc in ('US', 'CA'):
        rl = regional_local(norm_feed_words(smart_case(name)), cc)
        if rl:                                 # 'News 12 Brooklyn', 'WeatherNation Boston', 'Cable 14 Hamilton'
            place, given = rl
            rec['group'] = country_group(cc, 'Locals')
            rec['kind'] = 'channel'
            rec['lookup'] = given
            rec['lookups'] = [name]
            b = re.match(r'^(WeatherNation|Local Now|Spectrum News|News 12|Beach TV)\b', given)
            rec['logo_brand'] = b.group(1) if b else None      # the brand's logo when the edition has none
            return finish(rec, f'{cc}: {place} - {given}', q)
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
    named_country = re.search(r'\b(UK|USA|Canada|Australia|NZ|New Zealand|Ireland)\b', title)
    if home != cc and cc == 'US' and not _forced(title) and not named_country and (
            home == 'INT' and _in_guide(cc, title) or            # 'Oxygen' in a US group: the US guide has it
            home in ('UK', 'CA', 'AU', 'NZ', 'IE') and US_STREAM_TAG.search(rec['orig']) and   # 'Wonder' on US Sling
            not CA_BRAND_RE.match(title)):
        home = cc
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


# Channels for one city or area that are not broadcast stations: regional cable news (News 12, Spectrum News),
# the local editions of WeatherNation / Local Now, stations' own streaming brands and community channels.
# They sit with the locals, area first: 'US: Brooklyn - News 12 Brooklyn'. (regex, area, display name)
SPECTRUM_AREA = {'central ny': 'Syracuse', 'so cal': 'Los Angeles', 'socal': 'Los Angeles', 'rotx': 'Texas',
                 'cleveland/akron': 'Cleveland', 'toledo/lima': 'Toledo', 'coastal': 'Coastal North Carolina',
                 'carolinas coastal': 'Coastal North Carolina', 'mountain': 'Western North Carolina',
                 'carolinas mountain': 'Western North Carolina', 'capital region': 'Albany',
                 'albany capital region': 'Albany', 'dallas ft worth': 'Dallas', 'dallas -ft worth': 'Dallas'}
SPECTRUM_NAME = {'Rotx': 'Texas', 'So Cal': 'SoCal', 'Albany Capital Region': 'Albany', 'Carolinas Mountain': 'Mountain',
                 'Carolinas Coastal': 'Coastal', 'Dallas Ft Worth': 'Dallas', 'Dallas -Ft Worth': 'Dallas',
                 'Milwaukee': 'Wisconsin'}
REGIONAL_LOCALS = [
    (r'^News ?12(\+?) (?:The )?(Bronx)$', lambda m: ('Bronx', f'News 12{m[1]} The Bronx')),
    (r'^News ?12(\+?) (Brooklyn|Connecticut|Hudson Valley|Long Island|New Jersey|Westchester|New York)$',
     lambda m: (m[2], f'News 12{m[1]} {m[2]}')),
    (r'^(?:Spectrum )?Bay News 9(?: Tampa(?: Bay)?)?$', lambda m: ('Tampa', 'Spectrum Bay News 9')),
    (r'^Spectrum News 13$|^News 13 Orlando$', lambda m: ('Orlando', 'Spectrum News 13')),
    (r'^(?:Spectrum News(?: 1)?(?: -)? )?NY ?1$', lambda m: ('New York', 'Spectrum News NY1')),
    (r'^(?:Spectrum News )?NECN$|^NBC Boston News \(NECN\)$|^(?:NBC )?New England Cable News(?: \(NECN\))?(?: Boston)?$',
     lambda m: ('Boston', 'Spectrum News NECN')),
    (r'^Spectrum News?(?: 1)?(?: \((?:Carolinas|Kentucky|MA|New York|NY)\))?(?: -)? (?!1$|HD$)(.+)$', '_spectrum'),
    (r'^Local Now (?!HD$)(.+)$', lambda m: (m[1], f'Local Now {m[1]}')),
    (r'^WeatherNation (?!TV$)(.+)$', lambda m: (re.split(r'/| Durham$', m[1])[0].replace('Washington D.C.', 'Washington DC')
                                                 .replace('Ft. Worth', 'Fort Worth'), f'WeatherNation {m[1]}')),
    (r'^(?:The )?Atlanta Channel$', lambda m: ('Atlanta', 'Atlanta Channel')),
    (r'^DC Council Channel$', lambda m: ('Washington DC', 'DC Council Channel')),
    (r'^District of Columbia Network$|^DCN$', lambda m: ('Washington DC', 'District of Columbia Network')),
    (r'^(?:NO TV )?New Orleans (?:TV|Television)$|^NOTV$', lambda m: ('New Orleans', 'New Orleans TV')),
    (r'^LA ?(?:Local )?36$', lambda m: ('Los Angeles', 'LA36')),
    (r'^WCCA(?: TV)?(?: \(?Worcester\)?)?$', lambda m: ('Worcester', 'WCCA TV')),
    (r'^Red Apple 21\b.*$', lambda m: ('Fairfax', 'Red Apple 21')),
    (r'^WNYC$', lambda m: ('New York', 'WNYC')),
    (r'^Beach TV Panama City$', lambda m: ('Panama City', 'Beach TV Panama City')),
    (r'^Beach TV Key West (?:& )?(?:The )?Florida Keys$', lambda m: ('Key West', 'Beach TV Key West & Florida Keys')),
    (r'^Beach TV Myrtle Beach (?:& )?(?:The )?Grand Strand$', lambda m: ('Myrtle Beach', 'Beach TV Myrtle Beach & Grand Strand')),
    (r'^Beach TV Florida (?:& )?Alabama$', lambda m: ('Florida & Alabama', 'Beach TV Florida & Alabama')),
    (r'^Cable ?14(?: Hamilton)?$', lambda m: ('Hamilton', 'Cable 14')),
]
REGIONAL_LOCAL_RES = [(re.compile(rx, re.I), f) for rx, f in REGIONAL_LOCALS]
# the same names as the stations' markets where a city name is used in two states
REGIONAL_STATE = {'Springfield': 'Springfield, MA', 'Rochester': 'Rochester, NY', 'Albany': 'Albany, NY',
                  'Columbus': 'Columbus, OH', 'Wilmington': 'Wilmington, NC', 'Portland': 'Portland, OR',
                  'Richmond': 'Richmond, VA', 'Hartford': 'Hartford, CT', 'Charleston': 'Charleston, SC'}


def regional_local(name, cc):
    nm = re.sub(r'\s*\b(HD|FHD|SD|4K)$', '', name).strip()
    for rx, f in REGIONAL_LOCAL_RES:
        m = rx.match(nm)
        if not m:
            continue
        if f == '_spectrum':
            area = ' '.join(m[1].replace(' - ', ' ').split())
            area = re.sub(r'^\([^)]*\)\s*|\s+(?:Bk|Backup)$', '', area)                   # '(New York) Rochester'
            if re.match(r'^(?:SportsNet|Sports|News$|Radar|XCast|Originals)', area, re.I):
                return None
            area = re.sub(r'\s+Texas$', '', area)                      # 'El Paso Texas'
            label = SPECTRUM_NAME.get(area, area)
            place = SPECTRUM_AREA.get(area.lower(), label)
            return (REGIONAL_STATE.get(place, place), f'Spectrum News 1 {label}') if cc == 'US' else None
        place, given = f(m)
        if cc == 'CA' and place != 'Hamilton' or cc == 'US' and place == 'Hamilton':
            return None
        return REGIONAL_STATE.get(place, place), given
    return None


STREAM_RENAMED = {'CBS News Dallas': 'CBS News Texas', 'CBS News Denver': 'CBS News Colorado'}
# how FOX's own stations name their FOX LOCAL streams
FOX_LOCAL_PLACE = {'KMSP': 'Minnesota', 'WTVT': 'Tampa Bay', 'KDFW': 'Dallas-Fort Worth', 'WTTG': 'Washington DC',
                   'KTVU': 'San Francisco', 'WAGA': 'Atlanta', 'KTBC': 'Austin', 'WJBK': 'Detroit', 'KRIV': 'Houston',
                   'WTXF': 'Philadelphia', 'WFLD': 'Chicago', 'WOFL': 'Orlando', 'KTTV': 'Los Angeles',
                   'WNYW': 'New York', 'KSAZ': 'Phoenix', 'KCPQ': 'Seattle', 'WITI': 'Milwaukee', 'WHBQ': 'Memphis',
                   'WOGX': 'Gainesville'}


def stream_names(recs):
    """One name per station news stream: 'FOX LOCAL New York' (Pluto), 'FOX 5 LOCAL New York' (Samsung) and
    'FOX 5 New York' (Roku) are the same stream -> 'US: New York - FOX 5 Local New York'."""
    groups = collections.defaultdict(list)
    for r in recs:
        ls = r.get('stream')
        if ls and not r['drop']:
            k = ls['call'] or (ls['place'] or '').lower()
            if ls['kind'] == 'other' and not ls['call']:  # one stream per station: 'ABC Denver News' = 'KMGH Denver 7+ News'
                k = (k, re.sub(r'[^a-z0-9]', '', ls['given'].lower()))
            groups[(ls['kind'], k)].append(r)
    for (kind, _k), rs in groups.items():
        variants = [r['stream'] for r in rs]
        with_num = [v for v in variants if v['num']]
        places = collections.Counter(v['place'] for v in (with_num or variants) if v['place'])
        place = max(places.items(), key=lambda kv: (kv[1], len(kv[0]) > 2, len(kv[0])))[0] if places else None
        num = (with_num[0]['num'] if with_num else None)
        if kind == 'FOX':
            num = variants[0]['st_num'] or num
            local_places = collections.Counter(v['place'] for v in variants if v['place'] and 'Local' in v['given'])
            place = max(local_places.items(), key=lambda kv: (kv[1], len(kv[0])))[0] if local_places else place
            place = FOX_LOCAL_PLACE.get(variants[0]['call'] or '', place)
            disp = ' '.join(x for x in ('FOX', (num or '').split('.')[0], 'Local', place) if x)
        elif kind == 'NBC':
            disp = ' '.join(x for x in ('NBC', num, place, 'News') if x)
        elif kind == 'CBS':
            disp = f'CBS News {place}'
        else:
            v0 = variants[0]
            st0 = US_STATIONS.get(v0['call'] or '') or {}
            net0 = next((v['net'] for v in variants if v['net'] in ('ABC', 'CBS', 'NBC', 'FOX', 'CW')), None)
            if v0['call'] and st0.get('num') and st0.get('city') and net0 and not any(v.get('brand') for v in variants):
                # one pattern for every station's stream, whichever service carries it: 'KGUN 9 Tucson News' (Roku)
                # and 'ABC Tucson News' (Prime) -> 'ABC 9 Tucson News'
                disp = f"{net0} {st0['num'].split('.')[0]} {st0['city']} News"
            else:                                 # the commonest spelling; a tie goes to one without a call sign
                cnt = collections.Counter(v['given'] for v in variants)
                disp = max(cnt.items(), key=lambda kv: (kv[1], not re.match(r'[KW][A-Z]{2,3}\b', kv[0]), -len(kv[0]),
                                                        kv[0]))[0]
        disp = STREAM_RENAMED.get(disp, disp)
        city = variants[0]['city']
        alts = [disp] + [v['given'] for v in variants]           # every spelling, for the guide / logo lookup
        if kind == 'FOX' and place:
            alts += [f'FOX LOCAL {place}', f"FOX {(num or '').split('.')[0]} {place}".replace('  ', ' ')]
        if kind == 'NBC' and place:
            alts += [f'NBC {place} News', f'NBC {num} {place} News' if num else '']
        if kind == 'CBS' and place:
            alts += [f'CBSN {place}']
        alts = [a for a in dict.fromkeys(alts) if a]
        st = US_STATIONS.get(variants[0]['call'] or '') or {}
        cbs_own = kind == 'CBS'                    # 'CBS News Boston' has its own logo in tv-logos
        for r in rs:
            r['lookups'] = alts
            r['lookup'] = disp
            if st.get('logo') and not cbs_own and kind != 'NBC':
                r['station_logo'] = st['logo']
            q = r.get('quality')
            r['name'] = (f'US: {city} - {disp}' if city else f'US: {disp}') + (f' {q}' if q else '')
            r['ident'] = ('STREAM', kind, _k)


def process_all(entries):
    recs = [process_entry(c) for c in entries]
    stream_names(recs)
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
    for r in recs:                               # a call sign that is not a station: 'NBC: WIV MILWAUKEE WTMJ', 'KDKAD'
        loc = r.get('local')
        real = lambda c: c in US_STATIONS and bool(US_STATIONS[c]['city']) and bool(US_STATIONS[c]['num'])
        if loc and loc.get('call') and not real(loc['call']) and r.get('kind') == 'local':
            other = [c for c in re.findall(r'\b([KW][A-Z]{2,3})', r['orig'].upper()) if real(c)]
            if real(loc['call'][:4]):
                loc['call'] = loc['call'][:4]
            elif other:
                loc['call'] = other[0]
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
