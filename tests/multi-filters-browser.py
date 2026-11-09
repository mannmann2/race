"""Continent/source unions, optional intersection and old/new shared links."""
import gzip,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from ui_filters import select_sources,select_continents

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4175').rstrip('/')+'/'
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
specs=[('Europe',['utmb','itra']),('Asia',['itra']),('North America',['worldsmarathons']),('Africa',['utmb']),('Europe',['worldsmarathons']),('Asia',['utmb','worldsmarathons'])]
races=[]
for i,(continent,providers) in enumerate(specs,1):
 primary=providers[0];rid=f'utmb:{i}' if primary=='utmb' else f'{primary}:2027:{i}'
 races.append({'id':rid,'source':primary,'sourceId':str(i),'sourceUrl':'https://example.org/race/'+str(i),'eventId':'fixture:'+str(i),'name':'Race '+str(i),'eventName':'Multi-filter fixtures','date':'2027-01-10','country':'Fixture country','countryCode':'FR','continent':continent,'place':'Fixture town','longitude':7,'latitude':46,'locationId':str(i),'distanceKm':50,'extensions':{},'sources':[{'provider':p,'id':str(i),'url':'https://example.org/race/'+str(i)} for p in providers]})
data={'schemaVersion':3,'races':races,'fetchedAt':'2026-11-09T00:00:00Z','countries':{'FR':{'name':'France','continent':'Europe'}},'coverage':{'races':6,'unmapped':0,'from':'2027-01-10','to':'2027-01-10'}}
payload=gzip.compress(json.dumps(data).encode())
def count(page,n):
 expect(page.locator('#result-count')).to_have_text(str(n),timeout=30000)
 page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 for mobile in [False,True]:
  c=browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':950},has_touch=mobile,reduced_motion='reduce')
  c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
  c.route('**/data/catalog-index.json',lambda r:r.fulfill(status=404,body='Legacy fixture transport'))
  c.route('**/data/catalog.json.gz',lambda r:r.fulfill(status=200,content_type='application/gzip',body=payload))
  page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded');count(page,6)
  if mobile:page.locator('#open-filters').click()
  select_continents(page,['Europe','Asia']);count(page,4)
  select_sources(page,['utmb','itra']);count(page,3)
  page.locator('#source-match-all').check();count(page,1)
  select_continents(page,['Asia']);count(page,0)
  select_sources(page,['worldsmarathons','itra']);count(page,2)
  select_continents(page,['Europe','Asia']);count(page,4)
  page.reload(wait_until='domcontentloaded');count(page,4)
  if mobile:page.locator('#open-filters').click()
  page.locator('#source-picker summary').click();page.locator('#continent-picker summary').click()
  expect(page.locator('input[name=sources]:checked')).to_have_count(2)
  expect(page.locator('input[name=continents]:checked')).to_have_count(2)
  expect(page.locator('#snapshot-label')).to_contain_text('Data refreshed:')
  Path('test-results').mkdir(exist_ok=True)
  page.locator('#filters-panel').screenshot(path='test-results/multi-filters-'+('phone' if mobile else 'desktop')+'.png')
  page.goto(BASE+'#when=all&datePreset=any&inView=0&source=both&continent=Europe',wait_until='domcontentloaded');count(page,1)
  expect(page.locator('input[name=continents][value="Europe"]')).to_be_checked()
  expect(page.locator('#source-match-all')).to_be_checked()
  page.locator('#reset').click()
  expect(page.locator('input[name=sources]:checked')).to_have_count(0)
  expect(page.locator('input[name=continents]:checked')).to_have_count(0)
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  assert not errors,errors
  print(('Phone' if mobile else 'Desktop')+': multiple continents/sources, source intersection, URL persistence, legacy links and reset passed',flush=True)
  c.close()
 browser.close()
