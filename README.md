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

## Guide (EPG)
The server builds one guide for all playlists at `http://<machine-ip>:8765/<ACCESS_TOKEN>/guide.xml.gz`
(also `/guide.xml`), and every playlist it serves already points to it.
- Channels matched to a published guide get real listings: epgshare01 (US, US locals, sports, CA, UK, IE, AU,
  NZ, beIN, Plex, Distro, Peacock, TBN+, Whale TV+, FanDuel, Rakuten) and i.mjh.nz (Pluto TV, Samsung TV Plus,
  Roku, Plex, PBS, MeTV, Foxtel, Kayo). Only the files and channels actually used are kept.
- +1 channels and West feeds reuse the main channel's listings shifted by 1 or 3 hours.
- Everything else gets generated listings: event slots show the current event at its scheduled time
  ("Up next" before it, "event ended" after), 24/7, music and other channels show their name.

## Files
- rules.py / classify.py / process.py – naming, language and grouping rules (edit these to tweak)
- epgmap.py – guide-id matching (aliases at the top)
- guide.py – builds the combined guide
- logos.py – logo fallbacks (tv-logo/tv-logos repo, iptv-org database)
- data/ – guide channel lists, logo indexes, list of known-broken logo URLs
