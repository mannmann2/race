import { fold } from '../web/core.mjs';

const norm=s=>fold(s).replace(/(\p{L})(\d)/gu,'$1 $2').replace(/(\d)(\p{L})/gu,'$1 $2').replace(/[^\p{L}\p{N}]+/gu,' ').trim();
const host=s=>{try{return new URL(s).hostname.replace(/^www\./,'');}catch{return '';}};
const delta=(a,b)=>a&&b?Math.abs(Date.parse(a)-Date.parse(b))/86400000:Infinity;
const close=(a,b,pct,absolute)=>Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=Math.max(absolute,Math.max(a,b)*pct);
const words=s=>new Set(norm(s).split(' ').filter(Boolean));
const overlap=(a,b)=>{const x=words(a),y=words(b);return x.size&&y.size?2*[...x].filter(t=>y.has(t)).length/(x.size+y.size):0;};
const generic=new Set('the a de del des la le les du di do da of by trail trails ultra running run race races marathon festival international edition km k m'.split(' '));
// Keep names in their original script. Strip edition decoration, not place names or sponsors.
const eventKey=s=>norm(s).replace(/\b(?:19|20)\d{2}\b/g,' ').replace(/\b\d+ (?:st|nd|rd|th)\b/g,' ').replace(/\bfive\b/g,'5').replace(/\s+/g,' ').trim();
const distinctive=s=>[...words(eventKey(s))].filter(t=>!generic.has(t)&&!/^[0-9]+$/.test(t));
function locality(r,other) {
  const parts=(r.place||'').split(',').map(s=>s.trim());
  const countries=[r.country,other.country,r.countryCode].map(norm).filter(Boolean);
  if(parts.length>1&&countries.includes(norm(parts.at(-1))))parts.pop();
  return norm(parts.join(','));
}
function eventSpan(r){const span=delta(r.date,r.dateEnd);return r.datePrecision==='event'&&r.dateEnd>=r.date&&span<=31?span:0;}
function end(r){return eventSpan(r)?r.dateEnd:r.date;}
function geography(a,b) {
  const place=!!locality(a,b)&&locality(a,b)===locality(b,a);
  const coordinates=[a.longitude,a.latitude,b.longitude,b.latitude].every(Number.isFinite);
  const dy=coordinates?(a.latitude-b.latitude)*111:Infinity;
  const dx=coordinates?(a.longitude-b.longitude)*111*Math.cos((a.latitude+b.latitude)*Math.PI/360):Infinity;
  return {place,nearby:Math.hypot(dx,dy)<30};
}
const summary=r=>r.datePrecision!=='race'&&/ · .*\bkm\b/.test(r.name||'');
function variant(r) {
  // Calendar labels contain the event name, not the actual course variant.
  const name=summary(r)?'':norm(r.name).replace(eventKey(r.eventName),' '),relay=/\b(relay|relai|relais|relevos|estafeta|stafette)\b/.test(name);
  const night=/\b(night|nocturne|nocturna|nocturno|nuit)\b/.test(name),day=/\b(day|diurne|diurna|diurno)\b/.test(name);
  const leg=name.match(/\b(?:relay|relai|relais|leg|stage|etapa|etappe|day) (\d+)(?: (?:of|de) (\d+))?\b/);
  return {stage:/\bmulti stage\b/.test(name)?'multi':/\bsingle stage\b/.test(name)?'single':'',relay,time:night?'night':day&&!leg?'day':'',leg:leg?leg.slice(1).filter(Boolean).join('/'):'',team:/\b(team|duo|duet)\b/.test(name),solo:/\bsolo\b/.test(name)};
}
function variants(a,b) {
  const x=variant(a),y=variant(b),unknown=summary(a)||summary(b);
  const explicitConflict=(x.stage&&y.stage&&x.stage!==y.stage)||(x.leg&&y.leg&&x.leg!==y.leg)||(x.time&&y.time&&x.time!==y.time)||(x.team&&y.solo)||(y.team&&x.solo);
  const different=x.stage!==y.stage||x.relay!==y.relay||x.time!==y.time||x.leg!==y.leg||x.team!==y.team;
  return {variantConflict:!!explicitConflict||(!unknown&&different),variantUnknown:unknown&&different};
}
function course(r) {
  const event=words(r.eventName);
  return norm(r.name).split(' ').filter(t=>!event.has(t)&&!/^\d+$/.test(t)&&!generic.has(t)).sort().join(' ');
}
export function evidence(a,b) {
  const event=!!eventKey(a.eventName)&&eventKey(a.eventName)===eventKey(b.eventName);
  const sameName=!!norm(a.name)&&norm(a.name)===norm(b.name),days=delta(a.date,b.date);
  const withinEvent=!!eventSpan(b)&&a.date>=b.date&&a.date<=b.dateEnd;
  const validDate=b.datePrecision==='event'?withinEvent:days<=2;
  const distance=close(a.distanceKm,b.distanceKm,.02,.5),distanceCompatible=close(a.distanceKm,b.distanceKm,.08,.5);
  const gain=close(a.elevationGainM,b.elevationGainM,.1,100),gainCompatible=close(a.elevationGainM,b.elevationGainM,.2,100);
  const sameCourse=!!course(a)&&course(a)===course(b);
  const website=!!host(a.website)&&host(a.website)===host(b.website);
  const variant=variants(a,b);
  const candidate=!!a.countryCode&&a.countryCode===b.countryCode&&a.date?.slice(0,4)===b.date?.slice(0,4)&&validDate&&distanceCompatible&&!variant.variantConflict&&
    (sameName||a.elevationGainM==null||b.elevationGainM==null||close(a.elevationGainM,b.elevationGainM,.4,200));
  return {candidate,days,withinEvent,event,sameName,...geography(a,b),distance,distanceCompatible,gain,gainCompatible,sameCourse,website,...variant};
}

// Provider event IDs are not interchangeable: UTMB often uses one ID per course,
// while ITRA calendar fragments can use different representative course IDs.
// A bounded date cluster prevents annual or weekly editions becoming one event.
function editions(races) {
  const buckets=new Map(),groups=[];
  for(const race of races) {
    if(!race.date||!Number.isFinite(Date.parse(race.date))||!race.countryCode||!eventKey(race.eventName))continue;
    const key=`${race.countryCode}|${race.date.slice(0,4)}|${eventKey(race.eventName)}`;
    if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(race);
  }
  for(const [key,rows] of buckets) {
    let group;
    for(const race of rows.sort((a,b)=>a.date.localeCompare(b.date)||a.id.localeCompare(b.id))) {
      if(!group||delta(race.date,group.from)>6) {
        group={id:`${key}|${race.date}`,name:race.eventName,country:race.countryCode,year:race.date.slice(0,4),from:race.date,to:end(race),races:[]};groups.push(group);
      }
      group.races.push(race);if(end(race)>group.to)group.to=end(race);
    }
  }
  return groups;
}
function editionEvidence(a,b,separate) {
  const gap=a.from>b.to?delta(a.from,b.to):b.from>a.to?delta(b.from,a.to):0;
  if(a.country!==b.country||a.year!==b.year||gap>2)return null;
  const exact=eventKey(a.name)===eventKey(b.name),x=distinctive(a.name),y=distinctive(b.name),shared=x.filter(t=>y.includes(t));
  const nameCompatible=exact&&(x.length>0||/\d/.test(eventKey(a.name)))||shared.length>=1&&(overlap(eventKey(a.name),eventKey(b.name))>=.8||shared.length===Math.min(x.length,y.length));
  if(!nameCompatible)return null;
  const pairs=[];
  for(const r of b.races)for(const u of a.races) {
    if(separate.has(`${r.id}|${u.id}`))continue;
    const e=evidence(u,r);if(e.candidate)pairs.push({itraId:r.id,utmbId:u.id,...e});
  }
  // Count mutually unique distance/name anchors, never the cartesian product of
  // several similarly sized courses. Unlabelled bulk summaries need gain data.
  const anchors=pairs.filter(p=>(p.sameName&&!summary(b.races.find(r=>r.id===p.itraId)))||(p.distance&&p.gainCompatible));
  const unique=anchors.filter(p=>anchors.filter(q=>q.itraId===p.itraId).length===1&&anchors.filter(q=>q.utmbId===p.utmbId).length===1);
  const geo=unique.some(p=>p.place||p.nearby),named=unique.some(p=>p.sameName&&distinctive(b.races.find(r=>r.id===p.itraId).name).length>0&&!summary(b.races.find(r=>r.id===p.itraId))); 
  const linked=unique.length>0&&(exact?(geo||named||unique.length>=2):(shared.length>=2?(geo||unique.length>=2):(geo&&(named||unique.length>=2))));
  return {utmbEdition:a.id,itraEdition:b.id,utmbName:a.name,itraName:b.name,exact,anchors:unique.length,geography:geo,linked,pairs};
}

// Matching runs at refresh time; browser filtering never performs fuzzy matching.
export function matchSources(utmb,itra,overrides={match:{},separate:[]}) {
  const byId=new Map(utmb.map(r=>[r.id,r])),itraById=new Map();
  for(const r of itra){if(itraById.has(r.id))throw new Error(`Duplicate ITRA id: ${r.id}`);itraById.set(r.id,r);}
  const separate=new Set((overrides.separate||[]).map(pair=>pair.join('|'))),assigned=new Map(),claimed=new Set(),review=[],staleOverrides=[],accepted=[];
  for(const [iid,uid] of Object.entries(overrides.match||{})) {
    const a=byId.get(uid),b=itraById.get(iid);
    if(!a||!b){staleOverrides.push({itraId:iid,utmbId:uid});continue;}
    if(a.date?.slice(0,4)!==b.date?.slice(0,4)||claimed.has(uid)||separate.has(`${iid}|${uid}`))throw new Error(`Conflicting match override: ${iid} → ${uid}`);
    assigned.set(iid,uid);claimed.add(uid);accepted.push({itraId:iid,utmbId:uid,reason:'reviewed-override'});
  }
  const groups=editions(utmb),incoming=editions(itra),buckets=new Map(),links=[];
  for(const group of groups){const key=`${group.country}:${group.year}`;if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(group);}
  for(const b of incoming)for(const a of buckets.get(`${b.country}:${b.year}`)||[]) {
    const e=editionEvidence(a,b,separate);if(e?.pairs.length)links.push(e);
  }
  const eligible=links.filter(e=>e.linked),eventLinks=eligible.filter(e=>eligible.filter(q=>q.itraEdition===e.itraEdition).length===1&&eligible.filter(q=>q.utmbEdition===e.utmbEdition).length===1);
  const certainEvents=new Set(eventLinks),candidates=new Map();
  for(const link of links)for(const pair of link.pairs) {
    const race=itraById.get(pair.itraId);
    // Named, measured courses can differ by rounding, elevation methodology or
    // one day's start date. Calendar-only labels require matching measurements.
    const certain=certainEvents.has(link)&&!pair.variantUnknown&&(
      (race.datePrecision==='race'&&pair.sameName)||
      (pair.gainCompatible&&(pair.distance||pair.sameCourse||link.anchors>=2))
    );
    const c={...pair,certain,utmbEdition:link.utmbEdition,itraEdition:link.itraEdition,eventExact:link.exact,eventAnchors:link.anchors,eventLinked:certainEvents.has(link)};
    if(!candidates.has(pair.itraId))candidates.set(pair.itraId,[]);candidates.get(pair.itraId).push(c);
  }
  // Evaluate all plausible courses in both directions, including weaker and
  // already claimed alternatives. Do not force a leftover match after assigning
  // another course: that would conceal ambiguity in same-distance variants.
  const contenders=new Map();
  for(const found of candidates.values())for(const c of found.filter(c=>c.eventLinked)) {
    if(!contenders.has(c.utmbId))contenders.set(c.utmbId,new Set());contenders.get(c.utmbId).add(c.itraId);
  }
  for(const r of itra) {
    if(assigned.has(r.id))continue;
    const found=candidates.get(r.id)||[],plausible=found.filter(c=>c.eventLinked),c=plausible[0];
    if(plausible.length===1&&c.certain&&contenders.get(c.utmbId)?.size===1&&!claimed.has(c.utmbId)) {
      assigned.set(r.id,c.utmbId);claimed.add(c.utmbId);accepted.push({...c,reason:'edition-and-course'});
    } else if(found.length)review.push({itraId:r.id,name:r.name,date:r.date,candidates:found});
  }
  return {entries:itra.map(race=>({race,matchId:assigned.get(race.id)||null})),report:{algorithm:'edition-course-v2',imported:itra.length,merged:assigned.size,added:itra.length-assigned.size,unresolved:review.length,accepted,eventLinks:eventLinks.map(({pairs,...link})=>link),review,staleOverrides}};
}
