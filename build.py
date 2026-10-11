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
from logos import LogoIndex                  # noqa: E402
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


def main(src, out, report=None):
    if re.match(r'https?://', src):
        req = urllib.request.Request(src, headers={'User-Agent': 'TiviMate/5.0'})
        tmp = out + '.source.m3u'
        with urllib.request.urlopen(req, timeout=180) as r, open(tmp, 'wb') as f:
            f.write(r.read())
        src = tmp
    entries = parse(src)
    recs = process_all(entries)
    epg = EpgIndex()
    logos = LogoIndex(os.path.join(DATA, 'tvlogos_files.txt'), os.path.join(DATA, 'iptvorg'))

    # how many different channel names share each provider logo (detects generic art)
    logo_use = defaultdict(set)
    for e, r in zip(entries, recs):
        if not r['drop'] and e['attrs'].get('tvg-logo'):
            logo_use[e['attrs']['tvg-logo']].add(clean_for_lookup(r['name']).split(':')[0])

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
    for e, r in zip(entries, recs):
        if r['drop']:
            stats['dropped: ' + r['drop'].split(' (')[0]] += 1
            continue
        old_logo = e['attrs'].get('tvg-logo', '')
        cc = r['name'][:2] if r['kind'] == 'channel' and r['name'][2:4] == ': ' else \
            r['name'][:3] if r['name'].startswith('INT: ') else 'US'
        nm = clean_for_lookup(r['name'])
        # ---- EPG id
        tvg_id = ''
        if r['kind'] == 'local' and r['local'] and r['local'].get('call'):
            tvg_id = epg.local(r['local']['call'], r['local'].get('sub')) or ''
        elif r['kind'] in ('channel', 'league-channel'):
            tvg_id = epg.lookup(cc, nm) or ''
        if not tvg_id and e['attrs'].get('tvg-id') in epg.all_ids:
            tvg_id = e['attrs']['tvg-id']
        stats['epg ' + ('matched' if tvg_id else 'none') + ' (' + r['kind'] + ')'] += 1
        # ---- logo
        logo = old_logo
        fname = old_logo.rsplit('/', 1)[-1]
        weak = not old_logo or fname in WEAK_LOGOS
        if not weak and r['kind'] == 'local' and len(logo_use[old_logo]) > 6:
            weak = True                      # one numbered network picture reused across many stations
        if not weak and r['kind'] == 'local' and r['local'] and r['local'].get('num'):
            m = re.search(r'(\d+)', fname)
            if m and m.group(1) != r['local']['num']:
                weak = True                  # e.g. fox25.png on FOX 23
        if not weak and r['kind'] == 'channel':
            stem = re.sub(r'[^a-z0-9]', '', fname.rsplit('.', 1)[0].lower())
            key = re.sub(r'[^a-z0-9]', '', nm.lower())
            if stem and key and stem[:4] not in key and key[:4] not in stem:
                weak = True                  # picture apparently belongs to another channel
        if weak:
            alt = None
            if r['kind'] in ('channel', 'league-channel'):
                alt = logos.lookup(cc, nm)
            elif r['kind'] == 'local' and r['local']:
                alt = logos.network_logo(r['local'].get('net'))
            elif r['kind'] == 'event':
                alt = label_logo.get(r.get('label')) or logos.label_logo(r.get('label'))
            if alt:
                logo = alt
                stats['logo replaced/added'] += 1
        stats['logo ' + ('present' if logo else 'missing')] += 1
        kept.append({**r, 'tvg_id': tvg_id, 'logo': logo, 'url': e['url'], 'dur': e.get('dur', '-1'),
                     'old_id': e['attrs'].get('tvg-id', ''), 'old_logo': old_logo, 'old_group': r['src']})

    # identical names (same channel from several sources) -> number the extra copies
    seen = Counter()
    for r in sorted(kept, key=lambda r: (group_rank(r['group']), sort_key(r))):
        seen[(r['group'], r['name'])] += 1
        n = seen[(r['group'], r['name'])]
        if n > 1 and r['kind'] != 'event':
            r['name'] = f"{r['name']} ({n})"
    kept.sort(key=lambda r: (group_rank(r['group']), sort_key(r)))

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
    groups = Counter(r['group'] for r in kept)
    summary = {'input_entries': len(entries), 'kept': len(kept), 'groups': len(groups),
               'stats': dict(stats), 'group_counts': dict(sorted(groups.items(), key=lambda x: group_rank(x[0])))}
    json.dump(summary, open(out + '.summary.json', 'w'), indent=1)
    return summary


if __name__ == '__main__':
    s = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    print(json.dumps({k: v for k, v in s.items() if k != 'group_counts'}, indent=1))
    print(len(s['group_counts']), 'groups')
