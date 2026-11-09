import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {raceGrade,raceGrades,GRADES,UTMB_COLORS,ITRA_COLORS} from '../web/grades.mjs';
import {groupLocations} from '../web/core.mjs';
const race=(utmb,itra)=>({id:'fixture',extensions:{utmb:{category:utmb},itra:{endurancePoints:itra}},longitude:7,latitude:46,locationId:1});
test('source grade priority uses supplied UTMB category, otherwise ITRA points including zero',()=>{
 for(const category of Object.keys(UTMB_COLORS))for(const points of [0,1,6,null])assert.equal(raceGrade(race(category,points)).key,'utmb:'+category);
 for(let points=0;points<=6;points++)assert.equal(raceGrade(race(null,points)).key,'itra:'+points);
 for(const points of [null,undefined,-1,7,'3',1.5])assert.equal(raceGrade(race(null,points)).key,'other');
 assert.equal(raceGrade(race('unknown',4)).key,'itra:4');
});
test('official SVG badges exist and their color equals the card grade color',()=>{
 for(const grade of GRADES.filter(g=>g.icon)){
  const svg=readFileSync(new URL('../web/'+grade.icon.slice(2),import.meta.url),'utf8').toLowerCase();
  assert.match(svg,/<svg/);assert.ok(svg.includes(grade.color)||(grade.color==='#ffff00'&&svg.includes('#ff0')));
 }
 assert.equal(ITRA_COLORS[0],'#797b77');
});
test('colocated groups preserve each race grade instead of taking the first race color',()=>{
 const input=[race('50k',6),race(null,3),race('50k',null),{...race(null,0),longitude:null}];
 const [group]=groupLocations(input);assert.equal(group.count,3);
 assert.deepEqual(group.gradeCounts,{'utmb:50k':2,'itra:3':1});
 const reverse=groupLocations(input.slice().reverse())[0];assert.deepEqual(reverse.gradeCounts,group.gradeCounts);
});

test('display both supplied badges in provider order without changing the primary color',()=>{
 assert.deepEqual(raceGrades(race('50k',6)).map(g=>g.key),['utmb:50k','itra:6']);
 assert.deepEqual(raceGrades(race('20k',0)).map(g=>g.key),['utmb:20k','itra:0']);
 assert.deepEqual(raceGrades(race(null,3)).map(g=>g.key),['itra:3']);
 assert.deepEqual(raceGrades(race('100m',null)).map(g=>g.key),['utmb:100m']);
 assert.deepEqual(raceGrades(race(null,null)),[]);
 assert.equal(raceGrade(race('50k',6)).color,UTMB_COLORS['50k']);
});
