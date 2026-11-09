import collections
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from resolve_locations import Borders, Resolver, norm


def box(w, s, e, n):
    return [[[ [w,s],[e,s],[e,n],[w,n],[w,s] ]]]


def city(id, name, cc, admin, lon, lat):
    return {'id': id, 'name': name, 'primary': {norm(name)}, 'country': cc, 'admin': admin,
            'point': [lon, lat], 'population': 1000}


def resolver():
    cities=collections.defaultdict(dict)
    for c in [city('wendover','Wendover','GB','ENG',-.74,51.76),
              city('wales','Bangor','GB','WLS',-4.13,53.23),city('ni','Bangor','GB','NIR',-5.67,54.66),
              city('illinois','Vienna','US','IL',-88.9,37.42),city('virginia','Vienna','US','VA',-77.27,38.9),
              city('orizaba','Orizaba','MX','30',-97.1,18.85)]:
        cities[(c['country'],norm(c['name']))][c['id']]=c
    borders=Borders({'GB':box(-8,50,2,59), 'US':box(-125,25,-65,50), 'ID':box(106,-10,120,-5), 'MX':box(-118,14,-86,32)})
    countries={'MX':{'name':{'common':'Mexico','official':'United Mexican States'},'altSpellings':['MX']},
               'US':{'name':{'common':'United States','official':'United States of America'}}}
    return Resolver(cities,{'US.IL':['Illinois'],'US.VA':['Virginia'],'MX.15':['México']},borders,countries)


def race(id='itra:2026:1', **fields):
    return {'id':id,'source':'itra','eventName':'Test event','date':'2026-11-14','place':'Wendover',
            'countryCode':'GB','longitude':-114.04,'latitude':40.74,'locationPrecision':'event',
            'locationId':id,'geonamesId':None,**fields}


class LocationsTests(unittest.TestCase):
    def test_wrong_country_namesake_uses_unique_locality_and_preserves_original(self):
        r=race();result=resolver().resolve([r])
        fixed=result['corrections'][r['id']]
        self.assertEqual((fixed['longitude'],fixed['latitude']),(-.74,51.76))
        self.assertEqual(fixed['locationPrecision'],'town')
        self.assertEqual(r['longitude'],-114.04)

    def test_missing_coordinate_sign_corrected_only_when_country_is_unambiguous(self):
        r=resolver()
        rows=[race(countryCode='US',longitude=87.2,latitude=41.3,place='Hebron'),
              race('itra:2026:2',countryCode='ID',longitude=112.55,latitude=7.84,place='Malang'),
              race('itra:2026:3',longitude=.19,latitude=51.3,place='Otford')]
        result=r.resolve(rows)['corrections']
        self.assertEqual(result[rows[0]['id']]['longitude'],-87.2)
        self.assertEqual(result[rows[1]['id']]['latitude'],-7.84)
        self.assertNotIn(rows[2]['id'],result) # East of Greenwich is valid in Britain.

    def test_state_hint_beats_population_and_country_name_is_not_a_region_hint(self):
        r=resolver()
        v=race(countryCode='US',place='Vienna, IL, United States of America',longitude=-77.27,latitude=38.9,
               locationPrecision='town',geonamesId='virginia')
        self.assertEqual(r.resolve([v])['corrections'][v['id']]['geonamesId'],'illinois')
        m=race(countryCode='MX',place='Orizaba, Mexico',longitude=-97.1,latitude=18.85,
               locationPrecision='town',geonamesId='orizaba')
        candidates,hint=r.candidates(m)
        self.assertFalse(hint);self.assertEqual(candidates[0]['id'],'orizaba')

    def test_ambiguous_bangor_is_resolved_only_with_independent_same_edition_point(self):
        r=resolver();town=race(source='utmb',place='Bangor',longitude=-5.67,latitude=54.66,
                              locationPrecision='town',geonamesId='ni')
        alone=r.resolve([town]);self.assertNotIn(town['id'],alone['corrections']);self.assertTrue(alone['review'])
        point=race('itra:2026:2',place='Bangor',longitude=-4.12,latitude=53.23)
        self.assertEqual(r.resolve([town,point])['corrections'][town['id']]['geonamesId'],'wales')
        point['date']='2027-11-14'
        self.assertNotIn(town['id'],r.resolve([town,point])['corrections'])

    def test_non_latin_event_names_do_not_share_location_evidence(self):
        r=resolver()
        town=race(source='utmb',eventName='山の大会',place='Bangor',longitude=-5.67,latitude=54.66,
                  locationPrecision='town',geonamesId='ni')
        other=race('itra:2026:2',eventName='別の大会',place='Bangor',longitude=-4.12,latitude=53.23)
        self.assertNotIn(town['id'],r.resolve([town,other])['corrections'])

    def test_no_population_guess_after_country_mismatch(self):
        r=race(place='Bangor',longitude=-114.04,latitude=40.74)
        correction=resolver().resolve([r])['corrections'][r['id']]
        self.assertIsNone(correction['longitude']);self.assertEqual(correction['locationPrecision'],'unknown')

    def test_region_conflict_without_evidence_remains_a_review_item(self):
        r=race(countryCode='US',place='Smallville, IL, United States of America',longitude=-77.27,latitude=38.9,
               locationPrecision='town',geonamesId='virginia')
        report=resolver().resolve([r]);self.assertNotIn(r['id'],report['corrections'])
        self.assertEqual(report['review'][0]['reason'],'region-locality-unresolved')

    def test_island_and_border_buffer_does_not_reject_accurate_event_points(self):
        b=Borders({'IS':box(-20,60,-19.99,60.01)})
        self.assertTrue(b.plausible('IS',(-19.98,60.005)))
        self.assertFalse(b.plausible('IS',(-10,60)))

    def test_reviewed_event_rule_does_not_move_other_bangor_events(self):
        r=resolver();r.overrides=[{'match':{'countryCode':'GB','eventNames':['Welsh trail'],'place':['Bangor']},
                                 'location':{'longitude':-4.13,'latitude':53.23,'geonamesId':'wales'},'evidence':['organiser']}]
        welsh=race(eventName='Welsh trail',place='Bangor',longitude=-5.67,latitude=54.66)
        northern=race('itra:2026:2',eventName='Northern trail',place='Bangor',longitude=-5.67,latitude=54.66)
        result=r.resolve([welsh,northern])['corrections']
        self.assertEqual(result[welsh['id']]['longitude'],-4.13)
        self.assertNotIn(northern['id'],result)


if __name__=='__main__':unittest.main()
