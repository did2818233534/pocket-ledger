"""Verify inline multi-user viewing and single-owner entry selection on Android."""
import json,subprocess,os,time
from playwright.sync_api import sync_playwright
serial=os.environ.get('ANDROID_SERIAL','648718eb')
with sync_playwright() as p:
    b=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True,timeout=10000)
    page=b.contexts[0].pages[0];initial=json.loads(page.evaluate('Native.load()'))
    try:
        page.evaluate("viewUsers=null;navigate('ledger');render()")
        page.locator('#user-trigger').click()
        a=page.locator('#user-trigger').bounding_box();menu=page.locator('#user-menu').bounding_box()
        assert abs(a['y']+a['height']-menu['y'])<2
        assert abs(a['width']-menu['width'])<2
        assert page.locator('[aria-multiselectable=true]').count()==1
        assert page.locator('#user-menu .user-option[aria-selected=true]').count()==len(initial['users'])
        page.screenshot(path='/tmp/pocket-ledger-users-dropdown.png')
        for user in initial['users'][1:]:page.locator(f'[data-scope="{user["id"]}"]').click()
        assert page.locator('#user-trigger').get_attribute('aria-expanded')=='true'
        assert page.evaluate('selectedUsers().length')==1
        page.locator(f'[data-scope="{initial["users"][0]["id"]}"]').click()
        assert page.evaluate('selectedUsers().length')==1
        page.locator('#new-user-name').fill('仅输入不保存')
        subprocess.run(['adb','-s',serial,'shell','input','keyevent','4'],check=True)
        time.sleep(.3)
        # Text input may open the keyboard; dismiss it before testing menu Back.
        if page.locator('#user-trigger').get_attribute('aria-expanded')=='true':
            subprocess.run(['adb','-s',serial,'shell','input','keyevent','4'],check=True);time.sleep(.3)
        assert page.locator('#user-trigger').get_attribute('aria-expanded')=='false'
        assert page.evaluate('page')=='ledger'
        page.locator('#add').click();page.locator('#owner-trigger').click()
        assert page.locator('#owner-menu').is_visible()
        assert page.locator('#owner-menu [aria-selected=true]').count()==1
        page.screenshot(path='/tmp/pocket-ledger-owner-dropdown.png')
        subprocess.run(['adb','-s',serial,'shell','input','keyevent','4'],check=True);time.sleep(.4)
        assert page.locator('#owner-menu').is_hidden() and page.locator('#editor').evaluate('(e)=>e.open')
        page.locator('#cancel').click()
        assert json.loads(page.evaluate('Native.load()'))['entries']==initial['entries']
        print('PASS: anchored multi-select, at least one user, single-owner dropdown, keyboard/menu Back, no records or users created')
    finally:
        page.evaluate('(id)=>Native.selectUser(id)',initial['currentUser'])
        page.evaluate("setOwnerMenu(false);setUserMenu(false);document.getElementById('editor').close();viewUsers=null;navigate('ledger');render()")
        b.close()
