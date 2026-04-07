# Linux installer notes

This small document explains how `LINUX/install_miner.sh` finds and installs icons, and how to run the installer.

Image lookup
- The installer searches for icon files in the following locations (in this order):
  1. `LINUX/images`
 2. `$(dirname "$SCRIPT_DIR")/images` (project parent `images/`)
 3. `$(pwd)/images` (current working directory)
 4. `LINUX/../images` and a couple of ancestor `images/` locations

- The installer prefers exact-case filenames like `BM.png` / `BM.ico`, then lowercase variants `bm.png` / `bm.ico`.
- Supported formats: PNG and ICO. If an ICO is found the installer will convert it to PNG (ImageMagick `convert` preferred, otherwise Python/Pillow fallback).

Service binary handling
- Service management has moved to a separate repository. This installer focuses on the GUI only.
- If a service binary is present in the release it will be ignored; use the dedicated service repository to manage background services.

Running the installer
- User install (no sudo):
  ./LINUX/install_miner.sh BM

- System install (requires sudo):
  ./LINUX/install_miner.sh --system BM

- Dry-run (safe preview):
  ./LINUX/install_miner.sh --dry-run BM

Notes
- If icons are not found, put `BM.png` or `BM.ico` into the repository `images/` folder (project root `images/` is supported).
- If GUI features fail due to missing system libs (Qt / database clients), install the required distro packages or provide vendor client libraries before running the installer.

Linux build notes

This folder contains the helper script `build_linux.sh` used to produce a PyInstaller
one-file ELF of the GUI. PySide6 (Qt) applications require certain system shared
libraries at build-time and runtime. The build script can optionally attempt to
install the packages on Debian/Ubuntu (or Fedora) using `--install-deps` but
this requires sudo.

Quick checklist (recommended)

1) Prepare a Python virtualenv (the build script will create `.venv_build` if you run it without one):

```bash
python3 -m venv .venv_build
source .venv_build/bin/activate
python3 -m pip install --upgrade pip
# The script will pip-install the Python dependencies if missing, but you can preinstall them:
python3 -m pip install pyinstaller PySide6 psutil requests cryptography sounddevice pyserial numpy matplotlib h3 pillow shapely geoip2
```

2) Install required system packages (Debian/Ubuntu example)

The build will warn if these system libs are not available. On Debian/Ubuntu try:

```bash
sudo apt-get update
sudo apt-get install -y libxcb1 libxcb-cursor0 libtiff5 libx11-6 libx11-dev qt6-base-dev
```

Notes:
- Package names may vary by distro or release. If `libtiff5` is not available in your release, try `libtiff-dev` or `libtiff-tools`.
- If you are on Fedora/CentOS use:

```bash
sudo dnf install -y libxcb libtiff libX11 qt6-qtbase-devel
```

3) Quick fallback (not recommended for production)

If a plugin expects `libtiff.so.5` but your system only has `libtiff.so.6` you can create a compatibility symlink as a last-resort hack (only do this if you understand the ABI risk):

```bash
sudo ln -sf /lib/x86_64-linux-gnu/libtiff.so.6 /lib/x86_64-linux-gnu/libtiff.so.5
sudo ldconfig
```

4) Run the build

```bash
# from repo root
# optional: --install-deps to let the script try to install system packages (prompts for sudo)
./LINUX/build_linux.sh BM 5.5.5
```

What I changed earlier
- `LINUX/build_linux.sh` now:
  - Adds a `--install-deps` flag that attempts to install the Debian/Fedora Qt/X11 packages via sudo.
  - Adds conditional hidden-import checks so the script only passes hidden imports that actually import in the build environment.
  - Creates a temporary PyInstaller version-file to mirror the Windows builder metadata.

Troubleshooting
- If PyInstaller still warns about missing shared libs, run:

```bash
ldconfig -p | egrep 'libtiff|libxcb|libX11' || true
```

and install the package that provides the missing SONAME.

- If you prefer I can re-run the build here after you install the system packages, or I can add a small `--install-deps` mode that verifies package names for your specific distro/release.

Contact
- If things still fail, paste the short PyInstaller warning section (the lines with "Library not found:" and the warn-*.txt content) and I will interpret them and provide exact package names for your host.
