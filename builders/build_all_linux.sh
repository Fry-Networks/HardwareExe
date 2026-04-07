#!/usr/bin/env bash
set -euo pipefail

# Build PyInstaller onefile binaries for Linux, modeled on builders/build_all_windows.ps1.
# Default set omits AEM (Olostep browser dependency is Windows-only).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ---------- Defaults ----------
read -r -a DEFAULT_CODES <<<"BM IDM ODM ISM OSM SVN SDN RDN IRM"
CODES=("${DEFAULT_CODES[@]}")
VERSION="6.1.2"
VERSION_CHECK_SEC=600
PYTHON_BIN="${PYTHON_BIN:-python3}"
RELEASE_ROOT="$REPO_ROOT/release/linux"
SKIP_PIP=0

usage() {
  cat <<'EOF'
Usage: build_all_linux.sh [options]

Options:
  --codes LIST        Comma-separated miner codes to build (default: BM,IDM,ODM,ISM,OSM,SVN,SDN,RDN,IRM)
  --version STR       Version string to embed in names and config_profile.py (default: 6.1.2)
  --version-check-sec N  Interval for update checks in config_profile.py (default: 600)
  --python PATH       Python interpreter to use (default: python3 or $PYTHON_BIN env)
  --release-dir PATH  Output root for artifacts (default: release/linux)
  --skip-pip          Skip pip install/upgrade step
  --help              Show this help
EOF
}

log() { printf '>>> %s\n' "$*" >&2; }
err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || err "Required command not found on PATH: $cmd"
}

icon_base_for_code() {
  local code="${1^^}"
  case "$code" in
    BM) echo "BM" ;;
    IDM|ODM) echo "DB" ;;
    ISM|OSM) echo "GNSS" ;;
    RDN|SVN|SDN) echo "NODE" ;;
    AEM) echo "AEM" ;;
    IRM) echo "RAD" ;;
    *) echo "frynetworks_logo" ;;
  esac
}

find_icon_path() {
  local base="$1"
  for ext in png ico jpg; do
    local candidate="$REPO_ROOT/images/${base}.${ext}"
    [[ -f "$candidate" ]] && { echo "$candidate"; return; }
  done
  echo ""
}

qt_image_plugins() {
  "$PYTHON_BIN" - <<'PY'
import PySide6, pathlib
roots = [
    pathlib.Path(PySide6.__file__).parent / "plugins" / "imageformats",
    pathlib.Path(PySide6.__file__).parent / "Qt" / "plugins" / "imageformats",
]
seen = set()
for p in roots:
    if not p.is_dir():
        continue
    for base in ("qjpeg", "qpng", "qico", "qsvg"):
        for name in (f"{base}.dll", f"{base}.so", f"lib{base}.so"):
            cand = p / name
            if cand.exists() and cand not in seen:
                seen.add(cand)
                print(cand)
                break
PY
}

# ---------- Args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --codes)
      shift || err "--codes requires a value"
      IFS=',' read -r -a CODES <<<"${1// /}"
      ;;
    --version)
      shift || err "--version requires a value"
      VERSION="$1"
      ;;
    --version-check-sec)
      shift || err "--version-check-sec requires a value"
      VERSION_CHECK_SEC="$1"
      ;;
    --python)
      shift || err "--python requires a value"
      PYTHON_BIN="$1"
      ;;
    --release-dir)
      shift || err "--release-dir requires a value"
      RELEASE_ROOT="$1"
      ;;
    --skip-pip)
      SKIP_PIP=1
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

(( ${#CODES[@]} )) || err "At least one miner code must be specified"
require_cmd "$PYTHON_BIN"

if (( ! SKIP_PIP )); then
  log "Upgrading pip and required Python packages"
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib h3 pillow shapely geoip2
fi

mkdir -p "$RELEASE_ROOT"

# ---------- Build loop ----------
for CODE in "${CODES[@]}"; do
  CODE_UP="${CODE^^}"
  if [[ "$CODE_UP" == "AEM" ]]; then
    log "Skipping AEM (Olostep browser dependency is Windows-only)"
    continue
  fi

  log "Building ${CODE_UP} v${VERSION}"

  "$PYTHON_BIN" "$REPO_ROOT/miner_GUI/tools/make_profile.py" \
    --code "$CODE_UP" \
    --version "$VERSION" \
    --version-check-sec "$VERSION_CHECK_SEC" \
    --out "$REPO_ROOT/config_profile.py"

  gui_name="FRY_${CODE_UP}_v${VERSION}"
  gui_dist_dir="$REPO_ROOT/dist/linux/gui/$CODE_UP"
  mkdir -p "$gui_dist_dir"

  icon_base="$(icon_base_for_code "$CODE_UP")"
  icon_path="$(find_icon_path "$icon_base")"

  gui_args=(
    --clean
    --onefile
    --noconsole
    --noconfirm
    --name "$gui_name"
    --hidden-import PySide6.QtNetwork
    --hidden-import miner_GUI.ui.widgets.charts
    --hidden-import matplotlib.backends.backend_qtagg
    --hidden-import matplotlib.backends.backend_qt5agg
    --collect-data matplotlib
    --add-data "$REPO_ROOT/images:images"
    --distpath "$gui_dist_dir"
  )

  [[ -f "$REPO_ROOT/qt.conf" ]] && gui_args+=(--add-data "$REPO_ROOT/qt.conf:.")
  [[ -n "$icon_path" ]] && gui_args+=(--icon "$icon_path")

  mapfile -t plugins < <(qt_image_plugins || true)
  if (( ${#plugins[@]} )); then
    for pl in "${plugins[@]}"; do
      gui_args+=(--add-data "$pl:PySide6/plugins/imageformats")
    done
  else
    gui_args+=(--collect-all PySide6 --collect-all miner_GUI.LiveData)
  fi

  excludes=(--exclude-module pymongo)
  case "$CODE_UP" in
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

  "$PYTHON_BIN" -m PyInstaller "${gui_args[@]}" "$REPO_ROOT/main.py"

  gui_output="$gui_dist_dir/$gui_name"
  [[ -f "$gui_output" ]] || err "PyInstaller output not found for $CODE_UP"
  chmod +x "$gui_output"

  out_dir="$RELEASE_ROOT/$VERSION"
  mkdir -p "$out_dir"
  cp -f "$gui_output" "$out_dir/"
  [[ -n "$icon_path" ]] && cp -f "$icon_path" "$out_dir/"

  log "Created $out_dir/$(basename "$gui_output")"
done

log "All Linux builds complete."
