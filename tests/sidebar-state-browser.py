"""Opening a grouped race or returning from its provider must preserve pagination."""
import gzip,json,os,re
from playwright.sync_api import sync_playwright,expect

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4175').rstrip('/')+'/'
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
data={'schemaVersion':2,'fetchedAt':'2026-11-09T00:00:00Z','countries':{'FR':{'name':'France','continent':'Europe'}},'events':[['fixture','Sidebar fixtures']],'locations':[['Chamonix','FR',7,46,'town','1']],'records':[[str(i+1),0,f'Race {i+1:03d}','2027-01-10',50,2000,'50k',0,None,'fixture.'+str(i+1),'qualifier',0] for i in range(185)],'coverage':{'from':'2027-01-10','to':'2027-01-10','races':185,'unmapped':0}}
payload=gzip.compress(json.dumps(data).encode())
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 for mobile in [False,True]:
  c=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844} if mobile else {'width':1440,'height':950},has_touch=mobile,reduced_motion='reduce')
  c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
  c.route('**/data/catalog-index.json',lambda r:r.fulfill(status=404,body='Legacy fixture transport'))
  c.route('**/data/catalog.json.gz',lambda r:r.fulfill(status=200,content_type='application/gzip',body=payload))
  c.route(re.compile(r'https://utmb\.world/.*'),lambda r:r.fulfill(status=200,content_type='text/html',body='External race page'))
  page=c.new_page();page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'#when=all&datePreset=any&view=7,46,4',wait_until='domcontentloaded')
  page.wait_for_function("window.testMap?.isSourceLoaded('races') && !testMap.isMoving() && document.querySelector('#races').getAttribute('aria-busy')==='false' && document.querySelector('#result-count').textContent==='185'",timeout=60000)
  if mobile:page.locator('#show-list').click()
  for n in [120,180]:
   page.locator('#load-more').click();expect(page.locator('#races [data-race]')).to_have_count(n)
  panel=page.locator('#race-results');panel.evaluate('el=>el.scrollTop=15000')
  scroll=panel.evaluate('el=>el.scrollTop')
  if mobile:page.locator('#list-close').click()
  ids=page.locator('#races [data-race]').evaluate_all('els=>els.map(e=>e.dataset.race)')
  camera=page.evaluate('({center:testMap.getCenter().toArray(),zoom:testMap.getZoom()})')
  page.evaluate("() => {const point=testMap.project([7,46]);testMap.fire('click',{point,lngLat:testMap.unproject(point)});}")
  expect(page.locator('.details-group-list')).to_be_visible(timeout=20000)
  with c.expect_page() as opened:page.locator('.group-race-links a').first.click()
  external=opened.value;external.wait_for_load_state('domcontentloaded');external.close()
  page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
  expect(page.locator('#races [data-race]')).to_have_count(180)
  page.locator('.details-group-list [data-race]').nth(1).click()
  expect(page.locator('#detail-back')).to_be_visible()
  assert page.evaluate('({center:testMap.getCenter().toArray(),zoom:testMap.getZoom()})')==camera
  page.locator('#detail-back').click();expect(page.locator('.details-group-list')).to_be_visible()
  expect(page.locator('#races [data-race]')).to_have_count(180)
  page.locator('.details-group-list [data-race]').nth(1).click()
  page.locator('#detail-close').click()
  if mobile:page.locator('#show-list').click()
  expect(page.locator('#races [data-race]')).to_have_count(180)
  assert page.locator('#races [data-race]').evaluate_all('els=>els.map(e=>e.dataset.race)')==ids
  assert abs(panel.evaluate('el=>el.scrollTop')-scroll)<2
  page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
  expect(page.locator('#races')).to_have_attribute('aria-busy','false')
  expect(page.locator('#races [data-race]')).to_have_count(180)
  assert not errors,errors
  print(('Phone' if mobile else 'Desktop')+': 180 loaded rows and sidebar scroll survive group -> race -> close and provider-tab return',flush=True)
  c.close()
 browser.close()
