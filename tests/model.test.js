const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../app/src/main/assets/model.js');
test('calendar boundaries: Monday, new year, leap year, inclusive windows', () => {
  assert.deepEqual(M.period('week',new Date(2026,9,19)),{start:'2026-10-19',end:'2026-10-19'});
  assert.deepEqual(M.period('week',new Date(2026,9,25)),{start:'2026-10-19',end:'2026-10-25'});
  assert.deepEqual(M.period('7',new Date(2026,0,2)),{start:'2025-12-27',end:'2026-01-02'});
  assert.deepEqual(M.period('30',new Date(2024,2,1)),{start:'2024-02-01',end:'2024-03-01'});
  assert.equal(M.stats([], '7', new Date(2026,2,10)).days.length,7);
});
test('all categories, no future spending, zero-filled days and exact cents',()=>{
  const entries=[
    {at:'2026-10-20T12:00',amount:101,category:'daily'},
    {at:'2026-10-20T14:00',amount:209,category:'claim'},
    {at:'2026-10-19T23:59',amount:590,category:'extra'},
    {at:'2026-10-21T00:00',amount:999,category:'daily'},
    {at:'2026-09-30T23:59',amount:999,category:'daily'}
  ];
  const s=M.stats(entries,'month',new Date(2026,9,20));
  assert.equal(s.total,900);assert.equal(s.days.length,20);assert.equal(s.days[0].amount,0);
  assert.equal(s.days[19].amount,310);assert.equal(s.count,3);
  assert.deepEqual(s.totals,{daily:101,extra:590,claim:209,giving:0});
});
test('money parsing never rounds fractions silently',()=>{
  assert.equal(M.cents('0.29'),29);assert.equal(M.cents('12.3'),1230);
  for(const value of ['0','-1','1.234','abc','1e3','Infinity','1000000000'])assert.throws(()=>M.cents(value));
});
test('giving is included in every period and daily totals alongside older entries',()=>{
  const entries=[
    {at:'2026-10-20T12:00',amount:30000,category:'giving'},
    {at:'2026-10-20T13:00',amount:5000,category:'daily'}
  ];
  for(const period of ['month','week','7','30']){
    const s=M.stats(entries,period,new Date(2026,9,20));
    assert.equal(s.total,35000);
    assert.equal(s.totals.giving,30000);
    assert.equal(s.totals.daily,5000);
    assert.equal(s.days.at(-1).amount,35000);
    assert.equal(s.count,2);
  }
});
test('calculator respects precedence, nested brackets and exact final rounding',()=>{
 for(const [expression,expected] of [['480*2',96000],['(480+20)*2',100000],['2*(3+(4/2))',1000],['（10+2）÷3',400],['0.1+0.2',30],['1/3*3',100],['1.005',101],['.5+2.',250],['10--2',1200],['999999999.99',99999999999]])assert.equal(M.calculateAmount(expression),expected,expression);
});
test('calculator rejects malformed, unsafe, zero, negative and overflowing amounts',()=>{
 for(const expression of ['', '1+', '(2+3', '2(3)', '1/0', '1/(2-2)', '-2', '0.001', '1000000000', '1e3', 'alert(1)', '2**3', '1 2', '1'.repeat(121)])assert.throws(()=>M.calculateAmount(expression),expression);
});
test('note charts merge identical names across categories and parent notes within the selected period',()=>{
 const rows=[{at:'2026-10-20T12:00',amount:100,category:'daily',primaryNote:'吃饭',note:'面'},{at:'2026-10-20T13:00',amount:200,category:'extra',primaryNote:'吃饭',note:'面'},{at:'2026-10-20T14:00',amount:400,category:'claim',primaryNote:'出差',note:'面'},{at:'2026-10-20T15:00',amount:50,category:'giving',note:''},{at:'2026-09-01T12:00',amount:999,category:'daily',primaryNote:'吃饭',note:'面'}];
 const now=new Date(2026,9,20);
 assert.equal(M.breakdown(rows,'month','primaryNote',now).find(g=>g.key==='吃饭').amount,300);
 assert.equal(M.breakdown(rows,'month','note',now).find(g=>g.key==='面').amount,700);
 assert.equal(M.breakdown(rows,'month','note',now).find(g=>g.key==='').amount,50);
 assert.equal(M.breakdown(rows.slice(0,1),'month','note',now)[0].amount,100);
});
test('manual dates normalize separators and reject impossible days',()=>{
 for(const value of ['2024-2-29','2024/02/29','2024.02.29'])assert.equal(M.dateOnly(value),'2024-02-29');
 for(const value of ['2025-02-29','2026-04-31','2026-13-01','2026-00-01','2026-01-00','2026-10-20T12:00','abc'])assert.throws(()=>M.dateOnly(value));
});
test('eye exclusions update every statistic while retaining restorable legend items',()=>{
 const now=new Date(2026,9,20),rows=[
 {at:'2026-10-20',amount:3000,category:'daily',primaryNote:'吃饭',note:'面'},
 {at:'2026-10-19',amount:2000,category:'extra',primaryNote:'吃饭',note:'咖啡'},
 {at:'2026-10-20',amount:1000,category:'claim',primaryNote:'出差',note:'面'},
 {at:'2026-10-20',amount:500,category:'giving',primaryNote:'',note:''}];
 const r=M.reportData(rows,'month','primaryNote',['吃饭'],now);
 assert.equal(r.summary.total,1500);assert.equal(r.summary.count,2);assert.equal(r.summary.totals.claim,1000);
 assert.equal(r.summary.days.reduce((sum,d)=>sum+d.amount,0),1500);
 assert.equal(r.groups.find(g=>g.key==='吃饭').excluded,true);assert.equal(r.groups.length,3);
 assert.equal(M.reportData(rows,'7','note',['面'],now).summary.total,2500);
 assert.equal(M.reportData(rows,'week','category',['claim'],now).summary.total,5500);
 assert.equal(M.reportData(rows,'month','note',[''],now).summary.total,6000);
 const none=M.reportData(rows,'month','category',['daily','extra','claim','giving'],now);
 assert.equal(none.summary.total,0);assert.equal(none.summary.count,0);assert.ok(none.summary.days.every(d=>d.amount===0));assert.equal(none.groups.length,4);
 assert.equal(M.reportData(rows,'month','category',[],now).summary.total,6500);
 assert.equal(M.stats(rows,'month',now).total,6500);
});
