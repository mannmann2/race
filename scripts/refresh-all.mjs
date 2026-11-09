import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { copyFile, rename, mkdir } from 'node:fs/promises';
import { compose } from './compose-catalog.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.RACE_PYTHON || 'python3';
let failed=false;
const itraOnly=process.argv.includes('--itra-only');
const marathonsOnly=process.argv.includes('--worldsmarathons-only');
const detailArg=process.argv.find(a=>/^--detail-limit=\d+$/.test(a));
const bulkArg=process.argv.find(a=>/^--itra-bulk-max-age-days=\d+$/.test(a))?.replace('--itra-bulk','--bulk');
for(const script of marathonsOnly?['worldsmarathons.py']:itraOnly?['itra_browser.py']:['refresh.py','enrich.py','itra_browser.py','worldsmarathons.py']) {
  const browser=script==='itra_browser.py';
  const result=spawnSync(browser?'xvfb-run':python,browser?['-a',python,`scripts/${script}`,...(detailArg?[detailArg]:[]),...(bulkArg?[bulkArg]:[])]:[`scripts/${script}`,...(script==='worldsmarathons.py'&&process.argv.includes('--force')?['--max-age-days=0']:[])],{cwd:root,stdio:'inherit'});
  if(result.error||result.status!==0){failed=true;console.error(`${script} failed; retaining its previous data. ${result.error?.message||''}`);}
}
await compose();
if(process.argv.includes('--publish')) {
  // Publishing data never removes the live application directory or needs a server restart.
  await mkdir(`${root}dist/data`,{recursive:true});
  await copyFile(`${root}web/data/catalog.json.gz`,`${root}dist/data/catalog.json.gz.next`);
  await rename(`${root}dist/data/catalog.json.gz.next`,`${root}dist/data/catalog.json.gz`);
  console.log('Published refreshed catalog to the running application.');
}
if(failed)process.exitCode=1;
