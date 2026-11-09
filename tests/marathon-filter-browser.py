"""Real worker/UI with isolated course fixtures; never alters the race catalog."""
import gzip,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174')
DATE='2027-04-10';STAMP='2026-11-09T00:00:00Z'
rows=[['1',0,'Marathon graded 20K',DATE,42,0,'20k',0,None,None,'qualifier',0],['2',0,'Marathon graded 50K',DATE,42.2,0,'50k',0,None,None,'qualifier',0],['3',0,'Marathon graded 100K',DATE,42.195,0,'100k',0,None,None,'qualifier',0],['4',0,'Measured trail marathon',DATE,44.3,0,'50k',0,None,None,'qualifier',0],['5',0,'Half marathon',DATE,21.1,0,'20k',0,None,None,'qualifier',0],['6',0,'Fifty kilometres',DATE,50,0,'50k',0,None,None,'qualifier',0]]
itra={'id':'itra:fixture','source':'itra','sourceId':'fixture','sourceUrl':'https://itra.run/Races/RaceCalendar','name':'ITRA marathon','eventName':'Fixtures','date':DATE,'distanceKm':42.16,'longitude':6.87,'latitude':45.92,'locationId':'itra:fixture','countryCode':'FR','country':'France','extensions':{'itra':{'endurancePoints':2}}}
wm={**itra,'id':'worldsmarathons:fixture','source':'worldsmarathons','sourceId':'fixture','sourceUrl':'https://worldsmarathons.com/','distanceKm':42.195,'extensions':{'worldsmarathons':{'listingType':'marathon-event'}}}
data={'schemaVersion':2,'fetchedAt':STAMP,'countries':{'FR':{'name':'France','continent':'Europe'}},'events':[['fixture','Fixtures']],'locations':[['Chamonix','FR',6.87,45.92,'town','1']],'records':rows,'additionalRaces':[{'race':itra,'matchId':None},{'race':wm,'matchId':'utmb:4'}],'coverage':{'from':DATE,'to':DATE,'races':7,'unmapped':0}}
payload=gzip.compress(json.dumps(data).encode())
def count(page,n):
 expect(page.locator('#result-count')).to_have_text(str(n),timeout=20000)
 page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 for mobile in {'desktop':(False,), 'mobile':(True,)}.get(os.environ.get('TEST_DEVICE'),(False,True)):
  c=browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000},is_mobile=mobile,has_touch=mobile,reduced_motion='reduce')
  c.route('**/data/catalog.json.gz',lambda route:route.fulfill(status=200,content_type='application/gzip',body=payload))
  page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded');count(page,7)
  if mobile:page.locator('#open-filters').click()
  button=page.locator('[data-category="42"]');button.click();count(page,5)
  expect(button).to_have_attribute('aria-pressed','true')
  expect(page.locator('#races')).to_contain_text('Marathon graded 20K')
  expect(page.locator('#races')).to_contain_text('Marathon graded 100K')
  page.locator('[data-category="50k"]').click();count(page,6)
  button.click();count(page,3)
  page.locator('[data-category="50k"]').click();count(page,7)
  button.focus();page.keyboard.press('Space');count(page,5)
  page.reload(wait_until='domcontentloaded');count(page,5)
  if mobile:page.locator('#open-filters').click()
  expect(button).to_have_attribute('aria-pressed','true')
  for source,n in [('itra',1),('worldsmarathons',1),('utmb',4),('',5)]:
   page.locator('select[name=source]').select_option(source);count(page,n)
  button.scroll_into_view_if_needed()
  box=button.bounding_box();assert box and box['width']>=30 and box['height']>=30
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  out=Path('/root/race/test-results');out.mkdir(exist_ok=True)
  page.screenshot(path=str(out/('filter42-mobile.png' if mobile else 'filter42-desktop.png')))
  page.locator('#reset').click()
  expect(button).to_have_attribute('aria-pressed','false')
  assert not errors,errors
  print(('Phone' if mobile else 'Desktop')+': independent grades, all sources, category union, keyboard, reload and reset passed',flush=True)
  c.close()
 browser.close()
