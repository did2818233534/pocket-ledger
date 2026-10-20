"""Run against a disposable emulator with WebView forwarded to localhost:9228.
Requires playwright. Temporarily stop production service before running.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('server',ROOT/'desktop/server.py')
server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
with tempfile.TemporaryDirectory() as tmp:
    store=server.Store(tmp)
    http=server.ThreadingHTTPServer(('127.0.0.1',47831),server.handler(store))
    thread=threading.Thread(target=http.serve_forever);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True)
            page=browser.contexts[0].pages[0]
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.evaluate("JSON.parse(Native.load()).entries.forEach(e=>Native.remove(e.id))")
            page.reload()
            assert page.locator('h1').inner_text()=='小账'
            def synced():
                for _ in range(100):
                    state=json.loads(page.evaluate('Native.load()'))
                    if state['syncedRevision']==state['revision']: return
                    time.sleep(.15)
                raise AssertionError(state['status'])
            for amount,category,note in [('28.50','daily','午餐 · 一碗热面'),('129','extra','周末的小确幸'),('86.20','claim','出差打车')]:
                page.locator('#add').click()
                page.locator('#amount').fill(amount)
                page.locator('#category-trigger').click()
                page.locator(f'[data-category={category}]').click()
                page.locator('#note').fill(note)
                page.locator('button[type=submit]').click()
            assert page.locator('.entry').count()==3
            assert '243.70' in page.locator('.total').inner_text()
            page.screenshot(path=str(ROOT/'dist/账本.png'))
            page.locator('[data-page=stats]').click()
            for period in ['month','week','7','30']:
                page.locator(f'[data-period="{period}"]').click()
                assert '243.70' in page.locator('.stat-total').inner_text()
                assert page.locator('.legend-item').count()==4
            page.locator('[data-period="7"]').click()
            page.locator('.bar').last.click()
            assert '243.70' in page.locator('#bar-detail').inner_text()
            page.screenshot(path=str(ROOT/'dist/统计.png'))
            page.locator('[data-page=sync]').click()
            page.locator('#host').fill('10.0.2.2')
            page.locator('#key').fill(store.key)
            page.locator('#pair').click()
            # Android permission dialog overlays the WebView, grant by adb outside UI.
            import subprocess
            subprocess.run(['adb','-s','emulator-5580','shell','pm','grant','cn.guga.ledger','android.permission.POST_NOTIFICATIONS'],check=True)
            synced()
            assert len(store.export()['entries'])==3
            page.screenshot(path=str(ROOT/'dist/同步.png'))
            # Reload proves UI is repopulated from native SQLite, not JS memory.
            page.reload()
            page.wait_for_selector('.entry')
            assert page.locator('.entry').count()==3
            page.locator('.entry').filter(has_text='午餐').click()
            page.locator('#amount').fill('30.00')
            page.locator('button[type=submit]').click()
            synced()
            assert sum(e['amount'] for e in store.export()['entries'])==24520
            # Invoke the same bridge used by the confirmed delete dialog.
            eid=page.evaluate("JSON.parse(Native.load()).entries.find(e=>e.category==='extra').id")
            page.evaluate('(id)=>Native.remove(id)',eid)
            synced()
            assert len(store.export()['entries'])==2
            # Offline mutation remains durable, retry catches up when server returns.
            http.shutdown();http.server_close();thread.join()
            page.evaluate("Native.save(JSON.stringify({amount:600,category:'daily',at:'2026-10-20T09:00',note:'离线记账'}))")
            page.wait_for_timeout(1000)
            assert len(json.loads(page.evaluate('Native.load()'))['entries'])==3
            assert json.loads(page.evaluate('Native.load()'))['syncedRevision']<json.loads(page.evaluate('Native.load()'))['revision']
            http=server.ThreadingHTTPServer(('127.0.0.1',47831),server.handler(store))
            thread=threading.Thread(target=http.serve_forever);thread.start()
            page.evaluate('Native.sync()')
            synced()
            assert len(store.export()['entries'])==3
            assert errors==[],errors
            print('PASS: real Android SQLite CRUD, charts, authenticated sync, offline save, reconnect, JS errors=0')
            browser.close()
    finally:
        http.shutdown();http.server_close();thread.join()
