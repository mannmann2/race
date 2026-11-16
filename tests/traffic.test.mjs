import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,readdirSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {TrafficStore,dayAt,dateRange,clientIP,eligible,authorizedDebug,IDLE_MS} from '../scripts/traffic.mjs';
const ua='Mozilla/5.0 Chrome/141.0.0.0 Safari/537.36';
function req(ip='8.8.8.8',headers={}){return {socket:{remoteAddress:'127.0.0.1'},headers:{'x-race-client-ip':ip,'user-agent':ua,...headers}};}
function event(page='abcdefghijklmnop',seq=0,activeMs=0){return {page,seq,activeMs,start:seq===0};}
function fixture(){const folder=mkdtempSync(join(tmpdir(),'race-traffic-')),path=join(folder,'traffic.sqlite');let now=Date.parse('2026-11-16T12:00:00Z');const options={now:()=>now,geo:{lookup:()=>({country:'United Kingdom',countryCode:'GB',region:'England',city:'London'}),status:()=>({available:true})}};const store=new TrafficStore(path,options);return {folder,path,store,options,add:ms=>{now+=ms;},close:()=>{store.close();rmSync(folder,{recursive:true,force:true});}};}
test('daily visitors, reloads and tab overlap count a session once and union foreground time',()=>{const f=fixture();try{
 f.store.ingest(req(),event());f.add(15000);f.store.ingest(req(),event('abcdefghijklmnop',1,15000));
 f.store.ingest(req(),event('another-page-1234'));f.add(15000);f.store.ingest(req(),event('abcdefghijklmnop',2,30000));f.store.ingest(req(),event('another-page-1234',1,15000));
 const summary=f.store.summary('2026-11-16','2026-11-16');assert.equal(summary.todayVisitors,1);assert.equal(summary.sessions,1);assert.equal(summary.activeMs,30000);assert.equal(summary.spanMs,30000);assert.equal(summary.locations[0].city,'London');assert.equal(summary.countries[0].sessions,1);
 assert.equal(f.store.ingest(req(),event('abcdefghijklmnop',2,30000)).accepted,false);assert.equal(f.store.summary('2026-11-16','2026-11-16').activeMs,30000);
}finally{f.close();}});
test('inactivity starts another session while daily visitors remain deduplicated; time is bounded',()=>{const f=fixture();try{
 f.store.ingest(req(),event());f.add(10000);f.store.ingest(req(),event('abcdefghijklmnop',1,86400000));assert.equal(f.store.summary('2026-11-16','2026-11-16').activeMs,10000);
 f.add(IDLE_MS);f.store.ingest(req(),event('abcdefghijklmnop',2,86400000));const summary=f.store.summary('2026-11-16','2026-11-16');assert.equal(summary.sessions,2);assert.equal(summary.todayVisitors,1);assert.equal(summary.activeMs,10000);
}finally{f.close();}});
test('daily identifiers rotate, secret persists across restarts, and raw IPs or event IDs never reach storage',()=>{const f=fixture();try{
 f.store.ingest(req('203.0.113.43'),event());const original=f.store.db.prepare('SELECT visitor FROM visitors').get().visitor;f.store.close();
 const reopened=new TrafficStore(f.path,f.options);try{const other=new TrafficStore(join(f.folder,'other.sqlite'),{key:readFileSync(join(f.folder,'traffic-key')),now:f.options.now});try{assert.equal(reopened.hash('example'),other.hash('example'));}finally{other.close();}assert.equal(reopened.db.prepare('SELECT visitor FROM visitors').get().visitor,original);
 f.add(86400000);reopened.ingest(req('203.0.113.43'),event());const visitors=reopened.db.prepare('SELECT visitor FROM visitors').all();assert.notEqual(visitors[0].visitor,visitors[1].visitor);
 for(const file of readdirSync(f.folder).filter(n=>n.startsWith('traffic.sqlite')))assert.equal(readFileSync(join(f.folder,file)).includes(Buffer.from('203.0.113.43')),false);
 assert.equal(JSON.stringify(reopened.summary('2026-11-16','2026-11-17')).includes('abcdefghijklmnop'),false);
 }finally{reopened.close();}
}finally{rmSync(f.folder,{recursive:true,force:true});}});
test('retention removes identities, sessions and pages without leaving related records',()=>{const f=fixture();try{f.store.ingest(req(),event());f.add(90*86400000);f.store.prune();for(const table of ['visitors','sessions','pages'])assert.equal(f.store.db.prepare(`SELECT COUNT(*) count FROM ${table}`).get().count,0);}finally{f.close();}});
test('proxy IPs and debug identity are trusted only from loopback; bots and opt-outs are excluded',()=>{
 assert.equal(clientIP(req()),'8.8.8.8');assert.equal(clientIP({socket:{remoteAddress:'203.0.113.4'},headers:{'x-race-client-ip':'8.8.8.8'}}),'203.0.113.4');
 assert.equal(authorizedDebug(req('8.8.8.8',{'x-race-debug-user':'arman'}),true),true);assert.equal(authorizedDebug(req(),true),false);assert.equal(authorizedDebug({socket:{remoteAddress:'203.0.113.4'},headers:{'x-race-debug-user':'arman'}},true),false);
 for(const headers of [{'user-agent':'Googlebot'},{'user-agent':'HeadlessChrome'},{dnt:'1'},{'sec-gpc':'1'}])assert.equal(eligible(req('8.8.8.8',headers)),false);
 const f=fixture();try{assert.equal(f.store.ingest(req('8.8.8.8',{dnt:'1'}),event()).accepted,false);assert.equal(f.store.summary('2026-11-16','2026-11-16').sessions,0);}finally{f.close();}
});
test('calendar boundaries use UK time, ranges fill gaps, and event input is validated',()=>{
 assert.equal(dayAt(Date.parse('2026-07-01T23:30:00Z')),'2026-07-02');assert.equal(dayAt(Date.parse('2026-11-16T23:30:00Z')),'2026-11-16');assert.equal(dateRange('2028-02-28','2028-03-01').length,3);
 for(const [from,to]of [['2026-02-31','2026-03-01'],['2026-11-17','2026-11-16'],['2026-01-01','2026-12-31']])assert.throws(()=>dateRange(from,to));
 const f=fixture();try{assert.throws(()=>f.store.ingest(req(),{page:'bad',seq:0,activeMs:0,start:true}));const report=f.store.summary('2026-11-15','2026-11-16');assert.equal(report.daily.length,2);assert.equal(report.sessions,0);}finally{f.close();}
});
