import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const fields=['id','source','eventName','date','place','countryCode','country','continent','longitude','latitude','geonamesId','locationId','locationPrecision'];
export function resolveLocations(races) {
  const input=races.map(r=>Object.fromEntries(fields.map(k=>[k,r[k]??null])));
  const child=spawnSync(process.env.RACE_PYTHON||'python3',[fileURLToPath(new URL('./resolve_locations.py',import.meta.url))],{
    input:JSON.stringify(input),encoding:'utf8',maxBuffer:64*1024*1024,timeout:120000
  });
  if(child.error)throw child.error;
  if(child.status!==0)throw new Error('Location verification failed: '+child.stderr.trim().slice(0,500));
  return JSON.parse(child.stdout);
}
