# -*- coding: utf-8 -*-
"""Which country a channel really belongs to.

Providers often file channels under the country where they are carried, not where they come from:
CNN, ACC Network or WGN in a Canada group, BBC News in an Australia group, RTE in a UK group.
iptv-org's channel database lists the countries each channel brand actually exists in, so a channel
stays in its group only when that country has its own version; otherwise it moves to its home country
(US first, then the other English-speaking countries) or to International.
"""
import csv
import os
import re

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
ENGLISH = ['US', 'UK', 'CA', 'AU', 'NZ', 'IE', 'ZA']
IPTV_CC = {'GB': 'UK'}
# Canadian services that share a name with a US channel (Crave / Corus / Bell versions)
CA_OWN = {'hbo', 'hbo2', 'hbo1', 'starz', 'starz1', 'starz2', 'showcase', 'slice', 'w', 'wnetwork', 'treehouse',
          'teletoon', 'ytv', 'family', 'familychannel', 'disneychannel', 'disneyjunior', 'disneyxd', 'abcspark',
          'adultswim', 'cartoonnetwork', 'historytelevision', 'history', 'history2', 'cmt', 'much', 'muchmusic',
          'oln', 'gametv', 'dtour', 'flavournetwork', 'cottagelife', 'makeful', 'homenetwork', 'magnolianetwork',
          'lovenature', 'tsc', 'theshoppingchannel', 'vision', 'visiontv', 'joytv', 'omni1', 'omni2', 'aptn',
          'tvo', 'tvontario', 'knowledgenetwork', 'chch', 'ctv', 'global', 'citytv', 'cbc', 'yesTV'.lower(),
          'thenweathernetwork', 'theweathernetwork', 'weathernetwork', 'cp24', 'cpac', 'bnn', 'bnnbloomberg',
          'businessnewsnetwork', 'fx', 'fxx', 'e', 'eentertainment', 'hgtv', 'foodnetwork', 'discovery',
          'discoverychannel', 'discoveryscience', 'discoveryvelocity', 'investigationdiscovery', 'tlc',
          'animalplanet', 'natgeo', 'nationalgeographic', 'natgeowild', 'nationalgeowild', 'nationalgeographicwild',
          'mtv', 'mtv2', 'bravo', 'lifetime', 'bet', 'crimeinvestigation', 
          'oprahwinfreynetwork', 'own', 'smithsonianchannel', 'documentarychannel', 'cooking', 'cookingchannel',
          'thecookingchannel', 'nickelodeon', 'nicktoons', 'nickjr', 
           'fyi', 'h2', 'amc', 'moviTime'.lower(), 'movietime', 'max'}
GENERIC = {'tv', 'news', 'sports', 'sport', 'movies', 'music', 'golf', 'game', 'drive', 'taste', 'insight',
           'max', 'one', 'channel', 'live', 'kids', 'comedy', 'crime', 'drama', 'action', 'horror'}
# brands iptv-org spells differently ('Fox News Channel') or lacks
FORCE = {'foxnews': 'US', 'foxnewschannel': 'US', 'foxbusiness': 'US', 'headlinenews': 'US', 'hln': 'US',
         'bloomberg': 'US', 'bloombergtv': 'US', 'bloombergtvplus': 'US', 'peachtree': 'US', 'peachtreetv': 'US',
         'wgn': 'US', 'wgnamerica': 'US', 'newsnation': 'US', 'msnbc': 'US', 'cnbc': 'US', 'cnn': 'US',
         'cnnheadlinesinternational': 'INT', 'dwnews': 'INT', 'dw': 'INT', 'dwenglish': 'INT', 'arisenews': 'INT', 'bloombergeu': 'INT', 'courttv': 'US', 'cnnnews': 'US', 'cbsnews': 'US', 'cbsnews247': 'US', 'abcnews': 'US', 'abcnewslive': 'US', 'nbcnews': 'US', 'nbcnewsnow': 'US', 'foxnewsnow': 'US', 'usanetwork': 'US', 'foxweather': 'US', 'weatherchannel': 'US', 'theweatherchannel': 'US', 'newsmax': 'US', 'cspan': 'US', 'cspan2': 'US', 'iontv': 'US', 'rtamerica': 'INT', 'rtuk': 'INT', 'rtdocumentry': 'INT', 'rtdocumentary': 'INT', 'i24news': 'INT', 'cnnheadlines': 'US', 'bbcworldnews': 'UK', 'nasa': 'US', 'nasatv': 'US', 'fubosportsnetwork': 'US', 'fubosportsnetwork2': 'US', 'boomerang': 'US', 'cnninternational': 'INT', 'euronews': 'INT',
         'aljazeera': 'INT', 'aljazeeraenglish': 'INT', 'rtnews': 'INT', 'rt': 'INT', 'wion': 'INT',
         'i24news': 'INT', 'cna': 'INT', 'channelnewsasia': 'INT', 'channelnewsasiacna': 'INT', 'ndtv': 'INT',
         'bbcnews': 'UK', 'skynews': 'UK', 'gbnews': 'UK', 'rteone': 'IE', 'rte1': 'IE', 'rte2': 'IE',
         'rtetwo': 'IE', 'rteoneplus1': 'IE', 'rtetwoplus1': 'IE', 'rtenews': 'IE', 'virginmediaone': 'IE',
         'virgin1': 'IE', 'virgin2': 'IE', 'virginone': 'IE', 'virginmediaoneplus1': 'IE', 'oireachtas': 'IE',
         'utv': 'UK', 'eirsport1': 'IE', 'eirsport2': 'IE', 'tnasports': 'US', 'tnawrestling': 'US',
         'cbcnews': 'CA', 'cbcnewsnetwork': 'CA', 'ctvnews': 'CA', 'ctvnewschannel': 'CA', 'cp24': 'CA',
         'acc': 'US', 'accnetwork': 'US', 'golfchannel': 'US', 'nbcgolf': 'US', 'foxsportsracing': 'US',
         'monsterjam': 'US', 'turnerclassic': 'US', 'turnerclassicmovies': 'US', 'tcm': 'US', 'ae': 'US',
         'ane': 'US', 'aande': 'US', 'americanmovieclassics': 'US', 'gsn': 'US', 'gameshownetwork': 'US',
         'skynewsweather': 'AU', 'actionmax': 'US', 'moremax': 'US', 'thrillermax': 'US', 'outermax': 'US',
         'moviemax': 'US', '5starmax': 'US', 'cgtn': 'INT', 'cgtnenglish': 'INT', 'cnni': 'INT', 'nhkworld': 'INT',
         'nhkworldjapan': 'INT', 'nhkworldnews': 'INT', 'ndtvworld': 'INT', 'indiatoday': 'INT', 'euronewsworld': 'INT',
         'rtnewsamerica': 'INT', 'tickernews': 'AU', 'yessport5': 'INT', 'nowsportshk': 'INT', 'nowsports': 'INT',
         'bbc2northernireland': 'UK', 'bbctwonorthernireland': 'UK', 'bbconenorthernireland': 'UK',
         'bbc1northernireland': 'UK', 'rtenewsnow': 'IE', 'mtvclassicuk': 'UK', 'mtvclassicus': 'US', '4music': 'UK',
         'kerrang': 'UK', 'kiss': 'UK', 'magic': 'UK', 'boxhits': 'UK', 'clublandtv': 'UK', 'now70s': 'UK',
         'now80s': 'UK', 'now90s': 'UK', 'horseandcountry': 'UK', 'williamhilllive': 'UK', 'actionmaxwest': 'US',
         'moremaxwest': 'US', 'thrillermaxwest': 'US', 'redbulltv': 'INT', 'laligatv': 'UK', 'racingtv': 'UK',
         'skysportsracing': 'UK', 'premiersport1': 'UK', 'premiersport2': 'UK', 'premiersports1': 'UK',
         'premiersports2': 'UK', 'shadesofblack': 'US', 'thefirst': 'US', 'mtvwest': 'US', 'vh1': 'US',
         'mtvlive': 'US', 'vevo2k': 'US', 'vevo70s': 'US', 'vevo80s': 'US', 'vevo90s': 'US', 'vevocountry': 'US',
         'vevohiphop': 'US', 'vevopop': 'US', 'crimeandinvestigation': 'UK', 'skyaction': 'UK', 'skydrama': 'UK',
         'first': 'US', 'thefirstnews': 'US', 'tntultimate': 'UK', 'tntultimateplus': 'UK', 'tntsportsultimate': 'UK'}
_INDEX = None
_CATS = None


def norm(name):
    n = name.lower()
    n = re.sub(r'\b(4k|uhd|fhd|hd|sd|hdtv|east|west|pacific|feed|backup|\+1|en|eng|english)\b', ' ', n)
    n = re.sub(r'(?<=\w)\s+(canada|usa|us|uk|australia|ireland|au|nz|ca)\b', ' ', n)   # 'HGTV Canada', not 'USA Network'
    n = n.replace('&', 'and').replace('+', 'plus')
    n = re.sub(r'\(.*?\)', ' ', n)
    n = re.sub(r'^the ', '', n.strip())
    return re.sub(r'[^a-z0-9]', '', n)


def _load():
    global _INDEX, _CATS
    if _INDEX is not None:
        return
    _INDEX, _CATS = {}, {}
    path = os.path.join(_DATA, 'iptvorg', 'channels.csv')
    if not os.path.exists(path):
        return
    for r in csv.DictReader(open(path, encoding='utf-8')):
        cc = IPTV_CC.get(r['country'], r['country'])
        if r.get('closed') and cc not in ENGLISH:    # closed English channels still say where a brand comes from
            continue
        for nm in [r['name']] + [x for x in r.get('alt_names', '').split(';') if x]:
            k = norm(nm)
            if len(k) < 2:
                continue
            _INDEX.setdefault(k, set()).add(cc)
            if r.get('categories'):
                _CATS.setdefault((k, cc), set()).update(r['categories'].split(';'))


def countries(name):
    _load()
    return _INDEX.get(norm(name), set())


def home_country(name, cc):
    """cc the provider gave -> the country the channel belongs in (may be the same)."""
    if cc not in ENGLISH and cc != 'INT' or re.search(r'\b(Canada|Canadian)\b', name, re.I) and cc == 'CA':
        return cc                                 # INT means 'country unknown': look it up like the others
    tok = re.search(r'(?<!^)(?<!\b5 )(?<!Northern )\b(USA|US|Australia|NZ|New Zealand|Ireland|Canada|UK)\b(?! ?Version)', name)
    if tok:                                       # 'Nat Geo USA', 'Sky News Australia', 'Sky Sports NZ 3'
        t = tok.group(1)
        return {'USA': 'US', 'US': 'US', 'Australia': 'AU', 'NZ': 'NZ', 'New Zealand': 'NZ', 'Ireland': 'IE',
                'Irish': 'IE', 'Canada': 'CA', 'UK': 'UK'}[t]
    k = norm(name)
    if len(k) < 3 or k in GENERIC:
        return cc
    if k.startswith('musicchoice'):              # Music Choice is a US service, wherever a provider files it
        return 'US'
    if cc == 'CA' and (k in CA_OWN or re.sub(r'\d+$', '', k) in CA_OWN):
        return cc
    if k in FORCE:
        return FORCE[k] if not (cc == 'CA' and k in ('turnerclassicmovies', 'tcm')) else 'US'
    if cc == 'INT':                               # only hand-checked brands leave the International group
        if re.search(r'\bWest\b', name) and 'US' in countries(name):
            return 'US'                           # 'MTV (West)': West feeds are American
        return cc
    have = countries(name)
    if not have or cc in have:
        return cc
    for c in ENGLISH:
        if c in have:
            return c
    return 'INT'


CAT_MAP = [('news', 'News'), ('weather', 'News'), ('business', 'News'), ('sports', 'Sports'), ('movies', 'Movies'),
           ('music', 'Music')]


def iptv_category(name, cc):
    """'News' / 'Sports' / 'Movies' / 'Music' / 'General' from iptv-org's categories, or None if unknown."""
    _load()
    cats = _CATS.get((norm(name), cc))
    if not cats:
        return None
    for key, cat in CAT_MAP:
        if key in cats and (key != 'movies' or 'series' not in cats):
            return cat
    return 'General'
