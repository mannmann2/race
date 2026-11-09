"""Release gate: payload loading, sharing, mobile focus, fallbacks, cache and CSP."""
import json,os,re,time
from pathlib import Path
from urllib.request import urlopen,Request
from playwright.sync_api import sync_playwright,expect
os.environ['PW_TEST_SCREENSHOT_NO_FONTS_READY']='1'
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174').rstrip('/')+'/'
NAME=os.environ.get('TEST_BROWSER','chromium');OUT=Path('test-results/launch');OUT.mkdir(parents=True,exist_ok=True)
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
with sync_playwright() as p:
 browser=getattr(p,NAME).launch(headless=True,**({'args':['--no-sandbox','--enable-unsafe-swiftshader']} if NAME=='chromium' else {}))
 for mobile in [False,True]:
  c=browser.new_context(viewport={'width':390,'height':844} if mobile else {'width':1440,'height':900},has_touch=mobile,color_scheme='light',reduced_motion='reduce')
  requests=[];errors=[];c.on('request',lambda r:requests.append(r.url))
  c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
  c.route(re.compile(r'https://(?!race\.slopmaxx\.ing|127\.0\.0\.1|localhost).*'),lambda r:r.abort())
  page=c.new_page();page.set_default_timeout(25000);page.add_init_script(HOOK);page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE,wait_until='domcontentloaded');expect(page.locator('#races')).to_have_attribute('aria-busy','false',timeout=90000)
  expect(page.locator('[data-when="upcoming"]')).to_have_attribute('aria-pressed','true');expect(page.locator('[data-date="6m"]')).to_have_attribute('aria-pressed','true')
  assert any('catalog-upcoming-' in u for u in requests),requests
  assert not any(re.search(r'/catalog-[a-f0-9]{16}\.json\.gz',u) for u in requests),requests
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight')
  if mobile:
   page.locator('#open-filters').click();expect(page.locator('#filters-panel')).to_have_attribute('aria-modal','true');assert page.locator('.header').evaluate('e=>e.inert')
   page.locator('#filters-done').focus();page.keyboard.press('Tab');assert page.evaluate("!!document.activeElement.closest('#filters-panel')")
   page.keyboard.press('Escape');expect(page.locator('#open-filters')).to_be_focused();assert not page.locator('.header').evaluate('e=>e.inert')
   page.locator('#show-list').click()
  else:page.locator('#in-view').uncheck()
  page.locator('#races .race-card').first.click();expect(page.locator('#detail-dialog')).to_be_visible();expect(page.locator('#detail-dialog')).to_have_attribute('aria-labelledby','race-title')
  expect(page.locator('[data-share-race]')).to_be_visible();expect(page.locator('.detail-actions a')).to_have_attribute('href',re.compile('https://github.com/mannmann2/race/issues/new'))
  expect(page).to_have_url(re.compile(r'[&#]race='))
  shared=page.url;race=page.locator('#race-title').inner_text()
  page.locator('[data-share-race]').click()
  if page.locator('#share-dialog').is_visible():expect(page.locator('#share-link')).to_have_value(shared);page.locator('#share-close').click()
  else:expect(page.locator('#app-status')).to_be_visible()
  page.screenshot(path=str(OUT/(NAME+('-phone' if mobile else '-desktop')+'.png')))
  # Reload a selected race: the worker must resolve it even outside the current list.
  page.goto(shared,wait_until='domcontentloaded');expect(page.locator('#detail-dialog')).to_be_visible(timeout=90000);expect(page.locator('#race-title')).to_have_text(race)
  page.locator('#detail-close').click()
  if mobile:page.locator('#list-close').click() if page.locator('#race-results').evaluate('e=>e.classList.contains("open")') else None
  page.locator('#theme-toggle').click();expect(page.locator('html')).to_have_attribute('data-theme','dark')
  assert not errors,errors;c.close()
  print(NAME+(': phone focus, sharing and dark mode passed' if mobile else ': fast initial payload, race deep links and desktop passed'),flush=True)
 # History is loaded on demand; a map failure must leave all data browsable.
 c=browser.new_context(viewport={'width':1280,'height':800});c.route('**/data/map-style.json',lambda r:r.abort())
 page=c.new_page();page.goto(BASE+'#when=all&datePreset=any&inView=0',wait_until='domcontentloaded');expect(page.locator('#races .race-card').first).to_be_visible(timeout=90000)
 expect(page.locator('.error-banner')).to_be_visible();assert not page.locator('#in-view').is_checked()
 count=page.locator('#result-count').inner_text();assert int(count.replace(',',''))>0
 page.locator('#about-open').click();expect(page.locator('#about-dialog')).to_have_attribute('aria-labelledby','about-title');expect(page.locator('#privacy-title')).to_be_visible()
 c.close();browser.close();print(NAME+': archive browsing and map-failure fallback passed ('+count+' races)',flush=True)
# Exercise the actual HTTP contract as well as the browser.
with urlopen(Request(BASE+'app.mjs',headers={'Accept-Encoding':'br'}),timeout=15) as r:
 headers=r.headers;assert headers.get('Content-Security-Policy');etag=headers.get('ETag');assert etag
try:
 with urlopen(Request(BASE+'app.mjs',headers={'If-None-Match':etag,'Accept-Encoding':'br'}),timeout=15) as r:assert False,r.status
except __import__('urllib.error').error.HTTPError as e:assert e.code==304,e.code
print('HTTP: security headers and conditional requests passed.',flush=True)
# An optional archive outage must preserve browsing of the smaller upcoming payload.
with sync_playwright() as p:
 b=getattr(p,NAME).launch(headless=True,**({'args':['--no-sandbox']} if NAME=='chromium' else {}))
 c=b.new_context();c.route('**/data/map-style.json',lambda r:r.abort())
 c.route(re.compile(r'.*/catalog-[a-f0-9]{16}\.json\.gz$'),lambda r:r.fulfill(status=503,body='Temporarily unavailable'))
 page=c.new_page();page.goto(BASE,wait_until='domcontentloaded');expect(page.locator('#races')).to_have_attribute('aria-busy','false',timeout=90000)
 page.locator('[data-when="past"]').click();expect(page.locator('[data-when="upcoming"]')).to_have_attribute('aria-pressed','true',timeout=30000)
 expect(page.locator('#races .race-card').first).to_be_visible();expect(page.locator('.error-state')).to_have_count(0)
 c.close();b.close()
print(NAME+': archive failure preserves upcoming browsing.',flush=True)
