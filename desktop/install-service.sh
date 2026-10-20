#!/usr/bin/env bash
set -euo pipefail
BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=/opt/pocket-ledger
/usr/bin/python3 -c "import zeroconf" || {
    printf '缺少 mDNS 依赖，请先安装系统包 python3-zeroconf。\n' >&2
    exit 1
}
if [[ ! -d "$INSTALL_DIR" ]]; then
    sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" "$INSTALL_DIR"
fi
if [[ ! -w "$INSTALL_DIR" ]]; then
    printf '%s 不可写，请先将该目录授予当前用户。\n' "$INSTALL_DIR" >&2
    exit 1
fi
if [[ -d "$BASE/data" && -d "$INSTALL_DIR/data" ]]; then
    printf '源目录与安装目录均有 data，停止以避免覆盖，请先核对。\n' >&2
    exit 1
fi
systemctl --user stop pocket-ledger.service 2>/dev/null || true
# Existing data and pairing key are moved together without regeneration.
if [[ -d "$BASE/data" ]]; then
    mv -- "$BASE/data" "$INSTALL_DIR/data"
fi
install -m 0644 "$BASE/server.py" "$INSTALL_DIR/server.py.new"
mv -- "$INSTALL_DIR/server.py.new" "$INSTALL_DIR/server.py"
install -m 0644 "$BASE/requirements.txt" "$INSTALL_DIR/requirements.txt"
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
cat > "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/pocket-ledger.service" <<UNIT
[Unit]
Description=Pocket Ledger LAN backup
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 "$INSTALL_DIR/server.py" --data "$INSTALL_DIR/data"
WorkingDirectory=$INSTALL_DIR
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
UNIT
loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now pocket-ledger.service
printf '小账已部署到 %s，数据目录为 %s/data。\n' "$INSTALL_DIR" "$INSTALL_DIR"
printf '查看配对信息：python3 "%s/server.py" --pair\n' "$INSTALL_DIR"
