import {readFile}from'node:fs/promises';import{activateRelease}from'./build.mjs';import{locked}from'./lock.mjs';
await locked();const staged=JSON.parse(await readFile(new URL('../.cache/staged-release.json',import.meta.url),'utf8'));await activateRelease(staged.release);console.log('Activated verified release '+staged.id);
