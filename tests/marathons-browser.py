"""Desktop/mobile checks against the real imported marathon catalogue."""
import datetime as dt
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174')
OUT=ROOT/'test-results';OUT.mkdir(exist_ok=True)
SNAP=json.loads((ROOT/'data/worldsmarathons-snapshot.json').read_text())
HOOK='''
Object.defineProperty(window,'maplibregl',{configurable:true,get(){return this._maplibregl},set(lib){this._maplibregl=lib;const M=lib.Map;lib.Map=class extends M{constructor(...args){super(...args);window.testMap=this;}}}});
const W=window.Worker;window.Worker=class extends W{constructor(...args){super(...args);this.addEventListener('message',({data})=>{if(['results','view'].includes(data.type))window.testResults=data;});}};
'''

def count(page,n):
    expect(page.locator('#result-count')).to_have_text(f'{n:,}',timeout=30000)
    page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    devices={'desktop':(False,), 'mobile':(True,)}.get(os.environ.get('TEST_DEVICE'),(False,True))
    for mobile in devices:
        context=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000},is_mobile=mobile,has_touch=mobile,reduced_motion='reduce')
        page=context.new_page();page.add_init_script(HOOK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'#source=worldsmarathons&inView=0&datePreset=any&when=all',wait_until='domcontentloaded')
        count(page,len(SNAP['races']))
        expect(page.locator('#worldsmarathons-status')).to_contain_text('World’s Marathons listings')
        page.wait_for_function("window.testMap && testMap.getLayer('race-points') && window.testResults?.points?.length>0",timeout=60000)
        if mobile:page.locator('#open-filters').click()
        page.locator('select[name=worldsmarathonsSurface]').select_option('road');count(page,SNAP['coverage']['surfaces']['road'])
        page.reload(wait_until='domcontentloaded');count(page,SNAP['coverage']['surfaces']['road'])
        if mobile:page.locator('#open-filters').click()
        expect(page.locator('select[name=worldsmarathonsSurface]')).to_have_value('road')
        page.locator('select[name=worldsmarathonsSurface]').select_option('trail');count(page,SNAP['coverage']['surfaces']['trail'])
        page.locator('select[name=worldsmarathonsSurface]').select_option('')
        page.locator('[data-when=upcoming]').click()
        today=dt.date.today().isoformat();upcoming=sum((r.get('dateEnd') or r['date'])>=today for r in SNAP['races']);count(page,upcoming)
        page.locator('[data-date="6m"]').click()
        page.locator('#search').fill('Tokyo Marathon');count(page,1)
        if mobile:page.locator('#filters-done').click();page.locator('#show-list').click()
        expect(page.locator('#races')).to_contain_text('Tokyo Marathon')
        expect(page.locator('#races')).to_contain_text('World’s Marathons')
        if not mobile:
            page.locator('#races .race-card').hover()
            page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId.includes('tokyo-marathon')")
        page.locator('#races .race-card').click()
        expect(page.locator('#detail-content')).to_contain_text('7 March 2027')
        expect(page.locator('.detail-links a',has_text='View on World’s Marathons')).to_have_attribute('href','https://worldsmarathons.com/marathon/tokyo-marathon')
        page.wait_for_function("[...document.querySelectorAll('.detail-image')].some(i=>i.complete&&i.naturalWidth>0)",timeout=25000)
        page.screenshot(path=str(OUT/('marathons-mobile-detail.png' if mobile else 'marathons-desktop-detail.png')))
        page.locator('#detail-close').click()
        if mobile:page.locator('#list-close').click()
        page.locator('#theme-toggle').click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'horizontal overflow'
        if not mobile:
            page.locator('#in-view').check();count(page,1)
            page.evaluate("testMap.jumpTo({center:[-40,-25],zoom:1})")
            count(page,0)
            page.locator('#in-view').uncheck();count(page,1)
            page.locator('#search').fill('')
            page.wait_for_function("window.testResults?.globalTotal>1")
            page.locator('select[name=worldsmarathonsSurface]').scroll_into_view_if_needed()
            page.screenshot(path=str(OUT/'marathons-desktop-dark.png'))
        assert not errors,errors
        print(('Mobile' if mobile else 'Desktop')+': source, surfaces, URL persistence, upcoming, dates, map, image, details and themes passed',flush=True)
        context.close()
    browser.close()
