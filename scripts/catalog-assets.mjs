import {readFile,writeFile,rename,mkdir,rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {gzipSync,gunzipSync} from 'node:zlib';
import {join} from 'node:path';
import {expandDataset} from '../web/core.mjs';
import {validateCatalog} from './catalog-quality.mjs';
const hash=body=>createHash('sha256').update(body).digest('hex').slice(0,16);
export async function atomicWrite(path,body){await writeFile(path+'.next',body);await rename(path+'.next',path);}
export async function writeCatalogAssets(directory,data,{now=new Date()}={}){
 validateCatalog(data);await mkdir(directory,{recursive:true});
 const raw=gzipSync(JSON.stringify(data),{level:9}),version=hash(raw);
 const cutoff=new Date(now);cutoff.setUTCDate(cutoff.getUTCDate()-2);const from=cutoff.toISOString().slice(0,10);
 const races=expandDataset(data),upcoming=races.filter(r=>(r.dateEnd||r.date)>=from).map(({searchText,...r})=>r);
 const light=gzipSync(JSON.stringify({schemaVersion:3,races:upcoming}),{level:9});
 const archive=`catalog-${version}.json.gz`,upcomingName=`catalog-upcoming-${hash(light)}.json.gz`;
 await atomicWrite(join(directory,archive),raw);await atomicWrite(join(directory,upcomingName),light);
 const used=[...new Set(races.map(r=>r.countryCode).filter(Boolean))];
 const meta={fetchedAt:data.fetchedAt,coverage:{...data.coverage,unmapped:races.filter(r=>r.longitude==null).length},source:data.source,sourceMeta:data.sourceMeta,mergeSummary:data.mergeSummary,countries:used.map(code=>({code,name:data.countries[code]?.name||races.find(r=>r.countryCode===code)?.country||code})).sort((a,b)=>a.name.localeCompare(b.name))};
 const index={schemaVersion:1,version,generatedAt:now.toISOString(),upcoming:{url:upcomingName,from,races:upcoming.length,bytes:light.length},archive:{url:archive,races:races.length,bytes:raw.length},meta};
 // Immutable payloads land first; the small index is the only mutable pointer.
 // Mutable pointers must never be shadowed by a precompressed copy from an older release.
 await rm(join(directory,'catalog-index.json.br'),{force:true});await rm(join(directory,'catalog-index.json.gz'),{force:true});
 await atomicWrite(join(directory,'catalog-index.json'),JSON.stringify(index));
 return index;
}
export async function publishCatalog(source,destination){const data=JSON.parse(gunzipSync(await readFile(join(source,'catalog.json.gz'))));const index=await writeCatalogAssets(destination,data);await atomicWrite(join(destination,'catalog.json.gz'),await readFile(join(source,'catalog.json.gz')));return index;}
