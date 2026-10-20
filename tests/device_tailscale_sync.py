"""Live paired-phone test. Log into Tailscale first; uses only its own temporary entry.

Requires CDP :9228 and the installed desktop service. Restarts the app with mDNS
paused and an unreachable LAN address to prove the Tailscale path without changing Wi-Fi.
"""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

root = Path(os.environ.get('LEDGER_DATA_DIR', '/opt/pocket-ledger/data'))
serial=os.environ.get('ANDROID_SERIAL','648718eb')
remote = os.environ.get('LEDGER_TAILNET_IP') or subprocess.check_output(['tailscale','ip','-4'],text=True).strip()
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9228', no_defaults=True)
    page = browser.contexts[0].pages[0]
    def state():
        return json.loads(page.evaluate('Native.load()'))
    def wait(predicate, seconds=60):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            value=state()
            if predicate(value): return value
            time.sleep(.3)
        raise AssertionError({k:value[k] for k in ('status','lastRoute','revision','syncedRevision')})
    def backed_up():
        return wait(lambda s:s['revision']==s['syncedRevision'] and s['lastRoute']=='Tailscale')
    def disk_entries():
        return [e for file in root.glob('????-??.json') for e in json.loads(file.read_text())['entries']]
    def restart_with_lan(host):
        # Stop the app before updating only its connection preferences, so mDNS
        # cannot race this simulated off-LAN setup. Pairing secrets stay in memory.
        global browser,page
        browser.close()
        subprocess.run(['adb','-s',serial,'shell','am','force-stop','cn.guga.ledger'],check=True,stdout=subprocess.DEVNULL)
        try:
            raw=subprocess.check_output(['adb','-s',serial,'exec-out','run-as','cn.guga.ledger','cat','shared_prefs/sync.xml'])
            preferences=ET.fromstring(raw)
            for item in preferences:
                if item.get('name')=='host':item.text=host
                if item.get('name')=='enabled':item.set('value','false')
            subprocess.run(['adb','-s',serial,'shell',
                "run-as cn.guga.ledger sh -c 'cat > shared_prefs/sync.xml.test-new && mv shared_prefs/sync.xml.test-new shared_prefs/sync.xml'"],
                input=ET.tostring(preferences,encoding='utf-8',xml_declaration=True),check=True)
        finally:
            subprocess.run(['adb','-s',serial,'shell','am','start','-n','cn.guga.ledger/.MainActivity'],check=True,stdout=subprocess.DEVNULL)
            time.sleep(1)
            pid=subprocess.check_output(['adb','-s',serial,'shell','pidof','cn.guga.ledger'],text=True).strip()
            subprocess.run(['adb','-s',serial,'forward','tcp:9228','localabstract:webview_devtools_remote_'+pid],check=True,stdout=subprocess.DEVNULL)
            browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True,timeout=10000)
            page=browser.contexts[0].pages[0]
    initial=wait(lambda s:s['tailnet']['state']=='Running' and any(peer['ip']==remote for peer in s['tailnet']['peers']),120)
    entry={'id':str(uuid.uuid4()),'amount':1,'at':datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'), 'category':'giving','note':'Tailscale 临时验证'}
    try:
        assert page.evaluate('(ip)=>Native.selectRemote(ip)',remote)==''
        time.sleep(.5)
        restart_with_lan('10.255.255.254')
        assert state()['host']=='10.255.255.254' and not state()['enabled']
        wait(lambda s:s['tailnet']['state']=='Running' and any(peer['ip']==remote for peer in s['tailnet']['peers']),120)
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))',entry)==''
        backed_up()
        assert any(e['id']==entry['id'] and e['amount']==1 for e in disk_entries())
        print('PASS: save falls back to authenticated Tailscale and writes monthly desktop JSON')
        entry['amount']=2
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))',entry)==''
        backed_up()
        assert any(e['id']==entry['id'] and e['amount']==2 for e in disk_entries())
        page.evaluate('Native.disableRemote(false)')
        wait(lambda s:s['tailnet']['state']=='Off')
        entry['amount']=3
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))',entry)==''
        wait(lambda s:s['status']=='账目已保存，等待下次同步')
        assert state()['revision']>state()['syncedRevision']
        print('PASS: disconnected save stays local; automatic sync failure is quiet')
        page.evaluate('Native.enableRemote()')
        wait(lambda s:s['tailnet']['state']=='Running' and bool(s['tailnet']['peers']),120)
        page.evaluate('Native.sync()')
        backed_up()
        assert any(e['id']==entry['id'] and e['amount']==3 for e in disk_entries())
        print('PASS: re-enable restores login; manual retry backs up pending edit')
        page.evaluate('(id)=>Native.remove(id)',entry['id'])
        backed_up()
        assert not any(e['id']==entry['id'] for e in disk_entries())
        print('PASS: deletion also synchronizes through Tailscale')
    finally:
        if any(e['id']==entry['id'] for e in state()['entries']):
            page.evaluate('(id)=>Native.remove(id)',entry['id'])
        page.evaluate('Native.enableRemote()')
        assert page.evaluate('(host)=>Native.configure(host, "")',initial['host'])==''
        time.sleep(.2)
        if not initial['enabled']: page.evaluate('Native.stop()')
        page.evaluate('Native.sync()')
        wait(lambda s:s['revision']==s['syncedRevision'])
        after={e['id']:e for e in state()['entries']}
        for e in initial['entries']:assert after.get(e['id'])==e
        assert entry['id'] not in after
        assert not any(e['id']==entry['id'] for e in disk_entries())
        page.evaluate('render()')
        browser.close()
        print('PASS: test record removed, original records and LAN configuration preserved')
