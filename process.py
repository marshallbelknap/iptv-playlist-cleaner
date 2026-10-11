# -*- coding: utf-8 -*-
"""Apply the rules to every entry. Two passes so local stations can share city names."""
import re
import collections
from rules import (SPANISH_CALLS, NOT_CALLSIGNS, US_STATES, basic_clean, extract_quality, strip_tail_tags, smart_case, is_non_english, JUNK_RE,
                   country_group, sports_group, PPV_GROUP, G247, ADULT_GROUP, COUNTRY_ORDER)
from classify import (CHANNEL_SRC, SRC_CATEGORY, LOCAL_SRC, LEAGUE_SRC, SERVICE_SRC, DROP_SRC, LEAGUE_GROUP,
                      EVENTS_TO_PPV, resolve_label, parse_slot, slot_name, parse_country_name, display_label,
                      classify_category, parse_local, local_display, fix_mojibake, clean_event)

CHANNEL_LIKE_LABELS = {'NFL', 'NBA', 'MLB', 'NHL', 'WNBA', 'MLS', 'F1', 'EPL', 'UFC', 'Red Bull TV',
                       'Tennis', 'Golf', 'Soccer', 'PPV', 'Fubo Sports', 'GAA'}
LEAGUE_CHANNEL_RE = re.compile(r'^(NFL|NBA|MLB|NHL|WNBA)\b(?! ?G\b)')

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
    p = parse_slot(t)[0]
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


def process_entry(c):
    src = c['attrs'].get('group-title', '')
    url = c.get('url', '')
    raw = c['title']
    rec = {'src': src, 'orig': raw, 'drop': None, 'group': None, 'name': None, 'cc': None,
           'kind': None, 'quality': None, 'local': None}
    if '/series/' in url:
        rec['drop'] = 'VOD episode'
        return rec
    t = basic_clean(fix_mojibake(raw))
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
    if src == '24/7 Streams':
        rec['group'] = G247
        rec['kind'] = '247'
        if is_non_english(t) or re.match(r'^(MX|ES|AR|IN|FR)\b', t) or re.search(r'\((FR|ES|DE|IT|PT|NL)\)\s*$', t):
            rec['drop'] = 'non-English'
            return rec
        n = re.sub(r'^24/7\s*:?\s*', '', t)
        n = re.sub(r'^(?:M\d|VIBE|MC|US)\s*[:|]?\s*', '', n)
        n = strip_tail_tags(n)
        n = re.sub(r'\bSeason (\d+)\b', lambda m: f'S{int(m.group(1)):02d}', n)
        n = re.sub(r'\bS(\d)\b', r'S0\1', n)
        n, q = extract_quality(n)
        return finish(rec, '24/7 ' + smart_case(tidy(n)), q)

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

    if is_non_english(t):
        rec['drop'] = 'non-English'
        return rec
    # --- channel sources: some carry event slots too ------------------------------
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

    if cc == 'US':
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
            return finish(rec, f'US: {m_cw.group(1)} {m_cw.group(2)}, {m_cw.group(3)}', q)
        m_call = re.match(r'^([KW][A-Z]{2,3})(?:-?(?:TV|DT|LD|CD))?\s+([A-Z][A-Za-z .\'/-]+)$', name)
        if m_call and m_call.group(1) not in NOT_CALLSIGNS and not re.search(r'\bNews\b', name):
            name = f'{m_call.group(2)} ({m_call.group(1)})'
        elif re.fullmatch(r'[KW][A-Z]{2,3}', name) and name not in NOT_CALLSIGNS and src in LOCAL_SRC | {'United States', 'US Entertainment'}:
            name = f'({name})'
        loc = parse_local(name, loose=src in LOCAL_SRC or bool(bracket) or bool(m_call) or name.startswith('('))
        if loc and loc.get('call') in SPANISH_CALLS:
            rec['drop'] = 'non-English (Spanish-language local station)'
            return rec
        if loc and not re.search(r'\b(News Live|Localish|Telemundo|Univision)\b', name, re.I):
            rec['local'] = loc
            rec['group'] = country_group('US', 'Locals')
            rec['kind'] = 'local'
            rec['q_pending'] = q
            return rec
    if cc == 'CA' and CA_LOCAL_RE.match(name) and CA_PLACES.search(name):
        rec['group'] = country_group('CA', 'Locals')
        nm = norm_feed_words(smart_case(name))
        return finish(rec, f'CA: {nm}', q)

    cat = classify_category(name, src)
    if cc == 'INT' and cat not in ('Sports', 'News'):
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
            c = loc['city']
            score = 2 if not c.isupper() else 1
            cities[loc['call']][c] += score
    for r in recs:
        loc = r.get('local')
        if not loc:
            continue
        city = None
        if cities.get(loc['call']):
            city = cities[loc['call']].most_common(1)[0][0]
        # also reuse a channel number seen elsewhere for this call sign
        finish(r, 'US: ' + local_display(loc, city), r.pop('q_pending', None))
    return recs
