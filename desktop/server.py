#!/usr/bin/env python3
"""Phone-authoritative LAN backup server. Python standard library only."""
import argparse
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 47831
MAX_BODY = 4 * 1024 * 1024


def sign(key, text):
    return hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()


def lan(ip):
    a = ipaddress.ip_address(ip)
    return a.version == 4 and any(a in n for n in (
        ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16")))


def addresses():
    try:
        data = json.loads(subprocess.check_output(["ip", "-j", "-4", "addr"], timeout=3))
        return [(a["local"], a.get("broadcast")) for i in data for a in i.get("addr_info", [])
                if a.get("scope") == "global" and lan(a["local"])]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        config = self.directory / "config.json"
        if not config.exists():
            fd = os.open(config, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"key": secrets.token_hex(32)}, f)
        self.key = json.loads(config.read_text())["key"]
        self.db = self.directory / "ledger.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entries(device TEXT NOT NULL,id TEXT NOT NULL,amount INTEGER NOT NULL,
                    at TEXT NOT NULL,category TEXT NOT NULL,note TEXT NOT NULL,PRIMARY KEY(device,id));
            """)

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def accept(self, data):
        device = str(uuid.UUID(data["device"]))
        revision = data["revision"]
        if type(revision) is not int or not 0 <= revision <= 2**63-1:
            raise ValueError("invalid revision")
        entries = data["entries"]
        if not isinstance(entries, list) or len(entries) > 100000:
            raise ValueError("invalid entries")
        rows, seen = [], set()
        for e in entries:
            eid = str(uuid.UUID(e["id"]))
            if eid in seen:
                raise ValueError("duplicate id")
            seen.add(eid)
            amount = e["amount"]
            if type(amount) is not int or not 1 <= amount <= 99999999999:
                raise ValueError("invalid amount")
            when = e["at"]
            parsed = dt.datetime.fromisoformat(when)
            if parsed.tzinfo is not None or "T" not in when:
                raise ValueError("local time required")
            if e["category"] not in ("daily", "extra", "claim", "giving") or not isinstance(e["note"], str) or len(e["note"]) > 200:
                raise ValueError("invalid category or note")
            rows.append((device, eid, amount, when, e["category"], e["note"]))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT revision FROM devices WHERE id=?", (device,)).fetchone()
            if previous and previous[0] > revision:
                raise ValueError("stale revision")
            if not previous or previous[0] != revision:
                db.execute("DELETE FROM entries WHERE device=?", (device,))
                db.executemany("INSERT INTO entries VALUES(?,?,?,?,?,?)", rows)
                db.execute("INSERT OR REPLACE INTO devices VALUES(?,?,?)",
                           (device, revision, dt.datetime.now(dt.timezone.utc).isoformat()))
        return {"revision": revision, "count": len(rows)}

    def export(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return {"devices": [dict(r) for r in db.execute("SELECT * FROM devices")],
                    "entries": [dict(r) for r in db.execute("SELECT * FROM entries ORDER BY at DESC")]}


def handler(store):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            pass

        def reply(self, code, data, timestamp=""):
            body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            if timestamp:
                self.send_header("X-Signature", sign(store.key, timestamp + "\n" + body.decode()))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if not lan(self.client_address[0]) and self.client_address[0] != "127.0.0.1":
                return self.reply(403, {"error": "LAN only"})
            if self.path != "/sync":
                return self.reply(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {"error": "size limit"})
                timestamp = self.headers.get("X-Time", "")
                if abs(time.time() - int(timestamp)) > 120:
                    return self.reply(401, {"error": "clock or key"})
                body = self.rfile.read(length).decode("utf-8")
                if not hmac.compare_digest(sign(store.key, timestamp + "\n" + body),
                                           self.headers.get("X-Signature", "")):
                    return self.reply(401, {"error": "invalid signature"})
                result = store.accept(json.loads(body))
                self.reply(200, result, timestamp)
            except (ValueError, KeyError, TypeError, OverflowError):
                self.reply(400, {"error": "invalid snapshot"})
            except sqlite3.Error:
                self.reply(503, {"error": "storage unavailable"})

        def do_GET(self):
            self.reply(404, {"error": "not found"})
    return Handler


def announce(store, stop):
    while not stop.is_set():
        for host, broadcast in addresses():
            if not broadcast:
                continue
            body = json.dumps({"app": "pocket-ledger", "host": host, "time": int(time.time())}, separators=(",", ":"))
            payload = json.dumps({"body": body, "signature": sign(store.key, body)}).encode()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    sock.bind((host, 0))
                    sock.sendto(payload, (broadcast, 47832))
            except OSError:
                pass
        stop.wait(20)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(Path(__file__).resolve().parent / "data"))
    parser.add_argument("--pair", action="store_true")
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    store = Store(args.data)
    if args.pair:
        print("电脑地址：" + " / ".join(a for a, _ in addresses()))
        print("配对密钥：" + store.key)
        return
    if args.export:
        args.export.write_text(json.dumps(store.export(), ensure_ascii=False, indent=2))
        print("已导出：" + str(args.export))
        return
    stop = threading.Event()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), handler(store))
    server.daemon_threads = True
    worker = threading.Thread(target=announce, args=(store, stop), daemon=True)
    worker.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=4)


if __name__ == "__main__":
    main()
