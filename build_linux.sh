#!/usr/bin/env bash
set -euo pipefail
CODE="${1:?Usage: $0 CODE VERSION}"
VER="${2:?Usage: $0 CODE VERSION}"

python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib pymongo h3 shapely geoip2

python3 tools/make_profile.py --code "$CODE" --version "$VER"

SVC_NAME="miner-online-10min_${CODE}_v${VER}"
GEOLITE_PATH="${MAXMIND_DB_PATH:-$(pwd)/GeoLite2-Country.mmdb}"
SVC_EXTRA=""
if [[ -f "$GEOLITE_PATH" ]]; then
  SVC_EXTRA="--add-data \"${GEOLITE_PATH}:\.\""
  echo "Bundling GeoLite2 database from ${GEOLITE_PATH}" >&2
else
  echo "WARNING: GeoLite2-Country.mmdb not found; runtime country checks will require MAXMIND_DB_PATH" >&2
fi
pyinstaller --onefile --name "$SVC_NAME" --collect-binaries h3 --collect-all shapely --collect-all geoip2 $SVC_EXTRA miner_online_simple.py

GUI_NAME="miner-control_${CODE}_v${VER}"
pyinstaller --onefile --name "$GUI_NAME" --add-data "frynetworks_logo.png:." miner_control.py

