import {mkdir} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
export async function locked(){
 if(process.argv.includes('--locked'))return;
 await mkdir(root+'.cache',{recursive:true});
 const result=spawnSync('flock',['-w','600',root+'.cache/catalog-refresh.lock',process.execPath,...process.argv.slice(1),'--locked'],{stdio:'inherit',cwd:root});
 if(result.error)throw result.error;process.exit(result.status??1);
}
