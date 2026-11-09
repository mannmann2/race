import test from 'node:test';
import assert from 'node:assert/strict';
import { matches, combineRace, expandDataset, isWorldSeries, groupLocations } from '../web/core.mjs';
import { matchSources } from '../scripts/match-sources.mjs';
import { compose } from '../scripts/compose-catalog.mjs';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gzipSync, gunzipSync } from 'node:zlib';

const utmb={id:'utmb:1',source:'utmb',sourceId:'1',sourceUrl:'https://utmb.world/race/1',name:'Fixture Alpine 50K',eventName:'Fixture Alpine',date:'2027-07-16',countryCode:'FR',country:'France',continent:'Europe',place:'Chamonix',longitude:6.87,latitude:45.92,locationId:1,distanceKm:50,elevationGainM:2500,website:'https://fixture.example',extensions:{utmb:{category:'50k',level:'serie'}}};
const itra={...utmb,id:'itra:2027:2',source:'itra',sourceId:'2027:2',sourceUrl:'https://itra.run/Races/RaceDetails/Fixture/2027/2',datePrecision:'race',distanceKm:50.2,extensions:{itra:{endurancePoints:3,mountainLevel:6,finisherLevel:320}}};
test('same edition/course combines once and preserves original source values and links',()=>{
 const result=matchSources([utmb],[itra]);assert.equal(result.report.merged,1);assert.equal(result.entries[0].matchId,utmb.id);
 const r=combineRace(utmb,itra);assert.equal(r.distanceKm,50);assert.equal(r.sources.length,2);assert.equal(r.sources[1].url,itra.sourceUrl);
 assert.equal(r.extensions.utmb.category,'50k');assert.equal(r.extensions.itra.endurancePoints,3);assert.equal(r.conflicts[0].itra,50.2);assert.ok(isWorldSeries(r));
});
test('different years, distances, course variants, and missing dates never auto-merge',()=>{
 for(const changes of [{date:'2028-07-16'},{distanceKm:100},{name:'Fixture Alpine 50K Relay'},{date:null},{datePrecision:'event'}])assert.equal(matchSources([utmb],[{...itra,...changes}]).report.merged,0,JSON.stringify(changes));
 const shifted=matchSources([utmb],[{...itra,date:'2027-07-17'}]);
 assert.equal(shifted.report.merged,1);assert.ok(combineRace(utmb,shifted.entries[0].race).conflicts.some(c=>c.field==='date'));
 assert.equal(matchSources([utmb],[{...itra,date:'2027-07-20'}]).report.merged,0);
});
test('ambiguous matches remain separate in both directions regardless of input order',()=>{
 assert.equal(matchSources([utmb,{...utmb,id:'utmb:2'}],[itra]).report.merged,0);
 for(const races of [[itra,{...itra,id:'itra:2027:3'}],[{...itra,id:'itra:2027:3'},itra]])assert.equal(matchSources([utmb],races).report.merged,0);
});
test('non-Latin names remain distinct, rather than collapsing to empty match keys',()=>{
 const a={...utmb,name:'青山越野',eventName:'青山越野',place:'北京'};
 const b={...itra,name:'北山越野',eventName:'北山越野',place:'北京'};
 assert.equal(matchSources([a],[b]).report.merged,0);
 assert.equal(matchSources([a],[{...b,name:a.name,eventName:a.eventName}]).report.merged,1);
 assert.equal(matchSources([{...a,name:'',eventName:''}],[{...b,name:'',eventName:''}]).report.merged,0);
});
test('persistent match/separate overrides and collision protection',()=>{
 const changed={...itra,date:'2027-07-17'};
 assert.equal(matchSources([utmb],[changed],{match:{[itra.id]:utmb.id}}).report.merged,1);
 assert.equal(matchSources([utmb],[itra],{separate:[[itra.id,utmb.id]]}).report.merged,0);
 assert.throws(()=>matchSources([utmb],[itra,itra]),/Duplicate/);
 assert.throws(()=>matchSources([utmb],[itra],{match:{[itra.id]:utmb.id},separate:[[itra.id,utmb.id]]}),/Conflicting/);
});
test('source and ITRA rating filters combine; missing is not zero and bounds are inclusive',()=>{
 const race=combineRace(utmb,itra),zero={...itra,extensions:{itra:{endurancePoints:0,mountainLevel:0}}};
 assert.ok(matches(race,{source:'both',endurancePoints:['3'],mountainMin:'6',mountainMax:'6'},'2027-01-01'));
 assert.equal(matches(utmb,{source:'both'},'2027-01-01'),false);
 assert.equal(matches(utmb,{endurancePoints:['0']},'2027-01-01'),false);
 assert.equal(matches(utmb,{mountainMax:'12'},'2027-01-01'),false);
 assert.ok(matches(zero,{endurancePoints:['0'],mountainMax:'0'},'2027-01-01'));
 assert.equal(matches(race,{endurancePoints:['2','4']},'2027-01-01'),false);
 assert.equal(isWorldSeries(itra),false);assert.equal(groupLocations([itra])[0].count,1);
});
test('schema 2 composition, standalone ITRA pins, coverage counts and retained snapshot on failure',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'race-sources-'));
 try {
  const base={schemaVersion:1,fetchedAt:'2026-11-09T00:00:00Z',countries:{FR:{name:'France',continent:'Europe'}},events:[['event:1',utmb.eventName]],locations:[[utmb.place,'FR',6.87,45.92,'town','1']],records:[['1',0,utmb.name,utmb.date,50,2500,'50k',0,utmb.website,'race.1','serie',1]],coverage:{races:1,from:utmb.date,to:utmb.date}};
  const standalone={...itra,id:'itra:2027:3',sourceId:'2027:3',name:'Another Race',eventName:'Another Race',date:'2027-08-01',locationId:'itra:place:FR:annecy'};
  const options={basePath:join(dir,'base.gz'),itraPath:join(dir,'itra.json'),statusPath:join(dir,'status.json'),output:join(dir,'catalog.gz'),reportPath:join(dir,'report.json'),overridesPath:join(dir,'overrides.json')};
  await writeFile(options.basePath,gzipSync(JSON.stringify(base)));
  await writeFile(options.itraPath,JSON.stringify({schemaVersion:1,fetchedAt:base.fetchedAt,races:[itra,standalone]}));
  await writeFile(options.statusPath,JSON.stringify({state:'unavailable'}));
  options.marathonsPath=null;options.marathonsFallbackPath=null;
  const {data,report}=await compose(options);const races=expandDataset(data);
  assert.equal(report.imported,2);assert.equal(report.merged,1);assert.equal(data.coverage.races,2);assert.equal(races.length,2);
  assert.equal(races[0].sources.length,2);assert.equal(races[0].sources[0].values.distanceKm,50);assert.equal(races[1].id,standalone.id);
  assert.equal(data.sourceMeta.itra.state,'unavailable');assert.equal(data.sourceMeta.itra.races,2);
  const before=await readFile(options.output);await writeFile(options.itraPath,'{"schemaVersion":99}');
  await assert.rejects(compose(options));assert.deepEqual(await readFile(options.output),before);
  assert.equal(JSON.parse(gunzipSync(before)).schemaVersion,2);
 } finally {await rm(dir,{recursive:true,force:true});}
});

test('event ranges remain upcoming until their end; rolling dates cross years',()=>{
 const race={...itra,date:'2027-12-30',dateEnd:'2028-01-02',datePrecision:'event'};
 assert.ok(matches(race,{when:'upcoming',from:'2028-01-01',to:'2028-06-01'},'2028-01-01'));
 assert.equal(matches(race,{when:'past'},'2028-01-01'),false);
 assert.equal(matches(race,{when:'upcoming'},'2028-01-03'),false);
 assert.ok(matches(race,{when:'past'},'2028-01-03'));
 assert.equal(matches(race,{from:'2028-01-03'},'2028-01-01'),false);
 assert.equal(matches(race,{to:'2027-12-29'},'2028-01-01'),false);
});

test('single-day bulk summaries match only with strong unique event and course measurements',()=>{
 const listing={...itra,name:'Fixture Alpine · 50 km',datePrecision:'event-day'};
 assert.equal(matchSources([utmb],[listing]).report.merged,1);
 assert.equal(matchSources([utmb],[{...listing,elevationGainM:null}]).report.merged,0);
 assert.equal(matchSources([utmb],[{...listing,place:'Other town',longitude:8}]).report.merged,0);
 assert.equal(matchSources([utmb],[listing,{...listing,id:'itra:2027:3'}]).report.merged,0);
 assert.equal(matchSources([utmb,{...utmb,id:'utmb:2',name:'Fixture Alpine Night 50K'}],[listing]).report.merged,0);
});

test('town-country suffixes and numeric course spacing do not prevent matching',()=>{
 assert.equal(matchSources([{...utmb,place:'Chamonix, France',longitude:null}],[itra]).report.merged,1);
 assert.equal(matchSources([{...utmb,name:'Fixture Alpine UTNH100'}],[{...itra,name:'Fixture Alpine UTNH-100'}]).report.merged,1);
});
test('explicit multi-day ranges match a unique measured course, never ambiguous day/night courses',()=>{
 const listing={...itra,name:'Fixture Alpine · 50 km',date:'2027-07-15',dateEnd:'2027-07-17',datePrecision:'event'};
 assert.equal(matchSources([utmb],[listing]).report.merged,1);
 assert.equal(matchSources([utmb],[{...listing,dateEnd:'2027-07-15'}]).report.merged,0);
 assert.equal(matchSources([utmb,{...utmb,id:'utmb:2',date:'2027-07-17',name:'Fixture Alpine Night 50K'}],[listing]).report.merged,0);
 assert.equal(combineRace(utmb,listing).conflicts.some(c=>c.field==='date'),false);
});

test('event evidence connects different start towns and sponsor names before matching courses',()=>{
 const a=[utmb,{...utmb,id:'utmb:2',name:'Fixture Alpine 25K',distanceKm:25,elevationGainM:900}];
 const b=[itra,{...itra,id:'itra:2027:3',name:'Fixture Alpine 25K',distanceKm:25.3,elevationGainM:980}].map(r=>({...r,eventName:'Brand 17th Fixture Alpine',place:'Start village',longitude:8,date:'2027-07-17'}));
 const result=matchSources(a,b);
 assert.equal(result.report.eventLinks.length,1);assert.equal(result.report.merged,2);
 assert.deepEqual(result.entries.map(e=>e.matchId),['utmb:1','utmb:2']);
 assert.equal(result.report.accepted[0].reason,'edition-and-course');
});
test('a generic course name or shared generic event words cannot link unrelated events',()=>{
 for(const eventName of ['Unrelated Alpine','Other Ultra Trail','']) {
  assert.equal(matchSources([{...utmb,name:'50K'}],[{...itra,eventName,name:'50K'}]).report.merged,0,eventName);
 }
 assert.equal(matchSources([{...utmb,eventName:'Ultra Trail'}],[{...itra,eventName:'Ultra Trail'}]).report.merged,0);
});
test('relay leg numbers, stages, day/night and solo/team stay distinct',()=>{
 for(const [first,second] of [['125K RELAY 3 OF 4','125K RELAY 4 OF 4'],['Stage 1','Stage 2'],['50K Day','50K Night'],['50K Solo','50K Team'],['50K','50K Relay']]) {
  const a=[{...utmb,name:first},{...utmb,id:'utmb:2',name:second}];
  const b=[{...itra,name:first},{...itra,id:'itra:2027:3',name:second}];
  assert.deepEqual(matchSources(a,b).entries.map(e=>e.matchId),['utmb:1','utmb:2'],`${first}/${second}`);
  assert.equal(matchSources([a[0]],[b[1]]).report.merged,0);
 }
});
test('calendar-only names cannot resolve same-distance variants or use leftovers to force a match',()=>{
 const a=[utmb,{...utmb,id:'utmb:2',name:'Fixture Alpine Night 50K'}];
 const b=[itra,{...itra,id:'itra:2027:3',name:'Fixture Alpine · 50 km',datePrecision:'event-day'}];
 // The unspecified calendar listing is still a contender for the named course.
 assert.equal(matchSources(a,b).report.merged,0);
 assert.equal(matchSources(a.slice().reverse(),b.slice().reverse()).report.merged,0);
});
test('repeated editions and nearby but distinct course distances remain separate',()=>{
 const next={...utmb,id:'utmb:next',date:'2027-07-23'};
 assert.equal(matchSources([utmb,next],[{...itra,date:next.date}]).entries[0].matchId,next.id);
 const a=[utmb,{...utmb,id:'utmb:2',name:'Fixture Alpine 53K',distanceKm:53}];
 assert.equal(matchSources(a,[{...itra,name:'Fixture Alpine · 51 km',distanceKm:51,datePrecision:'event-day'}]).report.merged,0);
});

test('variant words in the event title do not label an individual course',()=>{
 const eventName='Fixture Alpine Running Day';
 assert.equal(matchSources([{...utmb,eventName}],[{...itra,eventName,name:eventName+' · 50 km',datePrecision:'event-day'}]).report.merged,1);
});
test('French relai and single/multi-stage distinctions are preserved',()=>{
 for(const [first,second] of [['W70','W70 relai'],['Single Stage 50K','Multi Stage 50K'],['Relais 1','Relais 2']]) {
  assert.equal(matchSources([{...utmb,name:first}],[{...itra,name:second}]).report.merged,0);
 }
});
test('a generic course label alone cannot overcome unrelated locations',()=>{
 assert.equal(matchSources([{...utmb,name:'50K'}],[{...itra,name:'50K',place:'Far away',longitude:20}]).report.merged,0);
});
