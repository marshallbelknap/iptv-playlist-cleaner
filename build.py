# -*- coding: utf-8 -*-
"""Clean an IPTV M3U playlist.

usage: python3 build.py INPUT(.m3u path or http URL) OUTPUT.m3u [REPORT.csv]

Re-run it against the live provider URL whenever you want fresh event names;
only names, groups, logos and guide ids change - stream URLs are copied untouched.
"""
import csv
import json
import os
import re
import sys
import urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from parse import parse                      # noqa: E402
from process import process_all              # noqa: E402
from epgmap import EpgIndex, EPG_URLS, SOURCES, family as epg_family  # noqa: E402
from logo_pick import Picker                 # noqa: E402
from adapt_p2 import adapt, is_pipe_style    # noqa: E402
from rules import COUNTRY_ORDER, CATEGORY_ORDER, PPV_GROUP, G247, ADULT_GROUP  # noqa: E402
from canon import Namer, split_name, clean as canon_clean  # noqa: E402

DATA = os.environ.get('CLEANER_DATA', os.path.join(HERE, 'data'))
WEAK_LOGOS = {'e.png', 'black.png', 'gaanbangla.png', 'syracusenynbcwstm.png', 'classicmovies.png',
              'starzencorewesternswest.png', 'starzencoreactionwest.png', 'starzencoresuspensewest.png'}
SPORTS_ORDER = ['NFL', 'NCAAF', 'NBA', 'WNBA', 'NCAAB', 'MLB', 'MiLB', 'NHL', 'CHL', 'Hockey (Other)',
                'MLS', 'EPL', 'EFL', 'SPFL', 'UEFA', 'La Liga', 'Serie A', 'Ligue 1', 'Soccer (Other)',
                'F1', 'MotoGP', 'Golf', 'Tennis', 'Darts', 'GAA', 'NCAA (Other)', 'Other',
                'ESPN+', 'Peacock', 'Paramount+', 'MAX', 'Prime Video', 'DAZN', 'TSN+', 'Sportsnet+', 'FloSports']


def group_rank(g):
    if ' | ' in g and not g.startswith('Sports | '):
        cc, cat = g.split(' | ', 1)
        ci = COUNTRY_ORDER.index(cc) if cc in COUNTRY_ORDER else len(COUNTRY_ORDER)
        ki = CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else 9
        return (0 if cc == 'US' else 2 if cc != 'INT' else 3, ci, ki, g)
    if g.startswith('Sports | '):
        lab = g[9:]
        return (1, SPORTS_ORDER.index(lab) if lab in SPORTS_ORDER else 99, 0, g)
    if g.startswith('24/7'):
        order = ['24/7 | TV Shows', '24/7 | Movies', '24/7 | Actors & Directors', '24/7 | Kids & Animation']
        return (4, 1, order.index(g) if g in order else 9, g)
    return (4, [PPV_GROUP, G247, ADULT_GROUP].index(g) if g in (PPV_GROUP, G247, ADULT_GROUP) else 9, 0, g)


def natural(s):
    return [(0, int(t), '') if t.isdigit() else (1, 0, t.lower()) for t in re.split(r'(\d+)', s) if t]


QUAL_RANK = {'4K': 0, 'FHD': 1, 'HD': 2, None: 3, 'SD': 4}


def sort_key(r):
    base = re.sub(r' (4K|FHD|HD|SD)$', '', r['name'])
    if r['kind'] == 'event':
        m = re.match(r'^(.*?) (\d+)(?::|$)', base)
        if m:
            return (natural(m.group(1)), int(m.group(2)), 0, base.lower())
    return (natural(base), 0, QUAL_RANK.get(r['quality'], 3), '')


def esc(s):
    return (s or '').replace('"', "'").replace('\n', ' ')


def clean_for_lookup(name):
    nm = re.sub(r'^[A-Z]{2,3}: ', '', name)
    return re.sub(r' (4K|FHD|HD|SD)$', '', nm)


SHIFT_SEP = '~'      # 'SkyCrime.uk~+60' = that channel's guide moved 60 minutes later (built by guide.py)
CALL_IN_NAME = re.compile(r'\b([KW][A-Z]{2,3})(?:-(?:DT|TV|LD|CD|CA)(\d)?)?\b')
WEST_WORDS = re.compile(r'\s*\b(West|Pacific)\b', re.I)


def channel_guide(epg, cc, nm):
    """Guide id for a regular channel, borrowing (and time-shifting) the main feed when needed."""
    hit = epg.lookup(cc, nm)
    if hit:
        return hit
    if re.search(r'\+1\b', nm):                       # 'Crime Inv +1' -> 'Crime Inv' one hour later
        base = epg.lookup(cc, re.sub(r'\s*\+1\b', '', nm).strip())
        if base:
            return f'{base}{SHIFT_SEP}+60'
    if cc in ('US', 'CA') and WEST_WORDS.search(nm):   # 'Cinemax Hits West' -> East feed three hours later
        base = epg.lookup(cc, WEST_WORDS.sub('', nm).strip())
        if base:
            return f'{base}{SHIFT_SEP}+180'
    if cc == 'US':                                     # 'FOX Lima (WLIO-DT2)', 'WKYC Cleveland 3'
        for m in CALL_IN_NAME.finditer(nm):
            if m.group(1) in epg.locals:
                hit = epg.local(m.group(1), m.group(2))
                if hit:
                    return hit
    return None


def gen_id(prefix, r, used):
    """Stable id for a channel that has no published guide; guide.py writes its listings.
    Event slots are keyed by slot ('NFL 02'), not by event text, so a renamed slot keeps its guide row."""
    base = r['name']
    m = re.match(r'^([^:]+?\s\d{1,3})(?::|$)', base) if r['kind'] == 'event' else None
    if m:
        base = m.group(1)
    else:                                   # copies of the same channel share one guide row (team feeds too)
        base = re.sub(r'\s*\(\d+\)$', '', base)
        base = re.sub(r'\s+(4K|FHD|HD|SD)$', '', base)
        slug = re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')[:60] or 'channel'
        return f'{prefix}.{slug}'
    slug = re.sub(r'[^a-z0-9]+', '-', base.lower()).strip('-')[:60] or 'channel'
    gid = f'{prefix}.{slug}'
    n = 1
    while gid in used:
        n += 1
        gid = f'{prefix}.{slug}-{n}'
    used.add(gid)
    return gid


CANON_KINDS = ('channel', 'league-channel')
DEBUG_ROWS = []
LOCAL_NAME = re.compile(r'^US: (?P<city>.*?) - (?P<net>[^-]+?) - (?P<call>[KW][A-Z]{2,3}(?:-[A-Z]{2}\d?)?) - (?P<num>[\d.]+)$')


def logo_name_fits(url, names):
    """Does a descriptive logo file name ('.../newsnation.png') belong to this channel?"""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return True
    stem = re.sub(r'\.(png|jpe?g|svg|webp|gif).*$', '', url.rsplit('/', 1)[-1].lower())
    stem = re.sub(r'(east|west|hd|us|usa|uk|ca|channel|network|tv|logo)$', '', re.sub(r'[^a-z0-9]', '', stem))
    if len(stem) < 3:
        return True
    for n in names:
        a = re.sub(r'[^a-z0-9]', '', re.sub(r'^(?:[A-Z]{2,3}: |24/7 )', '', n).lower())
        a = re.sub(r'(east|west|hd|channel|network|tv)$', '', a)
        if a and (a in stem or stem in a or fuzz.ratio(a, stem) >= 92):
            return True
    return False


def canonicalize(recs, namer):
    """Every copy of a channel gets the same name: 'US: FOX News Channel HD' / 'US: Fox News (FNC)' ->
    'US: FOX News HD' / 'US: FOX News'. Quality (4K/FHD/HD/SD) stays, since those are different streams."""
    todo = []
    for r in recs:
        if r['drop'] or not r.get('name'):
            continue
        if r['kind'] in CANON_KINDS:
            cc, base, q = split_name(r['name'])
            key = namer.add(cc or 'LEAGUE', base)
            r['ident'] = key
            todo.append((r, cc, q))
            if r.get('group') and r['group'].startswith(f'{cc} | '):
                namer.vote_group(key, r['group'])
        elif r['kind'] == '247':                  # '24/7 The Matrix' / '24/7 Matrix', "24/7 Bob's Burgers" / '24/7 Bobs Burgers'
            _cc, base, q = split_name(r['name'])
            base = re.sub(r'^24/7\s+', '', base)
            key = namer.add('247', base)
            r['ident'] = key
            todo.append((r, '247', q))
            namer.vote_group(key, r['group'])
    for r, cc, q in todo:
        disp = namer.name(r['ident'])
        g = namer.group(r['ident'])
        if cc == '247':
            if disp:
                r['name'] = f'24/7 {disp}' + (f' {q}' if q else '')
            if g:
                r['group'] = g
            continue
        if disp:
            r['name'] = (f'{cc}: ' if cc else '') + disp + (f' {q}' if q else '')
        if g and r['group'].startswith(f'{cc} | ') and g.startswith(f'{cc} | '):
            r['group'] = g                        # every copy of a channel in the same group
    # local stations: one spelling per station/subchannel (the most common one)
    by_station = defaultdict(Counter)
    for r in recs:
        if not r['drop'] and r['kind'] == 'local':
            cc, base, q = split_name(r['name'])
            m = LOCAL_NAME.match(f'US: {base}')
            if m:
                by_station[(m['call'].split('-')[0], m['num'])][base] += 1
    best = {k: max(v.items(), key=lambda kv: (kv[1], len(kv[0])))[0] for k, v in by_station.items()}
    for r in recs:
        if not r['drop'] and r['kind'] == 'local':
            cc, base, q = split_name(r['name'])
            m = LOCAL_NAME.match(f'US: {base}')
            if m:
                k = (m['call'].split('-')[0], m['num'])
                r['ident'] = ('LOCAL', f"{k[0]}-{k[1]}")
                r['name'] = f'US: {best[k]}' + (f' {q}' if q else '')


def group_key(r, i):
    """Which records are the same channel (they share one guide id and one logo)."""
    if r.get('ident'):
        return r['ident']
    if r['kind'] == 'event':
        return ('EVENT', i)
    cc, base, q = split_name(r['name'])
    return (r['kind'] or '', f'{cc or ""}:{base}'.lower())


def cc_of(r):
    if r['kind'] in ('channel', 'ca-local') and r['name'][2:4] == ': ':
        return r['name'][:2]
    if r['name'].startswith('INT: '):
        return 'INT'
    return r.get('cc') or 'US'


def lookup_names(r, namer):
    """Names to look a channel up under: its display name, then every other spelling copies used."""
    out = [clean_for_lookup(r.get('lookup') or r['name'])]
    if r['kind'] == '247':                        # '24/7 Star Trek' -> 'Star Trek' (FAST services have many of these)
        t = re.sub(r'^24/7\s+', '', clean_for_lookup(r['name']))
        out = [t, r.get('lookup')] if r.get('lookup') else [t]
    if r['kind'] == 'ca-local':                   # 'CA: Halifax - Global - CIHF - 8' -> 'Global Halifax', 'CIHF'
        parts = re.sub(r' (4K|FHD|HD|SD)$', '', r['name'][4:]).split(' - ')
        if len(parts) >= 2:
            out = [f'{parts[1]} {parts[0]}'] + ([parts[2]] if len(parts) >= 3 else []) + out
    if r.get('ident') and r['kind'] in CANON_KINDS:
        for v, _n in (namer.seen.get(r['ident'], Counter()) + namer.other.get(r['ident'], Counter())).most_common():
            out.append(v)
    return list(dict.fromkeys(x for x in out if x))


def local_call_sub(r):
    """('WALB', '2') for 'US: Albany - ABC - WALB - 10.2': the number says which subchannel it is."""
    loc = r.get('local') or {}
    call = loc.get('call')
    m = LOCAL_NAME.match(re.sub(r' (4K|FHD|HD|SD)$', '', r['name']))
    if m:
        call = m['call'].split('-')[0]
        num = m['num']
        sub = num.split('.')[1] if '.' in num else '1'
        return call, ('1' if sub in ('', '1') else sub)
    return call, loc.get('sub')


def guide_candidates(epg, cc, nm):
    """Every guide id that carries this channel, best first (a time-shifted copy of the main feed for
    '+1' channels and West feeds when no source has them separately). Matches we cannot vouch for
    ('National Geo' -> 'Geo TV') are left out: no guide is better than the wrong channel's guide."""
    found = []                                     # (id, how, name it was found under)
    found += [(i, h, nm) for i, h in epg.lookup_all(cc, nm, how=True)]
    prim = channel_guide(epg, cc, nm)
    if re.search(r'\+1\b', nm):
        base = re.sub(r'\s*\+1\b', '', nm).strip()
        found += [(f'{i}{SHIFT_SEP}+60', h, base) for i, h in epg.lookup_all(cc, base, how=True)]
    if cc in ('US', 'CA') and WEST_WORDS.search(nm):
        base = WEST_WORDS.sub('', nm).strip()
        found += [(f'{i}{SHIFT_SEP}+180', h, base) for i, h in epg.lookup_all(cc, base, how=True)]
    if prim and prim not in [f[0] for f in found]:
        base_nm = nm
        if SHIFT_SEP in prim:
            base_nm = re.sub(r'\s*\+1\b', '', WEST_WORDS.sub('', nm)).strip()
        found.insert(0, (prim, 'fuzzy', base_nm))
    elif prim:
        found.sort(key=lambda f: f[0] != prim)
    out = list(dict.fromkeys(i for i, h, n in found if epg.trusted(i, h, n, cc)))
    if out:                                        # alternatives must be the same country's broadcast: a
        fam = epg_family(epg.source_of.get(out[0].split(SHIFT_SEP)[0]))      # Canadian channel's schedule is not the US one
        out = [out[0]] + [i for i in out[1:] if epg_family(epg.source_of.get(i.split(SHIFT_SEP)[0])) == fam]
    return out


USER_AGENTS = [
    os.environ.get('PROVIDER_USER_AGENT') or 'TiviMate/5.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36',
    'VLC/3.0.21 LibVLC/3.0.21',
]


def download(url, dest):
    """Stream a provider playlist to disk (some are 80+ MB). Tries a few app identities, since some
    providers refuse certain ones. Raises on network/HTTP errors."""
    import urllib.error
    last = None
    for ua in dict.fromkeys(USER_AGENTS):
        req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': '*/*'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, 'wb') as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 406, 451):     # refused: try the next identity
                continue
            raise
        with open(dest, 'rb') as f:
            head = f.read(4096)
        if b'#EXTINF' in head or b'#EXTM3U' in head:
            return dest
        snippet = re.sub(r'\s+', ' ', head[:120].decode('utf-8', 'replace')).strip()
        last = ValueError(f'the server answered, but not with a playlist: "{snippet or "(empty)"}"')
    raise last


def logo_kind(logo, old):
    if logo == old:
        return 'provider'
    if '/marshallbelknap/' in logo:
        return 'league/category tile'
    if '__SERVER__/logo/' in logo:
        return 'name tile'
    if 'tv-logo/tv-logos' in logo:
        return 'tv-logos'
    return 'guide / iptv-org'


def main(src, out, report=None, gen_prefix='gen', name_tiles=False, cache_dir=None):
    if re.match(r'https?://', src):
        src = download(src, out + '.source.m3u')
    entries, vod_skipped = parse(src, skip_vod=True)
    if src == out + '.source.m3u':
        os.remove(src)                      # the raw download is no longer needed
    pre_drops = []
    if is_pipe_style(entries):
        entries, pre_drops = adapt(entries)
    recs = process_all(entries)
    namer = Namer(cache_dir, gen_prefix)
    canonicalize(recs, namer)                # one name per channel, whatever spelling each copy used
    namer.save()
    epg = EpgIndex()
    picker = Picker(cache_dir=cache_dir, server_base='__SERVER__' if name_tiles else None)

    # how many different channel names share each provider logo (detects generic art)
    logo_use = defaultdict(set)
    for e, r in zip(entries, recs):
        if not r['drop'] and e['attrs'].get('tvg-logo'):
            logo_use[e['attrs']['tvg-logo']].add(clean_for_lookup(r['name']).split(':')[0])

    def provider_ok(u, names=None):
        if not u or u.rsplit('/', 1)[-1] in WEAK_LOGOS or len(logo_use[u]) > 3:
            return False
        if names and 'm3uassets.com/' in u:      # their file names say whose logo it is: 'fifthgear.png' is not 'Historian'
            return logo_name_fits(u, names)
        return True

    # logos chosen for the same channel in the other playlist (kept in the cache between builds), so a
    # channel that only has a provider logo shows the same one in both playlists
    pool_path = os.path.join(cache_dir, 'logo_pool.json') if cache_dir else None
    try:
        pool = json.load(open(pool_path)) if pool_path and os.path.exists(pool_path) else {}
    except ValueError:
        pool = {}
    pool = {k: v for k, v in pool.items() if '|' in k and '/iptv-playlist-cleaner/' not in v and '/logo/' not in v}

    # guide ids chosen for the same channel in the other playlist
    gpool_path = os.path.join(cache_dir, 'guide_pool.json') if cache_dir else None
    try:
        gpool = json.load(open(gpool_path)) if gpool_path and os.path.exists(gpool_path) else {}
    except ValueError:
        gpool = {}
    gpool = {k: v for k, v in gpool.items() if v and v[0].split(SHIFT_SEP)[0] in epg.all_ids}

    # every copy of one channel is decided once: same guide id, same logo
    groups = defaultdict(list)
    for i, (e, r) in enumerate(zip(entries, recs)):
        if not r['drop']:
            groups[group_key(r, i)].append((e, r))
    decided = {}
    alts_out = {}
    for gk, members in groups.items():
        r0 = members[0][1]
        cc = cc_of(r0)
        names = lookup_names(r0, namer)
        tvg_id, alts = '', []
        if r0['kind'] == 'local':
            call, sub = local_call_sub(r0)
            if call:
                cands = epg.local_all(call, sub)
                if cands:
                    tvg_id, alts = cands[0], cands[1:]
        elif r0['kind'] in ('channel', 'league-channel', 'ca-local', '247'):
            for c2 in ([cc, 'US'] if r0['kind'] == '247' and cc != 'US' else [cc]):
                for nm in names:
                    cands = guide_candidates(epg, c2, nm)
                    if cands:
                        tvg_id, alts = cands[0], cands[1:]
                        break
                if tvg_id:
                    break
        if not tvg_id and r0['kind'] != 'event':
            # the provider's own guide id - only when it really is this channel
            ids = Counter(e['attrs'].get('tvg-id') for e, _ in members if e['attrs'].get('tvg-id') in epg.all_ids)
            for gid, _n in ids.most_common():
                src = epg.source_of.get(gid)
                if (src in SOURCES.get(cc, []) or src in ('US_LOCALS1', 'PBS')) and \
                        any(epg.trusted(gid, 'provider', nm, cc) for nm in names):
                    tvg_id = gid
                    break
        pkey = f'{"" if r0["kind"] == "247" else cc}|{gk[1] if isinstance(gk, tuple) else gk}'
        if r0['kind'] != 'event':                 # the other playlist settled on a guide for this channel: same here
            prev = gpool.get(pkey)
            if prev and r0['kind'] not in ('local',) and not any(
                    epg.trusted(prev[0], 'pool', nm, cc) for nm in names):
                prev = None                       # no longer looks like this channel: decide afresh
            if prev and (not tvg_id or r0['kind'] == '247' or prev[0] in alts):
                tvg_id, alts = prev[0], list(dict.fromkeys(prev[1:] + [x for x in [tvg_id] + alts if x and x != prev[0]]))
            if tvg_id:
                gpool[pkey] = [tvg_id] + alts
        if r0['kind'] == 'event':
            decided[gk] = None                    # event logos follow each slot's own event text
        else:
            logos_seen = Counter(e['attrs'].get('tvg-logo') for e, _ in members
                                 if provider_ok(e['attrs'].get('tvg-logo'), names))
            provider = logos_seen.most_common(1)[0][0] if logos_seen else ''
            if pool.get(pkey) and not provider_ok(pool[pkey], names) and 'm3uassets.com/' in pool[pkey]:
                del pool[pkey]                    # an older build kept another channel's logo here
            logo = picker.pick(r0, cc, names[0], tvg_id, provider or pool.get(pkey, ''))
            if pool.get(pkey) and (not logo or logo == provider) and pool[pkey] != logo:
                logo = pool[pkey]                 # the other playlist settled on this one: keep both the same
            if logo and pool_path and r0['group'] != PPV_GROUP and not r0['group'].startswith('Sports | '):
                pool.setdefault(pkey, logo)
            decided[gk] = (tvg_id, logo)
        if tvg_id and alts:
            alts_out[tvg_id] = list(dict.fromkeys(alts_out.get(tvg_id, []) + alts))
        if os.environ.get('CLEANER_DEBUG') and r0['kind'] != 'event':
            DEBUG_ROWS.append((gen_prefix, r0['kind'], cc, names[0], tvg_id, '|'.join(alts), ''))
        for _e, r in members:
            r['_tvg'] = tvg_id

    kept = []
    stats = Counter()
    if vod_skipped:
        stats['dropped: VOD movie/episode'] += vod_skipped
    for d in pre_drops:
        stats['dropped: ' + d.split(' (')[0]] += 1
    for i, (e, r) in enumerate(zip(entries, recs)):
        if r['drop']:
            stats['dropped: ' + r['drop'].split(' (')[0]] += 1
            continue
        old_logo = e['attrs'].get('tvg-logo', '')
        gk = group_key(r, i)
        tvg_id = r.pop('_tvg', '')
        if decided.get(gk):
            logo = decided[gk][1]
        else:                                     # event slots
            cc = cc_of(r)
            provider = old_logo if provider_ok(old_logo) else ''
            logo = picker.pick(r, cc, clean_for_lookup(r.get('lookup') or r['name']), tvg_id, provider)
        stats['epg ' + ('matched' if tvg_id else 'none') + ' (' + r['kind'] + ')'] += 1
        stats['logo: ' + logo_kind(logo, old_logo)] += 1
        kept.append({**r, 'tvg_id': tvg_id, 'logo': logo, 'url': e['url'], 'dur': e.get('dur', '-1'),
                     'old_id': e['attrs'].get('tvg-id', ''), 'old_logo': old_logo, 'old_group': r['src'],
                     'gkey': gk})

    # copies of the same channel (several sources) keep the same name - no (2)/(3) numbering
    kept.sort(key=lambda r: (group_rank(r['group']), sort_key(r)))

    if pool_path:
        tmp = pool_path + '.tmp'
        json.dump(pool, open(tmp, 'w'))
        os.replace(tmp, pool_path)
    if gpool_path:
        tmp = gpool_path + '.tmp'
        json.dump(gpool, open(tmp, 'w'))
        os.replace(tmp, gpool_path)
    if cache_dir:                                 # other guide ids for the same channels (guide.py falls back to them)
        tmp = os.path.join(cache_dir, f'guide_alts_{gen_prefix}.json.tmp')
        json.dump(alts_out, open(tmp, 'w'))
        os.replace(tmp, tmp[:-4])
    if cache_dir:
        with open(os.path.join(cache_dir, f'logos_missing_{gen_prefix}.tsv'), 'w', encoding='utf-8') as f:
            for row in sorted(set(picker.missing)):
                f.write('\t'.join(row) + '\n')
    used = set()
    for r in kept:
        if not r['tvg_id']:
            r['tvg_id'] = gen_id(gen_prefix, r, used)
            r['generated'] = True
    epg_urls = ','.join(EPG_URLS.values())
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f'#EXTM3U x-tvg-url="{epg_urls}" url-tvg="{epg_urls}"\n')
        for r in kept:
            f.write(f'#EXTINF:-1 tvg-id="{esc(r["tvg_id"])}" tvg-name="{esc(r["name"])}" '
                    f'tvg-logo="{esc(r["logo"])}" group-title="{esc(r["group"])}",{r["name"]}\n{r["url"]}\n')
    if report:
        with open(report, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['new_group', 'new_name', 'tvg_id', 'logo', 'old_group', 'old_name', 'old_tvg_id', 'old_logo'])
            for r in kept:
                w.writerow([r['group'], r['name'], r['tvg_id'], r['logo'], r['old_group'], r['orig'], r['old_id'], r['old_logo']])
    picker_unknown = sorted(picker.dims.unknown)
    if cache_dir:
        with open(os.path.join(cache_dir, f'logos_to_check_{gen_prefix}.txt'), 'w') as f:
            f.write('\n'.join(picker_unknown))
    groups = Counter(r['group'] for r in kept)
    summary = {'input_entries': len(entries) + vod_skipped + len(pre_drops), 'kept': len(kept), 'groups': len(groups),
               'stats': dict(stats), 'group_counts': dict(sorted(groups.items(), key=lambda x: group_rank(x[0])))}
    json.dump(summary, open(out + '.summary.json', 'w'), indent=1)
    return summary


if __name__ == '__main__':
    s = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps({k: v for k, v in s.items() if k != 'group_counts'}, indent=1))
    print(len(s['group_counts']), 'groups')
