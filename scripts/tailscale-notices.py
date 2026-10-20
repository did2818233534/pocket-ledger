"""Bundle licenses from modules linked into the embedded Android Tailscale library."""
import json
import os
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
env = dict(os.environ, GOOS='android', GOARCH='arm64', CGO_ENABLED='1')
lines = subprocess.check_output(['go','list','-deps','-f','{{if .Module}}{{.Module.Path}}{{end}}','.'],cwd=root/'mobiletailscale',env=env,text=True).splitlines()
modules = sorted((set(filter(None,lines)) | {'golang.org/x/mobile'}) - {'cn.guga/ledger/mobiletailscale'})
parts = ['小账内置 Tailscale 开源声明\nTailscale: https://github.com/tailscale/tailscale\nTailscale 核心采用 BSD-3-Clause；以下为实际链接依赖的许可。\n']
for module in modules:
    info = json.loads(subprocess.check_output(['go','list','-m','-json',module],cwd=root/'mobiletailscale',text=True))
    directory = Path(info['Dir'])
    files = [f for f in directory.iterdir() if f.is_file() and f.name.lower().startswith(('license','copying','notice','copyright'))]
    parts.append('\n' + '='*60 + '\n' + module + ' ' + info.get('Version','') + '\n')
    for f in sorted(files): parts.append(f.name+'\n'+f.read_text(errors='replace'))
    if not files: raise SystemExit('Missing license: '+module)
# Include the Go runtime license too.
goroot = Path(subprocess.check_output(['go','env','GOROOT'],text=True).strip())
parts.append('\nGo runtime\n'+(goroot/'LICENSE').read_text())
(root/'app/src/main/assets/tailscale-notices.txt').write_text('\n'.join(parts))
