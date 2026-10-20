"""Read-only device lifecycle test. Requires unlocked, paired phone and CDP port 9228.
Keep the screen awake for about two minutes. Uses Home and returns to the app;
verifies periodic sync, background shutdown and immediate resume without edits.
"""
import json,time,subprocess,os,xml.etree.ElementTree as E
from playwright.sync_api import sync_playwright
serial=os.environ.get('ANDROID_SERIAL','648718eb')
def adb(*args):return subprocess.check_output(['adb','-s',serial,*args],text=True)
def service():return 'ServiceRecord{' in adb('shell','dumpsys','activity','services','cn.guga.ledger/.SyncService')
with sync_playwright() as p:
 b=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True);page=b.contexts[0].pages[0]
 def state():return json.loads(page.evaluate('Native.load()'))
 first=state();assert service();print('PASS: foreground service running',flush=True)
 start=time.time();stamp=first['lastSync']
 while time.time()-start<70:
  time.sleep(2)
  if int(time.time()-start)%20<2:adb('shell','input','tap','50','180')
  if state()['lastSync']>stamp:break
 else:raise AssertionError('No periodic sync in foreground')
 print('PASS: foreground periodic sync',flush=True)
 adb('shell','input','keyevent','3');time.sleep(4)
 assert not service();stopped=state();assert stopped['tailnet']['state']=='Off';stamp=stopped['lastSync'];print('PASS: Home stops service; observing inactive interval',flush=True)
 time.sleep(32);time.sleep(32)
 assert not service();prefs=E.fromstring(adb('shell','run-as','cn.guga.ledger','cat','shared_prefs/sync.xml'));assert int(next(e.get('value') for e in prefs if e.get('name')=='lastSync'))==stamp
 print('PASS: no sync for >60 seconds in background',flush=True)
 adb('shell','am','start','-n','cn.guga.ledger/.MainActivity')
 start=time.time()
 while time.time()-start<20:
  time.sleep(1)
  if state()['lastSync']>stamp:break
 else:raise AssertionError('No immediate resume sync')
 after=state();assert service();assert first['entries']==after['entries'] and first['users']==after['users']
 print('PASS: reopening syncs immediately; records and profiles unchanged',flush=True)
 assert first['remoteEnabled']==after['remoteEnabled'];print('PASS: remote preference preserved',flush=True)
 b.close()
