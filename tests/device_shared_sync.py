"""Real Android + a simulated second replica. Deletes only UUIDs created by this test."""
import copy,datetime,hashlib,hmac,json,time,uuid,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path('/opt/pocket-ledger/data')
key=json.loads((root/'config.json').read_text())['key']
actor=str(uuid.uuid4());ids=[str(uuid.uuid4()) for _ in range(2)]
def disk():
    return [r for file in root.glob('????-??.json') for r in json.loads(file.read_text())['entries']]
def users():return json.loads((root/'sync.json').read_text())['users']
def exchange(records,profiles=None):
    body=json.dumps(dict(protocol=4,device=actor,revision=1,subscriptions=[u["id"] for u in (profiles or users())],users=profiles or users(),records=records),ensure_ascii=False).encode()
    ts=str(int(time.time()));signature=hmac.new(key.encode(),ts.encode()+b'\n'+body,hashlib.sha256).hexdigest()
    request=urllib.request.Request('http://127.0.0.1:47831/sync',body,{'X-Time':ts,'X-Signature':signature})
    with urllib.request.urlopen(request,timeout=10) as response:
        payload=response.read();assert response.headers['X-Signature']==hmac.new(key.encode(),ts.encode()+b'\n'+payload,hashlib.sha256).hexdigest()
        return json.loads(payload)
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True,timeout=10000)
    page=browser.contexts[0].pages[0]
    def state():return json.loads(page.evaluate('Native.load()'))
    def wait(predicate):
        end=time.monotonic()+35
        while time.monotonic()<end:
            result=state()
            if predicate(result):return result
            time.sleep(.25)
        raise AssertionError('Timed out: '+result['status'])
    initial=state();assert len(initial['users'])==2,'This live test requires exactly two existing user profiles; use isolated database tests for a fresh single-user ledger';u1,u2=[u['id'] for u in initial['users']];profile_before=copy.deepcopy(initial['users'])
    def flush():
        previous=state()['lastSync'];page.evaluate('Native.sync()')
        return wait(lambda s:s['lastSync']>previous and s['syncedRevision']==s['revision'])
    try:
        page.evaluate("navigate('ledger');render()")
        page.locator('#user-trigger').click()
        page.locator(f'[data-scope="{u1}"]').click()
        assert page.locator('#user-trigger').get_attribute('aria-expanded')=='true'
        page.locator('#users-done').click()
        page.locator('#add').click()
        assert page.locator('#owner').input_value()==u2
        page.locator('#cancel').click()
        now=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')
        a=dict(id=ids[0],amount=101,at=now,category='daily',note='共享账本临时验证 A')
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))',a)==''
        flush();entry=next(e for e in disk() if e['id']==ids[0]);assert entry['owner']==u2
        # Simulated phone uses the other user, and downloads the actual phone's entry.
        b=dict(id=ids[1],amount=202,at=now,category='giving',note='共享账本临时验证 B',owner=u1,version=max(e['version'] for e in disk())+1,actor=actor,deleted=False)
        reply=exchange([b]);assert any(e['id']==ids[0] for e in reply['records'])
        flush();assert any(e['id']==ids[1] and e['owner']==u1 for e in state()['entries'])
        print('PASS: two replicas add for different users; both download the combined ledger')
        page.evaluate("render();viewUsers=null;render()")
        baseline=[e for e in initial['entries'] if e['at'].startswith(now[:7])]
        expected=sum(e['amount'] for e in baseline)+303
        assert page.evaluate("stats(visibleEntries(),'month').total")==expected
        for uid in (u1,u2):
            page.evaluate('viewUsers=null;render()')
            page.locator('#user-trigger').click()
            for other in (u1,u2):
                if other!=uid:page.locator(f'[data-scope="{other}"]').click()
            page.locator('#users-done').click()
            assert page.evaluate('visibleEntries().every(e=>selectedUsers().includes(e.owner))')
            assert page.evaluate('selectedUsers().length')==1
        page.evaluate("navigate('stats')")
        page.locator('#user-trigger').click()
        page.locator('#users-all').click()
        page.locator('#users-done').click()
        for period in ('month','week','7','30'):
            page.locator(f'[data-period="{period}"]').click()
            assert page.locator('.ring').count()==1 and page.locator('.bars').count()==1
        page.screenshot(path='/tmp/pocket-ledger-shared-stats.png')
        print('PASS: recording user is separate from viewing scope; combined/individual charts work')
        # Other replica edits the actual phone's record, and the actual phone edits its record.
        edited={**entry,'amount':303,'version':b['version']+1,'actor':actor}
        exchange([edited,b]);flush();assert next(e for e in state()['entries'] if e['id']==ids[0])['amount']==303
        b_local={**b,'amount':404,'owner':u2}
        assert page.evaluate('(e)=>Native.save(JSON.stringify(e))',b_local)==''
        flush();remote=exchange([]);assert next(e for e in remote['records'] if e['id']==ids[1])['amount']==404
        # Rename and download, then restore original name in finally.
        profiles=users();profiles[1].update(name='验证用户',nameAt=int(time.time()*1000))
        exchange([],profiles);flush();assert state()['users'][1]['name']=='验证用户'
        print('PASS: cross-device editing, changing owner and profile-name synchronization')
        page.evaluate('(id)=>Native.remove(id)',ids[0]);flush()
        exchange([edited,b]);flush();assert not any(e['id']==ids[0] for e in state()['entries'])
        current=next(e for e in disk() if e['id']==ids[1]);exchange([{**current,'deleted':True,'version':current['version']+10,'actor':actor}]);flush()
        assert not any(e['id'] in ids for e in state()['entries'])
        print('PASS: deletion propagates both ways and stale replay does not resurrect entries')
    finally:
        for eid in ids:page.evaluate('(id)=>Native.remove(id)',eid)
        for original in profile_before:
            if next(u for u in state()['users'] if u['id']==original['id'])['name']!=original['name']:
                assert page.evaluate('(u)=>Native.renameUser(u.id,u.name)',original)==''
        page.evaluate('(id)=>Native.selectUser(id)',initial['currentUser']);flush()
        assert not any(e['id'] in ids for e in state()['entries'])
        assert sorted(state()['entries'],key=lambda e:e['id'])==sorted(initial['entries'],key=lambda e:e['id'])
        assert all(e['deleted'] for e in disk() if e['id'] in ids)
        page.evaluate("viewUsers=null;navigate('ledger');render()")
        page.screenshot(path='/tmp/pocket-ledger-shared-home.png')
        browser.close()
        print('PASS: original entries, names and current user restored; test records deleted')
