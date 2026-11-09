"""Synthetic format fixtures: these verify parsing, not live ITRA availability."""
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import itra

URL = 'https://itra.run/Races/RaceDetails/Fixture.Alpine.50K/2027/999001'


def calendar(distance='50 k', date='16 July 2027'):
    card = f'''<div class="events-list"><div class="event_name"><a href="{URL}"><h4>Fixture Alpine</h4></a></div>
    <div class="date">{date}</div><div class="location">Chamonix, FRA<img src="/images/CountryFlags/fr.svg"></div>
    <div class="races-boxes"><div class="boxes"><a href="{URL}"><div class="count">{distance}</div><div class="distance">+2500 m</div></a></div></div></div>'''
    return '<script>var raceSearchJsonSidePopupNew = ' + json.dumps([[card]]) + ';</script>'


def detail(points='zero', mountain='0', date='2027/07/16'):
    return f'''<h1>Fixture Alpine</h1><h3>Fixture Alpine 50K</h3>
    <div>Race Date: <span>{date}</span></div><div>Distance: <span>50.2</span></div>
    <div>Elevation Gain: <span>+2,500</span></div>
    <div>ITRA Points <img src="/images/itra_numbers/icons/{points}.svg"></div>
    <div>Mountain Level: <span>{mountain}</span></div><div>Finisher Level: <span>320</span></div>
    <meta property="og:image" content="https://itra.run/Files/Events/fixture.png">
    <a href="https://fixture.example">Official website</a>
    <p>Last year the date was 2026/07/15 and the course was 99 km.</p>'''


class ItraTest(unittest.TestCase):
    def test_batch_courses_and_no_event_duplicate(self):
        races, events = itra.parse_calendar(calendar())
        self.assertEqual(events, 1)
        self.assertEqual(len(races), 1)
        self.assertEqual(races[0]['sourceId'], '2027:999001')
        self.assertEqual(races[0]['countryCode'], 'FR')
        self.assertEqual(races[0]['place'], 'Chamonix')
        self.assertEqual(races[0]['datePrecision'], 'event')
        self.assertEqual(races[0]['distanceKm'], 50)
        self.assertIsNone(races[0]['extensions']['itra']['endurancePoints'])

    def test_short_course_urls_use_the_observed_edition_year(self):
        self.assertEqual(itra.race_identity('https://itra.run/Races/RaceDetails/115285', '2026'), '2026:115285')
        with self.assertRaises(itra.FeedError):
            itra.race_identity('https://itra.run/Races/RaceDetails/115285')
        races, _ = itra.parse_calendar(calendar().replace(URL, 'https://itra.run/Races/RaceDetails/999001'))
        self.assertEqual(races[0]['sourceId'], '2027:999001')

    @unittest.skipUnless((itra.ROOT / 'data/itra-indexed.json').exists(), 'Private snapshot not present')
    def test_real_indexed_import_preserves_ratings_evidence_and_freshness(self):
        document = json.loads((itra.ROOT / 'data/itra-indexed.json').read_text())
        snapshot = itra.indexed_snapshot(document)
        self.assertEqual(len(snapshot['races']), 35)
        self.assertIsNone(snapshot['fetchedAt'])
        self.assertEqual(snapshot['acquisition'], 'public-index')
        records = {r['sourceId']: r for r in snapshot['races']}
        budai = records['2026:115285']
        self.assertEqual(budai['extensions']['itra']['endurancePoints'], 0)
        self.assertEqual(budai['extensions']['itra']['mountainLevel'], 4)
        self.assertEqual(budai['distanceKm'], 13.8)
        self.assertEqual(budai['date'], '2026-12-06')
        self.assertIsNone(budai['sources'][0]['fetchedAt'])
        self.assertTrue(budai['sources'][0]['retrievedAt'])
        self.assertEqual(records['2026:111751']['extensions']['itra']['endurancePoints'], 2)
        self.assertIsNone(records['2026:116065']['extensions']['itra']['endurancePoints'])
        self.assertEqual(snapshot['coverage']['rated'], 7)
        self.assertEqual(snapshot['coverage']['mountainRated'], 31)

    @unittest.skipUnless((itra.ROOT / 'data/itra-indexed.json').exists(), 'Private snapshot not present')
    def test_indexed_import_rejects_unverified_ratings_and_edition_mismatches(self):
        document = json.loads((itra.ROOT / 'data/itra-indexed.json').read_text())
        document['records'] = [copy.deepcopy(document['records'][0])]
        document['records'][0]['endurancePoints'] = 6
        with self.assertRaisesRegex(itra.FeedError, 'evidence'):
            itra.indexed_snapshot(document)
        document['records'][0]['endurancePoints'] = None
        document['records'][0]['date'] = '2027-11-26'
        with self.assertRaisesRegex(itra.FeedError, 'edition'):
            itra.indexed_snapshot(document)

    def test_ratings_zero_and_detail_precedence(self):
        listing = itra.parse_calendar(calendar())[0][0]
        race = itra.parse_detail(detail(), listing)
        self.assertEqual(race['distanceKm'], 50.2)
        self.assertEqual(race['elevationGainM'], 2500)
        self.assertEqual(race['date'], '2027-07-16')
        self.assertEqual(race['datePrecision'], 'race')
        self.assertEqual(race['extensions']['itra'], {'endurancePoints': 0, 'mountainLevel': 0, 'finisherLevel': 320})
        self.assertEqual(race['imageSource'], URL)
        self.assertEqual(race['website'], 'https://fixture.example')
        self.assertIsNone(listing['extensions']['itra']['endurancePoints'])

    def test_missing_ratings_not_zero(self):
        listing = itra.parse_calendar(calendar())[0][0]
        race = itra.parse_detail(detail(points='missing', mountain='—'), listing)
        self.assertIsNone(race['extensions']['itra']['endurancePoints'])
        self.assertIsNone(race['extensions']['itra']['mountainLevel'])

    def test_invalid_measurements_and_different_edition_rejected(self):
        listing = itra.parse_calendar(calendar())[0][0]
        for content in [detail(mountain='13'), detail(mountain='-1'), detail(date='2026/07/16'), '<html>Access denied</html>']:
            with self.assertRaises(itra.FeedError):
                itra.parse_detail(content, listing)
        for content in ['', '<html>Challenge</html>', '<script>var raceSearchJsonSidePopupNew = [];</script>']:
            with self.assertRaises(itra.FeedError):
                itra.parse_calendar(content)

    def test_no_execution_of_embedded_javascript_or_untrusted_urls(self):
        with self.assertRaises(itra.FeedError):
            itra.parse_calendar('<script>var raceSearchJsonSidePopupNew = alert(1)</script>')
        for url in ['javascript:alert(1)', 'https://evil.example/Races/RaceDetails/Test/2027/1']:
            with self.assertRaises(itra.FeedError):
                itra.race_identity(url)
        self.assertIsNone(itra.safe_url('javascript:alert(1)'))

    def test_geocoding_does_not_match_empty_transliterated_names(self):
        race = itra.parse_calendar(calendar())[0][0]
        race.update(countryCode='CN', place='北京')
        itra.geocode([race])
        self.assertIsNone(race['longitude'])

    def test_capture_reads_only_successful_response_bodies(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'capture.har'
            entry = lambda url, body: {'request': {'url': url, 'headers': [{'name': 'Cookie', 'value': 'secret'}]}, 'response': {'status': 200, 'content': {'text': base64.b64encode(body.encode()).decode(), 'encoding': 'base64'}}}
            path.write_text(json.dumps({'log': {'entries': [entry(itra.CALENDAR, calendar()), entry(URL, detail()), entry('https://other.example', 'private')]}}))
            calendars, details = itra.read_capture(path)
            self.assertEqual(calendars, [calendar()])
            self.assertEqual(details, {URL: detail()})
            self.assertNotIn('secret', json.dumps([calendars, details]))

    def test_blocked_refresh_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            snapshot = path / 'races.json'
            snapshot.write_text('{"last":"good"}')
            with patch.object(sys, 'argv', ['itra.py', '--cache', temp]), patch.object(itra.Client, 'calendar', side_effect=itra.FeedError('HTTP 202 challenge')):
                self.assertEqual(itra.main(), 1)
            self.assertEqual(snapshot.read_text(), '{"last":"good"}')
            self.assertEqual(json.loads((path / 'status.json').read_text())['state'], 'unavailable')

    def test_offline_import_uses_same_pipeline_and_reports_partial_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            har = root / 'capture.har'
            (root / '.cache').mkdir()
            (root / '.cache/countries.json').write_text(json.dumps([{'cca2':'FR','name':{'common':'France'},'region':'Europe'}]))
            with zipfile.ZipFile(root / '.cache/cities1000.zip', 'w') as cities:
                cities.writestr('cities1000.txt', '\t'.join(['1','Chamonix','Chamonix','','45.923','6.87','P','PPL','FR','','','','','','8000'])+'\n')
            entries = [{'request': {'url': url}, 'response': {'status': 200, 'content': {'text': content}}} for url, content in [(itra.CALENDAR, calendar()), (URL, detail())]]
            har.write_text(json.dumps({'log': {'entries': entries}}))
            with patch.object(itra, 'ROOT', root), patch.object(sys, 'argv', ['itra.py', '--cache', str(root / 'cache'), '--har', str(har), '--offline']), patch.object(itra.Client, 'request', side_effect=AssertionError('network call')):
                self.assertEqual(itra.main(), 0)
            data = json.loads((root / 'cache/races.json').read_text())
            self.assertEqual(data['coverage']['races'], 1)
            self.assertEqual(data['coverage']['completeness'], 'unverified')
            self.assertEqual(data['races'][0]['sources'][0]['url'], URL)
            self.assertIsNotNone(data['races'][0]['longitude'])


if __name__ == '__main__':
    unittest.main()
