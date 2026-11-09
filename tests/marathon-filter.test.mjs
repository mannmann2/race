import test from 'node:test';
import assert from 'node:assert/strict';
import {isMarathon,matches,combineRace} from '../web/core.mjs';
const race={id:'utmb:fixture',source:'utmb',sourceId:'fixture',name:'Course',distanceKm:42.195,date:'2027-05-01',countryCode:'FR',searchText:'course',extensions:{utmb:{category:'50k'}}};
const filter={categories:['42']};
test('42 selects marathon distance independently of UTMB grades and source',()=>{
 for(const category of ['20k','50k','100k','100m',null])assert.ok(matches({...race,extensions:{utmb:{category}}},filter,'2027-01-01'));
 assert.ok(matches({...race,source:'itra',extensions:{itra:{endurancePoints:2}}},filter,'2027-01-01'));
 for(const distanceKm of [42,42.16,42.195,42.2,42.3])assert.ok(isMarathon({...race,distanceKm}));
 for(const distanceKm of [null,0,21.1,41.9,42.31,50,84.39])assert.equal(isMarathon({...race,distanceKm}),false);
 assert.equal(isMarathon({...race,name:'Half Marathon',distanceKm:21.1}),false);
});
test('merged marathon listings retain classification despite conflicting distances',()=>{
 const wm={...race,id:'worldsmarathons:fixture',source:'worldsmarathons',distanceKm:42.195,extensions:{worldsmarathons:{listingType:'marathon-event'}}};
 const merged=combineRace({...race,distanceKm:44.3},wm);
 assert.ok(matches(merged,filter,'2027-01-01'));
 const measured={...race,distanceKm:41.8,sources:[{provider:'itra',values:{distanceKm:42}}]};
 assert.ok(isMarathon(measured));
 assert.equal(isMarathon({...race,distanceKm:50,extensions:{worldsmarathons:{listingType:'other'}}}),false);
});
test('category buttons form a union; source, date and numeric filters still narrow it',()=>{
 const ultra={...race,distanceKm:50};
 assert.ok(matches(ultra,{categories:['42','50k']},'2027-01-01'));
 assert.equal(matches(ultra,filter,'2027-01-01'),false);
 assert.ok(matches({...race,extensions:{utmb:{category:'20k'}}},{categories:['42','50k']},'2027-01-01'));
 assert.equal(matches(race,{...filter,source:'itra'},'2027-01-01'),false);
 assert.equal(matches(race,{...filter,to:'2027-04-30'},'2027-01-01'),false);
 assert.equal(matches(race,{...filter,distanceMin:43},'2027-01-01'),false);
 assert.ok(matches(ultra,{categories:[]},'2027-01-01'));
});
