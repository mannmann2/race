import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {mkdir,readFile,realpath} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {compose} from './compose-catalog.mjs';
import {publishCatalog,atomicWrite} from './catalog-assets.mjs';
import {pruneData} from './prune.mjs';
import {locked} from './lock.mjs';
import {dueScripts} from './refresh-policy.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));await locked();
const python=process.env.RACE_PYTHON||'python3',itraOnly=process.argv.includes('--itra-only'),marathonsOnly=process.argv.includes('--worldsmarathons-only'),utmbOnly=process.argv.includes('--utmb-only');
const detailsOnly=process.argv.includes('--itra-details-only'),ifDue=process.argv.includes('--if-due');
const detailArg=process.argv.find(a=>/^--detail-limit=\d+$/.test(a));
const bulkArg=process.argv.find(a=>/^--itra-bulk-max-age-days=\d+$/.test(a))?.replace('--itra-bulk','--bulk');
await mkdir(root+'.cache',{recursive:true});let failed=false;
let scripts=detailsOnly?['itra_browser.py']:utmbOnly?['refresh.py']:marathonsOnly?['worldsmarathons.py']:itraOnly?['itra_browser.py']:['refresh.py','enrich.py','itra_browser.py','worldsmarathons.py'];
if(ifDue){
 let meta={},budget={};
 try{meta=JSON.parse(await readFile(root+'web/data/catalog-index.json','utf8')).meta;}catch(e){if(e.code!=='ENOENT')throw e;}
 try{budget=JSON.parse(await readFile(root+'.cache/itra/request-state.json','utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
 const due=new Set(dueScripts(meta,budget));scripts=scripts.filter(script=>due.has(script));
 if(!scripts.length){console.log('Bulk calendars are cached or in cooldown; no provider requests needed.');process.exit(0);}
}
// A targeted retry must preserve the other providers' recorded import results.
let results=[];
if(ifDue||detailsOnly||utmbOnly||itraOnly||marathonsOnly){try{const previous=JSON.parse(await readFile(root+'.cache/refresh-health.json','utf8'));results=(previous.results||[]).filter(r=>!scripts.includes(r.script));}catch(e){if(e.code!=='ENOENT')throw e;}}
async function itraVersion(){return (await Promise.all(['races.json','status.json'].map(async name=>{try{return await readFile(root+'.cache/itra/'+name,'utf8');}catch(e){if(e.code==='ENOENT')return '';throw e;}}))).join('\n');}
const beforeItra=detailsOnly?await itraVersion():null;
async function run(script,minutes){
 const browser=script==='itra_browser.py',args=browser?['-a',python,`scripts/${script}`,...(detailsOnly?['--details-only','--detail-limit=1']:detailArg?[detailArg]:['--detail-limit=0']),...(bulkArg?[bulkArg]:[])]:[`scripts/${script}`,...(script==='worldsmarathons.py'&&process.argv.includes('--force')?['--max-age-days=0']:[])];
 return await new Promise(resolve=>{
  const child=spawn(browser?'xvfb-run':python,args,{cwd:root,stdio:'inherit',detached:true});let timedOut=false,killTimer;
  const timer=setTimeout(()=>{timedOut=true;try{process.kill(-child.pid,'SIGTERM');}catch{}killTimer=setTimeout(()=>{try{process.kill(-child.pid,'SIGKILL');}catch{}},5000);},minutes*60000);
  child.once('error',()=>{});child.once('close',code=>{clearTimeout(timer);clearTimeout(killTimer);resolve({script,ok:code===0&&!timedOut,timedOut,finishedAt:new Date().toISOString()});});
 });
}
for(const script of scripts){
 const result=await run(script,script==='itra_browser.py'?30:script==='enrich.py'?10:15);results.push(result);
 if(script==='refresh.py')await atomicWrite(root+'.cache/utmb-status.json',JSON.stringify({state:result.ok?'available':'unavailable',attemptedAt:result.finishedAt,message:result.ok?'Verified index downloaded.':'Refresh failed; retaining the last verified index.'}));
 if(!result.ok){failed=true;console.error(`${script} failed${result.timedOut?' (time limit)':''}; retaining its last verified data and continuing other sources.`);}
}
failed=results.some(r=>!r.ok);
if(detailsOnly&&results.find(r=>r.script==='itra_browser.py')?.ok&&beforeItra===await itraVersion()){console.log('ITRA: no data or status changes; no catalog rebuild needed.');process.exit(0);}
try{
 const {data}=await compose();
 if(process.argv.includes('--publish')){
  const active=await realpath(root+(existsSync(root+'current')?'current':'dist'));
  await publishCatalog(root+'web/data',active+'/data');
  await pruneData(active+'/data');await pruneData(root+'web/data');
  console.log('Published validated catalog without replacing application files.');
 }
 await atomicWrite(root+'.cache/refresh-health.json',JSON.stringify({state:failed?'degraded':'ok',finishedAt:new Date().toISOString(),results,sourceMeta:data.sourceMeta}));
}catch(error){failed=true;await atomicWrite(root+'.cache/refresh-health.json',JSON.stringify({state:'failed',finishedAt:new Date().toISOString(),results,message:error.message}));console.error('Publication rejected:',error.message);}
if(failed)process.exitCode=1;
