import test from 'node:test';import assert from 'node:assert/strict';import{readFileSync}from'node:fs';import{mkdtemp,readFile,writeFile,access,rm}from'node:fs/promises';import{tmpdir}from'node:os';import{join}from'node:path';import{gunzipSync}from'node:zlib';
import{cameraFromURL,raceFromURL,sourceHealth}from'../web/sharing.mjs';import{validateCatalog}from'../scripts/catalog-quality.mjs';import{writeCatalogAssets}from'../scripts/catalog-assets.mjs';import{matchSources,providerCourseName}from'../scripts/match-sources.mjs';import{expandDataset}from'../web/core.mjs';
const base={schemaVersion:1,fetchedAt:'2026-11-09T00:00:00Z',countries:{FR:{name:'France',continent:'Europe'}},events:[['1','Synthetic Alpine']],locations:[['Chamonix','FR',6.8,45.9,'town',null]],records:[['1',0,'Synthetic Alpine 50K','2026-11-14',50,2500,'50k',0,null,null,'qualifier',0],['2',0,'Synthetic Alpine 50K','2020-11-14',50,2500,'50k',0,null,null,'qualifier',0]],coverage:{races:2,from:'2020-11-14',to:'2026-11-14'}};
test('shared camera and race links validate input; source health follows each source clock',()=>{
 assert.deepEqual(cameraFromURL('#view=6.8,45.9,6'),{center:[6.8,45.9],zoom:6});for(const s of ['#view=999,0,3','#view=0,0,99','#view=x,0,4'])assert.equal(cameraFromURL(s),null);
 assert.equal(raceFromURL('#race=itra%3A2027%3A123'),'itra:2027:123');assert.equal(raceFromURL('#race=javascript:foo'),null);
 assert.equal(sourceHealth({fetchedAt:'2026-11-08'},'utmb',new Date('2026-11-09')).stale,false);assert.equal(sourceHealth({fetchedAt:'2026-10-01'},'itra',new Date('2026-11-09')).stale,true);
 assert.equal(sourceHealth({fetchedAt:'2026-11-08'},'utmb',new Date('2026-11-15')).stale,false);
 assert.equal(sourceHealth({fetchedAt:'2026-11-08'},'utmb',new Date('2026-11-19')).stale,true);
 const partial=sourceHealth({state:'available',fetchedAt:'2026-11-08',detailRefreshError:'HTTP 403'},'itra',new Date('2026-11-09'));
 assert.equal(partial.failed,false);assert.equal(partial.detailsFailed,true);assert.equal(partial.stale,false);
 assert.equal(sourceHealth({state:'unavailable',fetchedAt:'2026-11-08'},'utmb',new Date('2026-11-09')).failed,true);
});
test('publication rejects duplicate IDs, invalid dates, ratings and unexpected source loss',()=>{
 assert.equal(validateCatalog(base).races,2);
 for(const mutate of [d=>d.records.push(d.records[0]),d=>{d.records=d.records.slice(0,1);d.coverage.races=1;}]){const data=structuredClone(base);mutate(data);assert.throws(()=>validateCatalog(data,{previous:base}));}
 const badDate={schemaVersion:3,races:[{...expandDataset(base)[0],date:'2026-02-31'}],coverage:{races:1}};assert.throws(()=>validateCatalog(badDate),/date/);
 const data={schemaVersion:3,races:[{...expandDataset(base)[0],extensions:{itra:{endurancePoints:7}}}],coverage:{races:1}};assert.throws(()=>validateCatalog(data),/endurancePoints/);
});
test('upcoming payload is small and archive preserves history with an immutable pointer',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'race-assets-'));try{const index=await writeCatalogAssets(dir,base,{now:new Date('2026-11-09')});assert.equal(index.upcoming.races,1);assert.equal(index.archive.races,2);const upcoming=JSON.parse(gunzipSync(await readFile(join(dir,index.upcoming.url))));assert.equal(upcoming.races[0].id,'utmb:1');const again=await writeCatalogAssets(dir,base,{now:new Date('2026-11-09')});assert.equal(index.version,again.version);assert.equal(index.upcoming.url,again.upcoming.url);}finally{await rm(dir,{recursive:true});}
});
test('reviewed launch matches retain evidence and do not mix the solo/walk/relay categories',()=>{
 const rows=JSON.parse(readFileSync(new URL('./fixtures/launch-matches.json',import.meta.url))),overrides=JSON.parse(readFileSync(new URL('../scripts/source-overrides.json',import.meta.url)));
 const result=matchSources(rows.map(r=>r.utmb),rows.map(r=>r.itra),overrides);assert.equal(result.report.merged,rows.length);
 const solo=rows.find(r=>r.itra.id==='itra:2027:125556'),relay={...solo.itra,id:'itra:2027:125687',sourceId:'2027:125687',sourceUrl:solo.itra.sourceUrl.replace('/2027/125556','RELAIS/2027/125687')};
 assert.ok(providerCourseName(relay).includes('relais'));assert.equal(matchSources([solo.utmb],[relay]).report.merged,0);
 const trail=rows.find(r=>r.itra.id==='itra:2027:122436'),walk={...trail.itra,id:'itra:2027:122437',sourceId:'2027:122437',sourceUrl:trail.itra.sourceUrl.replace('Trail.Experience','Caminhada').replace('/122436','/122437')};assert.equal(matchSources([trail.utmb],[walk]).report.merged,0);
});
test('explicit URL variants match the right courses with all neighbouring candidates present',()=>{
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/url-variants.json',import.meta.url))),result=matchSources(fixture.utmb,fixture.itra),actual=new Map(result.entries.map(e=>[e.race.id,e.matchId]));
 for(const [iid,uid]of Object.entries(fixture.expected))assert.equal(actual.get(iid),uid,iid);
 const reverse=matchSources(fixture.utmb.slice().reverse(),fixture.itra.slice().reverse());assert.deepEqual(new Map(reverse.entries.map(e=>[e.race.id,e.matchId])),actual);
});

test('publishing a changed catalog removes stale compressed index pointers',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'race-pointer-'));try{
  const first=await writeCatalogAssets(dir,base,{now:new Date('2026-11-09')});
  await writeFile(join(dir,'catalog-index.json.br'),'stale');await writeFile(join(dir,'catalog-index.json.gz'),'stale');
  const changed=structuredClone(base);changed.fetchedAt='2026-11-10T00:00:00Z';
  const second=await writeCatalogAssets(dir,changed,{now:new Date('2026-11-10')});assert.notEqual(first.version,second.version);
  await assert.rejects(access(join(dir,'catalog-index.json.br')));await assert.rejects(access(join(dir,'catalog-index.json.gz')));
  assert.equal(JSON.parse(await readFile(join(dir,'catalog-index.json'),'utf8')).version,second.version);
 }finally{await rm(dir,{recursive:true});}
});
