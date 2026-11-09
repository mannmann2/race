#!/usr/bin/env python3
"""Import full-marathon listings from the public World's Marathons search feed."""
import argparse
from collections import Counter
import datetime as dt
import fcntl
import json
import math
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

from itra import ROOT, FeedError, atomic_json, geocode

BASE = 'https://worldsmarathons.com'
# Keep only public event facts, never account, payment or session fields.
FIELDS = 'id title country countryCode city dateNextRaceLocal firstRaceDate lastRaceDate raceDistances surface courseDifficulty selfLink website image imageSmall geoStartPoint startPoint tags'.split()
# Audited non-race listing: the source page sells exhibition booths while marking
# their distance as 42.20 km. https://worldsmarathons.com/marathon/shanghai-sports-expo
EXCLUDED_EVENTS = {'shanghai-sports-expo': 'non-race-listing'}


def years_for(today):
    return list(range(today.year, today.year + 3))


def search_url(year, page):
    # Preserve the site's actual query shape (including its repeated race type).
    return BASE + '/api/search?' + urllib.parse.urlencode([
        ('sport', 'running'), ('racetype', 'full_marathon'), ('racetype', 'full_marathon'),
        ('years', year), ('search', ''), ('page', page), ('currency', 'EUR')])


class Client:
    def fetch(self, year, page):
        request = urllib.request.Request(search_url(year, page), headers={
            'Accept': 'application/json', 'Accept-Language': 'en-US,en;q=0.9',
            'Referer': BASE + '/s/running/full_marathon',
            'User-Agent': 'RaceAtlas/1.0 (+https://race.slopmaxx.ing)'})
        # No cookies, login, browser identity overrides or saved browser sessions.
        with urllib.request.urlopen(request, timeout=40) as response:
            if response.status != 200 or 'application/json' not in response.headers.get('Content-Type', ''):
                raise FeedError('World’s Marathons returned a non-JSON response')
            body = response.read(8_000_001)
            if len(body) > 8_000_000:
                raise FeedError('Oversized search response')
            return json.loads(body)


def capture_calendar(client, today, pause=.75):
    captured = []
    for year in years_for(today):
        rows, expected = {}, None
        for page in range(500):
            data = client.fetch(year, page)
            count, results = data.get('count'), data.get('results')
            if type(count) is not int or count < 0 or not isinstance(results, list):
                raise FeedError('Invalid search response')
            if expected is None:
                expected = count
            if count != expected:
                raise FeedError('Search count changed during pagination; retry on the next run')
            for row in results:
                identity = row.get('id')
                if not isinstance(identity, str) or not identity or identity in rows:
                    raise FeedError('Missing or repeated event identity; incomplete pagination')
                rows[identity] = {key: row[key] for key in FIELDS if key in row}
            print(f'World’s Marathons {year}: {len(rows)} / {count} events', flush=True)
            if len(rows) > expected or (not results and len(rows) != expected):
                raise FeedError('Search count does not match downloaded events')
            if len(rows) == expected:
                break
            time.sleep(pause)
        else:
            raise FeedError('Search pagination limit reached')
        captured.append({'year': year, 'count': expected, 'pages': page + 1, 'results': list(rows.values())})
    return {'capturedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'years': captured}


def local_date(value):
    if not isinstance(value, str) or not re.match(r'^\d{4}-\d{2}-\d{2}(?:T|$)', value):
        return None
    try:
        day = dt.date.fromisoformat(value[:10])
        return day.isoformat() if day.year >= 2000 else None
    except ValueError:
        return None


def url(value):
    if not isinstance(value, str):
        return None
    parsed = urllib.parse.urlsplit(value)
    return value if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username else None


def surface_of(value):
    value = (value or '').strip().lower()
    if value in ('road', 'asphalt'):
        return 'road'
    if value in ('trail', 'terrain', 'urban trail', 'mountain'):
        return 'trail'
    if value == 'mixed':
        return 'mixed'
    return 'other' if value else None


def point_of(row):
    coords = (row.get('geoStartPoint') or {}).get('coordinates') or row.get('startPoint')
    if isinstance(coords, list) and len(coords) == 2:
        lon, lat = coords
        if all(type(v) in (float, int) and math.isfinite(v) for v in coords) and -180 <= lon <= 180 and -90 <= lat <= 90 and (lon or lat):
            return lon, lat
    return None


def normalize(row, year, fetched_at):
    identity, title = row.get('id'), (row.get('title') or '').strip()
    if identity in EXCLUDED_EVENTS:
        return None, EXCLUDED_EVENTS[identity]
    if not identity or not title:
        return None, 'missing-identity'
    day = local_date(row.get('dateNextRaceLocal'))
    # Never derive the local race day from UTC or invent a later edition.
    if not day or int(day[:4]) != year:
        return None, 'missing-or-out-of-year-local-date'
    distances = {d['distance'] for d in row.get('raceDistances', [])
                 if not d.get('hidden') and d.get('measureType') == 0
                 and type(d.get('distance')) in (int, float) and 42000 <= d['distance'] <= 42300}
    if not distances:
        return None, 'no-explicit-marathon-distance'
    # Search rows describe events, not individual named courses. Do not create
    # separate fictitious courses for repeated entries/roundings in this array.
    distance = min(distances, key=lambda d: (abs(d - 42195), d)) / 1000
    start, finish = local_date(row.get('firstRaceDate')), local_date(row.get('lastRaceDate'))
    if start and finish and start <= day <= finish and (dt.date.fromisoformat(finish) - dt.date.fromisoformat(start)).days <= 31:
        day, date_end = start, finish
    else:
        date_end = day
    sid = f'{year}:{identity}:marathon'
    source_url = BASE + '/marathon/' + urllib.parse.quote(identity, safe='')
    image = next((u for key in ('imageSmall', 'image') if (u := url(row.get(key))) and '/default.' not in u.lower()), None)
    point = point_of(row)
    country = (row.get('countryCode') or '').upper()
    race = {'id': 'worldsmarathons:' + sid, 'source': 'worldsmarathons', 'sourceId': sid,
            'eventId': 'worldsmarathons:event:' + identity, 'editionId': f'worldsmarathons:{year}:{identity}',
            'name': title, 'eventName': title, 'date': day, 'dateEnd': date_end,
            'datePrecision': 'event-day' if day == date_end else 'event',
            'distanceKm': distance, 'elevationGainM': None, 'place': (row.get('city') or '').strip(),
            'countryCode': country if re.fullmatch(r'[A-Z]{2}', country) else None,
            'country': row.get('country'), 'continent': None,
            'longitude': point[0] if point else None, 'latitude': point[1] if point else None,
            'locationPrecision': 'event' if point else 'unknown',
            'locationId': f'worldsmarathons:event:{identity}', 'geonamesId': None,
            'website': url(row.get('website')), 'sourceUrl': source_url, 'image': image,
            'imageSource': source_url if image else None,
            'extensions': {'worldsmarathons': {'surface': surface_of(row.get('surface')),
                'sourceSurface': row.get('surface'), 'courseDifficulty': row.get('courseDifficulty'),
                'listingType': 'marathon-event', 'tags': [t['label'] for t in row.get('tags', []) if isinstance(t, dict) and isinstance(t.get('label'), str)]}}}
    race['sources'] = [{'provider': 'worldsmarathons', 'id': sid, 'url': source_url,
                       'fetchedAt': fetched_at, 'acquisition': 'search-api',
                       'values': {k: race.get(k) for k in ('name','eventName','date','dateEnd','datePrecision','distanceKm','place','countryCode')}}]
    return race, None


def normalize_capture(capture):
    fetched_at = capture['capturedAt']
    dt.datetime.fromisoformat(fetched_at)
    races, skipped, reports, seen = [], Counter(), [], set()
    if not capture.get('years'):
        raise FeedError('Empty calendar capture')
    for group in capture['years']:
        rows, year = group['results'], group['year']
        if year in seen or len(rows) != group['count'] or len({r.get('id') for r in rows}) != len(rows):
            raise FeedError('Incomplete or repeated calendar year')
        seen.add(year)
        reports.append({k: group[k] for k in ('year','count','pages')})
        for row in rows:
            race, reason = normalize(row, year, fetched_at)
            if race:
                races.append(race)
            else:
                skipped[reason] += 1
    if not races:
        raise FeedError('No usable full-marathon events; retaining the previous snapshot')
    provider_points = {r['id']: {k:r[k] for k in ('longitude','latitude','locationId','locationPrecision')} for r in races if r['longitude'] is not None}
    geocode(races)
    for race in races:
        race['locationId'] = race['locationId'].replace('itra:', 'worldsmarathons:', 1)
        if race['id'] in provider_points:
            race.update(provider_points[race['id']])
    return races, {'years': reports, 'eventsDownloaded': sum(g['count'] for g in reports), 'skipped': dict(skipped),
                   'completeness': 'search-count-verified', 'scope': 'Full marathon events; current year and next two years'}


def import_races(args, client=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    target = args.cache / 'races.json'
    fallback = args.snapshot
    previous = json.loads((target if target.exists() else fallback).read_text()) if target.exists() or fallback.exists() else None
    if not args.capture and previous and args.max_age_days > 0:
        age = (now.date() - dt.datetime.fromisoformat(previous['fetchedAt']).date()).days
        years = [g['year'] for g in previous.get('coverage', {}).get('years', [])]
        if 0 <= age < args.max_age_days and years == years_for(now.date()):
            print('World’s Marathons: reusing verified weekly snapshot', flush=True)
            return previous
    capture = json.loads(args.capture.read_text()) if args.capture else capture_calendar(client or Client(), now.date())
    if [g['year'] for g in capture['years']] != years_for(now.date()):
        raise FeedError('Capture does not cover the rolling three-year window')
    current, coverage = normalize_capture(capture)
    today, ids = now.date().isoformat(), {r['id'] for r in current}
    # Preserve past editions; remove future listings absent from a successful feed.
    archived = [r for r in (previous or {}).get('races', []) if r['id'] not in ids and (r.get('dateEnd') or r['date']) < today]
    coverage.update(races=len(current), archived=len(archived), upcoming=sum((r.get('dateEnd') or r['date']) >= today for r in current),
                    mapped=sum(r['longitude'] is not None for r in current), images=sum(bool(r['image']) for r in current),
                    surfaces=dict(Counter(r['extensions']['worldsmarathons']['surface'] or 'unknown' for r in current)))
    snapshot = {'schemaVersion':1, 'acquisition':'search-api', 'fetchedAt':capture['capturedAt'], 'coverage':coverage, 'races': current + archived}
    atomic_json(target, snapshot)
    atomic_json(fallback, snapshot)
    atomic_json(args.cache / 'status.json', {'state':'available','attemptedAt':now.isoformat()})
    print(json.dumps(coverage), flush=True)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / '.cache/worldsmarathons')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'data/worldsmarathons-snapshot.json')
    parser.add_argument('--capture', type=Path, help='Import a validated saved search capture')
    parser.add_argument('--max-age-days', type=int, default=7)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    with (args.cache / 'refresh.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('A World’s Marathons refresh is already running')
        try:
            import_races(args)
        except Exception as error:
            atomic_json(args.cache / 'status.json', {'state':'unavailable','attemptedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
                        'message':'Refresh failed; retaining the last verified marathon calendar.'})
            print(f'World’s Marathons refresh failed: {error}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
