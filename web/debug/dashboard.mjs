const $=s=>document.querySelector(s),number=n=>new Intl.NumberFormat('en-GB').format(n||0);
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const duration=ms=>{const seconds=Math.round((ms||0)/1000);return seconds<60?`${seconds}s`:seconds<3600?`${Math.floor(seconds/60)}m ${seconds%60}s`:`${Math.floor(seconds/3600)}h ${Math.floor(seconds%3600/60)}m`;};
const date=value=>new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));
function today(){const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());return ['year','month','day'].map(type=>parts.find(p=>p.type===type).value).join('-');}
let data,controller;
// Operators are excluded from future measurements in this browser by default.
try{if(localStorage.getItem('race-atlas-usage')===null)localStorage.setItem('race-atlas-usage','off');$('#exclude-self').checked=localStorage.getItem('race-atlas-usage')==='off';}catch{}
$('#exclude-self').addEventListener('change',event=>{try{localStorage.setItem('race-atlas-usage',event.target.checked?'off':'on');}catch{}});
function preset(days){$('#to').value=today();$('#from').value=new Date(Date.parse($('#to').value)-(days-1)*86400000).toISOString().slice(0,10);document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.days)===days)));}
function renderLocations(){if(!data)return;const city=$('#location-level').value==='city',groups=new Map();for(const row of city?data.locations:data.countries){const name=city?`${row.city}, ${row.country}`:row.country,key=city?JSON.stringify([row.city,row.region,row.country]):row.country;if(!groups.has(key))groups.set(key,{name,region:city?row.region:'',sessions:0,activeMs:0});const group=groups.get(key);group.sessions+=row.sessions;group.activeMs+=row.activeMs;}
 const rows=[...groups.values()].sort((a,b)=>b.sessions-a.sessions||a.name.localeCompare(b.name));$('#place-heading').textContent=city?'City / country':'Country';
 $('#locations').innerHTML=rows.length?rows.map(row=>{const share=data.sessions?100*row.sessions/data.sessions:0;return `<tr><td>${escape(row.name)}${row.region?`<small>${escape(row.region)}</small>`:''}</td><td>${number(row.sessions)}</td><td><span class="share-bar" style="--share:${share/2}px"></span>${share.toFixed(1)}%</td><td>${duration(row.activeMs/row.sessions)}</td></tr>`;}).join(''):'<tr><td colspan="4">No location data yet.</td></tr>';
 $('#geo-note').textContent=data.geo.available?'IP locations are estimates. VPNs, mobile networks and corporate gateways can point elsewhere. Unknown locations are retained in totals.':'The local IP-location database is unavailable. Visits are still counted with an unknown location.';
}
function renderChart(){const rows=data.daily,w=1100,h=240,left=42,right=18,top=18,bottom=34,inner=w-left-right,high=Math.max(1,...rows.flatMap(r=>[r.visitors,r.sessions])),max=high<=5?5:Math.ceil(high/5)*5,step=inner/rows.length,y=value=>h-bottom-value/max*(h-bottom-top);
 const grid=Array.from({length:6},(_,i)=>{const value=i*max/5;return `<line class="grid" x1="${left}" x2="${w-right}" y1="${y(value)}" y2="${y(value)}"/><text x="${left-10}" y="${y(value)+4}" text-anchor="end">${number(value)}</text>`;}).join('');
 const bars=rows.map((r,i)=>{const x=left+i*step;return `<g><title>${date(r.day)}: ${number(r.visitors)} visitors, ${number(r.sessions)} sessions, ${duration(r.sessions?r.active_ms/r.sessions:0)} average active time</title><rect class="bar-hit" x="${x}" y="${top}" width="${step}" height="${h-bottom-top}"/><rect class="visitors" x="${x+step*.25}" y="${y(r.visitors)}" width="${Math.max(2,Math.min(28,step*.5))}" height="${y(0)-y(r.visitors)}" rx="2"/>${i%Math.max(1,Math.ceil(rows.length/7))===0||i===rows.length-1?`<text x="${x+step/2}" y="${h-9}" text-anchor="middle">${date(r.day)}</text>`:''}</g>`;}).join('');
 const line=rows.map((r,i)=>`${left+(i+.5)*step},${y(r.sessions)}`).join(' ');
 $('#chart').innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Daily estimated visitors shown as green bars, sessions as a gold line. Exact values appear in the day-by-day table.">${grid}${bars}<polyline class="sessions" points="${line}"/></svg>`;
 $('#empty').hidden=!!data.sessions;
}
function render(){
 $('#live').textContent=number(data.live);$('#today-visitors').textContent=number(data.todayVisitors);$('#today-label').textContent=date(data.today);$('#sessions').textContent=number(data.sessions);$('#avg-active').textContent=data.sessions?duration(data.activeMs/data.sessions):'—';$('#avg-span').textContent=data.sessions?duration(data.spanMs/data.sessions):'—';
 $('#daily').innerHTML=data.daily.slice().reverse().map(r=>`<tr><td>${date(r.day)}</td><td>${number(r.visitors)}</td><td>${number(r.sessions)}</td><td>${r.sessions?duration(r.active_ms/r.sessions):'—'}</td></tr>`).join('');
 $('#since').textContent=`Collection started ${new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/London'}).format(new Date(data.startedAt))} (UK time). Earlier activity is unavailable.`;
 renderChart();renderLocations();$('#loading').hidden=true;$('#report').hidden=false;
}
async function load(){controller?.abort();controller=new AbortController();$('#error').hidden=true;$('#refresh').disabled=true;try{const response=await fetch('/debug/data?'+new URLSearchParams({from:$('#from').value,to:$('#to').value}),{signal:controller.signal,cache:'no-store'});if(!response.ok)throw new Error(response.status===401||response.status===403?'Your dashboard login has expired. Reload this page to sign in.':response.status===400?'Choose a valid date range of up to 90 days.':'Traffic data could not load. Please try again.');data=await response.json();render();}catch(e){if(e.name!=='AbortError'){$('#error').textContent=e.message;$('#error').hidden=false;$('#loading').hidden=true;}}finally{$('#refresh').disabled=false;}}
document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>{preset(Number(button.dataset.days));load();}));
for(const id of ['from','to'])$('#'+id).addEventListener('change',()=>{document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed','false'));load();});
$('#refresh').addEventListener('click',load);$('#location-level').addEventListener('change',renderLocations);
$('#to').max=today();$('#from').max=today();preset(14);load();setInterval(()=>{if(!document.hidden)load();},30000);
