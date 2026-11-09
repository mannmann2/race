"""Viewport containment, grade precedence and per-frame globe count visibility."""
import gzip,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
os.environ.setdefault('PW_TEST_SCREENSHOT_NO_FONTS_READY','1')
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174')
OUT=Path('/root/race/test-results');OUT.mkdir(exist_ok=True)
DATE='2027-04-10';STAMP='2026-11-09T00:00:00Z'
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
locations=[['Alps','FR',7,46,'town','1'],['Australia','AU',145,-35,'town','2'],['America','US',-100,35,'town','3'],['Africa','GA',30,0,'town','4'],['Atlantic','SN',-15,10,'town','5']]
records=[['1',0,'UTMB preferred',DATE,50,2500,'50k',0,None,None,'qualifier',0],['2',0,'Yellow twenty',DATE,20,1000,'20k',0,None,None,'qualifier',0],['3',0,'Far hemisphere',DATE,50,2000,'50k',1,None,None,'qualifier',0],['4',0,'Red hundred mile',DATE,160,5000,'100m',2,None,None,'qualifier',0],['5',0,'Zero points fallback',DATE,10,50,None,4,None,None,'qualifier',0]]
def itra(i,points,lon=30,lat=0):
 return {'id':'itra:'+str(i),'source':'itra','sourceId':str(i),'sourceUrl':'https://itra.run/Races/RaceCalendar','name':'ITRA '+str(points)+' points','eventName':'Fixtures','date':DATE,'distanceKm':50,'longitude':lon,'latitude':lat,'locationId':'itra:'+str(i),'countryCode':'FR','place':'Fixture town','extensions':{'itra':{'endurancePoints':points}}}
extras=[{'race':itra(1,6,7,46),'matchId':'utmb:1'},{'race':itra(5,0,-15,10),'matchId':'utmb:5'},{'race':itra(6,3),'matchId':None},{'race':itra(7,3),'matchId':None},{'race':itra(8,6,80,20),'matchId':None}]
records.append(['6',0,'No grade fixture',DATE,30,500,None,4,None,None,'qualifier',0])
extras.append({'race':itra(9,None,-15,10),'matchId':'utmb:6'})
extras[0]['race']['extensions']['itra']['mountainLevel']=7
data={'schemaVersion':2,'fetchedAt':STAMP,'countries':{'FR':{'name':'France','continent':'Europe'}},'events':[['fixture','Fixtures']],'locations':locations,'records':records,'additionalRaces':extras,'coverage':{'from':DATE,'to':DATE,'races':9,'unmapped':0}}
payload=gzip.compress(json.dumps(data).encode())
def fit(page):
 result=page.evaluate('''() => {window.scrollTo(99999,99999);return {x:scrollX,y:scrollY,w:innerWidth,h:innerHeight,scrollW:document.documentElement.scrollWidth,scrollH:document.documentElement.scrollHeight,bottom:document.querySelector('.workspace').getBoundingClientRect().bottom}}''')
 assert result['x']==0 and result['y']==0,result
 assert result['scrollW']<=result['w'] and result['scrollH']<=result['h'],result
 assert abs(result['bottom']-result['h'])<1,result
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 mobile=os.environ.get('TEST_DEVICE')=='mobile'
 c=browser.new_context(bypass_csp=True,viewport={'width':390,'height':600} if mobile else {'width':1440,'height':900},is_mobile=mobile,has_touch=mobile,color_scheme='light',reduced_motion='reduce')
 c.route('**/data/catalog-index.json',lambda route:route.fulfill(status=404,body='Fixture uses the legacy transport'))
 c.route('**/data/catalog.json.gz',lambda route:route.fulfill(status=200,content_type='application/gzip',body=payload))
 page=c.new_page();page.set_default_timeout(15000);page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded')
 expect(page.locator('#result-count')).to_have_text('9',timeout=30000)
 page.wait_for_function("window.testMap?.getLayer('race-points') && testMap.isSourceLoaded('races')",timeout=60000)
 fit(page);print('Loaded and viewport contained',flush=True)
 if mobile:page.locator('#show-list').click()
 unknown=page.locator('#races [data-race="utmb:6"]')
 expect(unknown.locator('.category-badge .grade-source')).to_have_text(['UTMB','ITRA'])
 expect(unknown.locator('.category-badge .grade-status')).to_have_text('No grade supplied')
 expect(unknown.locator('.grade-icon')).to_have_count(0)
 for rid,key,color in ([] if os.environ.get('TEST_PHASE')=='rotation' else [('utmb:1','utmb:50k','rgb(252, 90, 0)'),('utmb:5','itra:0','rgb(121, 123, 119)'),('itra:6','itra:3','rgb(91, 201, 238)')]):
  print('Check card',rid,flush=True)
  card=page.locator(f'#races [data-race="{rid}"]');expect(card).to_have_attribute('data-grade',key)
  assert card.evaluate('e=>getComputedStyle(e).borderLeftColor')==color
  card.click();expect(page.locator('#detail-content')).to_have_attribute('data-grade',key)
  image=page.locator('.detail-grade .grade-icon');expect(image).to_have_count(2 if rid=='utmb:1' else 1)
  if rid=='utmb:1':
   assert image.evaluate_all('images=>images.map(i=>i.alt)')==['UTMB 50K','ITRA 6 Endurance Points']
   assert 'ITRA pts' not in card.inner_text()
   expect(card.locator('.grade-source')).to_have_count(0)
   expect(card.locator('.source-badges')).to_have_text('Mountain 7/12')
   boxes=[image.nth(i).bounding_box() for i in range(2)]
   assert boxes[0]['x']+boxes[0]['width']<=boxes[1]['x'] and abs((boxes[0]['y']+boxes[0]['height']/2)-(boxes[1]['y']+boxes[1]['height']/2))<2
  page.wait_for_function("document.querySelector('.detail-grade img')?.naturalWidth>0")
  assert image.first.bounding_box()['height']>=32
  assert page.locator('.detail-top').evaluate('e=>getComputedStyle(e).borderTopColor')==color
  fit(page);print('Detail grade verified',key,flush=True)
  if rid=='utmb:1':page.screenshot(path=str(OUT/('grades-phone-detail.png' if mobile else 'grades-desktop-detail.png')))
  page.locator('#detail-close').click()
 if not mobile:
  page.mouse.move(700,100)
  page.evaluate('''() => {testMap.jumpTo({center:[7,46],zoom:6});}''')
  page.wait_for_function("testMap.isSourceLoaded('races') && testMap.queryRenderedFeatures(testMap.project([7,46]),{layers:['race-points','race-clusters']}).length>0")
  page.evaluate('''() => {testMap.fire('mousemove',{point:testMap.project([7,46])});}''')
  expect(page.locator('#tooltip')).to_be_visible(timeout=15000)
  expect(page.locator('#tooltip .grade-icon')).to_have_count(2)
  expect(page.locator('#tooltip .grade-source')).to_have_count(0)
  heading=page.locator('#tooltip>.eyebrow').bounding_box()
  badges=page.locator('#tooltip>.category-badge').bounding_box()
  assert badges['y']>=heading['y']+heading['height']+5,(heading,badges)
  page.screenshot(path=str(OUT/'grades-hover-row.png'))
 if mobile:
  page.locator('#list-close').click();page.locator('#open-filters').click()
  page.locator('#filters-panel').evaluate('e=>e.scrollTop=e.scrollHeight')
  assert page.locator('#filters-panel').evaluate('e=>e.scrollTop>0')
  fit(page);page.screenshot(path=str(OUT/'grades-phone-filters.png'));page.locator('#filters-done').click()
  page.set_viewport_size({'width':390,'height':450});fit(page)
 elif os.environ.get('TEST_PHASE')!='badges':
  page.locator('#filters-panel').evaluate('e=>e.scrollTop=e.scrollHeight');assert page.locator('#filters-panel').evaluate('e=>e.scrollTop>0');fit(page)
  page.locator('#races .race-card').first.scroll_into_view_if_needed()
  page.evaluate('''async () => {
   const {Globe}=await import('./globe.mjs'),original=Globe.prototype.drawCounts;
   window.countFrames=0;window.countVisibleFrames=0;window.hiddenCountFailures=[];
   Globe.prototype.drawCounts=function(){original.call(this);window.testGlobe=this;window.countFrames++;
    if(this.drawnCounts.length)window.countVisibleFrames++;
    for(const label of this.drawnCounts)if(this.map.transform.isLocationOccluded(maplibregl.LngLat.convert(label.coordinates))||!this.map.transform.isPointOnMapSurface({x:label.x,y:label.y},this.map.terrain))window.hiddenCountFailures.push(label);
   };testMap.triggerRepaint();
  }''')
  page.wait_for_function('!!window.testGlobe')
  assert page.evaluate("!testMap.getLayer('race-cluster-labels') && !testMap.getLayer('race-point-labels')")
  # Loaded point/cluster totals keep the preferred grades, including mixed locations.
  props=page.evaluate("testMap.getSource('races').serialize().data.features.map(f=>f.properties)")
  mixed=next(r for r in props if r['key']=='7,46');assert mixed['grade_0']==1 and mixed['grade_1']==1
  assert sum(r['grade_7'] for r in props)==2
  assert sum(r['grade_10'] for r in props)==1 # ITRA 6; the merged UTMB race retains UTMB priority.
  print('Checking rotation frames',flush=True)
  for center in [[160,-30],[-170,20],[-100,35],[12,25]]:
   page.evaluate('(center)=>{testMap.easeTo({center,zoom:1.8,duration:600,essential:true});}',center)
   print('Rotate',center,flush=True)
   page.wait_for_function('!testMap.isMoving()');page.wait_for_function('window.countFrames>0')
  assert page.evaluate('countFrames')>=8
  assert page.evaluate('countVisibleFrames')>0
  assert page.evaluate('hiddenCountFailures')==[]
  page.locator('#theme-toggle').click();page.screenshot(path=str(OUT/'grades-globe-dark.png'))
  assert page.evaluate('hiddenCountFailures')==[]
  page.locator('#theme-toggle').click();page.screenshot(path=str(OUT/'grades-globe-light.png'))
  for w,h in [(1280,600),(1024,400),(1440,900)]:page.set_viewport_size({'width':w,'height':h});fit(page)
 assert not errors,errors
 print(('Phone' if mobile else 'Desktop')+': viewport containment, panel scrolling, official badges, grade priority, detail accents'+(' and per-frame count occlusion' if not mobile and os.environ.get('TEST_PHASE')!='badges' else '')+' passed',flush=True)
 c.close();browser.close()
