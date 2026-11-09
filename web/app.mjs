import { localToday, safeUrl, presetDates, isWorldSeries, sourceRecords, providerName, raceGrade } from './core.mjs';
import { raceGrades } from './grades.mjs';
import { cameraFromURL, raceFromURL, sourceHealth } from './sharing.mjs';
import { Globe } from './globe.mjs';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const number=n=>new Intl.NumberFormat('en-GB',{maximumFractionDigits:1}).format(n);
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const displayDate=(value,long=false)=>value?new Intl.DateTimeFormat('en-GB',{day:'numeric',month:long?'long':'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z')):'Date unavailable';
const defaults=()=>({q:'',when:'upcoming',datePreset:'6m',...presetDates('6m'),categories:[],countries:[],source:'',worldsmarathonsSurface:'',endurancePoints:[],mountainMin:'',mountainMax:'',continent:'',distanceMin:'',distanceMax:'',elevationMin:'',elevationMax:'',worldSeries:false,inView:true,locationId:null});
let filters=defaults(),seq=0,viewVersion=0,ready=false,page=0,total=0,pending=false,meta,hoverRequest=0,currentHover=null,hoverTimer,filterTimer,groupRequest=0,detailRequest=0,visibleRaces=new Map(),viewTimer,locationIds=null,lastViewKey='',globePointKey=null,collapsed=false,hoveredRaceId=null,focusedRaceId=null;
let selectedRaceId=raceFromURL(location.hash),sharedCamera=cameraFromURL(location.hash),deepLinkPending=!!selectedRaceId,panelReturnTarget=null,toastTimer,dialogReturnTarget=null;
let activeGroup=null;
const failedImages=new Set();
const worker=new Worker(new URL('./worker.mjs',import.meta.url),{type:'module'}),form=$('#filters-form');
const pinIcon='<svg viewBox="0 0 16 18" aria-hidden="true"><path d="M14 7c0 4-6 9-6 9S2 11 2 7a6 6 0 1 1 12 0Z"/><circle cx="8" cy="7" r="2"/></svg>';
function categoryBadge(r){
 const grade=raceGrade(r),series=isWorldSeries(r)?'<b class="series-badge">◆ WORLD SERIES</b>':'';
 if(grade.icon)return `<span class="category-badge" data-grade="${grade.key}"><span class="grade-badges">${raceGrades(r).map(b=>`<img class="grade-icon grade-icon-${b.provider}" src="${b.icon}" alt="${b.label}" width="${b.provider==='utmb'?78:45}" height="26" decoding="async">`).join('')}</span>${series}</span>`;
 return `<span class="category-badge category-badge-ungraded" data-grade="other"><span class="grade-sources">${sourceRecords(r).map(source=>`<span class="grade-source">${escape(providerName(source.provider))}</span>`).join('')}</span><span class="grade-status"><i class="dot" style="--category-color:${grade.color}"></i>No grade supplied</span>${series}</span>`;
}
function ratingBadges(r){const level=r.extensions?.itra?.mountainLevel;return level!=null?`<div class="source-badges"><span class="rating-badge">Mountain ${number(level)}/12</span></div>`:'';}

function sourceProvenance(r){return sourceRecords(r).map(s=>`${escape(providerName(s.provider))} · ${escape(s.id)}${s.acquisition==='public-index'?` · Indexed copy, retrieved ${escape(displayDate(s.retrievedAt.slice(0,10)))}${s.indexAge?`<br>Index reported this copy as ${escape(s.indexAge)} at retrieval.`:''}`:s.fetchedAt?' · '+escape(displayDate(s.fetchedAt.slice(0,10)))+(s.detailsFetchedAt?' · Course details '+escape(displayDate(s.detailsFetchedAt.slice(0,10))):''):''}`).join('<br>');}
function sourceLinks(r){return sourceRecords(r).filter(s=>safeUrl(s.url)).map(s=>`<a class="secondary" href="${escape(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">View on ${escape(providerName(s.provider))} ↗</a>`).join('');}
function ratingDetails(r){const i=r.extensions?.itra;if(!i)return '';return `<dl class="detail-grid itra-details"><div><dt>ITRA Endurance Points</dt><dd>${i.endurancePoints==null?'Not supplied':number(i.endurancePoints)+' / 6'}</dd></div><div><dt>ITRA Mountain Level</dt><dd>${i.mountainLevel==null?'Not supplied':number(i.mountainLevel)+' / 12'}</dd></div>${i.finisherLevel!=null?`<div><dt>ITRA Finisher Level</dt><dd>${number(i.finisherLevel)}</dd></div>`:''}</dl>`;}
function conflictNote(r){return r.conflicts?.length?`<div class="source-conflicts"><strong>Sources report different course details</strong>${r.conflicts.map(c=>`<p>${escape({date:'Date',distanceKm:'Distance (km)',elevationGainM:'Elevation gain (m)'}[c.field])}: ${escape(providerName(c.primaryProvider||'utmb'))} ${escape(c.primaryValue??c.utmb)} · ${escape(providerName(c.incomingProvider||'itra'))} ${escape(c.incomingValue??c.itra)}</p>`).join('')}<small>${escape(providerName(r.source))} values are shown above. Check the linked listings before making plans.</small></div>`:'';}
function photo(r,className,loading='lazy'){return r.image&&!failedImages.has(r.image)?`<img class="${className}" src="${escape(r.image)}" alt="${escape(r.eventName)}" loading="${loading}" decoding="async" referrerpolicy="no-referrer">`:'';}
const raceDate=(r,long=false)=>displayDate(r.date,long)+(r.dateEnd&&r.dateEnd!==r.date?' – '+displayDate(r.dateEnd,long):'');
function card(r){const grade=raceGrade(r);return `<button data-grade="${grade.key}" style="--race-grade-color:${grade.color}" class="race-card${r.image?' has-photo':''}" data-race="${escape(r.id)}">${photo(r,'race-photo')}`+
 `<div class="race-card-top">${categoryBadge(r)}<time datetime="${escape(r.date||'')}">${escape(raceDate(r))}</time></div>`+
 `${ratingBadges(r)}<h3>${escape(r.name)}</h3>${r.eventName!==r.name?`<p class="event-name">${escape(r.eventName)}</p>`:''}`+
 `<p class="race-place">${pinIcon}${escape(r.place||r.country||'Location not supplied')}</p>`+
 `<div class="race-card-stats"><span>${r.distanceKm==null?'—':number(r.distanceKm)} <small>km</small></span><span>↗ ${r.elevationGainM==null?'—':number(r.elevationGainM)} <small>m D+</small></span></div>`+
 `${r.longitude==null?'<span class="unmapped-label">Location unavailable on globe</span>':''}<span class="card-arrow" aria-hidden="true">↗</span></button>`;}
function renderCards(items,append=false){if(!append){hoveredRaceId=null;focusedRaceId=null;globe.highlight(null);}for(const r of items)visibleRaces.set(r.id,r);if(append)$('#races').insertAdjacentHTML('beforeend',items.map(card).join(''));else $('#races').innerHTML=items.map(card).join('');}
function updatePanelToggle(){const open=matchMedia('(max-width:800px)').matches?$('#race-results').classList.contains('open'):!collapsed;const button=$('#results-toggle');button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-label',open?'Hide race calendar':'Show race calendar');button.title=open?'Hide race calendar':'Show race calendar';}
function closePanels(){$('#filters-panel').classList.remove('open');$('#race-results').classList.remove('open');$('#open-filters').setAttribute('aria-expanded','false');$('#show-list').setAttribute('aria-expanded','false');updatePanelToggle();syncPanelAccessibility();}
function showError(message){ready=false;$('#races').innerHTML=`<div class="error-state"><strong>The world is taking a moment.</strong><p>${escape(message)}</p><button id="retry">Try again</button></div>`;$('#result-caption').textContent='Race data unavailable';$('#load-more').hidden=true;}
function activeCount(){return Object.entries(filters).filter(([k,v])=>!['locationId','inView','datePreset','from','to'].includes(k)&&(Array.isArray(v)?v.length:typeof v==='boolean'?v:k==='when'?v!=='all':v!=='')).length+(filters.from||filters.to?1:0);}
function valid(){const dates=!!(filters.from&&filters.to&&filters.from>filters.to);let range=false;for(const prefix of ['distance','elevation','mountain']){const a=filters[prefix+'Min'],b=filters[prefix+'Max'];if((a!==''&&(!Number.isFinite(Number(a))||Number(a)<0))||(b!==''&&(!Number.isFinite(Number(b))||Number(b)<0))||(a!==''&&b!==''&&Number(a)>Number(b)))range=true;}if(['mountainMin','mountainMax'].some(k=>filters[k]!==''&&(!Number.isInteger(Number(filters[k]))||Number(filters[k])>12)))range=true;$('#date-error').hidden=!dates;$('#range-error').hidden=!range;return !dates&&!range;}
function writeURL(){const p=new URLSearchParams();for(const [k,v]of Object.entries(filters)){if(k==='locationId')continue;if(Array.isArray(v)){if(v.length)p.set(k,v.join(','));}else if(typeof v==='boolean')p.set(k,v?'1':'0');else if(v)p.set(k,v);}if($('#sort').value!=='soonest')p.set('sort',$('#sort').value);const map=globe?.ready?globe.map:null;if(map){const c=map.getCenter();p.set('view',[c.lng.toFixed(4),c.lat.toFixed(4),map.getZoom().toFixed(2)].join(','));}else if(sharedCamera)p.set('view',[...sharedCamera.center,sharedCamera.zoom].join(','));if(selectedRaceId)p.set('race',selectedRaceId);history.replaceState(null,'',location.pathname+location.search+'#'+p.toString());}
function updateSlider(){const low=Math.min(500,Number(filters.distanceMin)||0),high=filters.distanceMax===''?500:Math.min(500,Number(filters.distanceMax));$('#distance-low').value=low;$('#distance-high').value=high;$('#slider-fill').style.left=`${low/5}%`;$('#slider-fill').style.right=`${100-high/5}%`;$('#distance-readout').textContent=`${filters.distanceMin||0} – ${filters.distanceMax||'Any'} km`;$('#distance-low').setAttribute('aria-valuetext',`${filters.distanceMin||0} kilometres`);$('#distance-high').setAttribute('aria-valuetext',filters.distanceMax?`${filters.distanceMax} kilometres`:'No maximum distance');}
function updateFilterUI(){
 for(const el of form.elements)if(el.name&&el.name!=='country'&&filters[el.name]!=null)el.value=filters[el.name];
 $$('[data-when]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.when===filters.when)));
 $$('[data-date]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.date===filters.datePreset)));
 $$('[data-endurance]').forEach(b=>b.setAttribute('aria-pressed',String(filters.endurancePoints.includes(b.dataset.endurance))));
 $$('[data-category]').forEach(b=>b.setAttribute('aria-pressed',String(filters.categories.includes(b.dataset.category))));
 $$('#country-options input').forEach(el=>el.checked=filters.countries.includes(el.value));
 $('#country-summary').textContent=filters.countries.length?`${filters.countries.length} countr${filters.countries.length===1?'y':'ies'} selected`:'All countries';
 $('#world-series').setAttribute('aria-pressed',String(filters.worldSeries));$('#in-view').checked=filters.inView;
 const count=activeCount();$('#active-count').textContent=count?`${count} active`:'No filters';$('#mobile-active').textContent=count?`(${count})`:'';$('#clear-location').hidden=filters.locationId==null;updateSlider();
}
function syncView(){
 clearTimeout(viewTimer);viewTimer=null;if(!ready||!globe.ready)return;
 $('.globe-panel').classList.toggle('is-zoomed',globe.map.getZoom()>3);
 const ids=globe.visibleLocationIds(),key=ids?.slice().sort().join('|')||'';
 if(key===lastViewKey)return;locationIds=ids;lastViewKey=key;
 if(!filters.inView)return;
 viewVersion++;worker.postMessage({type:'view',seq,viewVersion,locationIds});
}
function scheduleView(immediate=false){if(immediate){syncView();return;}if(!viewTimer)viewTimer=setTimeout(syncView,100);}
function runFilters(){
 clearTimeout(filterTimer);clearHover();updateFilterUI();if(!valid())return;writeURL();if(!ready)return;
 seq++;page=0;pending=true;$('#load-more').hidden=true;$('#result-caption').textContent='Finding races…';$('#races').setAttribute('aria-busy','true');
 worker.postMessage({type:'filter',seq,viewVersion,filters,today:localToday(),sort:$('#sort').value,locationIds});
}
function setFilter(key,value,immediate=true){filters[key]=value;clearTimeout(filterTimer);if(immediate)runFilters();else filterTimer=setTimeout(runFilters,100);}
function restoreURL(){
 const p=new URLSearchParams(location.hash.slice(1));filters=defaults();selectedRaceId=raceFromURL(location.hash);sharedCamera=cameraFromURL(location.hash);
 for(const key of Object.keys(filters)){if(key==='locationId'||!p.has(key))continue;const v=p.get(key).slice(0,400);if(['categories','countries','endurancePoints'].includes(key))filters[key]=v.split(',').filter(Boolean);else if(['worldSeries','inView'].includes(key))filters[key]=v==='1';else filters[key]=v;}
 if(!['all','upcoming','past'].includes(filters.when))filters.when='upcoming';
 filters.endurancePoints=filters.endurancePoints.filter(v=>/^[0-6]$/.test(v));if(!['','utmb','itra','both','worldsmarathons'].includes(filters.source))filters.source='';
 if(!['','road','trail','mixed','other','unknown'].includes(filters.worldsmarathonsSurface))filters.worldsmarathonsSurface='';
 filters.categories=filters.categories.filter(c=>['20k','42','50k','100k','100m','other'].includes(c));
 if(p.has('datePreset')&&filters.datePreset!=='any')Object.assign(filters,presetDates(filters.datePreset));
 else if(p.has('from')||p.has('to')||filters.when!=='upcoming'){if(!p.has('datePreset'))filters.datePreset='';if(!p.has('from'))filters.from='';if(!p.has('to'))filters.to='';}
 if(filters.datePreset==='any')Object.assign(filters,{from:'',to:''});
 const sort=p.get('sort');$('#sort').value=['soonest','newest','distance','elevation'].includes(sort)?sort:'soonest';updateFilterUI();
}
function reset(){filters=defaults();$('#sort').value='soonest';$('#country-search').value='';$$('#country-options label').forEach(e=>e.hidden=false);runFilters();}
function handleResults(m){
 if(m.seq!==seq)return;
 if(m.type==='results'&&m.points&&m.pointKey!==globePointKey){globePointKey=m.pointKey;globe.setPoints(m.points);lastViewKey='';scheduleView(true);}
 if(m.viewVersion!==viewVersion)return;
 pending=false;page=0;total=m.total;$('#races').setAttribute('aria-busy','false');visibleRaces.clear();
 for(const id of ['result-count','globe-count','mobile-count','mobile-list-count'])$('#'+id).textContent=number(total);
 $('#result-caption').textContent=filters.inView?`${number(total)} in view · ${number(m.globalTotal)} worldwide`:`${number(m.countries)} countries · ${number(m.globalTotal)} worldwide`;
 $('#globe-count-label').textContent=filters.inView?'races in this view':'races worldwide';
 $('#location-note').hidden=!m.unmapped;$('#location-note').textContent=filters.inView?`${number(m.unmapped)} matches have no mapped location. Turn off “Only races in map view” to include them.`:`${number(m.unmapped)} matches have no mapped location and are listed here.`;
 renderCards(m.items);$('#load-more').hidden=m.items.length>=total;$('#load-more').disabled=false;
 if(!total)$('#races').innerHTML=`<div class="empty-state"><strong>${filters.inView?'No starting lines in this view.':'No matching starting lines.'}</strong><p>${filters.inView?'Move the globe, zoom out, or browse worldwide.':'Try a wider date range or loosen a filter.'}</p>${filters.inView?'<button id="show-worldwide">Browse worldwide</button>':''}<button id="empty-reset">Reset filters</button></div>`;
}
function detail(r){
 $('#detail-back').hidden=!activeGroup;
 clearHover();selectedRaceId=r.id;writeURL();globe.focus(r);globe.highlight(r);const site=safeUrl(r.website),grade=raceGrade(r);
 $('#detail-content').style.setProperty('--race-grade-color',grade.color);$('#detail-content').dataset.grade=grade.key;
 $('#detail-content').innerHTML=`${photo(r,'detail-image','eager')}<div class="detail-top"><div class="detail-grade">${categoryBadge(r)}<span>${escape(raceGrades(r).length>1?'UTMB + ITRA grades':grade.provider==='utmb'?'UTMB category':grade.provider==='itra'?'ITRA Endurance Points':'Race classification')}</span></div><span class="eyebrow">THE NEXT STARTING LINE</span><h2>${escape(r.name)}</h2><p>${escape(r.eventName)}</p></div><div class="detail-body"><dl class="detail-grid"><div><dt>Race date</dt><dd>${escape(raceDate(r,true))}</dd></div><div><dt>${raceGrades(r).length>1?'Grades':grade.provider==='utmb'?'UTMB category':grade.provider==='itra'?'ITRA Endurance Points':'Race type'}</dt><dd>${categoryBadge(r)}</dd></div><div><dt>Distance</dt><dd>${r.distanceKm==null?'Not supplied':number(r.distanceKm)+' km'}</dd></div><div><dt>Elevation gain</dt><dd>${r.elevationGainM==null?'Not supplied':number(r.elevationGainM)+' m D+'}</dd></div></dl>${ratingDetails(r)}${conflictNote(r)}${r.extensions?.worldsmarathons&&!r.extensions?.utmb&&!r.extensions?.itra?'<p class="small-note">Marathon distance and dates come from the event listing. Check the organiser for the exact course and start time.</p>':r.datePrecision==='event'?'<p class="small-note">Date is from the event calendar; the course start date is not confirmed.</p>':''}<div class="detail-place">${escape(r.place||r.country||'Location not supplied')}<small>${r.longitude==null?'No reliable location match. See the organiser’s website for the start.':`Approximate ${r.locationPrecision==='event'?'event':'town'} location · ${r.latitude.toFixed(4)}°, ${r.longitude.toFixed(4)}°<br>${r.locationPrecision==='event'?'Location supplied by the event catalogue':'Town name match from GeoNames'}; not a verified starting line.`}</small></div><div class="detail-actions"><button type="button" data-share-race>Share race ↗</button><a href="${escape(reportURL(r))}" target="_blank" rel="noopener noreferrer">Report a correction ↗</a></div><div class="detail-links">${site?`<a href="${escape(site)}" target="_blank" rel="noopener noreferrer">Visit race website ↗</a>`:''}${sourceLinks(r)}</div><p class="detail-source">${sourceProvenance(r)}${r.imageSource?`<br>Photo: <a href="${escape(r.imageSource)}" target="_blank" rel="noopener noreferrer">image source ↗</a>`:''}<br>Check race details with the organiser before making plans.</p></div>`;
 const dialog=$('#detail-dialog');const title=$('#detail-content h2');title.id='race-title';dialog.setAttribute('aria-labelledby','race-title');if(!dialog.open){dialogReturnTarget=document.activeElement;dialog.showModal();}dialog.scrollTop=0;
}
function openRace(id,{fromGroup=false}={}){
 if(fromGroup&&activeGroup){activeGroup.scrollTop=$('#detail-dialog').scrollTop;activeGroup.focusId=id;}
 else activeGroup=null;
 const r=visibleRaces.get(id);if(r)detail(r);else worker.postMessage({type:'detail',id,requestId:++detailRequest});}
function clearHover(){clearTimeout(hoverTimer);hoverRequest++;currentHover=null;$('#tooltip').hidden=true;}
function hover(point,pos){
 if(!point){clearHover();return;}if(matchMedia('(max-width:800px)').matches)return;
 const box=$('#tooltip'),bounds=$('#globe-container').getBoundingClientRect();box.style.left=`${Math.max(12,Math.min(pos.x+18,bounds.width-272))}px`;box.style.top=`${Math.max(12,Math.min(pos.y-15,bounds.height-330))}px`;
 if(currentHover===point)return;currentHover=point;box.hidden=true;clearTimeout(hoverTimer);const requestId=++hoverRequest;
 hoverTimer=setTimeout(()=>worker.postMessage({type:'group',locationIds:point.locationIds,requestId:`hover:${requestId}`}),60);
}
function selectPoint(point){clearHover();worker.postMessage({type:'group',locationIds:point.locationIds,requestId:`select:${++groupRequest}`});}
function groupCard(r){
 const site=safeUrl(r.website),grade=raceGrade(r);
 return `<article class="group-race" style="--race-grade-color:${grade.color}">${card(r)}<div class="group-race-links" aria-label="Race pages for ${escape(r.name)}">${site?`<a href="${escape(site)}" target="_blank" rel="noopener noreferrer">Race website ↗</a>`:''}${sourceLinks(r)}</div></article>`;
}
function showGroup(m,{restore=false}={}){
 if(m.items.length===1){activeGroup=null;detail(m.items[0]);return;}
 if(!restore){const map=globe.ready?globe.map:null;activeGroup={response:m,scrollTop:0,focusId:null,camera:map?{center:map.getCenter().toArray(),zoom:map.getZoom(),bearing:map.getBearing(),pitch:map.getPitch()}:null};}
 selectedRaceId=null;writeURL();$('#detail-back').hidden=true;
 $('#detail-content').style.removeProperty('--race-grade-color');delete $('#detail-content').dataset.grade;
 for(const r of m.items)visibleRaces.set(r.id,r);
 const places=[...new Set(m.items.map(r=>r.place).filter(Boolean))];
 $('#detail-content').innerHTML=`<div class="group-dialog-title"><span class="eyebrow">RACES IN THIS AREA</span><h2>${escape(places.length===1?places[0]:'More than one starting line.')}</h2><p>${number(m.total)} matching races.</p></div><div class="details-group-list">${m.items.map(groupCard).join('')}</div>${m.total>100?'<p class="small-note" style="padding:18px 28px">Showing the first 100. Narrow your dates to explore more.</p>':''}`;
 const dialog=$('#detail-dialog');$('#detail-content h2').id='race-title';dialog.setAttribute('aria-labelledby','race-title');
 if(!dialog.open){dialogReturnTarget=document.activeElement;dialog.showModal();}
 dialog.scrollTop=restore?activeGroup.scrollTop:0;
 if(restore){const target=[...dialog.querySelectorAll('[data-race]')].find(el=>el.dataset.race===activeGroup.focusId);target?.focus({preventScroll:true});}
}
function backToGroup(){
 if(!activeGroup)return;
 detailRequest++;clearHover();globe.highlight(null);
 if(activeGroup.camera&&globe.ready){globe.map.stop();globe.map.jumpTo(activeGroup.camera);}
 showGroup(activeGroup.response,{restore:true});
}

const globe=new Globe($('#globe'),{onHover:hover,onSelect:selectPoint,onMove:immediate=>{scheduleView(immediate);if(immediate&&ready)writeURL();}});
document.addEventListener('themechange',e=>globe.setTheme(e.detail));
globe.load().then(()=>{if(sharedCamera)globe.map.jumpTo(sharedCamera);}).catch(error=>{const notice=document.createElement('div');notice.className='error-banner';notice.textContent='The detailed map could not load. You can still browse races worldwide.';$('.globe-panel').append(notice);filters.inView=false;runFilters();console.warn(error.message);});
worker.onmessage=({data:m})=>{
 if(m.type==='ready'){
   ready=true;globePointKey=null;meta=m.meta;$('#snapshot-label').textContent=`${['utmb','itra','worldsmarathons'].filter(p=>p==='utmb'||meta.sourceMeta?.[p]?.races).map(p=>{const stamp=meta.sourceMeta?.[p]?.fetchedAt||(p==='utmb'?meta.fetchedAt:null);return `${p==='worldsmarathons'?'Marathons':providerName(p)} ${stamp?displayDate(stamp.slice(0,10)):'date unavailable'}`;}).join(' · ')}`;
   const itra=meta.sourceMeta?.itra;$('#itra-status').textContent=itra?.races?`${number(itra.races)} ITRA courses · ${number(meta.mergeSummary?.merged||0)} matched with UTMB. ${itra.acquisition==='public-index'?`Selected indexed listings; live refresh unavailable. ${number(itra.coverage?.rated||0)} have Endurance Points; ${number(itra.coverage?.mountainRated||0)} have Mountain Level.`:itra.state==='unavailable'?'Refresh unavailable; showing the last saved data.':itra.coverage?.completeness==='calendar-count-verified'?`Rolling 12-month calendar · Updated ${displayDate(itra.fetchedAt.slice(0,10))}. ${number(itra.coverage.rated)} have Endurance Points; ${number(itra.coverage.mountainRated)} have Mountain Level.`:'Partial calendar coverage.'}`:'ITRA data is not available yet. UTMB races are ready to browse.';
   const wm=meta.sourceMeta?.worldsmarathons;$('#worldsmarathons-status').hidden=!wm?.races;
   $('#worldsmarathons-status').textContent=wm?.races?`${number(wm.races)} World’s Marathons listings · ${number(wm.mergeSummary?.merged||0)} matched. ${wm.state==='unavailable'?'Refresh unavailable; showing saved data.':`Updated ${displayDate(wm.fetchedAt.slice(0,10))} · Refreshes weekly.`}`:'';
   $('#country-options').innerHTML=meta.countries.map(c=>`<label><input type="checkbox" name="country" value="${escape(c.code)}">${escape(c.name)}</label>`).join('');
   $('#about-stats').innerHTML=`<strong>${number(meta.coverage.races)} races</strong> · ${meta.coverage.from.slice(0,4)}–${meta.coverage.to.slice(0,4)}<br>UTMB snapshot: ${escape(displayDate(meta.fetchedAt.slice(0,10),true))}<br>${number(meta.coverage.races-meta.coverage.unmapped)} records have approximate locations.<br>${escape($('#itra-status').textContent)}<br>${escape($('#worldsmarathons-status').textContent)}`;updateSourceHealth();runFilters();if(deepLinkPending&&selectedRaceId){deepLinkPending=false;openRace(selectedRaceId);}
 }else if(m.type==='results'||m.type==='view')handleResults(m);
 else if(m.type==='page'){if(m.seq!==seq||m.viewVersion!==viewVersion)return;pending=false;page=m.page;renderCards(m.items,true);$('#load-more').hidden=(page+1)*60>=total;$('#load-more').disabled=false;}
 else if(m.type==='detail'){if(m.requestId===detailRequest)detail(m.race);}
 else if(m.type==='group'){
   const [kind,id]=m.requestId.split(':');
   if(kind==='hover'&&Number(id)===hoverRequest&&currentHover&&m.items.length){const r=m.items[0];$('#tooltip').style.setProperty('--race-grade-color',raceGrade(r).color);$('#tooltip').innerHTML=`${photo(r,'tooltip-image','eager')}<span class="eyebrow">${m.total>1?number(m.total)+' RACES IN THIS AREA':'YOUR NEXT ADVENTURE'}</span>${categoryBadge(r)}<h3>${escape(r.name)}</h3><p>${escape(r.place||r.country||'')}</p><div class="tooltip-stats"><span>${r.distanceKm==null?'—':number(r.distanceKm)} km</span><span>↗ ${r.elevationGainM==null?'—':number(r.elevationGainM)} m</span></div><p>${escape(raceDate(r))}</p>${ratingBadges(r)}`;$('#tooltip').hidden=false;}
   if(kind==='select'&&Number(id)===groupRequest)showGroup(m);
 }else if(m.type==='refresh-error'){notify('Could not check for updates. Browsing the last loaded races.');}else if(m.type==='archive-error'){filters.when='upcoming';filters.datePreset='6m';Object.assign(filters,presetDates('6m'));notify('Historical races could not load. Upcoming races are still available.');runFilters();}else if(m.type==='detail-missing'||m.type==='detail-error'){if(m.type==='detail-missing'){selectedRaceId=null;writeURL();}notify(m.message||'This race is no longer in the saved catalog.');}else if(m.type==='error')showError(m.message);
};
worker.onerror=()=>showError('Unable to start the race browser. Reload in an up-to-date browser.');
form.addEventListener('submit',e=>e.preventDefault());
form.addEventListener('input',e=>{const el=e.target;if(el.name==='country'){const s=new Set(filters.countries);if(el.checked)s.add(el.value);else s.delete(el.value);setFilter('countries',[...s]);}else if(Object.hasOwn(filters,el.name)){if(['from','to'].includes(el.name))filters.datePreset='';setFilter(el.name,el.value,false);}});
form.addEventListener('change',e=>{if(e.target.tagName==='SELECT'&&Object.hasOwn(filters,e.target.name))setFilter(e.target.name,e.target.value);});
$$('[data-when]').forEach(b=>b.addEventListener('click',()=>{filters.when=b.dataset.when;filters.datePreset='any';filters.from='';filters.to='';runFilters();}));
$$('[data-date]').forEach(b=>b.addEventListener('click',()=>{filters.datePreset=b.dataset.date;if(b.dataset.date!=='any')filters.when='upcoming';Object.assign(filters,presetDates(b.dataset.date));runFilters();}));
$$('[data-endurance]').forEach(b=>b.addEventListener('click',()=>{const s=new Set(filters.endurancePoints);if(s.has(b.dataset.endurance))s.delete(b.dataset.endurance);else s.add(b.dataset.endurance);setFilter('endurancePoints',[...s]);}));
$$('[data-category]').forEach(b=>b.addEventListener('click',()=>{const s=new Set(filters.categories);if(s.has(b.dataset.category))s.delete(b.dataset.category);else s.add(b.dataset.category);setFilter('categories',[...s]);}));
$$('[data-distance]').forEach(b=>b.addEventListener('click',()=>{[filters.distanceMin,filters.distanceMax]=b.dataset.distance.split(',');runFilters();}));
for(const which of ['low','high'])$('#distance-'+which).addEventListener('input',e=>{let value=Number(e.target.value);if(which==='low'){value=Math.min(value,Number($('#distance-high').value));filters.distanceMin=value===0?'':String(value);}else{value=Math.max(value,Number($('#distance-low').value));filters.distanceMax=value===500?'':String(value);}updateSlider();clearTimeout(filterTimer);filterTimer=setTimeout(runFilters,80);});
$('#world-series').addEventListener('click',()=>setFilter('worldSeries',!filters.worldSeries));$('#in-view').addEventListener('change',e=>setFilter('inView',e.target.checked));
$('#country-search').addEventListener('input',e=>{$$('#country-options label').forEach(l=>l.hidden=!l.textContent.toLowerCase().includes(e.target.value.toLowerCase()));});
$('#countries-clear').addEventListener('click',()=>setFilter('countries',[]));$('#reset').addEventListener('click',reset);$('#sort').addEventListener('change',runFilters);$('#clear-location').addEventListener('click',()=>setFilter('locationId',null));
$('#load-more').addEventListener('click',()=>{if(pending)return;pending=true;$('#load-more').disabled=true;worker.postMessage({type:'page',seq,viewVersion,page:page+1});});
function collapseResults(value){collapsed=value;$('.workspace').classList.toggle('results-collapsed',value);updatePanelToggle();requestAnimationFrame(()=>globe.map?.resize());}
$('#results-toggle').addEventListener('click',()=>{if(matchMedia('(max-width:800px)').matches){if($('#race-results').classList.contains('open'))closePanels();else $('#show-list').click();}else collapseResults(!collapsed);});
document.addEventListener('click',e=>{if(e.target.closest('[data-share-race]'))shareCurrent();const c=e.target.closest('[data-race]');if(c)openRace(c.dataset.race,{fromGroup:!!c.closest('.details-group-list')});if(e.target.closest('#empty-reset'))reset();if(e.target.closest('#show-worldwide'))setFilter('inView',false);if(e.target.closest('#retry'))location.reload();if(!e.target.closest('.country-picker'))$('.country-picker').open=false;});
function previewCalendarRace(){globe.highlight(visibleRaces.get(hoveredRaceId||focusedRaceId)||null);}
$('#races').addEventListener('pointerover',e=>{const card=e.target.closest('[data-race]');if(card&&card!==e.relatedTarget?.closest?.('[data-race]')){hoveredRaceId=card.dataset.race;previewCalendarRace();}});
$('#races').addEventListener('pointerout',e=>{const card=e.target.closest('[data-race]');if(card&&card!==e.relatedTarget?.closest?.('[data-race]')){hoveredRaceId=null;previewCalendarRace();}});
$('#races').addEventListener('focusin',e=>{focusedRaceId=e.target.closest('[data-race]')?.dataset.race||null;previewCalendarRace();});
$('#races').addEventListener('focusout',()=>{focusedRaceId=null;previewCalendarRace();});
document.addEventListener('error',e=>{if(e.target.tagName==='IMG'){if(/(?:race-photo|tooltip-image|detail-image)/.test(e.target.className)){if(failedImages.size>=1000)failedImages.delete(failedImages.values().next().value);failedImages.add(e.target.src);}e.target.hidden=true;if(e.target.classList.contains('race-photo'))e.target.closest('.race-card')?.classList.remove('has-photo');}},true);
$('#zoom-in').addEventListener('click',()=>globe.zoomBy(1));$('#zoom-out').addEventListener('click',()=>globe.zoomBy(-1));$('#globe-reset').addEventListener('click',()=>globe.reset());
$('#detail-back').addEventListener('click',backToGroup);
$('#detail-close').addEventListener('click',()=>$('#detail-dialog').close());$('#about-close').addEventListener('click',()=>$('#about-dialog').close());
for(const d of $$('dialog'))d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}});
$('#about-open').addEventListener('click',()=>$('#about-dialog').showModal());$('#category-help').addEventListener('click',()=>$('#about-dialog').showModal());
$('#open-filters').setAttribute('aria-controls','filters-panel');$('#show-list').setAttribute('aria-controls','race-results');
$('#open-filters').addEventListener('click',()=>{closePanels();$('#filters-panel').classList.add('open');panelReturnTarget=$('#open-filters');syncPanelAccessibility();$('#open-filters').setAttribute('aria-expanded','true');$('#search').focus();});
$('#filters-close').addEventListener('click',()=>{closePanels();$('#open-filters').focus();});$('#filters-done').addEventListener('click',()=>{if(valid()){closePanels();$('#open-filters').focus();}});
$('#show-list').addEventListener('click',()=>{closePanels();$('#race-results').classList.add('open');panelReturnTarget=$('#show-list');syncPanelAccessibility();$('#show-list').setAttribute('aria-expanded','true');$('#list-close').focus();updatePanelToggle();});$('#list-close').addEventListener('click',()=>{closePanels();$('#show-list').focus();});
$('.skip-link').addEventListener('click',e=>{if(matchMedia('(max-width:800px)').matches){e.preventDefault();$('#show-list').click();}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){clearHover();$('.country-picker').open=false;if(!$$('dialog[open]').length){closePanels();panelReturnTarget?.focus();}}if(e.key==='/'&&!['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName)&&!$$('dialog[open]').length){e.preventDefault();if(matchMedia('(max-width:800px)').matches)$('#open-filters').click();$('#search').focus();}});
window.addEventListener('hashchange',()=>{restoreURL();if(sharedCamera&&globe.ready)globe.map.jumpTo(sharedCamera);runFilters();if(selectedRaceId&&ready)openRace(selectedRaceId);});document.addEventListener('visibilitychange',()=>{if(!document.hidden&&ready){if(filters.datePreset&&filters.datePreset!=='any')Object.assign(filters,presetDates(filters.datePreset));runFilters();}});
if(matchMedia('(pointer:coarse)').matches)$('#globe-instruction').textContent='Drag to explore · Pinch to get closer';
matchMedia('(max-width:800px)').addEventListener('change',()=>{updatePanelToggle();syncPanelAccessibility();});
updatePanelToggle();syncPanelAccessibility();restoreURL();worker.postMessage({type:'init'});

// Recalculate relative windows across midnight, and pick up daily imports in long-lived tabs.
let observedDay=localToday(),lastDatasetCheck=Date.now();
function checkCalendarClock(){
 if(!ready||document.hidden)return;
 const today=localToday();
 if(today!==observedDay){observedDay=today;if(filters.datePreset&&filters.datePreset!=='any')Object.assign(filters,presetDates(filters.datePreset));runFilters();}
 if(Date.now()-lastDatasetCheck>=3600000){lastDatasetCheck=Date.now();worker.postMessage({type:'init',background:true});}
}
setInterval(checkCalendarClock,60000);
document.addEventListener('visibilitychange',checkCalendarClock);

function notify(text){const box=$('#app-status');box.textContent=text;box.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>box.hidden=true,5000);}
function reportURL(r){const p=new URLSearchParams({title:'Race correction: '+r.name,body:`Race: ${r.name} (${r.date})\nRace ID: ${r.id}\nSources:\n${sourceRecords(r).map(s=>s.url).filter(Boolean).join('\n')}\n\nWhat should change?\n`});return 'https://github.com/mannmann2/race/issues/new?'+p;}
async function shareCurrent(){writeURL();const url=location.href,title=selectedRaceId?($('#detail-content h2')?.textContent||'Race Atlas'):'Race Atlas — find your next starting line';
 try{if(navigator.share&&matchMedia('(pointer:coarse)').matches){await navigator.share({title,url});return;}if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(url);notify('Link copied.');return;}}catch(e){if(e.name==='AbortError')return;}
 $('#share-link').value=url;$('#share-dialog').showModal();$('#share-link').focus();$('#share-link').select();
}
$('#share-view').addEventListener('click',shareCurrent);$('#share-close').addEventListener('click',()=>$('#share-dialog').close());
$('#detail-dialog').addEventListener('close',()=>{activeGroup=null;$('#detail-back').hidden=true;selectedRaceId=null;writeURL();if(dialogReturnTarget?.isConnected&&!dialogReturnTarget.closest('[inert]'))dialogReturnTarget.focus();else if(!matchMedia('(max-width:800px)').matches)globe.map?.getCanvas().focus();});
function syncPanelAccessibility(){
 const mobile=matchMedia('(max-width:800px)').matches,active=mobile?$('.filters.open,.results-panel.open'):null;
 $('.header').inert=!!active;
 for(const e of [...$('.workspace').children])e.inert=!!active&&e!==active;
 for(const panel of [$('#filters-panel'),$('#race-results')]){if(mobile&&panel===active){panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');}else{panel.removeAttribute('role');panel.removeAttribute('aria-modal');}}
}
document.addEventListener('keydown',e=>{if(e.key!=='Tab'||$$('dialog[open]').length||!matchMedia('(max-width:800px)').matches)return;const panel=$('.filters.open,.results-panel.open');if(!panel)return;const stops=[...panel.querySelectorAll('button,a[href],input,select,summary,[tabindex="0"]')].filter(e=>!e.disabled&&!e.hidden&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');const first=stops[0],last=stops.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}});
function updateSourceHealth(){if(!meta?.sourceMeta)return;const warnings=[];for(const [provider,source]of Object.entries(meta.sourceMeta)){if(!source.races)continue;const h=sourceHealth(source,provider);if(h.failed||h.stale)warnings.push(`${providerName(provider)} ${h.failed?'refresh unavailable':'data is older than expected'}; showing saved listings.`);}const box=$('#source-warning');box.hidden=!warnings.length;box.textContent=warnings.join(' ');$('.filter-footer .status-dot').style.background=warnings.length?'var(--error)':'var(--accent-solid)';}
