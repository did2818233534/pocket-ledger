'use strict';
const {categories:C,day,stats,breakdown,filterEntries,statisticalEntries,reportData,dateOnly,cents,calculateAmount}=LedgerModel;
let editorInitial='',page='ledger',periodType='month',data,editing=null,month=day(new Date()).slice(0,7);
let chartDimension='category';
let ledgerFilters={},detailFilters={},detailMonth='',filterOpen=false,detailTitle='支出明细';
let statsScroll=0;
const excludedStats={category:new Set(),primaryNote:new Set(),note:new Set()};
let viewUsers=null,userMenuOpen=false,ownerMenuOpen=false; // null means all users
const $=id=>document.getElementById(id),money=n=>(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function load(){data=JSON.parse(Native.load());if(data.error)throw Error(data.error)}
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2500)}
function render(){load();document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===(page==='details'?'stats':page)));$('add').hidden=page==='sync'||filterOpen;$('app').innerHTML=page==='ledger'?ledger():page==='stats'?report():page==='details'?detailPage():syncPage();bind()}
function ledger(){const source=visibleEntries(),m=stats(source,'month'),w=stats(source,'week');const entries=filterEntries(source,ledgerFilters,month);let html=`<section class="hero"><small>本月累计支出</small><div class="total"><b>¥</b>${money(m.total)}</div><div class="hero-bottom"><div><small>本周支出</small><strong>¥ ${money(w.total)}</strong></div><div><small>本月记账</small><strong>${m.count} <small>笔</small></strong></div></div></section><div class="categories">${Object.entries(C).map(([k,c])=>`<div class="mini"><span><i class="dot" style="background:${c.color}"></i>${c.name}</span><strong>¥ ${money(m.totals[k])}</strong></div>`).join('')}</div>${detailToolbar(entries,ledgerFilters,month)}`;
return html+entryRows(entries)}
function entryRows(entries){let html='';if(!entries.length)return '<div class="card empty"><b>没有符合条件的支出</b>试试调整日期、用户或筛选条件</div>';
for(const date of [...new Set(entries.map(e=>e.at.slice(0,10)))]){const rows=entries.filter(e=>e.at.startsWith(date));html+=`<div class="day-title"><span>${esc(date)}</span><span>支出 ¥ ${money(rows.reduce((s,e)=>s+e.amount,0))}</span></div><div>${rows.map(e=>`<div class="entry">${e.category==='claim'?`<button type="button" class="entry-icon claim-toggle ${e.reimbursed?'reimbursed':''}" data-reimbursed="${e.id}" aria-pressed="${!!e.reimbursed}" aria-label="${e.reimbursed?'恢复待报销':'标记已报销'}">${e.reimbursed?'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>':C[e.category].icon}</button>`:`<span class="entry-icon" style="background:${C[e.category].bg};color:${C[e.category].color}">${C[e.category].icon}</span>`}<button type="button" class="entry-main" data-edit="${e.id}"><span class="entry-info"><strong>${esc(e.primaryNote||e.note||C[e.category].name)}</strong>${e.primaryNote&&e.note?`<span class="entry-detail">${esc(e.note)}</span>`:''}<small>${C[e.category].name}${e.category==='claim'?e.reimbursed?' · 已报销':' · 待报销':''} · ${esc(userName(e.owner))}</small></span><span class="entry-amount">−${money(e.amount)}</span></button></div>`).join('')}</div>`}return html}
function currentFilters(){return page==='details'?detailFilters:ledgerFilters}
const pickerChevron='<svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
function filterPicker(key,label,filters){const names=key==='category'?Object.keys(C):[...new Set(visibleEntries().map(e=>(e[key]||'').trim()))].sort((a,b)=>a.localeCompare(b,'zh-CN'));const chosen=filters[key]==null?[]:Array.isArray(filters[key])?filters[key]:[filters[key]];for(const value of chosen)if(!names.includes(value))names.push(value);const options=[{value:'all',name:'不限'},...names.map(k=>({value:JSON.stringify(k),name:key==='category'?C[k].name:k||'未填写'}))];const title=chosen.length>1?`已选 ${chosen.length} 项`:chosen.length?key==='category'?C[chosen[0]].name:chosen[0]||'未填写':'不限';return `<div class="filter-choice"><div class="field-label" id="label-${key}">${label}<span class="optional">可多选</span></div><input type="hidden" id="filter-${key}" value="${esc(chosen.length?JSON.stringify(chosen):'all')}"><button type="button" class="user-trigger" id="trigger-${key}" data-filter-trigger="${key}" aria-haspopup="listbox" aria-expanded="false" aria-controls="menu-${key}" aria-labelledby="label-${key} chosen-${key}"><span class="user-trigger-text" id="chosen-${key}">${esc(title)}</span>${pickerChevron}</button><div class="user-menu filter-options" id="menu-${key}" role="listbox" aria-multiselectable="true" aria-labelledby="label-${key}" hidden>${options.map(o=>{const selected=o.value==='all'?!chosen.length:chosen.includes(JSON.parse(o.value));return `<button type="button" class="user-option" role="option" aria-selected="${selected}" data-filter-key="${key}" data-filter-value="${esc(o.value)}"><span class="user-option-name">${esc(o.name)}</span><span class="user-checkbox" aria-hidden="true">${selected?'✓':''}</span></button>`}).join('')}<button type="button" class="secondary filter-choice-done" data-filter-done="${key}">完成选择</button></div></div>`}
function closeFilterChoices(focus=false){const open=document.querySelector('[data-filter-trigger][aria-expanded="true"]');document.querySelectorAll('[data-filter-trigger]').forEach(b=>{b.setAttribute('aria-expanded','false');$('menu-'+b.dataset.filterTrigger).hidden=true});if(focus)open?.focus({preventScroll:true});return !!open}
let dateInputTarget=null;
function pickInputDate(input){dateInputTarget=input;document.activeElement?.blur();Native.hideKeyboard();let date;try{date=dateOnly(input.value)}catch(_){date=day(new Date())}Native.chooseDate(date)}
function closeMonthMenu(){if($('month-menu'))$('month-menu').hidden=true;$('month-trigger')?.setAttribute('aria-expanded','false')}
function detailToolbar(entries,filters,selectedMonth){const active=Object.values(filters).some(v=>v!=null&&v!==undefined);return `<div class="section-title detail-title"><h2>支出明细</h2><div class="toolbar"><button id="filter-toggle" type="button" class="filter-toggle ${active?'active':''}" aria-expanded="${filterOpen}" aria-controls="entry-filters" aria-label="${active?'筛选，已有条件':'筛选'}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="2.5"/><circle cx="15" cy="17" r="2.5"/></svg><span>筛选</span>${active?'<i class="filter-active-dot" aria-hidden="true"></i>':''}</button><div class="month-choice"><input id="month" type="hidden" value="${selectedMonth}"><button id="month-trigger" type="button" class="filter-toggle" aria-label="选择流水月份" aria-expanded="false" aria-controls="month-menu"><span id="month-label">${selectedMonth.replace('-','年')}月</span>${pickerChevron}</button><div id="month-menu" class="card month-menu" hidden><div class="month-year"><button type="button" data-year-step="-1" aria-label="上一年">‹</button><input id="month-year" type="number" min="1900" max="9999" value="${selectedMonth.slice(0,4)}" aria-label="年份"><button type="button" data-year-step="1" aria-label="下一年">›</button></div><div class="month-grid">${Array.from({length:12},(_,i)=>`<button type="button" data-month-value="${i+1}" class="${i+1===Number(selectedMonth.slice(5))?'selected':''}">${i+1}月</button>`).join('')}</div></div></div></div></div><form id="entry-filters" class="card entry-filters" ${filterOpen?'':'hidden'}><div class="filter-dates">${[['start','开始日期'],['end','截止日期']].map(([key,label])=>`<div><label for="filter-${key}">${label}</label><div class="filter-date-input"><input id="filter-${key}" type="text" maxlength="10" placeholder="不限日期" value="${filters[key]||''}"><button type="button" data-filter-date="${key}" aria-label="滚动选择${label}"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 11h16"/></svg></button></div></div>`).join('')}</div><p class="hint">包含起止当天；填写日期后按日期范围查询，可跨月。</p>${[['category','支出属性'],['primaryNote','一级备注'],['note','二级备注']].map(([key,label])=>filterPicker(key,label,filters)).join('')}<p id="filter-error" class="error" role="status"></p><div class="filter-actions"><button id="filter-reset" type="button" class="secondary">清除筛选</button><button type="submit" class="primary">应用筛选</button></div></form><div class="detail-summary"><span>${filters.start||filters.end?`${esc(filters.start||'最早')} — ${esc(filters.end||'至今')}`:esc(selectedMonth)} · ${entries.length} 笔</span><strong>合计 ¥ ${money(entries.reduce((sum,e)=>sum+e.amount,0))}</strong></div>`}
function detailPage(){const entries=filterEntries(statisticalEntries(visibleEntries()),detailFilters,detailMonth);return `<button id="back-stats" type="button" class="text-button back-stats">‹ 返回统计</button>`+`<header><h1>${esc(detailTitle)}</h1></header>`+detailToolbar(entries,detailFilters,detailMonth)+entryRows(entries)}
function backToStats(){filterOpen=false;navigate('stats');window.scrollTo(0,statsScroll)}
function bindEntryFilters(){
 document.querySelectorAll('[data-filter-trigger]').forEach(button=>button.onclick=()=>{const open=button.getAttribute('aria-expanded')==='true';closeFilterChoices();if(!open){closeMonthMenu();button.setAttribute('aria-expanded','true');$('menu-'+button.dataset.filterTrigger).hidden=false}});
 document.querySelectorAll('[data-filter-key]').forEach(button=>button.onclick=()=>{const key=button.dataset.filterKey,input=$('filter-'+key),chosen=input.value==='all'?[]:JSON.parse(input.value);if(button.dataset.filterValue==='all')chosen.length=0;else{const value=JSON.parse(button.dataset.filterValue),i=chosen.indexOf(value);if(i>=0)chosen.splice(i,1);else chosen.push(value)}input.value=chosen.length?JSON.stringify(chosen):'all';$('chosen-'+key).textContent=chosen.length>1?`已选 ${chosen.length} 项`:chosen.length?(key==='category'?C[chosen[0]].name:chosen[0]||'未填写'):'不限';$('menu-'+key).querySelectorAll('[role=option]').forEach(o=>{const selected=o.dataset.filterValue==='all'?!chosen.length:chosen.includes(JSON.parse(o.dataset.filterValue));o.setAttribute('aria-selected',String(selected));o.querySelector('.user-checkbox').textContent=selected?'✓':''})});
 document.querySelectorAll('[data-filter-done]').forEach(button=>button.onclick=()=>closeFilterChoices(true));
 document.querySelectorAll('[data-filter-date]').forEach(button=>button.onclick=()=>{closeFilterChoices();pickInputDate($('filter-'+button.dataset.filterDate))});
 if($('month-trigger'))$('month-trigger').onclick=()=>{const open=$('month-menu').hidden;closeFilterChoices();$('month-menu').hidden=!open;$('month-trigger').setAttribute('aria-expanded',String(open))};
 document.querySelectorAll('[data-year-step]').forEach(button=>button.onclick=()=>{$('month-year').value=Math.max(1900,Math.min(9999,Number($('month-year').value)+Number(button.dataset.yearStep)))});
 document.querySelectorAll('[data-month-value]').forEach(button=>button.onclick=()=>{const year=Number($('month-year').value);if(!Number.isInteger(year)||year<1900||year>9999){toast('年份需为 1900–9999');return}$('month').value=year+'-'+button.dataset.monthValue.padStart(2,'0');$('month').dispatchEvent(new Event('change'))});

 if($('back-stats'))$('back-stats').onclick=backToStats;
 if($('filter-toggle'))$('filter-toggle').onclick=()=>{closeFilterChoices();closeMonthMenu();filterOpen=!filterOpen;$('add').hidden=filterOpen;$('entry-filters').hidden=!filterOpen;$('filter-toggle').setAttribute('aria-expanded',String(filterOpen))};
 if($('entry-filters'))$('entry-filters').onsubmit=event=>{event.preventDefault();try{const next={};for(const key of ['start','end']){const value=$('filter-'+key).value;if(value)next[key]=dateOnly(value)}if(next.start&&next.end&&next.start>next.end)throw Error('开始日期不能晚于截止日期');for(const key of ['category','primaryNote','note']){const value=$('filter-'+key).value;if(value!=='all')next[key]=JSON.parse(value)}if(page==='details'){detailFilters=next;detailTitle='筛选结果'}else ledgerFilters=next;filterOpen=false;render()}catch(error){$('filter-error').textContent=error.message}};
 if($('filter-reset'))$('filter-reset').onclick=()=>{if(page==='details'){detailFilters={};detailTitle='支出明细'}else ledgerFilters={};filterOpen=false;render()};
 document.querySelectorAll('[data-stat-detail]').forEach(button=>button.onclick=()=>{const range=LedgerModel.period(periodType);detailFilters={...range,[chartDimension]:button.dataset.statDetail};detailMonth=range.start.slice(0,7);detailTitle=button.dataset.statName;statsScroll=window.scrollY;filterOpen=false;navigate('details')});
}
function report(){const {summary:s,groups:allGroups}=reportData(visibleEntries(),periodType,chartDimension,[...excludedStats[chartDimension]]);const groups=allGroups.map((g,i)=>({...g,color:chartDimension==='category'?C[g.key].color:`hsl(${(153+i*137.508)%360} 32% 52%)`}));let accumulated=0;const gradient=groups.filter(g=>!g.excluded).map(g=>{const start=accumulated;accumulated+=s.total?g.amount/s.total*100:0;return `${g.color} ${start}% ${accumulated}%`}).join(',');const max=Math.max(1,...s.days.map(d=>d.amount));return `<div class="tabs">${[['month','当月'],['week','本周'],['7','近 7 天'],['30','近 30 天']].map(([k,n])=>`<button data-period="${k}" class="${periodType===k?'active':''}">${n}</button>`).join('')}</div><section class="card"><span class="hint">${esc(scopeTitle())} · ${excludedStats[chartDimension].size?'已按可见项目统计':'全部项目'}</span><div class="stat-total">¥ ${money(s.total)}</div><span class="range">${s.start} — ${s.end}</span><div class="tabs chart-dimensions" aria-label="统计方式">${[['category','支出属性'],['primaryNote','一级备注'],['note','二级备注']].map(([key,label])=>`<button data-dimension="${key}" class="${chartDimension===key?'active':''}">${label}</button>`).join('')}</div><div class="stats-filter-hint"><span>点小眼睛可排除项目，所有统计同步更新</span>${excludedStats[chartDimension].size?'<button id="restore-stats" type="button" class="text-button">全部恢复</button>':''}</div><div class="chart-row"><div class="ring" style="background:${s.total?'conic-gradient('+gradient+')':'#edf0e9'}"><div class="ring-hole"><strong>${s.count}</strong><small>笔支出</small></div></div><div class="legend">${groups.map(g=>`<div class="legend-item ${g.excluded?'excluded':''}"><button type="button" class="stat-eye" style="--item-color:${g.color}" data-stat-key="${esc(g.key)}" aria-pressed="${!g.excluded}" aria-label="${g.excluded?'纳入':'排除'}${esc(g.name)}的统计"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>${g.excluded?'<path d="m3 3 18 18"/>':''}</svg></button><button type="button" class="legend-content legend-detail" data-stat-detail="${esc(g.key)}" data-stat-name="${esc(g.name)}" aria-label="查看${esc(g.name)}的支出明细"><div class="legend-heading"><span class="legend-name">${esc(g.name)}</span><strong>${g.excluded?'已排除':`${s.total?(g.amount/s.total*100).toFixed(1):'0.0'}%`}</strong></div><small>¥ ${money(g.amount)} · ${g.count} 笔${g.excluded?' · 不计入总额':''} · 查看明细 ›</small></button></div>`).join('')||'<p class="hint">暂无支出</p>'}</div></div></section><section class="card"><div class="section-title" style="margin:0"><h2>每天花了多少</h2><span>元 · 点击柱查看</span></div><div class="bars">${s.days.map(d=>`<div class="bar-col"><button class="bar" aria-label="${d.date} 支出 ${money(d.amount)} 元" data-bar="${d.date} · ¥ ${money(d.amount)}" style="height:${d.amount/max*100}%"></button></div>`).join('')}</div><div class="bar-labels"><span>${s.start.slice(5)}</span><span>最高 ¥ ${money(max===1&&s.total===0?0:max)}</span><span>${s.end.slice(5)}</span></div><div id="bar-detail" class="chart-hint">${s.count?'点击柱状图查看当天金额':groups.length?'当前没有纳入统计的支出':'这个时间段还没有支出记录'}</div></section><div class="metrics"><div class="card"><span class="hint">日均支出</span><strong>¥ ${money(Math.round(s.total/s.days.length))}</strong></div><div class="card"><span class="hint">自付支出</span><strong>¥ ${money(s.total-s.totals.claim)}</strong></div></div><p class="footnote">已报销账单不计入统计<br>本周从周一开始 · 近 7 / 30 天包含今天</p>`}
function syncPage(){return usersSettings()+`<section class="card"><h2 id="sync-status">${esc(data.status)}</h2><p class="hint" id="sync-time">${syncDetail()}</p><button id="sync-now" class="primary">立即同步</button><p class="hint">${data.enabled?'打开、更改时立即同步 · 使用期间每分钟同步':'定时同步未开启'} · 后台停止</p>${data.enabled?'<button id="pause" class="text-button">暂停定时同步</button>':''}<details class="sync-fold" ${!data.paired?'open':''}><summary>电脑连接设置</summary><label>电脑主机名或局域网地址<input id="host" inputmode="url" placeholder="guga.local 或 192.168.1.8" value="${esc(data.host)}"></label><label>配对密钥<input id="key" type="password" autocomplete="off" placeholder="${data.paired?'已保存，留空沿用原密钥':'电脑显示的 64 位密钥'}"></label><p class="hint">已选择远程电脑时，局域网地址可留空。</p><button id="pair" class="secondary">保存并开启自动同步</button><div id="remote-panel" class="connection-remote">${remotePanel()}</div></details></section><section class="card"><h2>数据与备份</h2><button id="export" class="secondary">导出手机账本 JSON</button><details class="sync-fold"><summary>同步与数据说明</summary><p>账单先保存在手机，联网后自动合并到电脑。同步失败不弹窗，下次连接再试；其他手机在各自同步时获取更改。</p><p>局域网自动发现电脑，也可选用 Tailscale 远程连接。电脑需要开机；切到后台或息屏后停止同步，登录和配对信息保留。</p><p>局域网使用带签名验证的 HTTP，请使用可信网络；Tailscale 提供加密远程传输。</p></details></section>`}
let computerMenuOpen=false;
function computerStatus(peer){
 if(!peer)return {kind:'unknown',label:'状态待确认'};
 if(peer.expired)return {kind:'expired',label:'登录已过期'};
 return peer.online?{kind:'online',label:'在线'}:{kind:'offline',label:'离线'};
}
function computerStateDot(peer){const status=computerStatus(peer);return `<span class="computer-state ${status.kind}"><i aria-hidden="true"></i>${status.label}</span>`}
function remoteComputerPicker(){
 const peers=data.tailnet?.peers||[],selected=peers.find(peer=>peer.ip===data.remoteHost);
 return `<div id="computer-field"><div id="computer-label" class="field-label">同步到哪台电脑</div><button type="button" id="computer-trigger" aria-haspopup="listbox" aria-expanded="${computerMenuOpen}" aria-controls="computer-menu"><svg class="computer-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/></svg><span class="computer-name">${esc(selected?.name||(data.remoteHost?'已保存的电脑':'请选择你的电脑'))}</span>${data.remoteHost?computerStateDot(selected):''}<svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div id="computer-menu" role="listbox" aria-labelledby="computer-label" ${computerMenuOpen?'':'hidden'}>${peers.length?peers.map(peer=>`<button type="button" class="computer-option" role="option" aria-selected="${peer.ip===data.remoteHost}" data-computer="${esc(peer.ip)}"><span class="computer-name">${esc(peer.name||'未命名设备')}</span>${computerStateDot(peer)}<svg class="computer-check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg></button>`).join(''):'<p class="computer-empty"><span class="computer-state unknown"><i aria-hidden="true"></i>正在查找电脑…</span><br>请确认电脑已加入同一网络</p>'}</div></div>`;
}
function setComputerMenu(open,focus=false){
 computerMenuOpen=open;
 if(!$('computer-menu'))return;
 $('computer-menu').hidden=!open;$('computer-trigger').setAttribute('aria-expanded',String(open));
 if(focus)$('computer-trigger').focus();

}
document.addEventListener('click',event=>{if(computerMenuOpen&&!$('computer-field')?.contains(event.target))setComputerMenu(false)});
document.addEventListener('keydown',event=>{
 if(!computerMenuOpen&&!$('computer-field')?.contains(event.target))return;
 if(event.key==='Escape'){event.preventDefault();setComputerMenu(false,true);return}
 if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
  event.preventDefault();setComputerMenu(true);
  const items=[...document.querySelectorAll('.computer-option')];if(!items.length)return;
  const current=items.indexOf(document.activeElement),index=event.key==='Home'?0:event.key==='End'?items.length-1:current<0?0:(current+(event.key==='ArrowUp'?-1:1)+items.length)%items.length;
  items[index].focus();
 }
});
function remotePanel(){
 const t=data.tailnet||{},state=!data.remoteEnabled?(t.state==='LogoutFailed'?'LogoutFailed':'Off'):(t.state||'Starting'),ready=state==='Running';
 const labels={Off:'未开启 · 仅使用局域网',Starting:'正在连接 Tailscale…',NeedsLogin:'请登录电脑所在的 Tailscale 网络',NeedsMachineAuth:'等待网络管理员批准此设备',Running:'已连接 Tailscale 网络',Stopped:'Tailscale 已暂停',Error:'连接暂不可用，稍后自动重试',LogoutFailed:'已关闭连接，退出账号未完成；可重新开启后重试'};
 return `<div class="remote-heading"><h2>远程同步</h2><span class="remote-badge">可选</span></div><p id="remote-state" class="hint">${esc(labels[state]||'正在连接…')}</p><p class="hint">局域网优先，连接不上时通过 Tailscale 同步。无需登录也能继续使用局域网。</p>${!data.remoteEnabled?'<button id="remote-enable" class="secondary">开启 Tailscale 远程同步</button>':`${ready?`${remoteComputerPicker()}<p class="hint">选择运行小账同步服务的电脑；使用已保存的配对密钥验证身份。</p>`:`<button id="remote-login" class="primary">${t.authURL?'前往 Tailscale 登录':'获取登录链接'}</button><p class="hint">在手机浏览器完成登录后返回小账；若需审批，请先在 Tailscale 管理页面批准。</p>`}<div class="remote-actions"><button id="remote-disable" class="text-button">关闭远程同步</button><button id="remote-logout" class="text-button">退出 Tailscale 账号</button></div>`}<details class="remote-about"><summary>关于内置 Tailscale</summary><p class="hint">使用 Tailscale 开源网络核心，仅传输小账同步请求。登录状态保存在手机应用私有目录，关闭远程同步会保留登录，退出账号需要联网。</p><p class="hint">通过 Tailscale 传输时端到端加密；无法直连时可能经过加密中继。电脑仍需开机并联网。</p><a href="tailscale-notices.html" id="remote-notices">开源许可</a></details>`;
}
let remoteFingerprint='';
function refreshRemote(){
 const fingerprint=JSON.stringify([data.remoteEnabled,data.remoteHost,data.tailnet]);
 if(fingerprint!==remoteFingerprint&&$('remote-panel')){
  remoteFingerprint=fingerprint;$('remote-panel').innerHTML=remotePanel();bindRemote();
 }
}
function bindRemote(){
 if($('remote-enable'))$('remote-enable').onclick=()=>{Native.enableRemote();load();refreshRemote()};
 if($('remote-login'))$('remote-login').onclick=()=>{if(data.tailnet?.authURL){const error=Native.openRemoteLogin();if(error)toast(error)}else{Native.loginRemote();toast('正在准备登录链接…')}};
 if($('remote-disable'))$('remote-disable').onclick=()=>{Native.disableRemote(false);load();refreshRemote()};
 if($('remote-logout'))$('remote-logout').onclick=()=>{if(confirm('退出 Tailscale 账号？局域网同步仍可继续使用。')){Native.disableRemote(true);load();refreshRemote()}};
 if($('computer-trigger'))$('computer-trigger').onclick=()=>setComputerMenu(!computerMenuOpen);
 document.querySelectorAll('[data-computer]').forEach(button=>button.onclick=()=>{
  const error=Native.selectRemote(button.dataset.computer);
  if(error){toast(error);return}
  computerMenuOpen=false;load();remoteFingerprint='';refreshRemote();toast('远程电脑已保存，正在尝试同步');
 });
 if($('remote-notices'))$('remote-notices').onclick=e=>{e.preventDefault();Native.showLicenses()};
}
function syncDetail(){return `最近成功：${data.lastSync?new Date(data.lastSync).toLocaleString('zh-CN'):'尚未同步'}<br>${data.syncedRevision===data.revision?'本地更改已同步':'有本地更改等待同步'}`}
function userName(id){return data.users.find(u=>u.id===id)?.name||'未命名用户'}
function selectedUsers(){const ids=data.users.map(u=>u.id);const selected=viewUsers===null?ids:viewUsers.filter(id=>ids.includes(id));return selected.length?selected:ids}
function visibleEntries(){const selected=selectedUsers();return data.entries.filter(e=>selected.includes(e.owner))}
function scopeTitle(){const selected=selectedUsers();return selected.length===1?userName(selected[0]):selected.length===data.users.length?'全部用户 · 合计':`已选 ${selected.length} 位用户 · 合计`}
function userAvatar(u,i){return `<span class="user-avatar user-${i%2}">${u.avatar?`<img src="data:image/jpeg;base64,${esc(u.avatar)}" alt="">`:esc(u.name.slice(0,1))}</span>`}
function scopePicker(){const selected=selectedUsers();return `<section id="user-field" class="user-field"><div class="user-caption"><strong>账本用户</strong><span>可勾选多位用户合计</span></div><button type="button" id="user-trigger" class="user-trigger" aria-haspopup="listbox" aria-expanded="${userMenuOpen}" aria-controls="user-menu"><span class="user-avatar-stack" aria-hidden="true">${data.users.map((u,i)=>({u,i})).filter(({u})=>selected.includes(u.id)).slice(0,3).map(({u,i})=>userAvatar(u,i)).join('')}</span><span class="user-trigger-text">${esc(scopeTitle())}</span><svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div id="user-menu" class="user-menu" ${userMenuOpen?'':'hidden'}><div class="user-menu-heading"><span>选择查看的用户</span><button type="button" id="users-all" class="text-button">全选</button></div><div class="user-menu-list" role="listbox" aria-label="账本用户" aria-multiselectable="true">${data.users.map((u,i)=>`<button type="button" role="option" aria-selected="${selected.includes(u.id)}" class="user-option" data-scope="${u.id}">${userAvatar(u,i)}<span class="user-option-name">${esc(u.name)}${u.pending?'<small class="pending-user">等待同步 · 请确认 ID 已在电脑保存</small>':''}</span><span class="user-checkbox" aria-hidden="true">${selected.includes(u.id)?'✓':''}</span></button>`).join('')}</div><button type="button" id="users-done" class="secondary">完成选择</button></div><p class="user-recording-hint">新增支出默认记给 <strong>${esc(userName(data.currentUser))}</strong> · 记账时可调整</p></section>`}
function setUserMenu(open,focus=false){userMenuOpen=open;if(!$('user-menu'))return;$('user-menu').hidden=!open;$('user-trigger').setAttribute('aria-expanded',String(open));if(focus)$('user-trigger').focus()}
function refreshUserPicker(){const current=$('user-field');if(current){current.outerHTML=scopePicker();bindUserPicker()}}
function addProfile(input){const error=Native.addUser(input.value);if(error){toast(error);return}load();viewUsers=[data.currentUser];userMenuOpen=false;render();toast('已添加用户：'+userName(data.currentUser))}
function joinProfile(input){const error=Native.joinUser(input.value.trim());if(error){toast(error);return}userMenuOpen=false;viewUsers=null;render();toast('已添加用户 ID，连接电脑后获取名字和账单')}
function bindUserPicker(){
 if(!$('user-trigger'))return;
 $('user-trigger').onclick=()=>setUserMenu(!userMenuOpen);
 $('users-done').onclick=()=>{setUserMenu(false);render()};
 $('users-all').onclick=()=>{viewUsers=null;render()};
 document.querySelectorAll('[data-scope]').forEach(b=>b.onclick=()=>{
  let selected=selectedUsers().slice();const id=b.dataset.scope;
  if(selected.includes(id)){if(selected.length===1){toast('至少选择一位用户');return}selected=selected.filter(x=>x!==id)}else selected.push(id);
  viewUsers=selected;if(selected.length===1)Native.selectUser(selected[0]);render();
 });
}
function usersSettings(){return `<section class="card" id="users-settings">${scopePicker()}<details id="profile-settings" class="sync-fold"><summary>管理用户与头像</summary><p class="hint">仅同步本机添加的用户；另一部手机添加同一 ID 即可共享账本。</p>${data.users.map((u,i)=>`<div class="profile-card"><div class="profile-avatar-row">${userAvatar(u,i)}<button class="text-button" data-avatar="${u.id}" ${u.pending?'disabled':''}>${u.avatar?'更换头像':'添加头像'}</button>${u.avatar?`<button class="text-button" data-clear-avatar="${u.id}">移除头像</button>`:''}</div><label>用户 ${i+1}<div class="rename-row"><input id="name-${i}" value="${esc(u.name)}" maxlength="24" aria-label="用户${i+1}的名字" ${u.pending?'disabled':''}><button class="secondary" data-rename="${u.id}" data-input="name-${i}" ${u.pending?'disabled':''}>保存名字</button></div></label><div class="profile-id"><span>用户 ID</span><code>${/^[1-9][0-9]*$/.test(u.id)?esc(u.id):'等待电脑分配编号'}</code>${/^[1-9][0-9]*$/.test(u.id)?`<button class="text-button" data-copy-user="${u.id}">复制 ID</button>`:''}</div>${u.pending?'<p class="hint">等待获取用户资料。请确认 ID 正确，并让原手机先同步到同一台电脑。</p>':''}<button class="text-button remove-local" data-leave-user="${u.id}">从这部手机移除</button></div>`).join('')}<div class="user-create"><input id="settings-new-user" maxlength="24" placeholder="新用户名字" aria-label="新用户名字"><button id="settings-add-user" class="text-button">＋ 新建用户</button></div><details class="join-user"><summary>通过 ID 添加已有用户</summary><input id="settings-join-id" placeholder="输入用户编号，例如 1" inputmode="numeric" autocomplete="off" spellcheck="false"><button id="settings-join-user" class="secondary">添加并同步</button></details><p class="hint">勾选控制账本和统计范围；移除仅删除本机副本，电脑账单保留。</p></details></section>`}
function refreshProfileView(){load();if($('users-settings')){const open=$('profile-settings').open;$('users-settings').outerHTML=usersSettings();$('profile-settings').open=open;bindProfileSettings();bindUserPicker()}else if(!$('editor').open)render()}
function bindProfileSettings(){
 document.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=()=>Native.chooseAvatar(b.dataset.avatar));
 document.querySelectorAll('[data-clear-avatar]').forEach(b=>b.onclick=()=>{const error=Native.clearAvatar(b.dataset.clearAvatar);if(error)toast(error);else refreshProfileView()});
 if($('settings-add-user'))$('settings-add-user').onclick=()=>addProfile($('settings-new-user'));
 if($('settings-join-user'))$('settings-join-user').onclick=()=>joinProfile($('settings-join-id'));
 document.querySelectorAll('[data-copy-user]').forEach(b=>b.onclick=()=>{Native.copyUserId(b.dataset.copyUser);toast('用户 ID 已复制')});
 document.querySelectorAll('[data-leave-user]').forEach(b=>b.onclick=()=>{if(!confirm('从这部手机移除该用户和本地账单副本？电脑和其他手机上的账单会保留，之后可通过同一 ID 再次添加。'))return;const error=Native.leaveUser(b.dataset.leaveUser);if(error)toast(error);else{viewUsers=null;render();toast('已从本机移除，电脑账单保留')}});
 document.querySelectorAll('[data-rename]').forEach(b=>b.onclick=()=>{const error=Native.renameUser(b.dataset.rename,$(b.dataset.input).value);if(error)toast(error);else{load();refreshUserPicker();toast('名字已保存，等待同步')}});
}

function bind(){
document.querySelectorAll('[data-reimbursed]').forEach(button=>button.onclick=()=>{const error=Native.toggleReimbursed(button.dataset.reimbursed);if(error){toast(error);return}const completed=button.getAttribute('aria-pressed')!=='true';render();toast(completed?'已报销，统计中已排除':'已恢复待报销，重新纳入统计')});
bindEntryFilters();
document.querySelectorAll('[data-stat-key]').forEach(b=>b.onclick=()=>{const excluded=excludedStats[chartDimension],key=b.dataset.statKey;excluded.has(key)?excluded.delete(key):excluded.add(key);const scroll=document.querySelector('.legend')?.scrollTop||0;render();const legend=document.querySelector('.legend');if(legend)legend.scrollTop=scroll;[...document.querySelectorAll('[data-stat-key]')].find(x=>x.dataset.statKey===key)?.focus({preventScroll:true})});
if($('restore-stats'))$('restore-stats').onclick=()=>{excludedStats[chartDimension].clear();render()};
document.querySelectorAll('[data-dimension]').forEach(b=>b.onclick=()=>{chartDimension=b.dataset.dimension;render()});
 bindUserPicker();
 bindProfileSettings();
document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>{periodType=b.dataset.period;render()});document.querySelectorAll('[data-bar]').forEach(b=>b.onclick=()=>{$('bar-detail').textContent=b.dataset.bar;document.querySelectorAll('.bar').forEach(x=>x.classList.remove('selected'));b.classList.add('selected')});if($('month'))$('month').onchange=e=>{if(!e.target.value)return;if(page==='details')detailMonth=e.target.value;else month=e.target.value;delete currentFilters().start;delete currentFilters().end;filterOpen=false;render()};if(page==='sync'){$('sync-now').onclick=()=>{Native.sync();toast('正在检查电脑…')};$('pair').onclick=()=>{const error=Native.configure($('host').value.trim(),$('key').value.trim());if(error)toast(error);else {toast('已保存连接设置');render()}};if($('pause'))$('pause').onclick=()=>{Native.stop();render()};$('export').onclick=()=>Native.exportData();bindRemote()}}
function resolveAmount(){
 if(!$('amount').value.trim())return false;
 try{const amount=calculateAmount($('amount').value);$('amount').value=(amount/100).toFixed(2);$('amount-error').textContent='';return true}
 catch(err){$('amount-error').textContent=err.message;return false}
}
$('amount').addEventListener('input',()=>{$('amount-error').textContent=''});
$('amount').addEventListener('blur',resolveAmount);
$('amount').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();if(resolveAmount())$('amount').blur()}});
// Preserve the caret and prevent blur from evaluating a half-entered expression.
document.querySelectorAll('[data-amount-key],#amount-equals').forEach(button=>{
 button.addEventListener('pointerdown',event=>event.preventDefault());
 button.onclick=()=>{if(button.id==='amount-equals'){resolveAmount();return}const input=$('amount');const start=input.selectionStart??input.value.length,end=input.selectionEnd??start;if(input.value.length-(end-start)>=120)return;input.setRangeText(button.dataset.amountKey,start,end,'end');input.focus();$('amount-error').textContent=''};
});
$('choose-date').onclick=()=>pickInputDate($('at'));
window.setExpenseDate=value=>{if(dateInputTarget?.isConnected)dateInputTarget.value=dateOnly(value);dateInputTarget=null};
$('at').addEventListener('blur',()=>{try{$('at').value=dateOnly($('at').value)}catch(_){}});
function openEditor(id){if(!id&&selectedUsers().length===1&&data.users.find(u=>u.id===selectedUsers()[0])?.pending){toast('等待这个用户的资料同步后再记账');return}if(!data.users.some(u=>!u.pending)){toast('请等待用户资料同步，或先新建用户');return}editing=id||null;const e=data.entries.find(e=>e.id===id);$('edit-title').textContent=e?'编辑支出':'记一笔';$('amount-error').textContent='';$('amount').value=e?(e.amount/100).toFixed(2):'';const now=new Date();$('at').value=e?e.at.slice(0,10):day(now);setOwnerMenu(false);setOwner(e?e.owner:(data.users.find(u=>u.id===data.currentUser&&!u.pending)||data.users.find(u=>!u.pending)).id);setCategory(e?e.category:'daily');closeCategory();$('primary-note').value=e?(e.primaryNote||''):'';$('note').value=e?e.note:'';$('delete').hidden=!e;$('form-error').textContent='';editorInitial=editorValues();$('editor').showModal();$('editor').scrollTop=0}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{navigate(b.dataset.page)});$('add').onclick=()=>openEditor();$('cancel').onclick=closeEditor;$('entry-form').onsubmit=e=>{e.preventDefault();try{const entry={id:editing||'',amount:calculateAmount($('amount').value.trim()),at:dateOnly($('at').value),category:$('category').value,owner:$('owner').value,primaryNote:$('primary-note').value.trim(),note:$('note').value.trim()};if(!entry.at)throw Error('请选择支出日期');const error=Native.save(JSON.stringify(entry));if(error)throw Error(error);Native.selectUser(entry.owner);$('editor').close();render();toast('已保存在手机')}catch(err){$('form-error').textContent=err.message}};$('delete').onclick=()=>{if(confirm('确定删除这笔支出？删除也会同步到电脑。')){Native.remove(editing);$('editor').close();render();toast('记录已删除')}};
function ledgerFingerprint(){return JSON.stringify([data.entries,data.users,data.currentUser])}
setInterval(()=>{if($('editor').open||userMenuOpen||filterOpen||$('month-menu')&&!$('month-menu').hidden)return;const before=ledgerFingerprint(),dirtyProfiles=$('users-settings')&&(data.users.some((u,i)=>$('name-'+i)?.value!==u.name)||$('settings-new-user')?.value||$('settings-join-id')?.value||$('users-settings').contains(document.activeElement));load();if(page==='sync'){$('sync-status').textContent=data.status;$('sync-time').innerHTML=syncDetail();refreshRemote();if(before!==ledgerFingerprint()&&!dirtyProfiles)refreshProfileView()}else if(before!==ledgerFingerprint()){const y=scrollY;render();window.scrollTo(0,y)}},2000);render();
function setOwner(id){
 $('owner').value=id;
 $('owner-name').textContent=userName(id);
 $('owner-menu').innerHTML=data.users.filter(u=>!u.pending).map((u,i)=>`<button type="button" class="user-option" role="option" data-owner="${u.id}" aria-selected="${u.id===id}">${userAvatar(u,i)}<span class="user-option-name">${esc(u.name)}</span><span class="owner-check">${u.id===id?'✓':''}</span></button>`).join('');
 document.querySelectorAll('[data-owner]').forEach(b=>b.onclick=()=>{setOwner(b.dataset.owner);setOwnerMenu(false,true)});
}
function setOwnerMenu(open,focus=false){ownerMenuOpen=open;$('owner-menu').hidden=!open;$('owner-trigger').setAttribute('aria-expanded',String(open));if(focus)$('owner-trigger').focus();if(open)closeCategory()}
$('owner-trigger').onclick=()=>setOwnerMenu(!ownerMenuOpen);
document.addEventListener('click',event=>{if(userMenuOpen&&!event.composedPath().some(node=>node.id==='user-field')){setUserMenu(false);render()}if(ownerMenuOpen&&!$('owner-field').contains(event.target))setOwnerMenu(false)});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&(userMenuOpen||ownerMenuOpen)){event.preventDefault();event.stopPropagation();if(ownerMenuOpen)setOwnerMenu(false,true);else setUserMenu(false,true)}
 const field=ownerMenuOpen?$('owner-field'):userMenuOpen?$('user-field'):null;
 if(field?.contains(event.target)&&['ArrowDown','ArrowUp','Home','End'].includes(event.key)){
  event.preventDefault();const items=[...field.querySelectorAll('.user-option')],current=items.indexOf(document.activeElement);
  const index=event.key==='Home'?0:event.key==='End'?items.length-1:current<0?0:(current+(event.key==='ArrowUp'?-1:1)+items.length)%items.length;
  items[index]?.focus();
 }
});



function editorValues(){return JSON.stringify(['amount','at','category','owner','primary-note','note'].map(id=>$(id).value))}
function closeEditor(){
  if(ownerMenuOpen){setOwnerMenu(false);return}
  if(!$('category-menu').hidden){closeCategory();return}
  if(editorValues()!==editorInitial&&!confirm('这笔支出还没有保存，放弃修改？'))return;
  $('editor').close();
}
function navigate(target){
  if(target===page)return;
  if(page==='sync'&&($('host').value.trim()!==data.host||$('key').value.trim())&&!confirm('连接设置还没有保存，放弃修改？'))return;
  filterOpen=false;userMenuOpen=false;computerMenuOpen=false;page=target;render();window.scrollTo(0,0);
}
$('editor').addEventListener('cancel',event=>{event.preventDefault();closeEditor()});
window.handleAppBack=function(){
  if(closeFilterChoices(true))return 'handled';
  if($('month-menu')&&!$('month-menu').hidden){closeMonthMenu();return 'handled'}
  if(ownerMenuOpen){setOwnerMenu(false,true);return 'handled'}
  if(userMenuOpen){setUserMenu(false,true);return 'handled'}
  if(computerMenuOpen){setComputerMenu(false,true);return 'handled'}
  if(!$('category-menu').hidden){closeCategory();return 'handled'}
  if($('editor').open){closeEditor();return 'handled'}
  if(filterOpen){filterOpen=false;render();return 'handled'}
  if(page==='details'){backToStats();return 'handled'}
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
  setOwnerMenu(false);
  if(document.activeElement)document.activeElement.blur();
  if(typeof Native.hideKeyboard==='function')Native.hideKeyboard();
  $('category-menu').hidden=false;$('category-trigger').setAttribute('aria-expanded','true');

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
$('editor').addEventListener('close',()=>{closeCategory();setOwnerMenu(false)});
setCategory('daily');

document.addEventListener('click',event=>{if(!event.target.closest('.filter-choice'))closeFilterChoices();if(!event.target.closest('.month-choice'))closeMonthMenu()});
document.addEventListener('keydown',event=>{const field=event.target.closest('.filter-choice');if(!field)return;const trigger=field.querySelector('[data-filter-trigger]');if(event.key==='Escape'){if(closeFilterChoices(true)){event.preventDefault();event.stopPropagation()}return}if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();if(trigger.getAttribute('aria-expanded')!=='true')trigger.click();const options=[...field.querySelectorAll('[role=option]')],i=options.indexOf(document.activeElement);const next=event.key==='Home'?0:event.key==='End'?options.length-1:i<0?0:(i+(event.key==='ArrowUp'?-1:1)+options.length)%options.length;options[next]?.focus()}});
