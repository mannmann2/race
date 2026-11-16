import {DatabaseSync,backup} from 'node:sqlite';
import {mkdir,readdir,rm,rename} from 'node:fs/promises';
import {join,dirname} from 'node:path';
const path=process.env.RACE_TRAFFIC_DB;if(!path)throw new Error('RACE_TRAFFIC_DB is required');
const folder=join(dirname(path),'backups');await mkdir(folder,{recursive:true,mode:0o750});
const name='traffic-'+new Date().toISOString().slice(0,10)+'.sqlite',destination=join(folder,name),db=new DatabaseSync(path,{readOnly:true});
try{await backup(db,destination+'.next');await rename(destination+'.next',destination);}finally{db.close();}
const files=(await readdir(folder)).filter(name=>/^traffic-\d{4}-\d{2}-\d{2}\.sqlite$/.test(name)).sort();for(const name of files.slice(0,-7))await rm(join(folder,name));
console.log('Saved a consistent traffic database backup; keeping seven daily copies.');
