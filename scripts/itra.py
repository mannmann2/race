#!/usr/bin/env python3
"""ITRA calendar batches + cached course details. No challenge bypass or guessed ratings.

The calendar format is based on public implementations; a successful live import
is still required to establish coverage. Captured HTML/HAR responses use the same
parser as network responses. Only response bodies are retained, never cookies.
"""
import argparse
import base64
import copy
import datetime as dt
import gzip
import hashlib
import html
from html.parser import HTMLParser
import http.cookiejar
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://itra.run'
CALENDAR = BASE + '/Races/RaceCalendar'
MONTHS = {name.lower(): i for i, name in enumerate('January February March April May June July August September October November December'.split(), 1)}


class FeedError(ValueError):
    pass


class Node:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(c if isinstance(c, str) else c.text for c in self.children)).strip()

    def find(self, tag=None, cls=None):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get('class', '').split()):
                    result.append(child)
                result.extend(child.find(tag, cls))
        return result


class Document(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.current = self.root
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def safe_url(value, base=BASE):
    if not value:
        return None
    value = urllib.parse.urljoin(base, html.unescape(value))
    p = urllib.parse.urlsplit(value)
    return value if p.scheme in ('http', 'https') and p.hostname and not p.username and not p.password else None


def race_identity(url, year=None):
    p = urllib.parse.urlsplit(safe_url(url) or '')
    m = re.fullmatch(r'/Races/RaceDetails/[^/]+/(\d{4})/(\d+)/?', p.path, re.I)
    short = re.fullmatch(r'/Races/RaceDetails/(\d+)/?', p.path, re.I)
    if p.hostname == 'itra.run' and short and re.fullmatch(r'\d{4}', str(year or '')):
        return f'{year}:{short[1]}'
    if p.hostname != 'itra.run' or not m:
        raise FeedError('Unrecognised ITRA course URL')
    return f'{m[1]}:{m[2]}'


def numeric(value):
    m = re.search(r'[+-]?\d[\d\s.,]*', str(value if value is not None else ''))
    if not m:
        return None
    value = m[0].strip().replace(' ', '')
    if ',' in value and '.' in value:
        value = value.replace(',', '')
    elif ',' in value:
        value = value.replace(',', '.' if len(value.split(',')[-1]) != 3 else '')
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def parse_date(value):
    value = re.sub(r'\s+', ' ', value or '').strip()
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', value)
    if m:
        parts = [int(x) for x in m.groups()]
    else:
        m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', value)
        if not m or m[2].lower() not in MONTHS:
            return None
        parts = [int(m[3]), MONTHS[m[2].lower()], int(m[1])]
    try:
        return dt.date(*parts).isoformat()
    except ValueError:
        return None


def field(root, label):
    pattern = re.compile(r'^' + re.escape(label) + r'\s*:?\s*(.*)$', re.I)
    # Smallest labelled container; never mine event descriptions for measurements.
    values = [pattern.match(n.text) for n in root.find() if len(n.text) <= 160 and n.tag not in ('script', 'style')]
    values = [m[1] for m in values if m and m[1]]
    return min(values, key=len) if values else None


def first_text(root, cls=None, tag=None):
    nodes = root.find(tag, cls)
    return nodes[0].text if nodes else None


def parse_calendar(content):
    marker = re.search(r'\b(?:var|let|const)\s+raceSearchJsonSidePopupNew\s*=\s*', content)
    if not marker:
        raise FeedError('Calendar race array missing; refusing an empty import')
    try:
        payload, _ = json.JSONDecoder().raw_decode(content[marker.end():])
    except ValueError as error:
        raise FeedError('Calendar data format changed') from error

    def fragments(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from fragments(item)

    races, events = {}, set()
    for fragment in fragments(payload):
        root = Document(fragment).root
        cards = root.find(cls='events-list') or [root]
        for card in cards:
            event_name = first_text(card, tag='h4')
            if not event_name:
                continue
            location = first_text(card, cls='location') or ''
            flag = next((re.search(r'/CountryFlags/([a-z]{2})\.', n.attrs.get('src', ''), re.I) for n in card.find('img') if '/countryflags/' in n.attrs.get('src', '').lower()), None)
            country = flag[1].upper() if flag else None
            place = re.sub(r',\s*[A-Z]{2,3}\s*$', '', location).strip()
            event_date = parse_date(first_text(card, cls='date'))
            links = [n for n in card.find('a') if '/Races/RaceDetails/' in n.attrs.get('href', '')]
            if not links:
                continue
            event_url = safe_url(links[0].attrs.get('href'))
            events.add(event_url)
            course_links = [n for n in links if n.find(cls='count')]
            if not course_links:
                # An event link can lead to a default course, but is not itself proof
                # of a course listing. Reject rather than manufacturing a race.
                raise FeedError('Calendar event has no recognised course links')
            for link in course_links:
                source_url = safe_url(link.attrs.get('href'))
                source_id = race_identity(source_url, (event_date or '')[:4])
                distance = numeric(first_text(link, cls='count'))
                if distance is None or distance < 0:
                    raise FeedError('Calendar course distance missing')
                race = {'id': f'itra:{source_id}', 'sourceId': source_id, 'source': 'itra',
                        'sourceUrl': source_url, 'eventId': f'itra:event:{race_identity(event_url, (event_date or "")[:4])}',
                        'editionId': f'itra:event:{race_identity(event_url, (event_date or "")[:4])}',
                        'name': f'{event_name} · {distance:g} km', 'eventName': event_name,
                        'date': event_date, 'datePrecision': 'event', 'distanceKm': distance,
                        'elevationGainM': numeric(first_text(link, cls='distance')),
                        'place': place or None, 'countryCode': country, 'website': None,
                        'image': None, 'imageSource': None, 'longitude': None, 'latitude': None,
                        'locationPrecision': 'unknown', 'geonamesId': None,
                        'extensions': {'itra': {'endurancePoints': None, 'mountainLevel': None, 'finisherLevel': None}}}
                races[source_id] = race
    if not races:
        raise FeedError('Calendar contained no usable courses; previous snapshot preserved')
    return list(races.values()), len(events)


def parse_detail(content, listing):
    root = Document(content).root
    race = copy.deepcopy(listing)
    date = parse_date(field(root, 'Race Date'))
    distance = numeric(field(root, 'Distance'))
    if not date or distance is None or distance < 0:
        raise FeedError('Course detail lacks a labelled race date or distance')
    if date[:4] != race['sourceId'][:4]:
        raise FeedError('Course date disagrees with edition URL')
    canonical = next((safe_url(n.attrs.get('href')) for n in root.find('link') if n.attrs.get('rel') == 'canonical'), None)
    if canonical and race_identity(canonical, date[:4]) != race['sourceId']:
        raise FeedError('Course detail redirected to another edition')
    race.update(date=date, datePrecision='race', distanceKm=distance)
    name = first_text(root, tag='h3')
    if name:
        race['name'] = name
    gain = numeric(field(root, 'Elevation Gain'))
    if gain is not None and gain < 0:
        raise FeedError('Invalid elevation gain')
    if gain is not None:
        race['elevationGainM'] = gain
    points = numeric(field(root, 'ITRA Points') or field(root, 'Endurance Points'))
    if points is None:
        icons = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
        found = set()
        for image in root.find('img'):
            m = re.search(r'/itra_numbers/icons/(zero|one|two|three|four|five|six|[0-6])\.svg(?:\?|$)', image.attrs.get('src', ''), re.I)
            if m:
                word = m[1].lower()
                found.add(int(word) if word.isdigit() else icons[word])
        if len(found) == 1:
            points = found.pop()
    ratings = {'endurancePoints': points, 'mountainLevel': numeric(field(root, 'Mountain Level')), 'finisherLevel': numeric(field(root, 'Finisher Level'))}
    for key, maximum in [('endurancePoints', 6), ('mountainLevel', 12), ('finisherLevel', 1000)]:
        value = ratings[key]
        if value is not None and (not 0 <= value <= maximum or value != int(value)):
            raise FeedError(f'Invalid ITRA {key}')
    race['extensions']['itra'] = ratings
    image = next((safe_url(n.attrs.get('content'), race['sourceUrl']) for n in root.find('meta') if n.attrs.get('property') == 'og:image'), None)
    if not image:
        image = next((safe_url(n.attrs.get('src')) for n in root.find('img') if '/Files/Events/' in n.attrs.get('src', '')), None)
    if image:
        race.update(image=image, imageSource=race['sourceUrl'])
    # Website links only when explicitly labelled; registration/social links are not event identity.
    for link in root.find('a'):
        if re.search(r'^(?:official |event |race )?website\b', link.text, re.I):
            race['website'] = safe_url(link.attrs.get('href'))
            break
    return race


def geocode(races):
    from refresh import norm
    countries_path = ROOT / '.cache/countries.json'
    countries_raw = json.loads(countries_path.read_text()) if countries_path.exists() else []
    countries = {c['cca2']: c for c in countries_raw}
    needed = {(r['countryCode'], norm(r.get('place') or '')) for r in races if r.get('countryCode') and norm(r.get('place') or '')}
    cities, populations = {}, {}
    needed_countries = {cc for cc, _ in needed}
    city_path = ROOT / '.cache/cities1000.zip'
    if city_path.exists():
        with zipfile.ZipFile(city_path) as archive, archive.open('cities1000.txt') as source:
            for line in source:
                f = line.decode().split('\t')
                if f[8] not in needed_countries:
                    continue
                for name in {f[1], f[2], *f[3].split(',')}:
                    key = (f[8], norm(name))
                    if key in needed and int(f[14] or 0) > populations.get(key, -1):
                        cities[key] = (float(f[5]), float(f[4]), f[0])
                        populations[key] = int(f[14] or 0)
    for r in races:
        country = countries.get(r['countryCode'], {})
        region = country.get('region')
        r['country'] = country.get('name', {}).get('common', r['countryCode'])
        r['continent'] = ('South America' if country.get('subregion') == 'South America' else 'North America') if region == 'Americas' else region
        city = cities.get((r['countryCode'], norm(r.get('place') or '')))
        if city:
            r.update(longitude=city[0], latitude=city[1], geonamesId=city[2], locationPrecision='town')
        r['locationId'] = f"itra:place:{r['countryCode']}:{norm(r.get('place') or '')}"


class ItraRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.hostname != 'itra.run' or parsed.scheme != 'https':
            raise FeedError('ITRA redirected outside its origin')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, cache, captured=None, offline=False):
        self.cache, self.captured, self.offline = cache, captured or {}, offline
        self.opener = urllib.request.build_opener(ItraRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.last = 0

    def request(self, url, form=None):
        if urllib.parse.urlsplit(url).hostname != 'itra.run' or not url.startswith('https://'):
            raise FeedError('Only public HTTPS ITRA URLs can be fetched')
        if self.offline:
            raise FeedError('Response missing from offline capture')
        time.sleep(max(0, .7 - (time.monotonic() - self.last)))
        try:
            request = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode() if form else None)
            with self.opener.open(request, timeout=35) as response:
                if response.status != 200 or response.headers.get('x-amzn-waf-action') == 'challenge':
                    raise FeedError(f'ITRA access blocked (HTTP {response.status}); previous snapshot preserved')
                raw = response.read(12_000_001)
                if not raw or len(raw) > 12_000_000:
                    raise FeedError('ITRA returned an empty or oversized response')
                content = raw.decode('utf-8', errors='replace')
                if re.search(r'captcha-container|awswaf|Oops! Something Went Wrong', content, re.I):
                    raise FeedError('ITRA returned a challenge/error page')
                return content
        except urllib.error.HTTPError as error:
            raise FeedError(f'ITRA request failed (HTTP {error.code}); previous snapshot preserved') from error
        finally:
            self.last = time.monotonic()

    def detail(self, url):
        if url in self.captured:
            return self.captured[url]
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.html')
        if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
            return path.read_text()
        content = self.request(url)
        # Validate before caching so challenges never become successful cache hits.
        root = Document(content).root
        if not field(root, 'Race Date') or not field(root, 'Distance'):
            raise FeedError('Invalid ITRA detail response')
        path.write_text(content)
        return content

    def calendar(self, countries):
        content = self.request(CALENDAR)
        inputs = Document(content).root.find('input')
        token = next((n.attrs.get('value') for n in inputs if n.attrs.get('name') == '__RequestVerificationToken'), None)
        if not token:
            raise FeedError('ITRA search token missing')
        form = [('__RequestVerificationToken', token), ('Input.DateValue', '5'), ('Input.isDateFilterApplied', 'true'), ('Input.resultcount', '100000'), ('Input.NationalLeagues', 'false'), ('Input.NationalLeague', 'false')]
        form += [('Input.Country', c) for c in countries]
        return self.request(CALENDAR, form)


def read_capture(path):
    capture = json.loads(path.read_text())
    calendars, details = [], {}
    for entry in capture.get('log', {}).get('entries', []):
        request, response = entry.get('request', {}), entry.get('response', {})
        url = request.get('url', '')
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname != 'itra.run' or response.get('status') != 200:
            continue
        body = response.get('content', {})
        text = body.get('text', '')
        if body.get('encoding') == 'base64':
            text = base64.b64decode(text).decode('utf-8')
        if parsed.path in ('/Races/RaceCalendar', '/Races/RaceMap') and 'raceSearchJsonSidePopupNew' in text:
            calendars.append(text)
        elif '/Races/RaceDetails/' in parsed.path and text:
            details[urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, '', ''))] = text
    if not calendars:
        raise FeedError('Capture has no successful calendar response bodies')
    return calendars, details


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    os.replace(temp, path)


def indexed_snapshot(document):
    """Normalize audited factual extracts from public index copies, not live HTML.

Retrieval time must never masquerade as the age of the indexed source. Endurance
points require the exact linked ITRA number icon as evidence, not a calculation.
"""
    from refresh import norm
    if document.get('schemaVersion') != 1 or document.get('acquisition') != 'public-index' or not document.get('records'):
        raise FeedError('Invalid indexed-source document')
    retrieved = dt.datetime.fromisoformat(document['retrievedAt']).isoformat()
    countries_raw = json.loads((ROOT / '.cache/countries.json').read_text())
    country_codes = {}
    for country in countries_raw:
        for name in [country['name']['common'], country['name']['official'], *country.get('altSpellings', [])]:
            country_codes[norm(name)] = country['cca2']
    country_codes.update({'turkey': 'TR', 'vietnam': 'VN'})
    races, seen = [], set()
    for item in document['records']:
        date = parse_date(item.get('date'))
        if not date:
            raise FeedError('Indexed course lacks a valid race date')
        source_id = race_identity(item['sourceUrl'], date[:4])
        if source_id != item['sourceId'] or source_id in seen:
            raise FeedError('Indexed course identity mismatch or duplicate')
        if source_id[:4] != date[:4]:
            raise FeedError('Indexed course edition/date mismatch')
        seen.add(source_id)
        country_code = country_codes.get(norm(item['country']))
        if not country_code or not item.get('name') or not item.get('eventName'):
            raise FeedError('Indexed course lacks a known country or name')
        for key in ['distanceKm', 'elevationGainM']:
            value = item.get(key)
            if (key == 'distanceKm' and value is None) or (value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0)):
                raise FeedError(f'Invalid indexed {key}')
        ratings = {key: item.get(key) for key in ['endurancePoints', 'mountainLevel', 'finisherLevel']}
        for key, maximum in [('endurancePoints', 6), ('mountainLevel', 12), ('finisherLevel', 1000)]:
            value = ratings[key]
            if value is not None and (type(value) is not int or not 0 <= value <= maximum):
                raise FeedError(f'Invalid indexed {key}')
        if ratings['endurancePoints'] is not None:
            word = ['zero', 'one', 'two', 'three', 'four', 'five', 'six'][ratings['endurancePoints']]
            if item.get('pointsIcon') != f'{BASE}/images/itra_numbers/icons/{word}.svg':
                raise FeedError('Indexed Endurance Points lack matching source-icon evidence')
        race = {key: item.get(key) for key in ['name', 'eventName', 'date', 'distanceKm', 'elevationGainM', 'place', 'country', 'sourceUrl']}
        race.update(id=f'itra:{source_id}', source='itra', sourceId=source_id,
                    eventId=f'itra:listing:{source_id}', editionId=f'itra:listing:{source_id}',
                    datePrecision='race', countryCode=country_code, website=None, image=None, imageSource=None,
                    longitude=None, latitude=None, locationPrecision='unknown', geonamesId=None,
                    extensions={'itra': ratings})
        race['sources'] = [{'provider': 'itra', 'id': source_id, 'url': race['sourceUrl'], 'fetchedAt': None,
                            'retrievedAt': retrieved, 'acquisition': 'public-index', 'indexAge': item.get('indexAge'),
                            'pointsIcon': item.get('pointsIcon'),
                            'values': {key: item.get(key) for key in ['name', 'eventName', 'date', 'distanceKm', 'elevationGainM', 'place', 'country', 'endurancePoints', 'mountainLevel', 'finisherLevel']}}]
        races.append(race)
    geocode(races)
    coverage = {'scope': document.get('coverage'), 'completeness': 'selected-indexed-pages', 'races': len(races),
                'rated': sum(r['extensions']['itra']['endurancePoints'] is not None for r in races),
                'mountainRated': sum(r['extensions']['itra']['mountainLevel'] is not None for r in races)}
    return {'schemaVersion': 1, 'acquisition': 'public-index', 'retrievedAt': retrieved, 'fetchedAt': None,
            'coverage': coverage, 'races': races}


def run(args):
    cache = args.cache
    cache.mkdir(parents=True, exist_ok=True)
    if args.indexed_input:
        snapshot = indexed_snapshot(json.loads(args.indexed_input.read_text()))
        # Preserve the failed live-attempt status. The source metadata carries the
        # fallback provenance independently, so a later failed refresh cannot hide it.
        atomic_json(cache / 'races.json', snapshot)
        print(json.dumps(snapshot['coverage']))
        return
    detail_cache = cache / 'details'
    detail_cache.mkdir(exist_ok=True)
    calendars, captured = read_capture(args.har) if args.har else ([], {})
    if args.html:
        calendars += [p.read_text() for p in args.html]
    client = Client(detail_cache, captured, args.offline)
    if not calendars:
        calendars = [client.calendar(args.country)]
    listings, event_count = {}, 0
    for page in calendars:
        races, count = parse_calendar(page)
        event_count += count
        listings.update({r['id']: r for r in races})
    races = []
    for listing in listings.values():
        race = listing if args.listing_only else parse_detail(client.detail(listing['sourceUrl']), listing)
        races.append(race)
        if len(races) % 25 == 0:
            print(f'ITRA: {len(races)}/{len(listings)} courses processed', flush=True)
    geocode(races)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for race in races:
        race['sources'] = [{'provider': 'itra', 'id': race['sourceId'], 'url': race['sourceUrl'], 'fetchedAt': now,
                            'values': {k: race[k] for k in ('name', 'eventName', 'date', 'datePrecision', 'distanceKm', 'elevationGainM', 'place', 'countryCode')}}]
    coverage = {'scope': 'captured responses' if args.har or args.html else 'next 12 months', 'countries': args.country,
                'calendarPages': len(calendars), 'eventOccurrences': event_count, 'races': len(races),
                'details': 0 if args.listing_only else len(races), 'completeness': 'unverified',
                'rated': sum(r['extensions']['itra']['endurancePoints'] is not None for r in races),
                'mountainRated': sum(r['extensions']['itra']['mountainLevel'] is not None for r in races)}
    # Unknown server-side limits are exposed as partial coverage, never labelled worldwide/complete.
    snapshot = {'schemaVersion': 1, 'fetchedAt': now, 'coverage': coverage, 'races': races}
    atomic_json(cache / 'races.json', snapshot)
    atomic_json(cache / 'status.json', {'state': 'partial', 'attemptedAt': now, 'message': 'Imported available ITRA responses; full calendar coverage is not verified.'})
    print(json.dumps(coverage))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / '.cache/itra')
    parser.add_argument('--country', action='append', default=[], help='ISO2 country filter; repeat for multiple countries')
    parser.add_argument('--har', type=Path, help='Read response bodies from a browser capture; credentials are ignored')
    parser.add_argument('--html', type=Path, action='append', help='Read saved calendar HTML')
    parser.add_argument('--offline', action='store_true', help='Use only captured/cached responses')
    parser.add_argument('--listing-only', action='store_true', help='Import calendar summaries; ratings remain unknown')
    parser.add_argument('--indexed-input', type=Path, help='Import audited factual extracts from public indexed ITRA pages')
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        atomic_json(args.cache / 'status.json', {'state': 'unavailable', 'attemptedAt': dt.datetime.now(dt.timezone.utc).isoformat(), 'message': 'ITRA refresh failed. Any previous successful snapshot is retained.'})
        print(f'ITRA refresh failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
