import http from 'node:http';
import {stat,realpath,readFile} from 'node:fs/promises';
import {createReadStream,existsSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
const production=process.argv.includes('--production');
const root=resolve(process.env.SERVE_DIR||(production?(existsSync('current')?'current':'dist'):'web'));
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.txt':'text/plain; charset=utf-8','.xml':'application/xml; charset=utf-8','.gz':'application/gzip'};
const security={
 'X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin','X-Frame-Options':'DENY',
 'Permissions-Policy':'camera=(), microphone=(), geolocation=(), payment=()',
 'Content-Security-Policy':"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob:; font-src 'self'; connect-src 'self' https://tiles.basemaps.cartocdn.com https://basemaps.cartocdn.com; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
};
const server=http.createServer(async(req,res)=>{
 for(const [name,value]of Object.entries(security))res.setHeader(name,value);
 if(req.headers['x-forwarded-proto']==='https'){res.setHeader('Strict-Transport-Security','max-age=31536000');res.setHeader('Content-Security-Policy',security['Content-Security-Policy']+'; upgrade-insecure-requests');}
 if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{'Allow':'GET, HEAD'}).end();return;}
 try{
  const base=await realpath(root),url=new URL(req.url,'http://localhost'),pathname=decodeURIComponent(url.pathname);
  if(pathname==='/healthz'){
   const index=JSON.parse(await readFile(resolve(base,'data/catalog-index.json'),'utf8'));
   await stat(resolve(base,'data',index.upcoming.url));
   const body=JSON.stringify({status:'ok',release:base.split(sep).at(-1),catalogVersion:index.version,generatedAt:index.generatedAt,sources:Object.fromEntries(Object.entries(index.meta.sourceMeta||{}).map(([key,s])=>[key,{fetchedAt:s.fetchedAt,state:s.state||'available',...(s.detailRefreshError?{detailRefreshError:s.detailRefreshError}:{})}]))});
   res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store','Content-Length':Buffer.byteLength(body)});res.end(req.method==='HEAD'?undefined:body);return;
  }
  if(pathname.includes('\0')){res.writeHead(400).end();return;}
  let path=resolve(base,'.'+pathname);
  if(path!==base&&!path.startsWith(base+sep)){res.writeHead(403).end();return;}
  if((await stat(path)).isDirectory())path=resolve(path,'index.html');
  path=await realpath(path);if(!path.startsWith(base+sep)){res.writeHead(403).end();return;}
  const contentType=types[extname(path)]||'application/octet-stream';
  let encoding=null;
  if(!path.endsWith('.gz'))for(const [name,suffix]of [['br','.br'],['gzip','.gz']])if((req.headers['accept-encoding']||'').split(',').some(t=>{const [coding,...p]=t.trim().split(';');return coding===name&&!p.some(x=>/^q=0(?:\.0*)?$/.test(x.trim()));})&&existsSync(path+suffix)){path+=suffix;encoding=name;break;}
  const info=await stat(path),etag=`W/"${info.size.toString(16)}-${info.mtimeMs.toString(16)}"`;
  res.setHeader('ETag',etag);res.setHeader('Vary','Accept-Encoding');
  res.setHeader('Cache-Control',/\/assets\/app\/[a-f0-9]{16}\//.test(pathname)||/\/data\/catalog-(?:upcoming-)?[a-f0-9]{16}\.json\.gz$/.test(pathname)?'public, max-age=31536000, immutable':'no-cache');
  if(encoding)res.setHeader('Content-Encoding',encoding);
  if(req.headers['if-none-match']?.split(',').map(s=>s.trim()).includes(etag)){res.writeHead(304).end();return;}
  res.setHeader('Content-Type',contentType);res.setHeader('Content-Length',info.size);res.writeHead(200);
  if(req.method==='HEAD'){res.end();return;}
  const stream=createReadStream(path);stream.on('error',()=>res.destroy());res.on('close',()=>stream.destroy());stream.pipe(res);
 }catch(e){res.writeHead(e instanceof URIError?400:e.code==='ENOENT'||e.code==='ENOTDIR'?404:503,{'Content-Type':'text/plain; charset=utf-8','Cache-Control':'no-store'}).end('Unable to load this page.');}
});
server.requestTimeout=15000;server.headersTimeout=10000;server.keepAliveTimeout=5000;server.maxRequestsPerSocket=1000;
server.listen(Number(process.env.PORT||4173),process.env.HOST||(production?'127.0.0.1':'0.0.0.0'),()=>console.log(`Race Atlas listening on port ${server.address().port}`));
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{server.close(()=>process.exit(0));setTimeout(()=>process.exit(1),10000).unref();});
