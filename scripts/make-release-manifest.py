#!/usr/bin/env python3
"""Generate the update manifest from the current Android version and signed APK."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

root = Path(__file__).resolve().parents[1]
gradle = (root / 'app/build.gradle').read_text()
version = re.search(r"versionName\s+'([^']+)'", gradle).group(1)
code = int(re.search(r'versionCode\s+(\d+)', gradle).group(1))
parser = argparse.ArgumentParser()
parser.add_argument('apk', nargs='?', default=str(root / f'dist/PocketLedgerSmart-{version}.apk'))
parser.add_argument('--base-url', default='https://ocr.did2818233534.camdvr.org/updates/')
parser.add_argument('--output')
args = parser.parse_args()
apk = Path(args.apk)
content = apk.read_bytes()
manifest = {'schema': 1, 'versionCode': code, 'versionName': version, 'prerelease': False,
            'assets': {'arm64-v8a': {'url': args.base_url.rstrip('/') + '/' + quote(apk.name),
                                   'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content)}}}
path = Path(args.output) if args.output else apk.parent / 'latest.json'
path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
print(path)
