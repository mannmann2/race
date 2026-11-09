// Keep the original muted marker palette independently of official card badges.
const COLORS={'20k':'#e0c55a','50k':'#ec9658','100k':'#80bfa4','100m':'#be9bd6',other:'#9baaaa'};

const palettes={
  light:{land:'#91ac91',water:'#426f8c',waterway:'#56859c',cover:'#89a789',use:'#97af92',residential:'#b4bca6',park:'#7c9e7e',boundary:'#c6d1b7',outline:'#738f79',road:'#f4efdc',roadCase:'#809b83',path:'#607d69',building:'#a1ad97',text:'#243e36',halo:'#bbcdb0',waterText:'#e4eef2',cluster:'#244e3e',clusterText:'#fff9e8',stroke:'#faf7e9',pointStroke:'#294d3c',highlight:'#d46322'},
  dark:{land:'#819d86',water:'#426d87',waterway:'#59879b',cover:'#78957d',use:'#87a18a',residential:'#98a995',park:'#688b73',boundary:'#aabd9f',outline:'#547766',road:'#b6c4ac',roadCase:'#5d7e6b',path:'#486c5d',building:'#6a8874',text:'#182f2a',halo:'#a8bea3',waterText:'#e0ebef',cluster:'#f0cc82',clusterText:'#2b332b',stroke:'#293c34',pointStroke:'#f7efda',highlight:'#ffe1a0'}
};

// Paint-only updates preserve the camera, loaded tiles, filters and race sources.
export function themedPaint(layer,theme){
  const p=palettes[theme]||palettes.light,id=layer.id,paint={};
  if(id==='race-clusters')return {'circle-color':p.cluster,'circle-stroke-color':p.stroke};
  if(id==='race-cluster-labels'||id==='race-point-labels')return {'text-color':p.clusterText};
  if(id==='race-points')return {'circle-color':['case',['>',['get','count'],1],p.cluster,['match',['get','category'],...Object.entries(COLORS).flat(),COLORS.other]],'circle-stroke-color':['case',['>',['get','count'],1],p.stroke,p.pointStroke]};
  if(id==='race-highlight-halo')return {'circle-color':p.highlight,'circle-stroke-color':p.highlight};
  if(layer.type==='background')paint['background-color']=p.land;
  if(id==='water')paint['fill-color']=p.water;
  if(id==='waterway')paint['line-color']=p.waterway;
  if(id==='landcover')paint['fill-color']=p.cover;
  if(id==='landuse')paint['fill-color']=p.use;
  if(id==='landuse_residential')paint['fill-color']=p.residential;
  if(id.startsWith('park_'))paint['fill-color']=p.park;
  if(id.startsWith('boundary_'))paint['line-color']=id.includes('outline')?p.outline:p.boundary;
  if(layer.type==='line'&&/^(road_|bridge_|tunnel_|rail|aeroway)/.test(id))paint['line-color']=id.includes('case')?p.roadCase:/path|rail/.test(id)?p.path:p.road;
  if(id==='building-top'){paint['fill-color']=p.building;paint['fill-outline-color']=p.roadCase;}
  if(layer.type==='symbol'&&layer.layout?.['text-field']){paint['text-color']=p.text;paint['text-halo-color']=p.halo;}
  if(id.startsWith('watername_')||id==='waterway_label'){paint['text-color']=p.waterText;paint['text-halo-color']=p.water;}
  return paint;
}
