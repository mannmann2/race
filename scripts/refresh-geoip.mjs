import {mkdir,readFile,rename,rm,stat,writeFile} from 'node:fs/promises';
import {createWriteStream} from 'node:fs';
import {Readable,Transform} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {createGunzip} from 'node:zlib';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {Reader} from 'maxmind';
const root=fileURLToPath(new URL('../',import.meta.url)),folder=process.env.RACE_GEOIP_DIR||join(root,'.cache/geoip');await mkdir(folder,{recursive:true});
const now=new Date(),months=[now,new Date(Date.UTC(now.getUTCFullYear(),now.getUTCMonth()-1,1))].map(date=>date.toISOString().slice(0,7));
let saved={};try{saved=JSON.parse(await readFile(join(folder,'status.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
if(saved.month===months[0]&&await stat(join(folder,'city.mmdb')).catch(()=>null)){console.log('IP-location database already current.');process.exit(0);}
let completed=false;
for(const month of months){
 const source=`https://download.db-ip.com/free/dbip-city-lite-${month}.mmdb.gz`,temporary=join(folder,'city.mmdb.next');
 try{
  const response=await fetch(source,{signal:AbortSignal.timeout(300000)});if(response.status===404)continue;if(!response.ok)throw new Error(`Database download failed (${response.status})`);
  let compressed=0,expanded=0;const digest=createHash('sha256');
  await pipeline(Readable.fromWeb(response.body),new Transform({transform(chunk,encoding,callback){compressed+=chunk.length;if(compressed>160*1024*1024)return callback(new Error('Oversized download'));callback(null,chunk);}}),createGunzip(),new Transform({transform(chunk,encoding,callback){expanded+=chunk.length;if(expanded>256*1024*1024)return callback(new Error('Oversized database'));digest.update(chunk);callback(null,chunk);}}),createWriteStream(temporary,{mode:0o644}));
  const reader=new Reader(await readFile(temporary));if(!/city/i.test(reader.metadata.databaseType)||!reader.get('8.8.8.8')?.country?.iso_code)throw new Error('Invalid IP-location database');
  await rename(temporary,join(folder,'city.mmdb'));await writeFile(join(folder,'status.json'),JSON.stringify({month,source,updatedAt:new Date().toISOString(),sha256:digest.digest('hex'),license:'CC BY 4.0',attribution:'https://db-ip.com'}));
  console.log(`Updated local IP-location database (${month}); ${expanded} bytes. No visitor addresses were transmitted.`);completed=true;break;
 }catch(e){await rm(temporary,{force:true});if(month===months.at(-1))throw e;console.error(e.message+'; checking the previous monthly release.');}
}
if(!completed)throw new Error('No usable database release; any prior database is retained.');
