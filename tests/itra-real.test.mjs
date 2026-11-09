import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { expandDataset, matches, groupLocations } from '../web/core.mjs';
import { matchSources } from '../scripts/match-sources.mjs';

const base=JSON.parse(gunzipSync(readFileSync(new URL('../web/data/races.json.gz',import.meta.url))));
const indexed=JSON.parse(readFileSync(new URL('../data/itra-indexed-snapshot.json',import.meta.url)));
const overrides=JSON.parse(readFileSync(new URL('../scripts/source-overrides.json',import.meta.url)));
const matched=matchSources(expandDataset(base),indexed.races,overrides);
const races=expandDataset({...base,schemaVersion:2,additionalRaces:matched.entries});

test('real ITRA fallback adds courses, deduplicates shared editions and preserves UTMB records',()=>{
 assert.equal(indexed.races.length,35);
 assert.equal(matched.report.merged,24);assert.equal(matched.report.added,11);
 assert.equal(races.length,base.records.length+11);
 assert.equal(new Set(races.map(r=>r.id)).size,races.length);
 const withItra=races.filter(r=>matches(r,{source:'itra'},'2026-11-09'));
 assert.equal(withItra.length,35);
 assert.equal(withItra.filter(r=>r.longitude!=null).length,34);
 assert.equal(races.filter(r=>matches(r,{source:'both'},'2026-11-09')).length,24);
 assert.equal(groupLocations(withItra).reduce((n,g)=>n+g.count,0),34);
});
test('real source ratings include zero, exclude unknowns, and are not copied between courses',()=>{
 const withItra=races.filter(r=>matches(r,{source:'itra'},'2026-11-09'));
 assert.equal(withItra.filter(r=>matches(r,{endurancePoints:['0','1','2','3','4','5','6']},'2026-11-09')).length,7);
 assert.equal(withItra.filter(r=>matches(r,{mountainMin:'0',mountainMax:'12'},'2026-11-09')).length,31);
 const sky=races.find(r=>r.id==='utmb:139392');
 assert.equal(sky.extensions.itra.endurancePoints,2);assert.equal(sky.extensions.itra.mountainLevel,5);
 const day=races.find(r=>r.id==='utmb:153118'),night=races.find(r=>r.id==='utmb:153122');
 assert.equal(day.sources.find(s=>s.provider==='itra').id,'2026:116496');
 assert.equal(night.sources.find(s=>s.provider==='itra').id,'2026:116499');
 assert.equal(day.extensions.itra.finisherLevel,370);assert.equal(night.extensions.itra.finisherLevel,340);
});
test('indexed freshness and conflicting real dates remain explicit on shared records',()=>{
 const race=races.find(r=>r.id==='utmb:156240');
 assert.equal(race.date,'2026-12-06');
 assert.ok(race.conflicts.some(c=>c.field==='date'&&c.itra==='2026-12-05'));
 const source=race.sources.find(s=>s.provider==='itra');
 assert.equal(source.acquisition,'public-index');assert.equal(source.fetchedAt,null);
 assert.ok(source.retrievedAt);assert.ok(source.indexAge);
});
