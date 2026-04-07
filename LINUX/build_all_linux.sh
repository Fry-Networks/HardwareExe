#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- Defaults ----------
read -r -a DEFAULT_CODES <<<"BM IDM ODM ISM OSM SVN SDN RDN AEM IRM"
CODES=("${DEFAULT_CODES[@]}")
VERSION="5.5.2"
VERSION_CHECK_SEC=600
INTERVAL_SECONDS=600
SOFTWARE_UPTODATE=1
USE_1PASSWORD=1
USE_GITHUB=1
TLS_CA_FILE=""
OP_REF_API_BASE_URL=""
OP_REF_BEARER_TOKEN="op://VPS/Hardware_API/API_BEARER_TOKEN"
OP_REF_SIGNING_KEY="op://VSCode/hardware_exe/local_signing_key_hex"
OP_REF_UPDATE_REPO="op://VSCode/hardware_exe/Github_repo_test"
OP_REF_GITHUB_TOKEN="op://VSCode/hardware_exe/Github_token"
GITHUB_TOKEN=""
MAXMIND_DB_PATH="${MAXMIND_DB_PATH:-}"
RELEASE_ROOT="$SCRIPT_DIR/release/linux"
TMP_CONFIG_CREATED=0

usage() {
  cat <<'EOF'
Usage: build_all_linux.sh [options]

Options:
  --codes CODE1,CODE2    Comma-separated list of miner codes to build (default: all)
  --version VERSION      Version string to embed (default: 5.5.2)
  --version-check-sec N  Update interval for profile generation (default: 600)
  --interval-sec N       Interval seconds embedded in encrypted config (default: 600)
  --software-uptodate 0|1   Embed software_uptodate flag (default: 1)
  --tls-ca-file PATH     Bundle an additional CA file with the service
  --maxmind-db PATH      Override GeoLite2 database path (default: env MAXMIND_DB_PATH or repo copy)
  --op-api-base REF      1Password reference for API base URL
  --op-signing-key REF   1Password reference for signing key (optional)
  --op-update-repo REF   1Password reference for update repo (optional)
  --op-github-token REF  1Password reference for GitHub token (optional)
  --github-token TOKEN   Plain GitHub token (fallback when --no-1password or 1P ref missing)
  --no-1password         Disable 1Password integration / encrypted config embedding
  --no-github            Do not embed GitHub token or mark update usage
  --release-dir PATH     Directory to place final artifacts (default: release/linux)
  --help                 Show this help message
EOF
}

# ---------- Utilities ----------
log() { printf '>>> %s\n' "$*" >&2; }
err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || err "Required command not found on PATH: $cmd"
}

resolve_path() {
  "$PYTHON_BIN" -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$1"
}

ensure_images_assets() {
  local img_dir="$SCRIPT_DIR/images"
  mkdir -p "$img_dir"
  for name in background.png frynetworks_logo.png FryNetworks_logo.png; do
    if [[ -f "$SCRIPT_DIR/$name" ]]; then
      cp -f "$SCRIPT_DIR/$name" "$img_dir/$name"
    fi
  done
  if [[ -f "$img_dir/background.png" ]]; then
    "$PYTHON_BIN" - "$img_dir/background.png" "$img_dir/background.jpg" <<'PY'
from PIL import Image
import sys
Image.open(sys.argv[1]).convert("RGB").save(sys.argv[2], quality=90)
PY
  fi
}

icon_base_for_code() {
  local code="${1^^}"
  case "$code" in
    BM) echo "BM" ;;
    IDM|ODM) echo "DB" ;;
    ISM|OSM) echo "GNSS" ;;
    RDN|SVN|SDN|AEM) echo "NODE" ;;
    IRM) echo "RAD" ;;
    *) echo "frynetworks_logo" ;;
  esac
}

convert_icon_if_needed() {
  local base="$1"
  local img_dir="$SCRIPT_DIR/images"
  local ico="$img_dir/${base}.ico"
  [[ -f "$ico" ]] && { echo "$ico"; return; }
  local src=""
  if [[ -f "$img_dir/${base}.png" ]]; then
    src="$img_dir/${base}.png"
  elif [[ -f "$img_dir/${base}.jpg" ]]; then
    src="$img_dir/${base}.jpg"
  fi
  if [[ -n "$src" ]]; then
    "$PYTHON_BIN" - "$src" "$ico" <<'PY'
from PIL import Image
import sys
Image.open(sys.argv[1]).save(sys.argv[2], format="ICO",
                             sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
PY
    [[ -f "$ico" ]] && { echo "$ico"; return; }
  fi
  echo ""
}

ensure_png_icon() {
  local base="$1"
  local img_dir="$SCRIPT_DIR/images"
  local png="$img_dir/${base}.png"
  [[ -f "$png" ]] && { echo "$png"; return; }

  local src=""
  if [[ -f "$img_dir/${base}.ico" ]]; then
    src="$img_dir/${base}.ico"
  elif [[ -f "$img_dir/${base}.jpg" ]]; then
    src="$img_dir/${base}.jpg"
  fi

  if [[ -n "$src" ]]; then
    "$PYTHON_BIN" - "$src" "$png" <<'PY'
from PIL import Image
import sys
Image.open(sys.argv[1]).save(sys.argv[2], format="PNG")
PY
    [[ -f "$png" ]] && { echo "$png"; return; }
  fi

  echo ""
}

create_desktop_files() {
  local code="$1"
  local version="$2"
  local gui_output="$3"
  local svc_output="$4"
  local icon_path="$5"
  
  local release_dir="${RELEASE_DIR:-$SCRIPT_DIR/release/linux}"
  local desktop_dir="$release_dir/desktop"
  mkdir -p "$desktop_dir"
  
  # Create desktop file for GUI application
  local gui_name="miner-control_${code}_v${version}"
  local gui_desktop="$desktop_dir/${gui_name}.desktop"
  
  cat > "$gui_desktop" <<EOF
[Desktop Entry]
Name=Fry Networks Miner Control (${code^^})
Comment=Fry Networks Hardware Miner Control Interface
Exec=$gui_output
Icon=${icon_path:-frynetworks-logo}
Terminal=false
Type=Application
Categories=Network;Utility;
StartupNotify=true
EOF

  # Create desktop file for service (for manual launching)  
  local svc_name="miner-online-10min_${code}_v${version}"
  local svc_desktop="$desktop_dir/${svc_name}.desktop"
  
  cat > "$svc_desktop" <<EOF
[Desktop Entry]
Name=Fry Networks Miner Service (${code^^})
Comment=Fry Networks Hardware Miner Background Service
Exec=$svc_output
Icon=${icon_path:-frynetworks-logo}
Terminal=true
Type=Application
Categories=Network;System;
StartupNotify=false
NoDisplay=true
EOF
  
  log "Created desktop files: $gui_desktop, $svc_desktop"
  
  # Also copy icon to a standard location if it exists
  if [[ -n "$icon_path" && -f "$icon_path" ]]; then
    local icon_name="frynetworks-${code,,}"
    local icon_ext="${icon_path##*.}"
    cp "$icon_path" "$desktop_dir/${icon_name}.${icon_ext}"
    log "Copied icon to desktop directory: ${icon_name}.${icon_ext}"
  fi
}

write_desktop_entry() {
  local path="$1"
  local name="$2"
  local exec_cmd="$3"
  local icon_name="$4"
  local workdir="$5"
  cat >"$path" <<EOF
[Desktop Entry]
Type=Application
Name=$name
Exec=$exec_cmd
Icon=$icon_name
Path=$workdir
Terminal=false
Categories=Utility;
StartupNotify=false
EOF
}

write_launcher_script() {
  local path="$1"
  local binary="$2"
  cat >"$path" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$here/%%BINARY%%" "$@"
EOF
  sed -i "s|%%BINARY%%|$binary|g" "$path"
  chmod 755 "$path"
}

mark_desktop_trusted() {
  local desktop="$1"
  if command -v gio >/dev/null 2>&1; then
    gio set -t string "$desktop" metadata::trusted true 2>/dev/null || true
  fi
}

# ---------- Argument parsing ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --codes)
      shift || err "--codes requires an argument"
      IFS=',' read -r -a CODES <<<"${1// /}"
      ;;
    --version)
      shift || err "--version requires an argument"
      VERSION="$1"
      ;;
    --version-check-sec)
      shift || err "--version-check-sec requires an argument"
      VERSION_CHECK_SEC="$1"
      ;;
    --interval-sec)
      shift || err "--interval-sec requires an argument"
      INTERVAL_SECONDS="$1"
      ;;
    --software-uptodate)
      shift || err "--software-uptodate requires an argument"
      SOFTWARE_UPTODATE="$1"
      ;;
    --tls-ca-file)
      shift || err "--tls-ca-file requires an argument"
      TLS_CA_FILE="$1"
      ;;
    --maxmind-db)
      shift || err "--maxmind-db requires an argument"
      MAXMIND_DB_PATH="$1"
      ;;
    --op-api-base)
      shift || err "--op-api-base requires an argument"
      OP_REF_API_BASE_URL="$1"
      ;;
    --op-signing-key)
      shift || err "--op-signing-key requires an argument"
      OP_REF_SIGNING_KEY="$1"
      ;;
    --op-update-repo)
      shift || err "--op-update-repo requires an argument"
      OP_REF_UPDATE_REPO="$1"
      ;;
    --op-github-token)
      shift || err "--op-github-token requires an argument"
      OP_REF_GITHUB_TOKEN="$1"
      ;;
    --github-token)
      shift || err "--github-token requires an argument"
      GITHUB_TOKEN="$1"
      ;;
    --no-1password)
      USE_1PASSWORD=0
      ;;
    --no-github)
      USE_GITHUB=0
      ;;
    --release-dir)
      shift || err "--release-dir requires an argument"
      RELEASE_ROOT="$1"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      err "Unknown option: $1"
      ;;
  esac
  shift
done

[[ ${#CODES[@]} -gt 0 ]] || err "At least one code must be specified"

PYTHON_BIN="${PYTHON_BIN:-python3}"

require_cmd "$PYTHON_BIN"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib h3 pillow shapely geoip2

ensure_images_assets

if (( USE_1PASSWORD )); then
  require_cmd op
fi

mkdir -p "$RELEASE_ROOT"

# ---------- Helper for encrypted config patch ----------
patch_config_with_secret() {
  local api_base="$1"
  local bearer_token="$2"
  local interval="$3"
  local use_github="$4"
  local github_token="$5"
  local software_uptodate="$6"
  local tls_basename="$7"
  local signing_key="$8"
  local update_repo="$9"
  local tmp_cfg="$SCRIPT_DIR/_tmp_config.json"

  local py_env=(
    API_BASE_URL="$api_base"
    BEARER_TOKEN="$bearer_token"
    INTERVAL_SECONDS="$interval"
    USE_GITHUB="$use_github"
    SOFTWARE_UPTODATE="$software_uptodate"
    GITHUB_TOKEN_VALUE="$github_token"
    TLS_BASENAME="$tls_basename"
    SIGNING_KEY="$signing_key"
    UPDATE_REPO="$update_repo"
    OUTPUT_PATH="$tmp_cfg"
  )

  env "${py_env[@]}" "$PYTHON_BIN" - <<'PY'
import json, os, sys

cfg = {
    "external_api": {
        "base_url": os.environ["API_BASE_URL"],
        "timeout": 10.0
    },
    "interval_seconds": int(os.environ["INTERVAL_SECONDS"]),
    "use_github": os.environ["USE_GITHUB"] == "1",
    "software_uptodate": os.environ["SOFTWARE_UPTODATE"] == "1",
}

bearer_token = os.environ.get("BEARER_TOKEN", "").strip()
if bearer_token:
    cfg["external_api"]["bearer_token"] = bearer_token

github_token = os.environ.get("GITHUB_TOKEN_VALUE", "")
if cfg["use_github"]:
    if not github_token:
        raise SystemExit("GitHub token required when use_github=1")
    cfg["github_token"] = github_token
if os.environ.get("TLS_BASENAME"):
    cfg["tlsCAFile"] = os.environ["TLS_BASENAME"]
if os.environ.get("SIGNING_KEY"):
    sk = os.environ["SIGNING_KEY"].strip()
    if len(sk) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sk):
        raise SystemExit("Signing key must be 64 hex chars")
    cfg["local_signing_key_hex"] = sk
if os.environ.get("UPDATE_REPO"):
    cfg["update_repo"] = os.environ["UPDATE_REPO"].strip()

with open(os.environ["OUTPUT_PATH"], "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, separators=(",", ":"))
PY

  local enc_output
  enc_output="$("$PYTHON_BIN" tools/make_encrypted_config.py --in "$tmp_cfg" --json)"
  env ENC_JSON="$enc_output" "$PYTHON_BIN" - <<'PY'
import json, os, pathlib, sys

data = json.loads(os.environ["ENC_JSON"])
marker = "dlt=b''; dlp=b''; knt=b''; knp=b''"
src = pathlib.Path("miner_online_simple.py")
backup = src.with_suffix(".py.bak")
backup.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

text = src.read_text(encoding="utf-8")
if marker not in text:
    raise SystemExit("Placeholder for encrypted config not found in miner_online_simple.py")
replacement = f"dlt={data['dlt']}; dlp={data['dlp']}; knt={data['knt']}; knp={data['knp']}"
src.write_text(text.replace(marker, replacement, 1), encoding="utf-8")
PY
  TMP_CONFIG_CREATED=1
}

restore_config_if_needed() {
  local backup="$SCRIPT_DIR/miner_online_simple.py.bak"
  if [[ -f "$backup" ]]; then
    mv -f "$backup" "$SCRIPT_DIR/miner_online_simple.py"
  fi
  if (( TMP_CONFIG_CREATED )); then
    rm -f "$SCRIPT_DIR/_tmp_config.json"
    TMP_CONFIG_CREATED=0
  fi
}

trap restore_config_if_needed EXIT

# ---------- Build loop ----------
for CODE in "${CODES[@]}"; do
  log "Building ${CODE} v${VERSION}"
  "$PYTHON_BIN" tools/make_profile.py --code "$CODE" --version "$VERSION" --version-check-sec "$VERSION_CHECK_SEC"

  GUI_NAME="miner-control_${CODE}_v${VERSION}"
  gui_dist_dir="$SCRIPT_DIR/dist/linux/gui/$CODE"
  mkdir -p "$gui_dist_dir"
  gui_args=(
    --clean
    --onefile
    --noconsole
    --noconfirm
    --name "$GUI_NAME"
    --hidden-import PySide6.QtNetwork
    --hidden-import miner_GUI.LiveData
    --add-data "$SCRIPT_DIR/images:images"
    --distpath "$gui_dist_dir"
  )

  if [[ -f "$SCRIPT_DIR/qt.conf" ]]; then
    gui_args+=(--add-data "$SCRIPT_DIR/qt.conf:.")
  fi

  # Note: PyInstaller on Linux doesn't support embedded icons like Windows/macOS
  # Icons are handled via desktop files, but we'll try anyway for completeness
  if [[ -n "$icon_path" ]]; then
    gui_args+=(--icon "$icon_path")
    log "Attempting to add icon: $icon_path (may be ignored on Linux)"
  else
    icon_png_path="$(ensure_png_icon "$icon_base")"
    if [[ -n "$icon_png_path" ]]; then
      gui_args+=(--icon "$icon_png_path")
      log "Attempting to add icon: $icon_png_path (may be ignored on Linux)"
    fi
  fi

  qif="$("$PYTHON_BIN" -c 'import os, PySide6; print(os.path.join(os.path.dirname(PySide6.__file__), "plugins", "imageformats"))' 2>/dev/null || true)"
  plugin_paths=()
  if [[ -n "$qif" && -d "$qif" ]]; then
    while IFS= read -r path; do
      plugin_paths+=("$path")
    done < <(
      for base in qjpeg qpng qico qsvg; do
        for candidate in "$qif/${base}.dll" "$qif/lib${base}.so"; do
          if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            break
          fi
        done
      done
    )
  fi
  if (( ${#plugin_paths[@]} > 0 )); then
    for plugin_path in "${plugin_paths[@]}"; do
      gui_args+=(--add-data "$plugin_path:PySide6/plugins/imageformats")
    done
  else
    gui_args+=(--collect-all PySide6 --collect-all miner_GUI.LiveData)
  fi

  excludes=(--exclude-module pymongo)
  case "${CODE^^}" in
    BM|AEM)
      excludes+=(--exclude-module sounddevice --exclude-module serial)
      ;;
    IDM|ODM)
      excludes+=(--exclude-module serial)
      ;;
    ISM|OSM)
      excludes+=(--exclude-module sounddevice)
      ;;
    SVN|SDN|RDN)
      excludes+=(--exclude-module sounddevice --exclude-module serial --exclude-module matplotlib --exclude-module numpy)
      ;;
  esac
  gui_args+=("${excludes[@]}")

  "$PYTHON_BIN" -m PyInstaller "${gui_args[@]}" "$SCRIPT_DIR/miner_control.py"

  gui_output="$gui_dist_dir/$GUI_NAME"
  [[ -f "$gui_output" ]] || err "GUI build failed for $CODE"

  chmod +x "$gui_output"

  target_dir="$RELEASE_ROOT/$CODE"
  mkdir -p "$target_dir"
  cp -f "$gui_output" "$target_dir/"

  icon_release_path=""
  if [[ -n "$icon_png_path" ]]; then
    icon_release_path="$target_dir/${CODE}.png"
    cp -f "$icon_png_path" "$icon_release_path"
    icon_release_path="$(resolve_path "$icon_release_path")"
  fi

  desktop_path="$target_dir/${GUI_NAME}.desktop"
  launcher_path="$target_dir/${GUI_NAME}.sh"
  write_launcher_script "$launcher_path" "$GUI_NAME"
  desktop_exec="$launcher_path"

  icon_field="$icon_release_path"
  if [[ -z "$icon_field" && -n "$icon_png_path" ]]; then
    icon_field="$(resolve_path "$icon_png_path")"
  fi
  if [[ -z "$icon_field" && -n "$icon_path" ]]; then
    icon_field="$(resolve_path "$icon_path")"
  fi

  write_desktop_entry "$desktop_path" "Fry Networks ${CODE} Control" "$desktop_exec" "$icon_field" "$(resolve_path "$target_dir")"
  chmod 755 "$desktop_path"
  mark_desktop_trusted "$desktop_path"

  log "Artifacts ready under $target_dir"
done

restore_config_if_needed
log "All Linux builds complete."
