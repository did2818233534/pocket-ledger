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
  assert.deepEqual(s.totals,{daily:101,extra:590,claim:209});
});
test('money parsing never rounds fractions silently',()=>{
  assert.equal(M.cents('0.29'),29);assert.equal(M.cents('12.3'),1230);
  for(const value of ['0','-1','1.234','abc','1e3','Infinity','1000000000'])assert.throws(()=>M.cents(value));
});
