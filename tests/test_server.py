import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import uuid

spec = importlib.util.spec_from_file_location("server", Path(__file__).parents[1] / "desktop/server.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = s.Store(self.tmp.name)
        self.data = {"device": str(uuid.uuid4()), "revision": 1, "entries": [
            {"id": str(uuid.uuid4()), "amount": 1234, "at": "2026-10-20T12:30",
             "category": "daily", "note": "午餐 <script>"}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_edit_delete_idempotent_and_stale(self):
        self.store.accept(self.data)
        self.store.accept(self.data)
        self.assertEqual(len(self.store.export()["entries"]), 1)
        old = copy.deepcopy(self.data)
        self.data["revision"] = 2
        self.data["entries"][0]["amount"] = 2399
        self.store.accept(self.data)
        self.assertEqual(self.store.export()["entries"][0]["amount"], 2399)
        with self.assertRaises(ValueError):
            self.store.accept(old)
        self.data.update(revision=3, entries=[])
        self.store.accept(self.data)
        self.assertEqual(self.store.export()["entries"], [])

    def test_atomic_validation_and_device_isolation(self):
        self.store.accept(self.data)
        other = copy.deepcopy(self.data)
        other["device"] = str(uuid.uuid4())
        self.store.accept(other)
        self.data["revision"] = 2
        self.data["entries"][0]["amount"] = -1
        with self.assertRaises(ValueError):
            self.store.accept(self.data)
        self.assertEqual(len(self.store.export()["entries"]), 2)

    def test_http_signatures_clock_and_invalid_payload(self):
        server = s.ThreadingHTTPServer(("127.0.0.1", 0), s.handler(self.store))
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            def post(data, key=None, timestamp=None):
                body = json.dumps(data)
                ts = timestamp or str(int(time.time()))
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/sync", body.encode(),
                    {"X-Time": ts, "X-Signature": s.sign(key or self.store.key, ts + "\n" + body)})
                return urllib.request.urlopen(request, timeout=3), ts
            response, ts = post(self.data)
            reply = response.read().decode()
            self.assertEqual(response.headers["X-Signature"], s.sign(self.store.key, ts + "\n" + reply))
            self.assertEqual(json.loads(reply)["revision"], 1)
            for key, timestamp in [("wrong", None), (None, "1")]:
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    post(self.data, key, timestamp)
                self.assertEqual(cm.exception.code, 401)
            with self.assertRaises(urllib.error.HTTPError) as cm:
                post({"device": "invalid"})
            self.assertEqual(cm.exception.code, 400)
            self.assertEqual(len(self.store.export()["entries"]), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_lan_only(self):
        for ip in ("10.0.0.1", "172.16.0.1", "192.168.2.3"):
            self.assertTrue(s.lan(ip))
        for ip in ("8.8.8.8", "127.0.0.1", "169.254.1.2", "172.32.0.1"):
            self.assertFalse(s.lan(ip))


if __name__ == "__main__":
    unittest.main()
