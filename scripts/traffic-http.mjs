import {authorizedDebug} from './traffic.mjs';
export async function trafficRoute(req,res,url,{store,production,origin}){
 const path=url.pathname;
 if(path.startsWith('/debug')){
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Robots-Tag','noindex, nofollow');
  if(!authorizedDebug(req,production)){res.writeHead(403,{'Content-Type':'text/plain'}).end('This dashboard is private.');return true;}
  if(path==='/debug/data'){
   if(req.method!=='GET'){res.writeHead(405,{'Allow':'GET'}).end();return true;}
   try{if(!store){res.writeHead(503,{'Content-Type':'application/json'}).end(JSON.stringify({error:'Traffic collection is not configured.'}));return true;}
    const result=store.summary(url.searchParams.get('from'),url.searchParams.get('to'));res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(result));
   }catch{res.writeHead(400,{'Content-Type':'application/json'}).end(JSON.stringify({error:'Choose a valid date range of up to 90 days.'}));}return true;
  }
 }
 if(path!=='/api/traffic')return false;
 res.setHeader('Cache-Control','no-store');
 if(req.method!=='POST'){res.writeHead(405,{'Allow':'POST'}).end();return true;}
 if(!store){res.writeHead(204).end();return true;}
 if(req.headers.origin!==origin){res.writeHead(403).end();return true;}
 if(Number(req.headers['content-length']||0)>1024){res.writeHead(413).end();req.resume();return true;}
 try{let body='';for await(const chunk of req){body+=chunk.toString();if(Buffer.byteLength(body)>1024){res.writeHead(413).end();return true;}}
  let event;try{event=JSON.parse(body);}catch{res.writeHead(400).end();return true;}
  store.ingest(req,event);res.writeHead(204).end();
 }catch(e){if(!res.headersSent)res.writeHead(e.message==='Invalid traffic event.'?400:503).end();}
 return true;
}
