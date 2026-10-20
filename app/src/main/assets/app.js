'use strict';
const {categories:C,day,stats,cents,calculateAmount}=LedgerModel;
let editorInitial='',page='ledger',periodType='month',data,editing=null,month=day(new Date()).slice(0,7);
let viewUsers=null,userMenuOpen=false,ownerMenuOpen=false; // null means all users
const $=id=>document.getElementById(id),money=n=>(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}),esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function load(){data=JSON.parse(Native.load());if(data.error)throw Error(data.error)}
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',2500)}
function header(title,sub){return `<header><div><div class="eyebrow">${sub}</div><h1>${title}</h1></div><span class="badge">● 本地优先</span></header>`}
function render(){load();document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));$('add').hidden=page==='sync';$('app').innerHTML=page==='ledger'?ledger():page==='stats'?report():syncPage();bind()}
function ledger(){const source=visibleEntries(),m=stats(source,'month'),w=stats(source,'week');const entries=source.filter(e=>e.at.startsWith(month));let html=header('小账','A LITTLE EVERY DAY')+scopePicker()+`<section class="hero"><small>本月累计支出</small><div class="total"><b>¥</b>${money(m.total)}</div><div class="hero-bottom"><div><small>本周支出</small><strong>¥ ${money(w.total)}</strong></div><div><small>本月记账</small><strong>${m.count} <small>笔</small></strong></div></div></section><div class="categories">${Object.entries(C).map(([k,c])=>`<div class="mini"><span><i class="dot" style="background:${c.color}"></i>${c.name}</span><strong>¥ ${money(m.totals[k])}</strong></div>`).join('')}</div><div class="section-title"><h2>支出明细</h2><div class="toolbar"><input id="month" type="month" aria-label="流水月份" value="${month}"></div></div>`;
if(!entries.length)return html+'<div class="card empty"><b>从第一笔小账开始</b>点击右下角 ＋ 记录一笔支出<br>离线也能安心记账</div>';
for(const date of [...new Set(entries.map(e=>e.at.slice(0,10)))]){const rows=entries.filter(e=>e.at.startsWith(date));html+=`<div class="day-title"><span>${esc(date)}</span><span>支出 ¥ ${money(rows.reduce((s,e)=>s+e.amount,0))}</span></div><div>${rows.map(e=>`<button class="entry" data-edit="${e.id}"><span class="entry-icon" style="background:${C[e.category].bg};color:${C[e.category].color}">${C[e.category].icon}</span><span class="entry-info"><strong>${esc(e.note||C[e.category].name)}</strong><small>${e.at.slice(11,16)} · ${C[e.category].name} · ${esc(userName(e.owner))}</small></span><span class="entry-amount">−${money(e.amount)}</span></button>`).join('')}</div>`}return html+'<p class="footnote">每一笔，都留在你的手机里</p>'}
function report(){const s=stats(visibleEntries(),periodType);let accumulated=0;const gradient=Object.entries(C).map(([k,c])=>{const start=accumulated;accumulated+=s.total?s.totals[k]/s.total*100:0;return `${c.color} ${start}% ${accumulated}%`}).join(',');const max=Math.max(1,...s.days.map(d=>d.amount));return header('花销有数','SPENDING INSIGHTS')+scopePicker()+`<div class="tabs">${[['month','当月'],['week','本周'],['7','近 7 天'],['30','近 30 天']].map(([k,n])=>`<button data-period="${k}" class="${periodType===k?'active':''}">${n}</button>`).join('')}</div><section class="card"><span class="hint">${esc(scopeTitle())} · 含报销垫付</span><div class="stat-total">¥ ${money(s.total)}</div><span class="range">${s.start} — ${s.end}</span><div class="chart-row"><div class="ring" style="background:${s.total?'conic-gradient('+gradient+')':'#edf0e9'}"><div class="ring-hole"><strong>${s.count}</strong><small>笔支出</small></div></div><div class="legend">${Object.entries(C).map(([k,c])=>`<div class="legend-item"><i class="dot" style="background:${c.color}"></i>${c.name}<strong>${s.total?(s.totals[k]/s.total*100).toFixed(1):'0.0'}%</strong><small>¥ ${money(s.totals[k])}</small></div>`).join('')}</div></div></section><section class="card"><div class="section-title" style="margin:0"><h2>每天花了多少</h2><span>元 · 点击柱查看</span></div><div class="bars">${s.days.map(d=>`<div class="bar-col"><button class="bar" aria-label="${d.date} 支出 ${money(d.amount)} 元" data-bar="${d.date} · ¥ ${money(d.amount)}" style="height:${d.amount/max*100}%"></button></div>`).join('')}</div><div class="bar-labels"><span>${s.start.slice(5)}</span><span>最高 ¥ ${money(max===1&&s.total===0?0:max)}</span><span>${s.end.slice(5)}</span></div><div id="bar-detail" class="chart-hint">${s.count?'点击柱状图查看当天金额':'这个时间段还没有支出记录'}</div></section><div class="metrics"><div class="card"><span class="hint">日均支出</span><strong>¥ ${money(Math.round(s.total/s.days.length))}</strong></div><div class="card"><span class="hint">自付支出</span><strong>¥ ${money(s.total-s.totals.claim)}</strong></div></div><p class="footnote">本周从周一开始 · 近 7 / 30 天包含今天</p>`}
function syncPage(){return header('让账本相连','YOUR PRIVATE CONNECTION')+`<section class="card"><div class="sync-symbol">⇄</div><h2 id="sync-status">${esc(data.status)}</h2><p class="hint" id="sync-time">${syncDetail()}</p><button id="sync-now" class="primary">立即同步</button><p class="hint">${data.enabled?'后台检查已开启 · 每 1 分钟检查电脑':'后台检查未开启'}</p>${data.enabled?'<button id="pause" class="text-button">暂停后台检查</button>':''}</section><section class="card" id="remote-panel">${remotePanel()}</section><section class="card"><h2>连接我的电脑</h2><p class="hint">在电脑运行配对命令后填写密钥。局域网地址用于直接连接；已选择远程电脑时可留空。</p><label>电脑主机名或局域网地址<input id="host" inputmode="url" placeholder="guga.local 或 192.168.1.8" value="${esc(data.host)}"></label><label>配对密钥<input id="key" type="password" autocomplete="off" placeholder="${data.paired?'已保存，留空沿用原密钥':'电脑显示的 64 位密钥'}"></label><button id="pair" class="secondary">保存并开启后台检查</button></section>${usersSettings()}<section class="card"><h2>数据与备份</h2><p class="hint">每次保存先写入手机，再后台尝试同步；失败不弹窗，下次重试。电脑汇总账本，手机只保留本机已添加用户的账本，修改、删除和用户名字也会同步。电脑离线时各自保存，上线后合并。</p><button id="export" class="secondary">导出手机账本 JSON</button><details style="margin-top:18px"><summary>同步和后台运行说明</summary><p>电脑通过 mDNS 公布局域网服务，手机发现并验证配对后自动同步，支持电脑 IP 变化。手机每分钟重新检查，也可以手动同步。</p><p>自动同步使用常驻通知。请在系统设置中允许后台运行；省电、休眠、强行停止或手机重启可能暂停检查，重新打开应用即可恢复。访客 Wi-Fi 的设备隔离可能阻止同步。</p><p>未开启远程同步时，只在局域网 Wi-Fi / 以太网连接同步。开启并登录 Tailscale 后，局域网不可达时自动尝试加密远程连接，账本仍保存在手机和电脑。配对签名用于身份和完整性验证；账目在局域网通过 HTTP 传输，未做传输加密，请使用可信家庭网络。</p></details></section>`}
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
 if(open)$('computer-menu').scrollIntoView({block:'nearest',behavior:'smooth'});
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
function syncDetail(){return `最近成功：${data.lastSync?new Date(data.lastSync).toLocaleString('zh-CN'):'尚未同步'}<br>${data.syncedRevision===data.revision?'本地更改已同步 · 其他手机的更改在下次连接时获取':'有本地更改等待同步'}`}
function userName(id){return data.users.find(u=>u.id===id)?.name||'未命名用户'}
function selectedUsers(){const ids=data.users.map(u=>u.id);const selected=viewUsers===null?ids:viewUsers.filter(id=>ids.includes(id));return selected.length?selected:ids}
function visibleEntries(){const selected=selectedUsers();return data.entries.filter(e=>selected.includes(e.owner))}
function scopeTitle(){const selected=selectedUsers();return selected.length===1?userName(selected[0]):selected.length===data.users.length?'全部用户 · 合计':`已选 ${selected.length} 位用户 · 合计`}
function userAvatar(u,i){return `<span class="user-avatar user-${i%2}">${u.avatar?`<img src="data:image/jpeg;base64,${esc(u.avatar)}" alt="">`:esc(u.name.slice(0,1))}</span>`}
function scopePicker(){const selected=selectedUsers();return `<section id="user-field" class="user-field"><div class="user-caption"><strong>账本用户</strong><span>可勾选多位用户合计</span></div><button type="button" id="user-trigger" class="user-trigger" aria-haspopup="listbox" aria-expanded="${userMenuOpen}" aria-controls="user-menu"><span class="user-avatar-stack" aria-hidden="true">${data.users.map((u,i)=>({u,i})).filter(({u})=>selected.includes(u.id)).slice(0,3).map(({u,i})=>userAvatar(u,i)).join('')}</span><span class="user-trigger-text">${esc(scopeTitle())}</span><svg class="chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div id="user-menu" class="user-menu" ${userMenuOpen?'':'hidden'}><div class="user-menu-heading"><span>选择查看的用户</span><button type="button" id="users-all" class="text-button">全选</button></div><div class="user-menu-list" role="listbox" aria-label="账本用户" aria-multiselectable="true">${data.users.map((u,i)=>`<button type="button" role="option" aria-selected="${selected.includes(u.id)}" class="user-option" data-scope="${u.id}">${userAvatar(u,i)}<span class="user-option-name">${esc(u.name)}${u.pending?'<small class="pending-user">等待同步 · 请确认 ID 已在电脑保存</small>':''}</span><span class="user-checkbox" aria-hidden="true">${selected.includes(u.id)?'✓':''}</span></button>`).join('')}</div><div class="user-create"><input id="new-user-name" maxlength="24" placeholder="新用户名字" aria-label="新用户名字"><button type="button" id="create-user" class="text-button">＋ 新建用户</button></div><details class="join-user"><summary>通过 ID 添加已有用户</summary><p class="hint">在另一部手机的“同步 → 记账用户”复制用户 ID，粘贴到这里。</p><input id="join-user-id" placeholder="粘贴完整用户 ID" autocomplete="off" spellcheck="false"><button type="button" id="join-user" class="secondary">添加并同步</button></details><button type="button" id="users-done" class="secondary">完成选择</button></div><p class="user-recording-hint">新增支出默认记给 <strong>${esc(userName(data.currentUser))}</strong> · 记账时可调整</p></section>`}
function setUserMenu(open,focus=false){userMenuOpen=open;if(!$('user-menu'))return;$('user-menu').hidden=!open;$('user-trigger').setAttribute('aria-expanded',String(open));if(focus)$('user-trigger').focus();if(open)$('user-menu').scrollIntoView({block:'nearest',behavior:'smooth'})}
function refreshUserPicker(){const current=$('user-field');if(current){current.outerHTML=scopePicker();bindUserPicker()}}
function addProfile(input){const error=Native.addUser(input.value);if(error){toast(error);return}load();viewUsers=[data.currentUser];userMenuOpen=false;render();toast('已添加用户：'+userName(data.currentUser))}
function joinProfile(input){const error=Native.joinUser(input.value.trim());if(error){toast(error);return}userMenuOpen=false;viewUsers=null;render();toast('已添加用户 ID，连接电脑后获取名字和账单')}
function bindUserPicker(){
 if(!$('user-trigger'))return;
 $('user-trigger').onclick=()=>setUserMenu(!userMenuOpen);
 $('users-done').onclick=()=>{setUserMenu(false);render()};
 $('users-all').onclick=()=>{viewUsers=null;render()};
 $('join-user').onclick=()=>joinProfile($('join-user-id'));
 $('create-user').onclick=()=>addProfile($('new-user-name'));
 document.querySelectorAll('[data-scope]').forEach(b=>b.onclick=()=>{
  let selected=selectedUsers().slice();const id=b.dataset.scope;
  if(selected.includes(id)){if(selected.length===1){toast('至少选择一位用户');return}selected=selected.filter(x=>x!==id)}else selected.push(id);
  viewUsers=selected;if(selected.length===1)Native.selectUser(selected[0]);render();
 });
}
function usersSettings(){return `<section class="card" id="users-settings"><h2>本机同步的用户</h2><p class="hint">只同步在这部手机添加的用户。名字可以修改，ID 始终不变；另一部手机添加同一 ID 即可同步账单和名字。</p>${data.users.map((u,i)=>`<div class="profile-card"><div class="profile-avatar-row">${userAvatar(u,i)}<button class="text-button" data-avatar="${u.id}" ${u.pending?'disabled':''}>${u.avatar?'更换头像':'添加头像'}</button>${u.avatar?`<button class="text-button" data-clear-avatar="${u.id}">移除头像</button>`:''}</div><label>用户 ${i+1}<div class="rename-row"><input id="name-${i}" value="${esc(u.name)}" maxlength="24" aria-label="用户${i+1}的名字" ${u.pending?'disabled':''}><button class="secondary" data-rename="${u.id}" data-input="name-${i}" ${u.pending?'disabled':''}>保存名字</button></div></label><div class="profile-id"><span>用户 ID</span><code>${esc(u.id)}</code><button class="text-button" data-copy-user="${u.id}">复制 ID</button></div>${u.pending?'<p class="hint">等待获取用户资料。请确认 ID 正确，并让原手机先同步到同一台电脑。</p>':''}<button class="text-button remove-local" data-leave-user="${u.id}">从这部手机移除</button></div>`).join('')}<div class="user-create"><input id="settings-new-user" maxlength="24" placeholder="新用户名字" aria-label="新用户名字"><button id="settings-add-user" class="text-button">＋ 新建用户</button></div><details class="join-user"><summary>通过 ID 添加已有用户</summary><input id="settings-join-id" placeholder="粘贴完整用户 ID" autocomplete="off" spellcheck="false"><button id="settings-join-user" class="secondary">添加并同步</button></details><p class="hint">同名不代表同一个用户，要使用同一 ID。勾选仅控制查看范围；停止同步请从本机移除用户，不会删除电脑和其他手机上的账单。多位用户仍可合并统计。</p></section>`}
function refreshProfileView(){load();if($('users-settings')){$('users-settings').outerHTML=usersSettings();bindProfileSettings()}else if(!$('editor').open)render()}
function bindProfileSettings(){
 document.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=()=>Native.chooseAvatar(b.dataset.avatar));
 document.querySelectorAll('[data-clear-avatar]').forEach(b=>b.onclick=()=>{const error=Native.clearAvatar(b.dataset.clearAvatar);if(error)toast(error);else refreshProfileView()});
 if($('settings-add-user'))$('settings-add-user').onclick=()=>addProfile($('settings-new-user'));
 if($('settings-join-user'))$('settings-join-user').onclick=()=>joinProfile($('settings-join-id'));
 document.querySelectorAll('[data-copy-user]').forEach(b=>b.onclick=()=>{Native.copyUserId(b.dataset.copyUser);toast('用户 ID 已复制')});
 document.querySelectorAll('[data-leave-user]').forEach(b=>b.onclick=()=>{if(!confirm('从这部手机移除该用户和本地账单副本？电脑和其他手机上的账单会保留，之后可通过同一 ID 再次添加。'))return;const error=Native.leaveUser(b.dataset.leaveUser);if(error)toast(error);else{viewUsers=null;render();toast('已从本机移除，电脑账单保留')}});
 document.querySelectorAll('[data-rename]').forEach(b=>b.onclick=()=>{const error=Native.renameUser(b.dataset.rename,$(b.dataset.input).value);if(error)toast(error);else{load();toast('名字已保存，等待同步')}});
}

function bind(){
 bindUserPicker();
 bindProfileSettings();
document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>openEditor(b.dataset.edit));document.querySelectorAll('[data-period]').forEach(b=>b.onclick=()=>{periodType=b.dataset.period;render()});document.querySelectorAll('[data-bar]').forEach(b=>b.onclick=()=>{$('bar-detail').textContent=b.dataset.bar;document.querySelectorAll('.bar').forEach(x=>x.classList.remove('selected'));b.classList.add('selected')});if($('month'))$('month').onchange=e=>{month=e.target.value;render()};if(page==='sync'){$('sync-now').onclick=()=>{Native.sync();toast('正在检查电脑…')};$('pair').onclick=()=>{const error=Native.configure($('host').value.trim(),$('key').value.trim());if(error)toast(error);else {toast('已保存连接设置');render()}};if($('pause'))$('pause').onclick=()=>{Native.stop();render()};$('export').onclick=()=>Native.exportData();bindRemote()}}
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
function openEditor(id){if(!id&&selectedUsers().length===1&&data.users.find(u=>u.id===selectedUsers()[0])?.pending){toast('等待这个用户的资料同步后再记账');return}if(!data.users.some(u=>!u.pending)){toast('请等待用户资料同步，或先新建用户');return}editing=id||null;const e=data.entries.find(e=>e.id===id);$('edit-title').textContent=e?'编辑支出':'记一笔';$('amount-error').textContent='';$('amount').value=e?(e.amount/100).toFixed(2):'';const now=new Date();$('at').value=e?e.at.slice(0,16):day(now)+'T'+String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');setOwnerMenu(false);setOwner(e?e.owner:(data.users.find(u=>u.id===data.currentUser&&!u.pending)||data.users.find(u=>!u.pending)).id);setCategory(e?e.category:'daily');closeCategory();$('note').value=e?e.note:'';$('delete').hidden=!e;$('form-error').textContent='';editorInitial=editorValues();$('editor').showModal();$('editor').scrollTop=0}
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{navigate(b.dataset.page)});$('add').onclick=()=>openEditor();$('cancel').onclick=closeEditor;$('entry-form').onsubmit=e=>{e.preventDefault();try{const entry={id:editing||'',amount:calculateAmount($('amount').value.trim()),at:$('at').value,category:$('category').value,owner:$('owner').value,note:$('note').value.trim()};if(!entry.at)throw Error('请选择支出时间');const error=Native.save(JSON.stringify(entry));if(error)throw Error(error);Native.selectUser(entry.owner);$('editor').close();render();toast('已保存在手机')}catch(err){$('form-error').textContent=err.message}};$('delete').onclick=()=>{if(confirm('确定删除这笔支出？删除也会同步到电脑。')){Native.remove(editing);$('editor').close();render();toast('记录已删除')}};
function ledgerFingerprint(){return JSON.stringify([data.entries,data.users,data.currentUser])}
setInterval(()=>{if($('editor').open||userMenuOpen)return;const before=ledgerFingerprint(),dirtyProfiles=$('users-settings')&&(data.users.some((u,i)=>$('name-'+i)?.value!==u.name)||$('settings-new-user')?.value||$('settings-join-id')?.value||$('users-settings').contains(document.activeElement));load();if(page==='sync'){$('sync-status').textContent=data.status;$('sync-time').innerHTML=syncDetail();refreshRemote();if(before!==ledgerFingerprint()&&!dirtyProfiles)refreshProfileView()}else if(before!==ledgerFingerprint()){const y=scrollY;render();window.scrollTo(0,y)}},2000);render();
function setOwner(id){
 $('owner').value=id;
 $('owner-name').textContent=userName(id);
 $('owner-menu').innerHTML=data.users.filter(u=>!u.pending).map((u,i)=>`<button type="button" class="user-option" role="option" data-owner="${u.id}" aria-selected="${u.id===id}">${userAvatar(u,i)}<span class="user-option-name">${esc(u.name)}</span><span class="owner-check">${u.id===id?'✓':''}</span></button>`).join('');
 document.querySelectorAll('[data-owner]').forEach(b=>b.onclick=()=>{setOwner(b.dataset.owner);setOwnerMenu(false,true)});
}
function setOwnerMenu(open,focus=false){ownerMenuOpen=open;$('owner-menu').hidden=!open;$('owner-trigger').setAttribute('aria-expanded',String(open));if(focus)$('owner-trigger').focus();if(open){closeCategory();$('owner-menu').scrollIntoView({block:'nearest',behavior:'smooth'})}}
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



function editorValues(){return JSON.stringify(['amount','at','category','owner','note'].map(id=>$(id).value))}
function closeEditor(){
  if(ownerMenuOpen){setOwnerMenu(false);return}
  if(!$('category-menu').hidden){closeCategory();return}
  if(editorValues()!==editorInitial&&!confirm('这笔支出还没有保存，放弃修改？'))return;
  $('editor').close();
}
function navigate(target){
  if(target===page)return;
  if(page==='sync'&&($('host').value.trim()!==data.host||$('key').value.trim())&&!confirm('连接设置还没有保存，放弃修改？'))return;
  userMenuOpen=false;computerMenuOpen=false;page=target;render();window.scrollTo(0,0);
}
$('editor').addEventListener('cancel',event=>{event.preventDefault();closeEditor()});
window.handleAppBack=function(){
  if(ownerMenuOpen){setOwnerMenu(false,true);return 'handled'}
  if(userMenuOpen){setUserMenu(false,true);return 'handled'}
  if(computerMenuOpen){setComputerMenu(false,true);return 'handled'}
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
  setOwnerMenu(false);
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
$('editor').addEventListener('close',()=>{closeCategory();setOwnerMenu(false)});
setCategory('daily');
