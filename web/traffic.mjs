// First-party traffic measurement. No cookies, stored visitor IDs, filters or race choices.
const preference='race-atlas-usage',endpoint='/api/traffic',idleMs=120000;
let page=crypto.randomUUID(),seq=0,activeMs=0,lastSent=0,started=false,lastTick=performance.now(),lastInput=lastTick,wasActive=false;
function permitted(){try{return localStorage.getItem(preference)!=='off'&&!navigator.globalPrivacyControl&&navigator.doNotTrack!=='1';}catch{return !navigator.globalPrivacyControl&&navigator.doNotTrack!=='1';}}
function active(now){return permitted()&&document.visibilityState==='visible'&&document.hasFocus()&&now-lastInput<idleMs;}
function account(){const now=performance.now();if(wasActive)activeMs+=Math.max(0,Math.min(now,lastInput+idleMs)-lastTick);lastTick=now;wasActive=active(now);}
function transmit(start=false){if(!permitted())return;const body=JSON.stringify({page,seq:seq++,activeMs:Math.round(activeMs),start});lastSent=activeMs;try{if(navigator.sendBeacon?.(endpoint,body))return;}catch{}fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:true,credentials:'omit'}).catch(()=>{});}
function flush(force=false,resume=false){account();if(!permitted())return;if(!started&&document.visibilityState==='visible'){started=true;transmit(true);}else if(started&&((activeMs>lastSent&&(force||activeMs-lastSent>=14000))||(resume&&active(performance.now()))))transmit();}
function reset(){page=crypto.randomUUID();seq=0;activeMs=0;lastSent=0;started=false;lastTick=performance.now();lastInput=lastTick;wasActive=active(lastTick);}
for(const name of ['pointerdown','pointermove','keydown','wheel','scroll','touchstart'])window.addEventListener(name,()=>{account();lastInput=performance.now();wasActive=active(lastInput);},{passive:true,capture:name==='scroll'});
for(const name of ['focus','blur'])window.addEventListener(name,()=>flush(true,name==='focus'));
document.addEventListener('visibilitychange',()=>flush(true,document.visibilityState==='visible'));window.addEventListener('pagehide',()=>flush(true));
window.addEventListener('pageshow',event=>{if(event.persisted){reset();flush();}});
window.addEventListener('storage',event=>{if(event.key===preference){reset();updatePreference();flush();}});
function updatePreference(){const box=document.querySelector('#usage-statistics');if(box){box.checked=permitted();box.disabled=!!navigator.globalPrivacyControl||navigator.doNotTrack==='1';}}
document.querySelector('#usage-statistics')?.addEventListener('change',event=>{try{localStorage.setItem(preference,event.target.checked?'on':'off');}catch{}reset();updatePreference();flush();});
updatePreference();reset();flush();setInterval(()=>flush(),1000);
