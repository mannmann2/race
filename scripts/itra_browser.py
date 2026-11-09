#!/usr/bin/env python3
"""Rolling ITRA calendar import using ordinary displayed Chromium, with no saved session."""
import argparse
import copy
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time

from itra import (ROOT, CALENDAR, BASE, FeedError, Document, first_text, parse_date,
                  parse_calendar, parse_detail, race_identity, safe_url, geocode, atomic_json)

class DetailUnavailable(FeedError):
    pass


POINTS = dict(zip('zero one two three four five six'.split(), range(7)))


def event_dates(text):
    end = parse_date(text)
    match = re.fullmatch(r'(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', text or '')
    if match:
        start = parse_date(f'{match[1]} {match[3]} {match[4]}')
        if not start or not end or start > end:
            raise FeedError('Invalid event date range')
        return start, end
    if not end or ('-' in (text or '') and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text)):
        raise FeedError(f'Unrecognised calendar date: {text}')
    return end, end


def normalize_capture(capture):
    payload = capture['calendar']
    races, _ = parse_calendar('var raceSearchJsonSidePopupNew = ' + json.dumps(payload) + ';')
    expected = capture['metadata']['calendarDisplayedRaces']
    if not expected or len(races) != expected:
        raise FeedError(f'Incomplete calendar: parsed {len(races)}, expected {expected}')
    by_id = {r['sourceId']: r for r in races}
    coordinates = {}
    for row in capture.get('markers', []):
        if len(row) != 3:
            continue
        lat, lon, rid = row
        if all(isinstance(x, (int, float)) for x in (lat, lon)) and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
            coordinates[str(rid)] = (lon, lat)
    for row in payload:
        for fragment in row:
            root = Document(fragment).root
            for card in root.find(cls='events-list'):
                links = [n for n in card.find('a') if '/Races/RaceDetails/' in n.attrs.get('href', '')]
                courses = [n for n in links if n.find(cls='count')]
                if not courses:
                    continue
                start, end = event_dates(first_text(card, cls='date'))
                ids = [race_identity(n.attrs['href'], start[:4]) for n in courses]
                # The map may choose a different representative course for an event.
                positions = {coordinates[i.split(':')[-1]] for i in ids if i.split(':')[-1] in coordinates}
                point = next(iter(positions)) if len(positions) == 1 else None
                photo = next((safe_url(n.attrs.get('src')) for n in root.find('img') if '/Files/Events/' in n.attrs.get('src', '')), None)
                for link, source_id in zip(courses, ids):
                    race = by_id[source_id]
                    race.update(date=start, dateEnd=end, datePrecision='event-day' if start == end else 'event',
                                image=photo, imageSource=race['sourceUrl'] if photo else None)
                    if point:
                        race.update(longitude=point[0], latitude=point[1], locationPrecision='event',
                                    locationId=f'itra:event:{point[0]},{point[1]}')
                    icons = {POINTS[m[1]] for n in link.find('img')
                             if (m := re.fullmatch(r'/images/(zero|one|two|three|four|five|six)\.svg', n.attrs.get('src', '')))}
                    race['extensions']['itra']['endurancePoints'] = next(iter(icons)) if len(icons) == 1 else None
    # Country/continent metadata and town fallback; never replace provider coordinates.
    positions = {r['id']: {k:r.get(k) for k in ('longitude','latitude','locationPrecision','locationId')} for r in races if r['longitude'] is not None}
    geocode(races)
    for race in races:
        if race['id'] in positions:
            race.update(positions[race['id']])
    return races


def apply_details(listing, detail):
    result = copy.deepcopy(listing)
    for key in ('name','date','distanceKm','elevationGainM','website','image','imageSource','extensions'):
        if detail.get(key) is not None:
            result[key] = copy.deepcopy(detail[key])
    result.update(dateEnd=result['date'], datePrecision='race', detailsFetchedAt=detail['detailsFetchedAt'])
    # The current calendar is authoritative when it supplies a points value.
    points = listing['extensions']['itra']['endurancePoints']
    if points is not None:
        result['extensions']['itra']['endurancePoints'] = points
    return result


def fingerprint(race):
    return [race.get(k) for k in ('date','dateEnd','distanceKm','elevationGainM')] + [race['extensions']['itra']['endurancePoints']]


def retain_history(current, previous, today):
    ids = {r['id'] for r in current}
    # Future listings missing from a successful complete window are removed (e.g. cancellation).
    # Past editions remain searchable, but never manufacture next year's edition.
    return current + [r for r in previous if r['id'] not in ids and (r.get('dateEnd') or r.get('date') or today) < today]


class Browser:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False, args=['--no-sandbox'] if os.geteuid() == 0 else [])
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self

    def __exit__(self, *_):
        self.browser.close()
        self.playwright.stop()

    def calendar(self, path):
        response = self.page.goto(BASE + path, wait_until='domcontentloaded', timeout=60000)
        if response.status != 200:
            raise FeedError(f'ITRA returned HTTP {response.status}')
        self.page.wait_for_function('''() => typeof raceSearchJsonSidePopupNew !== 'undefined' &&
            raceSearchJsonSidePopupNew.length > 0 && /[0-9].*races found/.test(document.querySelector('.results')?.textContent || '') &&
            (location.pathname.endsWith('/RaceMap') || document.querySelector('#Next7day')?.value === '5') ''', timeout=60000)
        return self.page.evaluate('''() => ({rows:raceSearchJsonSidePopupNew,
            counts:document.querySelector('.results').textContent,
            from:document.querySelector('#Input_DateStart')?.value,
            to:document.querySelector('#Input_DateEnd')?.value})''')

    def capture(self):
        print('ITRA: loading rolling calendar', flush=True)
        calendar = self.calendar('/Races/RaceCalendar')
        print('ITRA: loading map locations', flush=True)
        markers = self.calendar('/Races/RaceMap')
        counts = re.search(r'([\d,]+)\s+events and\s+([\d,]+)\s+races found', calendar['counts'])
        if not counts:
            raise FeedError('Calendar result count missing')
        return {'calendar':calendar['rows'], 'markers':markers['rows'], 'metadata':{
            'capturedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
            'calendarDisplayedEvents':int(counts[1].replace(',','')),
            'calendarDisplayedRaces':int(counts[2].replace(',','')),
            'scope':'next 12 months', 'from':calendar['from'], 'to':calendar['to'],
            'mapCounts':markers['counts'].strip()}}

    def detail(self, race):
        time.sleep(.7)
        if not self.page.url.startswith(BASE + '/'):
            response = self.page.goto(race['sourceUrl'], wait_until='domcontentloaded', timeout=60000)
            result = {'status':response.status,'url':response.url,'text':response.text()}
        else:
            result = self.page.evaluate('''async url => {
                const r=await fetch(url,{signal:AbortSignal.timeout(35000)});return {status:r.status,url:r.url,text:await r.text()};
            }''', race['sourceUrl'])
        if result['status'] in (404,410):
            raise DetailUnavailable(f"Course unavailable (HTTP {result['status']})")
        if result['status'] != 200 or re.search(r'awswaf|captcha-container|Oops! Something Went Wrong', result['text'], re.I):
            raise FeedError(f"ITRA detail access failed (HTTP {result['status']})")
        try:
            if race_identity(result['url'], race['sourceId'][:4]) != race['sourceId']:
                raise FeedError('Course redirected to a different edition')
            return parse_detail(result['text'], race)
        except FeedError as error:
            raise DetailUnavailable(str(error)) from error


def load_bulk(args, browser, now):
    path = args.cache / 'bulk-listings.json'
    max_age = getattr(args, 'bulk_max_age_days', 0)
    if not args.capture and max_age > 0 and path.exists():
        try:
            cached = json.loads(path.read_text())
            captured = dt.datetime.fromisoformat(cached['metadata']['capturedAt'])
            age = now - captured
            rows = cached['races']
            if (cached['schemaVersion'] == 1 and age >= dt.timedelta(0) and (now.date()-captured.date()).days < max_age
                    and len(rows) == cached['metadata']['calendarDisplayedRaces']
                    and len({r['id'] for r in rows}) == len(rows) and rows):
                print('ITRA: reusing verified weekly bulk data; calendar not requested', flush=True)
                return rows, cached['metadata']
        except (ValueError, KeyError, TypeError):
            pass
    capture = json.loads(args.capture.read_text()) if args.capture else browser.capture()
    races = normalize_capture(capture)
    atomic_json(path, {'schemaVersion':1,'metadata':capture['metadata'],'races':races})
    return races, capture['metadata']


def import_races(args, browser=None):
    now = dt.datetime.now(dt.timezone.utc)
    races, bulk_meta = load_bulk(args, browser, now)
    today = now.date().isoformat()
    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    detail_path = cache / 'course-details.json'
    details = json.loads(detail_path.read_text()) if detail_path.exists() else {}
    failures_path = cache / 'detail-failures.json'
    failures = json.loads(failures_path.read_text()) if failures_path.exists() else {}
    old_path = cache / 'races.json'
    previous = json.loads(old_path.read_text()) if old_path.exists() else {'races':[]}
    # Prioritise unseen courses, then changed listings, then oldest detail refreshes.
    queue = sorted((r for r in races if (r.get('dateEnd') or r['date']) >= today), key=lambda r:(r['sourceId'] in details, details.get(r['sourceId'],{}).get('detailsFetchedAt',''), r['date'], r['id']))
    refreshed = 0
    attempted = 0
    failure = None
    for race in queue:
        saved = details.get(race['sourceId'])
        if saved and saved.get('fingerprint') == fingerprint(race) and (now-dt.datetime.fromisoformat(saved['detailsFetchedAt'])).days < 14:
            continue
        failed = failures.get(race['sourceId'])
        if failed and failed.get('fingerprint') == fingerprint(race) and (now-dt.datetime.fromisoformat(failed['attemptedAt'])).days < 1:
            continue
        if attempted >= args.detail_limit or browser is None:
            break
        attempted += 1
        try:
            enriched = browser.detail(race)
            enriched.update(detailsFetchedAt=dt.datetime.now(dt.timezone.utc).isoformat(), fingerprint=fingerprint(race))
            details[race['sourceId']] = enriched
            refreshed += 1
            failures.pop(race['sourceId'], None)
            if refreshed % 25 == 0:
                atomic_json(detail_path, details)
                print(f'ITRA: {refreshed} course details refreshed', flush=True)
        except DetailUnavailable as error:
            failures[race['sourceId']] = {'attemptedAt':now.isoformat(),'fingerprint':fingerprint(race),'message':str(error)}
            print(f'ITRA: skipping unavailable course {race["sourceId"]}: {error}', flush=True)
            continue
        except Exception as error:
            # Stop on access failures; preserve the verified bulk calendar and prior detail cache.
            failure = str(error)
            print(f'ITRA detail enrichment stopped: {error}', file=sys.stderr, flush=True)
            break
    atomic_json(detail_path, details)
    atomic_json(failures_path, failures)
    result = []
    for listing in races:
        saved = details.get(listing['sourceId'])
        race = apply_details(listing, saved) if saved and saved.get('fingerprint') == fingerprint(listing) else listing
        race['sources'] = [{'provider':'itra','id':race['sourceId'],'url':race['sourceUrl'],
            'fetchedAt':bulk_meta['capturedAt'], 'detailsFetchedAt':race.get('detailsFetchedAt'),
            'acquisition':'browser-calendar', 'values':{k:race.get(k) for k in ('name','eventName','date','dateEnd','datePrecision','distanceKm','elevationGainM','place','countryCode')}}]
        result.append(race)
    combined = retain_history(result, previous['races'], today)
    coverage = {**bulk_meta, 'races':len(result), 'archived':len(combined)-len(result),
        'completeness':'calendar-count-verified', 'details':sum(r.get('detailsFetchedAt') is not None for r in result),
        'rated':sum(r['extensions']['itra']['endurancePoints'] is not None for r in result),
        'mountainRated':sum(r['extensions']['itra']['mountainLevel'] is not None for r in result),
        'mapped':sum(r['longitude'] is not None for r in result), 'detailUnavailable':sum(r['sourceId'] in failures for r in result), 'detailRefreshError':failure}
    snapshot = {'schemaVersion':1,'acquisition':'browser-calendar','fetchedAt':bulk_meta['capturedAt'], 'coverage':coverage,'races':combined}
    atomic_json(old_path, snapshot)
    atomic_json(ROOT / 'data/itra-snapshot.json', snapshot)
    atomic_json(cache / 'status.json', {'state':'available','attemptedAt':now.isoformat(),
        'message':'Calendar count verified; course details enrich incrementally.', 'detailRefreshError':failure})
    print(json.dumps(coverage), flush=True)
    return snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=ROOT/'.cache/itra')
    parser.add_argument('--capture',type=Path,help='Use a saved credential-free bulk capture (offline)')
    parser.add_argument('--detail-limit',type=int,default=400)
    parser.add_argument('--bulk-max-age-days',type=int,default=0,help='Reuse verified bulk listings for this many days; 0 forces acquisition')
    args=parser.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    with (args.cache/'refresh.lock').open('w') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit('An ITRA refresh is already running')
        try:
            if args.capture: import_races(args)
            else:
                with Browser() as browser: import_races(args,browser)
        except Exception as error:
            atomic_json(args.cache/'status.json',{'state':'unavailable','attemptedAt':dt.datetime.now(dt.timezone.utc).isoformat(),
                'message':'ITRA refresh failed; retaining the last verified calendar.'})
            print(f'ITRA refresh failed: {error}',file=sys.stderr)
            return 1
    return 0

if __name__=='__main__': sys.exit(main())
