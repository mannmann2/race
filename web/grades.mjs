// Colors and badges are taken from the providers' original SVG assets.
export const UTMB_COLORS={'20k':'#ffff00','50k':'#fc5a00','100k':'#7ddf64','100m':'#f42525'};
export const ITRA_COLORS=['#797b77','#8cce3c','#d1c40a','#5bc9ee','#b16da7','#da702d','#b53229'];
const luminance=color=>{const rgb=color.slice(1).match(/../g).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2];};
export function gradeInk(color){const l=luminance(color),ink=luminance('#07152d');return (l+.05)/(ink+.05)>=1.05/(l+.05)?'#07152d':'#ffffff';}
export const GRADES=[
 ...Object.entries(UTMB_COLORS).map(([category,color])=>({key:'utmb:'+category,provider:'utmb',label:'UTMB '+category.toUpperCase(),color,icon:'./assets/grades/utmb-'+category+'.svg'})),
 ...ITRA_COLORS.map((color,points)=>({key:'itra:'+points,provider:'itra',label:'ITRA '+points+' Endurance Points',color,icon:'./assets/grades/itra-'+points+'.svg'})),
 {key:'other',provider:null,label:'No grade supplied',color:'#9baaaa',icon:null}
].map((g,i)=>({...g,property:'grade_'+i,ink:gradeInk(g.color)}));
export const GRADE_BY_KEY=Object.fromEntries(GRADES.map(g=>[g.key,g]));
export function raceGrade(race){
 const category=race.extensions?.utmb?.category;
 if(Object.hasOwn(UTMB_COLORS,category))return GRADE_BY_KEY['utmb:'+category];
 const points=race.extensions?.itra?.endurancePoints;
 if(Number.isInteger(points)&&points>=0&&points<=6)return GRADE_BY_KEY['itra:'+points];
 return GRADE_BY_KEY.other;
}
// Homogeneous groups use their shared grade; mixed groups get a neutral center
// and a segmented ring rather than a misleading grade from their first race.
export function groupGradeExpression(neutral){
 return ['case',...GRADES.flatMap(g=>[['==',['get',g.property],['get','race_count']],g.color]),neutral];
}

export function raceGrades(race){
 const primary=raceGrade(race),points=race.extensions?.itra?.endurancePoints;
 const itra=Number.isInteger(points)&&points>=0&&points<=6?GRADE_BY_KEY['itra:'+points]:null;
 return primary.provider==='utmb'&&itra?[primary,itra]:primary.icon?[primary]:[];
}
