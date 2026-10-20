"""Live test: paired phone with WebView CDP 9228 and installed monthly JSON server."""
import json
import os
import time
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright

data_dir = Path(os.environ.get('LEDGER_DATA_DIR', '/opt/pocket-ledger/data'))
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9228', no_defaults=True)
    page = browser.contexts[0].pages[0]
    def state():
        return json.loads(page.evaluate('Native.load()'))
    def synced():
        for _ in range(100):
            current = state()
            if current['syncedRevision'] == current['revision']:
                return
            time.sleep(.2)
        raise AssertionError(current['status'])
    def records(month):
        path = data_dir / (month + '.json')
        return json.loads(path.read_text())['entries'] if path.exists() else []
    initial = state()['entries']
    entry = {'id': str(uuid.uuid4()), 'amount': 1, 'at': '2026-10-20T12:00',
             'category': 'giving', 'note': '按月存储临时验证'}
    try:
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))', entry) == ''
        synced()
        assert any(e['id'] == entry['id'] for e in records('2026-10'))
        entry['at'] = '2026-09-30T12:00'
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))', entry) == ''
        synced()
        assert any(e['id'] == entry['id'] for e in records('2026-09'))
        assert not any(e['id'] == entry['id'] for e in records('2026-10'))
        print('PASS: phone save writes monthly JSON; date edit moves entry across month files')
    finally:
        page.evaluate('(id)=>Native.remove(id)', entry['id'])
        synced()
        assert not any(e['id'] == entry['id'] for e in records('2026-09') + records('2026-10'))
        after = {e['id']: e for e in state()['entries']}
        for e in initial:
            assert after.get(e['id']) == e
        assert not (data_dir / '.pending-sync.json').exists()
        page.evaluate('render()')
        browser.close()
        print('PASS: test entry removed from phone and desktop; existing records preserved')
