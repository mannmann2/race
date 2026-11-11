import test from 'node:test';
import assert from 'node:assert/strict';
import {dueScripts} from '../scripts/refresh-policy.mjs';
const now=new Date('2026-11-11T09:00:00Z');
const fresh=()=>({sourceMeta:Object.fromEntries(['utmb','itra','worldsmarathons'].map(p=>[p,{state:'available',fetchedAt:'2026-11-09T09:00:00Z'}]))});
test('fresh weekly calendars cause no network work',()=>{
 assert.deepEqual(dueScripts(fresh(),{},now),[]);
 const meta=fresh();meta.sourceMeta.itra.detailRefreshError='HTTP 403';assert.deepEqual(dueScripts(meta,{},now),[]);
});
test('retry only failed sources; a full weekly window expires precisely',()=>{
 const meta=fresh();meta.sourceMeta.utmb.state='unavailable';assert.deepEqual(dueScripts(meta,{},now),['refresh.py','enrich.py']);
 meta.sourceMeta.utmb.state='available';meta.sourceMeta.itra.fetchedAt='2026-11-04T09:00:00Z';assert.deepEqual(dueScripts(meta,{},now),['itra_browser.py']);
 assert.deepEqual(dueScripts(meta,{},new Date('2026-11-11T08:59:59Z')),[]);
});
test('ITRA cooldown defers overdue bulk work and survives daily checks',()=>{
 const meta=fresh();meta.sourceMeta.itra.fetchedAt='2026-11-01T00:00:00Z';const budget={cooldownUntil:'2026-11-13T09:00:00Z'};
 assert.deepEqual(dueScripts(meta,budget,now),[]);
 assert.deepEqual(dueScripts(meta,budget,new Date('2026-11-13T09:00:00Z')),['itra_browser.py']);
 assert.deepEqual(dueScripts({},budget,now),['refresh.py','enrich.py','worldsmarathons.py']);
});
