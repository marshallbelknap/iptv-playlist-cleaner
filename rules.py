# -*- coding: utf-8 -*-
"""Classification and naming rules for the playlist cleanup.

Everything here is pure data or pure functions so the same rules can be
re-applied to a fresh copy of the provider playlist at any time.
"""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Output group names
# ---------------------------------------------------------------------------
COUNTRY_ORDER = ['US', 'CA', 'UK', 'IE', 'AU', 'NZ', 'ZA']
CATEGORY_ORDER = ['Locals', 'News', 'Sports', 'Movies', 'General', 'Music']


def country_group(cc, cat):
    return f'{cc} | {cat}'


def sports_group(label):
    return f'Sports | {label}'


PPV_GROUP = 'PPV & Events'
G247 = '24/7'
ADULT_GROUP = 'Adult'

# ---------------------------------------------------------------------------
# Country prefixes found in names
# ---------------------------------------------------------------------------
ENGLISH_CC = {
    'US': 'US', 'USA': 'US', 'UK': 'UK', 'GB': 'UK', 'CA': 'CA', 'CAN': 'CA',
    'AU': 'AU', 'AUS': 'AU', 'NZ': 'NZ', 'IRE': 'IE', 'IE': 'IE', 'ZA': 'ZA',
}
# Spanish-language US stations (Univision, UniMas, Telemundo, Estrella, Azteca and affiliates)
SPANISH_CALLS = set('''
WXTV KMEX WGBO KDTV KUVN WLTV KXLN KFTV KUVS KUVE WUVG WUNI KWEX KABE KINT KUVI KREN KLUZ KTVW KVYE WVEA WUVP
WVEN WUVC KUTH KNVO KUVN KUVM KUNP KUNS KVER KVSN KAKW KCEC KUVO KLDO KORO KETF KAJB KESE KREN KRNS KPYX
WFUT KFTR WXFT KSTR KFTH WAMI KFSF KTFQ KTFD KTFF WUTF KTFV KTFU KTFK WFPA WFTT KTFN KTFO KTFH
WNJU KVEA WSNS KTMD KXTX WSCV KSTS KDEN KHRR KTAZ KNSO KBLR KTDO WKAQ WWSI WRMD WZTD KVDA KUAN KTLM KJTL
KSWT WTMO WWDT WNEU KCSO KMAS KPDF KMUV KNIC KEUV KVTF WRDC KWHY KRCA KZJL KMPX KAZA KJLA KBNT KXOS
KUVI KNIC WLII WSJN WAPA WUNI KQCW
'''.split())
SPANISH_CALLS.discard('KQCW')
FOREIGN_CC = {
    'AR', 'IN', 'IT', 'UA', 'PT', 'FR', 'ES', 'RU', 'CN', 'GR', 'PH', 'DE',
    'VN', 'JP', 'MX', 'BR', 'IL', 'PL', 'TR', 'KR', 'ZH', 'NL', 'SE', 'NO',
    'DK', 'FI', 'AL', 'RO', 'HU', 'CZ', 'HR', 'RS', 'BG', 'PK', 'BD', 'LK',
    'TH', 'ID', 'MY', 'KZ', 'EX', 'LATIN', 'CARIB', 'ASIAN', 'ARABIC',
    'TAIWANESE', 'POLISH', 'CAN', 'KURDISH', 'PERSIAN', 'AFRIKAANS', 'SOMALI',
}
PLUTO_REGIONS = {'USA': 'US', 'US': 'US', 'UK': 'UK', 'CA': 'CA', 'AU': 'AU',
                 'Canada': 'CA', 'Australia': 'AU'}

# Provider "source" tags that carry no meaning for the viewer.
SOURCE_TAGS = {
    'A', 'H', 'S', 'D', 'F', 'P', 'E', 'M', 'X', 'FL', 'PM', 'PC', 'FD', 'TB',
    'HX', 'F2', 'D3', 'CX', 'X2', 'TO', 'SP', 'GT', 'RK', 'STV', 'Rakuten',
    'Backup', 'B', 'C', 'G', 'L', 'N', 'R', 'T', 'V', 'Z', 'FOX1', 'GLB',
    'CITY', 'CBC', 'MC', 'Feed', 'Feeds', 'Live', 'Source', 'TUBI', 'Prime',
    'DZ', 'KAYO', 'Zone1', 'Zone2', 'Zone3', 'Main', 'ALT', 'Alt', 'VIP',
    'Faith', 'NEW', 'New', 'Plex', 'PLEX', 'XUMO', 'Xumo', 'Samsung',
}
# Service tags we keep as meaning (mapped to a readable suffix or dropped)
SERVICE_TAGS = {'RK': 'Roku', 'TUBI': 'Tubi', 'Prime': 'Prime Video',
                'GT': None, '7Plus': '7plus', '9Now': '9Now', 'SBS': None,
                'ABC': None}

# ---------------------------------------------------------------------------
# Non-English detection (dropped). Matched case-insensitively on whole words.
# ---------------------------------------------------------------------------
NON_ENGLISH_WORDS = [
    # Spanish / Portuguese / Latin American
    'telemundo', 'univision', 'unimas', 'unimás', 'galavision', 'galavisión',
    'tudn', 'estrella', 'estrellatv', 'azteca', 'universo', 'cinelatino',
    'cine latino', 'latino', 'pasiones', 'tyc', 'telefe', 'video rola',
    'hola tv', '¡hola', 'vme', 'ntn24', 'española', 'espanol', 'español',
    'en español', 'deportes', 'vix', 'wapa', 'tr3s', 'nuestra tele',
    'meganoticias', 'hogar de hgtv', 'discovery familia', 'sorpresa',
    'bandamax', 'de pelicula', 'de película', 'telehit', 'noticias', 'mi gente',
    'caracol', 'venevision', 'antena 3', 'rcn', 'ecuavisa', 'teleformula',
    'telefórmula', 'imagen tv', 'multimedios', 'jaripeo', 'cine mexicano',
    'cinema dinamita', 'exitos', 'éxitos', 'cinemáx', 'tlnovelas', 'canal 6',
    'milenio', 'adn noticias', 'claro sports', 'azteca uno', 'tv española',
    'televisa', 'las estrellas', 'unicable', 'distrito comedia', 'pantaya',
    'ritmoson', 'clic', 'cine sony', 'sony cine', 'cinecanal', 'tnt series latin',
    'globo', 'record tv', 'sbt', 'portugal', 'rtp', 'sic ',
    'canal+', 'canal plus', 'chilevision', 'tvn chile', 'telemicro',
    'tele antillas', 'cdn', 'tele 3', 'enlace', 'esne', 'ewtn espanol',
    'latin pop', 'reggaeton', 'adrenalina', 'musica', 'música', 'manorama', 'ndtv india', 'latinus', 'tvbj', 'hum europe', 'hum news', 'hum masala', 'hum sitaray', 'sony tv', 'sony entertainment', 'cine de oro', 'en espanol', 'películas', 'peliculas', 'telemundo al dia', 'cine de', 'fntz', 'fanatiz', 'mexicana', 'méxico', 'colombia',
    'argentina tv', 'venezuela', 'novelas', 'telenovela',
    # French (Canada / France)
    'tva', 'noovo', 'rds', 'rds2', 'rds info', 'télé-québec', 'tele quebec',
    'télé québec', 'radio-canada', 'ici tele', 'ici télé', 'ici rdi', 'ici art',
    'ici artv', 'ici explora', 'rdi', 'lcn', 'super ecran', 'super écran',
    'canal d', 'canal vie', 'vrak', 'ztélé', 'ztele', 'z télé', 'historia',
    'series+', 'séries+', 'casa', 'évasion', 'evasion', 'prise 2', 'unis',
    'tv5', 'tv5monde', 'télémag', 'telemag', 'matv', 'ma tv', 'savoir',
    'canal savoir', 'tfo', 'teletoon french', 'télétoon', 'yoopa', 'planete+', 'planète+', 'cinepop', 'cinépop', 'telelatino',
    'tln', 'assemblee nationale', 'assemblée nationale', 'franco', 'vrai',
    'moi et cie', 'moi&cie', 'tele v', 'télé v', 'qub', 'le canal nouvelles',
    'canal savoir', 'ztélé', 'explora', 'artv', 'ici',
    # Indian sub-continent / Asian / Middle East
    'zee', 'colors', 'star plus', 'star bharat', 'star gold', 'star utsav',
    'sony sab', 'sony max', 'set india', 'aaj tak', 'abp', 'news18', 'dangal',
    'dharm', 'gurbaani', 'gurbani', 'sanjha', 'diya tv', 'shemaroo', 'saga music',
    'punjabi', 'punajb', 'haryanvi', 'bangla', 'tamil', 'telugu', 'malayalam',
    'kannada', 'marathi', 'gujarati', 'hindi', 'urdu', 'bollywood', 'pitaara',
    'geo tv', 'geo kahani', 'geo news', 'ary', 'hum tv', 'ptv', 'asianet',
    'jhakaas', 'awaz', 'desi', 'utsav', 'b4u', 'aastha', 'sanskar', 'iqra',
    'noor tv', 'eman channel', 'islam tv', 'deen tv', 'takbeer', 'madani',
    'peace tv urdu', 'jus punjabi', 'chardikla', 'akaal', 'sangat', 'mh one',
    'star jalsha', 'sun tv', 'vijay', 'gemini', 'kalaignar', 'polimer',
    'jaya tv', 'raj tv', 'ptc', 'chsTV', 'chstv', 'kapatid', 'tfc', 'gma pinoy',
    'myx', 'abs-cbn', 'alto broadcasting', 'fairchild', 'omni', 'cctv', 'icitі',
    'iciti', 'tvb', 'mbc', 'rotana', 'lbci', 'al jadeed',
    'nbn', 'aghapy', 'sky news arabia', 'al mamlaka', 'palestine', 'senses tv',
    'al horreya', 'art cima', 'art aflam', 'al arabiya', 'alhurra', 'iqraa',
    'kurd', 'farsi', 'persian', 'manoto', 'gem tv', 'turk', 'türk', 'trt 1',
    'kanal d', 'arirang tv korean', 'kbs', 'sbs korea',
    'tvbs', 'cti', 'ettv', 'nhk japanese', 'vos marv', 'la 7', 'rai', 'mediaset',
    'canale 5', 'italia 1', 'rete 4', 'sky tg24', 'polsat', 'tvp', 'tvn24',
    'polonia', 'prosieben', 'sat.1', 'rtl', 'ard', 'zdf', 'orf', 'srf',
    'odyssey', 'greek cinema', 'ert', 'skai', 'ant1', 'ukraine', 'ukrainian',
    'russian', 'pervyi', 'rossiya', 'ntv mir', 'trace ayiti', 'trace urban french',
    'trace african french', 'trace sports stars french', 'euronews portuguese',
    'euronews português', 'euronews español', 'telesur', 'hispan', 'spanish',
    'latina', 'latin', 'carib', 'asian', 'arabic', 'taiwanese', 'polish',
    'french', 'francais', 'français', 'german', 'deutsch', 'italian', 'italiano',
    'portuguese', 'português', 'brasil', 'brazil', 'korean', 'chinese', 'mandarin',
    'cantonese', 'japanese', 'hebrew', 'thai', 'vietnamese', 'filipino', 'tagalog',
    'qazaqstan', 'kazakh',
]
# Words that look non-English above but are fine in these contexts
NON_ENGLISH_EXCEPTIONS = [
    'latin jazz', 'trace urban english', 'trace african english',
    'trace sports stars english', 'french open', 'french quarter',
]
_NON_EN_RE = re.compile(r'(?<![\w])(' + '|'.join(sorted(
    (re.escape(w) for w in NON_ENGLISH_WORDS), key=len, reverse=True)) + r')(?![\w])',
    re.I)

# Hard-coded English allowlist inside otherwise foreign-tagged sources
ENGLISH_INTL = re.compile(
    r"\b(ndtv 24 ?x ?7|india today|wion|times now( world)?|et now|cgtn( documentary)?|"
    r"france ?24 english|euronews english|dw english|nhk world|al jazeera english|"
    r"arirang|trt world|i24 english|trace (urban|african|sports stars) english|"
    r"travel ?xp|aquarium tv|fireplace tv|cars n stars|real world poker|"
    r"reelpx (family|unlimited) english|jewish life tv|infotainment tv|whats the tea|"
    r"m&e tv|mtm|afro music pop|newsmax(?! en))\b", re.I)

JUNK_RE = re.compile(
    r'(signal test|atomizertest|slatepo\d*|backhaul test|internal use|^test\b|'
    r'\btest channel\b|dummy|placeholder|do not use|\bzzz\b(?! ?offline))', re.I)

# ---------------------------------------------------------------------------
# Casing
# ---------------------------------------------------------------------------
ACRONYMS = set('''
ABC CBS NBC FOX CW PBS MNT ESPN ESPNU ESPN2 ESPNEWS CNN HLN HBO AMC TBS TNT TLC HGTV BET MTV MTV2 MTVU
VH1 CMT FX FXX FXM IFC OWN GSN AXS USA UK US TV BBC ITV ITV1 ITV2 ITV3 ITV4 STV RTE BT NFL NBA MLB NHL
WNBA MLS EPL EFL UEFA UFC WWE AEW PPV NCAA NCAAF NCAAB SEC ACC BTN CBSN MSNBC CNBC CSPAN QVC HSN DIY
NASA PGA LPGA ATP WTA F1 TSN CTV CTV2 CBC APTN CP24 BNN CPAC TVO SBS NITV NZ TVNZ GB CNA NHK CGTN DW
RT TRT ION INSP TCM LMN OAN NESN MSG SNY MASN NBCSN BYU EWTN TBN CBN NRB TYT LFC MUTV S4C
TG4 UTV FYI HD FHD SD UHD 4K II III IV DC NY KC TV2 TV3 OHL WHL QMJHL CHL PWHL SPHL ECHL KHL AHL
MLBN NBATV NHLN BIG10 PDC GAA MOTOGP WRC NASCAR IMSA INDYCAR AFL NRL ICC IPL CFL USL NWSL ACCN SECN
PBA ABC7 AMC+ BBC1 BBC2 BBC3 BBC4 E4 TJC QVC2 QVC3 CBBC DMAX AT&T WGN CTVN HSN2 CBSSN
NBCLX TVG TVG2 VSIN VSiN DTV CGTN ESPN+ DAZN PBC XFL UFL WBC IBF WBO WTT LIV TGL BKFC PFL ARY
MLBTV EPIX HDNET AXN NCIS CSI JAG FBI SWAT TMNT ER NDTV TVSN UCLA LSU USC SMU TCU UCF UNLV UTEP UTSA
UAB FIU FAU VMI UNC FCS FBS ACCNX SNL WE TV EN SEC CTV MSGSN BNN TSN1 TSN2 TSN3 TSN4 TSN5 NBA2K NWSL USWNT
USMNT CONCACAF FIBA FIFA FIA WEC IFAF ESPNU PBS MTV NHRA AMA UFC WTA PDC ECHL OJHL BCHL CEBL OUA ARCA SRX
CBSN NBCLX HBO2 TVA RDS NHLN NFLN MLBN WWE2 WPT HSN BBCA BBCW TBN CTN AFN NBA GB AM PM ET PT EDT EST CT MMA GPB NTV AFC FC SC CF RB PBR KPBS WTTW TNA ERC TAB NDRC GAC RFD TVC TVB HPI NBCSN UHD
'''.split())
SMALL_WORDS = {'a', 'an', 'and', 'at', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'vs', 'with', 'v'}
SPECIAL_CASE = {
    'MSNOW': 'MS NOW', 'SYFY': 'Syfy', 'REELZ': 'Reelz', 'TRUTV': 'truTV', 'TVLAND': 'TV Land',
    'IFILM': 'iFilm', 'FYI': 'FYI', 'E!': 'E!', 'METV': 'MeTV', 'IONTV': 'ION', 'FETV': 'FETV',
    'BOUNCE': 'Bounce', 'COZI': 'Cozi', 'GETTV': 'getTV', 'UPTV': 'UPtv', 'OXYGEN': 'Oxygen',
    'MAGNOLIA': 'Magnolia', 'NICKTOONS': 'Nicktoons', 'TEENNICK': 'TeenNick', 'NICKJR': 'Nick Jr.',
    'DISNEYXD': 'Disney XD', 'MOVIEPLEX': 'MoviePlex', 'RETROPLEX': 'RetroPlex',
    'INDIEPLEX': 'IndiePlex', 'SCREENPIX': 'ScreenPix', 'MGM+': 'MGM+', 'ESPNEWS': 'ESPNews',
    'TCM': 'TCM', 'CINEMAX': 'Cinemax', 'STARZ': 'Starz', 'SHOWTIME': 'Showtime',
    'NEWSMAX': 'Newsmax', 'NEWSNATION': 'NewsNation', 'MTV2': 'MTV2', 'DABL': 'Dabl',
    'U&DAVE': 'U&Dave', 'U&GOLD': 'U&Gold', 'U&W': 'U&W', 'U&YESTERDAY': 'U&Yesterday',
    'U&ALIBI': 'U&Alibi', 'U&DRAMA': 'U&Drama', 'MORE4': 'More4', 'FILM4': 'Film4',
    'E4': 'E4', '4SEVEN': '4seven', 'CBEEBIES': 'CBeebies', 'CBBC': 'CBBC',
    'QUEST': 'Quest', 'DMAX': 'DMAX', 'PBSKIDS': 'PBS Kids', 'ESPNU': 'ESPNU',
    'DAZN': 'DAZN', 'PPV': 'PPV', 'MCS': 'MCS', 'WWE': 'WWE', 'TSN': 'TSN', 'BEIN': 'beIN',
    'SHOXBET': 'SHOxBET', 'JR': 'Jr', 'JR.': 'Jr.', 'TVONTARIO': 'TVOntario', 'IHEARTRADIO': 'iHeartRadio',
    'IHEART': 'iHeart', 'HGTV': 'HGTV', 'ESPNEWS': 'ESPNews', 'MSNBC': 'MSNBC', 'NICK': 'Nick',
    'CNNI': 'CNNi', 'XTRA': 'Xtra', 'TV': 'TV', 'MCNEESE': 'McNeese', 'MCDONALD': 'McDonald',
    'DIRTVISION': 'DIRTVision', 'FLOSPORTS': 'FloSports', 'NEWSNOW': 'NewsNow',
}
PHRASE_FIX = [
    (r'(?i)\bla ?liga\b', 'LaLiga'), (r'\bTNT Sport (\d)', r'TNT Sports \1'),
    (r'\bMain Events\b', 'Main Event'), (r'\bLeauge\b', 'League'),
    (r'\bE! Entertainment Television\b', 'E!'), (r'\bThe Learning Channel\b', 'TLC'),
    (r'\bNick JR\b', 'Nick Jr'), (r'\bMcneese\b', 'McNeese'), (r'\bEL Rey\b', 'El Rey'),
    (r'\bSKy\b', 'Sky'), (r'\s+\+(?=\s|$)', '+'), (r'(?i)\b24 ?x ?7\b', '24x7'), (r'(?i)\bbein\b', 'beIN'),
    (r'\(\s+', '('), (r'\s+\)', ')'), (r'\bStarzkids\b', 'Starz Kids'), (r'\bHpitv\b', 'HPItv'),
    (r'\b(\w+) \(\1\)', r'\1'),
    (r'\bTSN ?([1-5])\b', r'TSN\1'), (r'\bSportsnet ONE\b', 'Sportsnet One'), (r'\bSportsnet WORLD\b', 'Sportsnet World'),
    (r'\bSPORTSNET\b', 'Sportsnet'), (r'\bNick\.JR\b', 'Nick Jr.'),
    (r'(?<![&\w])AT(?![&\w])', 'at'), (r'(?<![&\w])VS\.?(?![&\w])', 'vs'), (r'(?i)\bms now\b', 'MS NOW'), (r'(?i)\bmsgsn\b', 'MSGSN'), (r'(?i)\bnbc lx\b', 'NBC LX'),
    (r'(?i)\bc span ?(\d)?', lambda m: 'C-SPAN' + (' ' + m.group(1) if m.group(1) else '')),
    (r'(?i)\bcspan ?(\d)?', lambda m: 'C-SPAN' + (' ' + m.group(1) if m.group(1) else '')),
]


def _word_case(w, first):
    if '/' in w and len(w) > 3:
        return '/'.join(_word_case(p, first and i == 0) for i, p in enumerate(w.split('/')))
    if w.endswith('+1') and len(w) > 2:
        return _word_case(w[:-2], first) + '+1'
    core = w.strip('()[]:,.-"\'')
    up = core.upper()
    if not core:
        return w
    if up in SPECIAL_CASE:
        return w.replace(core, SPECIAL_CASE[up])
    if up in ACRONYMS:
        return w.replace(core, up)
    if w.startswith('(') and core.isupper() and len(core) <= 4:
        return w                            # (NSW) (QLD) (MA)
    if re.fullmatch(r'MC[A-Z]{3,}', up):
        return w.replace(core, 'Mc' + core[2:3].upper() + core[3:].lower())
    if re.fullmatch(r'[KW][A-Z]{2,3}(-?(TV|DT|LD|CD|CA|D\d?))?', up) and len(core) >= 4:
        return w.replace(core, up)          # US call sign
    if re.fullmatch(r'C[BFHIJK][A-Z]{2}(-?(TV|DT))?', up) and up not in ('CHEF', 'CHIC', 'CHAT', 'CHOP', 'CITY', 'CINE', 'CIAO', 'CHAN', 'CHIP'):
        return w.replace(core, up)          # Canadian call sign
    if re.fullmatch(r"\d{2,4}'?S", up):
        return w.replace(core, core[:-1] + 's')          # 70S -> 70s
    if re.fullmatch(r'\d+(ST|ND|RD|TH)', up):
        return w.replace(core, core.lower())             # 1ST -> 1st
    if re.search(r'\d', core) and len(core) <= 5:
        return w.replace(core, up)          # E4, 5USA, TV3, B2
    if not first and core.lower() in SMALL_WORDS:
        return w.replace(core, core.lower())
    if "'" in core:
        parts = core.split("'")
        return w.replace(core, "'".join([parts[0].capitalize()] + [p.lower() for p in parts[1:]]))
    if '&' in core and len(core) <= 4:
        return w.replace(core, up)
    return w.replace(core, core[:1].upper() + core[1:].lower())


def smart_case(s, aggressive=True):
    """Fix SHOUTED text while leaving intentional mixed case alone."""
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return s
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    words = s.split(' ')
    if upper_ratio >= 0.8:
        out = ' '.join(w if (not aggressive and len(w.strip('()[]:,.-@')) <= 3) else _word_case(w, i == 0)
                       for i, w in enumerate(words))
    elif not aggressive:
        out = s
    else:
        res = []
        for i, w in enumerate(words):
            core = w.strip('()[]:,.-+')
            up = core.upper()
            if len(core) >= 3 and re.fullmatch(r"[A-Z&/']+", core) and up not in ACRONYMS \
                    and not (w.startswith('(') and up in US_STATES):
                res.append(_word_case(w, i == 0))
            elif len(core) >= 3 and core.isalpha() and core == core.capitalize() and \
                    (up in ACRONYMS or up in SPECIAL_CASE):
                res.append(_word_case(w, i == 0))
            else:
                res.append(w)
        out = ' '.join(res)
    if aggressive and len(out.split()) >= 2:
        out = ' '.join(w[:1].upper() + w[1:] if (len(w) >= 3 and w.isalpha() and w.islower() and
                                                   (i == 0 or w not in SMALL_WORDS)) else w
                       for i, w in enumerate(out.split(' ')))
    for pat, rep in PHRASE_FIX:
        out = re.sub(pat, rep, out)
    return out


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------
SMALLCAPS = str.maketrans('ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡʏᴢ', 'ABCDEFGHIJKLMNOPQRSTUVWYZ')


def basic_clean(t):
    t = unicodedata.normalize('NFC', t)
    t = t.translate(SMALLCAPS)
    t = re.sub(r'[⁦-⁩​-‏﻿]', '', t)   # bidi / zero-width
    t = t.replace('ⓧ', '').replace('★', '').replace('✪', '').replace('●', '')
    t = t.replace('`', "'").replace('’', "'").replace('–', '-').replace('—', '-')
    t = re.sub(r'\s+', ' ', t).strip()
    return t


QUALITY_RE = re.compile(
    r'(?<![\w])(4K|UHD|FHD|1080[pi]?|HD|720p|SD|480p|360p|HEVC|H\.?265|50 ?FPS|60 ?FPS|HQ|LQ)(?![\w])', re.I)
BITRATE_RE = re.compile(r'\(\s*(\d{3,4})p\d*\s*@[^)]*\)', re.I)


def extract_quality(t):
    """Return (text_without_quality_tokens, quality or None)."""
    br = BITRATE_RE.search(t)
    if br:
        t = BITRATE_RE.sub(' ', t) + ' ' + {'1080': 'FHD', '720': 'HD'}.get(br.group(1), 'SD')
    t = re.sub(r'\(\s*(?:UHD|4K)\s*/\s*(?:UHD|4K)\s*\)', ' 4K ', t, flags=re.I)
    found = [m.group(1).upper().replace(' ', '') for m in QUALITY_RE.finditer(t)]
    q = None
    if any(f in ('4K', 'UHD') for f in found):
        q = '4K'
    elif any(f in ('FHD', '1080P', '1080I', '1080') for f in found):
        q = 'FHD'
    elif any(f in ('HD', '720P') for f in found):
        q = 'HD'
    elif any(f in ('SD', '480P', '360P') for f in found):
        q = 'SD'
    t = QUALITY_RE.sub(' ', t)
    t = re.sub(r'\(\s*[/|&,-]?\s*\)', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' -|:')
    return t, q


TAIL_TAG_RE = re.compile(r'\s*\((?:' + '|'.join(sorted(map(re.escape, SOURCE_TAGS), key=len, reverse=True)) +
                         r')\)\s*$')


INNER_TAG_RE = re.compile(r'\s\((?:A|H|S|D|F|P|E|M|X|FL|PM|PC|FD|TB|HX|F2|D3|CX|X2|TO|SP|GT|RK|HQ|Alt|ALT|Backup|Zone\d)\)(?=\s|$)')


def strip_tail_tags(t):
    t = INNER_TAG_RE.sub(' ', t)
    prev = None
    while prev != t:
        prev = t
        t = TAIL_TAG_RE.sub('', t).strip()
        t = re.sub(r'\s+(Source|Backup|Feeds?)$', '', t, flags=re.I)
    return t


def is_non_english(text):
    low = ' ' + text.lower() + ' '
    for ex in NON_ENGLISH_EXCEPTIONS:
        if ex in low:
            low = low.replace(ex, ' ')
    if ENGLISH_INTL.search(text):
        return False
    return bool(_NON_EN_RE.search(low))


# ---------------------------------------------------------------------------
# Channel categories (country channels)
# ---------------------------------------------------------------------------
NEWS_RE = re.compile(r"\b(news|cnn|hln|headline news|msnbc|ms ?now|cnbc|fox business|newsmax|newsnation|"
                     r"bloomberg|c-?span|cspan|weather|sky news|gb ?news|al jazeera|france ?24|euronews|"
                     r"dw( english)?|nhk world|cgtn|cp24|bnn|cpac|abc news|cbsn|livenow|news ?12|"
                     r"spectrum news|scripps news|oan|one america|ndtv|wion|india today|trt world|arise|"
                     r"i24|\brt\b|cheddar|weathernation|accuweather|parliament|oireachtas|assembly|"
                     r"legislat|senate|congress|times now|et now|tvc news|newsy|court tv|nbc lx|"
                     r"localish|local now|now ?this|reuters|yahoo finance|fox weather|bbc world|"
                     r"rte news|sky news extra|abc australia news|real america|first ?coast news|"
                     r"telemundo|cna|wfn|business)\b", re.I)
SPORTS_RE = re.compile(r"\b(espn\w*|sports?|fox sports|fs[12]|nfl|nba|mlb|nhl|wnba|golf|tennis|t2|btn|big ten|"
                       r"sec network|acc network|accn|secn|pac[- ]?12|tsn\d?|sportsnet|sky sports?|"
                       r"tnt sports?|bt sport|premier sports?|eurosport|bein|dazn|racing|tvg\d?|fight|"
                       r"ufc|wwe|boxing|mma|pokergo|yes network|msg\d?|nesn|sny|masn|marquee|bally|"
                       r"fanduel|root sports|altitude|space city|stadium|willow|speed|fubo|nbcsn|kayo|"
                       r"fox league|fox footy|fox cricket|supersport|setanta|mutv|lfc|liverpool tv|"
                       r"chelsea tv|man city|billiard|bowling|horse racing|racing\.com|greyhound|"
                       r"cricket|rugby|f1|formula|nascar|motor ?trend|motorsport|redzone|red zone|"
                       r"olympic|paralympic|ivy league|longhorn|sportsman|outdoor channel|pursuit|"
                       r"fishing|hunting|wfn|world fishing|sky sport|eir sport|premier league|red ?bull|hpi ?tv|tab|"
                       r"laliga|la liga|serie a|bundesliga|ligue 1|uefa|fifa|copa|champions|vsin|"
                       r"cbs sports|nbc sports|stadium|athletics|swim|ski|surf|skate|wrestl|aew|tna|"
                       r"impact wrestling|pbr|rodeo|bull riding|darts|snooker|poker|chess|esports?|"
                       r"gol tv|goltv|fox soccer|soccer|football|hockey|baseball|basketball|softball|"
                       r"volleyball|lacrosse|cycling|nhra|indycar|imsa|supercross|monster jam|"
                       r"fight network|combat|glory|bellator|pfl|triller|fite|dirt|track|trackside|"
                       r"sky racing|racing tv|at the races|wedge|tgl|liv golf|pga|lpga|atp|wta)\b",
                       re.I)
MOVIES_RE = re.compile(r"\b(hbo|cinemax|showtime|sho|starz|encore|movieplex|moviepl|mgm\+?|epix|tcm|"
                       r"turner classic|fxm|hallmark movies|movies? ?& ?myster|lmn|lifetime movie|"
                       r"movie|movies|cinema|film|films|filmrise movies|sky cinema|crave|hollywood suite|"
                       r"flix|screenpix|indieplex|retroplex|sony movies|great movies|great action|"
                       r"great romance|film4|talking pictures|true movies|movies ?24|legend|"
                       r"cinevault|cinebox|thriller|horror|westerns?|action|scifi|sci-fi|"
                       r"star movies|hdnet movies|movie ?sphere|moviesphere|shout! movies|"
                       r"cine|filmbox|paramount movie|amc\+? movies|miramax|lionsgate|"
                       r"black ?cinema|outdoor cinema|dove|5 action|5star|5 star|blockbuster|"
                       r"romance|rom ?coms?|comedy movies|family movies|cozi movies)\b", re.I)
MOVIES_NOT = re.compile(r"\b(hbo (drama|comedy)?\s*$|crave tv|showcase|movies & mysteries|"
                        r"filmrise (?!movies|horror|action|free movies|western movies)|action (news|park)|"
                        r"mr\.? bean|power rangers|"
                        r"law & crime|mystery|legendary)\b", re.I)
MUSIC_RE = re.compile(r"\b(music|mtv (live|classic|hits|80s|90s|00s|base|rocks|biggest pop|flow)|"
                      r"mtvu|cmt music|bet jams|bet soul|revolt|stingray|music choice|mc radio|"
                      r"clubland|now (70s|80s|90s|00s|rock|music)|the box|kerrang|kiss|magic|4music|"
                      r"trace|qello|concert|radio|vevo|xite|b4u music|box hits|vibe|jukebox|"
                      r"classic rock|yacht rock|"
                      r"soft rock|smooth jazz|jazz|hip ?hop|r&b|rnb|dance|edm|karaoke|"
                      r"nickelodeon music|nick music|mc\d{2}h|afro music|much)\b", re.I)
MUSIC_NOT = re.compile(r"\b(80s action|90s sitcoms?|80's action|70s & 80s tv|90s kids|dance moms|"
                       r"kiss of|radio ?times|sports radio|talk radio|news radio|radio canada)\b", re.I)

US_NETWORKS = ['ABC', 'CBS', 'NBC', 'FOX', 'CW', 'PBS', 'MNT', 'MyNetworkTV', 'MyTV', 'MY',
               'IND', 'ION', 'ME', 'METV', 'UPN', 'TCT', 'CTN', 'TBN', 'Telemundo', 'Univision']
CALL_RE = re.compile(r'(?<![A-Z])([KW][A-Z]{2,3})(?:[- ]?(?:TV|DT\d?|LD|CD|CA|D\d))?(?![A-Za-z])')
CA_CALL_RE = re.compile(r'\b(C[A-Z]{3})(?:[- ]?(?:TV|DT))?\b')
NOT_CALLSIGNS = {'WNBA', 'WWE', 'WPT', 'KIDS', 'WEST', 'WORLD', 'WILD', 'WOMEN', 'WAR', 'WAY',
                 'WTA', 'WTT', 'WBC', 'WBO', 'WRC', 'WFN', 'WE', 'KAYO', 'WHL', 'WIRE', 'WFH',
                 'WOW', 'KIDZ', 'KOOL', 'WIND', 'WINE', 'WOLF', 'KICK', 'KILL', 'KEEP', 'WALK',
                 'WARM', 'KNOW', 'WHAT', 'WHEN', 'WHY', 'WELL', 'WITH', 'WORK', 'WEB', 'WPN', 'WSL',
                 'KRAV', 'WAPA', 'WINS', 'WEEKEND', 'WOOD', 'KNOT', 'WIFE', 'WIDE', 'WAIT', 'KARMA',
                 'WATCH', 'WACKY', 'WHIP', 'WEIRD', 'WOKE', 'WAVES', 'KITCHEN', 'KNIGHT', 'WALL'}

US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS',
    'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY',
    'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY', 'DC', 'PR'}

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
