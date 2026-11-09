import { GRADES } from './grades.mjs';
import { themedPaint } from './map-theme.mjs';
const empty=()=>({type:'FeatureCollection',features:[]});
const raceLayers=['race-clusters','race-points'];
const clusterRadiusStops=[2,10,30,13,200,17];
const countNumber=new Intl.NumberFormat('en-GB');
function markerRadius(feature){
  if(!feature.properties.cluster)return feature.properties.count>1?7:4;
  const count=Number(feature.properties.race_count);
  for(let i=2;i<clusterRadiusStops.length;i+=2){
    if(count<=clusterRadiusStops[i]){const from=clusterRadiusStops[i-2],to=clusterRadiusStops[i];return clusterRadiusStops[i-1]+Math.max(0,(count-from)/(to-from))*(clusterRadiusStops[i+1]-clusterRadiusStops[i-1]);}
  }
  return clusterRadiusStops.at(-1);
}
export class Globe {
  constructor(container,{onHover,onSelect,onMove}) {
    this.container=container;this.onHover=onHover;this.onSelect=onSelect;this.onMove=onMove;this.points=[];this.cache=new Map();this.ready=false;this.hoverToken=0;this.viewRevision=0;this.highlightedRace=null;this.highlightRevision=0;this.highlightDirty=false;this.highlightedMarker=null;this.theme=document.documentElement.dataset.theme||'light';
  }
  async load() {
    const response=await fetch('./data/map-style.json');if(!response.ok)throw new Error('Map style unavailable');
    const style=await response.json();style.projection={type:'globe'};
    for(const layer of style.layers)Object.assign(layer.paint||={},themedPaint(layer,this.theme));
    this.map=new maplibregl.Map({container:this.container,style,center:[12,25],zoom:this.homeZoom(),minZoom:.5,maxZoom:17,maxPitch:60,attributionControl:false,canvasContextAttributes:{antialias:true},fadeDuration:150});
    this.map.addControl(new maplibregl.AttributionControl({compact:true}),'bottom-right');
    this.map.addControl(new maplibregl.ScaleControl({maxWidth:100,unit:'metric'}),'bottom-left');
    this.map.getCanvas().setAttribute('aria-label','Interactive race globe. Drag to pan, scroll or pinch to zoom; use arrow keys to move.');
    this.map.on('error',e=>{if(!this.mapReadyError&&e.error?.message){this.mapReadyError=e.error.message;console.warn('Map resource:',e.error.message);}});
    return new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>{if(!this.ready)reject(new Error('Map did not finish loading'));},30000);
      this.map.once('load',()=>{
        clearTimeout(timeout);this.ready=true;this.addRaceLayers();this.setTheme(this.theme);this.applyPoints();this.highlight(this.highlightedRace);
        this.map.on('move',()=>{this.hoverToken++;this.viewRevision++;this.onHover(null);this.onMove?.();});
        this.map.on('movestart',()=>this.queueHighlight());
        this.map.on('moveend',()=>this.onMove?.(true));
        this.map.on('sourcedata',e=>{if(e.sourceId==='races'&&e.isSourceLoaded)this.queueHighlight();});
        this.map.on('mousemove',e=>this.hover(e));
        this.map.on('mouseout',()=>{this.hoverToken++;this.onHover(null);});
        this.map.on('click',e=>this.click(e));
        this.observer=new ResizeObserver(()=>{this.map.resize();this.onMove?.(true);});this.observer.observe(this.container);
        this.onMove?.(true);resolve();
      });
    });
  }
  addRaceLayers() {
    const map=this.map;
    map.addSource('races',{type:'geojson',data:empty(),cluster:true,clusterRadius:34,clusterMaxZoom:13,clusterProperties:{race_count:['+',['get','count']],...Object.fromEntries(GRADES.map(g=>[g.property,['+',['get',g.property]]]))}});
    map.addLayer({id:'race-clusters',type:'circle',source:'races',filter:['has','point_count'],paint:{'circle-color':'#244e3e','circle-radius':['interpolate',['linear'],['get','race_count'],...clusterRadiusStops],'circle-stroke-width':2,'circle-stroke-color':'#faf7e9','circle-opacity':1}});
    map.addLayer({id:'race-points',type:'circle',source:'races',filter:['!', ['has','point_count']],paint:{'circle-color':'#244e3e','circle-radius':['case',['>',['get','count'],1],7,4],'circle-stroke-width':2,'circle-stroke-color':'#faf7e9'}});
    // Counts are drawn against the current camera on every frame. Symbol-layer
    // placement/fades can otherwise leave a count visible behind the globe.
    this.countCanvas=document.createElement('canvas');this.countCanvas.className='race-count-overlay';
    this.countCanvas.setAttribute('aria-hidden','true');this.container.append(this.countCanvas);
    this.countContext=this.countCanvas.getContext('2d');this.map.on('render',()=>{
      this.drawCounts();
      if(this.highlightDirty&&!map.isMoving()&&map.isSourceLoaded('races')){this.highlightDirty=false;void this.resolveHighlight();}
    });
    map.addSource('race-highlight',{type:'geojson',data:empty()});
    map.addLayer({id:'race-highlight-halo',type:'circle',source:'race-highlight',paint:{'circle-radius':['get','radius'],'circle-opacity':0,'circle-stroke-color':'#db691f','circle-stroke-width':3}});
  }
  setTheme(theme){
    this.theme=theme;if(!this.ready)return;
    for(const layer of this.map.getStyle().layers)for(const [property,value] of Object.entries(themedPaint(layer,theme)))this.map.setPaintProperty(layer.id,property,value);
  }
  setPoints(points) {this.points=points;this.pointByKey=new Map(points.map(p=>[p.key,p]));this.cache.clear();this.viewRevision++;this.hoverToken++;if(this.ready)this.applyPoints();}
  applyPoints(){
    this.queueHighlight();
    this.countContext?.clearRect(0,0,this.countCanvas.width,this.countCanvas.height);
    this.map.getSource('races').setData({type:'FeatureCollection',features:this.points.map(p=>({type:'Feature',geometry:{type:'Point',coordinates:[p.longitude,p.latitude]},properties:{key:p.key,count:p.count,race_count:p.count,category:p.category||'other',...Object.fromEntries(GRADES.map(g=>[g.property,p.gradeCounts?.[g.key]||0]))}}))});
  }
  drawCounts(){
    const canvas=this.countCanvas,ctx=this.countContext;if(!ctx)return;
    const width=this.container.clientWidth,height=this.container.clientHeight,ratio=window.devicePixelRatio||1;
    if(canvas.width!==Math.round(width*ratio)||canvas.height!==Math.round(height*ratio)){canvas.width=Math.round(width*ratio);canvas.height=Math.round(height*ratio);}
    ctx.setTransform(ratio,0,0,ratio,0,0);ctx.clearRect(0,0,width,height);
    const seen=new Set();this.drawnCounts=[];
    for(const feature of this.map.querySourceFeatures('races')){
      const props=feature.properties,count=Number(props.cluster?props.race_count:props.count);
      if(count<2)continue;
      const key=props.cluster?'cluster:'+props.cluster_id:props.key;if(seen.has(key))continue;seen.add(key);
      const point=this.visibleScreenPoint(feature.geometry.coordinates);
      if(!point||!this.map.transform.isPointOnMapSurface(point,this.map.terrain))continue;
      ctx.fillStyle=this.theme==='dark'?'#2b332b':'#fff9e8';
      ctx.font=(props.cluster?'700 9px':'700 8px')+' system-ui, sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
      ctx.fillText(countNumber.format(count),point.x,point.y+.5);
      this.drawnCounts.push({key,coordinates:feature.geometry.coordinates,count,x:point.x,y:point.y});
    }
  }
  visibleLocationIds() {
    if(!this.ready)return null;
    const ids=[];
    for(const p of this.points){
      if(!this.visibleScreenPoint([p.longitude,p.latitude]))continue;
      ids.push(...p.locationIds);
    }
    return [...new Set(ids)];
  }
  async featurePoint(feature) {
    const props=feature.properties,key=props.cluster?'cluster:'+props.cluster_id:props.key;
    if(this.cache.has(key))return this.cache.get(key);
    const revision=this.viewRevision;
    let point;
    if(props.cluster){const leaves=await this.map.getSource('races').getClusterLeaves(props.cluster_id,props.point_count,0);const points=leaves.map(f=>this.pointByKey.get(f.properties.key)).filter(Boolean);point={count:points.reduce((n,p)=>n+p.count,0),locationIds:points.flatMap(p=>p.locationIds),pointKeys:points.map(p=>p.key),cluster:true};}
    else point=this.pointByKey.get(props.key);
    if(point&&revision===this.viewRevision)this.cache.set(key,point);return point;
  }
  visibleScreenPoint(coordinates){
    const location=maplibregl.LngLat.convert(coordinates),map=this.map;
    // Use the same camera clipping test as MapLibre's own markers, including the horizon.
    if(map.transform.isLocationOccluded(location))return null;
    const p=map.project(location);
    return Number.isFinite(p.x)&&Number.isFinite(p.y)&&p.x>=0&&p.y>=0&&p.x<=this.container.clientWidth&&p.y<=this.container.clientHeight?p:null;
  }
  featuresAt(point){
    if(!this.ready||!this.map.transform.isPointOnMapSurface(point,this.map.terrain))return [];
    return this.map.queryRenderedFeatures([[point.x-8,point.y-8],[point.x+8,point.y+8]],{layers:raceLayers}).filter(feature=>{
      const p=this.visibleScreenPoint(feature.geometry.coordinates);
      return p&&Math.hypot(p.x-point.x,p.y-point.y)<=markerRadius(feature)+9;
    });
  }
  async hover(e){const features=this.featuresAt(e.point);this.map.getCanvas().style.cursor=features.length?'pointer':'';const token=++this.hoverToken;if(!features.length){this.onHover(null);return;}try{const point=await this.featurePoint(features[0]);if(token===this.hoverToken&&point)this.onHover(point,e.point);}catch{this.onHover(null);}}
  async click(e){const feature=this.featuresAt(e.point)[0];if(!feature)return;const revision=this.viewRevision;try{const point=await this.featurePoint(feature);if(point&&revision===this.viewRevision)this.onSelect(point);}catch{}}
  highlight(race){
    this.highlightedRace=race;if(!this.ready)return;
    const coordinates=race?.longitude!=null&&race?.latitude!=null?[race.longitude,race.latitude]:null;
    this.queueHighlight();
    if(coordinates&&!this.visibleScreenPoint(coordinates))this.map.easeTo({center:coordinates,zoom:this.map.getZoom(),duration:this.duration(450)});
  }
  queueHighlight(){
    this.highlightRevision++;this.highlightDirty=!!this.highlightedRace;
    if(this.highlightedMarker){this.map.getSource('race-highlight').setData(empty());this.highlightedMarker=null;}
    if(this.highlightDirty)this.map.triggerRepaint();
  }
  async resolveHighlight(){
    const race=this.highlightedRace,revision=this.highlightRevision;
    if(!race||race.longitude==null||race.latitude==null)return;
    const key=`${race.longitude},${race.latitude}`;
    if(!this.pointByKey.has(key))return;
    const position=this.visibleScreenPoint([race.longitude,race.latitude]);if(!position)return;
    // A whole-viewport rendered query can miss front-facing features on the globe.
    // Start with loaded bubbles, then confirm the matching bubble with a local hit.
    const seen=new Set(),features=this.map.querySourceFeatures('races').filter(f=>{
      const markerKey=f.properties.cluster?'cluster:'+f.properties.cluster_id:f.properties.key;
      if(seen.has(markerKey)||!this.visibleScreenPoint(f.geometry.coordinates))return false;
      seen.add(markerKey);return true;
    });
    // Check actual cluster membership, rather than guessing from nearby coordinates.
    // Cached leaves make subsequent sidebar hovers within the same group immediate.
    const distance=f=>{const p=this.map.project(f.geometry.coordinates);return Math.hypot(p.x-position.x,p.y-position.y);};
    features.sort((a,b)=>distance(a)-distance(b));
    try{
      for(const feature of features){
        const props=feature.properties;
        const contains=props.cluster?(await this.featurePoint(feature))?.pointKeys.includes(key):props.key===key;
        if(revision!==this.highlightRevision)return;
        if(!contains)continue;
        const markerKey=props.cluster?'cluster:'+props.cluster_id:props.key;
        const rendered=this.featuresAt(this.map.project(feature.geometry.coordinates)).find(f=>(f.properties.cluster?'cluster:'+f.properties.cluster_id:f.properties.key)===markerKey);
        if(!rendered)continue;
        const marker={type:'Feature',geometry:rendered.geometry,properties:{raceId:race.id,markerKey,radius:markerRadius(rendered)+5}};
        this.highlightedMarker=marker;this.map.getSource('race-highlight').setData({type:'FeatureCollection',features:[marker]});return;
      }
    }catch{/* A source refresh can invalidate a pending cluster query. */}
  }
  duration(ms){return matchMedia('(prefers-reduced-motion: reduce)').matches?0:ms;}
  zoomBy(delta){if(this.ready)this.map.zoomTo(this.map.getZoom()+delta,{duration:this.duration(280)});}
  homeZoom(){return Math.max(.5,Math.min(2.1,2.1+Math.log2(Math.min(this.container.clientWidth,this.container.clientHeight)/656)));}
  reset(){if(this.ready)this.map.flyTo({center:[12,25],zoom:this.homeZoom(),pitch:0,bearing:0,duration:this.duration(700)});}
  focus(race){if(this.ready&&race.longitude!=null)this.map.flyTo({center:[race.longitude,race.latitude],zoom:Math.max(this.map.getZoom(),6),duration:this.duration(650)});}
}
