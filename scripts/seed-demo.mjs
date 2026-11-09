import{mkdir,writeFile,access}from'node:fs/promises';import{gzipSync}from'node:zlib';import{synthetic}from'../tests/fixtures/synthetic.mjs';
try{await access('web/data/races.json.gz');throw new Error('A real snapshot already exists; demo seeding refused.');}catch(e){if(e.code!=='ENOENT')throw e;}
await mkdir('web/data',{recursive:true});await writeFile('web/data/races.json.gz',gzipSync(JSON.stringify(synthetic)));console.log('Created two clearly labelled synthetic races for local development/CI.');
