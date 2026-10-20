#!/usr/bin/env python3
"""Phone-authoritative LAN backup server. mDNS discovery via python-zeroconf."""
import argparse
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import sqlite3
import subprocess
import threading
import tempfile
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
                if "UP" in i.get("flags", []) and "LOWER_UP" in i.get("flags", [])
                and a.get("scope") == "global" and a.get("broadcast") and lan(a["local"])]
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
        self.path = self.directory / "ledger.json"
        self.lock = threading.RLock()
        if not self.path.exists():
            legacy = self.directory / "ledger.sqlite3"
            data = {"format": 1, "devices": [], "entries": []}
            if legacy.exists():
                with sqlite3.connect("file:" + str(legacy) + "?mode=ro", uri=True) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise OSError("Legacy database integrity check failed")
                    db.row_factory = sqlite3.Row
                    data["devices"] = [dict(row) for row in db.execute("SELECT * FROM devices")]
                    data["entries"] = [dict(row) for row in db.execute("SELECT * FROM entries ORDER BY at DESC")]
            self._write(data)
            if self.export() != data:
                raise OSError("JSON migration verification failed")
            if legacy.exists():
                archive = self.directory.parent / "backups"
                archive.mkdir(mode=0o700, exist_ok=True)
                backup = archive / ("ledger-before-json-" + str(time.time_ns()) + ".sqlite3")
                legacy.replace(backup)

    def _write(self, data):
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                    prefix=".ledger-", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def export(self):
        with self.lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("format") != 1 or not isinstance(data.get("devices"), list) or not isinstance(data.get("entries"), list):
                    raise ValueError("Invalid ledger format")
                return data
            except (ValueError, AttributeError) as error:
                raise OSError("Cannot read ledger JSON; file preserved") from error

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
        with self.lock:
            stored = self.export()
            previous = next((item for item in stored["devices"] if item["id"] == device), None)
            if previous and previous["revision"] > revision:
                raise ValueError("stale revision")
            if not previous or previous["revision"] != revision:
                stored["entries"] = [entry for entry in stored["entries"] if entry["device"] != device]
                stored["entries"].extend(dict(zip(("device", "id", "amount", "at", "category", "note"), row)) for row in rows)
                stored["entries"].sort(key=lambda entry: entry["at"], reverse=True)
                stored["devices"] = [item for item in stored["devices"] if item["id"] != device]
                stored["devices"].append({"id": device, "revision": revision,
                    "updated": dt.datetime.now(dt.timezone.utc).isoformat()})
                self._write(stored)
        return {"revision": revision, "count": len(rows)}


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
            except (OSError, sqlite3.Error):
                self.reply(503, {"error": "storage unavailable"})

        def do_GET(self):
            self.reply(404, {"error": "not found"})
    return Handler


MDNS_TYPE = "_pocket-ledger._tcp.local."


def mdns_properties(key, hosts):
    addresses_text = ",".join(sorted(hosts))
    return {"v": "1", "hosts": addresses_text, "proof": sign(key, "mdns\n" + addresses_text + "\n" + str(PORT))}


def announce(store, stop):
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
    zeroconf = None
    published = ()
    try:
        while not stop.is_set():
            hosts = tuple(sorted({host for host, _ in addresses()}))
            if hosts != published or (hosts and zeroconf is None):
                if zeroconf is not None:
                    zeroconf.close()
                    zeroconf = None
                published = ()
                if hosts:
                    try:
                        zeroconf = Zeroconf(interfaces=list(hosts), ip_version=IPVersion.V4Only)
                        instance = "Pocket Ledger " + hashlib.sha256(store.key.encode()).hexdigest()[:8]
                        info = ServiceInfo(MDNS_TYPE, instance + "." + MDNS_TYPE,
                            addresses=[socket.inet_aton(host) for host in hosts], port=PORT,
                            properties=mdns_properties(store.key, hosts),
                            server=socket.gethostname().split(".")[0] + ".local.")
                        zeroconf.register_service(info, allow_name_change=True)
                        published = hosts
                    except Exception as error:
                        print("mDNS publication will retry: " + type(error).__name__, flush=True)
                        if zeroconf is not None:
                            zeroconf.close()
                            zeroconf = None
            stop.wait(20)
    finally:
        if zeroconf is not None:
            zeroconf.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/opt/pocket-ledger/data")
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
    def terminate(_signum, _frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=8)


if __name__ == "__main__":
    main()
