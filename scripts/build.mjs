import {cp,mkdir,readFile,readdir,writeFile,rename,symlink,rm,readlink,stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join,relative} from 'node:path';
import {createHash} from 'node:crypto';
import {brotliCompressSync,gzipSync} from 'node:zlib';
import {compose} from './compose-catalog.mjs';
import {writeCatalogAssets,atomicWrite} from './catalog-assets.mjs';
import {spawnSync} from 'node:child_process';
import {locked} from './lock.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
async function files(dir){const found=[];for(const e of await readdir(dir,{withFileTypes:true})){const p=join(dir,e.name);if(e.isDirectory())found.push(...await files(p));else if(e.isFile())found.push(p);}return found.sort();}
export async function build({publish=!process.argv.includes('--stage')}={}){
 const {data}=await compose();
 const source=join(root,'web'),sourceFiles=await files(source),digest=createHash('sha256');
 for(const p of sourceFiles.filter(p=>!p.includes('/data/'))){digest.update(relative(source,p));digest.update(await readFile(p));}
 const version=digest.digest('hex').slice(0,16),id=new Date().toISOString().replace(/[-:.]/g,'')+'-'+version;
 const releases=join(root,'.releases'),release=join(releases,id);await mkdir(release,{recursive:true});let published=false;
 try{
  // Stage the application away from the serving pointer. Data is validated first.
  await cp(source,release,{recursive:true,preserveTimestamps:true});
  const index=await writeCatalogAssets(join(release,'data'),data);
  const immutable=join(release,'assets/app',version);await mkdir(immutable,{recursive:true});
  for(const p of sourceFiles.filter(p=>/\.(?:m?js|css)$/.test(p))){let body=await readFile(p);if(p.endsWith('/worker.mjs'))body=Buffer.from(body.toString().replaceAll("'./data/","'../../../data/"));
   if(p.endsWith('/style.css'))body=Buffer.from(body.toString().replaceAll("./assets/fonts/","../../fonts/"));
   const destination=join(immutable,relative(source,p));await mkdir(join(destination,'..'),{recursive:true});await writeFile(destination,body);
  }
  let html=await readFile(join(release,'index.html'),'utf8');
  html=html.replace(/((?:src|href)="\.\/)([^"?]+\.(?:m?js|css))"/g,(_,start,path)=>`${start}assets/app/${version}/${path}"`);
  await writeFile(join(release,'index.html'),html);
  await writeFile(join(release,'release.json'),JSON.stringify({id,version,builtAt:new Date().toISOString(),catalogVersion:index.version}));
  for(const p of (await files(release)).filter(p=>!p.includes('/data/')&&/\.(?:html|m?js|css|json|svg|txt|xml)$/.test(p))){const body=await readFile(p);if(body.length>512){await writeFile(p+'.br',brotliCompressSync(body));await writeFile(p+'.gz',gzipSync(body));}}
  // Keep prior versioned application assets accessible to tabs opened before deployment.
  let previous=null;try{previous=await readlink(join(root,'current'));}catch{}
  if(previous)try{await cp(join(root,previous,'assets/app'),join(release,'assets/app'),{recursive:true,force:false,errorOnExist:false,preserveTimestamps:true});}catch(e){if(e.code!=='ENOENT')throw e;}
  if(process.getuid?.()===0){const uid=spawnSync('id',['-u','race-refresh'],{encoding:'utf8'});if(uid.status===0){const result=spawnSync('chown',['-R','race-refresh:race-refresh',join(release,'data')]);if(result.status!==0)throw new Error('Cannot grant the importer access to release data');}}
  await atomicWrite(join(root,'.cache/staged-release.json'),JSON.stringify({release,id,version,catalogVersion:index.version}));
  if(publish){await activateRelease(release);published=true;}
  console.log(`${publish?'Published':'Staged'} release ${id}: ${index.upcoming.races} initial races (${index.upcoming.bytes} bytes); archive loads on demand.`);
  return {release,index,id};
 }catch(error){try{published=await readlink(join(root,'current'))===relative(root,release);}catch{}if(!published)await rm(release,{recursive:true,force:true});throw error;}
}
export async function activateRelease(release){
 const releases=join(root,'.releases');if(!release.startsWith(releases+'/')||relative(releases,release).includes('/'))throw new Error('Invalid release directory');
 await readFile(join(release,'release.json'));
 let previous=null;try{previous=await readlink(join(root,'current'));}catch{}
 if(!previous&&await stat(join(root,'dist')).catch(()=>null)){const legacy=join(releases,'legacy-'+Date.now());await cp(join(root,'dist'),legacy,{recursive:true});const {gunzipSync}=await import('node:zlib');await writeCatalogAssets(join(legacy,'data'),JSON.parse(gunzipSync(await readFile(join(legacy,'data/catalog.json.gz')))));await writeFile(join(legacy,'release.json'),JSON.stringify({id:'legacy'}));previous=relative(root,legacy);}
 // Persist recovery information before changing the serving pointer.
 await atomicWrite(join(releases,'last-release.json'),JSON.stringify({current:relative(root,release),previous,builtAt:new Date().toISOString()}));
 await rm(join(root,'.current.next'),{force:true});await symlink(relative(root,release),join(root,'.current.next'));await rename(join(root,'.current.next'),join(root,'current'));
 const dist=join(root,'dist');let target;try{target=await readlink(dist);}catch{}
 if(target!=='current'){try{await rename(dist,join(releases,'old-dist-'+Date.now()));}catch(e){if(e.code!=='ENOENT')throw e;}await symlink('current',dist);}
}
if(process.argv[1]===fileURLToPath(import.meta.url)){await locked();await build();}
