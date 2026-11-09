import { readFile, writeFile, rename, mkdir } from 'node:fs/promises';
import { gzipSync, gunzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { expandDataset } from '../web/core.mjs';
import { matchSources } from './match-sources.mjs';
import { matchMarathons } from './match-marathons.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
async function optional(path,fallback){if(!path)return fallback;try{return JSON.parse(await readFile(path,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
export async function compose({basePath=resolve(root,'web/data/races.json.gz'),itraPath=resolve(root,'.cache/itra/races.json'),fallbackPath=resolve(root,'data/itra-snapshot.json'),statusPath=resolve(root,'.cache/itra/status.json'),output=resolve(root,'web/data/catalog.json.gz'),reportPath=resolve(root,'.cache/itra/match-report.json'),overridesPath=resolve(root,'scripts/source-overrides.json'),marathonsPath=resolve(root,'.cache/worldsmarathons/races.json'),marathonsFallbackPath=resolve(root,'data/worldsmarathons-snapshot.json'),marathonsStatusPath=resolve(root,'.cache/worldsmarathons/status.json'),marathonsReportPath=resolve(root,'.cache/worldsmarathons/match-report.json')}={}) {
  const base=JSON.parse(gunzipSync(await readFile(basePath)));
  const snapshot=await optional(itraPath,null)||await optional(fallbackPath,null),status=await optional(statusPath,{state:'not-imported'}),overrides=await optional(overridesPath,{});
  if(snapshot?.acquisition==='browser-calendar'&&status.state==='not-imported')status.state='available';
  if(snapshot?.acquisition==='public-index'&&status.state==='not-imported')status.state='indexed-only';
  if(snapshot && (snapshot.schemaVersion!==1||!Array.isArray(snapshot.races)||!snapshot.races.length))throw new Error('Invalid ITRA snapshot; catalog preserved');
  const {entries,report}=matchSources(expandDataset(base),snapshot?.races||[],overrides);
  const data={...base,schemaVersion:2,additionalRaces:entries,sourceMeta:{utmb:{fetchedAt:base.fetchedAt,races:base.records.length},itra:{...status,fetchedAt:snapshot?.fetchedAt||null,retrievedAt:snapshot?.retrievedAt||null,acquisition:snapshot?.acquisition||'direct',races:entries.length,coverage:snapshot?.coverage||null}},mergeSummary:{imported:report.imported,merged:report.merged,added:report.added,unresolved:report.unresolved}};
  const marathons=await optional(marathonsPath,null)||await optional(marathonsFallbackPath,null);
  let marathonsReport=null;
  if(marathons) {
    if(marathons.schemaVersion!==1||!Array.isArray(marathons.races)||!marathons.races.length||marathons.races.some(r=>r.source!=='worldsmarathons'))throw new Error('Invalid World’s Marathons snapshot; catalog preserved');
    const result=matchMarathons(expandDataset(data),marathons.races);marathonsReport=result.report;
    data.additionalRaces.push(...result.entries);
    data.sourceMeta.worldsmarathons={...await optional(marathonsStatusPath,{state:'available'}),fetchedAt:marathons.fetchedAt,acquisition:marathons.acquisition,races:marathons.races.length,coverage:marathons.coverage,mergeSummary:marathonsReport};
    // Detailed match evidence stays in the server-side report, not the transport.
    data.sourceMeta.worldsmarathons.mergeSummary={imported:marathonsReport.imported,merged:marathonsReport.merged,added:marathonsReport.added,unresolved:marathonsReport.unresolved};
    await mkdir(resolve(marathonsReportPath,'..'),{recursive:true});
    await writeFile(marathonsReportPath,JSON.stringify(marathonsReport,null,2)+'\n');
  }
  const expanded=expandDataset(data),dates=expanded.map(r=>r.date).filter(Boolean).sort();
  data.coverage={...base.coverage,from:dates[0],to:dates.at(-1),races:expanded.length,unmapped:expanded.filter(r=>r.longitude==null).length};
  await mkdir(resolve(reportPath,'..'),{recursive:true});
  await writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
  await writeFile(output+'.tmp',gzipSync(JSON.stringify(data),{level:9}));await rename(output+'.tmp',output);
  console.log(`Catalog: ${data.coverage.races} races; ITRA ${report.imported} imported, ${report.merged} merged, ${report.unresolved} need review (${status.state}).`);
  if(marathonsReport)console.log(`World’s Marathons: ${marathonsReport.imported} imported, ${marathonsReport.merged} merged, ${marathonsReport.added} added.`);
  return {data,report,marathonsReport};
}
if(process.argv[1]===fileURLToPath(import.meta.url))await compose();
