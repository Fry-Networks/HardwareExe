#!/usr/bin/env bash
set -euo pipefail
CODE="${1:?CODE (e.g. BM)}"
SERVICE="miner-online-${CODE}.service"
APPDIR="/opt/miner-${CODE}"
sudo systemctl stop "$SERVICE" 2>/dev/null || true
sudo systemctl disable "$SERVICE" 2>/dev/null || true
sudo rm -f "/etc/systemd/system/$SERVICE"
sudo systemctl daemon-reload
sudo rm -f "$APPDIR/miner-online-10min" "$APPDIR/miner-control" "$APPDIR/minerkey.txt" "$APPDIR/gnss.json" "$APPDIR/config.json" "$APPDIR/ca.pem"
sudo rmdir "$APPDIR" 2>/dev/null || true
echo "Uninstalled ${CODE}."
