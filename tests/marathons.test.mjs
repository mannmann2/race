import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { combineRace, expandDataset, matches, groupLocations } from '../web/core.mjs';
import { matchMarathons } from '../scripts/match-marathons.mjs';

const base={id:'utmb:1',source:'utmb',sourceId:'1',name:'Fixture Alpine Marathon',eventName:'Fixture Alpine Marathon',date:'2027-05-01',datePrecision:'race',countryCode:'FR',place:'Paris',longitude:2.35,latitude:48.86,distanceKm:42.2,elevationGainM:500,sourceUrl:'https://utmb.world/race/1',extensions:{utmb:{category:'50k'}}};
const wm={...base,id:'worldsmarathons:2027:fixture:marathon',source:'worldsmarathons',sourceId:'2027:fixture:marathon',sourceUrl:'https://worldsmarathons.com/marathon/fixture',datePrecision:'event-day',distanceKm:42.195,elevationGainM:null,extensions:{worldsmarathons:{surface:'road'}}};

test('marathon listing matches only a unique edition and course; rejects ambiguous and different variants',()=>{
 assert.equal(matchMarathons([base],[wm]).report.merged,1);
 for(const change of [{date:'2028-05-01'},{distanceKm:50},{name:'Fixture Alpine Marathon Relay'},{name:'Fixture Alpine Marathon Night'},{countryCode:'GB'},{eventName:'Different Marathon',name:'Different Marathon'},{date:'2027-05-08'}])assert.equal(matchMarathons([{...base,...change}],[wm]).report.merged,0,JSON.stringify(change));
 assert.equal(matchMarathons([base,{...base,id:'utmb:2',name:'Other course'}],[wm]).report.merged,0);
 assert.equal(matchMarathons([base],[wm,{...wm,id:'worldsmarathons:2027:duplicate:marathon'}]).report.merged,0);
});

test('third source preserves previous conflicts, all links and source-specific surface filters',()=>{
 const itra={...base,source:'itra',sourceId:'2',id:'itra:2',distanceKm:42.1,sourceUrl:'https://itra.run/race/2',extensions:{itra:{endurancePoints:2}}};
 const race=combineRace(combineRace(base,itra),wm);
 assert.deepEqual(race.sources.map(s=>s.provider),['utmb','itra','worldsmarathons']);
 assert.equal(race.conflicts.length,2);assert.equal(race.conflicts[0].itra,42.1);assert.equal(race.conflicts[1].worldsmarathons,42.195);
 assert.equal(race.extensions.itra.endurancePoints,2);
 assert.ok(matches(race,{source:'worldsmarathons',worldsmarathonsSurface:'road'},'2027-01-01'));
 assert.ok(matches(race,{source:'both'},'2027-01-01'));
 assert.equal(matches(race,{worldsmarathonsSurface:'trail'},'2027-01-01'),false);
 assert.equal(matches(base,{worldsmarathonsSurface:'unknown'},'2027-01-01'),false);
 assert.ok(matches({...wm,extensions:{worldsmarathons:{surface:null}}},{worldsmarathonsSurface:'unknown'},'2027-01-01'));
});

test('live marathon snapshot has validated coverage, correct provenance and one published listing per source id',()=>{
 const snapshot=JSON.parse(readFileSync(new URL('../data/worldsmarathons-snapshot.json',import.meta.url)));
 const data=JSON.parse(gunzipSync(readFileSync(new URL('../web/data/catalog.json.gz',import.meta.url))));
 const races=expandDataset(data),marathons=races.filter(r=>matches(r,{source:'worldsmarathons'},'2000-01-01'));
 assert.equal(snapshot.coverage.eventsDownloaded,snapshot.coverage.races+Object.values(snapshot.coverage.skipped).reduce((a,b)=>a+b,0));
 assert.equal(snapshot.races.length,snapshot.coverage.races+snapshot.coverage.archived);
 assert.equal(marathons.length,snapshot.races.length);
 assert.equal(new Set(marathons.flatMap(r=>r.sources.filter(s=>s.provider==='worldsmarathons').map(s=>s.id))).size,snapshot.races.length);
 assert.equal(groupLocations(marathons).reduce((n,p)=>n+p.count,0),marathons.filter(r=>r.longitude!=null).length);
 for(const race of snapshot.races){
  assert.ok(race.distanceKm>=42&&race.distanceKm<=42.3);assert.ok(race.date<=race.dateEnd);
  assert.match(race.sourceUrl,/^https:\/\/worldsmarathons.com\/marathon\//);
  assert.equal(race.sources[0].fetchedAt,snapshot.fetchedAt);
  assert.ok(!race.image||!race.image.includes('/default.'));
  assert.ok(!race.image||race.imageSource===race.sourceUrl);
 }
 assert.ok(marathons.some(r=>r.sources.length>1));
});

test('reviewed real overlaps include trail measurements, sponsor titles, festival dates and three-source records',()=>{
 const fixtures=JSON.parse(readFileSync(new URL('./fixtures/marathon-overlaps.json',import.meta.url)));
 for(const {existing,incoming,expected} of fixtures){
  const result=matchMarathons(existing,[incoming]);
  assert.equal(result.entries[0].matchId,expected,incoming.eventName);
 }
});

test('matching requires independent corroboration and keeps uncertain course variants separate',()=>{
 const trail={...base,name:'Marathon',distanceKm:44.3};
 assert.equal(matchMarathons([trail],[wm]).report.merged,1);
 assert.equal(matchMarathons([{...trail,name:'40km'}],[wm]).report.merged,0);
 assert.equal(matchMarathons([{...base,date:'2027-05-03'}],[{...wm,datePrecision:'event',dateEnd:'2027-05-04'}]).report.merged,1);
 assert.equal(matchMarathons([{...base,date:'2027-04-30',dateEnd:'2027-05-03',datePrecision:'event'}],[wm]).report.merged,1);
 const unmapped={...base,longitude:null,latitude:null,place:'Elsewhere'};
 for(const website of ['https://instagram.com/organiser','https://runsignup.com/races'])assert.equal(matchMarathons([{...unmapped,website}],[{...wm,website}]).report.merged,0);
 assert.equal(matchMarathons([{...unmapped,website:'https://fixture-race.example'}],[{...wm,website:'https://fixture-race.example'}]).report.merged,1);
 for(const name of ['Half Marathon','1/2 Marathon','Marathon Relay','Marathon Stage 1','Night Marathon'])assert.equal(matchMarathons([{...base,name}],[wm]).report.merged,0,name);
 // Weaker same-event alternatives block a match in either direction.
 assert.equal(matchMarathons([base],[wm,{...wm,id:'worldsmarathons:other',place:'Elsewhere',longitude:null,latitude:null}]).report.merged,0);
 assert.equal(matchMarathons([base,{...unmapped,id:'utmb:other'}],[wm]).report.merged,0);
});

test('published three-provider overlaps retain every link and ITRA ratings once each',()=>{
 const data=JSON.parse(gunzipSync(readFileSync(new URL('../web/data/catalog.json.gz',import.meta.url))));
 const races=expandDataset(data);
 for(const id of ['utmb:141000','utmb:159954','utmb:160670','utmb:158028']){
  const race=races.find(r=>r.id===id);
  assert.deepEqual(race.sources.map(s=>s.provider),['utmb','itra','worldsmarathons'],id);
  assert.ok(race.sources.every(s=>s.url.startsWith('https://')));
  assert.ok(race.extensions.itra.endurancePoints!=null);
  for(const source of race.sources)assert.equal(races.filter(r=>r.sources.some(s=>s.provider===source.provider&&s.id===source.id)).length,1);
 }
});
