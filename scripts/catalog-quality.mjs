import { expandDataset, sourceRecords } from '../web/core.mjs';
const validDate=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
export function validateCatalog(data,{previous=null,minRetention=.7}={}) {
 const races=expandDataset(data),ids=new Set(),sources=new Set(),counts={};
 if(!races.length)throw new Error('Catalog is empty; previous data preserved');
 for(const r of races){
  if(!r.id||ids.has(r.id))throw new Error('Duplicate or missing race ID');ids.add(r.id);
  if(!r.name||(r.date!=null&&!validDate(r.date))||(r.dateEnd&&(!validDate(r.dateEnd)||r.dateEnd<r.date)))throw new Error(`Invalid name/date: ${r.id}`);
  for(const key of ['distanceKm','elevationGainM'])if(r[key]!=null&&(!Number.isFinite(r[key])||r[key]<0))throw new Error(`Invalid ${key}: ${r.id}`);
  if((r.longitude==null)!==(r.latitude==null)||(r.longitude!=null&&(!Number.isFinite(r.longitude)||!Number.isFinite(r.latitude)||Math.abs(r.longitude)>180||Math.abs(r.latitude)>90)))throw new Error(`Invalid coordinates: ${r.id}`);
  for(const [key,max] of [['endurancePoints',6],['mountainLevel',12]]){const v=r.extensions?.itra?.[key];if(v!=null&&(!Number.isInteger(v)||v<0||v>max))throw new Error(`Invalid ${key}: ${r.id}`);}
  for(const s of sourceRecords(r)){const key=s.provider+':'+s.id;if(sources.has(key))throw new Error(`Duplicate source identity: ${key}`);sources.add(key);counts[s.provider]=(counts[s.provider]||0)+1;}
 }
 if(data.coverage?.races!==races.length)throw new Error('Catalog coverage count does not match its contents');
 if(previous){const old={};for(const r of expandDataset(previous))for(const s of sourceRecords(r))old[s.provider]=(old[s.provider]||0)+1;
  for(const [provider,count]of Object.entries(old))if((counts[provider]||0)<count*minRetention)throw new Error(`${provider} count fell from ${count} to ${counts[provider]||0}; review before publishing`);
 }
 return {races:races.length,counts,unmapped:races.filter(r=>r.longitude==null).length};
}
