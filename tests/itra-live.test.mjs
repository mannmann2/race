import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { expandDataset, matches, groupLocations } from '../web/core.mjs';
import { gunzipSync } from 'node:zlib';
if(!(existsSync(new URL('../data/itra-snapshot.json',import.meta.url)) && existsSync(new URL('../web/data/catalog.json.gz',import.meta.url))))test('private provider snapshots are optional in a public checkout',{skip:true},()=>{});else{
const snapshot=JSON.parse(readFileSync(new URL('../data/itra-snapshot.json',import.meta.url)));
const catalog=JSON.parse(gunzipSync(readFileSync(new URL('../web/data/catalog.json.gz',import.meta.url))));
test('live bulk snapshot matches reported coverage and has valid per-course dates, coordinates and ratings',()=>{
 assert.equal(snapshot.acquisition,'browser-calendar');
 assert.equal(snapshot.coverage.races,snapshot.coverage.calendarDisplayedRaces);
 assert.equal(snapshot.races.length,snapshot.coverage.races+snapshot.coverage.archived);
 assert.equal(new Set(snapshot.races.map(r=>r.id)).size,snapshot.races.length);
 for(const r of snapshot.races){
  assert.match(r.sourceUrl,/^https:\/\/itra\.run\/Races\/RaceDetails\//);
  assert.match(r.date,/^\d{4}-\d{2}-\d{2}$/);
  assert.ok(!r.dateEnd||r.dateEnd>=r.date);
  assert.ok(r.longitude==null||(Math.abs(r.longitude)<=180&&Math.abs(r.latitude)<=90));
  for(const [key,max] of [['endurancePoints',6],['mountainLevel',12]]){
   const value=r.extensions.itra[key];assert.ok(value==null||(Number.isInteger(value)&&value>=0&&value<=max));
  }
  if(r.detailsFetchedAt)assert.equal(r.datePrecision,'race');
 }
});
test('published catalog includes every live source record once, with both links on matched cards',()=>{
 const races=expandDataset(catalog),itra=races.filter(r=>matches(r,{source:'itra'},'2000-01-01'));
 assert.equal(itra.length,catalog.additionalRaces.filter(e=>e.race.source==='itra').length);
 assert.equal(new Set(itra.flatMap(r=>r.sources.filter(s=>s.provider==='itra').map(s=>s.id))).size,itra.length);
 assert.equal(races.filter(r=>matches(r,{source:'both'},'2000-01-01')).length,catalog.mergeSummary.merged);
 assert.equal(groupLocations(itra).reduce((n,g)=>n+g.count,0),itra.filter(r=>r.longitude!=null).length);
 assert.ok(itra.some(r=>!r.sources.some(s=>s.provider==='utmb')&&r.longitude!=null));
 for(const r of itra.filter(r=>r.sources.length===2))assert.ok(r.sources.every(s=>/^https:\/\//.test(s.url)));
});

}
