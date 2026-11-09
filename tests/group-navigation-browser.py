"""Group -> race -> group navigation and direct provider links, desktop and phone."""
import json,os,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4175').rstrip('/')+'/'
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#416f83'}}]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 for mobile in [False,True]:
  c=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844} if mobile else {'width':1440,'height':950},has_touch=mobile,reduced_motion='reduce')
  c.route('**/data/map-style.json',lambda r:r.fulfill(status=200,content_type='application/json',body=json.dumps(STYLE)))
  c.route(re.compile(r'https://(?!race\.slopmaxx\.ing|127\.0\.0\.1|localhost).*'),lambda r:r.fulfill(status=200,content_type='text/html',body='External race page'))
  page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.add_init_script(HOOK)
  page.goto(BASE+'#q=Slate+Trail+Ultra&when=all&datePreset=any&inView=0',wait_until='domcontentloaded')
  page.wait_for_function("window.testMap && testMap.getLayer('race-points') && testMap.isSourceLoaded('races') && document.querySelector('#races').getAttribute('aria-busy')==='false'",timeout=90000)
  # A real marker click resolves the group through the worker.
  page.evaluate("testMap.jumpTo({center:[-4.13,53.23],zoom:5})")
  page.wait_for_function("!testMap.isMoving() && testMap.isSourceLoaded('races')")
  camera=page.evaluate('({center:testMap.getCenter().toArray(),zoom:testMap.getZoom()})')
  page.evaluate("() => {const point=testMap.project([-4.12936,53.22752]);testMap.fire('click',{point,lngLat:testMap.unproject(point)});}")
  dialog=page.locator('#detail-dialog');expect(dialog).to_be_visible(timeout=20000)
  cards=page.locator('.details-group-list [data-race]');expect(cards.first).to_be_visible();count=cards.count();assert count>1
  title=page.locator('#race-title').inner_text();expect(page.locator('#detail-back')).to_be_hidden()
  assert page.locator('.group-race-links a[href*="utmb.world"]').count()>0
  assert page.locator('.group-race-links a[href*="itra.run"]').count()>0
  assert page.locator('.group-race-links a').evaluate_all("els=>els.every(a=>!a.closest('button')&&a.target==='_blank'&&a.rel.includes('noopener'))")
  direct=page.locator('.group-race-links a').first;href=direct.get_attribute('href')
  with c.expect_page() as opened:direct.click()
  external=opened.value;external.wait_for_load_state('domcontentloaded');assert external.url==href;external.close()
  expect(page.locator('.details-group-list')).to_be_visible();assert cards.count()==count
  chosen=cards.nth(1);chosen.scroll_into_view_if_needed();race_id=chosen.get_attribute('data-race');scroll=dialog.evaluate('d=>d.scrollTop')
  chosen.click();expect(page.locator('#detail-back')).to_be_visible();expect(page.locator('.details-group-list')).to_have_count(0)
  assert 'race=' in page.url
  # The back action remains accessible after scrolling the full race detail.
  dialog.evaluate('d=>d.scrollTop=d.scrollHeight');expect(page.locator('#detail-back')).to_be_in_viewport()
  page.locator('#detail-back').click();expect(page.locator('.details-group-list')).to_be_visible();expect(page.locator('#race-title')).to_have_text(title)
  assert cards.count()==count;assert 'race=' not in page.url
  expect(page.locator(f'.details-group-list [data-race="{race_id}"]')).to_be_focused()
  assert abs(dialog.evaluate('d=>d.scrollTop')-scroll)<5
  restored=page.evaluate('({center:testMap.getCenter().toArray(),zoom:testMap.getZoom()})');assert abs(restored['zoom']-camera['zoom'])<.01
  assert all(abs(a-b)<.001 for a,b in zip(restored['center'],camera['center']))
  # Closing the group must not leave a back button on independently opened races.
  page.locator('#detail-close').click()
  if mobile:page.locator('#show-list').click()
  page.locator('#races [data-race]').first.click();expect(dialog).to_be_visible();expect(page.locator('#detail-back')).to_be_hidden()
  assert not errors,errors
  Path('test-results').mkdir(exist_ok=True);page.screenshot(path='test-results/group-navigation-'+('phone' if mobile else 'desktop')+'.png')
  c.close();print(('Phone' if mobile else 'Desktop')+': group back, scroll/focus/camera restoration and direct links passed',flush=True)
 browser.close()
