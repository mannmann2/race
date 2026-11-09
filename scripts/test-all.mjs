import{spawnSync}from'node:child_process';import{readdir}from'node:fs/promises';
const files=(await readdir('tests')).filter(n=>n.endsWith('.test.mjs')).sort().map(n=>'tests/'+n);
for(const [bin,args]of [[process.execPath,['--test',...files]],[process.env.RACE_PYTHON||'python3',['-m','unittest','discover','-s','tests','-p','*_test.py']]]){const r=spawnSync(bin,args,{stdio:'inherit'});if(r.status!==0)process.exit(r.status??1);}
