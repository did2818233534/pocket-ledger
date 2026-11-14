"""Exercise multi-select with isolated synthetic data in headless Chrome."""
import datetime, html, json, pathlib, re, shutil, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class BatchSelectionUITest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('google-chrome'), 'Chrome not installed')
    def test_long_press_cancel_and_confirm_delete(self):
        assets = ROOT / 'app/src/main/assets'
        with tempfile.TemporaryDirectory(prefix='ledger-batch-test-') as tmp:
            d = pathlib.Path(tmp)
            for n in ('index.html', 'model.js', 'app.js', 'style.css'):
                shutil.copy(assets / n, d / n)
            day = datetime.date.today().isoformat()
            state = {'users':[{'id':'1','name':'测试','pending':False}], 'currentUser':'1',
                     'entries':[{'id':i,'owner':'1','amount':100,'at':day,'category':'daily','note':i} for i in ('a','b')],
                     'drafts':[], 'capture':{}, 'tailnet':{}}
            (d/'mock.js').write_text('window.testState='+json.dumps(state,ensure_ascii=False)+';window.calls=[];window.confirm=()=>window.allowDelete;window.Native={load:()=>JSON.stringify(window.testState),removeMany:s=>{window.calls.push(JSON.parse(s));return ""},hideKeyboard:()=>{}};')
            (d/'test.js').write_text('''
const checks=[], click=s=>{const e=document.querySelector(s);if(!e)throw Error('missing '+s);e.click()};
const press=e=>e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:10,clientY:10}));
try {
 let b=document.querySelector('[data-edit="a"]');press(b);b.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:50,clientY:10}));
 setTimeout(()=>{try{
  checks.push(!document.querySelector('#batch-delete'));press(document.querySelector('[data-edit="a"]'));
  setTimeout(()=>{try{
   checks.push(document.querySelector('#batch-delete')!==null&&document.body.innerText.includes('已选 1 笔'));
   setTimeout(()=>{try{
    click('[data-select="b"]');checks.push(document.body.innerText.includes('已选 2 笔'));
    window.allowDelete=false;click('#batch-delete');checks.push(window.calls.length===0);
    window.allowDelete=true;click('#batch-delete');checks.push(window.calls.length===1&&window.calls[0].sort().join(',')==='a,b');
    document.body.dataset.test=JSON.stringify(checks);
   }catch(e){document.body.dataset.test='ERROR:'+e.message}},400);
  }catch(e){document.body.dataset.test='ERROR:'+e.message}},600);
 }catch(e){document.body.dataset.test='ERROR:'+e.message}},600);
}catch(e){document.body.dataset.test='ERROR:'+e.message}
''')
            path=d/'index.html'; page=path.read_text().replace('<meta http-equiv="Content-Security-Policy"','<meta data-http-equiv="Content-Security-Policy"').replace('<script src="model.js"></script>','<script src="mock.js"></script><script src="model.js"></script>').replace('</body>','<script src="test.js"></script></body>');path.write_text(page)
            cmd=[shutil.which('google-chrome'),'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--user-data-dir='+str(d/'profile'),'--virtual-time-budget=2500','--dump-dom',path.as_uri()]
            result=subprocess.run(cmd,capture_output=True,text=True,timeout=30,check=True)
            match=re.search(r'data-test="([^"]*)"',result.stdout)
            self.assertIsNotNone(match, result.stderr[-500:])
            self.assertEqual(html.unescape(match.group(1)),'[true,true,true,true,true]')

if __name__ == '__main__': unittest.main()
