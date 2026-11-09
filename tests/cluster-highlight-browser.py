"""Sidebar previews must outline the rendered parent bubble, at every zoom."""
import gzip,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4175').rstrip('/')+'/'
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
locations=[['West','FR',7,46,'town','1'],['Centre','FR',7.10,46,'town','2'],['East','FR',7.15,46,'town','3'],['Nearby','FR',8,46,'town','4'],['Far side','AU',145,-35,'town','5']]
data={'schemaVersion':2,'fetchedAt':'2026-11-09T00:00:00Z','countries':{'FR':{'name':'France','continent':'Europe'},'AU':{'name':'Australia','continent':'Oceania'}},'events':[['fixture','Preview fixtures']],'locations':locations,'records':[[str(i+1),0,name,'2027-01-10',50,2000,'50k',loc,None,None,'qualifier',0] for i,(name,loc) in enumerate([('West race',0),('Centre race',1),('East race',2),('Same spot race',0),('Nearby race',3),('Far side race',4)])],'coverage':{'from':'2027-01-10','to':'2027-01-10','races':6,'unmapped':0}}
payload=gzip.compress(json.dumps(data).encode())

def wait_highlight(page,race_id):
 page.wait_for_function("id=>testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId===id",arg=race_id)
 return page.evaluate("testMap.getSource('race-highlight').serialize().data.features[0]")

with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 c=browser.new_context(bypass_csp=True,viewport={'width':1440,'height':950},reduced_motion='reduce')
 c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
 c.route('**/data/catalog-index.json',lambda r:r.fulfill(status=404,body='Legacy fixture transport'))
 c.route('**/data/catalog.json.gz',lambda r:r.fulfill(status=200,content_type='application/gzip',body=payload))
 page=c.new_page();page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded')
 expect(page.locator('#result-count')).to_have_text('6',timeout=30000)
 page.wait_for_function("window.testMap?.getLayer('race-highlight-halo') && testMap.isSourceLoaded('races')",timeout=60000)
 page.evaluate("testMap.jumpTo({center:[7.08,46],zoom:6})")
 page.wait_for_function("!testMap.isMoving() && testMap.isSourceLoaded('races')")
 west=page.locator('#races [data-race="utmb:1"]');west.hover()
 highlighted=wait_highlight(page,'utmb:1')
 assert highlighted['properties']['markerKey'].startswith('cluster:')
 assert abs(highlighted['geometry']['coordinates'][0]-7)>.01,'Must outline the cluster, not the hidden individual location'
 # The highlight coincides with a real rendered marker that contains this race.
 assert page.evaluate("""async () => {
  const h=testMap.getSource('race-highlight').serialize().data.features[0];
  const marker=testMap.queryRenderedFeatures({layers:['race-clusters']}).find(f=>'cluster:'+f.properties.cluster_id===h.properties.markerKey);
  if(!marker||JSON.stringify(marker.geometry)!==JSON.stringify(h.geometry))return false;
  const leaves=await testMap.getSource('races').getClusterLeaves(marker.properties.cluster_id,marker.properties.point_count,0);
  return leaves.some(f=>f.properties.key==='7,46')&&h.properties.radius>10;
 }""")
 assert page.evaluate("!testMap.getLayer('race-highlight-point') && testMap.getPaintProperty('race-highlight-halo','circle-opacity')===0")
 Path('test-results').mkdir(exist_ok=True)
 for theme in ['light','dark']:
  page.locator('#theme-toggle').evaluate('(el,theme)=>{if(document.documentElement.dataset.theme!==theme)el.click()}',theme)
  page.screenshot(path='test-results/cluster-highlight-'+theme+'.png')
 # Same-location races use exactly the same cluster, rather than another inner dot.
 page.locator('#races [data-race="utmb:4"]').hover()
 assert wait_highlight(page,'utmb:4')['properties']['markerKey']==highlighted['properties']['markerKey']
 # Rapid hovers must leave only the latest requested race highlighted.
 west.hover();page.locator('#races [data-race="utmb:5"]').hover()
 assert wait_highlight(page,'utmb:5')['properties']['markerKey']=='8,46'
 page.mouse.move(30,30)
 page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features.length===0")
 # Keyboard preview survives zoom changes, following the newly split marker.
 west.focus();wait_highlight(page,'utmb:1')
 page.evaluate("testMap.jumpTo({center:[7,46],zoom:13})")
 page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features[0]?.properties.markerKey==='7,46'")
 split=wait_highlight(page,'utmb:1');assert split['properties']['radius']==12 # Same-location bubble radius 7 + external gap 5.
 page.evaluate("testMap.jumpTo({center:[7.08,46],zoom:6})")
 page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features[0]?.properties.markerKey.startsWith('cluster:')")
 page.locator('#results-toggle').focus()
 page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features.length===0")
 # The whole-globe view needs a local rendered hit; a full-viewport query can omit it.
 page.evaluate("testMap.jumpTo({center:[12,25],zoom:1.7})")
 page.wait_for_function("!testMap.isMoving() && testMap.isSourceLoaded('races')")
 west.hover();wide=wait_highlight(page,'utmb:1')
 assert wide['properties']['markerKey'].startswith('cluster:')
 assert page.evaluate("""() => {const h=testMap.getSource('race-highlight').serialize().data.features[0],p=testMap.project(h.geometry.coordinates);return testMap.queryRenderedFeatures([[p.x-8,p.y-8],[p.x+8,p.y+8]],{layers:['race-clusters','race-points']}).some(f=>'cluster:'+f.properties.cluster_id===h.properties.markerKey);} """)
 page.evaluate("testMap.jumpTo({center:[7.08,46],zoom:6})")
 page.wait_for_function("!testMap.isMoving() && testMap.isSourceLoaded('races')")
 # Worldwide browsing still brings a far-side race into view, without adding a pin.
 page.locator('#races [data-race="utmb:6"]').hover()
 assert wait_highlight(page,'utmb:6')['properties']['markerKey']=='145,-35'
 assert abs(page.evaluate('testMap.getZoom()')-6)<.001
 # Filtering while a preview is active cannot leave its outline behind.
 page.locator('#search').fill('No matching race')
 expect(page.locator('.empty-state')).to_be_visible()
 page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features.length===0")
 assert not errors,errors
 print('Parent-cluster membership, same-location bubbles, both themes, rapid hover, focus, zoom regrouping, far-side reveal and clearing passed',flush=True)
 browser.close()
