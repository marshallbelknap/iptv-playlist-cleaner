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
and set the app's playlist auto-update interval. Each playlist is rebuilt from the provider at most
every `CACHE_MINUTES` (default 30). `/playlist.m3u` is an alias for the first one.

## Synology (Container Manager)
Every push to `main` builds `ghcr.io/marshallbelknap/iptv-playlist-cleaner:latest` (amd64 + arm64).
In Container Manager: Project > Create > "Create docker-compose.yml", paste `docker-compose.yml`,
fill in the provider links and token, Build. To update later: Project > iptv-cleaner > Action > Build
(or Image > Update), which pulls the latest image.

## Guide (EPG) URLs to add in TiviMate / UHF
The playlist header already lists them; add manually if your app ignores it:
- https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_PLEX1.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_CA2.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_IE1.xml.gz
- https://epgshare01.online/epgshare01/epg_ripper_AU1.xml.gz
(plus NZ1, ZA1, BEIN1, DISTROTV1 if you watch those)

## Files
- rules.py / classify.py / process.py – naming, language and grouping rules (edit these to tweak)
- epgmap.py – guide-id matching (aliases at the top)
- logos.py – logo fallbacks (tv-logo/tv-logos repo, iptv-org database)
- data/ – guide channel lists, logo indexes, list of known-broken logo URLs
