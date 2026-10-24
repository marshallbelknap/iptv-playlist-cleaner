# -*- coding: utf-8 -*-
"""Logo fallback lookup: tv-logo/tv-logos repo, then iptv-org database."""
import csv
import os
import re
from epgmap import norm

TVLOGOS_RAW = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/'
FOLDERS = {'US': 'united-states', 'UK': 'united-kingdom', 'CA': 'canada', 'AU': 'australia',
           'NZ': 'new-zealand', 'IE': 'ireland', 'ZA': 'south-africa', 'INT': 'international'}
IPTV_CC = {'US': 'US', 'UK': 'UK', 'CA': 'CA', 'AU': 'AU', 'NZ': 'NZ', 'IE': 'IE', 'ZA': 'ZA', 'INT': None}

# event label -> logo file in tv-logos repo
LABEL_LOGOS = {
    'ESPN+': 'countries/united-states/espn-plus-us.png',
    'DAZN': 'countries/united-states/dazn-us.png',
    'Paramount+': 'countries/united-states/paramount-plus-us.png',
    'NFL': 'misc/sports/leagues/nfl-us.png',
    'NBA': 'countries/united-states/nba-league-pass-us.png',
    'NBA G League': 'countries/united-states/nba-league-pass-us.png',
    'WNBA': 'countries/united-states/wnba-league-pass-us.png',
    'MLB': 'countries/united-states/mlb-extra-innings-us.png',
    'NHL': 'countries/united-states/nhl-center-ice-us.png',
    'MLS': 'countries/united-states/mls-logo-us.png',
    'EPL': 'misc/sports/leagues/premier-league-uk.png',
    'NCAAF': 'misc/sports/organizations/ncaa.png',
    'NCAAB': 'misc/sports/organizations/ncaa.png',
    'NCAA': 'misc/sports/organizations/ncaa.png',
    'UFC': 'countries/united-states/ufc-fight-pass-us.png',
    'Fubo Sports': 'countries/united-states/fubo-sports-network-us.png',
}
NETWORK_LOGOS = {
    'ABC': 'countries/united-states/abc-us.png', 'CBS': 'countries/united-states/cbs-logo-white-us.png',
    'NBC': 'countries/united-states/nbc-us.png', 'FOX': 'countries/united-states/fox-us.png',
    'PBS': 'countries/united-states/pbs-us.png', 'CW': 'countries/united-states/cw-us.png',
    'MyNetworkTV': 'countries/united-states/my-network-tv-us.png',
    'ION': 'countries/united-states/ion-television-us.png',
    'ION Mystery': 'countries/united-states/ion-mystery-us.png',
    'MeTV': 'countries/united-states/me-tv-us.png',
    'Telemundo': 'countries/united-states/telemundo-us.png',
    'Univision': 'countries/united-states/univision-us.png',
    'Cozi TV': 'countries/united-states/cozi-tv-us.png',
    'Antenna TV': 'countries/united-states/antenna-us.png',
    'Heroes & Icons': 'countries/united-states/heroes-and-icons-us.png',
    'Start TV': 'countries/united-states/start-tv-us.png',
    'Grit': 'countries/united-states/grit-us.png',
    'Bounce TV': 'countries/united-states/bounce-us.png',
    'Court TV': 'countries/united-states/court-tv-us.png',
    'Dabl': 'countries/united-states/dabl-us.png',
    'Charge!': 'countries/united-states/charge-us.png',
    'Comet': 'countries/united-states/comet-us.png',
    'Story Television': 'countries/united-states/story-television-us.png',
    'Catchy Comedy': 'countries/united-states/catchy-comedy-us.png',
    'Laff': 'countries/united-states/laff-us.png',
    'Roar': 'countries/united-states/roar-us.png',
    'Defy': 'countries/united-states/defy-us.png',
    'TBN': 'countries/united-states/tbn-us.png',
    'Daystar': 'countries/united-states/daystar-us.png',
    '3ABN': 'countries/united-states/3abn-us.png',
    'HSN': 'countries/united-states/hsn-us.png',
    'QVC': 'countries/united-states/qvc-us.png',
    'Retro TV': 'countries/united-states/retro-tv-us.png',
    'Buzzr': 'countries/united-states/buzzr-us.png',
    'getTV': 'countries/united-states/get-tv-us.png',
    'Movies!': 'countries/united-states/movies-us.png',
    'Shop LC': 'countries/united-states/shop-lc-us.png',
    'MeTV Toons': 'countries/united-states/me-tv-toons-us.png',
}

STRIP = {'hd', 'fhd', 'uhd', 'sd', '4k', 'tv', 'channel', 'network', 'the', 'us', 'uk', 'ca', 'au', 'nz',
         'ie', 'hz', 'logo', 'icon', 'white', 'light', 'dark', 'color', 'square', 'east', 'and'}


def lkey(s):
    return ' '.join(w for w in norm(s).split() if w not in STRIP)


class LogoIndex:
    def __init__(self, files_txt, iptv_dir):
        self.repo = {}
        for line in open(files_txt):
            p = line.strip().strip('"')
            m = re.match(r'^countries/([^/]+)/(?:(.*)/)?([^/]+)\.png$', p)
            if not m:
                continue
            folder, sub, stem = m.groups()
            stem = re.sub(r'[-_](us|uk|ca|au|nz|ie|za|int)$', '', stem)
            # skip obvious variants when a plain version exists (sub-folders like 'beinsports/old/...' rank last)
            variant = bool(re.search(r'-(hz|white|light|dark|icon|square|alt|old|\d{4})(-|$)', stem)) or \
                bool(sub and re.search(r'\bold\b', sub))
            k = lkey(stem.replace('-', ' '))
            cur = self.repo.setdefault(folder, {}).get(k)
            if cur is None or (cur[1] and not variant):
                self.repo[folder][k] = (p, variant)
        self.iptv = {}
        names = {}
        for r in csv.DictReader(open(os.path.join(iptv_dir, 'channels.csv'), encoding='utf-8')):
            if r.get('closed'):
                continue
            names[r['id']] = (r['country'], [r['name']] + [a for a in r['alt_names'].split(';') if a])
        bad_path = os.path.join(os.path.dirname(files_txt), 'bad_logos.txt')
        bad = set(l.strip() for l in open(bad_path)) if os.path.exists(bad_path) else set()
        logos = {}
        for r in csv.DictReader(open(os.path.join(iptv_dir, 'logos.csv'), encoding='utf-8')):
            if r['feed'] or r['in_use'] == 'FALSE' or r['url'].strip() in bad:
                continue
            w = int(r['width'] or 0)
            if r['channel'] not in logos or w > logos[r['channel']][1]:
                logos[r['channel']] = (r['url'], w)
        for cid, (country, nms) in names.items():
            if cid not in logos:
                continue
            for n in nms:
                self.iptv.setdefault((country, lkey(n)), logos[cid][0])
                self.iptv.setdefault((None, lkey(n)), logos[cid][0])

    def lookup(self, cc, name):
        k = lkey(name)
        if not k:
            return None
        folder = FOLDERS.get(cc)
        for f in [folder, 'international']:
            hit = self.repo.get(f, {}).get(k) if f else None
            if hit:
                return TVLOGOS_RAW + hit[0]
        country = IPTV_CC.get(cc)
        u = self.iptv.get((country, k)) if country else None
        if u:
            return u
        if cc == 'INT':
            return self.iptv.get((None, k))
        return None

    @staticmethod
    def label_logo(label):
        p = LABEL_LOGOS.get(label)
        return TVLOGOS_RAW + p if p else None

    @staticmethod
    def network_logo(net):
        p = NETWORK_LOGOS.get(net)
        return TVLOGOS_RAW + p if p else None
