import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('gateway', Path(__file__).resolve().parents[1] / 'ocr/api/gateway.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = g.DB
        g.DB = self.tmp.name + '/keys.sqlite3'
        self.key = g.issue('test', 3, 5)
    def tearDown(self):
        g.DB = self.old
        self.tmp.cleanup()
    def test_invalid_revoked_and_independent_keys(self):
        self.assertEqual(g.authorize('bad')[0], 401)
        other = g.issue('other', 2, 2)
        for _ in range(3): self.assertEqual(g.authorize(self.key)[0], 200)
        self.assertEqual(g.authorize(self.key)[0], 429)
        self.assertEqual(g.authorize(other)[0], 200)
        with g.connect() as db:
            db.execute('UPDATE keys SET enabled=0 WHERE name=?', ('other',))
        self.assertEqual(g.authorize(other)[0], 401)
    def test_atomic_quota(self):
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda _: g.authorize(self.key)[0], range(12)))
        self.assertEqual(results.count(200), 3)
        self.assertEqual(g.authorize(self.key, False)[1]['used_today'], 3)
    def test_minute_daily_reset(self):
        with patch.object(g.time, 'time', return_value=120):
            for _ in range(3): self.assertEqual(g.authorize(self.key)[0], 200)
        with patch.object(g.time, 'time', return_value=180):
            for _ in range(2): self.assertEqual(g.authorize(self.key)[0], 200)
            self.assertEqual(g.authorize(self.key)[0], 429)
        with patch.object(g.time, 'strftime', return_value='2099-01-01'), patch.object(g.time, 'time', return_value=240):
            self.assertEqual(g.authorize(self.key)[0], 200)
    def test_http_contract_fallback_and_errors(self):
        seen = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                seen.append((self.path, self.headers.get('X-Token'), self.rfile.read(int(self.headers['Content-Length']))))
                result = json.dumps({'lines': [{'text':'test'}], 'fields':{'amount':'12.50'}}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(result)
        upstream = ThreadingHTTPServer(('127.0.0.1',0), Upstream)
        server = g.Server(('127.0.0.1',0), g.Handler)
        threads = [threading.Thread(target=s.serve_forever) for s in (upstream, server)]
        for t in threads:t.start()
        def request(path, token=None, body=None, content='image/png'):
            headers = {'Content-Type': content}
            if token:headers['Authorization']='Bearer '+token
            try:
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path, data=body, headers=headers)) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as e:
                return e.code,json.load(e)
        try:
            with patch.dict(os.environ, OCR_UPSTREAM_TOKEN='internal', OCR_UPSTREAMS=f'http://127.0.0.1:1,http://127.0.0.1:{upstream.server_port}'):
                self.assertEqual(request('/v1/ocr', body=b'image')[0],401)
                self.assertEqual(request('/v1/ocr',self.key,b'image','text/plain')[0],415)
                self.assertEqual(request('/v1/receipts/parse',self.key,b'image')[0],200)
                self.assertEqual(seen,[('/parse','internal',b'image')])
                self.assertEqual(request('/v1/usage',self.key)[1]['used_today'],1)
                self.assertEqual(request('/bad',self.key)[0],404)
        finally:
            for s in (server, upstream):s.shutdown();s.server_close()
            for t in threads:t.join()

if __name__ == '__main__': unittest.main()
