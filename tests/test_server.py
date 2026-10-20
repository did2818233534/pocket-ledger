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
import sqlite3
import shutil
from unittest.mock import patch

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

    def test_giving_category_round_trip_and_invalid_category(self):
        self.data["entries"][0]["category"] = "giving"
        self.store.accept(self.data)
        self.assertEqual(self.store.export()["entries"][0]["category"], "giving")
        self.data["revision"] = 2
        self.data["entries"][0]["category"] = "unknown"
        with self.assertRaises(ValueError):
            self.store.accept(self.data)
        self.assertEqual(self.store.export()["entries"][0]["category"], "giving")

    def test_mdns_proof_binds_address_list_and_port_without_exposing_key(self):
        props = s.mdns_properties(self.store.key, ["192.168.10.157", "10.0.0.2"])
        self.assertEqual(props["hosts"], "10.0.0.2,192.168.10.157")
        self.assertEqual(props["proof"], s.sign(self.store.key, "mdns\n10.0.0.2,192.168.10.157\n47831"))
        self.assertNotEqual(props["proof"], s.sign(self.store.key, "mdns\n192.168.10.1\n47831"))
        self.assertNotEqual(props["proof"], s.sign(self.store.key, "mdns\n10.0.0.2,192.168.10.157\n80"))
        self.assertNotIn(self.store.key, json.dumps(props))

    def test_failed_atomic_replace_preserves_previous_ledger(self):
        self.store.accept(self.data)
        previous = self.store.export()
        self.data["revision"] = 2
        self.data["entries"][0]["amount"] = 9999
        with patch.object(s.os, "replace", side_effect=OSError("simulated disk error")):
            with self.assertRaises(OSError):
                self.store.accept(self.data)
        self.assertEqual(self.store.export(), previous)
        self.assertEqual(list(self.store.directory.glob(".ledger-*.tmp")), [])

    def test_json_directory_can_be_copied_with_pairing_and_versions(self):
        self.store.accept(self.data)
        with tempfile.TemporaryDirectory() as destination:
            copied = Path(destination) / "data"
            shutil.copytree(self.store.directory, copied)
            restored = s.Store(copied)
            self.assertEqual(restored.key, self.store.key)
            self.assertEqual(restored.export(), self.store.export())
            self.data.update(revision=2, entries=[])
            restored.accept(self.data)
            self.assertEqual(restored.export()["entries"], [])

    def test_month_partition_date_move_delete_and_unchanged_month(self):
        september = {**self.data["entries"][0], "id": str(uuid.uuid4()), "at": "2026-09-30T23:59"}
        self.data["entries"].append(september)
        self.store.accept(self.data)
        september_path = self.store.directory / "2026-09.json"
        september_mtime = september_path.stat().st_mtime_ns
        october = json.loads((self.store.directory / "2026-10.json").read_text())
        self.assertEqual(len(october["entries"]), 1)
        self.data["revision"] = 2
        self.data["entries"][0]["at"] = "2026-11-01T00:01"
        self.store.accept(self.data)
        self.assertFalse((self.store.directory / "2026-10.json").exists())
        self.assertTrue((self.store.directory / "2026-11.json").exists())
        self.assertEqual(september_path.stat().st_mtime_ns, september_mtime)
        self.data["revision"] = 3
        self.data["entries"].remove(september)
        self.store.accept(self.data)
        self.assertFalse(september_path.exists())
        self.assertEqual(json.loads(self.store.path.read_text())["months"], ["2026-11"])
        self.assertEqual(len(self.store.export()["entries"]), 1)

    def test_interrupted_cross_month_sync_recovers_on_restart(self):
        self.store.accept(self.data)
        self.data["revision"] = 2
        self.data["entries"][0]["at"] = "2026-11-02T12:00"
        write = self.store._atomic_write
        def fail_before_metadata(path, value):
            if path == self.store.path:
                raise OSError("simulated interruption")
            write(path, value)
        with patch.object(self.store, "_atomic_write", side_effect=fail_before_metadata):
            with self.assertRaises(OSError):
                self.store.accept(self.data)
        self.assertTrue(self.store.pending.exists())
        restarted = s.Store(self.store.directory)
        self.assertFalse(restarted.pending.exists())
        self.assertEqual(restarted.export()["devices"][0]["revision"], 2)
        self.assertEqual(restarted.export()["entries"][0]["at"], "2026-11-02T12:00")
        self.assertFalse((self.store.directory / "2026-10.json").exists())
        restarted.accept(self.data)
        self.assertEqual(len(restarted.export()["entries"]), 1)

    def test_single_json_migrates_to_month_files_without_losing_metadata(self):
        self.store.accept(self.data)
        old = self.store.export()
        target = Path(self.tmp.name) / "legacy-json" / "data"
        target.mkdir(parents=True)
        (target / "ledger.json").write_text(json.dumps(old))
        (target / "config.json").write_text(json.dumps({"key": self.store.key}))
        migrated = s.Store(target)
        self.assertEqual(migrated.export(), old)
        self.assertEqual(migrated.key, self.store.key)
        self.assertTrue((target / "2026-10.json").exists())
        self.assertFalse((target / "ledger.json").exists())
        self.assertEqual(len(list((target.parent / "backups").glob("*.json"))), 1)

    def test_sqlite_migration_preserves_pairing_records_and_revision(self):
        legacy_dir = Path(self.tmp.name) / "migration" / "data"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "config.json").write_text(json.dumps({"key": self.store.key}))
        entry = self.data["entries"][0]
        with sqlite3.connect(legacy_dir / "ledger.sqlite3") as db:
            db.executescript("""
                CREATE TABLE devices(id TEXT, revision INTEGER, updated TEXT);
                CREATE TABLE entries(device TEXT,id TEXT,amount INTEGER,at TEXT,category TEXT,note TEXT);
            """)
            db.execute("INSERT INTO devices VALUES(?,?,?)", (self.data["device"], 1, "2026-10-20"))
            db.execute("INSERT INTO entries VALUES(?,?,?,?,?,?)",
                       (self.data["device"], entry["id"], entry["amount"], entry["at"], entry["category"], entry["note"]))
        restored = s.Store(legacy_dir)
        self.assertEqual(restored.key, self.store.key)
        self.assertEqual(restored.export()["devices"][0]["revision"], 1)
        self.assertEqual(restored.export()["entries"][0], {"device": self.data["device"], **entry})
        self.assertFalse((legacy_dir / "ledger.sqlite3").exists())
        self.assertEqual(len(list((legacy_dir.parent / "backups").glob("*.sqlite3"))), 1)
        restored.accept(self.data)
        self.assertEqual(len(restored.export()["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
