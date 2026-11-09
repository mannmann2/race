import { cp, mkdir, rm } from 'node:fs/promises';
import { compose } from './compose-catalog.mjs';
await compose();
await rm('dist', { recursive: true, force: true });
await mkdir('dist', { recursive: true });
await cp('web', 'dist', { recursive: true });
console.log('Built dist/ — deploy at any domain or subdirectory.');
