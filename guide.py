# -*- coding: utf-8 -*-
"""Build one XMLTV guide covering every channel in the cleaned playlists.

* Channels matched to a published guide (epgshare01, Pluto, Samsung, Roku, Plex, ...) get the real listings.
  Only the sources and channels actually used are downloaded/kept, so the guide stays small.
* 'Name~+60' ids reuse another channel's listings shifted by N minutes (+1 channels, West feeds).
* Every other channel (event slots, 24/7, music, adult, anything with no published guide) gets generated
  listings: event slots show the current event at its scheduled time, the rest show the channel name.

usage: python3 guide.py out.xml.gz playlist1.m3u [playlist2.m3u ...]
"""
import gzip
import html
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epgmap import EpgIndex, EPG_URLS  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    EASTERN = ZoneInfo('America/New_York')
except Exception:                              # no tz database: fixed EDT offset
    EASTERN = timezone(timedelta(hours=-4))

SHIFT_SEP = '~'
SOURCE_HOURS = float(os.environ.get('GUIDE_SOURCE_HOURS', '12'))   # re-download published guides this often
DAYS_AHEAD = float(os.environ.get('GUIDE_DAYS', '3'))          # how far ahead the guide goes
KEEP_PAST_HOURS = 6
EVENT_HOURS = 3
UA = {'User-Agent': 'Mozilla/5.0 (iptv-playlist-cleaner)'}
MONTHS = {m: i + 1 for i, m in enumerate('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split())}
EXTINF = re.compile(r'tvg-id="([^"]*)".*?tvg-logo="([^"]*)".*?group-title="([^"]*)",(.*)$')
WHEN = re.compile(r'\((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}) (\d{1,2})(?::(\d{2}))? ?([AP]M)'
                  r'(?: (ET|EST|EDT|PT|CT|MT|UK|GMT|BST|UTC))?\)\s*$')
TZ_OFFSET = {'PT': 3, 'MT': 2, 'CT': 1}       # hours after Eastern


def log(*a):
    print('[guide]', *a, flush=True)


def xt(dt):
    return dt.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S +0000')


def parse_xt(s):
    s = s.strip()
    dt = datetime.strptime(s[:14], '%Y%m%d%H%M%S')
    off = s[14:].strip()
    if re.fullmatch(r'[+-]\d{4}', off):
        sign = 1 if off[0] == '+' else -1
        dt = dt.replace(tzinfo=timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:]))))
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def esc(s):
    return html.escape(s or '', quote=True)


# ---------------------------------------------------------------------------
# playlists
# ---------------------------------------------------------------------------
def read_playlists(paths):
    chans = {}                                  # id -> dict(name, logo, group)
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            if not line.startswith('#EXTINF'):
                continue
            m = EXTINF.search(line.rstrip('\n'))
            if not m or not m.group(1):
                continue
            gid, logo, group, name = m.groups()
            chans.setdefault(html.unescape(gid), {'name': html.unescape(name), 'logo': html.unescape(logo),
                                                  'group': html.unescape(group)})
    return chans


def display_title(name):
    """'US: Music Choice 20 HD (2)' -> 'Music Choice 20';  '24/7 The Simpsons' -> 'The Simpsons'."""
    t = re.sub(r'\s*\(\d+\)$', '', name)
    t = re.sub(r'\s+(4K|FHD|HD|SD)$', '', t)
    t = re.sub(r'^(?:[A-Z]{2,3}): ', '', t)
    t = re.sub(r'^24/7\s+', '', t)
    return t.strip() or name


# ---------------------------------------------------------------------------
# published guides
# ---------------------------------------------------------------------------
def fetch(src, cache_dir):
    url = EPG_URLS.get(src)
    if not url:
        return None
    path = os.path.join(cache_dir, f'{src}.xml.gz')
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < SOURCE_HOURS * 3600:
        return path
    tmp = path + '.part'
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r, open(tmp, 'wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(tmp, path)
        log('downloaded', src, os.path.getsize(path) // 1024, 'KB')
    except Exception as e:
        log('download failed', src, e, '(using previous copy)' if os.path.exists(path) else '')
        if os.path.exists(tmp):
            os.remove(tmp)
    return path if os.path.exists(path) else None


def copy_programmes(path, wanted, out, lo, hi):
    """Stream one XMLTV file, writing programmes for wanted ids (and their shifted copies). Returns ids seen."""
    seen = set()
    opener = gzip.open if path.endswith('.gz') else open
    try:
        with opener(path, 'rb') as f:
            ctx = ET.iterparse(f, events=('start', 'end'))
            _, root = next(ctx)
            for ev, el in ctx:
                if ev != 'end':
                    continue
                if el.tag == 'programme':
                    cid = el.get('channel')
                    targets = wanted.get(cid)
                    if targets:
                        try:
                            start, stop = parse_xt(el.get('start')), parse_xt(el.get('stop') or el.get('start'))
                        except ValueError:
                            root.clear()
                            continue
                        for tid, shift in targets:
                            s2, e2 = start + timedelta(minutes=shift), stop + timedelta(minutes=shift)
                            if e2 < lo or s2 > hi:
                                continue
                            el.set('channel', tid)
                            el.set('start', xt(s2))
                            el.set('stop', xt(e2))
                            el.tail = '\n'
                            out.write(ET.tostring(el, encoding='unicode'))
                            seen.add(tid)
                    root.clear()
                elif el.tag == 'channel':
                    root.clear()
    except (ET.ParseError, OSError, EOFError) as e:
        log('could not read', os.path.basename(path), e)
    return seen


# ---------------------------------------------------------------------------
# generated listings
# ---------------------------------------------------------------------------
def event_parts(name):
    """'NFL 02: Jaguars vs Eagles (Oct 11 9:30 AM ET)' -> ('NFL 02', 'Jaguars vs Eagles', datetime|None)."""
    slot, _, text = name.partition(': ')
    if not text:
        return name, '', None
    when = None
    m = WHEN.search(text)
    if m:
        mon, day, hh, mm, ap, tz = m.groups()
        h = int(hh) % 12 + (12 if ap == 'PM' else 0)
        now = datetime.now(EASTERN)
        year = now.year
        try:
            when = datetime(year, MONTHS[mon], int(day), h, int(mm or 0), tzinfo=EASTERN)
        except ValueError:
            when = None
        if when:
            if (when - now).days > 180:
                when = when.replace(year=year - 1)
            elif (now - when).days > 180:
                when = when.replace(year=year + 1)
            if tz in TZ_OFFSET:
                when += timedelta(hours=TZ_OFFSET[tz])
            elif tz in ('UK', 'GMT', 'UTC', 'BST'):
                when = when.replace(tzinfo=timezone(timedelta(hours=1 if tz == 'BST' else 0)))
        text = text[:m.start()].strip()
    return slot.strip(), text.strip(' -'), when


def prog(cid, start, stop, title, desc=None):
    d = f'<desc lang="en">{esc(desc)}</desc>' if desc else ''
    return (f'<programme start="{xt(start)}" stop="{xt(stop)}" channel="{esc(cid)}">'
            f'<title lang="en">{esc(title)}</title>{d}</programme>\n')


def generated(cid, ch, lo, hi):
    """Listings for a channel with no published guide."""
    name, group = ch['name'], ch['group']
    day0 = lo.replace(minute=0, second=0, microsecond=0)
    out = []
    is_event = group == 'PPV & Events' or (group.startswith('Sports |') and re.match(r'^[^:]+ \d{1,3}(:|$)', name))
    if is_event:
        slot, text, when = event_parts(name)
        if not text:
            out.append(prog(cid, day0, hi, f'{slot}: no event scheduled',
                            'The provider has not listed an event on this channel yet.'))
            return out
        if when:
            end = when + timedelta(hours=EVENT_HOURS)
            if when > day0:
                out.append(prog(cid, day0, when, f'Up next: {text}', f'{text} starts at '
                                f'{when.astimezone(EASTERN).strftime("%-I:%M %p ET, %a %b %-d")}.'))
            out.append(prog(cid, max(when, day0), max(end, day0 + timedelta(hours=1)), text, f'{slot} - {text}'))
            if end < hi:
                out.append(prog(cid, max(end, day0 + timedelta(hours=1)), hi, f'{slot}: event ended',
                                f'Last event: {text}'))
        else:
            out.append(prog(cid, day0, hi, text, f'{slot} - {text}'))
        return out
    title = display_title(name)
    desc = {'24/7': f'Non-stop {title}.', 'Adult': None}.get(group, None)
    t = day0
    while t < hi:                                  # 6-hour blocks: looks normal in the grid, keeps the file small
        out.append(prog(cid, t, min(t + timedelta(hours=6), hi), title, desc))
        t += timedelta(hours=6)
    return out


# ---------------------------------------------------------------------------
def build(out_path, playlists, cache_dir=None):
    t0 = time.time()
    cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(out_path)), 'guide_sources')
    os.makedirs(cache_dir, exist_ok=True)
    chans = read_playlists(playlists)
    epg = EpgIndex()
    now = datetime.now(timezone.utc)
    lo, hi = now - timedelta(hours=KEEP_PAST_HOURS), now + timedelta(days=DAYS_AHEAD)

    wanted = {}                                   # source -> {base id: [(target id, shift minutes)]}
    for cid in chans:
        base, _, shift = cid.partition(SHIFT_SEP)
        src = epg.source_of.get(base)
        if src:
            wanted.setdefault(src, {}).setdefault(base, []).append((cid, int(shift or 0)))

    tmp = out_path + '.tmp'
    covered = set()
    with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=6) as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-playlist-cleaner">\n')
        for cid, ch in chans.items():
            icon = f'<icon src="{esc(ch["logo"])}"/>' if ch['logo'] else ''
            out.write(f'<channel id="{esc(cid)}"><display-name>{esc(display_title(ch["name"]))}</display-name>'
                      f'{icon}</channel>\n')
        for src, ids in sorted(wanted.items()):
            path = fetch(src, cache_dir)
            if path:
                got = copy_programmes(path, ids, out, lo, hi)
                covered |= got
                log(f'{src}: listings for {len(got)} of {sum(len(v) for v in ids.values())} channels')
        n_gen = 0
        for cid, ch in chans.items():
            if cid not in covered:                # no published guide, or the source had nothing for it
                for p in generated(cid, ch, lo, hi):
                    out.write(p)
                n_gen += 1
        out.write('</tv>\n')
    os.replace(tmp, out_path)
    log(f'{len(chans)} channels: {len(covered)} with published listings, {n_gen} generated '
        f'({os.path.getsize(out_path) // 1024} KB, {time.time() - t0:.0f}s)')
    return out_path


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2:])
