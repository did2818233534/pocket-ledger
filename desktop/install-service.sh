#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
cat > "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/pocket-ledger.service" <<EOF
[Unit]
Description=Pocket Ledger LAN backup
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 "$BASE/server.py" --data "$BASE/data"
WorkingDirectory=$BASE
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF
loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now pocket-ledger.service
printf '小账电脑服务已启动，已开启开机启动。\n'
printf '查看配对信息：python3 "%s/server.py" --pair\n' "$BASE"
