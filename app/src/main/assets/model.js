(function(root){
'use strict';
const categories={daily:{name:'日常生活',color:'#257d61',bg:'#eaf2eb',icon:'⌂'},extra:{name:'额外支出',color:'#d99957',bg:'#fbf0e3',icon:'✦'},claim:{name:'报销垫付',color:'#9380bc',bg:'#f1ecf7',icon:'↗'},giving:{name:'借出赠与',color:'#648eae',bg:'#eaf1f7',icon:'♡'}};
function day(d){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function period(type,now=new Date()) {const end=new Date(now.getFullYear(),now.getMonth(),now.getDate());const start=new Date(end);if(type==='month')start.setDate(1);else if(type==='week')start.setDate(start.getDate()-(start.getDay()+6)%7);else start.setDate(start.getDate()-(type==='30'?29:6));return {start:day(start),end:day(end)}}
function stats(entries,type,now=new Date()){const range=period(type,now);const days=[];for(let d=new Date(range.start+'T12:00:00');day(d)<=range.end;d.setDate(d.getDate()+1))days.push({date:day(d),amount:0});const totals=Object.fromEntries(Object.keys(categories).map(k=>[k,0]));const included=entries.filter(e=>e.at.slice(0,10)>=range.start&&e.at.slice(0,10)<=range.end);for(const e of included){totals[e.category]+=e.amount;days.find(d=>d.date===e.at.slice(0,10)).amount+=e.amount}return {...range,days,totals,total:included.reduce((s,e)=>s+e.amount,0),count:included.length}}
function cents(value){if(!/^\d{1,9}(\.\d{1,2})?$/.test(value))throw Error('金额最多 9 位整数、2 位小数');const [a,b='']=value.split('.');const n=Number(a)*100+Number(b.padEnd(2,'0'));if(n<=0)throw Error('请输入大于零的金额');return n}
const api={categories,day,period,stats,cents};if(typeof module!=='undefined')module.exports=api;root.LedgerModel=api;
})(globalThis);
