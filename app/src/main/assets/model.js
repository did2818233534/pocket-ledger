(function(root){
'use strict';
const categories={daily:{name:'日常生活',color:'#257d61',bg:'#eaf2eb',icon:'⌂'},extra:{name:'额外支出',color:'#d99957',bg:'#fbf0e3',icon:'✦'},claim:{name:'报销垫付',color:'#9380bc',bg:'#f1ecf7',icon:'↗'},giving:{name:'借出赠与',color:'#648eae',bg:'#eaf1f7',icon:'♡'}};
function day(d){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function period(type,now=new Date()) {const end=new Date(now.getFullYear(),now.getMonth(),now.getDate());const start=new Date(end);if(type==='month')start.setDate(1);else if(type==='week')start.setDate(start.getDate()-(start.getDay()+6)%7);else start.setDate(start.getDate()-(type==='30'?29:6));return {start:day(start),end:day(end)}}
function stats(entries,type,now=new Date()){const range=period(type,now);const days=[];for(let d=new Date(range.start+'T12:00:00');day(d)<=range.end;d.setDate(d.getDate()+1))days.push({date:day(d),amount:0});const totals=Object.fromEntries(Object.keys(categories).map(k=>[k,0]));const included=entries.filter(e=>e.at.slice(0,10)>=range.start&&e.at.slice(0,10)<=range.end);for(const e of included){totals[e.category]+=e.amount;days.find(d=>d.date===e.at.slice(0,10)).amount+=e.amount}return {...range,days,totals,total:included.reduce((s,e)=>s+e.amount,0),count:included.length}}
function cents(value){if(!/^\d{1,9}(\.\d{1,2})?$/.test(value))throw Error('金额最多 9 位整数、2 位小数');const [a,b='']=value.split('.');const n=Number(a)*100+Number(b.padEnd(2,'0'));if(n<=0)throw Error('请输入大于零的金额');return n}
function dateOnly(value){
 const match=String(value).trim().match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/);
 if(!match)throw Error('请填写日期，例如 2026-10-20');
 const y=Number(match[1]),m=Number(match[2]),d=Number(match[3]);
 if(y<1900||y>9999||m<1||m>12||d<1||d>new Date(y,m,0).getDate())throw Error('日期无效，请检查年月日');
 return `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
}
function breakdown(entries,type,dimension='category',now=new Date()){
 const range=period(type,now),groups=new Map();
 for(const e of entries){if(e.at.slice(0,10)<range.start||e.at.slice(0,10)>range.end)continue;
  const key=dimension==='category'?e.category:(e[dimension]||'').trim();
  const item=groups.get(key)||{key,name:dimension==='category'?categories[key].name:key||'未填写',amount:0,count:0};
  item.amount+=e.amount;item.count++;groups.set(key,item);
 }
 return [...groups.values()].sort((a,b)=>b.amount-a.amount||a.name.localeCompare(b.name,'zh-CN'));
}
function filterEntries(entries,filters={},month=''){
 return entries.filter(e=>{const date=e.at.slice(0,10);
  if(filters.start||filters.end){if(filters.start&&date<filters.start||filters.end&&date>filters.end)return false}
  else if(month&&!date.startsWith(month))return false;
  return ['category','primaryNote','note'].every(key=>filters[key]==null||(Array.isArray(filters[key])?filters[key].includes(key==='category'?e.category:(e[key]||'').trim()):(key==='category'?e.category:(e[key]||'').trim())===filters[key]));
 }).slice().sort((a,b)=>b.at.localeCompare(a.at)||a.id.localeCompare(b.id));
}
function statisticalEntries(entries){return entries.filter(e=>!(e.category==='claim'&&e.reimbursed))}
function reportData(entries,type,dimension='category',excluded=[],now=new Date()){
 entries=statisticalEntries(entries);
 const hidden=new Set(excluded);
 const included=entries.filter(e=>!hidden.has(dimension==='category'?e.category:(e[dimension]||'').trim()));
 return {summary:stats(included,type,now),groups:breakdown(entries,type,dimension,now).map(g=>({...g,excluded:hidden.has(g.key)}))};
}
// Parse arithmetic as exact rational values; round only the final result to cents.
function calculateAmount(value){
 const text=String(value).replace(/×/g,'*').replace(/÷/g,'/').replace(/（/g,'(').replace(/）/g,')').trim();
 if(!text||text.length>120)throw Error('请输入金额或算式（最多 120 个字符）');
 let at=0;
 const skip=()=>{while(/\s/.test(text[at]||'')&&at<text.length)at++};
 const fail=()=>{throw Error('算式不完整，请检查数字、运算符和括号')};
 function atom(){
  skip();let sign=1n;
  while(text[at]==='+'||text[at]==='-'){if(text[at++]==='-')sign=-sign;skip()}
  let v;
  if(text[at]==='('){at++;v=sum();skip();if(text[at++]!==')')fail()}
  else{const m=text.slice(at).match(/^(?:\d+(?:\.\d*)?|\.\d+)/);if(!m)fail();at+=m[0].length;const [whole,frac='']=m[0].split('.');v=[BigInt((whole||'0')+frac),10n**BigInt(frac.length)]}
  return [v[0]*sign,v[1]];
 }
 function product(){let v=atom();while(true){skip();const op=text[at];if(op!=='*'&&op!=='/')return v;at++;const w=atom();if(op==='/'){if(w[0]===0n)throw Error('不能除以零');v=[v[0]*w[1],v[1]*w[0]]}else v=[v[0]*w[0],v[1]*w[1]];if(v[1]<0n)v=[-v[0],-v[1]]}}
 function sum(){let v=product();while(true){skip();const op=text[at];if(op!=='+'&&op!=='-')return v;at++;const w=product();v=[v[0]*w[1]+(op==='+'?1n:-1n)*w[0]*v[1],v[1]*w[1]]}}
 const [n,d]=sum();skip();if(at!==text.length)fail();
 const result=(n*200n+d)/(2n*d);
 if(n<=0n||result<=0n)throw Error('金额需大于零，且四舍五入后至少为 0.01 元');
 if(result>99999999999n)throw Error('金额最多 9 位整数、2 位小数');
 return Number(result);
}
const api={categories,day,period,stats,breakdown,filterEntries,statisticalEntries,reportData,dateOnly,cents,calculateAmount};if(typeof module!=='undefined')module.exports=api;root.LedgerModel=api;
})(globalThis);
