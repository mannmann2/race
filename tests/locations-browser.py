"""Check corrected real race positions in the worker, cards and map source."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174').rstrip('/')+'/'
HOOK='''let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});
const W=window.Worker;window.Worker=class extends W{constructor(...a){super(...a);this.addEventListener('message',({data})=>{if(data.type==='results')window.testResults=data;});}};'''
CASES=[
 ('Slate Trail Ultra',['utmb:138830','utmb:138832','itra:2026:112206'],(-4.5,53,-3.8,53.5)),
 ('Wendover',['utmb:138428','itra:2026:117858'],(-1,51.5,-.5,52)),
 ('Tunnel Hill',['utmb:156458'],(-90,36,-87,39)),
 ('Leavenworth',['utmb:159450','utmb:159452'],(-121,47,-120,48)),
 ('Kokoda Brisbane',['utmb:156288'],(152,-28,154,-27)),
 ('Granite Peaks',['utmb:158378'],(-6.2,54,-5.5,54.5)),
]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 page=browser.new_page(bypass_csp=True,viewport={'width':1440,'height':950})
 page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded')
 page.wait_for_function("window.testMap && testMap.getLayer('race-points') && window.testResults",timeout=90000)
 for query,ids,bounds in CASES:
  page.locator('#search').fill(query)
  page.wait_for_function('(q)=>testResults?.items?.length && document.querySelector("#races").getAttribute("aria-busy")==="false" && testResults.items.every(r=>q.toLowerCase().split(" ").every(t=>r.searchText? r.searchText.includes(t):[r.name,r.eventName,r.place].join(" ").toLowerCase().includes(t)))',arg=query,timeout=30000)
  rows=page.evaluate('testResults.items')
  w,s,e,n=bounds
  mapped=[r for r in rows if r['longitude'] is not None]
  assert mapped,query
  # All editions with a known location for these event queries belong here.
  assert all(w<=r['longitude']<=e and s<=r['latitude']<=n for r in mapped),[(r['id'],r['longitude'],r['latitude']) for r in mapped]
  for id in ids:assert any(r['id']==id for r in rows),(query,id)
  page.wait_for_function('(v)=>{const [w,s,e,n]=v;const f=testMap.getSource("races").serialize().data.features;return f.length>0&&f.every(f=>{const [x,y]=f.geometry.coordinates;return x>=w&&x<=e&&y>=s&&y<=n;});}',arg=list(bounds),timeout=30000)
  print(query+': calendar and globe coordinates passed',flush=True)
 page.locator('#search').fill('Slate Trail Ultra');expect(page.locator('#races [data-race="utmb:138832"]')).to_be_visible(timeout=30000)
 page.locator('[data-race="utmb:138832"]').click();expect(page.locator('#detail-dialog')).to_be_visible()
 expect(page.locator('#race-title')).to_have_text('Ultra Tour of the Quarries')
 Path('test-results').mkdir(exist_ok=True);page.screenshot(path='test-results/corrected-locations.png')
 assert not errors,errors
 browser.close()
