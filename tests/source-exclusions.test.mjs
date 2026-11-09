import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sourceExcluded} from '../scripts/source-exclusions.mjs';

const exclusions=JSON.parse(readFileSync(new URL('../scripts/source-exclusions.json',import.meta.url)));
test('reviewed provider placeholders stay excluded when their listing dates change',()=>{
 for(const year of [2026,2027,2030])for(const slug of ['internal-test-event','membership-test-event','rothwell-kebabathon-juoes-test']){
  assert.equal(sourceExcluded({id:`worldsmarathons:${year}:${slug}:marathon`,eventId:`worldsmarathons:event:${slug}`},exclusions),true);
 }
 for(const id of ['itra:2027:118896','itra:2027:122030'])assert.equal(sourceExcluded({id},exclusions),true);
});
test('exclusions use exact provider IDs and preserve legitimate names containing test or demo',()=>{
 for(const r of [
  {id:'utmb:156184',name:'5K Vertical Test'},
  {id:'utmb:78698',name:'DEMO TRAIL ULTRA'},
  {id:'itra:2026:123152',name:'The Shortest Day'},
  {id:'itra:unreviewed',name:'Internal Test Event'},
  {id:'worldsmarathons:2027:internal-test-event-other:marathon',eventId:'worldsmarathons:event:internal-test-event-other'}
 ])assert.equal(sourceExcluded(r,exclusions),false,r.id);
});
