"""Verify actual three-source records and the light-mode surround on both layouts."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4174')
OUT=Path(__file__).resolve().parents[1]/'test-results'
OUT.mkdir(exist_ok=True)
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}}}});"""
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    for mobile in (False,True):
        context=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844} if mobile else {'width':1440,'height':1000},is_mobile=mobile,has_touch=mobile,color_scheme='light',reduced_motion='reduce')
        page=context.new_page();page.add_init_script(HOOK);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE+'#inView=0',wait_until='domcontentloaded')
        page.wait_for_function("window.testMap?.getLayer('race-points') && testMap.isSourceLoaded('races') && document.querySelector('#races .race-card')",timeout=60000)
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        assert page.locator('.globe-panel').evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(229, 227, 222)'
        page.screenshot(path=str(OUT/('stone-mobile.png' if mobile else 'stone-desktop.png')))
        if mobile:page.locator('#open-filters').click()
        page.locator('#search').fill('Guatemala Impact Marathon Beast')
        expect(page.locator('#result-count')).to_have_text('1',timeout=30000)
        for source in ['worldsmarathons','utmb','itra','both','']:
            page.locator('select[name=source]').select_option(source)
            expect(page.locator('#result-count')).to_have_text('1')
        if mobile:
            page.locator('#filters-done').click();page.locator('#show-list').click()
        expect(page.locator('#races .race-card')).to_have_count(1)
        page.locator('#races .race-card').click()
        for label in ['View on UTMB','View on ITRA','View on World’s Marathons']:
            expect(page.locator('.detail-links a',has_text=label)).to_have_count(1)
        expect(page.locator('.itra-details')).to_contain_text('Endurance')
        page.screenshot(path=str(OUT/('three-source-mobile.png' if mobile else 'three-source-desktop.png')))
        page.locator('#detail-close').click()
        if mobile:page.locator('#list-close').click()
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        assert page.locator('.globe-panel').evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(23, 21, 31)'
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        print(('Mobile' if mobile else 'Desktop')+': light surround, theme toggle, three source filters/links, unique card and ITRA ratings passed',flush=True)
        context.close()
    browser.close()
