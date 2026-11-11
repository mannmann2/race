// A lightweight daily check contacts only providers whose weekly import is due.
export function dueScripts(meta,requestState={},now=new Date()){
 const due=provider=>{const source=meta?.sourceMeta?.[provider],stamp=Date.parse(source?.fetchedAt||'');return source?.state==='unavailable'||!Number.isFinite(stamp)||now-stamp>=7*86400000;};
 const scripts=[];
 if(due('utmb'))scripts.push('refresh.py','enrich.py');
 const cooldown=Date.parse(requestState.cooldownUntil||'');
 if(due('itra')&&!(cooldown>now.getTime()))scripts.push('itra_browser.py');
 if(due('worldsmarathons'))scripts.push('worldsmarathons.py');
 return scripts;
}
