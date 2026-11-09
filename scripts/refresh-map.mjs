import { writeFile, rename } from 'node:fs/promises';
const response=await fetch('https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json');
if(!response.ok)throw new Error(`Map style fetch failed: ${response.status}`);
const style=await response.json();
if(style.version!==8||!style.sources||!style.layers?.length)throw new Error('Invalid map style; previous style preserved');
await writeFile('web/data/map-style.tmp',JSON.stringify(style));
await rename('web/data/map-style.tmp','web/data/map-style.json');
console.log('Updated CARTO map style. Run npm run build to publish.');
