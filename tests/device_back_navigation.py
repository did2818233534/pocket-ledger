# Requires an unlocked phone on the ledger home page and CDP forwarded to port 9228.
import os,subprocess,time,json,xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright
SERIAL=os.environ['ANDROID_SERIAL']
def adb(*args):return subprocess.check_output(['adb','-s',SERIAL,*args])
def back():adb('shell','input','keyevent','KEYCODE_BACK');time.sleep(.7)
def choose(text):
 adb('shell','uiautomator','dump','/data/local/tmp/ledger-back-test.xml')
 root=ET.fromstring(adb('shell','cat','/data/local/tmp/ledger-back-test.xml'))
 matches=[n for n in root.iter('node') if n.get('text')==text]
 assert matches,'Missing dialog choice: '+text
 import re
 x1,y1,x2,y2=map(int,re.findall(r'\d+',matches[0].get('bounds')))
 adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2));time.sleep(.5)
with sync_playwright() as p:
 browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True)
 page=browser.contexts[0].pages[0]
 page.on('dialog',lambda dialog: None)
 assert not page.locator('#editor').evaluate('(e)=>e.open'), 'Close existing draft before running this test'
 initial=json.loads(page.evaluate('Native.load()'))['entries']
 for tab in ['stats','sync']:
  page.locator(f'[data-page={tab}]').click();back()
  assert page.locator('h1').inner_text()=='小账'
 print('PASS: statistics and sync return to ledger',flush=True)
 back();choose('留在小账');assert page.locator('h1').inner_text()=='小账'
 print('PASS: home requires explicit confirmation',flush=True)
 page.locator('#add').click();page.locator('#amount').fill('123.45')
 # A genuine Android keyboard must be dismissed before the editor.
 page.locator('#amount').click();time.sleep(.5);back()
 assert page.locator('#editor').evaluate('(e)=>e.open')
 back();choose('取消')
 assert page.locator('#editor').evaluate('(e)=>e.open')
 assert page.locator('#amount').input_value()=='123.45'
 back();choose('放弃修改')
 assert not page.locator('#editor').evaluate('(e)=>e.open')
 print('PASS: keyboard first, unsaved draft protected, discard closes only editor',flush=True)
 # A clean editor returns without asking to exit the app.
 page.locator('#add').click();back()
 if page.locator('#editor').evaluate('(e)=>e.open'):back()
 assert not page.locator('#editor').evaluate('(e)=>e.open')
 assert page.locator('h1').inner_text()=='小账'
 assert json.loads(page.evaluate('Native.load()'))['entries']==initial
 print('PASS: empty editor closes, existing ledger unchanged',flush=True)
 browser.close()
adb('shell','rm','-f','/data/local/tmp/ledger-back-test.xml')
