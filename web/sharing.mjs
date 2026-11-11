export function cameraFromURL(hash){
 const p=new URLSearchParams(hash.replace(/^#/,'')),parts=(p.get('view')||'').split(',').map(Number);
 if(parts.length!==3||parts.some(n=>!Number.isFinite(n))||Math.abs(parts[0])>180||Math.abs(parts[1])>85||parts[2]<.5||parts[2]>17)return null;
 return {center:parts.slice(0,2),zoom:parts[2]};
}
export function raceFromURL(hash){const id=new URLSearchParams(hash.replace(/^#/,'' )).get('race');return id&&/^(?:utmb:\d+|itra:\d{4}:\d+|worldsmarathons:[\w:-]+)$/.test(id)?id:null;}
export function sourceHealth(source,provider,now=new Date()){
 const threshold=provider==='utmb'?3:10,date=Date.parse(source?.fetchedAt||''),age=Number.isFinite(date)?Math.max(0,(now-date)/86400000):Infinity;
 return {stale:age>threshold,failed:source?.state==='unavailable',detailsFailed:!!source?.detailRefreshError,ageDays:Math.floor(age)};
}
