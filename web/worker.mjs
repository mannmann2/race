import { expandDataset, matches, sortRaces, groupLocations, racesInView } from './core.mjs';
let races=[], all=[], current=[], byId=new Map(), filters={}, filterSeq=0, viewVersion=0, locations=null,pointKey='',points=[];
const publicRace=({searchText,...race})=>race;
function listResult(type,extra={}) {
  current=racesInView(all,locations,filters.inView);
  self.postMessage({type,seq:filterSeq,viewVersion,total:current.length,globalTotal:all.length,unmapped:all.filter(r=>r.longitude==null).length,countries:new Set(current.map(r=>r.countryCode).filter(Boolean)).size,items:current.slice(0,60).map(publicRace),page:0,...extra});
}
self.onmessage=async ({data:m})=>{
 try {
  if(m.type==='init') {
   const response=await fetch('./data/catalog.json.gz',{cache:'no-cache'});if(!response.ok)throw new Error(`Race snapshot unavailable (${response.status})`);
   const data=await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();
   races=expandDataset(data);pointKey='';points=[];byId=new Map(races.map(r=>[r.id,r]));
   const used=[...new Set(races.map(r=>r.countryCode).filter(Boolean))];
   self.postMessage({type:'ready',meta:{fetchedAt:data.fetchedAt,coverage:{...data.coverage,unmapped:races.filter(r=>r.longitude==null).length},source:data.source,sourceMeta:data.sourceMeta,mergeSummary:data.mergeSummary,countries:used.map(code=>({code,name:data.countries[code]?.name||races.find(r=>r.countryCode===code)?.country||code})).sort((a,b)=>a.name.localeCompare(b.name))}});
  } else if(m.type==='filter') {
   filters=m.filters;filterSeq=m.seq;viewVersion=m.viewVersion;locations=m.locationIds;
   all=sortRaces(races.filter(r=>matches(r,filters,m.today)),m.sort,m.today);
   const {inView,...geographicFilters}=filters,key=JSON.stringify({filters:geographicFilters,today:m.today});
   if(key!==pointKey)points=groupLocations(all);pointKey=key;
   // Every result is self-contained: an earlier response may be discarded by the UI.
   listResult('results',{points,pointKey});
  } else if(m.type==='view') {
   if(m.seq!==filterSeq)return;locations=m.locationIds;viewVersion=m.viewVersion;listResult('view');
  } else if(m.type==='page') {
   if(m.seq!==filterSeq||m.viewVersion!==viewVersion)return;
   self.postMessage({type:'page',seq:filterSeq,viewVersion,page:m.page,items:current.slice(m.page*60,(m.page+1)*60).map(publicRace)});
  } else if(m.type==='detail') {
   const race=byId.get(m.id);if(race)self.postMessage({type:'detail',requestId:m.requestId,race:publicRace(race)});
  } else if(m.type==='group') {
   const ids=new Set(m.locationIds),found=all.filter(r=>ids.has(r.locationId));
   self.postMessage({type:'group',requestId:m.requestId,total:found.length,items:found.slice(0,100).map(publicRace)});
  }
 } catch(error){self.postMessage({type:m.background?'refresh-error':'error',message:error.message});}
};
