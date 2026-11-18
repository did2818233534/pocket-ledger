"""Authenticated OCR gateway. No image/response storage; SQLite stores keys and counters only."""
from contextlib import contextmanager
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get('OCR_API_DB', 'data/api.sqlite3')
MAX_BODY = 16 * 1024 * 1024
ROUTES = {'/v1/ocr': '/ocr', '/v1/receipts/parse': '/parse'}


@contextmanager
def connect():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS keys (id TEXT PRIMARY KEY, name TEXT, hash TEXT UNIQUE, rpm INTEGER, daily INTEGER, enabled INTEGER DEFAULT 1)')
    db.execute('CREATE TABLE IF NOT EXISTS usage (id TEXT, day TEXT, count INTEGER, PRIMARY KEY(id, day))')
    db.execute('CREATE TABLE IF NOT EXISTS minute_usage (id TEXT PRIMARY KEY, minute INTEGER, count INTEGER)')
    db.commit()
    try:
        with db:
            yield db
    finally:
        db.close()


def issue(name, rpm, daily):
    if rpm < 1 or daily < 1:
        raise ValueError('limits must be positive')
    key = 'sk-ocr-' + secrets.token_urlsafe(32)
    with connect() as db:
        db.execute('INSERT INTO keys VALUES(?,?,?,?,?,1)', (secrets.token_hex(6), name, hashlib.sha256(key.encode()).hexdigest(), rpm, daily))
    return key


def authorize(key, charge=True):
    digest = hashlib.sha256(key.encode()).hexdigest()
    minute = int(time.time() // 60)
    day = time.strftime('%Y-%m-%d', time.gmtime())
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT id,name,rpm,daily FROM keys WHERE hash=? AND enabled=1', (digest,)).fetchone()
        if not row:
            return 401, None
        ident, name, rpm, daily = row
        used = db.execute('SELECT count FROM usage WHERE id=? AND day=?', (ident, day)).fetchone()
        used = used[0] if used else 0
        burst = db.execute('SELECT count FROM minute_usage WHERE id=? AND minute=?', (ident, minute)).fetchone()
        burst = burst[0] if burst else 0
        info = dict(id=ident, name=name, daily_limit=daily, used_today=used, requests_per_minute=rpm, day_utc=day)
        if charge:
            if used >= daily or burst >= rpm:
                return 429, info
            db.execute('INSERT INTO usage VALUES(?,?,1) ON CONFLICT(id,day) DO UPDATE SET count=count+1', (ident, day))
            db.execute('INSERT INTO minute_usage VALUES(?,?,1) ON CONFLICT(id) DO UPDATE SET minute=excluded.minute,count=CASE WHEN minute=excluded.minute THEN count+1 ELSE 1 END', (ident, minute))
            db.execute("DELETE FROM usage WHERE day < date('now','-31 days')")
        return 200, info


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Bound connection count, including slow clients, before starting handler threads.
    slots = threading.BoundedSemaphore(24)
    def process_request(self, request, address):
        if not self.slots.acquire(False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    jobs = threading.BoundedSemaphore(2)
    def setup(self):
        super().setup()
        self.connection.settimeout(20)
    def log_message(self, *args):
        pass  # never log credentials, image bytes, or recognition results
    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if status == 429:
            self.send_header('Retry-After', '60')
        self.end_headers()
        self.wfile.write(body)
    def error(self, status, code, message):
        self.reply(status, {'error': {'code': code, 'message': message}})
    def auth(self, charge=True):
        header = self.headers.get('Authorization', '')
        if not header.startswith('Bearer ') or len(header) > 256:
            self.error(401, 'invalid_api_key', 'Provide Authorization: Bearer <API_KEY>')
            return False
        status, info = authorize(header[7:], charge)
        if status == 401:
            self.error(401, 'invalid_api_key', 'Invalid or revoked API key')
        elif status == 429:
            self.error(429, 'rate_limit_exceeded', 'Minute or daily limit exceeded; daily quota resets at 00:00 UTC')
        else:
            return info
        return False
    def do_GET(self):
        if self.path == '/v1/docs':
            body = (Path(__file__).parent / 'README.md').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/v1/health':
            return self.reply(200, {'ok': True})
        if self.path == '/v1/usage':
            info = self.auth(False)
            if info:
                self.reply(200, info)
            return
        self.error(404, 'not_found', 'Unknown API endpoint')
    def do_POST(self):
        if self.path not in ROUTES:
            return self.error(404, 'not_found', 'Unknown API endpoint')
        if not self.auth(False):
            return
        if self.headers.get('Transfer-Encoding'):
            return self.error(400, 'invalid_request', 'Use Content-Length, not chunked encoding')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY:
            return self.error(413, 'image_too_large', 'Send an image up to 16 MiB')
        if self.headers.get_content_type() not in ('image/png', 'image/jpeg', 'image/webp', 'application/octet-stream'):
            return self.error(415, 'invalid_content_type', 'Send raw PNG, JPEG or WebP image bytes')
        if not self.jobs.acquire(False):
            return self.error(503, 'busy', 'OCR is busy; retry later')
        try:
            try:
                body = self.rfile.read(length)
            except (TimeoutError, OSError):
                return self.error(408, 'upload_timeout', 'Image upload timed out')
            if len(body) != length:
                return self.error(400, 'incomplete_image', 'Incomplete upload')
            if not self.auth(True):
                return
            headers = {'Content-Type': self.headers.get_content_type(), 'X-Token': os.environ['OCR_UPSTREAM_TOKEN']}
            for name in ('X-Date', 'X-Cashflow'):
                value = self.headers.get(name)
                if value and len(value) <= 32:
                    headers[name] = value
            for base in os.environ.get('OCR_UPSTREAMS', 'http://127.0.0.1:18091,http://127.0.0.1:18090').split(','):
                req = urllib.request.Request(base.rstrip('/') + ROUTES[self.path], data=body, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        result = json.loads(response.read(8 * 1024 * 1024))
                    return self.reply(200, result)
                except urllib.error.HTTPError as e:
                    if e.code in (400, 413, 415):
                        return self.error(e.code, 'invalid_image', 'Invalid or oversized image')
                except (OSError, ValueError, http.client.HTTPException):
                    pass
            self.error(502, 'upstream_unavailable', 'OCR service temporarily unavailable')
        finally:
            self.jobs.release()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create-key')
    create.add_argument('name')
    create.add_argument('--rpm', type=int, default=20)
    create.add_argument('--daily', type=int, default=500)
    sub.add_parser('list-keys')
    revoke = sub.add_parser('revoke-key')
    revoke.add_argument('id')
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=18092)
    args = parser.parse_args()
    if args.command == 'create-key':
        print(issue(args.name, args.rpm, args.daily))
    elif args.command == 'list-keys':
        with connect() as db:
            print(json.dumps(db.execute('SELECT id,name,rpm,daily,enabled FROM keys').fetchall(), ensure_ascii=False))
    elif args.command == 'revoke-key':
        with connect() as db:
            db.execute('UPDATE keys SET enabled=0 WHERE id=?', (args.id,))
    else:
        if not os.environ.get('OCR_UPSTREAM_TOKEN'):
            raise SystemExit('OCR_UPSTREAM_TOKEN is required')
        with connect():
            pass
        Server(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
