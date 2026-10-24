# -*- coding: utf-8 -*-
"""One way of writing event times: 'Arsenal vs Leeds (Oct 10 7:30 AM ET)'.

Providers write the start time of an event a dozen ways - 'Saturday, 10 October 2026 15:00',
'Sun 11 Oct 18:30 EDT (US)', 'UK Fri 11 Sep 7:50pm - ET Fri 11 Sep 2:50pm', 'start:2026 10 12 01:00:00 stop:...',
'- 6/13 08:30pm -', '11-10-2026 - 20:00 (GMT)', '1pm Vikings at Saints', 'Mansfield Town 15:00 Bromley 10/10'.
`normalise(text, label)` finds the time, takes it out of the text and puts it back at the end in Eastern time,
the form the guide builder reads to schedule the event. Times without a zone are read as UK time for British
and European competitions and as Eastern time otherwise.
"""
import re
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    EASTERN, LONDON = ZoneInfo('America/New_York'), ZoneInfo('Europe/London')
except Exception:                                        # no tz database: summer offsets
    EASTERN, LONDON = timezone(timedelta(hours=-4)), timezone(timedelta(hours=1))

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MON = {m.lower(): i + 1 for i, m in enumerate(MONTHS)}
MON.update({'sept': 9, 'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12})
DAY = r'(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)[a-z]*\.?'
MONTH = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?'
UK_LABELS = re.compile(r'^(EPL|EFL|SPFL|UEFA|GAA|Darts|PDC|Rugby|Super League|NIFL|Scottish|National League|'
                       r'Ligue 1|La ?Liga|Serie A|Bundesliga|Premier League|FA Cup|Carabao|Women.s Super League|'
                       r'WSL|Ulster|Tyrone|GAAGO|GAA TV|Soccer PPV|Pre-Season|LOI|League of Ireland|Cricket|'
                       r'Snooker|Racing|Viaplay|Stan|Rally|WRC|MotoGP|Cycling|Eurosport)', re.I)
ZONES = {'ET': EASTERN, 'EST': EASTERN, 'EDT': EASTERN, 'US': EASTERN, 'PT': -3, 'PST': -3, 'PDT': -3, 'CT': -1,
         'CST': -1, 'CDT': -1, 'MT': -2, 'MST': -2, 'MDT': -2, 'UK': LONDON, 'BST': LONDON, 'GMT': timezone.utc,
         'UTC': timezone.utc, 'CET': 'CET', 'CEST': 'CET'}
TZ = r'(?:\s*\(?\b(ET|EST|EDT|PT|PST|PDT|CT|CST|CDT|MT|MST|MDT|UK|BST|GMT|UTC|CET|CEST)\b\)?)?'
TIME = r'(\d{1,2})(?:[:.](\d{2}))?\s*([AaPp]\.?[Mm]\.?)?'


def _hour(h, mi, ap):
    h, mi = int(h), int(mi or 0)
    if ap:
        ap = ap.lower().replace('.', '')
        h = h % 12 + (12 if ap == 'pm' else 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return h, mi


def _zone(z, label):
    z = (z or '').upper()
    if z in ZONES:
        v = ZONES[z]
        if isinstance(v, int):                          # Pacific/Central/Mountain: hours behind Eastern
            return ('ET+', -v)
        if v == 'CET':
            try:
                return ZoneInfo('Europe/Paris')
            except Exception:
                return timezone(timedelta(hours=2))
        return v
    return LONDON if UK_LABELS.search(label or '') else EASTERN


def _make(y, mo, d, hm, z, label, now):
    if not hm:
        return None
    if y is None:                                       # no year: the nearest one to today
        y = now.year
        try:
            cand = datetime(y, mo, d)
        except ValueError:
            return None
        if (cand - now.replace(tzinfo=None)).days > 180:
            y -= 1
        elif (now.replace(tzinfo=None) - cand).days > 180:
            y += 1
    try:
        naive = datetime(int(y), int(mo), int(d), hm[0], hm[1])
    except ValueError:
        return None
    zone = _zone(z, label)
    if isinstance(zone, tuple):                          # 'PT' etc.
        return naive.replace(tzinfo=EASTERN) + timedelta(hours=zone[1])
    return naive.replace(tzinfo=zone).astimezone(EASTERN)


def _today(hm, z, label, now, weekday=None):
    """A time with no date: today (Eastern), or the next such weekday."""
    zone = _zone(z, label)
    base = now.astimezone(EASTERN)
    d = base.date()
    if weekday is not None:
        d = d + timedelta(days=(weekday - d.weekday()) % 7)
    naive = datetime(d.year, d.month, d.day, hm[0], hm[1])
    if isinstance(zone, tuple):
        dt = naive.replace(tzinfo=EASTERN) + timedelta(hours=zone[1])
    else:
        dt = naive.replace(tzinfo=zone).astimezone(EASTERN)
    return dt


def fmt(dt):
    h = dt.hour % 12 or 12
    return f'({MONTHS[dt.month - 1]} {dt.day} {h}:{dt.minute:02d} {"AM" if dt.hour < 12 else "PM"} ET)'


WEEKDAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}

# (pattern, function(match, label, now) -> datetime) tried in order; the first one found wins
_P = []


def _rule(rx):
    def deco(fn):
        _P.append((re.compile(rx, re.I), fn))
        return fn
    return deco


@_rule(r'^(.+?)\s+(\d{1,2})[:.](\d{2})\s+(.+?)\s+(\d{1,2})/(\d{1,2})$')
def _efl(m, label, now):                                # 'Mansfield Town 15:00 Bromley (L1) 10/10' (day/month, UK time)
    a, h, mi, b, d, mo = m.groups()
    dt = _make(None, int(mo), int(d), _hour(h, mi, None), 'UK', label, now)
    return (dt, f'{a} vs {b}') if dt else None


@_rule(r'(?:^|(?<=\s))(' + DAY + r')\s+(\d{1,2})(?:st|nd|rd|th)\s+' + TIME + TZ)
def _day_nth(m, label, now):                            # 'Sun 6th 7:00pm': this month (or next) on that day
    wd, d, h, mi, ap, z = m.groups()
    hm = _hour(h, mi, ap)
    if not hm:
        return None
    base = now.astimezone(EASTERN)
    mo, y = base.month, base.year
    if int(d) < base.day - 7:
        mo, y = (1, y + 1) if mo == 12 else (mo + 1, y)
    return _make(y, mo, int(d), hm, z, label, now)


@_rule(r'\bUK\s+' + DAY + r'\s+\d{1,2}\s+' + MONTH + r'\s+' + TIME + r'\s*-\s*ET\s+' + DAY + r'\s+(\d{1,2})\s+(' + MONTH + r')\s+' + TIME)
def _uk_et(m, label, now):                              # 'UK Fri 11 Sep 7:50pm - ET Fri 11 Sep 2:50pm'
    g = m.groups()
    return _make(None, MON[g[4][:3].lower()], int(g[3]), _hour(g[5], g[6], g[7]), 'ET', label, now)


@_rule(r'\bstart:\s*(20\d\d)[ -](\d\d)[ -](\d\d)\s+(\d\d):(\d\d)(?::\d\d)?(?:\s*stop:\s*20\d\d[ -]\d\d[ -]\d\d\s+\d\d:\d\d(?::\d\d)?)?')
def _startstop(m, label, now):                          # 'start:2026 10 12 01:00:00 stop:2026 10 12 08:13:20' (UTC)
    y, mo, d, h, mi = m.groups()
    return _make(int(y), int(mo), int(d), (int(h), int(mi)), 'UTC', label, now)


@_rule(DAY + r',?\s+(\d{1,2})(?:st|nd|rd|th)?\s+(' + MONTH + r'),?\s+(20\d\d)?\s*(?:at\s+|-\s*)?' + TIME + TZ)
def _day_d_month(m, label, now):                        # 'Saturday, 10 October 2026 15:00', 'Sun 11 Oct 18:30 EDT'
    d, mon, y, h, mi, ap, z = m.groups()
    return _make(int(y) if y else None, MON[mon.rstrip('.').lower()[:3] if mon.lower()[:4] != 'sept' else 'sep'],
                 int(d), _hour(h, mi, ap), z, label, now)


@_rule(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(' + MONTH + r'),?\s+(20\d\d)?\s*(?:at\s+|-\s*)?' + TIME + TZ)
def _d_month(m, label, now):                            # '5 May 2:00pm', '22 Mar 17:35'
    d, mon, y, h, mi, ap, z = m.groups()
    if not (mi or ap):
        return None
    return _make(int(y) if y else None, MON[mon.rstrip('.').lower()[:3]], int(d), _hour(h, mi, ap), z, label, now)


@_rule(r'\(?\b(' + MONTH + r')\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:(20\d\d)\s+)?' + TIME + TZ + r'\)?')
def _month_d(m, label, now):                            # '(Oct 11 1:00 PM ET)', 'Oct 10 7:20 AM'
    mon, d, y, h, mi, ap, z = m.groups()
    if not (mi or ap):
        return None
    return _make(int(y) if y else None, MON[mon.rstrip('.').lower()[:3]], int(d), _hour(h, mi, ap), z, label, now)


@_rule(r'\b(\d{1,2})-(\d{1,2})-(20\d\d)\s*-?\s*(\d{1,2}):(\d{2})' + TZ)
def _dmy(m, label, now):                                # '11-10-2026 - 20:00 (GMT)' (day first)
    d, mo, y, h, mi, z = m.groups()
    return _make(int(y), int(mo), int(d), _hour(h, mi, None), z, label, now)


@_rule(r'(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(?:20)?\d\d)?\s*,?\s*' + TIME + TZ + r'(?=\s*[-,)]|\s*$|\s+[A-Z(])')
def _md_time(m, label, now):                            # '6/13 08:30pm', '12/02 2:05pm,' (US month first)
    a, b, h, mi, ap, z = m.groups()
    if not (mi or ap):
        return None
    mo, d = (int(a), int(b)) if not UK_LABELS.search(label or '') else (int(b), int(a))
    if mo > 12:
        mo, d = d, mo
    return _make(None, mo, d, _hour(h, mi, ap), z, label, now)


@_rule(r'(?:^|(?<=\s)|(?<=-))(?:(' + DAY + r')\s+)?(\d{1,2})(?:[:.](\d{2}))\s*([AaPp]\.?[Mm]\.?)?' + TZ + r'(?:\s+(' + DAY + r'))?(?=\s|$|\)|,)')
def _clock(m, label, now):                              # '8:00 pm', '15:00', '15.00', 'Sun 18:00', '5:35am Sun'
    d1, h, mi, ap, z, d2 = m.groups()
    hm = _hour(h, mi, ap)
    if not hm:
        return None
    wd = d1 or d2
    return _today(hm, z, label, now, WEEKDAYS.get(wd[:3].lower()) if wd else None)


@_rule(r'\[(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})\]')
def _bracket_dm(m, label, now):                         # 'Rally TV Live [23.09 14:35]' (day.month)
    d, mo, h, mi = m.groups()
    return _make(None, int(mo), int(d), _hour(h, mi, None), None, label, now)


@_rule(r'(?:^|(?<=\s))(\d{1,2})(\d{2})\s*([AaPp][Mm])' + TZ + r'(?=\s|$|\))')
def _hhmm_ampm(m, label, now):                          # '415PM', '1245PM'
    h, mi, ap, z = m.groups()
    hm = _hour(h, mi, ap)
    return _today(hm, z, label, now) if hm else None


@_rule(r'(?:^|(?<=\s))(\d{1,2})\s*([AaPp][Mm])' + TZ + r'(?=\s|$|\))')
def _hour_only(m, label, now):                          # '1pm Vikings at Saints'
    h, ap, z = m.groups()
    return _today(_hour(h, None, ap), z, label, now)


def normalise(text, label=None, now=None):
    """Return the event text with its start time (if any) written once, at the end, in Eastern time."""
    if not text:
        return text
    now = now or datetime.now(timezone.utc)
    for rx, fn in _P:
        m = rx.search(text)
        if not m:
            continue
        try:
            dt = fn(m, label, now)
        except (ValueError, KeyError, TypeError):
            dt = None
        if not dt:
            continue
        rest = None
        if isinstance(dt, tuple):
            dt, rest = dt
        rest = rest or (text[:m.start()] + ' ' + text[m.end():])
        rest = re.sub(r'(?:^|\s)' + DAY + r'\s+\d{1,2}(?:st|nd|rd|th|n)?(?=\s|$)', ' ', rest)   # leftover 'Sat 10n'
        rest = re.sub(r'\s*\((?:US|UK)\)\s*', ' ', rest)
        rest = re.sub(r'(?<!\w)(?:\d{1,2}/\d{1,2})(?!\w)', ' ', rest) if fn in (_clock, _hour_only) else rest
        rest = re.sub(r'\s*-\s*(?:' + DAY + r')?\s*(?=-|$)', ' ', rest)       # '... - Mon', '... -'
        rest = re.sub(r'\s+-\s+(?=\()', ' ', rest)
        rest = re.sub(r'\s+:', ':', rest)
        rest = re.sub(r'^\s*[-,:|]\s*|\s*[-,:|]\s*$', '', rest.strip())
        rest = re.sub(r'\s{2,}', ' ', rest).strip(' -,')
        rest = re.sub(r'\(\s*\)', '', rest).strip()
        return f'{rest} {fmt(dt)}'.strip()
    return text


VS = re.compile(r'(?<=\w)\s+(?:v|V|v\.|vs\.?|VS\.?|Vs\.?|x|X)\s+(?=[A-Z0-9#])')


def tidy_matchup(text):
    """'Arsenal v Leeds', 'Arsenal vs. Leeds', 'Dodgers x Brewers' -> 'Arsenal vs Leeds'."""
    return VS.sub(' vs ', text)
