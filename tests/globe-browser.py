"""Focused globe interaction regressions; run against TEST_URL (default :4173)."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('TEST_URL', 'http://127.0.0.1:4173').rstrip('/') + '/'
OUT = Path(__file__).resolve().parents[1] / 'test-results'
OUT.mkdir(exist_ok=True)
HOOK = """
let lib;
Object.defineProperty(window,'maplibregl',{get(){return lib},set(v){lib=v;
const M=v.Map;v.Map=class extends M{constructor(...args){super(...args);window.testMap=this;}};}});
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--enable-unsafe-swiftshader'])
    page = browser.new_page(viewport={'width': 1280, 'height': 860})
    page.add_init_script(HOOK)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until='domcontentloaded')
    page.wait_for_function("window.testMap && testMap.getLayer('race-highlight-point') && testMap.isSourceLoaded('races')", timeout=60000)
    page.wait_for_selector('#races .race-card', timeout=60000)
    page.wait_for_function("!testMap.isMoving() && document.querySelector('#races').getAttribute('aria-busy')==='false'")
    # Back-to-back filters must not drop the point data with a stale worker response.
    page.locator('#search').fill('no-such-race-marker-regression')
    page.wait_for_function("document.querySelector('.empty-state') && testMap.getSource('races').serialize().data.features.length===0")
    page.evaluate("""() => {
      const search=document.querySelector('#search'),sort=document.querySelector('#sort');
      search.value='';search.dispatchEvent(new Event('input',{bubbles:true}));
      sort.value='distance';sort.dispatchEvent(new Event('change',{bubbles:true}));
      sort.value='soonest';sort.dispatchEvent(new Event('change',{bubbles:true}));
    }""")
    page.wait_for_function("testMap.getSource('races').serialize().data.features.length>0 && testMap.isSourceLoaded('races') && document.querySelector('#races .race-card')")
    print('Markers recover after empty results and rapid filter changes', flush=True)
    page.evaluate("""async () => {
      const {Globe}=await import('./globe.mjs');
      window.probe=Object.create(Globe.prototype);
      Object.assign(probe,{map:testMap,container:document.querySelector('#globe'),ready:true});
    }""")
    # Real renderer queries can report hidden races; only front-facing hits should survive.
    hits = page.evaluate("""() => {
      const map=testMap,rect=map.getCanvas().getBoundingClientRect();
      const result={outside:[],hidden:[],front:null};
      for(let y=5;y<rect.height;y+=14)for(let x=5;x<rect.width;x+=14){
        const point={x,y},raw=map.queryRenderedFeatures([[x-8,y-8],[x+8,y+8]],{layers:['race-clusters','race-points']});
        if(!raw.length)continue;
        const actual=probe.featuresAt(point),on=map.transform.isPointOnMapSurface(point,map.terrain);
        if(!on){if(actual.length)throw Error('Outside globe selectable');if(result.outside.length<3)result.outside.push(point);}
        const hiddenOnly=raw.every(f=>map.transform.isLocationOccluded(maplibregl.LngLat.convert(f.geometry.coordinates)));
        if(hiddenOnly){if(actual.length)throw Error('Hidden hemisphere selectable');if(result.hidden.length<3)result.hidden.push(point);}
        if(!result.front && actual[0]?.properties.cluster && document.elementFromPoint(rect.x+x,rect.y+y)?.classList.contains('maplibregl-canvas'))result.front=point;
      }
      return result;
    }""")
    assert hits['outside'] and hits['hidden'] and hits['front'], hits
    bounds = page.locator('#globe').bounding_box()
    for point in hits['outside']:
        page.mouse.move(bounds['x'] + point['x'], bounds['y'] + point['y'])
        page.mouse.click(bounds['x'] + point['x'], bounds['y'] + point['y'])
        expect(page.locator('#detail-dialog')).not_to_be_visible()
        expect(page.locator('#tooltip')).not_to_be_visible()
    point = hits['front']
    page.mouse.move(bounds['x'] + point['x'], bounds['y'] + point['y'])
    expect(page.locator('#tooltip')).to_be_visible(timeout=15000)
    assert 'Approximate location' not in page.locator('#tooltip').inner_text()
    assert 'Click to' not in page.locator('#tooltip').inner_text()
    zoom = page.evaluate('testMap.getZoom()')
    page.mouse.click(bounds['x'] + point['x'], bounds['y'] + point['y'])
    expect(page.locator('#detail-dialog')).to_be_visible(timeout=15000)
    assert abs(page.evaluate('testMap.getZoom()') - zoom) < .001
    page.keyboard.press('Escape')
    print('Outside/hidden markers rejected; visible marker hover and group click passed', flush=True)

    # Calendar hover and keyboard focus set a location highlight and clear on exit.
    card = page.locator('#races .race-card').first
    race_id = card.get_attribute('data-race')
    card.hover()
    page.wait_for_function("id=>testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId===id", arg=race_id)
    page.screenshot(path=str(OUT / 'calendar-highlight.png'))
    page.mouse.move(30, 30)
    page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features.length===0")
    card.focus()
    page.wait_for_function("id=>testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId===id", arg=race_id)
    page.locator('#results-toggle').focus()
    page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features.length===0")

    # A worldwide race behind the camera is brought into view at the current zoom.
    page.evaluate("probe.highlight({id:'far-side-check',longitude:160,latitude:-35})")
    page.wait_for_function("!testMap.isMoving() && Math.abs(testMap.getCenter().lng-160)<.1")
    assert abs(page.evaluate('testMap.getZoom()') - zoom) < .001
    assert page.evaluate('!!probe.visibleScreenPoint([160,-35])')
    page.evaluate('probe.highlight(null)')
    for center, zoom_level in [([-179, 60], 2), ([179, -45], 2), ([7, 46], 9)]:
        page.evaluate('(v)=>{testMap.jumpTo({center:v[0],zoom:v[1]});}', [center, zoom_level])
        assert page.evaluate('(c)=>!!probe.visibleScreenPoint(c)', center)
    assert not errors, errors
    print('Calendar hover/focus, clearing, far-side reveal and detailed zoom passed', flush=True)

    phone = browser.new_page(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True)
    phone.add_init_script(HOOK)
    phone.on('pageerror', lambda e: errors.append(str(e)))
    phone.goto(BASE, wait_until='domcontentloaded')
    phone.wait_for_function("window.testMap && testMap.getLayer('race-highlight-point')", timeout=60000)
    phone.locator('#show-list').tap()
    phone.locator('#races .race-card').first.tap()
    expect(phone.locator('#detail-dialog')).to_be_visible(timeout=15000)
    assert not phone.evaluate('document.documentElement.scrollWidth>innerWidth')
    assert not errors, errors
    print('Phone calendar and race details passed', flush=True)
    browser.close()
