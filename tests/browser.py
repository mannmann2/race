"""End-to-end checks; run a local server and set TEST_URL for its address."""
import gzip,json,os,pathlib,time
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4173').rstrip('/')+'/'
OUT=pathlib.Path(__file__).resolve().parents[1]/'test-results';OUT.mkdir(exist_ok=True)
EXPECTED=int(json.loads(gzip.decompress((OUT.parent/'web/data/catalog.json.gz').read_bytes()))['coverage']['races'])
HOOK="""
let library;
Object.defineProperty(window,'maplibregl',{configurable:true,get(){return library;},set(value){library=value;const Map=value.Map;value.Map=class extends Map{constructor(...args){super(...args);window.testMap=this;}};}});
const NativeWorker=window.Worker;
window.Worker=class extends NativeWorker {constructor(...args){super(...args);this.addEventListener('message',({data})=>{if(['results','view'].includes(data.type))window.testResults=data;});}};
"""
def settle(page):
    page.wait_for_function("window.testResults && document.querySelector('#races').getAttribute('aria-busy')==='false'",timeout=60000)
    page.wait_for_timeout(250)
def loaded(page):
    page.goto(BASE,wait_until='domcontentloaded')
    page.wait_for_function("window.testMap && window.testMap.getLayer('race-points') && window.testResults",timeout=60000)
    page.wait_for_selector('.race-card',state='attached',timeout=60000);settle(page)

def details_match_view(page):
    return page.evaluate("""() => {
      const map=testMap,canvas=map.getCanvas();
      return testResults.items.every(r=>{
        if(r.longitude==null)return false;
        const p=map.project([r.longitude,r.latitude]);if(p.x<0||p.y<0||p.x>canvas.clientWidth||p.y>canvas.clientHeight)return false;
        const back=map.unproject(p);return Math.abs(((back.lng-r.longitude+540)%360)-180)<.1 && Math.abs(back.lat-r.latitude)<.1;
      });
    }""")
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    errors=[]
    if os.environ.get('TEST_SCOPE')!='mobile':
        page=browser.new_page(viewport={'width':1280,'height':860});errors=[]
        page.add_init_script(HOOK);page.on('pageerror',lambda error:errors.append(str(error)))
        start=time.monotonic();loaded(page);print(f'Globe + initial calendar ready in {time.monotonic()-start:.2f}s',flush=True)
        expect(page.locator('[data-date="6m"]')).to_have_attribute('aria-pressed','true')
        expect(page.locator('[data-when="upcoming"]')).to_have_attribute('aria-pressed','true')
        assert details_match_view(page)
        page.screenshot(path=str(OUT/'desktop.png'))
        if os.environ.get('TEST_SCOPE')!='map':
            # Calendar month presets and custom dates.
            for preset in ['2w','1m','3m','6m','12m']:
                page.locator('[data-date="'+preset+'"]').click();settle(page)
                expect(page.locator('[data-date="'+preset+'"]').first).to_have_attribute('aria-pressed','true')
                assert page.locator('input[name="from"]').input_value()==time.strftime('%Y-%m-%d')
            page.locator('[data-date="6m"]').click();settle(page)
            # Both distance thumbs are operable using keyboard; numeric inputs remain precise.
            page.locator('#distance-low').focus();page.keyboard.press('ArrowRight');page.keyboard.press('ArrowRight');page.wait_for_timeout(250);settle(page)
            assert float(page.locator('input[name="distanceMin"]').input_value())==2
            page.locator('#distance-high').focus();page.keyboard.press('ArrowLeft');page.wait_for_timeout(250);settle(page)
            assert page.locator('input[name="distanceMax"]').input_value()=='499'
            page.locator('input[name="distanceMin"]').fill('25');page.locator('input[name="distanceMax"]').fill('60');page.wait_for_timeout(250);settle(page)
            assert all(25<=r['distanceKm']<=60 for r in page.evaluate('testResults.items'))
            # World Series is a source classification, including Majors and Finals.
            page.locator('#world-series').click();settle(page)
            assert page.evaluate("testResults.items.length>0 && testResults.items.every(r=>['serie','major','finale'].includes(r.extensions.utmb.level))")
            print('Presets, both slider handles, and World Series passed',flush=True)
            # Viewport reacts to navigation and accurately rejects the far side.
            page.evaluate('testMap.jumpTo({center:[138,36],zoom:4})');page.wait_for_timeout(600);settle(page)
            assert details_match_view(page)
            first_ids=page.evaluate('testResults.items.map(r=>r.id)')
            page.evaluate('testMap.jumpTo({center:[7,45],zoom:4})');page.wait_for_timeout(600);settle(page)
            assert details_match_view(page);assert first_ids!=page.evaluate('testResults.items.map(r=>r.id)')
            # Collapse expands map and recalculates viewport; restore preserves zoom.
            before=page.locator('#globe').bounding_box()['width'];page.locator('#results-toggle').click();page.wait_for_timeout(350)
            assert page.locator('#globe').bounding_box()['width']>before+200
            expect(page.locator('#race-results')).not_to_be_visible()
            page.locator('#results-toggle').click();page.wait_for_timeout(350);expect(page.locator('#race-results')).to_be_visible()
            print('Viewport and collapse passed',flush=True)
            # Worldwide includes unknown locations, and all dates reach the full source dataset.
            page.locator('#in-view').uncheck();page.locator('#reset').click();page.locator('#in-view').uncheck();page.locator('[data-when="all"]').click();settle(page)
            expect(page.locator('#result-count')).to_have_text(f'{EXPECTED:,}')
            page.locator('#load-more').scroll_into_view_if_needed();page.locator('#load-more').click();expect(page.locator('.race-card')).to_have_count(120)
            page.locator('select[name="continent"]').select_option('Europe');settle(page)
            page.locator('.country-picker summary').click();page.locator('#country-options input[value="FR"]').check();page.locator('#country-options input[value="IT"]').check();page.locator('.country-picker summary').click();settle(page)
            assert page.evaluate("testResults.items.every(r=>r.continent==='Europe'&&['FR','IT'].includes(r.countryCode))")
            page.locator('[data-category="50k"]').click();settle(page)
            assert page.evaluate("testResults.items.every(r=>r.extensions.utmb.category==='50k')")
            saved=page.url;count=page.locator('#result-count').inner_text();page.reload();page.wait_for_function('window.testResults',timeout=60000);settle(page)
            expect(page.locator('#result-count')).to_have_text(count);assert page.url==saved
            page.locator('.race-card').first.click();expect(page.locator('#detail-dialog')).to_be_visible();page.keyboard.press('Escape')
            page.locator('#reset').click();page.locator('#in-view').uncheck();page.locator('#world-series').click();settle(page)
            assert page.locator('.race-photo').count()>0
            # Actual remote photos render, rather than just URLs being present.
            page.wait_for_function("[...document.querySelectorAll('.race-photo')].some(i=>i.complete&&i.naturalWidth>0)",timeout=30000)
            page.locator('.race-card.has-photo').first.click();expect(page.locator('#detail-dialog')).to_be_visible();expect(page.locator('.detail-image')).to_be_visible();page.keyboard.press('Escape')
            print('Worldwide data, URL state, pagination and real images passed',flush=True)
        # Cluster clicks and shared-location clicks open the same race-list modal.
        page.locator('#reset').click();settle(page);page.evaluate('testMap.jumpTo({center:[12,25],zoom:2.1})');page.wait_for_timeout(800)
        page.wait_for_function("testMap.loaded() && testMap.isSourceLoaded('races') && !testMap.isMoving() && testMap.queryRenderedFeatures({layers:['race-clusters','race-points']}).length>0")
        point=page.evaluate("""() => {const r=document.querySelector('#globe').getBoundingClientRect();for(let y=110;y<r.height-150;y+=16)for(let x=55;x<r.width-55;x+=16){const found=testMap.queryRenderedFeatures([x,y],{layers:['race-clusters','race-points']});if(found.some(f=>f.properties.cluster) && document.elementFromPoint(r.x+x,r.y+y)?.classList.contains('maplibregl-canvas'))return {x:r.x+x,y:r.y+y};}return null;}""")
        page.mouse.move(point['x'],point['y']);expect(page.locator('#tooltip')).to_be_visible(timeout=10000)
        zoom=page.evaluate('testMap.getZoom()');page.mouse.click(point['x'],point['y']);page.wait_for_timeout(700)
        expect(page.locator('#detail-dialog')).to_be_visible()
        assert abs(page.evaluate('testMap.getZoom()')-zoom)<0.001
        if page.locator('#detail-dialog').is_visible():page.keyboard.press('Escape')
        page.locator('#reset').click();page.locator('#search').fill('no-such-race-xxxx');page.wait_for_timeout(300);settle(page);expect(page.locator('.empty-state')).to_be_visible()
        page.locator('#empty-reset').click();settle(page)
        page.evaluate('testMap.jumpTo({center:[7,46],zoom:9})');page.wait_for_timeout(700)
        assert page.locator('[data-map]').count()==0
        assert page.evaluate("!testMap.getSource('terrain-tiles') && !testMap.getLayer('terrain-map')")
        page.screenshot(path=str(OUT/'zoomed-map.png'))
        assert not errors,errors;print('Map: marker hover/click, group modal without zoom and deep zoom passed' if os.environ.get('TEST_SCOPE')=='map' else 'Desktop: presets, dual slider, viewport/far-side filtering, collapse, World Series, photos, URLs, pagination and marker interaction passed',flush=True)
    mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True);mobile.add_init_script(HOOK);mobile.on('pageerror',lambda e:errors.append(str(e)));loaded(mobile)
    assert not mobile.evaluate('document.documentElement.scrollWidth>innerWidth')
    mobile.screenshot(path=str(OUT/'mobile.png'))
    mobile.locator('#open-filters').tap();mobile.locator('[data-date="1m"]').tap();settle(mobile)
    mobile.locator('#distance-low').focus();mobile.keyboard.press('ArrowRight');mobile.wait_for_timeout(250)
    mobile.locator('#filters-done').tap();mobile.locator('#show-list').tap();expect(mobile.locator('#race-results')).to_be_visible()
    mobile.locator('.race-card').first.tap();expect(mobile.locator('#detail-dialog')).to_be_visible();mobile.screenshot(path=str(OUT/'mobile-detail.png'))
    mobile.locator('#detail-close').tap();mobile.locator('#list-close').tap();mobile.locator('#about-open').tap();expect(mobile.locator('#about-dialog')).to_be_visible()
    assert not errors,errors;print('Phone: responsive globe, presets, slider, calendar and details passed',flush=True)
    browser.close()
