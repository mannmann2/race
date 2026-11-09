import test from 'node:test';
import assert from 'node:assert/strict';
import {expandDataset,correctLocation} from '../web/core.mjs';

test('location corrections apply before merging and preserve original source facts',()=>{
  const data={schemaVersion:2,fetchedAt:'2026-11-09',countries:{GB:{name:'United Kingdom',continent:'Europe'},US:{name:'United States',continent:'North America'}},
    events:[['1','Welsh race']],locations:[['Bangor','GB',-5.67,54.66,'town','ni']],
    records:[['1',0,'50K','2026-11-14',50,2000,'50k',0,null,null,'qualifier',0]],
    locationCorrections:{'utmb:1':{longitude:-4.13,latitude:53.23,geonamesId:'wales',locationId:'geonames:wales'}},
    additionalRaces:[{matchId:'utmb:1',race:{id:'itra:2026:2',source:'itra',sourceId:'2026:2',name:'50K',date:'2026-11-14',countryCode:'GB',longitude:-4.12,latitude:53.23,locationPrecision:'event',extensions:{itra:{endurancePoints:2}}}}]};
  const [race]=expandDataset(data);assert.equal(race.longitude,-4.13);assert.equal(race.geonamesId,'wales');
  assert.equal(race.sources[0].values.place,'Bangor');assert.equal(race.sources.length,2);
  const moved=correctLocation({id:'utmb:2',countryCode:'SL'},{'utmb:2':{countryCode:'ES',country:'Spain',continent:'Europe',id:'do-not-overwrite'}});
  assert.equal(moved.countryCode,'ES');assert.equal(moved.id,'utmb:2');
});

test('standalone incoming records receive corrections as well as primary records',()=>{
  const races=expandDataset({schemaVersion:2,records:[],countries:{},locationCorrections:{'itra:2026:2':{longitude:-.74,latitude:51.76,locationPrecision:'town'}},additionalRaces:[{matchId:null,race:{id:'itra:2026:2',name:'Wendover',source:'itra',sourceId:'2026:2',longitude:-114,latitude:40,extensions:{}}}]});
  assert.equal(races[0].longitude,-.74);assert.equal(races[0].locationPrecision,'town');
});
