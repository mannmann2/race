import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { matchSources } from '../scripts/match-sources.mjs';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/matching-real.json',import.meta.url)));
const result=matchSources(fixture.utmb,fixture.itra);
const ids=new Map(result.entries.map(e=>[e.race.id,e.matchId]));
// Independently reviewed source pairs, including all neighbouring courses in the
// frozen inputs so these checks cannot pass by hiding competing alternatives.
const reviewed={
 '2026:113341':'151290','2026:113342':'151292','2026:113344':'151298',
 '2026:113343':'151300','2026:113345':'151294','2026:113346':'151296',
 '2026:117735':'147286',
 '2026:121361':'153822','2026:121091':'153820','2026:123206':'158490',
 '2026:121088':'153818','2026:121087':'153816','2026:121086':'153814',
 '2026:125149':'159270','2026:125150':'159268',
 '2026:121320':'147422','2026:121321':'147418','2026:121322':'147416',
 '2026:121523':'153786','2026:121524':'153788','2026:121522':'153782','2026:121518':'153780',
 '2026:118417':'148092','2026:123524':'156608','2026:115755':'144336',
 '2027:123749':'156926','2027:124680':'156930',
 '2027:125789':'159192','2027:125788':'159196'
};
test('reviewed real courses match despite start-town, sponsor, date and measurement differences',()=>{
 for(const [itra,utmb] of Object.entries(reviewed))assert.equal(ids.get(`itra:${itra}`),`utmb:${utmb}`,itra);
 assert.equal(new Set(result.entries.map(e=>e.matchId).filter(Boolean)).size,result.report.merged);
});
test('real relay legs do not merge with another leg or the full 125K course',()=>{
 const solo=ids.get('itra:2026:121516');assert.equal(solo,'utmb:153778');
 for(const key of ['121523','121524','121522','121518'])assert.notEqual(ids.get(`itra:2026:${key}`),solo);
 // A malformed ITRA relay distance must not be silently treated as the solo W70.
 assert.equal(ids.get('itra:2026:115756'),null);
});
test('same-distance courses use distinct ascent evidence; unspecified stage formats stay unresolved',()=>{
 assert.notEqual(ids.get('itra:2027:123749'),ids.get('itra:2027:124680'));
 for(const id of ['itra:2027:124181','itra:2027:124177'])assert.equal(ids.get(id),null,id);
 // 10.32 km versus 12 km is too large a discrepancy to assume identity.
 assert.equal(ids.get('itra:2026:121319'),null);
});
test('reversing source order cannot change any assignment',()=>{
 const reversed=matchSources(fixture.utmb.slice().reverse(),fixture.itra.slice().reverse());
 assert.deepEqual(new Map(reversed.entries.map(e=>[e.race.id,e.matchId])),ids);
});
