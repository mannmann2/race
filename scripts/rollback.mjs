import{readFile,symlink,rename,rm}from'node:fs/promises';
import{fileURLToPath}from'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const state=JSON.parse(await readFile(root+'.releases/last-release.json','utf8'));
if(!state.previous||!/^\.releases\/[\w-]+$/.test(state.previous))throw new Error('No previous release to restore');
await rm(root+'.current.next',{force:true});await symlink(state.previous,root+'.current.next');await rename(root+'.current.next',root+'current');
console.log('Restored '+state.previous);
