"""Run as root on the existing OCR host, after copying gateway and service files."""
from pathlib import Path
import subprocess
root = Path('/opt/pocket-ledger-ocr-api')
caddy = Path('/etc/caddy/Caddyfile')
old = caddy.read_text()
anchor = 'ocr.did2818233534.camdvr.org {\n'
route = '    handle /v1/* {\n        reverse_proxy 127.0.0.1:18092\n    }\n'
assert old.count(anchor) == 1
new = old if route in old else old.replace(anchor, anchor + route)
candidate = root / 'Caddyfile.candidate'
candidate.write_text(new)
subprocess.run(['caddy','validate','--config',str(candidate),'--adapter','caddyfile'],check=True)
service = Path('/etc/systemd/system/pocket-ledger-ocr-api.service')
service.write_bytes((root / service.name).read_bytes())
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','enable','--now',service.name],check=True)
# Preserve the prior routing for rollback; this file contains no keys.
(root / 'Caddyfile.before-api').write_text(old)
caddy.write_text(new)
try:
    subprocess.run(['systemctl','reload','caddy'],check=True)
except Exception:
    caddy.write_text(old)
    subprocess.run(['systemctl','reload','caddy'],check=True)
    raise
print('OCR API route deployed; legacy routes unchanged.')
