"""Clock rollover + live worker catalog replacement without reloading the application."""
import datetime,gzip,json,os
from playwright.sync_api import sync_playwright,expect
BASE=os.environ.get('TEST_URL','http://127.0.0.1:4173').rstrip('/')+'/'
def data(lon):
 return gzip.compress(json.dumps({'schemaVersion':1,'fetchedAt':'2027-12-31T12:00:00Z','countries':{'FR':{'name':'France','continent':'Europe'}},'events':[['1','Clock fixture']], 'locations':[['Town','FR',lon,46,'event',None]],'records':[['1',0,'Clock fixture','2028-01-06',50,2000,'50k',0,None,'clock','qualifier',0]],'coverage':{'from':'2028-01-06','to':'2028-01-06','races':1,'unmapped':0}}).encode())
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
 c=b.new_context(timezone_id='UTC',viewport={'width':1380,'height':1000},reduced_motion='reduce')
 state={'lon':6,'requests':0}
 def response(route):
  state['requests']+=1;route.fulfill(status=200,content_type='application/gzip',body=data(state['lon']))
 c.route('**/data/catalog.json.gz',response)
 page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.add_init_script("""const W=window.Worker;window.Worker=class extends W{constructor(...a){super(...a);this.addEventListener('message',({data})=>{if(data.type==='results')window.testResults=data;});}};""")
 page.clock.install(time=datetime.datetime(2027,12,31,23,59,tzinfo=datetime.timezone.utc))
 page.goto(BASE+'#inView=0',wait_until='domcontentloaded')
 expect(page.locator('#result-count')).to_have_text('1',timeout=60000)
 expect(page.locator('[name=from]')).to_have_value('2027-12-31')
 page.clock.fast_forward(120000)
 expect(page.locator('[name=from]')).to_have_value('2028-01-01')
 state['lon']=9
 page.clock.fast_forward(3600001)
 page.wait_for_function('testResults?.points?.[0]?.longitude===9',timeout=30000)
 assert state['requests']>=2
 page.locator('[name=from]').fill('2028-01-05');page.locator('[name=to]').fill('2028-01-10')
 page.clock.fast_forward(86400000)
 expect(page.locator('[name=from]')).to_have_value('2028-01-05')
 expect(page.locator('[name=to]')).to_have_value('2028-01-10')
 expect(page.locator('#result-count')).to_have_text('1')
 assert not errors,errors
 print('Passed: midnight/year rollover, hourly dataset/pin replacement, and fixed custom dates.',flush=True)
 b.close()
