#!/usr/bin/env python3
"""Snapshot UTMB's structured index; geocode locally using GeoNames, never race-page scraping."""
import argparse, collections, datetime, gzip, io, json, os, pathlib, re, time, unicodedata, urllib.parse, urllib.request, zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
API = 'https://api.utmb.world/search/races-qualifiers'
COUNTRIES = 'https://raw.githubusercontent.com/mledoze/countries/master/countries.json'
CITIES = 'https://download.geonames.org/export/dump/cities1000.zip'
MONTHS = dict(zip('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), range(1,13)))

def download(url, headers=None):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=120) as response:
                return response.read()
        except Exception:
            if attempt == 3: raise
            time.sleep(2 ** attempt)

def cached(name, url):
    p = CACHE / name
    if not p.exists(): p.write_bytes(download(url))
    return p.read_bytes()

def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower()).strip()

def date(s):
    try:
        y,m,d = s.split('-')
        return f'{int(y):04}-{MONTHS[m]:02}-{int(d):02}'
    except (ValueError, KeyError, AttributeError): return None

def url(s):
    try: return s if urllib.parse.urlsplit(s or '').scheme in ('http','https') else None
    except ValueError: return None

def fetch_races(end):
    races, offset, expected = [], 0, None
    while True:
        query = urllib.parse.urlencode(dict(lang='en', dateMin='2000-01-01', dateMax=end, limit=100000, offset=offset))
        page = json.loads(download(API+'?'+query, {'x-tenant-id':'worldseries'}))
        if not isinstance(page.get('races'), list) or not isinstance(page.get('nbHits'), int):
            raise ValueError('UTMB feed shape changed; previous snapshot preserved')
        expected = page['nbHits']
        batch = page['races']
        if not batch: break
        races.extend(batch)
        offset += len(batch)
        if offset >= expected: break
        time.sleep(.2)
    unique = {str(r['id']):r for r in races}
    if len(unique) < expected: raise ValueError(f'Incomplete response: {len(unique)} / {expected}')
    return list(unique.values())

def prepare(races, countries_raw, cities_raw):
    countries = {c['cca2']: {'name':c['name']['common'], 'continent':c['region'] if c['region'] != 'Americas' else ('South America' if c['subregion']=='South America' else 'North America')} for c in countries_raw}
    aliases = {'ZR':'CD','UK':'GB'}
    country_names = {}
    for c in countries_raw:
        for n in [c['name']['common'],c['name']['official'],*c.get('altSpellings',[])]: country_names[norm(n)] = c['cca2']
    country_names.update({'hong kong china':'HK','chinese taipei':'TW','south korea':'KR','reunion':'RE'})
    city_index = collections.defaultdict(dict)
    with zipfile.ZipFile(io.BytesIO(cities_raw)) as z:
        for line in z.read('cities1000.txt').decode().splitlines():
            f = line.split('\t'); cc=f[8]; pop=int(f[14] or 0)
            record = {'name':f[1], 'lat':float(f[4]),'lon':float(f[5]),'population':pop,'id':f[0]}
            for name in set([f[1],f[2],*f[3].split(',')]):
                key=norm(name)
                if not key or len(key)<2: continue
                old=city_index[cc].get(key)
                if old is None or pop > old['population']: city_index[cc][key]=record
    events, event_ids, locations, location_ids, records = [], {}, [], {}, []
    missing = 0
    for r in races:
        cc=aliases.get(r.get('startCountry'),r.get('startCountry')) or ''
        place=(r.get('startPlace') or '').strip()
        parts=[p.strip() for p in re.split(r'[,;/]',place) if p.strip()]
        if cc not in countries and parts: cc=country_names.get(norm(parts[-1]),cc)
        event_key = (r.get('uriResults') or '').split('.')[0]
        if not event_key.isdigit(): event_key='name:'+norm(r.get('eventName') or r['name'])
        # Names can change between editions (sponsors, renames); retain each source title.
        event_name=r.get('eventName') or r['name']
        dictionary_key=(event_key,event_name)
        if dictionary_key not in event_ids:
            event_ids[dictionary_key]=len(events)
            events.append([f'utmb:event:{event_key}', event_name])
        loc_key = cc+'|'+place
        if loc_key not in location_ids:
            # Exact normalized locality names only. No fuzzy or country-centroid pins.
            candidates=parts[:-1] if len(parts)>1 and norm(parts[-1]) in country_names else parts
            city=None
            for part in candidates:
                city=city_index[cc].get(norm(part))
                if city: break
            location_ids[loc_key]=len(locations)
            locations.append([place or None,cc or None,city['lon'] if city else None,city['lat'] if city else None,'town' if city else 'unknown',city['id'] if city else None])
        li=location_ids[loc_key]
        if locations[li][2] is None: missing+=1
        distance=float(r['distance']) if r.get('distance') is not None else None
        records.append([str(r['id']),event_ids[dictionary_key],r['name'],date(r.get('startDate')),distance,r.get('elevationGain'),r.get('category'),li,url(r.get('url')),r.get('uriResults'),r.get('level'),r.get('nbStones',0)])
    records.sort(key=lambda r:(r[3] or '',r[0]))
    return {'schemaVersion':1,'fetchedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':{'id':'utmb','name':'UTMB Index','url':'https://utmb.world/utmb-index/index-races','endpoint':API},'coverage':{'from':records[0][3],'to':records[-1][3],'races':len(records),'unmapped':missing},'countries':countries,'events':events,'locations':locations,'records':records}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',help='Use an existing raw API JSON response');parser.add_argument('--end',default=f'{datetime.date.today().year+1}-12-31');args=parser.parse_args()
    CACHE.mkdir(exist_ok=True)
    races=json.loads(pathlib.Path(args.input).read_text())['races'] if args.input else fetch_races(args.end)
    data=prepare(races,json.loads(cached('countries.json',COUNTRIES)),cached('cities1000.zip',CITIES))
    if not data['records']: raise ValueError('Empty feed; previous snapshot preserved')
    target=ROOT/'web/data/races.json.gz'; temp=target.with_suffix('.tmp')
    if target.exists():
        previous=json.loads(gzip.decompress(target.read_bytes()))
        ids={r[0] for r in data['records']}
        data['enrichment']={key:value for key,value in previous.get('enrichment',{}).items() if key in ids}
        if previous.get('enrichmentMeta'):data['enrichmentMeta']=previous['enrichmentMeta']
        data['coverage']['unmapped']=sum(data['locations'][r[7]][2] is None and data['enrichment'].get(r[0],{}).get('longitude') is None for r in data['records'])
    temp.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode(),compresslevel=9)); os.replace(temp,target)
    (ROOT/'web/data/manifest.json').write_text(json.dumps({k:v for k,v in data.items() if k not in ('records','events','locations','countries','enrichment')},indent=2)+'\n')
    print(json.dumps(data['coverage']));print(f'Snapshot: {target.stat().st_size:,} bytes compressed')

if __name__=='__main__': main()
