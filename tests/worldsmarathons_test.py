import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import worldsmarathons as wm


def event(**changes):
    return dict(id='fixture-marathon', title='Fixture Marathon', countryCode='FR', city='Paris',
                dateNextRaceLocal='2027-04-11T00:00:00', dateNextRace='2027-04-10T22:00:00',
                firstRaceDate='2027-04-11T00:00:00', lastRaceDate='2027-04-11T00:00:00',
                raceDistances=[{'distance':42195, 'hidden':False, 'measureType':0}],
                geoStartPoint={'coordinates':[2.35,48.86]}, surface='Road',
                image='https://wmimg.azureedge.net/public/img/marathons/default.jpg', **changes)


def capture():
    return {'capturedAt':'2026-11-09T12:00:00+00:00', 'years':[
        {'year':2026, 'count':0, 'pages':1, 'results':[]},
        {'year':2027, 'count':1, 'pages':1, 'results':[event()]},
        {'year':2028, 'count':0, 'pages':1, 'results':[]}]}


class WorldMarathonsTests(unittest.TestCase):
    def test_local_dates_event_ranges_and_actual_distance(self):
        e=event();e['raceDistances']*=2
        race,reason=wm.normalize(e,2027,'2026-11-09T00:00:00Z')
        self.assertIsNone(reason);self.assertEqual(race['date'],'2027-04-11')
        self.assertEqual(race['distanceKm'],42.195);self.assertEqual(race['datePrecision'],'event-day')
        self.assertIsNone(race['image']);self.assertIsNone(race['elevationGainM'])
        self.assertEqual(race['sourceUrl'],'https://worldsmarathons.com/marathon/fixture-marathon')
        e['firstRaceDate']='2027-04-10T00:00:00'
        race,_=wm.normalize(e,2027,'2026-11-09T00:00:00Z')
        self.assertEqual((race['date'],race['dateEnd'],race['datePrecision']),('2027-04-10','2027-04-11','event'))

    def test_unknown_dates_distances_and_invalid_coordinates_not_invented(self):
        for changes in [{'id':'shanghai-sports-expo'},{'dateNextRaceLocal':None},{'dateNextRaceLocal':'2027-02-29T00:00:00'},
                        {'raceDistances':[]},{'raceDistances':[{'distance':42195,'measureType':1}]},
                        {'raceDistances':[{'distance':42195,'measureType':0,'hidden':True}]}]:
            self.assertIsNone(wm.normalize({**event(),**changes},2027,'2026-11-09')[0])
        self.assertEqual(wm.local_date('2028-02-29T00:00:00'),'2028-02-29')
        for coords in [[0,0],[181,45],[2,91],['2',48],[True,48]]:
            self.assertIsNone(wm.point_of({'geoStartPoint':{'coordinates':coords}}))

    def test_pagination_validates_total_unique_ids_and_changed_counts(self):
        class Client:
            def fetch(self,year,page):
                return {'count':2,'results':[{**event(),'id':str(page)}]} if year==2027 else {'count':0,'results':[]}
        result=wm.capture_calendar(Client(),dt.date(2026,11,9),pause=0)
        self.assertEqual(result['years'][1]['pages'],2)
        self.assertEqual(len(result['years'][1]['results']),2)
        self.assertNotIn('dateNextRace',result['years'][1]['results'][0])
        for response in [{'count':2,'results':[]},{'count':2,'results':[event(),event()]},{'count':0,'results':[event()]}]:
            with self.subTest(response=response):
                with patch.object(Client,'fetch',return_value=response):
                    with self.assertRaises(wm.FeedError):wm.capture_calendar(Client(),dt.date(2026,11,9),pause=0)
        with patch.object(Client,'fetch',side_effect=[{'count':2,'results':[event()]},{'count':3,'results':[]} ]):
            with self.assertRaisesRegex(wm.FeedError,'changed'):wm.capture_calendar(Client(),dt.date(2026,11,9),pause=0)

    @patch('worldsmarathons.geocode')
    def test_verified_capture_and_three_year_rollover(self,_):
        races,coverage=wm.normalize_capture(capture())
        self.assertEqual(len(races),1);self.assertEqual(coverage['eventsDownloaded'],1)
        self.assertEqual(wm.years_for(dt.date(2027,12,31)),[2027,2028,2029])
        self.assertEqual(wm.years_for(dt.date(2028,1,1)),[2028,2029,2030])
        broken=capture();broken['years'][1]['count']=3
        with self.assertRaises(wm.FeedError):wm.normalize_capture(broken)

    @patch('worldsmarathons.geocode')
    def test_weekly_cache_expiry_failure_preservation_history_and_removal(self,_):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'capture.json';source.write_text(json.dumps(capture()))
            args=SimpleNamespace(cache=root/'cache',snapshot=root/'snapshot.json',capture=source,max_age_days=7)
            now=dt.datetime(2026,11,9,13,tzinfo=dt.timezone.utc)
            initial=wm.import_races(args,now=now)
            before=args.snapshot.read_bytes();args.capture=None
            with patch('worldsmarathons.capture_calendar') as fetch:
                self.assertEqual(wm.import_races(args,now=now+dt.timedelta(days=6)),initial);fetch.assert_not_called()
            with patch('worldsmarathons.capture_calendar',side_effect=wm.FeedError('blocked')):
                with self.assertRaises(wm.FeedError):wm.import_races(args,now=now+dt.timedelta(days=7))
                self.assertEqual(args.snapshot.read_bytes(),before)
            old=copy.deepcopy(initial);old['races'] += [{**initial['races'][0],'id':'past','date':'2025-01-01','dateEnd':'2025-01-01'},
                                                       {**initial['races'][0],'id':'removed','date':'2027-12-01','dateEnd':'2027-12-01'}]
            wm.atomic_json(args.cache/'races.json',old)
            args.capture=source
            updated=wm.import_races(args,now=now)
            self.assertIn('past',{r['id'] for r in updated['races']});self.assertNotIn('removed',{r['id'] for r in updated['races']})
            broken=capture();broken['years'][1]['count']=100;source.write_text(json.dumps(broken))
            before=args.snapshot.read_bytes()
            with self.assertRaises(wm.FeedError):wm.import_races(args,now=now)
            self.assertEqual(args.snapshot.read_bytes(),before)
            # A fresh December snapshot cannot suppress acquisition of a new year.
            args.capture=None;old['fetchedAt']='2026-12-31T12:00:00Z';wm.atomic_json(args.cache/'races.json',old)
            with patch('worldsmarathons.capture_calendar',side_effect=wm.FeedError('new year requested')) as fetch:
                with self.assertRaises(wm.FeedError):wm.import_races(args,now=dt.datetime(2027,1,1,tzinfo=dt.timezone.utc))
                fetch.assert_called_once()


if __name__=='__main__':unittest.main()
