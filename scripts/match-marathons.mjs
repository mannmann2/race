import { fold, sourceRecords } from '../web/core.mjs';
import { evidence } from './match-sources.mjs';

const nameKey=s=>fold(s||'').replace(/(\p{L})(\d)/gu,'$1 $2').replace(/(\d)(\p{L})/gu,'$1 $2').replace(/\b(?:19|20)\d{2}\b/g,'').replace(/[^\p{L}\p{N}]+/gu,' ').trim().replace(/\s+/g,' ');
const generic=new Set('marathon marathons maratona ultramaratona maraton international the de du des la le of by and run runs race races trail trails ultra half festival challenge km k'.split(' '));
const distinctive=s=>[...new Set(nameKey(s).split(' ').filter(w=>!generic.has(w)&&!/^\d+$/.test(w)))];
const days=(a,b)=>Math.abs(Date.parse(a)-Date.parse(b))/86400000;
const end=r=>r.dateEnd>=r.date&&days(r.date,r.dateEnd)<=7?r.dateEnd:r.date;
const dateGap=(a,b)=>a.date>end(b)?days(a.date,end(b)):b.date>end(a)?days(b.date,end(a)):0;
function official(s){try{const u=new URL(s);return {host:u.hostname.replace(/^www\./,''),path:u.pathname.replace(/\/$/,'')};}catch{return null;}}
const sharedPlatform=/^(?:facebook\.com|instagram\.com|linktr\.ee|runsignup\.com|raceentry\.com|eventbrite\.[a-z.]+|worldsmarathons\.com|itra\.run|utmb\.world)$/;
function websites(a,b){
  const target=official(b.website);if(!target||sharedPlatform.test(target.host))return {host:false,exact:false};
  const sites=[a.website,...sourceRecords(a).map(s=>s.values?.website)].map(official).filter(Boolean);
  return {host:sites.some(s=>s.host===target.host),exact:!!target.path&&sites.some(s=>s.host===target.host&&s.path===target.path)};
}
function courseLabels(r){
  const values=[r,...sourceRecords(r).map(s=>s.values).filter(Boolean)];
  const labels=values.filter(v=>!(/ · .*\bkm\b/.test(v.name||'')&&v.datePrecision!=='race')).map(v=>{
    const full=nameKey(v.name),event=nameKey(v.eventName),rest=event?full.replace(event,'').trim():full;
    return rest||full;
  });
  for(const source of sourceRecords(r)){
    try{const part=new URL(source.url).pathname.match(/\/RaceDetails\/([^/]+)/i)?.[1];if(part){const full=nameKey(decodeURIComponent(part)),event=nameKey(source.values?.eventName||r.eventName);labels.push(full.replace(event,'').trim()||full);}}catch{}
  }
  return labels;
}
function nameEvidence(a,b,country=null){
  const clean=value=>country?(' '+nameKey(value)+' ').replaceAll(' '+nameKey(country)+' ',' '):value;
  const target=distinctive(clean(b.eventName)),names=[a.eventName,a.name,...sourceRecords(a).flatMap(s=>[s.values?.eventName,s.values?.name])].filter(Boolean);
  let best=0;
  for(const name of names){const tokens=distinctive(clean(name)),shared=tokens.filter(w=>target.includes(w)).length;
    if(!shared)continue;
    const smaller=Math.min(tokens.length,target.length),larger=Math.max(tokens.length,target.length);
    // A distinctive place/name may carry sponsor or translated-title decoration.
    if(shared===smaller&&(shared>=2||larger===1))best=Math.max(best,shared/larger);
  }
  return best;
}

// Match event summaries to a unique marathon course, retaining source conflicts.
// Course labels justify trail measurement differences; ambiguous courses stay separate.
export function matchMarathons(existing,incoming) {
  const candidates=new Map(),contenders=new Map(),seen=new Set(),buckets=new Map();
  for(const race of existing){const key=`${race.countryCode}:${race.date?.slice(0,4)}`;if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(race);}
  for(const race of incoming) {
    if(seen.has(race.id))throw new Error('Duplicate World’s Marathons identity');seen.add(race.id);
    const found=[];
    for(const base of buckets.get(`${race.countryCode}:${race.date?.slice(0,4)}`)||[]) {
      if(!race.countryCode||!Number.isFinite(base.distanceKm)||!Number.isFinite(race.distanceKm)||!base.date)continue;
      const gap=dateGap(base,race),difference=Math.abs(base.distanceKm-race.distanceKm);
      if(!Number.isFinite(gap)||gap>2||difference>race.distanceKm*.1)continue;
      const labels=courseLabels(base);
      // Event titles may advertise both full and half; inspect the actual course.
      if(labels.some(n=>/\b(?:half|demi|1 2|relay|relai|relais|relevos|estafeta|stafette|night|nocturne|nocturna|nocturno|nuit|team|duo|duet|stage|etapa|etappe|leg)\b/.test(n)))continue;
      const nominalMarathon=labels.some(n=>/\b(?:marathon|maraton|maratona|42(?:\s*(?:2|195))?\s*(?:k|km)|26\s*2)\b/.test(n));
      if(difference>.8&&!nominalMarathon)continue;
      let similarity=nameEvidence(base,race),countryNameDecoration=false;
      // A country suffix is presentation, provided the same marathon is independently
      // corroborated by an overlapping date, near-identical length and a nearby start.
      const mapped=[base.longitude,base.latitude,race.longitude,race.latitude].every(Number.isFinite);
      const startGapKm=mapped?111.2*Math.hypot(base.latitude-race.latitude,(base.longitude-race.longitude)*Math.cos((base.latitude+race.latitude)*Math.PI/360)):Infinity;
      if(gap===0&&difference<=.3&&nominalMarathon&&startGapKm<=1){
        const normalized=nameEvidence(base,race,race.country||base.country);
        if(normalized>similarity){similarity=normalized;countryNameDecoration=true;}
      }
      if(similarity<.5)continue;
      const ev=evidence(base,{...race,name:race.eventName+' · '+race.distanceKm+' km'}),site=websites(base,race);
      const geography=ev.place||ev.nearby||site.exact||(!mapped&&site.host&&similarity>=2/3);
      const eligible=geography&&(gap===0||nominalMarathon)&&(similarity>=2/3||site.host);
      found.push({id:base.id,name:base.name,eligible,evidence:{date:gap?'festival-course-offset':'overlapping-edition',dateGapDays:gap,distanceDifferenceKm:difference,nominalMarathon,nameSimilarity:similarity,countryNameDecoration,place:ev.place,nearby:ev.nearby,officialHost:site.host,officialPage:site.exact}});
      if(!contenders.has(base.id))contenders.set(base.id,[]);contenders.get(base.id).push(race.id);
    }
    candidates.set(race.id,found);
  }
  const accepted=[],review=[];
  const entries=incoming.map(race=>{
    const found=candidates.get(race.id),match=found.length===1&&found[0].eligible&&contenders.get(found[0].id)?.length===1?found[0]:null;
    if(match)accepted.push({sourceId:race.id,matchId:match.id,...match.evidence});
    else if(found.length)review.push({sourceId:race.id,name:race.name,reason:found.length>1?'ambiguous-course':'insufficient-corroboration',candidates:found});
    return {race,matchId:match?.id||null};
  });
  return {entries,report:{algorithm:'marathon-event-v3',imported:incoming.length,merged:accepted.length,added:incoming.length-accepted.length,unresolved:review.length,accepted,review}};
}
