#!/usr/bin/env python3
"""Resolve country/region conflicts during composition; never geocode in the browser."""
import collections
import gzip
import io
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
import zipfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCATION_FIELDS = ('longitude', 'latitude', 'locationPrecision', 'locationId', 'geonamesId',
                   'countryCode', 'country', 'continent', 'place')


def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode().lower()).strip()


def event_key(value):
    return re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', value or '').casefold()).strip()


def distance(a, b):
    x, y = map(math.radians, a)
    u, v = map(math.radians, b)
    value = math.sin((y-v)/2)**2 + math.cos(y)*math.cos(v)*math.sin((x-u)/2)**2
    return 12742 * math.asin(min(1, math.sqrt(value)))


def in_ring(ring, x, y):
    inside = False
    a, b = ring[-1]
    for u, v in ring:
        if (v > y) != (b > y) and x < (a-u)*(y-v)/(b-v)+u:
            inside = not inside
        a, b = u, v
    return inside


class Borders:
    def __init__(self, countries):
        self.countries = {}
        self.cache = {}
        self.plausible_cache = {}
        for cc, polygons in countries.items():
            self.countries[cc] = [(min(x for x, y in p[0]), min(y for x, y in p[0]),
                                   max(x for x, y in p[0]), max(y for x, y in p[0]), p) for p in polygons]

    def contains(self, cc, point):
        key = (cc, *point)
        if key in self.cache:
            return self.cache[key]
        x, y = point
        value = any(w <= x <= e and s <= y <= n and in_ring(p[0], x, y)
                    and not any(in_ring(h, x, y) for h in p[1:])
                    for w, s, e, n, p in self.countries.get(cc, []))
        self.cache[key] = value
        return value

    def plausible(self, cc, point, buffer_km=20):
        key = (cc, *point, buffer_km)
        if key in self.plausible_cache:
            return self.plausible_cache[key]
        related = {'CN': ['HK', 'MO'], 'GB': ['IM', 'JE', 'GG', 'GI'],
                   'US': ['PR', 'VI', 'GU', 'AS', 'MP'],
                   'FR': ['RE', 'MQ', 'GP', 'GF', 'YT', 'PF', 'NC', 'PM', 'BL', 'MF']}
        codes = [cc, *related.get(cc, [])]
        if cc not in self.countries or any(self.contains(c, point) for c in codes):
            self.plausible_cache[key] = True
            return True
        # A distance to the coastline preserves tiny islands and near-border starts;
        # sampling around a point can miss an entire narrow island.
        x, y = point
        scale_x = max(1, 111 * math.cos(math.radians(y)))
        margin_x, margin_y = buffer_km / scale_x, buffer_km / 111
        for code in codes:
            for w, south, east, north, poly in self.countries.get(code, []):
                if not (w-margin_x <= x <= east+margin_x and south-margin_y <= y <= north+margin_y):
                    continue
                for ring in poly:
                    a, b = ring[-1]
                    for u, v in ring:
                        ax, ay, bx, by = (a-x)*scale_x, (b-y)*111, (u-x)*scale_x, (v-y)*111
                        dx, dy = bx-ax, by-ay
                        t = max(0, min(1, -(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
                        if (ax+t*dx)**2+(ay+t*dy)**2 <= buffer_km*buffer_km:
                            self.plausible_cache[key] = True
                            return True
                        a, b = u, v
        self.plausible_cache[key] = False
        return False


def place_parts(place):
    return [p.strip() for p in re.split(r'[,;/]', place or '') if p.strip()]


def city_queries(place):
    parts = place_parts(place)
    # Whole compound names (Zell/Mosel, Burg (Spreewald)) precede shorter aliases.
    values = [place or '', *parts]
    if parts:
        values.append(re.sub(r'\s*\([^)]*\)', '', parts[0]))
    return list(dict.fromkeys(norm(v) for v in values if norm(v)))


def load_cities(races, path):
    needed = {(r.get('countryCode'), q) for r in races for q in city_queries(r.get('place'))}
    result = collections.defaultdict(dict)
    if not path.exists():
        return result
    with zipfile.ZipFile(path) as archive, archive.open('cities500.txt' if 'cities500.txt' in archive.namelist() else 'cities1000.txt') as rows:
        for line in rows:
            f = line.decode().split('\t')
            keys = {(f[8], norm(n)) for n in [f[1], f[2], *f[3].split(',')]} & needed
            if not keys:
                continue
            city = {'id': f[0], 'name': f[1], 'primary': {norm(f[1]), norm(f[2])},
                    'country': f[8], 'admin': f[10], 'point': [float(f[5]), float(f[4])],
                    'population': int(f[14] or 0)}
            for key in keys:
                result[key][city['id']] = city
    return result


class Resolver:
    def __init__(self, cities, regions, borders, countries, overrides=()):
        self.cities, self.borders, self.countries, self.overrides = cities, borders, countries, overrides
        self.regions = collections.defaultdict(lambda: collections.defaultdict(set))
        for key, names in regions.items():
            cc, code = key.split('.', 1)
            for label in [code, *names]:
                self.regions[cc][norm(label)].add(code)

    def candidates(self, race):
        cc, place = race.get('countryCode'), race.get('place') or ''
        parts = place_parts(place)
        country = self.countries.get(cc, {})
        country_labels = {norm(n) for n in [cc or '', country.get('name', {}).get('common', ''),
                          country.get('name', {}).get('official', ''), *country.get('altSpellings', [])]}
        if parts and norm(parts[-1]) in country_labels:
            parts = parts[:-1]
        # Only explicit region components, never words found inside an event name.
        regions = set()
        for part in parts[1:]:
            regions.update(self.regions[cc].get(norm(part), []))
        for q in city_queries(place):
            cities = list(self.cities.get((cc, q), {}).values())
            if not cities:
                continue
            if regions:
                cities = [c for c in cities if c['admin'] in regions]
                if not cities:
                    return [], True
            primary = [c for c in cities if q in c['primary']]
            return primary or cities, bool(regions)
        return [], bool(regions)

    @staticmethod
    def town(city):
        return {'longitude': city['point'][0], 'latitude': city['point'][1],
                'geonamesId': city['id'], 'locationPrecision': 'town',
                'locationId': f"geonames:{city['id']}"}

    def resolve(self, races):
        corrections, accepted, review = {}, [], []
        prepared, references = [], collections.defaultdict(list)
        for original in races:
            r = dict(original)
            reason = None
            evidence = None
            for rule in self.overrides:
                match = rule['match']
                if ((not match.get('source') or r.get('source') == match['source'])
                        and r.get('countryCode') == match.get('countryCode')
                        and event_key(r.get('eventName')) in {event_key(n) for n in match['eventNames']}
                        and (not match.get('place') or norm(r.get('place')) in {norm(p) for p in match['place']})):
                    r.update(rule['location'])
                    country = self.countries.get(r.get('countryCode'), {})
                    if 'countryCode' in rule['location']:
                        r.update(country=country.get('name', {}).get('common', r['countryCode']),
                                 continent=country.get('region'))
                    reason, evidence = 'reviewed-location', rule['evidence']
                    break
            point = (r.get('longitude'), r.get('latitude'))
            if all(isinstance(v, (int, float)) for v in point) and not reason:
                cc = r.get('countryCode')
                if not self.borders.plausible(cc, point):
                    flips = {(point[0]*a, point[1]*b) for a, b in [(-1, 1), (1, -1), (-1, -1)]}
                    valid = [p for p in flips if self.borders.contains(cc, p)]
                    if len(valid) == 1:
                        r.update(longitude=valid[0][0], latitude=valid[0][1], geonamesId=None,
                                 locationId=f"corrected:{cc}:{valid[0][0]},{valid[0][1]}")
                        reason = 'coordinate-sign'
                    else:
                        candidates, _ = self.candidates(r)
                        # A single exact locality in the correct country is safe; population is not evidence.
                        if len(candidates) == 1:
                            r.update(self.town(candidates[0]))
                            reason = 'outside-country-town'
                        else:
                            r.update(longitude=None, latitude=None, geonamesId=None,
                                     locationPrecision='unknown', locationId='unlocated:'+r['id'])
                            reason = 'outside-country-unresolved'
                            review.append({'id': r['id'], 'event': r.get('eventName'), 'place': r.get('place'),
                                           'country': cc, 'point': point, 'reason': reason})
            # The provider point cannot retain the ID of a different fallback town.
            if r.get('locationPrecision') == 'event' and r.get('geonamesId'):
                r['geonamesId'] = None
            prepared.append((original, r, reason, evidence))
            if r.get('locationPrecision') == 'event' and r.get('longitude') is not None:
                references[(r.get('countryCode'), event_key(r.get('eventName')))].append(r)

        for original, r, reason, evidence in prepared:
            candidates, region_hint = self.candidates(r)
            if r.get('locationPrecision') == 'town' and not reason:
                chosen = None
                if len(candidates) == 1:
                    chosen = candidates[0]
                elif candidates:
                    # A supplied event point can distinguish nearby towns from distant namesakes.
                    refs = references[(r.get('countryCode'), event_key(r.get('eventName')))] if event_key(r.get('eventName')) else []
                    votes = set()
                    for ref in refs:
                        if (ref.get('date') or '')[:4] != (r.get('date') or '')[:4]:
                            continue
                        ranked = sorted((distance(c['point'], (ref['longitude'], ref['latitude'])), c['id']) for c in candidates)
                        if ranked[0][0] < 35 and (len(ranked) == 1 or ranked[1][0] > 100):
                            votes.add(ranked[0][1])
                    if len(votes) == 1:
                        chosen = next(c for c in candidates if c['id'] in votes)
                if chosen and chosen['id'] != r.get('geonamesId'):
                    r.update(self.town(chosen))
                    reason = 'region-locality' if region_hint else 'corroborated-locality'
                elif region_hint and not candidates:
                    # Region metadata can itself be wrong (GeoNames currently puts Pai
                    # in Chiang Mai). Flag the conflict instead of inventing a new pin.
                    review.append({'id': r['id'], 'event': r.get('eventName'), 'place': r.get('place'),
                                   'country': r.get('countryCode'), 'reason': 'region-locality-unresolved'})
                elif len(candidates) > 1 and any(distance(candidates[0]['point'], c['point']) > 50 for c in candidates[1:]):
                    review.append({'id': r['id'], 'event': r.get('eventName'), 'place': r.get('place'),
                                   'country': r.get('countryCode'), 'reason': 'ambiguous-town',
                                   'candidates': [{'id': c['id'], 'name': c['name'], 'admin': c['admin'], 'point': c['point']} for c in candidates]})
            changed = {k: r.get(k) for k in LOCATION_FIELDS if r.get(k) != original.get(k)}
            if changed:
                corrections[r['id']] = changed
                if reason:
                    accepted.append({'id': r['id'], 'event': r.get('eventName'), 'place': r.get('place'),
                                     'reason': reason, 'before': {k: original.get(k) for k in LOCATION_FIELDS},
                                     'after': changed, **({'evidence': evidence} if evidence else {})})
        return {'corrections': corrections, 'accepted': accepted, 'review': review}


def main():
    races = json.load(sys.stdin)
    geo = ROOT/'scripts/geo'
    borders = Borders(json.loads(gzip.decompress((geo/'countries.json.gz').read_bytes())))
    regions = json.loads((geo/'admin1.json').read_text())
    countries_path = ROOT/'.cache/countries.json'
    countries = {c['cca2']: c for c in json.loads(countries_path.read_text())} if countries_path.exists() else {}
    overrides = json.loads((ROOT/'scripts/location-overrides.json').read_text())
    # Corrections to a source country also need its city's candidates available.
    candidates = list(races)
    for rule in overrides:
        if rule['location'].get('countryCode'):
            candidates.extend([{**r, 'countryCode': rule['location']['countryCode']} for r in races
                               if event_key(r.get('eventName')) in {event_key(n) for n in rule['match']['eventNames']}])
    smaller = ROOT/'.cache/cities500.zip'
    existing = ROOT/'.cache/cities1000.zip'
    # Reuse GeoNames locally. A new production host fetches the fuller gazetteer
    # once; offline builds can keep using the existing cities1000 cache.
    if existing.exists() and not smaller.exists():
        try:
            with urllib.request.urlopen('https://download.geonames.org/export/dump/cities500.zip', timeout=20) as response:
                raw = response.read(30*1024*1024)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if 'cities500.txt' not in archive.namelist():
                    raise ValueError('Unexpected GeoNames archive')
            temporary = smaller.with_suffix('.next')
            temporary.write_bytes(raw)
            temporary.replace(smaller)
        except (OSError, ValueError, zipfile.BadZipFile):
            pass
    cities = load_cities(candidates, smaller if smaller.exists() else existing)
    result = Resolver(cities, regions, borders, countries, overrides).resolve(races)
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    main()
