"""Verify the real Android inline computer menu after Tailscale login."""
import json
import os
import re
import subprocess
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9228',no_defaults=True,timeout=10000)
    page=browser.contexts[0].pages[0]
    page.evaluate("navigate('sync');render()")
    state=json.loads(page.evaluate('Native.load()'))
    host=state['remoteHost']
    assert state['tailnet']['state']=='Running'
    assert any(peer['ip']==host for peer in state['tailnet']['peers'])
    page.locator('#computer-trigger').click()
    assert page.locator('#computer-trigger').get_attribute('aria-expanded')=='true'
    assert page.locator('#remote-peer').count()==0
    assert not re.search(r'\b\d{1,3}(?:\.\d{1,3}){3}\b',page.locator('#computer-menu').inner_text())
    geometry=page.evaluate('(()=>{const a=document.getElementById("computer-trigger").getBoundingClientRect(),b=document.getElementById("computer-menu").getBoundingClientRect();return {bottom:a.bottom,top:b.top,width:a.width,menuWidth:b.width}})()')
    assert abs(geometry['bottom']-geometry['top'])<2
    assert abs(geometry['width']-geometry['menuWidth'])<2
    assert page.locator('#computer-menu .computer-state.online i').count()>0
    assert page.evaluate("computerStatus({online:false}).kind")=='offline'
    assert page.evaluate("computerStatus({online:true,expired:true}).kind")=='expired'
    assert page.evaluate("computerStatus(null).kind")=='unknown'
    time.sleep(.4)
    page.screenshot(path='/tmp/pocket-ledger-computer-menu.png')
    subprocess.run(['adb','-s',os.environ.get('ANDROID_SERIAL','648718eb'),'shell','input','keyevent','4'],check=True)
    for _ in range(20):
        if page.locator('#computer-trigger').get_attribute('aria-expanded')=='false':break
        time.sleep(.1)
    assert page.locator('#computer-trigger').get_attribute('aria-expanded')=='false'
    assert page.evaluate('page')=='sync'
    page.locator('#computer-trigger').click()
    page.locator(f'[data-computer="{host}"]').click()
    assert page.locator('#computer-trigger').get_attribute('aria-expanded')=='false'
    assert json.loads(page.evaluate('Native.load()'))['remoteHost']==host
    browser.close()
    print('PASS: inline computer dropdown, no visible IPs, status dots, native Back closes menu, selection retained')
