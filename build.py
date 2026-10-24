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
from epgmap import EpgIndex, EPG_URLS        # noqa: E402
from logo_pick import Picker                 # noqa: E402
from adapt_p2 import adapt, is_pipe_style    # noqa: E402
from rules import COUNTRY_ORDER, CATEGORY_ORDER, PPV_GROUP, G247, ADULT_GROUP  # noqa: E402

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
    if r['kind'] == 'event':
        m = re.match(r'^([^:]+?\s\d{1,3})(?::|$)', base)
        base = m.group(1) if m else base.split(':')[0] + ' ' + base.split(':', 1)[-1][:40]
    else:                                   # copies of the same channel share one guide row
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
    epg = EpgIndex()
    picker = Picker(cache_dir=cache_dir, server_base='__SERVER__' if name_tiles else None)

    # how many different channel names share each provider logo (detects generic art)
    logo_use = defaultdict(set)
    for e, r in zip(entries, recs):
        if not r['drop'] and e['attrs'].get('tvg-logo'):
            logo_use[e['attrs']['tvg-logo']].add(clean_for_lookup(r['name']).split(':')[0])

    # logos chosen for the same channel name in the other playlists (kept in the cache between builds)
    pool_path = os.path.join(cache_dir, 'logo_pool.json') if cache_dir else None
    try:
        pool = json.load(open(pool_path)) if pool_path and os.path.exists(pool_path) else {}
    except ValueError:
        pool = {}
    # a channel's logo from another copy of the same channel (one source has it, another does not)
    same_name_logo = {}
    for e, r in zip(entries, recs):
        u = e['attrs'].get('tvg-logo', '')
        if not r['drop'] and u and len(logo_use[u]) <= 3 and u.rsplit('/', 1)[-1] not in WEAK_LOGOS:
            same_name_logo.setdefault(clean_for_lookup(r.get('lookup') or r['name']).lower(), u)

    # most common provider logo per event label, reused for slots that have none
    lab_logos = defaultdict(Counter)
    for e, r in zip(entries, recs):
        if not r['drop'] and r['kind'] == 'event' and e['attrs'].get('tvg-logo'):
            stem = e['attrs']['tvg-logo'].rsplit('/', 1)[-1]
            if not re.search(r'\d', stem):          # skip slot-numbered art such as espnplus07.png
                lab_logos[r.get('label')][e['attrs']['tvg-logo']] += 1
    label_logo = {k: v.most_common(1)[0][0] for k, v in lab_logos.items()}

    kept = []
    stats = Counter()
    if vod_skipped:
        stats['dropped: VOD movie/episode'] += vod_skipped
    for d in pre_drops:
        stats['dropped: ' + d.split(' (')[0]] += 1
    for e, r in zip(entries, recs):
        if r['drop']:
            stats['dropped: ' + r['drop'].split(' (')[0]] += 1
            continue
        old_logo = e['attrs'].get('tvg-logo', '')
        cc = r['name'][:2] if r['kind'] in ('channel', 'ca-local') and r['name'][2:4] == ': ' else \
            r['name'][:3] if r['name'].startswith('INT: ') else (r.get('cc') or 'US')
        nm = clean_for_lookup(r.get('lookup') or r['name'])
        # ---- EPG id
        tvg_id = ''
        if r['kind'] == 'local' and r['local'] and r['local'].get('call'):
            tvg_id = epg.local(r['local']['call'], r['local'].get('sub')) or ''
        elif r['kind'] in ('channel', 'league-channel', 'ca-local') or (r['kind'] == '247' and r.get('lookup')):
            tvg_id = channel_guide(epg, cc, nm) or ''
        if not tvg_id and e['attrs'].get('tvg-id') in epg.all_ids:
            tvg_id = e['attrs']['tvg-id']
        stats['epg ' + ('matched' if tvg_id else 'none') + ' (' + r['kind'] + ')'] += 1
        # ---- logo (see logo_pick.py for the order)
        provider = old_logo
        if provider and (provider.rsplit('/', 1)[-1] in WEAK_LOGOS or len(logo_use[provider]) > 3):
            provider = ''                    # one generic picture shared by many different channels
        provider = provider or same_name_logo.get(nm.lower(), '') or pool.get(nm.lower(), '')
        logo = picker.pick(r, cc, nm, tvg_id, provider)
        stats['logo: ' + logo_kind(logo, old_logo)] += 1
        kept.append({**r, 'tvg_id': tvg_id, 'logo': logo, 'url': e['url'], 'dur': e.get('dur', '-1'),
                     'old_id': e['attrs'].get('tvg-id', ''), 'old_logo': old_logo, 'old_group': r['src']})

    # copies of the same channel (several sources) keep the same name - no (2)/(3) numbering
    kept.sort(key=lambda r: (group_rank(r['group']), sort_key(r)))

    if pool_path:
        for r in kept:
            if r['logo'] and r['group'] not in ('PPV & Events',) and not r['group'].startswith('Sports | '):
                pool.setdefault(clean_for_lookup(r.get('lookup') or r['name']).lower(), r['logo'])
        tmp = pool_path + '.tmp'
        json.dump(pool, open(tmp, 'w'))
        os.replace(tmp, pool_path)
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
