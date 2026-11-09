import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { expandDataset, matches, sortRaces, groupLocations, safeUrl, localToday, presetDates, isWorldSeries, racesInView } from '../web/core.mjs';
const data=JSON.parse(gunzipSync(readFileSync(new URL('../web/data/races.json.gz',import.meta.url))));
const races=expandDataset(data);
const base={q:'',categories:[],countries:[],when:'all',continent:'',from:'',to:'',distanceMin:'',distanceMax:'',elevationMin:'',elevationMax:''};
const fixture={...races.find(r=>r.longitude!=null),id:'fixture',name:'Épreuve des Alpes',date:'2026-11-08',distanceKm:50,elevationGainM:0,countryCode:'FR',continent:'Europe',searchText:'epreuve des alpes chamonix france europe',extensions:{utmb:{category:'100k'}}};
test('complete snapshot has stable unique ids, valid dates and only usable URLs',()=>{
 assert.equal(races.length,data.coverage.races);assert.equal(new Set(races.map(r=>r.id)).size,races.length);
 for(const r of races){assert.match(r.id,/^utmb:\d+$/);assert.match(r.date,/^\d{4}-\d{2}-\d{2}$/);assert.ok(!Number.isNaN(Date.parse(r.date)));assert.ok(r.distanceKm==null || Number.isFinite(r.distanceKm));assert.ok(r.longitude==null || (r.longitude>=-180 && r.longitude<=180 && r.latitude>=-90 && r.latitude<=90));assert.ok(r.website==null || /^https?:/.test(r.website));}
});
test('upcoming includes today and past excludes today, dates are inclusive',()=>{
 assert.equal(matches(fixture,{...base,when:'upcoming'},'2026-11-08'),true);
 assert.equal(matches(fixture,{...base,when:'past'},'2026-11-08'),false);
 assert.equal(matches(fixture,{...base,from:'2026-11-08',to:'2026-11-08'},'2026-11-08'),true);
 assert.equal(matches(fixture,{...base,from:'2026-11-09'},'2026-11-08'),false);
});
test('search ignores accents and supports multiple terms; categories do not substitute for actual distance',()=>{
 assert.equal(matches(fixture,{...base,q:'épreuve france'},'2026-11-08'),true);
 assert.equal(matches(fixture,{...base,q:'Nepal'},'2026-11-08'),false);
 assert.equal(matches(fixture,{...base,categories:['100k'],distanceMax:'55'},'2026-11-08'),true);
 assert.equal(matches(fixture,{...base,categories:['50k']},'2026-11-08'),false);
});
test('filters combine and retain zero elevation while excluding missing measurements',()=>{
 assert.equal(matches(fixture,{...base,countries:['US','FR'],continent:'Europe',distanceMin:'50',distanceMax:'50',elevationMin:'0',elevationMax:'0'},'2026-11-08'),true);
 assert.equal(matches({...fixture,elevationGainM:null},{...base,elevationMax:'100'},'2026-11-08'),false);
 assert.equal(matches(fixture,{...base,continent:'Asia'},'2026-11-08'),false);
});
test('next-up sorting prioritises upcoming then most recent historical editions',()=>{
 const items=['2025-01-01','2026-11-09','2026-11-08','2026-10-20'].map((date,i)=>({...fixture,id:String(i),date}));
 assert.deepEqual(sortRaces(items,'soonest','2026-11-08').map(r=>r.date),['2026-11-08','2026-11-09','2026-10-20','2025-01-01']);
});
test('map groups colocated race editions without dropping their counts; missing coordinates remain ungrouped',()=>{
 const group=groupLocations([fixture,{...fixture,id:'two'},{...fixture,id:'missing',longitude:null}]);
 assert.equal(group.length,1);assert.equal(group[0].count,2);
 const real=groupLocations(races);assert.equal(real.reduce((n,g)=>n+g.count,0),races.filter(r=>r.longitude!=null).length);
});
test('external links reject executable schemes',()=>{assert.equal(safeUrl('javascript:alert(1)'),null);assert.equal(safeUrl('data:text/html,test'),null);assert.equal(safeUrl('https://example.com'),'https://example.com/');});
test('local calendar date does not shift across UTC boundaries',()=>{const d=new Date(2026,10,8,23,59);assert.equal(localToday(d),'2026-11-08');});
test('date presets use local calendar months and clamp month ends and leap years',()=>{
 assert.deepEqual(presetDates('2w','2026-12-25'),{from:'2026-12-25',to:'2027-01-08'});
 assert.deepEqual(presetDates('1m','2026-01-31'),{from:'2026-01-31',to:'2026-02-28'});
 assert.deepEqual(presetDates('1m','2024-01-31'),{from:'2024-01-31',to:'2024-02-29'});
 assert.deepEqual(presetDates('6m','2026-11-08'),{from:'2026-11-08',to:'2027-05-08'});
 assert.deepEqual(presetDates('12m','2024-02-29'),{from:'2024-02-29',to:'2025-02-28'});
 assert.deepEqual(presetDates('any','2026-11-08'),{from:'',to:''});
});
test('World Series uses source levels, including Majors and Finals, not a name heuristic',()=>{
 for(const level of ['serie','major','finale'])assert.ok(isWorldSeries({...fixture,extensions:{utmb:{level}}}));
 assert.equal(isWorldSeries({...fixture,eventName:'by UTMB',extensions:{utmb:{level:'qualifier'}}}),false);
 assert.equal(matches(fixture,{...base,worldSeries:true},'2026-11-08'),false);
});
test('viewport selection excludes unmapped and off-screen locations without losing the global data',()=>{
 const input=[{...fixture,locationId:'visible'},{...fixture,id:'away',locationId:'away'},{...fixture,id:'unknown',locationId:'visible',longitude:null}];
 assert.deepEqual(racesInView(input,['visible']).map(r=>r.id),['fixture']);
 assert.equal(racesInView(input,[],false).length,3);assert.equal(racesInView(input,[]).length,0);
 assert.equal(racesInView(input,null).length,3);
});
test('photos retain provenance and missing categories are exactly the source nulls',()=>{
 assert.ok(races.filter(r=>r.image).length>0);
 for(const r of races.filter(r=>r.image)){assert.ok(r.imageSource);assert.match(r.image,/^https:/);}
 assert.equal(races.filter(r=>!r.extensions.utmb.category).length,data.records.filter(row=>!row[6]).length);
});
