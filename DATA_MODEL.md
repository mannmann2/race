# Canonical race model

Source records are normalised before filtering. All distances are kilometres, elevations are metres, and dates are local race calendar dates (`YYYY-MM-DD`), not UTC midnight instants. Unknown values are `null`, never zero or guessed. `0` elevation is valid data.

```js
{
  id: 'utmb:161694',           // provider namespace + source race/edition id
  source: 'utmb',
  sourceId: '161694',
  eventId: 'utmb:event:35968', // recurring organiser event
  editionId: 'utmb:event:35968:2027',
  name: 'LEENDERBOS ULTRA',    // one distance/course at this edition
  eventName: 'LEENDERBOS ULTRA',
  date: '2027-12-19',
  distanceKm: 51,
  elevationGainM: 85,
  locationId: 123,            // snapshot-local location index; not stable identity
  place: 'Leende, Netherlands',
  countryCode: 'NL',          // ISO 3166-1 alpha-2, with legacy codes normalised
  country: 'Netherlands',
  continent: 'Europe',        // six inhabited continents; Americas split N/S
  longitude: 5.55,            // illustrative; actual coordinates from geocoding
  latitude: 51.35,
  locationPrecision: 'town', // 'town', 'event', 'unknown'; extend with 'start'
  geonamesId: '...',
  website: 'https://...',
  sourceUrl: 'https://utmb.world/utmb-index/races/...',
  sources: [{ provider: 'utmb', id: '161694', url: 'https://...', fetchedAt: '2026-11-09T00:00:00Z', values: { /* original source course fields */ } }],
  image: null,                // optional HTTP(S) promotional image
  imageSource: null,          // provenance: official event website
  extensions: { utmb: { category: '50k', level: 'qualifier', stones: 0 } }
}
```

`searchText` is an internal, accent-normalised index generated in the worker. It is excluded from UI payloads. `source` and `sourceId` identify the primary record for compatibility; `sources` contains **all** source records and links. `sources[].values` preserves original names, date, distance, elevation and locality. Provider acquisition/status metadata is retained in `sourceMeta`. Conflicts in dates, distances or elevation gains appear in `conflicts` and in the UI. Ratings live under their originating provider, never under a shared inferred classification.

## Event / edition / race

An event can recur each year. An edition can contain several distances on different dates and at different start towns. Each race retains its own date and location. Event identities use the recurring numeric event prefix in UTMB's result URI; names are a fallback. Records are not collapsed just because they share a location or date. A calendar-year edition key reflects the current feed's granularity; a future provider with multiple editions per year should supply its explicit edition ID instead.

## Compact transport

`races.json.gz` uses `schemaVersion: 1`, event and location dictionaries, and compact race rows to reduce transfer size. The full model is expanded in the worker using `expandDataset`.

The application loads **`catalog.json.gz`, schema 2**, generated from this unchanged UTMB snapshot and the last successful ITRA import. Schema 2 retains those compact fields and adds `additionalRaces: [{race, matchId}]`, `sourceMeta` and `mergeSummary`. `matchId` is a precomputed canonical UTMB ID or null. The worker combines a matched record once or appends an unmatched record. If its matched primary ID disappears, the ITRA record remains standalone. Coverage counts describe unique visible race records, not summed provider counts. `expandDataset` supports both versions.

ITRA IDs use `itra:<edition year>:<course id>` from the detail URL. Its `eventId`/`editionId` identifies the calendar event's default course URL for that edition, not a verified recurring event identity. No recurring ITRA event ID is invented. `datePrecision: 'race' | 'event-day' | 'event'` distinguishes exact course dates, single-day event dates, and multi-day event ranges. `dateEnd` is the inclusive event end; filtering uses interval overlap until an exact course date is known. Calendar summaries require exact event identity, locality, distance/gain and uniqueness in both directions. Explicit multi-day ranges may match a course date within that range (up to 31 days); conflicting exact course dates remain separate pending review. ITRA locations are source-namespaced strings; colocated records group by coordinates on the map.

`extensions.itra` contains `endurancePoints` (integer 0–6), `mountainLevel` (integer 0–12), and `finisherLevel` (when supplied). Missing values are null, including on records without an ITRA source. Zero is a valid supplied rating. Selecting either rating filter excludes unknown values. ITRA source metadata records the rolling 12-month scope, detail/rating coverage and `calendar-count-verified` completeness. This means the unique course count matches the live calendar total, not that every historical or unpublished ITRA race is included.

Race tuple order: `[sourceId, eventIndex, name, date, distanceKm, elevationGainM, category, locationIndex, website, resultsURI, level, stones]`.

Event tuple: `[eventId, eventName]`. Several event dictionary entries may share a stable event ID while retaining different historical names, so older sponsors/titles do not overwrite newer editions. Location tuple: `[sourcePlace, countryCode, longitude, latitude, precision, geonamesId]`.

These are UTMB transport details, not the canonical model. Treat IDs as strings. Never infer UTMB category from raw distance; effort categories and actual course distance are different filters.

## Adding a provider

1. Add a source adapter alongside the UTMB adapter. Fetch structured metadata and preserve source IDs, links, acquisition time, and provider-specific fields.
2. Map into the canonical model above; namespace all identifiers and place source-specific data under `extensions.<provider>`. Add an optional `image` URL only with valid provenance/usage rights; do not use the UTMB category logo as an event photo.
3. Extend the catalog composer with normalized records and precomputed identity links. The filter, calendar and globe operate on canonical fields. Leave UTMB classification absent for other providers. Source selectors query all entries in `sources`, not the primary source.
4. Use explicit reviewed identity links first. The UTMB/ITRA matcher requires exact course dates, country, compatible names and distance, matching locality, and unique candidates in both directions. Ambiguity and conflicts are reported for review instead of silently merging. `scripts/source-overrides.json` persists reviewed `match` and `separate` decisions; original source values and URLs remain intact. No ratings are inferred from course measurements or transferred across editions.

Country-level locations must not be presented as exact starts. Missing dates should not match date-constrained or upcoming/past queries. Keep unknown measurements visible in unconstrained results and exclude them when their numeric range is constrained.

## Enrichment and viewport filtering

Optional `enrichment` is keyed by provider source race ID. Each entry may contain `image`, `imageSource`, or catalogue `longitude` / `latitude`. Event coordinates only fill records without matched town coordinates; they are labelled approximate event locations. Enriched locations use a string `locationId` derived from their coordinates; other location IDs remain snapshot-local numbers. Stable event and race IDs are unchanged. Images are not evidence of course or edition identity. The snapshot retains `enrichmentMeta` acquisition time, catalogue source and coverage.

World Series filtering reads UTMB levels `serie`, `major` and `finale` exactly. A null category remains null and displays as No UTMB category. No source classification is inferred from names.

The worker retains the global filtered/sorted set and derives viewport lists from it. Map marker data always uses the global set, so moving the map never erases races outside the prior viewport. Filter sequence and view revision numbers reject stale asynchronous responses and pagination after a view change. The default viewport filter excludes unknown locations; users can disable it to see the complete set.

## Refresh and persistence

`data/itra-snapshot.json` is the durable live snapshot, used if `.cache/itra/races.json` is absent. Each run creates a new anonymous displayed Chromium session, loads the site's rolling next-12-month calendar, and validates the unique course count against the reported total. Raw cookies, tokens and full pages are not persisted. Normalized course details live in `.cache/itra/course-details.json`, with per-course freshness and a calendar fingerprint that invalidates details when dates or measurements change. `sources[].fetchedAt` is calendar acquisition time; `detailsFetchedAt` describes the older or current detail enrichment independently.

Successful refreshes replace future listings within the current feed scope and retain ended editions for historical browsing. Missing future entries are removed, while future years are fetched from the provider rather than derived from old records. Calendar failure preserves the last good snapshot. Detail failure stops enrichment but permits the independently verified calendar to publish with unknown/stale detail fields explicitly dated.

The ITRA bulk calendar is downloaded every seven calendar days; daily course enrichment reuses the verified normalized bulk cache with its original `fetchedAt`. Failed weekly acquisition retains that cache and the published snapshot. The scheduled daily refresh atomically replaces `dist/data/catalog.json.gz`. Open clients reload data hourly; point caches are invalidated after reload. Relative presets are recomputed at local midnight or when returning to a tab, including leap days and year changes. Custom dates remain fixed.

`data/itra-indexed-snapshot.json` and `data/itra-indexed.json` retain the historical 35-course search-index fixture for regression tests. These are not the production fallback. Their `public-index` acquisition, null `fetchedAt`, `retrievedAt`, and `indexAge` retain the original provenance.

## World’s Marathons event listings

Provider key `worldsmarathons` uses `worldsmarathons:<year>:<slug>:marathon` for the full-marathon event listing, `worldsmarathons:event:<slug>` for the recurring event, and a year-specific edition ID. The feed does not identify individual named marathon courses reliably; repeated distance rows are collapsed to one event-level listing. `datePrecision` is `event-day` or `event`, never `race`. `dateNextRaceLocal` supplies local dates; UTC dates and expired registration flags are not used to infer race days or cancellation. Distances come from explicit visible metre-based source values; elevation is unknown.

`extensions.worldsmarathons` holds `surface` (`road`, `trail`, `mixed`, `other`, or null), the unmodified `sourceSurface`, `courseDifficulty`, `tags` and `listingType: 'marathon-event'`. Road includes source labels Road/Asphalt; Trail includes Trail/Terrain/Urban trail/Mountain. Other labels remain other, missing labels remain null. Surface filtering is provider-specific and does not invent classifications for UTMB/ITRA records.

Schema 2 `additionalRaces` now contains multiple providers in composition order: ITRA, then World’s Marathons. A marathon entry’s `matchId` may reference an existing UTMB **or standalone ITRA** canonical ID. Original IDs and all source links remain in `sources`. Three-source merging preserves earlier `conflicts` and records `primaryProvider`, `incomingProvider`, `primaryValue` and `incomingValue`; legacy provider-named fields remain for compatibility. `sourceMeta.worldsmarathons` holds per-year verified search counts, exclusion reasons, source freshness, surface/image/location coverage, and its own merge summary. The original top-level `mergeSummary` continues to describe UTMB/ITRA matching.

A complete snapshot covers the current and following two calendar years. Annual source counts are checked before normalization; rejected non-marathon/malformed listings are counted separately. This verifies the returned search window, not all marathons worldwide. Only validated snapshots replace saved data; future missing listings disappear and past editions remain. Weekly cache reuse is invalidated by a year change. No cookies or browser credentials enter the snapshot or app.

Marathon matching uses edition ranges and distinctive names with independent locality/official-website support. Named marathon courses allow trail measurement variation up to 10%; unnamed courses require agreement within 0.8 km. Up to two days of festival/course offset require an explicit marathon course label. Half/relay/night/team/stage variants and competing plausible courses prevent automatic merging. Reviewed ITRA/UTMB course links are applied before World’s Marathons, so one canonical row may expose all three provider links and the original ITRA ratings.

## Display grades

`raceGrade` selects a valid supplied UTMB category first, then integer ITRA Endurance Points 0–6, then an unknown neutral grade. It never infers a provider grade from distance. Official badge colors and URLs are centralized in `web/grades.mjs`. `raceGrades` returns both supplied badges in UTMB-then-ITRA order; `raceGrade` continues to choose the primary accent color. The official ITRA badge replaces the additional numeric points chip. Worker map groups retain a `gradeCounts` histogram over canonical races; matched provider records count once using that race’s preferred grade. GeoJSON cluster properties retain those histograms, while map bubbles use their original muted theme palette independently of the official card colors. Display colors and histograms are derived, not persisted source facts.

## Production transport and publication

The normalized source-independent race model remains the same. The composed schema-2 catalog is validated before publication, then written as two immutable transport assets: an upcoming-only schema-3 document (`{schemaVersion:3,races:[canonicalRace,...]}`), and the complete schema-2 archive. The upcoming payload includes a two-day timezone buffer and every known later edition; source acquisition horizons continue rolling independently. Search text is rebuilt locally and is not transmitted.

`catalog-index.json` holds content-derived filenames, sizes, an acquisition cutoff, coverage and per-source freshness. Payloads land before this pointer changes. The worker starts with upcoming data and loads the archive on demand for historical filters or older race links. A failed background check preserves loaded data; failed archive requests return the user to upcoming browsing. Mutable index pointers are never served from stale precompressed copies.

The source matcher now uses an explicitly named course suffix from a validated, matching-year ITRA URL to distinguish walking, relay, night, team and stage variants hidden by event-only calendar labels. It still requires a mutually unique course within an independently linked edition. Manually reviewed pairs, explicit separations and their evidence remain in `scripts/source-overrides.json`. Identified test records are excluded by exact source ID in `scripts/source-exclusions.json`; their raw source snapshots are retained on the host. No broad keyword suppression is applied.

## Location verification

Composition verifies source coordinates against Natural Earth country outlines with a 20 km coastal/border buffer. A coordinate sign is corrected only when exactly one sign combination falls in the listed country. Otherwise a unique GeoNames locality is used, or a demonstrably wrong-country pin is removed while the race remains in the calendar. Region components such as `IL`, `Utah` and `New York` disambiguate town names; population alone cannot establish a correction. Country names are not interpreted as state hints. Same-name ambiguity without sufficient evidence remains in the review report.

`scripts/location-overrides.json` records organiser-verified event corrections, scoped by country, event and locality rather than a global town-name replacement. The composer writes these and automatic corrections to `locationCorrections`, applied to each source record before matching. Original provider fields remain in `sources[].values`. The full audit, including unresolved cases, is written to `.cache/location-report.json` on every composition. GeoNames cities500 is cached once for small towns, with cities1000 as an offline fallback; country and region reference data live in `scripts/geo/`.
