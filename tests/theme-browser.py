"""Theme persistence, live map updates and desktop/mobile surface checks."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE=os.environ.get('TEST_URL','http://127.0.0.1:4173').rstrip('/')+'/'
OUT=Path(__file__).resolve().parents[1]/'test-results'
OUT.mkdir(exist_ok=True)
HOOK="""let lib;Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;
const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}};}});"""

def load(page):
    page.goto(BASE,wait_until='domcontentloaded')
    page.wait_for_function("window.testMap && testMap.getLayer('race-points') && testMap.isSourceLoaded('races') && document.querySelector('#races .race-card')",timeout=60000)
    page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    context=browser.new_context(bypass_csp=True,viewport={'width':1280,'height':860},color_scheme='light',reduced_motion='reduce')
    page=context.new_page();page.add_init_script(HOOK)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    load(page)
    expect(page.locator('html')).to_have_attribute('data-theme','light')
    page.screenshot(path=str(OUT/'theme-light.png'))
    before=page.evaluate("""() => {window.originalRaceSource=testMap.getSource('races');return {hash:location.hash,center:testMap.getCenter().toArray(),zoom:testMap.getZoom(),points:originalRaceSource.serialize().data.features.length,count:document.querySelector('#result-count').textContent,water:testMap.getPaintProperty('water','fill-color')};}""")
    page.locator('#theme-toggle').focus();page.keyboard.press('Space')
    expect(page.locator('#theme-toggle')).to_have_attribute('aria-pressed','true')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    page.wait_for_timeout(500)
    after=page.evaluate("""() => ({hash:location.hash,center:testMap.getCenter().toArray(),zoom:testMap.getZoom(),points:testMap.getSource('races').serialize().data.features.length,count:document.querySelector('#result-count').textContent,water:testMap.getPaintProperty('water','fill-color')})""")
    assert before.pop('water')!=after.pop('water')
    assert before==after,(before,after)
    assert page.evaluate("originalRaceSource===testMap.getSource('races')")
    assert page.evaluate("localStorage.getItem('race-atlas-theme')==='dark'")
    page.screenshot(path=str(OUT/'theme-dark.png'))
    # Visible bubbles still produce hover cards and open the race modal after switching.
    point=page.evaluate("""async () => {
      const {Globe}=await import('./globe.mjs'),g=Object.create(Globe.prototype),m=testMap;
      Object.assign(g,{map:m,ready:true,container:document.querySelector('#globe')});
      const r=m.getCanvas().getBoundingClientRect();
      for(let y=110;y<r.height-150;y+=14)for(let x=40;x<r.width-40;x+=14)
        if(g.featuresAt({x,y}).length&&document.elementFromPoint(r.x+x,r.y+y)?.classList.contains('maplibregl-canvas'))return {x:r.x+x,y:r.y+y};
    }""")
    assert point
    page.mouse.move(point['x'],point['y']);expect(page.locator('#tooltip')).to_be_visible(timeout=15000)
    page.screenshot(path=str(OUT/'theme-dark-tooltip.png'))
    page.mouse.click(point['x'],point['y']);expect(page.locator('#detail-dialog')).to_be_visible()
    page.keyboard.press('Escape')
    page.locator('#races .race-card').first.click();expect(page.locator('.detail-body')).to_be_visible()
    page.screenshot(path=str(OUT/'theme-dark-detail.png'))
    page.keyboard.press('Escape')
    page.locator('.country-picker summary').click();expect(page.locator('.country-menu')).to_be_visible()
    page.locator('.country-picker summary').click()
    # Saved choice survives reload and overrides a later OS preference change.
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    page.emulate_media(color_scheme='light')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    page.locator('#theme-toggle').click()
    expect(page.locator('html')).to_have_attribute('data-theme','light')
    print('Desktop: both palettes, keyboard toggle, saved choice, unchanged map/filter state and marker interactions passed',flush=True)
    context.close()

    mobile_context=browser.new_context(bypass_csp=True,viewport={'width':390,'height':844},is_mobile=True,has_touch=True,color_scheme='dark',reduced_motion='reduce')
    mobile=mobile_context.new_page();mobile.add_init_script(HOOK);mobile.on('pageerror',lambda error:errors.append(str(error)))
    load(mobile)
    expect(mobile.locator('html')).to_have_attribute('data-theme','dark')
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    mobile.screenshot(path=str(OUT/'theme-mobile-dark.png'))
    mobile.locator('#open-filters').tap();mobile.screenshot(path=str(OUT/'theme-mobile-filters.png'))
    mobile.locator('#filters-done').tap();mobile.locator('#show-list').tap()
    mobile.screenshot(path=str(OUT/'theme-mobile-calendar.png'))
    mobile.locator('#races .race-card').first.tap();expect(mobile.locator('#detail-dialog')).to_be_visible()
    mobile.locator('#detail-close').tap();mobile.locator('#list-close').tap()
    mobile.locator('#theme-toggle').tap()
    expect(mobile.locator('html')).to_have_attribute('data-theme','light')
    mobile.screenshot(path=str(OUT/'theme-mobile-light.png'))
    mobile_context.close()
    # Restricted storage must not prevent the theme control from working.
    restricted=browser.new_context(bypass_csp=True,color_scheme='dark')
    page=restricted.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
    page.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Denied','SecurityError')}})")
    page.goto(BASE,wait_until='domcontentloaded')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    page.emulate_media(color_scheme='light')
    expect(page.locator('html')).to_have_attribute('data-theme','light')
    page.locator('#theme-toggle').click()
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    assert not errors,errors
    print('Phone: system default, filter/calendar/detail surfaces, touch toggle and restricted storage passed',flush=True)
    browser.close()
