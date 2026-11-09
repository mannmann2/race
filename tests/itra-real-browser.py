"""Verify published real bulk data, map points, both source links, ratings and mobile."""
from ui_filters import select_sources
import gzip,json,os
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads(gzip.decompress((ROOT/'web/data/catalog.json.gz').read_bytes()))
ENTRIES=DATA['additionalRaces']; COUNT=len(ENTRIES)
RATED=sum(e['race']['extensions']['itra']['mountainLevel'] is not None for e in ENTRIES)
SHARED=next(e for e in ENTRIES if e['matchId'] and e['race']['extensions']['itra']['mountainLevel'] is not None)
NEW=next(e for e in ENTRIES if not e['matchId'] and e['race']['longitude'] is not None and e['race']['extensions']['itra']['endurancePoints'] is not None)
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4173').rstrip('/')+'/'
OUT=ROOT/'test-results';OUT.mkdir(exist_ok=True)
HOOK="""let library;Object.defineProperty(window,'maplibregl',{get(){return library},set(v){library=v;
const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}};}});
const W=window.Worker;window.Worker=class extends W{constructor(...a){super(...a);this.addEventListener('message',({data})=>{if(['results','view'].includes(data.type))window.testResults=data;});}};"""
def count(page,n):
 expect(page.locator('#result-count')).to_have_text(f'{n:,}',timeout=30000)
 page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")
def load(page,**extra):
 page.goto(BASE+'#'+urlencode(dict(source='itra',inView='0',when='all',datePreset='any',**extra)),wait_until='domcontentloaded')
 page.wait_for_function("window.testResults && window.testMap && testMap.getLayer('race-points')",timeout=60000)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 errors=[]
 c=b.new_context(bypass_csp=True,viewport={'width':1380,'height':1000},reduced_motion='reduce')
 page=c.new_page();page.add_init_script(HOOK);page.on('pageerror',lambda e:errors.append(str(e)))
 load(page);count(page,COUNT)
 expect(page.locator('#itra-status')).to_contain_text('Rolling 12-month calendar')
 assert sum(x['count'] for x in page.evaluate('testResults.points'))>3000
 select_sources(page,'both');count(page,DATA['mergeSummary']['merged'])
 select_sources(page,'itra')
 page.locator('select[name=mountainMin]').select_option('0');count(page,RATED)
 load(page,q=SHARED['race']['eventName'])
 card=page.locator(f'#races [data-race="{SHARED["matchId"]}"]')
 card.hover();page.wait_for_function("id => testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId===id",arg=SHARED['matchId'])
 card.click();expect(page.locator('.detail-links a',has_text='View on ITRA')).to_have_attribute('href',SHARED['race']['sourceUrl'])
 expect(page.locator('.detail-links a',has_text='View on UTMB')).to_be_visible()
 expect(page.locator('.itra-details')).to_contain_text(str(int(SHARED['race']['extensions']['itra']['mountainLevel']))+' / 12')
 expect(page.locator('.detail-source')).to_contain_text('Course details')
 page.screenshot(path=str(OUT/'itra-live-shared.png'));c.close()
 print(f'Desktop: {COUNT} ITRA records, {DATA["mergeSummary"]["merged"]} matches, {RATED} Mountain ratings, pins and both links passed.',flush=True)
 c=b.new_context(bypass_csp=True,viewport={'width':390,'height':844},is_mobile=True,has_touch=True,color_scheme='dark',reduced_motion='reduce')
 page=c.new_page();page.add_init_script(HOOK);page.on('pageerror',lambda e:errors.append(str(e)))
 load(page,q=NEW['race']['eventName']);page.locator('#open-filters').tap()
 pts=str(int(NEW['race']['extensions']['itra']['endurancePoints']));page.locator(f'[data-endurance="{pts}"]').tap()
 page.wait_for_function("testResults.items.length && testResults.items.every(r=>r.extensions.itra.endurancePoints===Number(new URLSearchParams(location.hash.slice(1)).get('endurancePoints')))")
 page.locator('#filters-done').tap();page.locator('#show-list').tap()
 page.locator(f'#races [data-race="{NEW["race"]["id"]}"]').tap()
 expect(page.locator('.detail-links a',has_text='View on ITRA')).to_have_attribute('href',NEW['race']['sourceUrl'])
 expect(page.locator('.detail-links a',has_text='View on UTMB')).to_have_count(0)
 assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
 page.screenshot(path=str(OUT/'itra-live-mobile.png'))
 assert not errors,errors
 print('Mobile: real ITRA-only course, Endurance filter, source link and responsive layout passed.',flush=True)
 b.close()
