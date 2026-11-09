"""Nonconsecutive month selection, URL persistence and date-range switching."""
import datetime,gzip,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4175').rstrip('/')+'/'
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
dates=['2027-01-01','2027-01-31','2027-02-01','2027-03-01','2027-03-31','2027-06-01','2026-01-01']
data={'schemaVersion':2,'fetchedAt':'2026-11-09T00:00:00Z','countries':{'FR':{'name':'France','continent':'Europe'}},'events':[['fixture','Month fixtures']],'locations':[['Chamonix','FR',7,46,'town','1']],'records':[[str(i+1),0,'Race '+date,date,50,2000,'50k',0,None,None,'qualifier',0] for i,date in enumerate(dates)],'coverage':{'from':min(dates),'to':max(dates),'races':len(dates),'unmapped':0}}
payload=gzip.compress(json.dumps(data).encode())

def count(page,n):
 expect(page.locator('#result-count')).to_have_text(str(n),timeout=30000)
 page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")

with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 for mobile in [False,True]:
  c=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844} if mobile else {'width':1440,'height':950},has_touch=mobile,color_scheme='dark' if mobile else 'light',reduced_motion='reduce')
  c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
  c.route('**/data/catalog-index.json',lambda r:r.fulfill(status=404,body='Legacy fixture transport'))
  c.route('**/data/catalog.json.gz',lambda r:r.fulfill(status=200,content_type='application/gzip',body=payload))
  page=c.new_page();page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.clock.set_fixed_time(datetime.datetime(2026,11,9,12,tzinfo=datetime.timezone.utc))
  page.goto(BASE+'#inView=0',wait_until='domcontentloaded');count(page,5)
  if mobile and page.locator('#open-filters').get_attribute('aria-expanded')!='true':page.locator('#open-filters').click()
  page.locator('#month-picker summary').click()
  expect(page.locator('[data-month]')).to_have_count(12)
  page.get_by_role('button',name='January 2027',exact=True).click();count(page,2)
  page.get_by_role('button',name='March 2027',exact=True).click();count(page,4)
  expect(page.locator('#month-summary')).to_have_text('2 months selected')
  expect(page.locator('[name=from]')).to_have_value('');expect(page.locator('[name=to]')).to_have_value('')
  assert 'months=2027-01%2C2027-03' in page.url
  page.wait_for_function("testMap?.getSource('races')?.serialize().data.features[0]?.properties.count===4")
  page.reload(wait_until='domcontentloaded');count(page,4)
  if mobile and page.locator('#open-filters').get_attribute('aria-expanded')!='true':page.locator('#open-filters').click()
  expect(page.get_by_role('button',name='January 2027',exact=True)).to_have_attribute('aria-pressed','true')
  expect(page.get_by_role('button',name='March 2027',exact=True)).to_have_attribute('aria-pressed','true')
  Path('test-results').mkdir(exist_ok=True)
  page.locator('#filters-panel').screenshot(path='test-results/months-'+('phone-dark' if mobile else 'desktop-light')+'.png')
  january=page.get_by_role('button',name='January 2027',exact=True);january.focus();page.keyboard.press('Space');count(page,2)
  expect(january).to_be_focused()
  page.locator('[data-date="12m"]').click();count(page,6)
  expect(page.locator('[data-month][aria-pressed=true]')).to_have_count(0)
  page.get_by_role('button',name='June 2027',exact=True).click();count(page,1)
  page.locator('[name=from]').fill('2027-01-01');page.locator('[name=to]').fill('2027-01-31');count(page,2)
  expect(page.locator('[data-month][aria-pressed=true]')).to_have_count(0)
  page.get_by_role('button',name='March 2027',exact=True).click();count(page,2)
  page.locator('#months-clear').click();count(page,6)
  expect(page.locator('[data-date="any"]')).to_have_attribute('aria-pressed','true')
  page.locator('#reset').click();count(page,5)
  expect(page.locator('[data-date="6m"]')).to_have_attribute('aria-pressed','true')
  # Shared selections remain explicit about year and survive their months ageing out.
  page.goto(BASE+'#when=all&months=2026-01,2026-01,2027-13,bad&inView=0',wait_until='domcontentloaded');count(page,1)
  if mobile and page.locator('#open-filters').get_attribute('aria-expanded')!='true':page.locator('#open-filters').click()
  expect(page.get_by_role('button',name='January 2026',exact=True)).to_have_attribute('aria-pressed','true')
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
  assert not errors,errors
  print(('Phone' if mobile else 'Desktop')+': Jan + Mar union, map counts, URL reload, keyboard, presets, custom dates, clear/reset and saved past months passed',flush=True)
  c.close()
 browser.close()
