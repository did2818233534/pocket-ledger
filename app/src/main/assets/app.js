'use strict';
const {categories:C,day,stats,cents}=LedgerModel;
let editorInitial='',page='ledger',periodType='month',data,editing=null,month=day(new Date()).slice(0,7);
const $=id=>document.getElementById(id),money=n=>(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function load(){data=JSON.parse(Native.load());if(data.error)throw Error(data.error)}
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2500)}
function header(title,sub){return `<header><div><div class="eyebrow">${sub}</div><h1>${title}</h1></div><span class="badge">● 本地优先</span></header>`}
function render(){load();document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('add').hidden=page==='sync';$('app').innerHTML=page==='ledger'?ledger():page==='stats'?report():syncPage();bind()}
function ledger(){const m=stats(data.entries,'month'),w=stats(data.entries,'week');const entries=data.entries.filter(e=>e.at.startsWith(month));let html=header('小账','A LITTLE EVERY DAY')+`<section class="hero"><small>本月累计支出</small><div class="total"><b>¥</b>${money(m.total)}</div><div class="hero-bottom"><div><small>本周支出</small><strong>¥ ${money(w.total)}</strong></div><div><small>本月记账</small><strong>${m.count} <small>笔</small></strong></div></div></section><div class="categories">${Object.entries(C).map(([k,c])=>`<div class="mini"><span><i class="dot" style="background:${c.color}"></i>${c.name}</span><strong>¥ ${money(m.totals[k])}</strong></div>`).join('')}</div><div class="section-title"><h2>支出明细</h2><div class="toolbar"><input id="month" type="month" aria-label="流水月份" value="${month}"></div></div>`;
if(!entries.length)return html+'<div class="card empty"><b>从第一笔小账开始</b>点击右下角 ＋ 记录一笔支出<br>离线也能安心记账</div>';
for(const date of [...new Set(entries.map(e=>e.at.slice(0,10)))]){const rows=entries.filter(e=>e.at.startsWith(date));html+=`<div class="day-title"><span>${esc(date)}</span><span>支出 ¥ ${money(rows.reduce((s,e)=>s+e.amount,0))}</span></div><div>${rows.map(e=>`<button class="entry" data-edit="${e.id}"><span class="entry-icon" style="background:${C[e.category].bg};color:${C[e.category].color}">${C[e.category].icon}</span><span class="entry-info"><strong>${esc(e.note||C[e.category].name)}</strong><small>${e.at.slice(11,16)} · ${C[e.category].name}</small></span><span class="entry-amount">−${money(e.amount)}</span></button>`).join('')}</div>`}return html+'<p class="footnote">每一笔，都留在你的手机里</p>'}
function report(){const s=stats(data.entries,periodType);let accumulated=0;const gradient=Object.entries(C).map(([k,c])=>{const start=accumulated;accumulated+=s.total?s.totals[k]/s.total*100:0;return `${c.color} ${start}% ${accumulated}%`}).join(',');const max=Math.max(1,...s.days.map(d=>d.amount));return header('花销有数','SPENDING INSIGHTS')+`<div class="tabs">${[['month','当月'],['week','本周'],['7','近 7 天'],['30','近 30 天']].map(([k,n])=>`<button data-period="${k}" class="${periodType===k?'active':''}">${n}</button>`).join('')}</div><section class="card"><span class="hint">总支出 · 含报销垫付</span><div class="stat-total">¥ ${money(s.total)}</div><span class="range">${s.start} — ${s.end}</span><div class="chart-row"><div class="ring" style="background:${s.total?'conic-gradient('+gradient+')':'#edf0e9'}"><div class="ring-hole"><strong>${s.count}</strong><small>笔支出</small></div></div><div class="legend">${Object.entries(C).map(([k,c])=>`<div class="legend-item"><i class="dot" style="background:${c.color}"></i>${c.name}<strong>${s.total?(s.totals[k]/s.total*100).toFixed(1):'0.0'}%</strong><small>¥ ${money(s.totals[k])}</small></div>`).join('')}</div></div></section><section class="card"><div class="section-title" style="margin:0"><h2>每天花了多少</h2><span>元 · 点击柱查看</span></div><div class="bars">${s.days.map(d=>`<div class="bar-col"><button class="bar" aria-label="${d.date} 支出 ${money(d.amount)} 元" data-bar="${d.date} · ¥ ${money(d.amount)}" style="height:${d.amount/max*100}%"></button></div>`).join('')}</div><div class="bar-labels"><span>${s.start.slice(5)}</span><span>最高 ¥ ${money(max===1&&s.total===0?0:max)}</span><span>${s.end.slice(5)}</span></div><div id="bar-detail" class="chart-hint">${s.count?'点击柱状图查看当天金额':'这个时间段还没有支出记录'}</div></section><div class="metrics"><div class="card"><span class="hint">日均支出</span><strong>¥ ${money(Math.round(s.total/s.days.length))}</strong></div><div class="card"><span class="hint">自付支出</span><strong>¥ ${money(s.total-s.totals.claim)}</strong></div></div><p class="footnote">本周从周一开始 · 近 7 / 30 天包含今天</p>`}
function syncPage(){return header('只在身边同步','LOCAL CONNECTION')+`<section class="card"><div class="sync-symbol">⇄</div><h2 id="sync-status">${esc(data.status)}</h2><p class="hint" id="sync-time">${syncDetail()}</p><button id="sync-now" class="primary">立即同步</button><p class="hint">${data.enabled?'自动同步已开启 · 每 1 分钟检查电脑':'自动同步未开启'}</p>${data.enabled?'<button id="pause" class="text-button">暂停自动同步</button>':''}</section><section class="card"><h2>连接我的电脑</h2><p class="hint">手机和电脑连接同一局域网，在电脑运行配对命令后填写以下信息。</p><label>电脑局域网地址<input id="host" inputmode="decimal" placeholder="192.168.1.8" value="${esc(data.host)}"></label><label>配对密钥<input id="key" type="password" autocomplete="off" placeholder="${data.paired?'已保存，留空沿用原密钥':'电脑显示的 64 位密钥'}"></label><button id="pair" class="secondary">保存并开启自动同步</button></section><section class="card"><h2>数据与备份</h2><p class="hint">账目保存在手机，电脑保存完整副本。修改、删除也会同步到电脑。</p><button id="export" class="secondary">导出手机账本 JSON</button><details style="margin-top:18px"><summary>同步和后台运行说明</summary><p>电脑每 20 秒发送带签名的局域网探测。手机收到后立即尝试同步；未收到时，每分钟检查保存的电脑地址。首次配对后支持电脑地址变化。</p><p>自动同步使用常驻通知。请在系统设置中允许后台运行；省电、休眠、强行停止或手机重启可能暂停检查，重新打开应用即可恢复。访客 Wi-Fi 的设备隔离可能阻止同步。</p><p>只有局域网 Wi-Fi / 以太网连接才同步，不使用云端。配对签名用于身份和完整性验证；账目在局域网通过 HTTP 传输，未做传输加密，请使用可信家庭网络。</p></details></section>`}
function syncDetail(){return `最近成功：${data.lastSync?new Date(data.lastSync).toLocaleString('zh-CN'):'尚未同步'}<br>${data.syncedRevision===data.revision?'所有更改已备份到电脑':'有本地更改等待同步'}`}
function bind(){document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>{periodType=b.dataset.period;render()});document.querySelectorAll('[data-bar]').forEach(b=>b.onclick=()=>{$('bar-detail').textContent=b.dataset.bar;document.querySelectorAll('.bar').forEach(x=>x.classList.remove('selected'));b.classList.add('selected')});if($('month'))$('month').onchange=e=>{month=e.target.value;render()};if(page==='sync'){$('sync-now').onclick=()=>{Native.sync();toast('正在检查电脑…')};$('pair').onclick=()=>{const error=Native.configure($('host').value.trim(),$('key').value.trim());if(error)toast(error);else {toast('已保存连接设置');render()}};if($('pause'))$('pause').onclick=()=>{Native.stop();render()};$('export').onclick=()=>Native.exportData()}}
function openEditor(id){editing=id||null;const e=data.entries.find(e=>e.id===id);$('edit-title').textContent=e?'编辑支出':'记一笔';$('amount').value=e?(e.amount/100).toFixed(2):'';const now=new Date();$('at').value=e?e.at.slice(0,16):day(now)+'T'+String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');setCategory(e?e.category:'daily');closeCategory();$('note').value=e?e.note:'';$('delete').hidden=!e;$('form-error').textContent='';editorInitial=editorValues();$('editor').showModal();$('editor').scrollTop=0}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{navigate(b.dataset.page)});$('add').onclick=()=>openEditor();$('cancel').onclick=closeEditor;$('entry-form').onsubmit=e=>{e.preventDefault();try{const entry={id:editing||'',amount:cents($('amount').value.trim()),at:$('at').value,category:$('category').value,note:$('note').value.trim()};if(!entry.at)throw Error('请选择支出时间');const error=Native.save(JSON.stringify(entry));if(error)throw Error(error);$('editor').close();render();toast('已保存在手机')}catch(err){$('form-error').textContent=err.message}};$('delete').onclick=()=>{if(confirm('确定删除这笔支出？删除也会同步到电脑。')){Native.remove(editing);$('editor').close();render();toast('记录已删除')}};
setInterval(()=>{if(page==='sync'&&!$('editor').open){load();$('sync-status').textContent=data.status;$('sync-time').innerHTML=syncDetail()}},2000);render();

function editorValues(){return JSON.stringify(['amount','at','category','note'].map(id=>$(id).value))}
function closeEditor(){
  if(!$('category-menu').hidden){closeCategory();return}
  if(editorValues()!==editorInitial&&!confirm('这笔支出还没有保存，放弃修改？'))return;
  $('editor').close();
}
function navigate(target){
  if(target===page)return;
  if(page==='sync'&&($('host').value.trim()!==data.host||$('key').value.trim())&&!confirm('连接设置还没有保存，放弃修改？'))return;
  page=target;render();window.scrollTo(0,0);
}
$('editor').addEventListener('cancel',event=>{event.preventDefault();closeEditor()});
window.handleAppBack=function(){
  if(!$('category-menu').hidden){closeCategory();return 'handled'}
  if($('editor').open){closeEditor();return 'handled'}
  if(page!=='ledger'){navigate('ledger');return 'handled'}
  return 'root';
};

const categoryPaths={giving:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',daily:'<path d="m3 11 9-8 9 8M5 10v10h14V10M9 20v-7h6v7"/>',extra:'<path d="m12 3 2.6 6.4L21 12l-6.4 2.6L12 21l-2.6-6.4L3 12l6.4-2.6Z"/>',claim:'<rect x="4" y="6" width="16" height="15" rx="3"/><path d="M9 6V3h6v3M8 12h8M8 16h5"/>'};
const categoryDescriptions={giving:'借给他人，或赠送的心意',daily:'餐饮、交通与日常所需',extra:'购物、旅行与偶尔的奖励',claim:'工作垫付，后续可报销'};
function categorySymbol(key){return '<svg viewBox="0 0 24 24" aria-hidden="true">'+categoryPaths[key]+'</svg>'}
function setCategory(key){
  const c=C[key];$('category').value=key;$('category-name').textContent=c.name;
  $('category-icon').innerHTML=categorySymbol(key);$('category-icon').style.background=c.bg;$('category-icon').style.color=c.color;
  document.querySelectorAll('.category-option').forEach(b=>b.setAttribute('aria-selected',String(b.dataset.category===key)));
}
function closeCategory(focus=false){$('category-menu').hidden=true;$('category-trigger').setAttribute('aria-expanded','false');if(focus)$('category-trigger').focus()}
function openCategory(){
  if(document.activeElement)document.activeElement.blur();
  if(typeof Native.hideKeyboard==='function')Native.hideKeyboard();
  $('category-menu').hidden=false;$('category-trigger').setAttribute('aria-expanded','true');
  setTimeout(()=>{if(!$('category-menu').hidden)$('category-menu').scrollIntoView({block:'nearest',behavior:'smooth'})},250);
}
$('category-menu').innerHTML=Object.entries(C).map(([key,c])=>`<button type="button" class="category-option" role="option" data-category="${key}" aria-selected="false"><span class="category-icon" style="background:${c.bg};color:${c.color}">${categorySymbol(key)}</span><span class="option-text"><strong>${c.name}</strong><small>${categoryDescriptions[key]}</small></span><svg class="category-check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg></button>`).join('');
$('category-trigger').onclick=()=>{$('category-menu').hidden?openCategory():closeCategory()};
document.querySelectorAll('.category-option').forEach(b=>b.onclick=()=>{setCategory(b.dataset.category);closeCategory(true)});
document.addEventListener('click',e=>{if(!$('category-field').contains(e.target))closeCategory()});
$('category-field').addEventListener('keydown',e=>{
  if(e.key==='Escape'&&!$('category-menu').hidden){e.preventDefault();e.stopPropagation();closeCategory(true)}
  if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){
    e.preventDefault();if($('category-menu').hidden)openCategory();
    const options=[...document.querySelectorAll('.category-option')],current=options.indexOf(document.activeElement);
    const index=e.key==='Home'?0:e.key==='End'?options.length-1:current<0?(e.key==='ArrowDown'?0:options.length-1):(current+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;
    options[index].focus();
  }
});
$('editor').addEventListener('close',()=>closeCategory());
setCategory('daily');
