
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DEPS=false
CODE=""
VER=""

# Simple CLI: optional --install-deps before positional CODE VERSION
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-deps)
      INSTALL_DEPS=true; shift ;;
    --help|-h)
      echo "Usage: $0 [--install-deps] CODE VERSION"; exit 0 ;;
    *)
      if [[ -z "$CODE" ]]; then CODE="$1"; elif [[ -z "$VER" ]]; then VER="$1"; else echo "Unexpected argument: $1"; exit 2; fi; shift ;;
  esac
done

if [[ -z "$CODE" ]] || [[ -z "$VER" ]]; then
  echo "Usage: $0 [--install-deps] CODE VERSION"; exit 2
fi

# export variables for older parts of the script
export CODE VER

python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib h3 pillow shapely geoip2

# Attempt to run make_profile if present (matches Windows builder behavior)
if [[ -f "tools/make_profile.py" ]]; then
  python3 tools/make_profile.py --code "$CODE" --version "$VER" --version-check-sec 600 || true
else
  echo "Warning: tools/make_profile.py not found; skipping profile generation step."
fi

GUI_NAME="FRY_${CODE}_v${VER}"

# ---------- Metadata mapping (mirror build_windows.ps1) ----------
declare -A META_PRODUCT
declare -A META_DESC
META_PRODUCT[BM]="Fry Networks Bandwidth Miner"
META_DESC[BM]="Fry Networks Bandwidth Miner"
META_PRODUCT[IDM]="Fry Networks Indoor Decibel Miner"
META_DESC[IDM]="Fry Networks Indoor Decibel Miner"
META_PRODUCT[ODM]="Fry Networks Outdoor Decibel Miner"
META_DESC[ODM]="Fry Networks Outdoor Decibel Miner"
META_PRODUCT[ISM]="Fry Networks Indoor Satellite Miner"
META_DESC[ISM]="Fry Networks Indoor Satellite Miner"
META_PRODUCT[OSM]="Fry Networks Outdoor Satellite Miner"
META_DESC[OSM]="Fry Networks Outdoor Satellite Miner"
META_PRODUCT[RDN]="Fry Networks Reward Decentralization Node"
META_DESC[RDN]="Fry Networks Reward Decentralization Node"
META_PRODUCT[SDN]="Fry Networks Storage Decentralization Node"
META_DESC[SDN]="Fry Networks Storage Decentralization Node"
META_PRODUCT[SVN]="Fry Networks Storage Validator Node"
META_DESC[SVN]="Fry Networks Storage Validator Node"
META_PRODUCT[AEM]="Fry Networks AI Edge Miner"
META_DESC[AEM]="Fry Networks AI Edge Miner"
META_PRODUCT[IRM]="Fry Networks Radiation Miner"
META_DESC[IRM]="Fry Networks Radiation Miner"

COMPANY_NAME="Fry Networks LLC"
UPPER_CODE="${CODE^^}"
PRODUCT_NAME="${META_PRODUCT[$UPPER_CODE]:-Fry Networks $CODE}"
FILE_DESC="${META_DESC[$UPPER_CODE]:-Fry Networks component $CODE.}"


# ---------- Version file writer for PyInstaller (--version-file) ----------
new_version_file() {
  local path="$1"; shift
  local companyName="$1"; shift
  local productName="$1"; shift
  local fileDescription="$1"; shift
  local fileVersion="$1"; shift
  local internalName="$1"; shift
  local originalFilename="$1"; shift

  # Convert semantic version "5.3.0" to "5, 3, 0, 0"
  IFS='.' read -r -a parts <<< "$fileVersion"
  for i in {0..3}; do
    if [[ -z "${parts[i]:-}" ]]; then parts[i]=0; fi
  done
  verTuple="${parts[0]}, ${parts[1]}, ${parts[2]}, ${parts[3]}"

  cat > "$path" <<EOF
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($verTuple),
    prodvers=($verTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'$companyName'),
            StringStruct(u'FileDescription', u'$fileDescription'),
            StringStruct(u'FileVersion', u'$fileVersion'),
            StringStruct(u'InternalName', u'$internalName'),
            StringStruct(u'OriginalFilename', u'$originalFilename'),
            StringStruct(u'ProductName', u'$productName'),
            StringStruct(u'ProductVersion', u'$fileVersion'),
            StringStruct(u'LegalCopyright', u'© $(date +%Y) $companyName')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
EOF
}


# ---------- Locate PyInstaller plugin directory for PySide6 imageformats ----------
qif=""
qif=$(python3 - <<PY - 2>/dev/null
import os
try:
    import PySide6
    print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins', 'imageformats'))
except Exception:
    pass
PY
)

have_plugins=false
if [[ -n "$qif" ]] && [[ -d "$qif" ]]; then
  # look for known plugin files; on Linux these may be .so but keep same checks as windows builder
  if [[ -f "$qif/qjpeg.dll" ]] || [[ -f "$qif/qjpeg.so" ]] || [[ -f "$qif/qjpeg" ]]; then
    have_plugins=true
  fi
fi

# ---------- Build arguments (mirror Windows builder) ----------
guiDistDir="$PWD/dist/gui/${CODE}"
mkdir -p "$guiDistDir"

guiArgs=(--clean --onefile --noconsole --noconfirm --name "$GUI_NAME" --hidden-import PySide6.QtNetwork --add-data "images:images" --distpath "$guiDistDir")

# Simplified GUI: Include only history/chart modules (health, themes, responsive removed)
hidden=(
  ui.widgets.charts
  miner_GUI.ui.widgets.charts
)
for h in "${hidden[@]}"; do
  if python3 -c "import importlib; importlib.import_module('$h')" >/dev/null 2>&1; then
    guiArgs+=(--hidden-import "$h")
  else
    echo "Note: hidden import '$h' not importable in this environment; skipping."
  fi
done

# Ensure matplotlib runtime data and common backends are bundled for connectivity charts
guiArgs+=(--collect-data matplotlib --hidden-import matplotlib.backends.backend_qtagg --hidden-import matplotlib.backends.backend_qt5agg --hidden-import matplotlib.backends.backend_agg --hidden-import matplotlib.backends.backend_tkagg)

# Attach icon if present (reuse previous logic)
ICON_BASE=""
case "$UPPER_CODE" in
  BM) ICON_BASE="BM" ;;
  IDM|ODM) ICON_BASE="DB" ;;
  ISM|OSM) ICON_BASE="GNSS" ;;
  RDN|SVN|SDNCMSC) ICON_BASE="NODE" ;;
  AEM) ICON_BASE="AEM" ;;
  IRM) ICON_BASE="RAD" ;;
  *) ICON_BASE="frynetworks_logo" ;;
esac
if [[ -f "images/${ICON_BASE}.ico" ]]; then
  guiArgs+=(--icon "images/${ICON_BASE}.ico")
elif [[ -f "images/${ICON_BASE}.png" ]]; then
  guiArgs+=(--icon "images/${ICON_BASE}.png")
fi

if [[ "$have_plugins" == true ]]; then
  # add plugin files that exist
  plugins=(qjpeg.dll qpng.dll qico.dll qsvg.dll)
  added=false
  for pl in "${plugins[@]}"; do
    candidate="$qif/$pl"
    if [[ -f "$candidate" ]]; then
      guiArgs+=(--hidden-import miner_GUI.LiveData --add-data "$candidate:PySide6/plugins/imageformats")
      added=true
    fi
  done
  if [[ "$added" == false ]]; then
    guiArgs+=(--collect-all PySide6 --collect-all miner_GUI.LiveData)
  fi
else
  guiArgs+=(--collect-all PySide6 --collect-all miner_GUI.LiveData)
fi

# Exclude modules per Code (matching Windows excludes)
excludes=(--exclude-module pymongo)
case "$UPPER_CODE" in
  BM) excludes+=(--exclude-module sounddevice --exclude-module serial) ;;
  AEM) excludes+=(--exclude-module sounddevice --exclude-module serial) ;;
  IDM) excludes+=(--exclude-module serial) ;;
  ODM) excludes+=(--exclude-module serial) ;;
  ISM) excludes+=(--exclude-module sounddevice) ;;
  OSM) excludes+=(--exclude-module sounddevice) ;;
  SVN) excludes+=(--exclude-module sounddevice --exclude-module serial --exclude-module matplotlib --exclude-module numpy) ;;
  SDN) excludes+=(--exclude-module sounddevice --exclude-module serial --exclude-module matplotlib --exclude-module numpy) ;;
  RDN) excludes+=(--exclude-module sounddevice --exclude-module serial --exclude-module matplotlib --exclude-module numpy) ;;
esac
for e in "${excludes[@]}"; do guiArgs+=($e); done

# Create version file and add to args
guiVerFile="$PWD/_tmp_version_gui_${CODE}.txt"
new_version_file "$guiVerFile" "$COMPANY_NAME" "$PRODUCT_NAME" "$FILE_DESC" "$VER" "$GUI_NAME" "${GUI_NAME}.exe"
guiArgs+=(--version-file "$guiVerFile")

echo "Running PyInstaller with: ${guiArgs[*]}"

## Pre-check: common Qt/system shared libraries that, if missing, trigger many PyInstaller warnings
check_shared_libs() {
  local missing=()
  local libs=(libxcb-cursor.so.0 libtiff.so.5 libX11.so.6 libxcb.so.1)
  for lib in "${libs[@]}"; do
    if ! ldconfig -p 2>/dev/null | grep -q "$lib"; then
      missing+=("$lib")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "\nWarning: the build host is missing some system libraries required by Qt/PySide6:" >&2
    for m in "${missing[@]}"; do echo "  - $m" >&2; done
    echo "\nTo reduce PyInstaller warnings and produce a more complete bundled runtime, install the system Qt and X11 libraries." >&2
    echo "On Debian/Ubuntu you can run (example):" >&2
    echo "  sudo apt-get install -y libxcb1 libxcb-cursor0 libtiff5 libx11-6 libx11-dev qt6-base-dev" >&2
    echo "On Fedora/CentOS you can run (example):" >&2
    echo "  sudo dnf install -y libxcb libtiff libX11 qt6-qtbase-devel" >&2
    echo "If you cannot install system packages on this host, you can still build — the warnings are non-fatal, but the target system must provide these libraries at runtime." >&2
  fi
}

check_shared_libs

if [[ "$INSTALL_DEPS" == true ]]; then
  echo "--install-deps specified: attempting to install system packages. This requires sudo."
  if command -v apt-get >/dev/null 2>&1; then
    SUDO_CMD="sudo"
    echo "Detected apt-get: attempting apt install of Qt/X11 libs (Debian/Ubuntu)."
    echo "Running: sudo apt-get update && sudo apt-get install -y libxcb1 libxcb-cursor0 libtiff5 libx11-6 libx11-dev qt6-base-dev"
    if $SUDO_CMD apt-get update && $SUDO_CMD apt-get install -y libxcb1 libxcb-cursor0 libtiff5 libx11-6 libx11-dev qt6-base-dev; then
      echo "System packages installed (apt)."
    else
      echo "Failed to install packages via apt-get. You may need to run the commands manually as root." >&2
    fi
  elif command -v dnf >/dev/null 2>&1; then
    SUDO_CMD="sudo"
    echo "Detected dnf: attempting dnf install of Qt/X11 libs (Fedora/CentOS)."
    echo "Running: sudo dnf install -y libxcb libtiff libX11 qt6-qtbase-devel"
    if $SUDO_CMD dnf install -y libxcb libtiff libX11 qt6-qtbase-devel; then
      echo "System packages installed (dnf)."
    else
      echo "Failed to install packages via dnf. You may need to run the commands manually as root." >&2
    fi
  else
    echo "Unsupported package manager. Please install the following packages manually:" >&2
    echo "  Debian/Ubuntu: sudo apt-get install -y libxcb1 libxcb-cursor0 libtiff5 libx11-6 libx11-dev qt6-base-dev" >&2
    echo "  Fedora: sudo dnf install -y libxcb libtiff libX11 qt6-qtbase-devel" >&2
  fi
fi

python3 -m PyInstaller "${guiArgs[@]}" main.py

# Move output to release folder
out_dir="$PWD/release/$CODE"
mkdir -p "$out_dir"
built="$guiDistDir/$GUI_NAME"
if [[ -f "$built" ]] || [[ -f "$built.exe" ]]; then
  if [[ -f "$built.exe" ]]; then
    mv -f "$built.exe" "$out_dir/${GUI_NAME}.exe"
  else
    mv -f "$built" "$out_dir/${GUI_NAME}"
  fi
fi

# Clean up version file
rm -f "$guiVerFile" || true

echo "Build complete for $CODE v$VER"

