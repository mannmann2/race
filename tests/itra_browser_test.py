import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import itra_browser as b
from itra import FeedError
from unittest.mock import patch


def fixture():
    card='''<div class="events-list"><h4>Alpine Weekend</h4><div class="date">30 - 31 December 2027</div>
    <div class="location">Chamonix, FRA<img src="/images/CountryFlags/fr.svg"></div>
    <a href="/Races/RaceDetails/Alpine/2027/100"><div class="count">50 k</div><div class="distance">+2500 m</div><img src="/images/zero.svg"></a>
    <a href="/Races/RaceDetails/Alpine/2027/101"><div class="count">100 k</div><div class="distance">+5000 m</div><img src="/images/five.svg"></a></div>
    <img src="/Files/Events/photo.png">'''
    return {'calendar':[[card]],'markers':[[45.92,6.87,101]],'metadata':{'calendarDisplayedRaces':2}}

class BrowserImportTests(unittest.TestCase):
    @patch('itra_browser.geocode')
    def test_bulk_ratings_and_map_join_any_course(self,_):
        races=b.normalize_capture(fixture())
        self.assertEqual(len(races),2)
        self.assertEqual(races[0]['extensions']['itra']['endurancePoints'],0)
        self.assertEqual(races[1]['extensions']['itra']['endurancePoints'],5)
        self.assertIsNone(races[0]['extensions']['itra']['mountainLevel'])
        for race in races:
            self.assertEqual(race['date'],'2027-12-30')
            self.assertEqual(race['dateEnd'],'2027-12-31')
            self.assertEqual(race['longitude'],6.87)
            self.assertEqual(race['locationPrecision'],'event')
            self.assertEqual(race['image'],'https://itra.run/Files/Events/photo.png')

    @patch('itra_browser.geocode')
    def test_invalid_coordinates_and_conflicting_points_not_invented(self,_):
        data=fixture();data['markers']=[[45920000,6870000,101],[0,0,100]]
        self.assertTrue(all(r['longitude'] is None for r in b.normalize_capture(data)))
        data['markers']=[[45,6,100],[48,2,101]]
        self.assertTrue(all(r['longitude'] is None for r in b.normalize_capture(data)))

    def test_incomplete_calendar_rejected(self):
        data=fixture();data['metadata']['calendarDisplayedRaces']=3
        with self.assertRaisesRegex(FeedError,'Incomplete'):b.normalize_capture(data)

    def test_rolling_window_retains_past_removes_cancelled_and_adds_new_year(self):
        old=[{'id':'old','date':'2027-12-31'}, {'id':'cancelled','date':'2028-06-01'}]
        current=[{'id':'new-edition','date':'2028-12-31'}]
        result=b.retain_history(current,old,'2028-01-01')
        self.assertEqual({r['id'] for r in result},{'old','new-edition'})
        self.assertEqual(b.retain_history(current,result,'2028-01-02'),result)
        self.assertEqual(b.event_dates('29 February 2028'),('2028-02-29','2028-02-29'))
        with self.assertRaises(FeedError):b.event_dates('29 February 2027')

    @patch('itra_browser.geocode')
    def test_weekly_bulk_reuse_boundary_and_failure_retention(self,_):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);args=SimpleNamespace(cache=cache,capture=None,bulk_max_age_days=7)
            initial=fixture();initial['metadata']['capturedAt']='2027-12-28T03:36:00+00:00'
            browser=Mock();browser.capture.return_value=initial
            rows,meta=b.load_bulk(args,browser,dt.datetime(2027,12,28,4,tzinfo=dt.timezone.utc))
            browser.capture.assert_called_once()
            browser.reset_mock()
            again,again_meta=b.load_bulk(args,browser,dt.datetime(2028,1,3,4,tzinfo=dt.timezone.utc))
            browser.capture.assert_not_called();self.assertEqual(again,rows);self.assertEqual(again_meta,meta)
            # Calendar-day expiry avoids timer jitter turning seven days into eight.
            next_capture=fixture();next_capture['metadata']['capturedAt']='2028-01-04T03:30:00+00:00'
            browser.capture.return_value=next_capture
            _,new_meta=b.load_bulk(args,browser,dt.datetime(2028,1,4,3,30,tzinfo=dt.timezone.utc))
            browser.capture.assert_called_once();self.assertNotEqual(meta['capturedAt'],new_meta['capturedAt'])
            before=(cache/'bulk-listings.json').read_bytes()
            broken=fixture();broken['metadata']['calendarDisplayedRaces']=100
            browser.capture.return_value=broken
            with self.assertRaises(FeedError):b.load_bulk(args,browser,dt.datetime(2028,1,11,4,tzinfo=dt.timezone.utc))
            self.assertEqual((cache/'bulk-listings.json').read_bytes(),before)

    @patch('itra_browser.geocode')
    def test_incomplete_capture_cannot_replace_last_good_snapshot(self,_):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=root/'cache';cache.mkdir();(root/'data').mkdir()
            target=cache/'races.json';target.write_text('{"schemaVersion":1,"races":[{"id":"keep"}]}')
            before=target.read_bytes()
            capture=fixture();capture['metadata']['calendarDisplayedRaces']=99
            source=root/'capture.json';source.write_text(json.dumps(capture))
            args=SimpleNamespace(capture=source,cache=cache,detail_limit=0)
            with patch('itra_browser.ROOT',root):
                with self.assertRaises(FeedError):b.import_races(args)
            self.assertEqual(target.read_bytes(),before)
            self.assertFalse((root/'data/itra-snapshot.json').exists())

    @patch('itra_browser.geocode')
    def test_current_calendar_points_override_detail_cache_and_dates_become_exact(self,_):
        race=b.normalize_capture(fixture())[0]
        detail=copy.deepcopy(race)
        detail.update(date='2027-12-31',name='Alpine 50K',detailsFetchedAt='2027-12-01T00:00:00+00:00')
        detail['extensions']['itra']={'endurancePoints':3,'mountainLevel':5,'finisherLevel':300}
        merged=b.apply_details(race,detail)
        self.assertEqual(merged['dateEnd'],'2027-12-31')
        self.assertEqual(merged['datePrecision'],'race')
        self.assertEqual(merged['extensions']['itra']['endurancePoints'],0)
        self.assertEqual(merged['extensions']['itra']['mountainLevel'],5)
        changed=copy.deepcopy(race);changed['date']='2027-12-29'
        self.assertNotEqual(b.fingerprint(race),b.fingerprint(changed))

if __name__=='__main__':unittest.main()
