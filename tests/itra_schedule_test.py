"""Persisted scheduling, request limits, cache expiry and restart recovery; no live requests."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import itra_browser as b
import itra_schedule as s
from itra_browser_test import fixture

NOW=dt.datetime(2027,12,1,12,tzinfo=dt.timezone.utc)

class SchedulingTests(unittest.TestCase):
    def test_budget_survives_restarts_and_reserves_before_a_request(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder)
            self.assertTrue(s.RequestBudget(cache).reserve(NOW))
            restarted=s.RequestBudget(cache)
            self.assertFalse(restarted.reserve(NOW+dt.timedelta(minutes=19)))
            self.assertTrue(restarted.reserve(NOW+dt.timedelta(minutes=20)))
            self.assertEqual(s.moment(restarted.state['lastAttemptAt']),NOW+dt.timedelta(minutes=20))

    def test_access_backoff_doubles_honours_retry_after_and_caps_at_two_weeks(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);now=NOW
            for hours in [48,96,192,336,336]:
                budget=s.RequestBudget(cache);budget.fail('HTTP 403',now,blocked=True)
                self.assertEqual(budget.deferred_until(now),now+dt.timedelta(hours=hours))
                now+=dt.timedelta(hours=hours,seconds=1)
            budget.success(now);budget.fail('timeout',now)
            self.assertEqual(budget.deferred_until(now),now+dt.timedelta(hours=6))
            budget.success(now);budget.fail('HTTP 429',now,blocked=True,retry=str(21*86400))
            self.assertEqual(budget.deferred_until(now),now+dt.timedelta(days=21))
            http_date=(now+dt.timedelta(days=25)).strftime('%a, %d %b %Y %H:%M:%S GMT')
            self.assertEqual(s.retry_after(http_date,now),now+dt.timedelta(days=25))
            self.assertIsNone(s.retry_after('bad',now))

    def test_known_existing_block_is_imported_without_another_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);s.write_changed(cache/'status.json',{'attemptedAt':NOW.isoformat(),'detailRefreshError':'HTTP 403'})
            first=s.RequestBudget(cache)
            self.assertEqual(first.deferred_until(NOW),NOW+dt.timedelta(hours=48))
            self.assertEqual(s.RequestBudget(cache).state,first.state)

    @patch('itra_browser.geocode')
    def test_cache_lasts_sixty_days_and_repeat_refreshes_prioritise_race_date(self,_):
        races=b.normalize_capture(fixture());early=copy.deepcopy(races[0]);late=copy.deepcopy(races[1]);early.update(date='2027-12-15',dateEnd='2027-12-15');late.update(date='2027-12-20',dateEnd='2027-12-20')
        def saved(race,days):return {'fingerprint':b.fingerprint(race),'detailsFetchedAt':(NOW-dt.timedelta(days=days)).isoformat()}
        details={early['sourceId']:saved(early,59),late['sourceId']:saved(late,100)}
        queue=lambda rs,ds,fs={}:s.detail_queue(rs,ds,fs,NOW.date().isoformat(),NOW,b.fingerprint)
        self.assertEqual(queue([early,late],details),[late])
        details[early['sourceId']]=saved(early,60)
        self.assertEqual(queue([late,early],details),[early,late])
        fresh=copy.deepcopy(late);fresh.update(id='new',sourceId='2027:999')
        self.assertEqual(queue([late,early,fresh],details),[fresh,early,late])
        changed=copy.deepcopy(early);changed['distanceKm']+=1
        details[early['sourceId']]=saved(early,1)
        self.assertEqual(queue([late,changed],details),[changed,late])
        past=copy.deepcopy(early);past.update(date='2027-11-30',dateEnd='2027-11-30')
        self.assertEqual(queue([past],{}),[])
        failures={late['sourceId']:{'fingerprint':b.fingerprint(late),'attemptedAt':(NOW-dt.timedelta(days=59)).isoformat()}}
        self.assertEqual(queue([late],{},failures),[])
        failures[late['sourceId']]['attemptedAt']=(NOW-dt.timedelta(days=60)).isoformat()
        self.assertEqual(queue([late],{},failures),[late])

    def setup_import(self,root):
        cache=root/'cache';cache.mkdir();capture=fixture();capture['metadata']['capturedAt']=NOW.isoformat()
        with patch('itra_browser.geocode'):races=b.normalize_capture(capture)
        s.write_changed(cache/'bulk-listings.json',{'schemaVersion':1,'metadata':capture['metadata'],'races':races})
        return cache,races,SimpleNamespace(cache=cache,capture=None,details_only=True,detail_limit=400)

    def test_incremental_worker_never_bursts_and_does_not_rebuild_or_refetch_when_idle(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache,races,args=self.setup_import(root)
            browser=Mock();browser.detail.side_effect=lambda r:copy.deepcopy(r)
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW):
                first=b.import_races(args,browser)
                self.assertEqual(browser.detail.call_count,1)
                before={name:(cache/name).stat().st_mtime_ns for name in ['races.json','status.json','course-details.json']}
                second=b.import_races(args,browser)
                self.assertEqual(browser.detail.call_count,1);self.assertEqual(first,second)
                self.assertEqual(before,{name:(cache/name).stat().st_mtime_ns for name in before})
            browser.capture.assert_not_called()
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW+dt.timedelta(minutes=21)):
                b.import_races(args,browser)
            self.assertEqual(browser.detail.call_count,2)
            # Both course pages are cached: future timer ticks do not access ITRA.
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW+dt.timedelta(hours=1)):
                b.import_races(args,browser)
            self.assertEqual(browser.detail.call_count,2)

    def test_block_stops_requests_and_restart_preserves_cache_and_calendar_health(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache,races,args=self.setup_import(root)
            details={races[0]['sourceId']:{**races[0],'fingerprint':b.fingerprint(races[0]),'detailsFetchedAt':(NOW-dt.timedelta(days=1)).isoformat()}}
            s.write_changed(cache/'course-details.json',details)
            browser=Mock();browser.detail.side_effect=b.AccessLimited('HTTP 429','259200')
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW):
                first=b.import_races(args,browser)
                self.assertEqual(browser.detail.call_count,1)
                self.assertEqual(json.loads((cache/'status.json').read_text())['state'],'available')
                self.assertEqual(first['coverage']['details'],1)
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW+dt.timedelta(days=1)):
                second=b.import_races(args,browser)
            self.assertEqual(browser.detail.call_count,1);browser.capture.assert_not_called()
            self.assertEqual(first['races'],second['races'])
            self.assertEqual(s.RequestBudget(cache).deferred_until(NOW),NOW+dt.timedelta(days=3))
            self.assertEqual(json.loads((cache/'course-details.json').read_text()),details)

    def test_lazy_browser_is_never_started_when_there_is_no_network_work(self):
        with patch('itra_browser.Browser') as browser:
            with b.LazyBrowser():pass
            browser.assert_not_called()

    def test_blocked_http_responses_carry_retry_after_without_retrying_the_page(self):
        browser=b.Browser();browser.page=Mock();browser.page.url=b.BASE+'/'
        for code,text in [(429,'Too many requests'),(403,'Forbidden'),(202,'challenge'),(200,'captcha-container')]:
            browser.page.evaluate.return_value={'status':code,'text':text,'url':b.BASE+'/Races/RaceDetails/A/2027/1','retryAfter':'259200'}
            with self.assertRaises(b.AccessLimited) as raised:browser.detail({'sourceUrl':b.BASE+'/Races/RaceDetails/A/2027/1'})
            self.assertEqual(raised.exception.retry_after,'259200')
        self.assertEqual(browser.page.evaluate.call_count,4)

    def test_detail_worker_cannot_clear_a_failed_calendar_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache,races,args=self.setup_import(root)
            s.write_changed(cache/'races.json',{'fetchedAt':NOW.isoformat(),'races':races})
            s.write_changed(cache/'status.json',{'state':'unavailable','attemptedAt':NOW.isoformat()})
            s.RequestBudget(cache).fail('HTTP 403',NOW,blocked=True,scope='calendar')
            browser=Mock()
            with patch('itra_browser.ROOT',root),patch('itra_browser.now_utc',return_value=NOW):b.import_races(args,browser)
            self.assertEqual(s.load_json(cache/'status.json',{})['state'],'unavailable')
            browser.detail.assert_not_called();browser.capture.assert_not_called()

    def test_expired_bulk_is_not_requested_during_global_block_or_by_detail_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            cache,races,args=self.setup_import(Path(folder));browser=Mock()
            budget=s.RequestBudget(cache);budget.fail('HTTP 403',NOW,blocked=True)
            args.details_only=False;args.bulk_max_age_days=0
            rows,_=b.load_bulk(args,browser,NOW+dt.timedelta(days=1))
            self.assertEqual(rows,races);browser.capture.assert_not_called()
            args.details_only=True
            b.load_bulk(args,browser,NOW+dt.timedelta(days=10));browser.capture.assert_not_called()

if __name__=='__main__':unittest.main()
