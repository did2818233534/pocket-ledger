# Live integration test: unlocked paired phone, WebView CDP 9228, and installed service.
import os,json,time,uuid,subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
base=Path(__file__).resolve().parents[1]
data_dir=Path(os.environ.get('LEDGER_DATA_DIR','/opt/pocket-ledger/data'))
def service(action):subprocess.run(['systemctl','--user',action,'pocket-ledger.service'],check=True)
with sync_playwright() as p:
 b=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True);page=b.contexts[0].pages[0]
 def state():return json.loads(page.evaluate('Native.load()'))
 def wait_for(predicate,seconds=25):
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   s=state()
   if predicate(s):return s
   time.sleep(.2)
  raise AssertionError(s['status'])
 def synced():return wait_for(lambda s:s['revision']==s['syncedRevision'])
 marker='mDNS同步调试-'+uuid.uuid4().hex[:8];created=[];initial=state();original_host=initial['host']
 try:
  assert initial['lastDiscovery']>0
  before=initial['lastDiscovery']
  assert page.evaluate('Native.configure("192.168.10.254", "")')==''
  s=wait_for(lambda s:s['lastDiscovery']>before and s['host']!='192.168.10.254')
  synced()
  print('PASS: signed mDNS replaces stale IP and syncs to guga.local service',flush=True)
  previous_sync=s['lastSync']
  assert page.evaluate('Native.configure("guga.local", "")')==''
  wait_for(lambda s:s['lastSync']>previous_sync)
  # Every save still syncs even when periodic background checks are paused.
  page.evaluate('Native.stop()');time.sleep(.5)
  stamp=page.evaluate("new Date().getFullYear()+'-'+String(new Date().getMonth()+1).padStart(2,'0')+'-'+String(new Date().getDate()).padStart(2,'0')+'T12:00'")
  record={'amount':1,'category':'giving','at':stamp,'note':marker+'-online'}
  assert page.evaluate('(record)=>Native.save(JSON.stringify(record))',record)==''
  s=synced();created.extend(e['id'] for e in s['entries'] if e['note']==record['note'])
  assert not s['enabled']
  print('PASS: save triggers successful sync even with background polling paused',flush=True)
  page.evaluate('(host)=>Native.configure(host, "")',original_host);synced()
  service('stop')
  page.locator('[data-page=ledger]').click();page.locator('#add').click()
  page.locator('#amount').fill('0.01');page.locator('#note').fill(marker+'-offline')
  page.locator('button[type=submit]').click()
  assert not page.locator('#editor').evaluate('(e)=>e.open')
  assert '已保存在手机' in page.locator('#toast').inner_text()
  s=wait_for(lambda s:s['syncedRevision']<s['revision'] and s['status']=='账目已保存，等待下次同步')
  created.extend(e['id'] for e in s['entries'] if e['note']==marker+'-offline')
  print('PASS: offline save succeeds immediately with no failure popup',flush=True)
  service('start')
  s=wait_for(lambda s:s['revision']==s['syncedRevision'],75)
  index=json.loads((data_dir/'sync.json').read_text())
  backed_up=[entry for month in index['months'] for entry in json.loads((data_dir/(month+'.json')).read_text())['entries']]
  for eid in created:assert sum(e['device']==s['device'] and e['id']==eid for e in backed_up)==1
  print('PASS: mDNS/automatic retry uploads pending records after computer service returns',flush=True)
 finally:
  service('start')
  for entry in state()['entries']:
   if entry['note'].startswith(marker):page.evaluate('(id)=>Native.remove(id)',entry['id'])
  synced()
  if not initial['enabled']:page.evaluate('Native.stop()')
  page.locator('[data-page=ledger]').click()
  after={e['id']:e for e in state()['entries']}
  for e in initial['entries']:assert after.get(e['id'])==e
  b.close()
