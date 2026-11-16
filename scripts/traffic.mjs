import {DatabaseSync} from 'node:sqlite';
import {createHmac,randomBytes} from 'node:crypto';
import {mkdirSync,readFileSync,writeFileSync,statSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {isIP} from 'node:net';
import {Reader} from 'maxmind';

export const TIMEZONE='Europe/London',IDLE_MS=30*60*1000,RETENTION_DAYS=90;
const BOT=/bot|spider|crawler|headless|lighthouse|curl|wget|python|monitor|preview|facebookexternalhit|slurp/i;
export function dayAt(time){const parts=new Intl.DateTimeFormat('en-GB',{timeZone:TIMEZONE,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(time));return ['year','month','day'].map(t=>parts.find(p=>p.type===t).value).join('-');}
export function validDate(value){return /^\d{4}-\d{2}-\d{2}$/.test(value||'')&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;}
export function dateRange(from,to){if(!validDate(from)||!validDate(to)||from>to||(Date.parse(to)-Date.parse(from))/86400000>=90)throw new Error('Choose a date range of up to 90 days.');const days=[];for(let date=Date.parse(from);date<=Date.parse(to);date+=86400000)days.push(new Date(date).toISOString().slice(0,10));return days;}
export function normalizeIP(value){let ip=String(value||'').trim();if(ip.startsWith('::ffff:')&&isIP(ip.slice(7))===4)ip=ip.slice(7);return isIP(ip)?ip.toLowerCase():null;}
export function clientIP(req){const remote=normalizeIP(req.socket.remoteAddress);return ['127.0.0.1','::1'].includes(remote)?normalizeIP(req.headers['x-race-client-ip'])||remote:remote;}
export function authorizedDebug(req,production){const peer=normalizeIP(req.socket.remoteAddress);return !production||(['127.0.0.1','::1'].includes(peer)&&req.headers['x-race-debug-user']==='arman');}
export function eligible(req){const ua=String(req.headers['user-agent']||'');return ua.length>0&&ua.length<1024&&!BOT.test(ua)&&req.headers.dnt!=='1'&&req.headers['sec-gpc']!=='1';}
function agentFamily(ua){return `${/Android|iPhone|iPad|Mobile/i.test(ua)?'mobile':'desktop'}:${/Firefox/i.test(ua)?'Firefox':/Edg\//i.test(ua)?'Edge':/Chrome|Chromium/i.test(ua)?'Chrome':/Safari/i.test(ua)?'Safari':'other'}`;}

export class GeoLocations{
 constructor(path){this.path=path;this.reader=null;this.version=null;this.lastChecked=0;this.reload();}
 reload(){this.lastChecked=Date.now();try{const file=statSync(this.path),version=`${file.size}:${file.mtimeMs}`;if(version!==this.version){const reader=new Reader(readFileSync(this.path));if(!/city/i.test(reader.metadata.databaseType))throw new Error('Not a city database');this.reader=reader;this.version=version;this.updatedAt=new Date(file.mtimeMs).toISOString();}}catch{}}
 lookup(ip){if(Date.now()-this.lastChecked>300000)this.reload();try{const data=this.reader?.get(ip);return {country:data?.country?.names?.en||'Unknown',countryCode:data?.country?.iso_code||'',region:data?.subdivisions?.[0]?.names?.en||'',city:data?.city?.names?.en||'Unknown'};}catch{return {country:'Unknown',countryCode:'',region:'',city:'Unknown'};}}
 status(){return {available:!!this.reader,updatedAt:this.updatedAt||null,provider:'DB-IP Lite'};}
}

export class TrafficStore{
 constructor(path,{key,geo,now=()=>Date.now()}={}){
  mkdirSync(dirname(path),{recursive:true,mode:0o750});this.now=now;this.geo=geo;this.limits=new Map();
  if(!key){const keyPath=join(dirname(path),'traffic-key');try{key=readFileSync(keyPath);}catch(e){if(e.code!=='ENOENT')throw e;key=randomBytes(32);writeFileSync(keyPath,key,{flag:'wx',mode:0o600});}}
  this.key=key;this.db=new DatabaseSync(path);this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=3000; PRAGMA foreign_keys=ON; PRAGMA secure_delete=ON;
   CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS visitors(day TEXT NOT NULL,visitor TEXT NOT NULL,country TEXT NOT NULL,country_code TEXT NOT NULL,region TEXT NOT NULL,city TEXT NOT NULL,last_seen INTEGER NOT NULL,PRIMARY KEY(day,visitor));
   CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,day TEXT NOT NULL,visitor TEXT NOT NULL,started INTEGER NOT NULL,last_seen INTEGER NOT NULL,active_ms INTEGER NOT NULL DEFAULT 0,active_until INTEGER NOT NULL,FOREIGN KEY(day,visitor) REFERENCES visitors(day,visitor) ON DELETE CASCADE);
   CREATE INDEX IF NOT EXISTS session_visitor ON sessions(day,visitor,last_seen);
   CREATE TABLE IF NOT EXISTS pages(day TEXT NOT NULL,page TEXT NOT NULL,session TEXT NOT NULL,sequence INTEGER NOT NULL,total_ms INTEGER NOT NULL,last_seen INTEGER NOT NULL,PRIMARY KEY(day,page),FOREIGN KEY(session) REFERENCES sessions(id) ON DELETE CASCADE);
   CREATE INDEX IF NOT EXISTS sessions_day ON sessions(day);
   CREATE INDEX IF NOT EXISTS pages_session ON pages(session);
  `);
  this.db.prepare("INSERT OR IGNORE INTO settings VALUES('started_at',?)").run(new Date(now()).toISOString());this.prune();
 }
 hash(value){return createHmac('sha256',this.key).update(value).digest('hex');}
 prune(){const before=new Date(Date.parse(dayAt(this.now()))-(RETENTION_DAYS-1)*86400000).toISOString().slice(0,10);this.db.prepare('DELETE FROM visitors WHERE day < ?').run(before);this.lastPruned=dayAt(this.now());}
 ingest(req,event){
  if(!eligible(req))return {accepted:false};
  if(!event||!/^[-a-zA-Z0-9_]{16,80}$/.test(event.page||'')||!Number.isSafeInteger(event.seq)||event.seq<0||event.seq>1000000||!Number.isSafeInteger(event.activeMs)||event.activeMs<0||event.activeMs>86400000||typeof event.start!=='boolean')throw new Error('Invalid traffic event.');
  const now=this.now(),day=dayAt(now),ip=clientIP(req);if(!ip)return {accepted:false};
  if(day!==this.lastPruned)this.prune();
  const visitor=this.hash(`${day}\0${ip}\0${agentFamily(req.headers['user-agent'])}`),page=this.hash(`${day}\0${visitor}\0${event.page}`);
  const limit=this.limits.get(visitor);if(limit&&now-limit.started<60000){if(limit.count++>=40)return {accepted:false};}else this.limits.set(visitor,{started:now,count:1});
  if(this.limits.size>10000)for(const [key,value]of this.limits)if(now-value.started>=60000)this.limits.delete(key);
  if(this.limits.size>20000)this.limits.delete(this.limits.keys().next().value);
  let existing=this.db.prepare('SELECT * FROM pages WHERE day=? AND page=?').get(day,page);
  if(existing&&event.seq<=existing.sequence)return {accepted:false};
  const current=this.db.prepare('SELECT * FROM visitors WHERE day=? AND visitor=?').get(day,visitor);
  const location=current?null:this.geo?.lookup(ip)||{country:'Unknown',countryCode:'',region:'',city:'Unknown'};
  this.db.exec('BEGIN');
  try{
   if(!current)this.db.prepare('INSERT INTO visitors VALUES(?,?,?,?,?,?,?)').run(day,visitor,location.country,location.countryCode,location.region,location.city,now);
   else this.db.prepare('UPDATE visitors SET last_seen=? WHERE day=? AND visitor=?').run(now,day,visitor);
   let session=this.db.prepare('SELECT * FROM sessions WHERE day=? AND visitor=? ORDER BY last_seen DESC LIMIT 1').get(day,visitor);
   if(!session||now-session.last_seen>=IDLE_MS){session={id:randomBytes(16).toString('hex'),started:now,last_seen:now,active_ms:0,active_until:now};this.db.prepare('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)').run(session.id,day,visitor,now,now,0,now);}
   const continuing=existing&&existing.session===session.id;
   const delta=continuing?Math.min(Math.max(0,event.activeMs-existing.total_ms),Math.max(0,now-existing.last_seen),60000):0;
   // Union foreground intervals across tabs rather than counting overlapping time twice.
   const active=Math.max(0,now-Math.max(now-delta,session.active_until));
   this.db.prepare('UPDATE sessions SET last_seen=?,active_ms=active_ms+?,active_until=? WHERE id=?').run(now,active,active?now:session.active_until,session.id);
   this.db.prepare('INSERT INTO pages VALUES(?,?,?,?,?,?) ON CONFLICT(day,page) DO UPDATE SET session=excluded.session,sequence=excluded.sequence,total_ms=excluded.total_ms,last_seen=excluded.last_seen').run(day,page,session.id,event.seq,event.activeMs,now);
   this.db.exec('COMMIT');return {accepted:true};
  }catch(e){this.db.exec('ROLLBACK');throw e;}
 }
 summary(from,to){
  if(dayAt(this.now())!==this.lastPruned)this.prune();
  const days=dateRange(from,to),query=`SELECT s.day,COUNT(DISTINCT s.visitor) visitors,COUNT(*) sessions,COALESCE(SUM(s.active_ms),0) active_ms,COALESCE(SUM(s.last_seen-s.started),0) span_ms FROM sessions s WHERE s.day BETWEEN ? AND ? GROUP BY s.day`,rows=this.db.prepare(query).all(from,to),byDay=new Map(rows.map(r=>[r.day,r]));
  const daily=days.map(day=>byDay.get(day)||{day,visitors:0,sessions:0,active_ms:0,span_ms:0});
  const total=daily.reduce((a,d)=>({sessions:a.sessions+d.sessions,activeMs:a.activeMs+d.active_ms,spanMs:a.spanMs+d.span_ms}),{sessions:0,activeMs:0,spanMs:0});
  const locations=this.db.prepare(`SELECT v.country,v.country_code countryCode,v.region,v.city,COUNT(*) sessions,SUM(s.active_ms) activeMs FROM sessions s JOIN visitors v ON s.day=v.day AND s.visitor=v.visitor WHERE s.day BETWEEN ? AND ? GROUP BY v.country,v.country_code,v.region,v.city ORDER BY sessions DESC,v.country,v.city LIMIT 200`).all(from,to);
  const countries=this.db.prepare(`SELECT v.country,COUNT(*) sessions,SUM(s.active_ms) activeMs FROM sessions s JOIN visitors v ON s.day=v.day AND s.visitor=v.visitor WHERE s.day BETWEEN ? AND ? GROUP BY v.country ORDER BY sessions DESC,v.country`).all(from,to);
  const today=dayAt(this.now()),todayVisitors=this.db.prepare('SELECT COUNT(*) count FROM visitors WHERE day=?').get(today).count,live=this.db.prepare('SELECT COUNT(*) count FROM visitors WHERE last_seen>=?').get(this.now()-5*60000).count;
  return {from,to,timezone:TIMEZONE,startedAt:this.db.prepare("SELECT value FROM settings WHERE key='started_at'").get().value,today,todayVisitors,live,daily,locations,countries,geo:this.geo?.status()||{available:false},...total,retentionDays:RETENTION_DAYS,generatedAt:new Date(this.now()).toISOString()};
 }
 close(){this.db.close();}
}
