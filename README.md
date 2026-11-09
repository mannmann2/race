# Race Atlas

A standalone, mobile-friendly race globe for **race.slopmaxx.ing**. Source lives in this directory. No Sites dependency, account, API key, or npm installation is required. The site is static; scheduled data acquisition runs separately on the host.

```sh
npm run dev       # development: 0.0.0.0:4173
npm test          # snapshot integrity and filter/date tests
npm run build     # static application in dist/
npm start         # production: serves dist/ on 0.0.0.0:4173
```

Point your reverse proxy at **http://127.0.0.1:4173** when it runs on the same machine. Set `PORT` to change it. The installed `race-atlas.service` keeps the production server running on port 4173 and starts it after reboot. Its reproducible definition is in `deploy/`. Node 18+ is required for these commands, Python 3.10+ for acquisition/enrichment. Browsers need WebGL, ES modules, Web Workers, dialog and DecompressionStream (current Chrome, Firefox and Safari).

## Discovery

- Starts with **Upcoming + next 6 calendar months**. Date presets cover 2 weeks, 1, 3, 6 and 12 months, with inclusive custom dates and an Any dates option. Calendar months clamp correctly at month ends and leap years.
- Dual-handle distance slider: drag either end; keyboard arrows also work. The right endpoint means no maximum, so unusually long races remain available. Numeric inputs permit precise bounds, including distances beyond the slider's 500 km scale.
- Multi-country/category search, continent, actual distance, elevation gain, and one-click **UTMB World Series** (source levels `serie`, `major`, `finale`). UTMB categories are effort classifications, not raw distance. The adjacent **42** option selects marathon listings and races with a 42–42.3 km distance in any source, independently of their UTMB grade. It combines with other selected category buttons using OR, while dates, source, viewport and numeric filters continue to apply.
- Source selection (all, UTMB, ITRA, World’s Marathons, UTMB + ITRA), multi-select **ITRA Endurance Points 0–6**, and **Mountain Level 0–12** bounds. Missing ratings do not match a selected rating or range. Shared listings retain both source links; conflicting measurements appear in details.
- **Only races in map view** is on by default. Rotating/panning, pinching, zooming and resizing update the calendar. Camera visibility tests reject points behind the globe and outside the screen; marker clicks also require the pointer to be on the globe surface. Turn the option off to include worldwide and unmapped records.
- Use the sidepanel icon in the header to open or close the calendar. On desktop, closing it enlarges the globe. Phone filters/calendar open separately.
- The application stays inside the viewport, including short windows and phones. Filters and race lists scroll within their own panels.
- Official UTMB category badges/colors are used when supplied; otherwise the ITRA Endurance Points badge/color is used, including zero. Missing grades are gray. Both official badges appear side by side when available, UTMB then ITRA. Graded cards omit repeated source-name chips; ungraded cards use that same row for source names and an explicit “No grade supplied” label. Hover badges start on their own row below the heading. The duplicate numeric points chip is omitted. Calendar cards, hover previews and detail accents use UTMB color first, otherwise ITRA. Map bubbles retain their original muted palette: green groups in light mode, gold groups in dark mode, and muted UTMB colors for individual points. Original SVG sources are recorded in `web/assets/grades/sources.json`.
- Bubble counts are painted from the current camera on every rendered frame, with globe occlusion and surface checks; they do not use delayed symbol placement/fades.
- The sun/moon button switches the entire app and map between light and dark modes. It initially follows your device theme, then remembers your choice locally. Theme changes preserve the current map view and filters.
- Hover or keyboard-focus a calendar race to highlight its location. Worldwide races outside the current view are brought into view without changing the zoom.
- MapLibre GL JS globe transitions into a detailed CARTO/OpenStreetMap vector map as you zoom. Country/place labels and roads appear at appropriate scales. Click a cluster or a shared location to open its race-list modal; hover or tap an individual race for details.
- Real event images appear in cards, hover previews and details when available. Images load lazily, and unavailable images disappear. No generic stock images are substituted.
- Filters and sorting are shareable in the URL. Relative date presets are recalculated on load; custom dates stay fixed. There is no application tracking or account requirement.

## Race data and images

The initial snapshot contains **68,006 real UTMB records**, from 2000 through 2027. **4,487** have a null UTMB category and are labelled **No UTMB category**; they come directly from the same feed. Past editions and missing source fields are retained. The snapshot date and location limitations are shown in the app.

UTMB's structured index is fetched from `https://api.utmb.world/search/races-qualifiers`, with `x-tenant-id: worldseries` and pagination until all reported hits are received. It is an undocumented endpoint and may change. No individual UTMB race detail pages are scraped.

GeoNames exact locality-name/alias matches within the source country supply approximate town coordinates. Ambiguous aliases use the largest matching locality. UTMB's World Series catalogue supplies approximate event coordinates where town coordinates are absent; these are labelled event locations, not verified race starts. Other records have no marker and can be found with the viewport filter disabled.

The enrichment step obtains photos from:

1. Structured event metadata embedded in UTMB's official World Series catalogue.
2. `og:image` / `twitter:image` metadata on the official websites linked by upcoming races, fetched once during preprocessing with caching, bounded downloads/timeouts, and public-address validation.

Current coverage: **5,959 race records across 377 event websites** have image URLs. Photos can represent an event rather than a specific edition. Attribution links remain on race details. Image availability and provider restrictions can change; a broken image never prevents browsing. Event websites are not queried by the application at runtime, but image files are requested from their providers as needed.

### Refresh

```sh
npm run refresh    # refresh UTMB/photos/ITRA independently, then compose the catalog
npm test
npm run build      # production server sees the rebuilt files
```

The default acquisition horizon is December 31 of next year. To change it:

```sh
python3 scripts/refresh.py --end 2028-12-31
python3 scripts/enrich.py
npm run build
```

Photo enrichment defaults to checking at most 600 previously uncached upcoming website URLs per run. Repeating it advances through remaining URLs without re-requesting cached websites:

```sh
npm run enrich
python3 scripts/enrich.py --limit 1000
```

`.cache/` stores GeoNames, country metadata and `event-images.json`. Remove that last file to recheck previously failed or changed image metadata. Race refresh preserves enrichment for surviving source IDs. A failed/incomplete feed fetch leaves the previous snapshot intact. A failed catalogue fetch leaves the previous enriched snapshot intact. The installed `race-refresh.timer` runs daily at 03:30 UTC (with up to 10 minutes of jitter), including a catch-up after missed runs while the host was offline. It refreshes UTMB and course details daily, downloads the ITRA bulk calendar only when the verified copy is seven calendar days old, and atomically publishes the catalog without restarting the site. Open tabs recheck the data hourly and advance relative dates across midnight. On another host, install the units in `deploy/` and update their paths first.

### ITRA rolling browser acquisition

`scripts/itra_browser.py` loads the public calendar in ordinary **displayed Chromium under Xvfb**, with a new anonymous session each time. Plain HTTP requests receive a browser challenge on this host and headless Chromium receives 403. No user cookies, login, challenge solvers, proxy rotation, or browser identity overrides are used. Session credentials stay in browser memory and disappear when it closes.

Scheduled bulk acquisition runs **weekly**, requesting the site's **next 12 months** preset relative to that date. Between bulk downloads, daily enrichment uses `.cache/itra/bulk-listings.json` and preserves its original acquisition timestamp. The seven-calendar-day check avoids scheduling jitter delaying the refresh an extra day. Manual refresh commands still force acquisition unless `--itra-bulk-max-age-days=7` is supplied. The full embedded calendar is extracted in one response and its unique course count must match ITRA's displayed race total before publication. The initial verified capture returned 3,358 courses. This verifies the returned calendar window, not every event in ITRA's database. The public map reports somewhat different totals, so its coordinates are joined by any known course ID in an event; invalid coordinates and conflicting joins are discarded. Exact GeoNames towns fill gaps. Event points are approximate, not verified starts.

Bulk data supplies course links, distances, gains, event date ranges, Endurance Points and optional event images. Course details supply precise dates/names, Mountain Level and Finisher Level. Each daily run refreshes at most 400 upcoming course pages, spaced at least 0.7 seconds apart. New courses are prioritised, then the oldest details; detail freshness lasts 14 days, and changed calendar measurements invalidate them immediately. Coverage and rating counts are shown in the app. Missing ratings are never inferred. Course-detail timestamps are retained separately from calendar freshness.

Past editions remain searchable. Future listings removed from a successful calendar disappear from the active snapshot; editions are never invented by shifting a year. A failed/incomplete calendar preserves the last successful snapshot. Unavailable/malformed individual course pages are skipped and retried after a day. Access failures stop detail enrichment independently while the verified bulk calendar is published. `data/itra-snapshot.json` is the durable fallback for clean builds; `.cache/itra/course-details.json` caches normalized details. The older `data/itra-indexed*` files remain historical test fixtures, not the production feed.

```sh
# One-time acquisition dependencies (the site itself still needs no Python packages):
python3 -m pip install -r requirements-browser.txt
python3 -m playwright install --with-deps chromium
# Linux also needs xvfb and xauth.

npm run refresh:itra              # live rolling calendar + bounded detail enrichment
npm run build                    # publish application changes
# Publish data only, atomically, without rebuilding the application:
node scripts/refresh-all.mjs --itra-only --publish
# Respect the weekly bulk cache while continuing daily course enrichment:
node scripts/refresh-all.mjs --itra-only --publish --itra-bulk-max-age-days=7

# Inspect automatic refresh and the last run:
systemctl list-timers race-refresh.timer
systemctl status race-refresh.service
journalctl -u race-refresh.service -n 60
# Run the complete scheduled workflow now:
systemctl start race-refresh.service
```

The installed unit uses `/root/.venv/bin/python3`; set `RACE_PYTHON` for another interpreter. `deploy/race-refresh.service` and `.timer` are the reproducible unit definitions. A file lock prevents overlapping scheduled refreshes, and a second lock protects ITRA acquisition. Per-source failures produce a nonzero job exit while preserving and publishing the other source's latest good data. The ITRA source status in the app reports a failed refresh rather than presenting stale data as fresh.

Legacy HTML/HAR/public-index import remains available through `scripts/itra.py` for diagnostics and fixtures. It is not the scheduled acquisition path.

`scripts/compose-catalog.mjs` writes `web/data/catalog.json.gz` (schema 2) atomically. It keeps UTMB's compact rows, adds canonical ITRA records, and precomputes matches. Existing UTMB IDs and display measurements remain primary; missing values may be filled from ITRA. A source failure retains that source's last good snapshot and is reported in the app. `npm run refresh` exits nonzero if any source fails, even when composition succeeds.

Automatic matching first groups each provider's courses into event editions using country, normalized event name and a bounded date window. Provider event IDs alone are not reliable: UTMB often uses one per course and ITRA may use different representative courses. Editions link only with compatible names plus corroborating course measurements/names and locality or multiple independent course matches. Sponsor and edition-number differences can be accepted when supported by that evidence.

Within a linked edition, course matching allows up to a two-day start-date discrepancy (or a UTMB date inside an explicit ITRA event range) and distance differences up to 8% or 0.5 km. Named courses or elevation evidence must also agree; matching distance alone is insufficient. Both sides must have a unique plausible course. Relay legs, day/night, solo/team and single/multi-stage variants are checked separately. An unspecified bulk variant stays unresolved; matches are not forced by eliminating already assigned courses. Different years and competing event editions remain separate. These rules prioritize avoiding false merges, so the overlap count is intentionally conservative; it is not a measured accuracy score.

Review `.cache/itra/match-report.json`: `eventLinks` explains edition evidence, `accepted` records each match's evidence or manual override, and `review` contains unresolved candidates. Resolve independently reviewed pairs in `scripts/source-overrides.json`:

```json
{"match":{"itra:2027:12345":"utmb:67890"},"separate":[["itra:2027:23456","utmb:78901"]]}
```

These are illustrative IDs, not actual overrides. Rebuild after editing. Different-year overrides and conflicting assignments are rejected. Source values, both links and rating provenance remain available on merged records. Matching is performed during preprocessing, never during globe interaction.

### Maps

The renderer and style JSON are vendored. Map tiles, labels and imagery use their providers' network services; the race dataset and filtering work independently. Maps require WebGL. If the detailed map fails to initialise, the app falls back to the worldwide calendar. An unavailable photo is hidden automatically.

The pinned CARTO style includes versioned tile/font endpoints. Refresh it periodically or if the provider changes those endpoints:

```sh
npm run refresh:map
npm run build
```

## Hosting

Example reverse proxy (TLS can be handled by your existing proxy):

```nginx
server {
    listen 80;
    server_name race.slopmaxx.ing;
    location / {
        proxy_pass http://127.0.0.1:4173;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Alternatively serve the contents of `dist/` directly with any static host. Relative asset paths allow hosting at a subdirectory too; redirect `/races` to `/races/` if you use one. No client-side route rewrites are needed. Serve `data/catalog.json.gz` as `application/gzip` **without** `Content-Encoding: gzip`: it is an archive decompressed in the worker. Standard static hosts normally do this already. Apply HTTP compression to other assets as usual.

MapLibre uses its own Web Worker. If configuring CSP, allow `worker-src 'self' blob:` and the tile/font/image origins in `web/data/map-style.json` and image metadata. A strict allowlist must account for official event image hosts; do not disable browser security to work around provider restrictions.

## Implementation and verification

- `web/app.mjs`: controls, race calendar, dialogs, URL state, viewport request sequencing.
- `web/globe.mjs`: MapLibre globe, clustered markers, accurate visibility and deep zoom.
- `web/worker.mjs`: snapshot loading, filtering/sorting, viewport lists and pagination off the main thread.
- `web/core.mjs`: canonical records, date maths, provider classification and shared filters.
- `scripts/refresh.py` / `scripts/enrich.py`: acquisition, local geocoding and image enrichment.
- `DATA_MODEL.md`: source-independent records and extending providers.

Unit tests cover the real snapshot, missing/zero measurements, combined filters, calendar arithmetic, World Series levels, viewport membership and image provenance. Browser tests cover desktop/phone interactions, both slider handles, collapse, the globe's far side, image rendering, shareable URLs, sorting and pagination:

```sh
# Python Playwright and its Chromium installation are required only for browser tests.
TEST_URL=http://127.0.0.1:4173 npm run test:browser
TEST_URL=http://127.0.0.1:4173 python3 tests/globe-browser.py  # hit testing and calendar highlights
TEST_URL=http://127.0.0.1:4173 python3 tests/theme-browser.py  # themes, persistence and mobile surfaces
TEST_URL=http://127.0.0.1:4173 python3 tests/sources-browser.py # isolated multi-source fixtures; real worker/globe
TEST_URL=http://127.0.0.1:4173 python3 tests/itra-real-browser.py # actual imported ITRA records
```

Screenshots go in ignored `test-results/`. Google Fonts is optional; removing the first import in `web/style.css` uses system fonts.

Independent personal project; not affiliated with UTMB, ITRA or World’s Marathons. Confirm course details and exact starts with organisers. Credits and licences are in `THIRD_PARTY_NOTICES.md`.

Clock and live-data refresh checks: `TEST_URL=http://127.0.0.1:4173 python3 tests/refresh-browser.py` verifies year rollover, hourly point replacement, and fixed custom dates.

### World’s Marathons

The public `/api/search` endpoint supplies full-marathon event listings through `scripts/worldsmarathons.py`. It uses the website’s `sport=running`, `racetype=full_marathon`, `years` and `page` parameters, with a truthful Race Atlas user agent. **No cookies, account, clearance token or individual race-page scraping is required.** The initial capture verified 1,188 returned event listings against the reported counts across 59 pages for 2026–2028. Of these, 99 lacked an explicit visible marathon distance and one was an audited exhibition listing; 1,088 were imported, with 1,073 mapped and 1,009 image URLs. The count is event-edition listings, not verified individual named courses or a claim of complete worldwide coverage.

The import keeps all full-marathon surfaces. Select **World’s Marathons** in Race sources & ratings, then optionally choose **Road / asphalt**, **Trail**, **Mixed**, **Other surfaces**, or **Not supplied**. Surface filtering uses this source’s labels and excludes records without a World’s Marathons source. Ratings from UTMB and ITRA remain separate. Event photographs are optional, exclude known provider placeholders, and retain source attribution.

Search rows contain event-level distance arrays but no reliable named-course IDs. The adapter produces one marathon listing per provider event and edition, takes the explicit distance in metres (42–42.3 km accommodates source rounding), and never invents missing elevation, local dates or later editions. It preserves multi-day event ranges and explains this limitation in details. Provider coordinates are labelled approximate event locations; GeoNames towns fill gaps. The original local race date is preferred over UTC to avoid shifting races to the previous day.

`scripts/match-marathons.mjs` compares listings against the combined UTMB/ITRA catalogue. It requires the same country/year, overlapping event ranges (or up to two days of festival/course date discrepancy), distinctive event-name agreement, and locality or official-website corroboration. Distances must agree within 0.8 km; an explicitly named marathon/42 km/26.2-mile course allows up to 10% variation to accommodate measured trail distances. Sponsor decoration, word order and plural titles are normalized. Half-marathon, relay, night, team and stage variants stay separate. Both directions must be unique, including weaker competing candidates. Shared social/registration hosts cannot establish identity. The November 9 review found 34 World’s Marathons overlaps, including four three-source records; ambiguous cases remain separate. All source links, ratings, measurements and earlier conflicts survive. Evidence is in `.cache/worldsmarathons/match-report.json`; reviewed real cases are regression fixtures.

The existing daily refresh job now includes this importer. Its verified snapshot is reused for seven calendar days. Acquisition covers the **current year and next two years**, recalculated each run; a year change forces acquisition even if the previous snapshot is less than a week old. Each year must download exactly its reported number of distinct events with a stable count across pages. Failed/incomplete downloads leave the previous snapshot untouched and expose a refresh warning. Successful refreshes retain ended editions and remove absent future listings. It does not infer cancellation status or registration availability.

```sh
npm run refresh:marathons                 # uses the weekly cache when fresh
npm run refresh:marathons -- --force      # force a new full public-feed acquisition
npm run refresh:marathons -- --publish    # atomically publish the composed data
python3 scripts/worldsmarathons.py --max-age-days=0
TEST_URL=http://127.0.0.1:4173 /root/.venv/bin/python3 tests/marathons-browser.py
```

`data/worldsmarathons-snapshot.json` is the durable fallback; `.cache/worldsmarathons/races.json` and `status.json` track acquisition. Only selected public event facts are retained. This is an undocumented website endpoint, so schema/access changes can require adapter maintenance. The browser continues using the last verified snapshot independently of source availability.
