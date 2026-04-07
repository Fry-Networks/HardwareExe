#!/usr/bin/env bash
# Fry Networks Miner Installer for Linux
# Installs binaries, desktop files, icons, and sets up system integration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_PREFIX="${INSTALL_PREFIX:-$HOME/.local}"
SYSTEM_INSTALL="${SYSTEM_INSTALL:-false}"
DRY_RUN="${DRY_RUN:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation paths
if [[ "$SYSTEM_INSTALL" == "true" ]]; then
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor"
    REQUIRES_SUDO=true
else
    BIN_DIR="$INSTALL_PREFIX/bin"
    DESKTOP_DIR="$INSTALL_PREFIX/share/applications"
    ICON_DIR="$INSTALL_PREFIX/share/icons/hicolor"
    REQUIRES_SUDO=false
fi

# Logging functions
log() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
debug() { echo -e "${BLUE}[DEBUG]${NC} $*" >&2; }

# Dry run wrapper
run_cmd() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY-RUN]${NC} $*"
    else
        "$@"
    fi
}

# Sudo wrapper
maybe_sudo() {
    if [[ "$REQUIRES_SUDO" == "true" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            echo -e "${BLUE}[DRY-RUN]${NC} sudo $*"
        else
            sudo "$@"
        fi
    else
        run_cmd "$@"
    fi
}

show_usage() {
    cat <<EOF
Fry Networks Miner Installer

USAGE:
    $0 [OPTIONS] [CODE]

OPTIONS:
    --system              Install system-wide (requires sudo)
    --user               Install for current user only (default)
    --dry-run            Show what would be done without executing
    --uninstall          Remove installed files
    --list-installed     Show currently installed miners
    --prefix PATH        Custom installation prefix (default: ~/.local)
    --help               Show this help

CODES:
    BM                   Bandwidth Miner
    IDM                  Indoor Decibel Miner
    ODM                  Outdoor Decibel Miner
    ISM                  Indoor Satellite Miner
    OSM                  Outdoor Satellite Miner
    RDN                  Rewards Decentralization Node
    SVN                  Storage Validator Node
    SDN                  Storage Decentralization Node
    AEM                  AI Edge Miner
    IRM                  Indoor Radiation Miner
    all                  Install all available miners

EXAMPLES:
    $0 BM                # Install Bandwidth Miner for current user
    $0 --system BM       # Install Bandwidth Miner system-wide
    $0 --dry-run all     # Show what installing all miners would do
    $0 --uninstall BM    # Remove Bandwidth Miner installation

EOF
}

find_release_files() {
    local code="$1"
    local code="$1"
    # Try several common release locations (project LINUX/release, project/release, root release, dist)
    local candidates=(
        "$SCRIPT_DIR/release/linux/$code"
        "$SCRIPT_DIR/release/$code"
        "$(dirname "$SCRIPT_DIR")/release/$code"
        "$(dirname "$SCRIPT_DIR")/release/linux/$code"
        "$SCRIPT_DIR/../release/$code"
        "$SCRIPT_DIR/../release/linux/$code"
        "$SCRIPT_DIR/../dist/$code"
        "$SCRIPT_DIR/dist"
        "$SCRIPT_DIR/../dist"
        "$SCRIPT_DIR/../../release/$code"
        "$(pwd)/release/$code"
        "$(pwd)/release/linux/$code"
    )

    local release_dir=""
    for d in "${candidates[@]}"; do
        if [[ -d "$d" ]]; then
            release_dir="$d"
            break
        fi
    done

    if [[ -z "$release_dir" ]]; then
        error "Release directory not found in known locations. Checked: ${candidates[*]}"
        error "Run build script first or move your release into one of those paths."
        return 1
    fi

    # Find executables in the release dir. Prefer miner-control_* and miner-online* names.
    local gui_binary=""
    local svc_binary=""

    for file in "$release_dir"/*; do
        if [[ -f "$file" && -x "$file" ]]; then
            local basename="$(basename "$file")"
            if [[ -z "$gui_binary" && ( "$basename" == miner-control_* || "$basename" == *control* || "$basename" == FRY_* || "$basename" == *${code}_* || "$basename" == *${code}* ) ]]; then
                gui_binary="$file"
                continue
            fi
            if [[ -z "$svc_binary" && ( "$basename" == miner-online* || "$basename" == *online* ) ]]; then
                svc_binary="$file"
            fi
        fi
    done

    # If only one executable found, use it as GUI and skip service (service optional)
    if [[ -z "$gui_binary" ]]; then
        # try to pick the first executable
        for file in "$release_dir"/*; do
            if [[ -f "$file" && -x "$file" ]]; then
                gui_binary="$file"
                break
            fi
        done
    fi

    if [[ -z "$gui_binary" ]]; then
        error "No executable GUI binary found in $release_dir"
        return 1
    fi

    # Return the GUI binary path (service is maintained in a separate repository)
    echo "$gui_binary"
}

install_binary() {
    local src="$1"
    local name="$2"
    local dest="$BIN_DIR/$name"
    
    log "Installing binary: $name"
    maybe_sudo mkdir -p "$BIN_DIR"
    maybe_sudo cp "$src" "$dest"
    maybe_sudo chmod 755 "$dest"
    
    debug "Installed: $src -> $dest"
}

create_desktop_file() {
    local code="$1"
    local binary_name="$2"
    local app_type="$3"  # "gui" or "service"
    local version="$4"
    
    local desktop_file="$DESKTOP_DIR/frynetworks-${code,,}-${app_type}.desktop"
    
    # Determine application details based on code
    local app_name=""
    local app_comment=""
    local icon_name="frynetworks-${code,,}"
    
    case "${code^^}" in
        BM)
            app_name="Fry Networks Bandwidth Miner"
            app_comment="Network Bandwidth Mining and Monitoring"
            ;;
        IDM)
            app_name="Fry Networks Indoor Decibel Miner"
            app_comment="Indoor Audio Level Monitoring"
            ;;
        ODM)
            app_name="Fry Networks Outdoor Decibel Miner"
            app_comment="Outdoor Audio Level Monitoring"
            ;;
        ISM)
            app_name="Fry Networks Indoor Satellite Miner"
            app_comment="Indoor GNSS/Satellite Signal Analysis"
            ;;
        OSM)
            app_name="Fry Networks Outdoor Satellite Miner"
            app_comment="Outdoor GNSS/Satellite Signal Analysis"
            ;;
        RDN)
            app_name="Fry Networks Router Data Node"
            app_comment="Network Router Data Collection"
            ;;
        SVN)
            app_name="Fry Networks Satellite Vehicle Node"
            app_comment="Satellite Vehicle Data Processing"
            ;;
        SDN)
            app_name="Fry Networks Sensor Data Node"
            app_comment="Multi-Sensor Data Aggregation"
            ;;
        AEM)
            app_name="Fry Networks Atmospheric Environment Miner"
            app_comment="Environmental Data Collection"
            ;;
        IRM)
            app_name="Fry Networks Indoor Radiation Miner"
            app_comment="Indoor Radiation Level Monitoring"
            ;;
        *)
            app_name="Fry Networks ${code^^} Miner"
            app_comment="Fry Networks Hardware Mining Application"
            ;;
    esac
    
    if [[ "$app_type" == "gui" ]]; then
        app_name="$app_name Control"
        app_comment="$app_comment - Control Interface"
    else
        app_name="$app_name Service"
        app_comment="$app_comment - Background Service"
    fi
    
    log "Creating desktop file: $(basename "$desktop_file")"
    maybe_sudo mkdir -p "$DESKTOP_DIR"
    
    local terminal_setting="false"
    local categories="Network;Utility;"
    local no_display=""
    
    if [[ "$app_type" == "service" ]]; then
        terminal_setting="true"
        categories="Network;System;"
        no_display="NoDisplay=true"
    fi
    
    maybe_sudo tee "$desktop_file" > /dev/null <<EOF
[Desktop Entry]
Version=1.0
Name=$app_name
Comment=$app_comment
Exec=$BIN_DIR/$binary_name
Icon=$icon_name
Terminal=$terminal_setting
Type=Application
Categories=$categories
StartupNotify=true
$no_display
X-GNOME-UsesNotifications=true
Keywords=frynetworks;miner;${code,,};network;monitoring;
EOF
    
    maybe_sudo chmod 644 "$desktop_file"
    debug "Created: $desktop_file"
}

install_icon() {
    local code="$1"
    local size="$2"
    
    local icon_name="frynetworks-${code,,}"
    local src_icon=""
    
    # Find the appropriate icon file
    local icon_base=""
    case "${code^^}" in
        BM) icon_base="BM" ;;
        IDM|ODM) icon_base="DB" ;;
        ISM|OSM) icon_base="GNSS" ;;
        RDN|SVN|SDN|AEM) icon_base="NODE" ;;
        IRM) icon_base="RAD" ;;
        *) icon_base="frynetworks_logo" ;;
    esac

    # Search several likely image directories (LINUX/images, project root images, cwd images, parent images)
    local possible_img_dirs=(
        "$SCRIPT_DIR/images"
        "$(dirname \"$SCRIPT_DIR\")/images"
        "$(pwd)/images"
        "$(dirname \"$SCRIPT_DIR\")/../images"
        "$SCRIPT_DIR/../images"
        "$SCRIPT_DIR/../../images"
    )

    src_icon=""
    for img_dir in "${possible_img_dirs[@]}"; do
        # prefer exact-case PNG, then ICO, then lowercase png/ico
        if [[ -f "$img_dir/${icon_base}.png" ]]; then
            src_icon="$img_dir/${icon_base}.png"
            break
        elif [[ -f "$img_dir/${icon_base}.ico" ]]; then
            src_icon="$img_dir/${icon_base}.ico"
            break
        elif [[ -f "$img_dir/${icon_base,,}.png" ]]; then
            src_icon="$img_dir/${icon_base,,}.png"
            break
        elif [[ -f "$img_dir/${icon_base,,}.ico" ]]; then
            src_icon="$img_dir/${icon_base,,}.ico"
            break
        fi
    done

    if [[ -z "$src_icon" ]]; then
        warn "No icon found for $code (looked in: ${possible_img_dirs[*]} for ${icon_base}.{png,ico})"
        return 0
    fi
    
    local dest_dir="$ICON_DIR/${size}x${size}/apps"
    local dest_icon="$dest_dir/${icon_name}.png"
    
    log "Installing icon: ${icon_name}.png (${size}x${size}) from $src_icon"
    maybe_sudo mkdir -p "$dest_dir"

    # Convert ICO to PNG using ImageMagick or Python/PIL fallback
    if [[ "$src_icon" == *.ico ]]; then
        if command -v convert >/dev/null 2>&1; then
            run_cmd convert "$src_icon" -resize "${size}x${size}" "$dest_icon"
        else
            run_cmd python3 - <<PY
from PIL import Image
img = Image.open(r"$src_icon")
img = img.resize(($size, $size), Image.Resampling.LANCZOS)
img.save(r"$dest_icon", "PNG")
print('Converted', r"$src_icon", '->', r"$dest_icon")
PY
        fi
        maybe_sudo chmod 644 "$dest_icon"
    else
        # PNG: resize with convert if available, otherwise copy
        if command -v convert >/dev/null 2>&1; then
            run_cmd convert "$src_icon" -resize "${size}x${size}" "$dest_icon"
        else
            run_cmd cp "$src_icon" "$dest_icon"
        fi
        maybe_sudo chmod 644 "$dest_icon"
    fi
    
    debug "Installed: $src_icon -> $dest_icon"
}

## Note: service unit creation removed — services are managed in a separate repository.

install_miner() {
    local code="$1"
    
    log "Installing Fry Networks ${code^^} Miner"
    
    # Find release files (returns GUI binary path)
    local gui_binary
    if ! gui_binary="$(find_release_files "$code")"; then
        return 1
    fi
    
    # Extract version from binary name
    local version=""
    if [[ "$(basename "$gui_binary")" =~ _v([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
        version="${BASH_REMATCH[1]}"
    else
        version="unknown"
    fi
    
    local gui_name="frynetworks-${code,,}-control"
    local svc_name=""

    # Install GUI binary
    install_binary "$gui_binary" "$gui_name"

    # Create desktop file for GUI only
    create_desktop_file "$code" "$gui_name" "gui" "$version"
    
    # Install icons in multiple sizes
    for size in 16 32 48 64 128 256; do
        install_icon "$code" "$size"
    done
    
    # Services are managed in a separate repository; installer focuses on the GUI only.
    
    log "Successfully installed ${code^^} Miner v$version"
}

update_system_caches() {
    log "Updating system caches"
    
    # Update desktop database
    if command -v update-desktop-database >/dev/null 2>&1; then
        if [[ "$SYSTEM_INSTALL" == "true" ]]; then
            maybe_sudo update-desktop-database "$DESKTOP_DIR"
        else
            run_cmd update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
        fi
    fi
    
    # Update icon cache
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        if [[ "$SYSTEM_INSTALL" == "true" ]]; then
            maybe_sudo gtk-update-icon-cache -f "$ICON_DIR" 2>/dev/null || true
        else
            run_cmd gtk-update-icon-cache -f "$ICON_DIR" 2>/dev/null || true
        fi
    fi
    
    # Update MIME database
    if command -v update-mime-database >/dev/null 2>&1 && [[ "$SYSTEM_INSTALL" == "true" ]]; then
        maybe_sudo update-mime-database /usr/share/mime 2>/dev/null || true
    fi
}

uninstall_miner() {
    local code="$1"

    log "Uninstalling Fry Networks ${code^^} Miner (GUI only)"

    local gui_name="frynetworks-${code,,}-control"

    # Remove GUI binary
    maybe_sudo rm -f "$BIN_DIR/$gui_name"

    # Remove desktop file
    maybe_sudo rm -f "$DESKTOP_DIR/frynetworks-${code,,}-gui.desktop"

    # Remove icons
    local icon_name="frynetworks-${code,,}"
    for size in 16 32 48 64 128 256; do
        maybe_sudo rm -f "$ICON_DIR/${size}x${size}/apps/${icon_name}.png"
    done

    log "Successfully uninstalled ${code^^} Miner"
}

list_installed() {
    log "Checking installed Fry Networks miners"
    
    local found_any=false
    
    for code in BM IDM ODM ISM OSM RDN SVN SDN AEM IRM; do
        local gui_name="frynetworks-${code,,}-control"
        if [[ -f "$BIN_DIR/$gui_name" ]]; then
            found_any=true
            echo "  ${code^^}"
            echo "    GUI: $BIN_DIR/$gui_name"
        fi
        
        # Note: service binaries and units are managed in a separate repository and are not tracked here.
        done
    
    if [[ "$found_any" != "true" ]]; then
        log "No Fry Networks miners are currently installed"
    fi
}

# Parse command line arguments
UNINSTALL=false
LIST_INSTALLED=false
CODES=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --system)
            SYSTEM_INSTALL=true
            shift
            ;;
        --user)
            SYSTEM_INSTALL=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --list-installed)
            LIST_INSTALLED=true
            shift
            ;;
        --prefix)
            INSTALL_PREFIX="$2"
            shift 2
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        -*)
            error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            CODES+=("$1")
            shift
            ;;
    esac
done

# Handle special commands
if [[ "$LIST_INSTALLED" == "true" ]]; then
    list_installed
    exit 0
fi

# Validate codes
if [[ ${#CODES[@]} -eq 0 ]]; then
    error "No miner code specified"
    show_usage
    exit 1
fi

# Expand 'all' to all available codes
if [[ " ${CODES[*]} " =~ " all " ]]; then
    CODES=(BM IDM ODM ISM OSM RDN SVN SDN AEM IRM)
fi

# Validate individual codes
VALID_CODES=(BM IDM ODM ISM OSM RDN SVN SDN AEM IRM)
for code in "${CODES[@]}"; do
    if [[ ! " ${VALID_CODES[*]} " =~ " ${code^^} " ]]; then
        error "Invalid miner code: $code"
        error "Valid codes: ${VALID_CODES[*]}"
        exit 1
    fi
done

# Show installation plan
if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY RUN MODE - No changes will be made"
fi

if [[ "$SYSTEM_INSTALL" == "true" ]]; then
    log "System-wide installation to /usr/local/bin (requires sudo)"
else
    log "User installation to $INSTALL_PREFIX"
fi

# Check sudo availability if needed
if [[ "$REQUIRES_SUDO" == "true" && "$DRY_RUN" != "true" ]]; then
    if ! sudo -n true 2>/dev/null; then
        log "This installation requires sudo privileges"
        sudo -v || { error "Failed to obtain sudo privileges"; exit 1; }
    fi
fi

# Perform installation or uninstallation
for code in "${CODES[@]}"; do
    code="${code^^}"
    if [[ "$UNINSTALL" == "true" ]]; then
        uninstall_miner "$code"
    else
        install_miner "$code"
    fi
done

# Update system caches
if [[ "$UNINSTALL" != "true" && "$DRY_RUN" != "true" ]]; then
    update_system_caches
fi

# Final message
if [[ "$DRY_RUN" != "true" ]]; then
    if [[ "$UNINSTALL" == "true" ]]; then
        log "Uninstallation complete!"
    else
    log "Installation complete!"
    log ""
    log "You can now:"
    log "  • Find the application in your application menu"
    log "  • Run the GUI from the terminal: frynetworks-<code>-control"
    fi
fi