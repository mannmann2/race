import { expandDataset, matches, sortRaces, groupLocations, racesInView } from './core.mjs';
let races=[],all=[],current=[],byId=new Map(),filters={},filterSeq=0,viewVersion=0,locations=null,pointKey='',points=[],index=null,full=false,chain=Promise.resolve();
const publicRace=({searchText,...race})=>race;
async function request(path,gzip=false){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000);
 try{const response=await fetch(path,{cache:'no-cache',signal:controller.signal});if(!response.ok){const error=new Error(`Race data unavailable (${response.status}). Please try again.`);error.status=response.status;throw error;}
  if(gzip&&typeof DecompressionStream==='undefined')throw new Error('Please use a current browser to load the race catalog.');
  return await (gzip?new Response(response.body.pipeThrough(new DecompressionStream('gzip'))):response).json();
 }catch(e){if(e.name==='AbortError')throw new Error('The race download took too long. Check your connection and try again.');throw e;}finally{clearTimeout(timer);}
}
function install(data){const next=expandDataset(data);races=next;byId=new Map(next.map(r=>[r.id,r]));pointKey='';points=[];}
async function archive(){if(full||!index)return;try{const data=await request('./data/'+index.archive.url,true);install(data);full=true;}catch(e){e.kind='archive';throw e;}}
function listResult(type,extra={}){current=racesInView(all,locations,filters.inView);self.postMessage({type,seq:filterSeq,viewVersion,total:current.length,globalTotal:all.length,unmapped:all.filter(r=>r.longitude==null).length,countries:new Set(current.map(r=>r.countryCode).filter(Boolean)).size,items:current.slice(0,60).map(publicRace),page:0,...extra});}
async function handle(m){
 if(m.type==='init'){
  let next;
  try{next=await request('./data/catalog-index.json');}catch(e){if(e.status!==404)throw e;}
  if(next){
   if(next.schemaVersion!==1||!next.meta||!/^catalog-[a-z0-9-]+\.json\.gz$/.test(next.archive?.url)||!/^catalog-upcoming-[a-z0-9]+\.json\.gz$/.test(next.upcoming?.url))throw new Error('The catalog needs updating. Please try again later.');
   if(m.background&&index?.version===next.version&&index?.upcoming?.url===next.upcoming.url){self.postMessage({type:'refresh-unchanged'});return;}
   const useFull=full,body=await request('./data/'+(useFull?next.archive.url:next.upcoming.url),true);install(body);index=next;full=useFull;
   self.postMessage({type:'ready',meta:next.meta});
  }else{const data=await request('./data/catalog.json.gz',true);install(data);index=null;full=true;const used=[...new Set(races.map(r=>r.countryCode).filter(Boolean))];self.postMessage({type:'ready',meta:{fetchedAt:data.fetchedAt,coverage:{...data.coverage,unmapped:races.filter(r=>r.longitude==null).length},source:data.source,sourceMeta:data.sourceMeta,mergeSummary:data.mergeSummary,countries:used.map(code=>({code,name:data.countries[code]?.name||races.find(r=>r.countryCode===code)?.country||code})).sort((a,b)=>a.name.localeCompare(b.name))}});}
 }else if(m.type==='filter'){
  if(index&&!full&&(m.filters.when!=='upcoming'||(m.filters.from&&m.filters.from<index.upcoming.from)||(!m.filters.from&&m.today<index.upcoming.from)))await archive();
  filters=m.filters;filterSeq=m.seq;viewVersion=m.viewVersion;locations=m.locationIds;
  all=sortRaces(races.filter(r=>matches(r,filters,m.today)),m.sort,m.today);
  const {inView,...rest}=filters,key=JSON.stringify({filters:rest,today:m.today});if(key!==pointKey)points=groupLocations(all);pointKey=key;listResult('results',{points,pointKey});
 }else if(m.type==='view'){if(m.seq!==filterSeq)return;locations=m.locationIds;viewVersion=m.viewVersion;listResult('view');
 }else if(m.type==='page'){if(m.seq!==filterSeq||m.viewVersion!==viewVersion)return;self.postMessage({type:'page',seq:filterSeq,viewVersion,page:m.page,items:current.slice(m.page*60,(m.page+1)*60).map(publicRace)});
 }else if(m.type==='detail'){if(!byId.has(m.id))await archive();const race=byId.get(m.id);self.postMessage({type:race?'detail':'detail-missing',requestId:m.requestId,...(race?{race:publicRace(race)}:{})});
 }else if(m.type==='group'){const ids=new Set(m.locationIds),found=all.filter(r=>ids.has(r.locationId));self.postMessage({type:'group',requestId:m.requestId,total:found.length,items:found.slice(0,100).map(publicRace)});}
}
self.onmessage=({data:m})=>{chain=chain.then(()=>handle(m)).catch(e=>self.postMessage({type:m.background?'refresh-error':m.type==='detail'?'detail-error':e.kind==='archive'?'archive-error':'error',message:e.message}));};
