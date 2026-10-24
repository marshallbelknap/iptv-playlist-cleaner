# IPTV playlist cleaner

Cleans the provider M3U: removes VOD episodes and non-English channels, renames everything
(`US: ESPN HD`, `NFL 02: Jaguars vs Eagles (Oct 11 9:30 AM ET)`), regroups into
`<Country> | <Category>`, `Sports | <League/Service>`, `PPV & Events`, `24/7`, `Adult`,
sets epgshare01 guide ids and fixes logos. Stream URLs are never modified.

## One-off clean
    pip install rapidfuzz          # optional, improves guide matching
    python3 build.py "https://pia.cx/m3u/USER/PASS" playlist_clean.m3u changes.csv

## Always-current playlists (event names update when the provider renames slots)
    PROVIDER_URL_PRIVATE_IPTV="https://provider-one/..." PROVIDER_URL_KINGDOM_IPTV="http://provider-two/get.php?..." \
    ACCESS_TOKEN=some-long-word python3 serve.py 8765
Point TiviMate/UHF at `http://<machine-ip>:8765/<ACCESS_TOKEN>/private-iptv.m3u` (and `kingdom-iptv.m3u`) — the part after
`PROVIDER_URL_` names the playlist
and set the app's playlist auto-update interval. If a provider gives you backup server addresses, add
`PROVIDER_MIRRORS_<NAME>="host1 host2"`; the same login is tried on each until one answers. Each playlist is rebuilt from the provider at most
every `CACHE_MINUTES` (default 30). `/playlist.m3u` is an alias for the first one.

## Synology (Container Manager)
Every push to `main` builds `ghcr.io/marshallbelknap/iptv-playlist-cleaner:latest` (amd64 + arm64).
In Container Manager: Project > Create > "Create docker-compose.yml", paste `docker-compose.yml`,
fill in the provider links and token, Build. To update later: Project > iptv-cleaner > Action > Build
(or Image > Update), which pulls the latest image.

## Naming and groups
- Local stations: `US: Boston - NBC - WBTS - 10` (City - Network - Call sign - Channel). Missing parts are filled
  from `data/us_stations.tsv` (every US station on Wikipedia: market, network, subchannels, branded channel number,
  logo) and `data/ca_stations.tsv`. Branded names ('ABC7 Chicago', 'KIRO 7 Seattle', 'Boston 25') are recognised
  as locals too. A subchannel shows its own number, e.g. `US: Asheville - MyNetworkTV - WLOS - 13.2`.
- Channels go to their home country (`origin.py`, using iptv-org's channel database): CNN or WGN in a Canada
  group become US channels, BBC News in an Australia group a UK one, RTE in a UK group an Irish one. A channel
  stays where it is when that country has its own version (HGTV Canada, Adult Swim Canada). US stations carried in
  Canada (Buffalo, Seattle, Detroit) go to `US | Locals`.
- One channel, one name: every copy of a channel - in both playlists - gets the same name, guide, logo and group,
  however the provider spelled it (`FOX News Channel HD`, `Fox News (FNC)` -> `US: FOX News HD`, `US: FOX News`).
  `canon.py` reduces each name to an identity (East feed, 'Channel'/'Network'/'TV', punctuation and abbreviations
  in brackets do not count); `data/channel_aliases.tsv` joins spellings that are the same channel (`ID` /
  `Investigation Discovery`, `Showtime` / `Paramount+ with Showtime`, old regional sports network names) and
  `data/channel_names.tsv` holds the official name where one is known; otherwise the spelling most copies use wins.
  The quality suffix (4K/FHD/HD/SD), West feeds and +1 channels stay separate, since those are different streams.
- Event start times are written one way, in Eastern time, at the end of the name: `(Oct 10 7:30 PM ET)`
  (`eventtime.py` reads 'Saturday, 10 October 2026 15:00', 'Sun 11 Oct 18:30 EDT', '1pm', '11-10-2026 - 20:00
  (GMT)' and other provider formats). Matchups read `A vs B`.
- 24/7 loops are split into `24/7 | TV Shows`, `24/7 | Movies`, `24/7 | Actors & Directors`, `24/7 | Kids & Animation`.
  Show/movie/actor channels found in country groups move there too (`data/loop_channels.tsv`, hand-checked; rules in `loops.py`).

## Logos
`logo_pick.py` only uses real, official logos - nothing is ever drawn or generated. Sports and event channels get
the league's / organiser's official logo (`data/sports_logos.tsv`, from Wikipedia/Wikimedia; event text such as
'UFC 312' or 'WWE Raw' picks the organiser). 24/7 channels get the show's or film's own logo
(`data/show_logos.tsv`, from Wikipedia) or the logo the free streaming service publishes. Everything else:
the station's own logo for locals, hand-checked brand logos (`data/logo_aliases.tsv`), tv-logos, the official
logo from the matched guide (upsized), iptv-org, Pluto / Samsung / Roku / Plex / Xumo logos
(`data/fast_logos.tsv`), the provider's logo, then the same channel's logo from the other playlist.
When none of those has a logo (obscure 24/7 titles, adult feeds, unnamed 'PPV 08' event slots before the
provider fills them in) the logo is left blank rather than invented; they are listed in the cache as
`logos_missing_<playlist>.tsv`.

## Guide (EPG)
The server builds one guide for all playlists at `http://<machine-ip>:8765/<ACCESS_TOKEN>/guide.xml.gz`
(also `/guide.xml`), and every playlist it serves already points to it.
- Channels matched to a published guide get real listings: epgshare01 (US, US locals, sports, CA, UK, IE, AU,
  NZ, beIN, Plex, Distro, Peacock, TBN+, Whale TV+, FanDuel, Rakuten), Open-EPG (US, US locals, CA, UK, IE, AU,
  NZ, ZA) and i.mjh.nz (Pluto TV, Samsung TV Plus, Roku, Plex, PBS, MeTV, Foxtel, Kayo).
- Each channel's other guide ids are kept (`guide_alts_<playlist>.json` in the cache). When a source stops updating
  (epgshare01 did in October 2026), the guide takes that channel's listings from the source with the most
  listings for the next day, so a channel never falls back to its own name while another source has it.
- A guide match is only used when it is clearly the same channel (same identity, a hand-checked alias or a very
  close name, and the same country's broadcast); a provider's own guide id is checked the same way.
- +1 channels and West feeds reuse the main channel's listings shifted by 1 or 3 hours.
- Everything else gets generated listings: event slots show the current event at its scheduled time
  ("Up next" before it, "event ended" after), 24/7, music and other channels show their name.

## Files
- rules.py / classify.py / process.py – naming, language and grouping rules (edit these to tweak)
- canon.py – one identity and one name per channel (with data/channel_aliases.tsv, data/channel_names.tsv)
- eventtime.py – event start times in one format
- epgmap.py – guide-id matching (aliases at the top)
- guide.py – builds the combined guide
- logos.py – logo fallbacks (tv-logo/tv-logos repo, iptv-org database)
- data/ – guide channel lists, logo indexes, list of known-broken logo URLs
