const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const model=require('../app/src/main/assets/model.js');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/src/main/assets/app.js'),'utf8');
function fixture(saved={}){
 const inputs={};let renders=0;
 const c=vm.createContext({LedgerModel:model,Native:{statsPreferences:()=>JSON.stringify(saved),setStatsPeriodEnabled:(k,v)=>saved[k]=v},document:{querySelectorAll:()=>[],activeElement:null},$:id=>inputs[id],render:()=>renders++,pickInputDate:()=>{}});
 vm.runInContext("let periodType='7';"+source.slice(source.indexOf('const statsPreferences='),source.indexOf('function expenseReport()')),c);
 return {c,inputs,renders:()=>renders,run:s=>vm.runInContext(s,c)};
}
test('default/custom period controls and persisted optional tabs',()=>{
 const f=fixture();const html=f.run('statsPeriodControls()');
 assert(!html.includes('data-period="month"'));assert(!html.includes('data-period="week"'));
 assert(html.includes('data-period="custom"'));
 const saved={month:true,week:true},g=fixture(saved);assert(g.run('statsPeriodControls()').includes('data-period="month"'));
 g.run("periodType='custom'");assert(g.run('statsPeriodControls()').includes('custom-range-panel'));
});
test('custom edits apply automatically; invalid range preserves the applied statistics',()=>{
 const f=fixture();f.inputs['stats-range']={};f.inputs['stats-range-error']={textContent:''};
 f.inputs['stats-start']={value:'2026-10-01'};f.inputs['stats-end']={value:'2026-10-31'};
 f.run('bindStatsRange()');f.inputs['stats-start'].onchange();
 assert.equal(f.run('customStatsRange.end'),'2026-10-31');assert.equal(f.renders(),1);
 f.inputs['stats-start'].value='2026-11-01';f.inputs['stats-start'].onchange();
 assert.equal(f.run('customStatsRange.start'),'2026-10-01');assert(f.inputs['stats-range-error'].textContent);
});
