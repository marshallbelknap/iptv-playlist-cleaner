# -*- coding: utf-8 -*-
"""24/7 channels: recognise show / movie / actor loops and sort them into
'24/7 | TV Shows', '24/7 | Movies', '24/7 | Actors & Directors', '24/7 | Kids & Animation'.

data/loop_channels.tsv holds hand-checked decisions for channels that sit in country groups
(name -> S show, M movie, A actor/personality, K kids, X non-English); everything else uses the rules below.
"""
import os
import re

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
GROUPS = {'S': '24/7 | TV Shows', 'M': '24/7 | Movies', 'A': '24/7 | Actors & Directors', 'K': '24/7 | Kids & Animation'}


def _norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


LABELS = {}
_p = os.path.join(DATA, 'loop_channels.tsv')
if os.path.exists(_p):
    for _l in open(_p, encoding='utf-8'):
        if '\t' in _l and not _l.startswith('#'):
            _n, _c = _l.rstrip('\n').split('\t')[:2]
            LABELS[_norm(_n)] = _c

KIDS_RE = re.compile(r"\b(kids|nick jr|disney junior|disney channel|toddler|preschool|nursery|cartoons?|toons?|animat\w*|anime|cocomelon|"
                     r"paw patrol|peppa|bluey|spongebob|sponge bob|pokemon|pokémon|yu-?gi-?oh|digimon|naruto|boruto|"
                     r"dragon ?ball|sailor moon|inuyasha|one piece|hunter x hunter|sonic|mario|teletubbies|"
                     r"sesame|elmo|muppets?|thomas (and|&) friends|thomas the tank|bob the builder|fireman sam|^barney( (and|&) friends)?$|"
                     r"caillou|arthur|clifford|curious george|dora|blues clues|blue'?s clues|garfield|scooby|"
                     r"looney|tom (and|&) jerry|flintstones|jetsons|smurfs|care bears|my little pony|strawberry "
                     r"shortcake|polly pocket|barbie|lego(?! ?star wars movies)|power rangers|ninja turtles|tmnt|transformers|he-?man|"
                     r"she-?ra|thundercats|inspector gadget|go go gadget|pink panther|mr\.? bean animated|"
                     r"teen titans|ben 10|powerpuff|dexter'?s lab|ed,? edd|courage the cowardly|rugrats|hey arnold|"
                     r"wild kratts|magic school bus|reading rainbow|zoboomafoo|mister rogers|daniel tiger|"
                     r"yo gabba|baby shark|pinkfong|little angel|super simple|kidz bop|ryan'?s? (world|and friends)|"
                     r"like nastya|vlad and niki|diana and roma|fgteev|blippi|ms rachel|miraculous|lol surprise|"
                     r"tayo|robocar|rainbow ruby|grizzy|mickey mouse|slugterra|dungeons (and|&) dragons|minecraft|roblox|"
                     r"avatar(?: the last airbender| the legend of korra)|kung fu panda|shrek|madagascar|despicable|minions|toy story|pixar|"
                     r"dreamworks|nickelodeon|nick jr|cartoon network|boomerang|family guy|simpsons|futurama|"
                     r"south park|bob'?s burgers|king of the hill|american dad|rick (and|&) morty|beavis|"
                     r"daria|archer|bojack|animaniacs|pinky (and|&) the brain|tiny toon|doug|recess|"
                     r"kim possible|phineas|gravity falls|adventure time|regular show|steven universe|"
                     r"gumball|we bare bears|totally spies|winx|beyblade|bakugan|zelda|sonic|pac-?man|angry birds|"
                     r"oggy|masha|peppa|ben (and|&) holly|octonauts|pj masks|hey duggee|in the night garden|"
                     r"fraggle|wiggles|hi-?5|play school|bananas in pyjamas|noddy|postman pat|paddington|"
                     r"rupert|wombles|the herbs|danger mouse|count duckula|dennis the menace|horrid henry)\b", re.I)
ADULT_ANIMATION = re.compile(r"\b(family guy|simpsons|futurama|south park|bob'?s burgers|king of the hill|american dad|"
                             r"rick (and|&) morty|beavis|daria|archer|bojack|adult swim|adult animation)\b", re.I)
MOVIE_RE = re.compile(r"\b(movies?|films?|cinema|cine|flix|flicks?|saga|trilogy|collection|franchise|blockbusters?|"
                      r"james bond|007|harry potter|fast (and|&) (the )?furious|rocky|rambo|jurassic|terminator|"
                      r"alien|predator|indiana jones|back to the future|lord of the rings|hobbit|matrix|"
                      r"mission impossible movies|pirates of the caribbean|transformers movies|twilight|hunger games|"
                      r"halloween|friday the 13th|nightmare on elm|saw|scream|godzilla|king kong|planet of the apes|"
                      r"die hard|lethal weapon|police academy|american pie|national lampoon|home alone|"
                      r"the godfather|star wars movies|marvel(?!'s)(?! (rising|agents?|runaways))|mcu|dc movies|batman|superman|spider-?man|x-?men|"
                      r"john wick|jason bourne|bourne|mad max|ghostbusters|men in black|karate kid|top gun|"
                      r"shrek movies|ice age|toy story movies|hallmark movies|christmas movies|horror movies)\b",
                      re.I)
SERIES_HINT = re.compile(r"\b(series|season|s\d{2}|episodes?|show|sitcoms?|seasons|twilight zone|rings of power|"
                         r"animated|assemble|brave and the bold|agents? of)\b", re.I)
FIRST_NAMES = set('''
aaron adam adrian al alan albert alec alex alexander alfred alice alicia allison amanda amy andrew andy angela
angelina ann anna anne anthony arnold audrey ava barbara ben benedict bernie bette betty bill billy bob bobby
brad bradley brendan brian bridget bruce burt cameron carol caroline cary cate catherine charles charlie
charlotte chris christian christopher chuck clint colin courteney craig dakota dan dana daniel danny david
dean debbie demi denzel dennis diana diane dick dolly don donald doris drew dustin dwayne ed eddie edward
elizabeth ellen elvis emma eric ethan eva farrah frank fred gary gene george gerard gina glenn goldie grace
greta gwyneth halle harrison harry heath heather helen henry hugh ian jack jackie jake james jamie jane jason
jean jeff jennifer jenny jeremy jerry jessica jim jimmy joan joe joel john johnny jon jonathan jordan joseph
josh judd judy julia julie justin karen kate katharine katherine keanu kevin kim kirk kristen kurt lana larry
laura lauren lee leonardo liam lindsay lisa liz lucille lucy macaulay madonna marilyn mark martin mary matt
matthew mel meg meryl michael michelle mickey mike morgan natalie nicolas nicole norm olivia orson owen pam
pamela patrick paul peter philip quentin rachel ralph ray reese richard rob robert robin rock roger ron rosie
russell ryan sally sam samuel sandra sarah scarlett sean sharon shirley sidney stanley steve steven sylvester
ted terry tim timothy tina tom tommy tony uma val vin vince vincent walter wes whoopi will william woody
'''.split())
DIRECTORS = re.compile(r"\b(spielberg|tarantino|hitchcock|kubrick|scorsese|nolan|coppola|lucas|cameron|"
                       r"carpenter|craven|romero|cronenberg|lynch|burton|zemeckis|scott|fincher|eastwood|"
                       r"tyler perry|wes anderson|coen)\b", re.I)


FAMOUS = re.compile(r"\b(stallone|schwarzenegger|van damme|jcvd|seagal|chuck norris|bruce lee|jackie chan|jet li|"
                    r"tom cruise|tom hanks|tom hardy|brad pitt|denzel washington|will smith|will ferrell|"
                    r"adam sandler|jim carrey|eddie murphy|robin williams|steve martin|steve carell|ben stiller|"
                    r"keanu reeves|nicolas cage|liam neeson|harrison ford|clint eastwood|john wayne|al pacino|"
                    r"robert de niro|robert downey|morgan freeman|samuel l\.? jackson|vin diesel|dwayne johnson|"
                    r"the rock|jason statham|mel gibson|bruce willis|kevin costner|kevin hart|ryan reynolds|"
                    r"leonardo dicaprio|matt damon|ben affleck|johnny depp|george clooney|meryl streep|"
                    r"julia roberts|sandra bullock|angelina jolie|scarlett johansson|jennifer aniston|"
                    r"jennifer lopez|halle berry|cameron diaz|reese witherspoon|kate winslet|nicole kidman|"
                    r"charlize theron|tyler perry|elvis|marilyn monroe|audrey hepburn|john candy|chevy chase|"
                    r"bill murray|jamie foxx|benedict cumberbatch|bradley cooper|mike tyson|bob ross|"
                    r"gordon ramsay|jamie oliver|martha stewart|emeril|ellen degeneres|dr\.? phil|joel osteen|"
                    r"mrbeast|mr beast|jack hanna|50 cent|anthony bourdain|cesar millan|steve irwin)\b", re.I)
PERSON_TAIL = re.compile(r"\b(movies?|films?|collection|classics|favorites|filmography)\s*\d*$", re.I)


def is_person(name, actor_group=False):
    """'Will Ferrell Movies', 'David Oyelowo' (in an actors group), 'Bob Ross' look like a person's channel."""
    if re.search(r"'s\b|\bshow\b|\bhour\b|\bwith\b", name, re.I):     # 'Tyler Perry's House of Payne'
        return False
    if FAMOUS.match(name) or (actor_group and FAMOUS.search(name)):
        return True
    words = re.sub(r"\b(movies?|films?|collection|channel|presents|tv|classics?|favorites)\b|\d+", ' ', name,
                   flags=re.I).split()
    looks = len(words) in (2, 3) and words[0].lower() in FIRST_NAMES and all(w[:1].isupper() for w in words)
    if actor_group and len(words) in (2, 3) and all(w[:1].isupper() for w in words) and not MOVIE_RE.search(name):
        return True                                               # 'Viola Davis' in a movies/actors group
    return looks and (actor_group or bool(PERSON_TAIL.search(name)))


def loop_type(name, src=''):
    """S/M/A/K for a 24/7 loop channel name (without '24/7 ' or country prefix). src = provider's group,
    used as a hint ('24/7 CARTOON VIP', '24/7 MOVIES/ACTORS VIP', '24/7 DRAMA VIP' ...)."""
    lab = LABELS.get(_norm(name))
    if lab in GROUPS:
        return lab
    src = src or ''
    actor_group = bool(re.search(r'ACTOR', src, re.I))
    if is_person(name, actor_group) or (DIRECTORS.match(name) and not re.search(r"'s\b|hour|presents", name, re.I)):
        return 'A'
    if re.search(r'CARTOON|KIDS', src, re.I) and not ADULT_ANIMATION.search(name):
        return 'K'
    if KIDS_RE.search(name) and not ADULT_ANIMATION.search(name):
        return 'K'
    if re.search(r'SHOWS|COMEDY|DRAMA|REALITY|CRIME|SERIES|ON AIR', src, re.I) and not MOVIE_RE.search(name):
        return 'S'
    if MOVIE_RE.search(name) and not SERIES_HINT.search(name):
        return 'M'
    if re.search(r'MOVIES|CINEMANIA HOLLYWOOD|SKY STORE', src, re.I) and not SERIES_HINT.search(name):
        return 'M'
    return 'S'


def country_label(name):
    """Hand-checked decision for a channel in a country group: S/M/A/K (move to 24/7), X (drop) or None."""
    return LABELS.get(_norm(name))
