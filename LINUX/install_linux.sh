#!/usr/bin/env bash
set -euo pipefail
CODE="${1:?CODE (e.g. BM)}"
VER="${2:?VERSION (e.g. 1.0.0)}"
APPDIR="/opt/miner-${CODE}"

sudo mkdir -p "$APPDIR"
SRC="$(cd "$(dirname "$0")" && pwd)"
sudo install -m 755 "$SRC/dist/miner-control_${CODE}_v${VER}" "$APPDIR/miner-control"
sudo install -m 755 "$SRC/dist/miner-online-10min_${CODE}_v${VER}" "$APPDIR/miner-online-10min"
[ -f "$SRC/minerkey.txt" ] && sudo install -m 600 "$SRC/minerkey.txt" "$APPDIR/minerkey.txt"
[ -f "$SRC/gnss.json" ] && sudo install -m 600 "$SRC/gnss.json" "$APPDIR/gnss.json"
[ -f "$SRC/config.json" ] && sudo install -m 600 "$SRC/config.json" "$APPDIR/config.json"
[ -f "$SRC/ca.pem" ] && sudo install -m 600 "$SRC/ca.pem" "$APPDIR/ca.pem"

SERVICE="miner-online-${CODE}.service"
sudo tee "/etc/systemd/system/$SERVICE" >/dev/null <<UNIT
[Unit]
Description=Miner Online Status (${CODE}) v${VER}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APPDIR
ExecStart=$APPDIR/miner-online-10min
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
echo "Installed. Launch GUI: $APPDIR/miner-control"
