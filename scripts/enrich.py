#!/usr/bin/env python3
"""Add real event imagery from UTMB's catalogue and official website Open Graph metadata."""
import argparse, concurrent.futures, datetime, gzip, html.parser, ipaddress, json, os, pathlib, re, socket, urllib.parse, urllib.request
from refresh import ROOT, CACHE, download, norm
CATALOG='https://utmb.world/utmb-world-series-events'

def host(url):
    return (urllib.parse.urlsplit(url or '').hostname or '').lower().removeprefix('www.')

def usable_image(url):
    if not url or not url.startswith('https://'):return False
    query=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    # Some websites advertise a generated grey tile containing only “Home”/“Accueil”.
    generic={'home','homepage','accueil','welcome','index'}
    return not any(norm(value) in generic for key,values in query.items() if key.lower() in ('text','title') for value in values)

def public_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('Not a public website URL')
    for info in socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:raise ValueError('Non-public address')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,public_url(newurl))

class Meta(html.parser.HTMLParser):
    def __init__(self):super().__init__();self.images={}
    def handle_starttag(self,tag,attrs):
        if tag=='meta':
            a=dict(attrs);key=a.get('property',a.get('name','')).lower()
            if key in ('og:image','og:image:secure_url','twitter:image','twitter:image:src') and a.get('content'):self.images[key]=a['content']

def website_image(item):
    key,url=item
    result={'image':None,'imageSource':url,'checkedAt':datetime.date.today().isoformat()}
    try:
        opener=urllib.request.build_opener(Redirect())
        with opener.open(urllib.request.Request(public_url(url),headers={'User-Agent':'Mozilla/5.0 (compatible; RaceAtlas/1.0; personal event discovery)'}),timeout=8) as response:
            if 'html' not in response.headers.get('Content-Type','').lower():return key,result
            parser=Meta();parser.feed(response.read(450000).decode('utf-8',errors='replace'))
            for field in ('og:image:secure_url','og:image','twitter:image','twitter:image:src'):
                candidate=urllib.parse.urljoin(response.url,parser.images.get(field,'')) if parser.images.get(field) else ''
                if usable_image(candidate):
                    public_url(candidate);result.update(image=candidate,imageSource=response.url);break
    except Exception:pass
    return key,result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--limit',type=int,default=600);ap.add_argument('--catalog',help='Reuse saved UTMB Next.js JSON');args=ap.parse_args();CACHE.mkdir(exist_ok=True)
    if args.catalog:page=json.loads(pathlib.Path(args.catalog).read_text())
    else:
        page_html=download(CATALOG).decode();m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',page_html);page=json.loads(m[1])
    catalog=next(s['data']['events']for s in page['props']['pageProps']['slices']if s['type']=='eventsWorldMap')
    byhost={host(e['url']):e for e in catalog}
    p=ROOT/'web/data/races.json.gz';data=json.loads(gzip.decompress(p.read_bytes()));records=data['records'];today=datetime.date.today().isoformat();end=f'{datetime.date.today().year+1}-{datetime.date.today().month:02}-{datetime.date.today().day:02}'
    cachepath=CACHE/'event-images.json';cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}
    enrichment={key:value for key,value in data.get('enrichment',{}).items() if not value.get('image') or usable_image(value['image'])};matched={};targets={}
    for row in records:
        eid,name=data['events'][row[1]];e=byhost.get(host(row[8]))
        if not e:
            namekey=norm(name).replace(' ','')
            found=[c for c in catalog if norm(c['title']).replace(' ','')==namekey]
            if len(found)==1:e=found[0]
        if e:matched[row[0]]=e
        elif row[8] and row[3] and today<=row[3]<=end and row[8] not in cache:targets.setdefault(row[8],row[8])
    targets=dict(list(targets.items())[:max(0,args.limit)])
    print(f'UTMB catalogue: {len(catalog)} events. Checking {len(targets)} official website pages for photos.',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for index,(key,value) in enumerate(pool.map(website_image,targets.items()),1):
            cache[key]=value
            if index%50==0:print(f'Checked {index}/{len(targets)} websites; {sum(bool(v["image"])for v in cache.values())} image URLs found.',flush=True)
    cachepath.write_text(json.dumps(cache,ensure_ascii=False))
    for row in records:
        info={};event=matched.get(row[0]);ci=cache.get(row[8],{})
        if event:
            picture=event.get('picture')
            if picture:info={'image':'https://img.utmb.world/image/upload/f_auto,q_auto,w_720,c_limit/'+urllib.parse.quote(picture.lstrip('/'),safe='/'),'imageSource':event['url']}
            if data['locations'][row[7]][2] is None and event.get('longitude') is not None:info.update(longitude=event['longitude'],latitude=event['latitude'])
        elif usable_image(ci.get('image')):info={k:ci[k]for k in ('image','imageSource')}
        if info:enrichment[row[0]]=info
    data['enrichment']=enrichment
    data['coverage']['unmapped']=sum(data['locations'][r[7]][2] is None and enrichment.get(r[0],{}).get('longitude') is None for r in records)
    data['enrichmentMeta']={'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'catalogSource':CATALOG,'photoRaces':sum(bool(v.get('image'))for v in enrichment.values()),'photoEvents':len({v.get('imageSource')for v in enrichment.values()if v.get('image')}),'websitePagesChecked':len(cache)}
    tmp=p.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode(),compresslevel=9));os.replace(tmp,p)
    manifest=ROOT/'web/data/manifest.json';meta=json.loads(manifest.read_text());meta['coverage']=data['coverage'];meta['enrichment']=data['enrichmentMeta'];manifest.write_text(json.dumps(meta,indent=2)+'\n');print(data['enrichmentMeta'],flush=True)
if __name__=='__main__':main()
