import{readdir,stat,rm,readFile,readlink}from'node:fs/promises';import{join}from'node:path';import{fileURLToPath}from'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),cutoff=Date.now()-30*86400000;
export async function pruneData(directory){let index;try{index=JSON.parse(await readFile(join(directory,'catalog-index.json'),'utf8'));}catch{return;}
 const keep=new Set([index.archive.url,index.upcoming.url]);for(const name of await readdir(directory))if(/^catalog-(?:upcoming-)?[a-f0-9]{16}\.json\.gz$/.test(name)&&!keep.has(name)&&(await stat(join(directory,name))).mtimeMs<cutoff)await rm(join(directory,name));
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 await pruneData(root+'web/data');await pruneData(root+'current/data');
 const folder=root+'.releases',all=(await readdir(folder)).filter(n=>/^\d{8}T[\dZ]+-[a-f0-9]{16}$/.test(n)).sort().reverse(),state=JSON.parse(await readFile(folder+'/last-release.json','utf8'));
 const keep=new Set([...(all.slice(0,5)),state.current?.split('/').at(-1),state.previous?.split('/').at(-1)]);
 for(const name of all)if(!keep.has(name))await rm(join(folder,name),{recursive:true,force:true});
 console.log('Retained five recent releases, the rollback target and 30 days of immutable data.');
}
