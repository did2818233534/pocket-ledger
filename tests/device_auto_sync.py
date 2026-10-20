# Run after device_smoke.py on the disposable emulator, with UDP 47832 forwarded.
import sys,time,tempfile,threading,json,socket
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import server
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
 store=server.Store(tmp)
 http=server.ThreadingHTTPServer(('127.0.0.1',47831),server.handler(store))
 t=threading.Thread(target=http.serve_forever);t.start()
 try:
  b=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True);page=b.contexts[0].pages[0]
  page.evaluate('key=>Native.configure("10.0.2.3",key)',store.key)
  time.sleep(1)
  body=json.dumps({'app':'pocket-ledger','host':'10.0.2.2','time':int(time.time())},separators=(',',':'))
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp: udp.sendto(json.dumps({'body':body,'signature':server.sign(store.key,body)}).encode(),('127.0.0.1',47832))
  for _ in range(100):
   state=json.loads(page.evaluate('Native.load()'))
   if state['host']=='10.0.2.2' and len(store.export()['entries'])==3: break
   time.sleep(.15)
  else: raise AssertionError(('discovery failed',state['status'],state['host']))
  print('PASS: signed computer discovery updates address and triggers sync',flush=True)
  http.shutdown();http.server_close();t.join()
  page.evaluate("Native.save(JSON.stringify({amount:800,category:'daily',at:'2026-10-20T10:00',note:'定时同步测试'}))")
  time.sleep(2)
  http=server.ThreadingHTTPServer(('127.0.0.1',47831),server.handler(store));t=threading.Thread(target=http.serve_forever);t.start()
  started=time.monotonic()
  while time.monotonic()-started<75:
   if len(store.export()['entries'])==4: break
   time.sleep(1)
  else: raise AssertionError('periodic retry failed')
  print('PASS: automatic periodic retry after offline save, recovered in %.1fs'%(time.monotonic()-started),flush=True)
  b.close()
 finally:
  http.shutdown();http.server_close();t.join()
