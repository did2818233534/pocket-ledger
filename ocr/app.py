"""Screenshot OCR service for 小账 (RapidOCR / PP-OCR on CPU).

POST /parse  body = PNG/JPEG bytes -> {"fields": {...}, "lines": [...], "ms": int}
             a bill list (e.g. a long screenshot of 账单) also gets {"entries": [...], "skipped": n};
             optional header X-Date: YYYY-MM-DD (day the screenshot was taken) resolves 今天/昨天
POST /ocr    body = PNG/JPEG bytes -> {"lines": [...], "ms": int}
GET  /health                       -> {"ok": true}

If OCR_TOKEN is set, POST requests must send the same value in the X-Token header.
The service keeps no images or results.
"""
import hmac
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
from rapidocr import RapidOCR

from receipt import parse, parse_list

MAX_BODY = 16 * 1024 * 1024
PORT = int(os.environ.get("PORT", "18086"))
TOKEN = os.environ.get("OCR_TOKEN", "")

# Measured on a DXP2800 (Intel N100): capping the detector input at 736 px on the long side and
# skipping the direction classifier keeps payment fields intact at ~1.5-3.5 s per screenshot.
params = {"Det.limit_type": "max", "Det.limit_side_len": 736, "Global.use_cls": False}
if os.environ.get("OCR_THREADS"):
    # Cap onnxruntime's threads on a shared machine; by default it uses every physical core.
    params["EngineConfig.onnxruntime.intra_op_num_threads"] = int(os.environ["OCR_THREADS"])
engine = RapidOCR(params=params)
lock = threading.Lock()  # one inference at a time; onnxruntime already uses every core


def _recognize(image, top):
    result = engine(image)
    lines = []
    for box, text, score in zip(result.boxes if result.txts else (), result.txts or (), result.scores or ()):
        lines.append({"text": text, "score": round(float(score), 4), "box": [[int(x), int(y) + top] for x, y in box]})
    return lines


def recognize(image):
    """OCR an image; scrolling (long) screenshots are read in screen-sized tiles.

    The detector input is capped at 736 px, so a 1080x12000 long screenshot read in one pass would
    shrink to 66 px wide. Tiles of about one screen keep the usual scale; neighbouring tiles overlap,
    and each line is kept only by the tile that owns its centre, so lines cut at an edge are not lost
    or doubled.
    """
    height, width = image.shape[:2]
    if height <= width * 2.4:  # phone screens are about 2.2:1
        return _recognize(image, 0)
    tile, overlap = width * 2, width // 4
    lines, top = [], 0
    while True:
        bottom = min(height, top + tile)
        low = 0 if top == 0 else top + overlap // 2
        high = height if bottom == height else bottom - overlap // 2
        lines += [line for line in _recognize(image[top:bottom], top)
                  if low <= sum(y for _, y in line["box"]) / 4 < high]
        if bottom == height:
            return lines
        top = bottom - overlap


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def screenshot_day(self):
        try:
            return date.fromisoformat(self.headers.get("X-Date", ""))
        except ValueError:
            return datetime.now(timezone(timedelta(hours=8))).date()  # the users are in China

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ok": True})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ("/ocr", "/parse"):
            return self.reply(404, {"error": "not found"})
        if TOKEN and not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
            return self.reply(401, {"error": "token"})
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_BODY:
            return self.reply(413, {"error": "size limit"})
        image = cv2.imdecode(np.frombuffer(self.rfile.read(length), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return self.reply(400, {"error": "not an image"})
        start = time.perf_counter()
        with lock:
            lines = recognize(image)
        result = {"lines": lines, "ms": round((time.perf_counter() - start) * 1000)}
        if self.path == "/parse":
            result["fields"] = parse(lines, height=image.shape[0])
            listed = parse_list(lines, width=image.shape[1], today=self.screenshot_day())
            if listed:
                result.update(listed)
        self.reply(200, result)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
