"""Actual phone plus isolated simulated user: ID joining, scope, rename and current-only avatars.
Only the generated UUID user and entry are removed from the server in cleanup.
"""
import base64,copy,datetime,hashlib,hmac,importlib.util,io,json,subprocess,time,uuid,urllib.request
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
root=Path('/opt/pocket-ledger/data');key=json.loads((root/'config.json').read_text())['key']
actor,uid,eid=[str(uuid.uuid4()) for _ in range(3)]
def avatar(color):
    out=io.BytesIO();Image.new('RGB',(32,32),color).save(out,format='JPEG');return base64.b64encode(out.getvalue()).decode()
a1,a2=avatar('#298064'),avatar('#c7863b')
def exchange(profiles,records):
    body=json.dumps(dict(protocol=4,device=actor,revision=1,subscriptions=[uid],users=profiles,records=records),ensure_ascii=False).encode();ts=str(int(time.time()))
    sig=hmac.new(key.encode(),ts.encode()+b'\n'+body,hashlib.sha256).hexdigest()
    req=urllib.request.Request('http://127.0.0.1:47831/sync',body,{'X-Time':ts,'X-Signature':sig})
    with urllib.request.urlopen(req,timeout=10) as response:return json.loads(response.read())
def profile():return next(u for u in json.loads((root/'sync.json').read_text())['users'] if u['id']==uid)
record=dict(id=eid,amount=1,at=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'),category='daily',note='ID 同步独立测试',owner=uid,version=1,actor=actor,deleted=False)
user=dict(id=uid,name='ID 同步临时用户',nameAt=int(time.time()*1000),avatar=a1,avatarAt=int(time.time()*1000))
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True,timeout=10000);page=browser.contexts[0].pages[0]
    def state():return json.loads(page.evaluate('Native.load()'))
    def wait(predicate):
        end=time.monotonic()+45
        while time.monotonic()<end:
            current=state()
            if predicate(current):return current
            time.sleep(.25)
        raise AssertionError('Timeout: '+current['status'])
    def flush():
        before=state()['lastSync'];page.evaluate('Native.sync()');return wait(lambda s:s['lastSync']>before and s['revision']==s['syncedRevision'])
    initial=state()
    try:
        exchange([user],[record]);flush()
        assert not any(u['id']==uid for u in state()['users']) and not any(e['id']==eid for e in state()['entries'])
        print('PASS: unadded user, avatar and entry stay off the phone')
        page.evaluate("navigate('ledger');render();setUserMenu(true)")
        page.locator('#user-menu details summary').click();page.locator('#join-user-id').fill(uid);page.locator('#join-user').click()
        wait(lambda s:any(u['id']==uid and not u['pending'] for u in s['users']) and any(e['id']==eid for e in s['entries']))
        assert next(u for u in state()['users'] if u['id']==uid)['avatar']==a1
        page.evaluate("navigate('sync');refreshProfileView()")
        assert page.locator(f'[data-avatar="{uid}"]').count()==1
        assert page.locator('.profile-avatar-row img').count()>=1
        page.locator('#users-settings').screenshot(path='/tmp/pocket-ledger-user-id-avatar.png')
        assert page.evaluate('(id)=>Native.renameUser(id,"名字改变 ID 不变")',uid)=='';flush()
        assert profile()['id']==uid and profile()['name']=='名字改变 ID 不变'
        new_profile={**profile(),'avatar':a2,'avatarAt':profile()['avatarAt']+1000}
        exchange([new_profile],[]);flush()
        assert next(u for u in state()['users'] if u['id']==uid)['avatar']==a2
        assert a1 not in (root/'sync.json').read_text()
        # A stale name update cannot undo the avatar; removing it also propagates.
        exchange([user],[]);flush();assert next(u for u in state()['users'] if u['id']==uid)['avatar']==a2
        assert page.evaluate('(id)=>Native.clearAvatar(id)',uid)=='';flush();assert profile()['avatar']==''
        exchange([new_profile],[]);flush();assert next(u for u in state()['users'] if u['id']==uid)['avatar']==''
        print('PASS: join by ID downloads ledger and avatar; rename retains ID; current avatar replaces old; stale image cannot return')
        assert page.evaluate('(id)=>Native.leaveUser(id)',uid)=='';flush()
        assert not any(u['id']==uid for u in state()['users']) and not any(e['id']==eid for e in state()['entries'])
        assert exchange([],[])['records'][0]['id']==eid
        print('PASS: local removal stops downloads and removes cached data, while computer ledger is preserved')
    finally:
        if any(u['id']==uid for u in state()['users']):
            flush();assert page.evaluate('(id)=>Native.leaveUser(id)',uid)=='';flush()
        subprocess.run(['systemctl','--user','stop','pocket-ledger.service'],check=True)
        try:
            spec=importlib.util.spec_from_file_location('test_cleanup_server',Path(__file__).parents[1]/'desktop/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            store=module.Store(root);data=store.export()
            data['users']=[u for u in data['users'] if u['id']!=uid];data['entries']=[e for e in data['entries'] if e['id']!=eid];data['devices']=[d for d in data['devices'] if d['id']!=actor];store._write(data)
        finally:subprocess.run(['systemctl','--user','start','pocket-ledger.service'],check=True)
        page.evaluate('(id)=>Native.selectUser(id)',initial['currentUser']);flush()
        after=state();assert after['entries']==initial['entries'] and after['users']==initial['users']
        page.evaluate("viewUsers=null;navigate('ledger');render()")
        browser.close();print('PASS: temporary user, entry and images cleaned; original phone ledger and profiles unchanged')
