"""Exercise the real worker/globe/UI with synthetic multi-source responses.

Fixtures are intercepted in this browser only; never written to the public data.
"""
import datetime
import gzip
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get('TEST_URL', 'http://127.0.0.1:4174').rstrip('/') + '/'
OUT = Path(__file__).resolve().parents[1] / 'test-results'
OUT.mkdir(exist_ok=True)
DATE = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
STAMP = datetime.datetime.now(datetime.timezone.utc).isoformat()
HOOK = """
let library;Object.defineProperty(window,'maplibregl',{get(){return library},set(v){library=v;
const M=v.Map;v.Map=class extends M{constructor(...a){super(...a);window.testMap=this;}};}});
const W=window.Worker;window.Worker=class extends W{constructor(...a){super(...a);this.addEventListener('message',({data})=>{if(['results','view'].includes(data.type))window.testResults=data;});}};
"""


def itra(i, name, points, mountain, lon):
    return {'id': f'itra:{DATE[:4]}:{i}', 'sourceId': f'{DATE[:4]}:{i}', 'source': 'itra',
            'sourceUrl': f'https://itra.run/Races/RaceDetails/Fixture/{DATE[:4]}/{i}',
            'name': name, 'eventName': 'Fixture Alpine', 'date': DATE, 'datePrecision': 'race',
            'countryCode': 'FR', 'country': 'France', 'continent': 'Europe', 'place': 'Chamonix',
            'longitude': lon, 'latitude': 45.92, 'locationId': f'itra:place:{i}', 'locationPrecision': 'town',
            'distanceKm': 50.2, 'elevationGainM': 2500, 'website': None, 'image': None, 'imageSource': None,
            'extensions': {'itra': {'endurancePoints': points, 'mountainLevel': mountain, 'finisherLevel': 320}}}


DATA = {'schemaVersion': 2, 'fetchedAt': STAMP,
        'countries': {'FR': {'name': 'France', 'continent': 'Europe'}},
        'events': [['utmb:event:1', 'Fixture Alpine']], 'locations': [['Chamonix', 'FR', 6.87, 45.92, 'town', '1']],
        'records': [['1', 0, 'Fixture Alpine 50K', DATE, 50, 2500, '50k', 0, None, 'fixture.1', 'serie', 1],
                    ['2', 0, 'UTMB only 100K', DATE, 100, 5000, '100k', 0, None, 'fixture.2', 'qualifier', 0]],
        'additionalRaces': [{'matchId': 'utmb:1', 'race': itra(101, 'Fixture Alpine 50K', 3, 6, 6.87)},
                            {'matchId': None, 'race': itra(102, 'ITRA zero rating', 0, 0, 6.9)},
                            {'matchId': None, 'race': itra(103, 'ITRA unrated', None, None, 6.95)}],
        'coverage': {'from': DATE, 'to': DATE, 'races': 4, 'unmapped': 0},
        'sourceMeta': {'itra': {'races': 3, 'state': 'partial', 'fetchedAt': STAMP}},
        'mergeSummary': {'imported': 3, 'merged': 1, 'unresolved': 0}}
PAYLOAD = gzip.compress(json.dumps(DATA).encode())


def count(page, number):
    expect(page.locator('#result-count')).to_have_text(str(number), timeout=20000)
    page.wait_for_function("document.querySelector('#races').getAttribute('aria-busy')==='false'")


def load(context):
    context.route('**/data/catalog.json.gz', lambda route: route.fulfill(status=200, content_type='application/gzip', body=PAYLOAD))
    page = context.new_page()
    page.add_init_script(HOOK)
    page.goto(BASE + '#inView=0', wait_until='domcontentloaded')
    page.wait_for_function("window.testMap && testMap.getLayer('race-points') && window.testResults", timeout=60000)
    count(page, 4)
    return page


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--enable-unsafe-swiftshader'])
    errors = []
    context = browser.new_context(viewport={'width': 1380, 'height': 1000}, color_scheme='light', reduced_motion='reduce')
    context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
    page = load(context)
    expect(page.locator('#itra-status')).to_contain_text('3 ITRA courses')
    page.locator('select[name=source]').select_option('both')
    count(page, 1)
    expect(page.locator('#races .grade-icon-utmb')).to_have_attribute('alt','UTMB 50K')
    expect(page.locator('#races .grade-icon-itra')).to_have_attribute('alt','ITRA 3 Endurance Points')
    page.locator('#races .race-card').hover()
    page.wait_for_function("testMap.getSource('race-highlight').serialize().data.features[0]?.properties.raceId==='utmb:1'")
    page.locator('#races .race-card').click()
    expect(page.locator('.detail-links a', has_text='View on UTMB')).to_have_attribute('href', 'https://utmb.world/utmb-index/races/fixture.1')
    expect(page.locator('.detail-links a', has_text='View on ITRA')).to_have_attribute('href', f'https://itra.run/Races/RaceDetails/Fixture/{DATE[:4]}/101')
    expect(page.locator('.itra-details')).to_contain_text('3 / 6')
    expect(page.locator('.itra-details')).to_contain_text('6 / 12')
    expect(page.locator('.source-conflicts')).to_contain_text('UTMB 50 · ITRA 50.2')
    page.screenshot(path=str(OUT / 'sources-detail-light.png'))
    page.locator('#detail-close').click()
    page.locator('select[name=source]').select_option('')
    page.locator('[data-endurance="0"]').click()
    count(page, 1)
    expect(page.locator('#races')).to_contain_text('ITRA zero rating')
    page.locator('[data-endurance="3"]').click()
    count(page, 2)
    page.locator('select[name=mountainMax]').select_option('0')
    count(page, 1)
    page.locator('#theme-toggle').click()
    page.reload(wait_until='domcontentloaded')
    count(page, 1)
    expect(page.locator('[data-endurance="0"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('[data-endurance="3"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('select[name=mountainMax]')).to_have_value('0')
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
    page.locator('select[name=source]').select_option('utmb')
    count(page, 0)
    page.locator('#reset').click()
    expect(page.locator('[data-date="6m"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('[data-when=upcoming]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('select[name=mountainMax]')).to_have_value('')
    page.wait_for_function("testMap.getLayer('race-points')")
    page.evaluate("testMap.jumpTo({center:[6.9,45.92],zoom:4})")
    count(page, 4)
    # A cluster opens the grouped modal and preserves zoom.
    page.wait_for_function("testMap.isSourceLoaded('races')")
    point = page.evaluate("""() => {const m=testMap,f=m.queryRenderedFeatures({layers:['race-clusters','race-points']})[0],p=m.project(f.geometry.coordinates),b=m.getCanvas().getBoundingClientRect();return {x:b.x+p.x,y:b.y+p.y,zoom:m.getZoom()};}""")
    page.mouse.click(point['x'], point['y'])
    expect(page.locator('.group-dialog-title')).to_be_visible()
    expect(page.locator('.details-group-list .race-card')).to_have_count(4)
    assert page.evaluate('testMap.getZoom()') == point['zoom']
    page.locator('#detail-close').click()
    page.evaluate("testMap.jumpTo({center:[-100,30],zoom:5})")
    count(page, 0)
    page.evaluate("testMap.jumpTo({center:[6.9,45.92],zoom:4})")
    count(page, 4)
    page.screenshot(path=str(OUT / 'sources-desktop-dark.png'))
    print('Desktop: dedup counts, both links, conflicts, zero/unknown ratings, combined filters, URL persistence, reset, map groups and viewport passed', flush=True)
    context.close()

    context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, color_scheme='dark', reduced_motion='reduce')
    context.on('page', lambda page: page.on('pageerror', lambda error: errors.append(str(error))))
    page = load(context)
    page.locator('#open-filters').tap()
    page.locator('select[name=source]').select_option('itra')
    page.locator('[data-endurance="3"]').tap()
    page.locator('select[name=mountainMin]').select_option('6')
    page.locator('select[name=mountainMax]').select_option('6')
    count(page, 1)
    page.screenshot(path=str(OUT / 'sources-mobile-filters.png'))
    page.locator('#filters-done').tap()
    page.locator('#show-list').tap()
    page.locator('#races .race-card').tap()
    expect(page.locator('.itra-details')).to_contain_text('3 / 6')
    expect(page.locator('.detail-links a', has_text='View on ITRA')).to_be_visible()
    page.screenshot(path=str(OUT / 'sources-mobile-detail.png'))
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.locator('#detail-close').tap()
    page.locator('#list-close').tap()
    page.locator('#theme-toggle').tap()
    expect(page.locator('html')).to_have_attribute('data-theme', 'light')
    print('Mobile: touch filters, combined ratings, links, detail layout, and theme switching passed', flush=True)
    assert not errors, errors
    browser.close()
