import { raceGrade, UTMB_COLORS } from './grades.mjs';
export { raceGrade };
export const CATEGORIES = ['20k','50k','100k','100m'];
export const COLORS = { ...UTMB_COLORS, other:'#9baaaa' };
export function fold(value) { return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(); }
export function localToday(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
export function presetDates(preset, today=localToday()) {
  const [year,month,day]=today.split('-').map(Number);
  if(preset==='2w') {const end=new Date(year,month-1,day+14,12);return {from:today,to:localToday(end)};}
  const months={'1m':1,'3m':3,'6m':6,'12m':12}[preset];
  if(!months)return {from:'',to:''};
  const end=new Date(year,month-1+months,1,12);
  const last=new Date(end.getFullYear(),end.getMonth()+1,0,12).getDate();
  end.setDate(Math.min(day,last));return {from:today,to:localToday(end)};
}
export function nextMonths(today=localToday()) {
  const [year,month]=today.split('-').map(Number);
  return Array.from({length:12},(_,i)=>localToday(new Date(year,month-1+i,1,12)).slice(0,7));
}
export function isWorldSeries(race) { return ['serie','major','finale'].includes(race.extensions?.utmb?.level); }
export function sourceRecords(race) {
  return race.sources || [{provider:race.source,id:race.sourceId,url:race.sourceUrl}];
}
// Full-marathon listings remain discoverable when providers disagree on the
// measured trail distance. Numeric matching accepts the feeds' 42–42.3 km rounding.
export function isMarathon(race) {
  if(race.extensions?.worldsmarathons?.listingType==='marathon-event')return true;
  return [race.distanceKm,...sourceRecords(race).map(s=>s.values?.distanceKm)]
    .some(km=>Number.isFinite(km)&&km>=42&&km<=42.3);
}
export function providerName(provider) {
  return provider==='worldsmarathons'?'World’s Marathons':String(provider||'').toUpperCase();
}
function searchable(race) {
  race.searchText=fold([race.name,race.eventName,race.place,race.country,race.continent,...sourceRecords(race).flatMap(s=>[s.values?.name,s.values?.eventName])].join(' '));
  return race;
}
export function combineRace(base, incoming) {
  const race={...base,sources:[...sourceRecords(base),...sourceRecords(incoming)],extensions:{...base.extensions,...incoming.extensions},conflicts:[...(base.conflicts||[])]};
  for(const field of ['name','eventName','date','distanceKm','elevationGainM','place','countryCode','country','continent','website','image','imageSource']) {
    if(race[field]==null || race[field]==='')race[field]=incoming[field];
    else if(incoming[field]!=null && incoming[field]!=='' && race[field]!==incoming[field] && ['date','distanceKm','elevationGainM'].includes(field)&&!(field==='date'&&incoming.datePrecision==='event'&&base.date>=incoming.date&&base.date<=incoming.dateEnd))race.conflicts.push({field,[base.source]:base[field],[incoming.source]:incoming[field],primaryProvider:base.source,incomingProvider:incoming.source,primaryValue:base[field],incomingValue:incoming[field]});
  }
  if(!base.date&&incoming.date)for(const field of ['dateEnd','datePrecision'])race[field]=incoming[field];
  if(race.longitude==null && incoming.longitude!=null)for(const field of ['longitude','latitude','locationId','locationPrecision','geonamesId'])race[field]=incoming[field];
  return searchable(race);
}
export function racesInView(races, locationIds, enabled=true) {
  if(!enabled || locationIds==null)return races;
  const ids=new Set(locationIds);return races.filter(r=>ids.has(r.locationId)&&r.longitude!=null);
}
export function safeUrl(value) {
  try { const u=new URL(value); return ['https:','http:'].includes(u.protocol) ? u.href : null; } catch { return null; }
}
const sourceDate=value=>{if(!value||!/^\d{4}-\d{2}-\d{2}$/.test(value)||!Number.isFinite(Date.parse(value)))return null;return new Date(value).toISOString().slice(0,10)===value?value:null;};
const measurement=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0?value:null;
const locationFields=['longitude','latitude','locationPrecision','locationId','geonamesId','countryCode','country','continent','place'];
export function correctLocation(race, corrections) {
  const correction=corrections?.[race.id];
  if(correction)for(const key of locationFields)if(Object.hasOwn(correction,key))race[key]=correction[key];
  return race;
}
export function expandDataset(data) {
  if(data.schemaVersion===3){if(!Array.isArray(data.races))throw new Error('Invalid race catalog');return data.races.map(r=>searchable(r));}
  if(![1,2].includes(data.schemaVersion)) throw new Error('Unsupported race data version');
  const races=data.records.map(row => {
    const [sourceId,ei,name,date,distanceKm,elevationGainM,category,li,website,results,level,stones]=row;
    const [eventId,eventName]=data.events[ei];
    const [place,code,lon,lat,precision,geonamesId]=data.locations[li];
    const country=data.countries[code];
    const race={id:`utmb:${sourceId}`,sourceId,source:'utmb',eventId,editionId:`${eventId}:${date?.slice(0,4) || 'unknown'}`,name:name||eventName||'Unnamed race',eventName,date:sourceDate(date),distanceKm:measurement(distanceKm),elevationGainM:measurement(elevationGainM),locationId:li,place,countryCode:code,country:country?.name || code || null,continent:country?.continent || null,longitude:lon,latitude:lat,locationPrecision:precision,geonamesId,website:safeUrl(website),image:null,sourceUrl:results ? `https://utmb.world/utmb-index/races/${encodeURIComponent(results)}` : 'https://utmb.world/utmb-index/index-races',extensions:{utmb:{category,level,stones}}};
    const enrichment=data.enrichment?.[sourceId] || {};
    race.image=safeUrl(enrichment.image);race.imageSource=safeUrl(enrichment.imageSource);
    if(enrichment.longitude!=null){race.longitude=enrichment.longitude;race.latitude=enrichment.latitude;race.locationPrecision='event';race.locationId=`event:${enrichment.longitude},${enrichment.latitude}`;}
    race.sources=[{provider:'utmb',id:sourceId,url:race.sourceUrl,fetchedAt:data.fetchedAt,values:{name,eventName,date,distanceKm,elevationGainM,place,countryCode:code}}];
    return searchable(correctLocation(race,data.locationCorrections));
  });
  const index=new Map(races.map((r,i)=>[r.id,i]));
  for(const entry of data.additionalRaces || []) {
    const race=correctLocation(structuredClone(entry.race),data.locationCorrections);
    for(const field of ['website','image','imageSource','sourceUrl'])race[field]=safeUrl(race[field]);
    race.sources=sourceRecords(race).map(s=>({...s,url:safeUrl(s.url)}));
    const position=index.get(entry.matchId);
    if(position!==undefined)races[position]=combineRace(races[position],race);
    else {if(index.has(race.id))throw new Error('Duplicate race identity');index.set(race.id,races.length);races.push(searchable(race));}
  }
  return races;
}
export function matches(race, filters, today) {
  const terms=fold(filters.q).split(/\s+/).filter(Boolean);
  if(terms.some(t=>!race.searchText.includes(t))) return false;
  if(filters.categories?.length && !filters.categories.some(c=>c==='42'?isMarathon(race):c===(race.extensions?.utmb?.category || 'other'))) return false;
  const providers=sourceRecords(race).map(s=>s.provider);
  const selectedSources=Array.isArray(filters.sources)?filters.sources:filters.source==='both'?['utmb','itra']:filters.source?[filters.source]:[];
  if(selectedSources.length && !(filters.sourceMatch==='all'||filters.source==='both'?selectedSources.every(s=>providers.includes(s)):selectedSources.some(s=>providers.includes(s))))return false;
  if(filters.worldsmarathonsSurface && (!race.extensions?.worldsmarathons||(race.extensions.worldsmarathons.surface||'unknown')!==filters.worldsmarathonsSurface))return false;
  const itra=race.extensions?.itra;
  if(filters.endurancePoints?.length && (itra?.endurancePoints==null || !filters.endurancePoints.map(Number).includes(itra.endurancePoints)))return false;
  for(const [key,test] of [['mountainMin',(v,b)=>v>=b],['mountainMax',(v,b)=>v<=b]])if(filters[key]!=='' && filters[key]!=null && (itra?.mountainLevel==null || !test(itra.mountainLevel,Number(filters[key]))))return false;
  if(filters.countries?.length && !filters.countries.includes(race.countryCode)) return false;
  const continents=Array.isArray(filters.continents)?filters.continents:filters.continent?[filters.continent]:[];
  if(continents.length && !continents.includes(race.continent)) return false;
  if(filters.worldSeries && !isWorldSeries(race)) return false;
  if(filters.when==='upcoming' && (!race.date || (race.dateEnd||race.date)<today)) return false;
  if(filters.when==='past' && (!race.date || (race.dateEnd||race.date)>=today)) return false;
  if(filters.from && (!race.date || (race.dateEnd||race.date)<filters.from)) return false;
  if(filters.to && (!race.date || race.date>filters.to)) return false;
  if(filters.months?.length && (!race.date || !filters.months.some(month=>race.date.slice(0,7)<=month&&(race.dateEnd||race.date).slice(0,7)>=month)))return false;
  for(const [field,min,max] of [['distanceKm','distanceMin','distanceMax'],['elevationGainM','elevationMin','elevationMax']]) {
    if(filters[min]!=='' && filters[min]!=null && (race[field]==null || race[field]<Number(filters[min]))) return false;
    if(filters[max]!=='' && filters[max]!=null && (race[field]==null || race[field]>Number(filters[max]))) return false;
  }
  if(filters.locationId!=null && race.locationId!==filters.locationId) return false;
  return true;
}
export function sortRaces(races, sort, today) {
  return races.sort((a,b)=> {
    if(sort==='distance') return (a.distanceKm??Infinity)-(b.distanceKm??Infinity) || a.id.localeCompare(b.id);
    if(sort==='elevation') return (b.elevationGainM??-Infinity)-(a.elevationGainM??-Infinity) || a.id.localeCompare(b.id);
    if(sort==='newest') return (b.date||'').localeCompare(a.date||'') || a.id.localeCompare(b.id);
    const ap=a.date && (a.dateEnd||a.date)>=today, bp=b.date && (b.dateEnd||b.date)>=today;
    if(ap!==bp) return ap?-1:1;
    return (ap?(a.date||'').localeCompare(b.date||''):(b.date||'').localeCompare(a.date||'')) || a.id.localeCompare(b.id);
  });
}
export function groupLocations(races) {
  const groups=new Map();
  for(const race of races) {
    if(race.longitude==null || race.latitude==null) continue;
    const key=`${race.longitude},${race.latitude}`;
    let group=groups.get(key);
    if(!group){group={key,longitude:race.longitude,latitude:race.latitude,count:0,firstId:race.id,locationIds:[],category:race.extensions?.utmb?.category,gradeCounts:{}};groups.set(key,group);}
    group.count++;
    const grade=raceGrade(race).key;group.gradeCounts[grade]=(group.gradeCounts[grade]||0)+1;
    if(!group.locationIds.includes(race.locationId)) group.locationIds.push(race.locationId);
  }
  return [...groups.values()];
}
