# Requires an unlocked paired phone, the local desktop service, and WebView CDP on 9228.
import os,json,time,uuid,subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
base=Path(__file__).resolve().parents[1]
data_dir=Path(os.environ.get('LEDGER_DATA_DIR','/opt/pocket-ledger/data'))
serial=os.environ['ANDROID_SERIAL']
with sync_playwright() as p:
 b=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True);page=b.contexts[0].pages[0]
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def state():return json.loads(page.evaluate('Native.load()'))
 def synced():
  for _ in range(100):
   s=state()
   if s['revision']==s['syncedRevision']:return s
   time.sleep(.2)
  raise AssertionError(s['status'])
 initial=state()['entries'];marker='分类调试-'+uuid.uuid4().hex[:8];eid=None
 try:
  page.locator('#add').click();page.locator('#category-trigger').click();page.wait_for_timeout(400)
  assert page.locator('.category-option').count()==4
  assert page.locator('#category-menu').is_visible()
  rect=page.locator('#category-trigger').bounding_box();menu=page.locator('#category-menu').bounding_box()
  assert abs(menu['y']-rect['y']-rect['height'])<2,(rect,menu)
  assert abs(menu['width']-rect['width'])<2
  assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  page.screenshot(path=str(base/'dist/属性下拉.png'))
  subprocess.run(['adb','-s',serial,'shell','input','keyevent','KEYCODE_BACK'],check=True)
  page.wait_for_timeout(600)
  assert page.locator('#category-menu').is_hidden()
  assert page.locator('#editor').evaluate('(e)=>e.open')
  page.locator('#category-trigger').click();page.locator('label[for=note]').click()
  assert page.locator('#category-menu').is_hidden()
  page.locator('#category-trigger').click();page.locator('[data-category=giving]').click()
  assert page.locator('#category-name').inner_text()=='借出赠与'
  assert page.locator('#category').input_value()=='giving'
  assert page.locator('#category-menu').is_hidden()
  page.locator('#amount').fill('0.01');page.locator('#note').fill(marker)
  page.locator('button[type=submit]').click()
  s=synced();eid=next(e['id'] for e in s['entries'] if e['note']==marker)
  index=json.loads((data_dir/'sync.json').read_text())
  backed_up=[entry for month in index['months'] for entry in json.loads((data_dir/(month+'.json')).read_text())['entries']]
  assert any(e['device']==s['device'] and e['id']==eid and e['category']=='giving' and e['amount']==1 for e in backed_up)
  page.locator(f'[data-edit="{eid}"]').click()
  assert page.locator('#category-name').inner_text()=='借出赠与'
  page.locator('#cancel').click()
  page.locator('[data-page=stats]').click()
  for span in ['month','week','7','30']:
   page.locator(f'[data-period="{span}"]').click()
   assert page.locator('.legend-item').count()==4
   assert '借出赠与' in page.locator('.legend').inner_text()
  print('PASS: anchored 4-option menu, outside/back dismissal, edit retention, giving save and LAN sync, four reports',flush=True)
  assert errors==[],errors
 finally:
  if not eid:eid=next((e['id'] for e in state()['entries'] if e['note']==marker),None)
  if eid:
   page.evaluate('(id)=>Native.remove(id)',eid);synced()
  page.locator('[data-page=ledger]').click()
  # Existing entries are untouched; a user could add another entry during the test.
  after={e['id']:e for e in state()['entries']}
  for e in initial:assert after.get(e['id'])==e
  page.screenshot(path=str(base/'dist/账本新版.png'))
  b.close()
