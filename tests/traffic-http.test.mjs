import test from 'node:test';
import assert from 'node:assert/strict';
import {Readable} from 'node:stream';
import {trafficRoute} from '../scripts/traffic-http.mjs';
function request(path,{method='GET',origin='https://race.slopmaxx.ing',headers={},body=''}={}){const req=Readable.from([body]);req.method=method;req.url=path;req.socket={remoteAddress:'127.0.0.1'};req.headers={origin,'user-agent':'Mozilla/5.0 Chrome/141.0.0.0',...headers};return req;}
function response(){return {headers:{},status:200,setHeader(k,v){this.headers[k]=v;},writeHead(code,headers={}){this.status=code;Object.assign(this.headers,headers);this.headersSent=true;return this;},end(body){this.body=body;this.ended=true;}};}
const options={production:true,origin:'https://race.slopmaxx.ing',store:{ingest(){},summary(){return {sessions:3};}}};
test('private debug data rejects missing or untrusted identity before reading analytics',async()=>{
 for(const path of ['/debug','/debug/','/debug/data?from=2026-11-16&to=2026-11-16']){const req=request(path),res=response();assert.equal(await trafficRoute(req,res,new URL(path,'https://race.slopmaxx.ing'),options),true);assert.equal(res.status,403);assert.equal(res.headers['Cache-Control'],'no-store');}
 const path='/debug/data?from=2026-11-16&to=2026-11-16',res=response();await trafficRoute(request(path,{headers:{'x-race-debug-user':'arman'}}),res,new URL(path,'https://race.slopmaxx.ing'),options);assert.equal(res.status,200);assert.equal(JSON.parse(res.body).sessions,3);
});
test('collector permits only same-origin bounded POST bodies and stores no cross-origin traffic',async()=>{
 const event=JSON.stringify({page:'abcdefghijklmnop',seq:0,activeMs:0,start:true});
 for(const [args,status]of [[{method:'GET'},405],[{method:'POST',origin:'https://elsewhere.example',body:event},403],[{method:'POST',body:'broken'},400],[{method:'POST',headers:{'content-length':'9000'},body:event},413],[{method:'POST',body:'x'.repeat(1100)},413],[{method:'POST',body:event},204]]){const res=response();await trafficRoute(request('/api/traffic',args),res,new URL('https://race.slopmaxx.ing/api/traffic'),options);assert.equal(res.status,status,JSON.stringify(args));}
});
