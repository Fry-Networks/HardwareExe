#!/usr/bin/env python3
import os, sys, re, json, time, subprocess, platform, socket
from pathlib import Path
from typing import List, Any, Optional, Sequence, cast

import psutil
import requests
from PySide6 import QtWidgets, QtCore, QtGui
from banner import TopBanner
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from cache_integrity import verify_cache_signature
from gui_updater import GuiAutoUpdater

try:
    from theme import Theme
except Exception:
    Theme = None  # type: ignore

from miner_online_simple import load_config, connect_mongo, registered_mac_from_devices
from gui_updater import GuiAutoUpdater

try:
    import sounddevice as sd
    HAVE_SD = True
except Exception:
    sd = cast(Any, None)
    HAVE_SD = False

try:
    import serial, serial.tools.list_ports
    HAVE_SERIAL = True
except Exception:
    serial = cast(Any, None)
    HAVE_SERIAL = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAVE_MPL = True
except Exception:
    FigureCanvas = cast(Any, None)
    Figure = cast(Any, None)
    HAVE_MPL = False

from config_profile import MINER_CODE, VERSION, GROUP, DISPLAY_NAME, METRIC_LABEL, METRIC_UNIT
try:
    from config_profile import DEV
except Exception:
    DEV = False

APP_SERVICE_WIN_BASENAME = "FRY_PoC"          # Windows service name prefix (service name)
APP_SERVICE_BIN_BASE = "FRY_PoC"              # Embedded service binary prefix (exe filename)
APP_SERVICE_WIN = f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}_v{VERSION}"
APP_SERVICE_LIN = f"miner-online-{MINER_CODE}.service"

# Miner types that are mutually exclusive at runtime (shared hardware)
EXCLUSIVE_PAIRS = {
    "ISM": "OSM",
    "OSM": "ISM",
    "IDM": "ODM",
    "ODM": "IDM",
}

def app_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).resolve().parent

def resource_path(name: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and isinstance(bundle_root, str):
        return Path(bundle_root) / name
    return app_dir() / name

def image_path(name: str) -> Path:
    """Return path to an image under the bundled 'images' directory, with fallback to root.
    This supports a transition where images may still be at repo root during migration.
    """
    # Prefer images/<name>
    bundle_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    if isinstance(bundle_root, str):
        p = Path(bundle_root) / 'images' / name
    else:
        p = app_dir() / 'images' / name
    if p.exists():
        return p
    # Fallback to legacy root location
    return resource_path(name)

# --- Splash screen with Fry banner ---
class FrySplash(QtWidgets.QDialog):
    def __init__(self):
        super().__init__(None, QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Dialog)
        self.setModal(False)
        self.setObjectName("StartupScreen")
        # Compact fixed size
        try:
            self.setFixedSize(420, 170)
        except Exception:
            self.resize(420, 170)
        lay = QtWidgets.QVBoxLayout(self)
        try:
            lay.setContentsMargins(16, 16, 16, 16)
            lay.setSpacing(10)
        except Exception:
            pass
        try:
            self.setStyleSheet(self.styleSheet() + "\n"
                               "#StartupScreen { background-color: #000000; }\n"
                               "QLabel { color: white; }\n"
                               "QProgressBar { border: 1px solid white; background-color: black; color: white; height: 12px; }\n"
                               "QProgressBar::chunk { background-color: #E10600; }\n")
        except Exception:
            pass
        try:
            bp = image_path("background.png")
        except Exception:
            bp = resource_path("images/background.png")
        banner_img = str(bp) if hasattr(bp, 'exists') and bp.exists() else (bp if isinstance(bp, str) else None)
        self.banner = TopBanner(f"FRY {DISPLAY_NAME} - v{VERSION}", banner_img, height=80)
        try:
            # Slightly smaller title font on splash to fit compact width
            self.banner.setStyleSheet(self.banner.styleSheet() + "#bannerTitle { font-size: 24px; }")
        except Exception:
            pass
        self.msg = QtWidgets.QLabel("Initializing...")
        try:
            self.msg.setWordWrap(True)
        except Exception:
            pass
        self.keyLbl = QtWidgets.QLabel("")
        self.bar = QtWidgets.QProgressBar()
        try:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        except Exception:
            pass
        lay.addWidget(self.banner)
        lay.addWidget(self.msg)
        lay.addWidget(self.keyLbl)
        lay.addWidget(self.bar)

    def step(self, text: str, value: int):
        try:
            self.msg.setText(text)
            self.bar.setValue(max(0, min(100, value)))
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def set_key(self, key: str | None):
        try:
            k = (key or "").strip()
            if k:
                self.keyLbl.setText(f"Key: {k}")
            else:
                self.keyLbl.clear()
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

def miner_icon_path() -> Path:
    """Return the per-miner icon path under images/ based on MINER_CODE."""
    try:
        code = (MINER_CODE or "").upper()
    except Exception:
        code = ""
    base = None
    if code == "BM":
        base = "BM.jpg"
    elif code == "AEM":
        base = "AEM.jpg"
    elif code == "IRM":
        base = "RAD.jpg"
    elif code in ("IDM", "ODM"):
        base = "DB.jpg"
    elif code in ("ISM", "OSM"):
        base = "GNSS.jpg"
    elif code in ("RDN", "SVN", "SDN"):
        base = "NODE.jpg"
    else:
        base = "frynetworks_logo.png"
    return image_path(base)
def embedded_path(name: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and isinstance(bundle_root, str):
        return Path(bundle_root) / 'embedded' / name
    return app_dir() / 'embedded' / name

def _parse_sc_qc_binary_path(service_name: str) -> str | None:
    """Return the BINARY_PATH_NAME from `sc qc` for a service (Windows only)."""
    if not sys.platform.startswith('win'):
        return None
    try:
        out = subprocess.run(["sc", "qc", service_name], capture_output=True, text=True)
        for line in (out.stdout or '').splitlines():
            if 'BINARY_PATH_NAME' in line:
                # extract path between quotes if present, else first token up to .exe
                s = line.split(':', 1)[1].strip()
                if s.startswith('"') and '"' in s[1:]:
                    return s.split('"')[1]
                # fallback: split on spaces, take token up to .exe
                parts = s.split()
                for tok in parts:
                    if tok.lower().endswith('.exe'):
                        return tok
        return None
    except Exception:
        return None

def ensure_admin_windows() -> bool:
    if not sys.platform.startswith('win'):
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def relaunch_as_admin() -> bool:
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        params = ' '.join([f'"{p}"' for p in sys.argv])
        ret = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, None, 1)
        return ret and ret > 32
    except Exception:
        return False

# ---- version helpers ----
def _parse_ver_list(s: str) -> list[int]:
    try:
        return [int(x) for x in re.split(r"[^0-9]+", s or "") if x]
    except Exception:
        return [0]

def _cmp_ver(a: str, b: str) -> int:
    A = _parse_ver_list(a); B = _parse_ver_list(b)
    L = max(len(A), len(B)); A += [0]*(L-len(A)); B += [0]*(L-len(B))
    return (A > B) - (A < B)

def _extract_service_version(name: str) -> str | None:
    try:
        m = re.search(r"_V(\d+(?:\.\d+)*)$", name, re.IGNORECASE)
        return m.group(1) if m else None
    except Exception:
        return None

def _extract_process_version(name: str) -> str | None:
    try:
        m = re.search(r"_V(\d+(?:\.\d+)*)\.exe$", name, re.IGNORECASE)
        return m.group(1) if m else None
    except Exception:
        return None

def make_key_pattern(prefix: str) -> re.Pattern:
    return re.compile(rf"^{re.escape(prefix)}-[A-Z0-9]{{32}}$")

def _close_older_gui_instances() -> bool:
    """Terminate older GUI processes for this miner type if present.
    Returns True if a newer GUI version is already running (so caller should exit).
    """
    try:
        base_pref = f"fry_{MINER_CODE.lower()}_v"
        newer_running = False
        for p in psutil.process_iter(["pid","name"]):
            try:
                nm_full = p.info.get("name") or ""
                nm = nm_full.lower()
                if not nm.startswith(base_pref):
                    continue
                ver = _extract_process_version(nm_full) or ""
                if not ver:
                    continue
                cmp = _cmp_ver(ver, VERSION)
                if cmp < 0:
                    # Older GUI instance: terminate
                    try:
                        p.terminate(); p.wait(2)
                    except Exception:
                        try:
                            subprocess.run(["taskkill","/F","/PID", str(p.info.get('pid'))], capture_output=True)
                        except Exception:
                            pass
                elif cmp > 0:
                    newer_running = True
            except Exception:
                continue
        # After closing older GUIs, also stop any older Windows services for this miner type
        try:
            if sys.platform.startswith('win'):
                out = subprocess.run(["sc","query","type=","service","state=","all"], capture_output=True, text=True)
                svc_names = []
                for line in (out.stdout or '').splitlines():
                    lu = line.strip()
                    if lu.upper().startswith('SERVICE_NAME:'):
                        nm = lu.split(':',1)[1].strip()
                        svc_names.append(nm)
                base = f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}"
                for nm in svc_names:
                    try:
                        if not nm.upper().startswith(base.upper()):
                            continue
                        # Skip current versioned service, stop legacy or lower versions
                        if nm.upper() == APP_SERVICE_WIN.upper():
                            continue
                        ver = _extract_service_version(nm)
                        if ver is None or _cmp_ver(ver, VERSION) < 0:
                            # Stop then delete older/legacy services
                            try:
                                subprocess.run(["sc","stop", nm], capture_output=True)
                            except Exception:
                                pass
                            try:
                                subprocess.run(["sc","delete", nm], capture_output=True)
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
        return newer_running
    except Exception:
        return False

KEY_PATTERN = make_key_pattern(MINER_CODE)

def write_miner_key(miner_key: str):
    """Persist miner_key primarily to ProgramData so the service and GUI agree.
    Also write to the legacy app_dir minerkey.txt for backward compatibility.
    """
    try:
        pd = data_dir_gui()
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "minerkey.txt").write_text(miner_key.strip() + "\n", encoding="utf-8")
    except Exception:
        pass
    try:
        (app_dir() / "minerkey.txt").write_text(miner_key.strip() + "\n", encoding="utf-8")
    except Exception:
        pass

def read_miner_key() -> str:
    """Read miner_key, preferring ProgramData copy used by the service."""
    try:
        p_pd = data_dir_gui() / "minerkey.txt"
        if p_pd.exists():
            val = p_pd.read_text(encoding="utf-8", errors="ignore").strip()
            if KEY_PATTERN.match(val or ""):
                return val
    except Exception:
        pass
    p = app_dir() / "minerkey.txt"
    try:
        return p.read_text(encoding="utf-8", errors="ignore").strip() if p.exists() else ""
    except Exception:
        return ""

def gui_log_path() -> Path:
    try:
        base = data_dir_gui()
        p = base / 'logs'
        p.mkdir(parents=True, exist_ok=True)
        return p / 'gui_start.log'
    except Exception:
        return app_dir() / 'gui_start.log'

def log_step(msg: str, data: dict | None = None):
    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} | {msg}"
        path = gui_log_path()
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
            if isinstance(data, dict):
                try:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                except Exception:
                    f.write(str(data) + "\n")
    except Exception:
        pass

def _fry_logo_icon() -> QtGui.QIcon:
    try:
        return QtGui.QIcon(str(miner_icon_path()))
    except Exception:
        return QtGui.QIcon()

def fry_error(parent, title: str, message: str):
    try:
        log_step(f"ERROR dlg: {title}", {"message": message})
        m = QtWidgets.QMessageBox(parent)
        m.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        m.setWindowTitle(f"FryNetworks - {title}")
        m.setText(message)
        m.setWindowIcon(_fry_logo_icon())
        m.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        m.exec()
    except Exception:
        try:
            QtWidgets.QMessageBox.critical(parent, title, message)
        except Exception:
            pass

def fry_warn(parent, title: str, message: str):
    try:
        log_step(f"WARN dlg: {title}", {"message": message})
        m = QtWidgets.QMessageBox(parent)
        m.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        m.setWindowTitle(f"FryNetworks - {title}")
        m.setText(message)
        m.setWindowIcon(_fry_logo_icon())
        m.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        m.exec()
    except Exception:
        try:
            QtWidgets.QMessageBox.warning(parent, title, message)
        except Exception:
            pass

def _format_conflict_details(details: dict | None) -> str:
    try:
        if not isinstance(details, dict):
            return ''
        host = details.get('hostname')
        last = details.get('last_seen_at')
        exp  = details.get('lease_expires_at')
        extra = []
        if host:
            extra.append(f"Host: {host}")
        if last:
            extra.append(f"Last seen: {last}")
        if exp:
            extra.append(f"Lease expires: {exp}")
        return ("\n" + " | ".join(extra)) if extra else ''
    except Exception:
        return ''

def _in_use_message(key: str | None, details: str = '') -> str:
    try:
        k = (key or '').strip()
        part_key = (f"\nminer_key: {k}" if k else '')
        return (
            f"Only one {DISPLAY_NAME} is allowed on the same computer." +
            part_key +
            "\nPlease close any other running instance or installed service and try again." +
            (details or '')
        )
    except Exception:
        return f"Only one {DISPLAY_NAME} is allowed on the same computer. Please close any other running instance or installed service and try again."

def _cleanup_local_identity_and_logs():
    """Minimal cleanup on conflict: do NOT delete install_id; only trim error logs.

    Rationale: This device may legitimately run another miner_key of the same type.
    Keeping install_id preserves its identity for future runs. We only remove
    high-churn error logs to avoid confusing the user on subsequent attempts.
    """
    try:
        base = data_dir_gui()
        # Keep install_id.txt intact
        # Remove only transient error/output logs if present
        for rel in (('logs', 'service.err.log'), ('logs', 'service.out.log')):
            try:
                p = base
                for part in rel:
                    p = p / part
                if p.exists():
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass

def _trim_text(s: str, max_len: int = 1200) -> str:
    try:
        if not isinstance(s, str):
            return ''
        if len(s) <= max_len:
            return s
        return s[:max_len] + '...'
    except Exception:
        return ''

def _collect_start_failure_details(self) -> str:
    try:
        base = data_dir_gui()
        key = (self.keyEdit.text() or '').strip()
        nssm_local = base / 'nssm.exe'
        exe_path = base / f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe"
        exists = {
            'ProgramData': str(base),
            'nssm.exe': f"{nssm_local} ({'ok' if nssm_local.exists() else 'missing'})",
            'service.exe': f"{exe_path} ({'ok' if exe_path.exists() else 'missing'})",
            'minerkey.txt': f"{(base / 'minerkey.txt')} ({'ok' if (base / 'minerkey.txt').exists() else 'missing'})",
        }
        parts: list[str] = []
        # Service config via sc qc
        try:
            qc = subprocess.run(["sc","qc", APP_SERVICE_WIN], capture_output=True, text=True)
            qc_out = (qc.stdout or '')
        except Exception:
            qc_out = ''
        # NSSM view of Application/AppDirectory (best-effort)
        app_line = appdir_line = ''
        try:
            nssm = str(nssm_local)
            if os.path.exists(nssm):
                # Capture raw bytes to handle UTF-16 output from NSSM 'get'
                r1 = subprocess.run([nssm,'get',APP_SERVICE_WIN,'Application'], capture_output=True, text=False)
                r2 = subprocess.run([nssm,'get',APP_SERVICE_WIN,'AppDirectory'], capture_output=True, text=False)
                def _decode(b: bytes) -> str:
                    try:
                        s = b.decode('utf-16le', errors='ignore').strip('\r\n\0 ')
                        return s if s else b.decode(errors='ignore').strip()
                    except Exception:
                        try:
                            return b.decode(errors='ignore').strip()
                        except Exception:
                            return ''
                app_line = _decode(r1.stdout or b'')
                appdir_line = _decode(r2.stdout or b'')
        except Exception:
            pass
        # Append last stdout lines if present
        try:
            outp = base / 'logs' / 'service.out.log'
            if outp.exists():
                lines = outp.read_text(encoding='utf-8', errors='ignore').splitlines()[-15:]
                tail_out = "\n".join(lines)
                if tail_out:
                    parts.append("Last stdout lines:\n" + _trim_text(tail_out, 1200))
        except Exception:
            pass
        # Append last error lines if present
        try:
            errp = base / 'logs' / 'service.err.log'
            tail = ''
            if errp.exists():
                lines = errp.read_text(encoding='utf-8', errors='ignore').splitlines()[-15:]
                tail = "\n".join(lines)
        except Exception:
            tail = ''
        parts = []
        parts.append(f"miner_key: {key if key else '-'}")
        parts.append(f"ProgramData: {exists['ProgramData']}")
        parts.append(f"nssm: {exists['nssm.exe']}")
        parts.append(f"binary: {exists['service.exe']}")
        parts.append(f"keyfile: {exists['minerkey.txt']}")
        if app_line:
            parts.append(f"nssm Application: {app_line}")
        if appdir_line:
            parts.append(f"nssm AppDirectory: {appdir_line}")
        if qc_out:
            try:
                # Show only the BINARY_PATH_NAME line to avoid noise
                bp = ''
                for ln in qc_out.splitlines():
                    if 'BINARY_PATH_NAME' in ln:
                        bp = ln.strip(); break
                if bp:
                    parts.append(f"sc qc: {bp}")
            except Exception:
                pass
        if tail:
            parts.append("Last error lines:\n" + _trim_text(tail, 1200))
        return "\n".join(parts)
    except Exception:
        return ''

# Styled input dialog for miner_key entry with FryNetworks icon and wider field
def ask_miner_key(parent) -> tuple[str, bool]:
    try:
        dlg = QtWidgets.QInputDialog(parent)
        dlg.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dlg.setWindowTitle('Miner Key')
        dlg.setLabelText(f'Enter miner_key for {DISPLAY_NAME}:')
        dlg.setWindowIcon(_fry_logo_icon())
        try:
            # Apply FryNetworks dark theme to the prompt so it matches the app
            from theme import Theme
            dlg.setStyleSheet(Theme().qss())
        except Exception:
            pass
        try:
            dlg.setMinimumWidth(380)
            dlg.resize(400, 180)
        except Exception:
            pass
        try:
            edit = dlg.findChild(QtWidgets.QLineEdit)
            if edit is not None:
                edit.setPlaceholderText(f"{MINER_CODE}-[A-Z0-9]{{32}}")
                edit.setMinimumWidth(540)
        except Exception:
            pass
        ok = (dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted)
        return dlg.textValue().strip(), ok
    except Exception:
        # Fallback to basic getText if custom dialog fails
        text, ok = QtWidgets.QInputDialog.getText(parent, 'Miner Key', f'Enter miner_key for {DISPLAY_NAME}:')
        return (text or '').strip(), bool(ok)

# --- pre-start key validation helpers (module-level) ---
def _check_key_exists_global(key: str) -> bool:
    try:
        cmd: list[str] = []
        if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
            svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
            if svc.exists():
                cmd = [str(svc), "--check-key", key]
        if not cmd:
            svc_py = app_dir() / "miner_online_simple.py"
            if svc_py.exists():
                cmd = [sys.executable, str(svc_py), "--check-key", key]
        if not cmd:
            return False
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return p.returncode == 0
    except Exception:
        return False

def _check_key_concurrency_global(key: str) -> tuple[bool, dict | None]:
    try:
        cmd: list[str] = []
        if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
            svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
            if svc.exists():
                cmd = [str(svc), "--check-concurrency", key]
        if not cmd:
            svc_py = app_dir() / "miner_online_simple.py"
            if svc_py.exists():
                cmd = [sys.executable, str(svc_py), "--check-concurrency", key]
        if not cmd:
            return True, None
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        try:
            doc = json.loads((p.stdout or "").strip() or "{}")
        except Exception:
            doc = {}
        if p.returncode == 0:
            return True, doc if doc else None
        if p.returncode == 8:
            return False, doc.get("conflict") if isinstance(doc, dict) else {"reason": "conflict"}
        return False, doc if doc else {"reason": "error"}
    except Exception:
        return False, {"reason": "exception"}

def _check_key_version_global(key: str) -> tuple[bool | None, str | None, str | None]:
    try:
        cmd: list[str] = []
        if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
            svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
            if svc.exists():
                cmd = [str(svc), "--check-version", key]
        if not cmd:
            svc_py = app_dir() / "miner_online_simple.py"
            if svc_py.exists():
                cmd = [sys.executable, str(svc_py), "--check-version", key]
        if not cmd:
            return None, None, None
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        needed = installed = None
        ok: bool | None = None
        try:
            doc = json.loads(p.stdout.strip() or "{}")
            ok = bool(doc.get("ok")) if "ok" in doc else (p.returncode == 0)
            needed = doc.get("needed")
            installed = doc.get("installed") or VERSION
        except Exception:
            ok = (p.returncode == 0)
        return ok, needed, installed
    except Exception:
        return None, None, None

# Marker set by pre-start validation so MainWindow can skip duplicate prompts
_PRECHECK_OK: bool = False
# Flip to True when prestart version check finds we are behind so the GUI auto-updater can run even if config says up-to-date.
_FORCE_UPDATE_REQUIRED: bool = False

def is_internet_up(timeout=4) -> bool:
    try:
        r = requests.get("http://clients3.google.com/generate_204", timeout=timeout)
        return r.status_code == 204
    except requests.RequestException:
        return False

# --- Windows autostart (GUI) ---
def _autostart_reg_name() -> str:
    try:
        return f"FRY_{MINER_CODE}_GUI"
    except Exception:
        return "FRY_Miner_GUI"

def ensure_gui_autostart_windows():
    """Register this GUI to start at Windows logon under HKCU Run.
    Best-effort, no admin required. Safe to call repeatedly.
    """
    if not sys.platform.startswith('win'):
        return
    try:
        import winreg
        # Determine the executable to run on startup
        exe = sys.executable if getattr(sys, 'frozen', False) else str(Path(__file__).resolve())
        cmd = f'"{exe}"'
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            try:
                cur, _ = winreg.QueryValueEx(key, _autostart_reg_name())
            except FileNotFoundError:
                cur = None
            if cur != cmd:
                winreg.SetValueEx(key, _autostart_reg_name(), 0, winreg.REG_SZ, cmd)
    except Exception:
        # Non-fatal; GUI will still run even if we cannot set autostart
        pass

def ensure_gui_autostart_task():
    """Register a Windows Task Scheduler entry to start the GUI at logon with highest privileges.
    Attempts a per-user, interactive task to avoid UAC prompts. Falls back silently on failure.
    """
    if not sys.platform.startswith('win'):
        return
    try:
        tn = f"FRY_{MINER_CODE}_GUI"
        exe = sys.executable if getattr(sys, 'frozen', False) else str(Path(__file__).resolve())
        def _exists():
            try:
                p = subprocess.run(["schtasks","/Query","/TN",tn], capture_output=True, text=True)
                return p.returncode == 0
            except Exception:
                return False
        args = [
            "schtasks","/Create",
            "/TN", tn,
            "/SC","ONLOGON",
            "/TR", f'"{exe}"',
            "/RL","HIGHEST",
            "/IT",
            "/F",
        ]
        if _exists():
            try:
                subprocess.run(["schtasks","/Delete","/TN",tn,"/F"], capture_output=True, text=True)
            except Exception:
                pass
        subprocess.run(args, capture_output=True, text=True)
    except Exception:
        pass

def remove_gui_autostart_task():
    """Remove the Windows Task Scheduler entry created for GUI autostart (if present)."""
    if not sys.platform.startswith('win'):
        return
    try:
        tn = f"FRY_{MINER_CODE}_GUI"
        subprocess.run(["schtasks","/Delete","/TN",tn,"/F"], capture_output=True, text=True)
    except Exception:
        pass

# --- Single-instance IPC via QLocalServer/QLocalSocket ---
class SingleInstance(QtCore.QObject):
    wakeRequested = QtCore.Signal()
    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.server = QLocalServer(self)
        try:
            QLocalServer.removeServer(self.key)
        except Exception:
            pass
    def start_or_signal(self) -> bool:
        if self.server.listen(self.key):
            self.server.newConnection.connect(self._on_new_connection)
            return True
        sock = QLocalSocket()
        sock.connectToServer(self.key, QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if sock.waitForConnected(750):
            sock.write(b"SHOW\\n")
            sock.flush()
            sock.waitForBytesWritten(250)
            sock.disconnectFromServer()
        return False
    def _on_new_connection(self):
        sock = self.server.nextPendingConnection()
        if not sock:
            return
        sock.readyRead.connect(lambda s=sock: self._read_and_wake(s))
    def _read_and_wake(self, sock: QLocalSocket):
        try:
            _ = sock.readAll()
        except Exception:
            pass
        self.wakeRequested.emit()
        try:
            sock.disconnectFromServer()
        except Exception:
            pass

def service_exists(miner_code: str) -> bool:
    try:
        if sys.platform.startswith("win"):
            # Versioned service name: FRY_PoC_<CODE>_v<VERSION>
            svc_name = f"{APP_SERVICE_WIN_BASENAME}_{miner_code}_v{VERSION}"
            out = subprocess.run(["sc", "query", svc_name],
                                 capture_output=True, text=True)
            return "SERVICE_NAME" in out.stdout
        else:
            svc_name = f"miner-online-{miner_code}.service"
            out = subprocess.run(["systemctl", "status", svc_name],
                                 capture_output=True, text=True)
            return out.returncode == 0
    except Exception:
        return False

class HourlyBar(QtWidgets.QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        if not HAVE_MPL:
            lay=QtWidgets.QVBoxLayout(self); lay.addWidget(QtWidgets.QLabel("Chart unavailable")); return
        self.fig=Figure(figsize=(6,2),dpi=100, constrained_layout=True)
        self.ax=self.fig.add_subplot(111)
        self.canvas=FigureCanvas(self.fig)
        lay=QtWidgets.QVBoxLayout(self); lay.addWidget(self.canvas)
        self.draw_counts([0]*24, [f"{h:02d}" for h in range(24)])
    def draw_counts(self, counts: Sequence[float], labels: Sequence[str]):
        if not HAVE_MPL:
            return
        self.ax.clear()
        self.ax.set_facecolor("#121212")
        self.fig.patch.set_facecolor("#121212")
        values = [float(c) for c in counts]
        n = min(24, len(values))
        values = (values + [0.0]*24)[:24]
        self.ax.bar(range(24), values, color="#dc2626", alpha=0.85)  # shadow-red-600
        # Display y-axis as percentage (0..100) like the 7-day view
        self.ax.set_ylim(0,100)
        try:
            self.ax.set_yticks([0,25,50,75,100])
        except Exception:
            pass
        self.ax.tick_params(axis="x", colors="#9e9e9e")
        self.ax.tick_params(axis="y", colors="#9e9e9e")
        for spine in self.ax.spines.values():
            spine.set_color("#7e7e7e")
        xticks = list(range(0,24,3))
        self.ax.set_xticks(xticks)
        label_list = list(labels)
        self.ax.set_xticklabels([label_list[i] if i < len(label_list) else "" for i in xticks], color="#9e9e9e")
        try:
            # Let Matplotlib allocate space so tick labels remain visible on resize
            self.fig.tight_layout(pad=0.6)
        except Exception:
            pass
        self.canvas.draw()

class Rolling7Bar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        if not HAVE_MPL:
            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(QtWidgets.QLabel("Chart unavailable"))
            return
        self.fig = Figure(figsize=(4.5, 2), dpi=100, constrained_layout=True)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.canvas)
        self.draw_percents([0]*7, [""]*7)

    def draw_percents(self, percents: list[float], labels: list[str]):
        if not HAVE_MPL:
            return
        self.ax.clear()
        self.ax.set_facecolor("#121212")
        self.fig.patch.set_facecolor("#121212")
        n = max(1, len(percents))
        self.ax.bar(range(n), percents, color="#dc2626", alpha=0.85)
        self.ax.set_ylim(0, 100)
        self.ax.tick_params(axis="x", colors="#9e9e9e")
        self.ax.tick_params(axis="y", colors="#9e9e9e")
        for spine in self.ax.spines.values():
            spine.set_color("#7e7e7e")
        try:
            self.ax.set_xticks(range(n))
            self.ax.set_xticklabels(labels, rotation=0, color="#9e9e9e")
            self.fig.tight_layout(pad=0.6)
        except Exception:
            pass
        self.canvas.draw()

class LogoLabel(QtWidgets.QLabel):
    def __init__(self, pix: QtGui.QPixmap | None = None, parent=None):
        super().__init__(parent)
        self._base_pix = pix
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        try:
            policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
            self.setSizePolicy(policy)
        except Exception:
            pass
        try:
            self.setMinimumSize(128, 128)
        except Exception:
            pass
        if pix is not None:
            self._apply_scaled()

    def set_base_pixmap(self, pix: QtGui.QPixmap):
        self._base_pix = pix
        self._apply_scaled()

    def resizeEvent(self, ev):  # type: ignore[override]
        try:
            self._apply_scaled()
        except Exception:
            pass
        return super().resizeEvent(ev)

    def _apply_scaled(self):
        if self._base_pix is None:
            return
                # Scale relative to containing group's height with a max 320x320 box
        try:
            anc = self.parentWidget()
            while anc is not None and not isinstance(anc, QtWidgets.QGroupBox):
                anc = anc.parentWidget()
            group_h = anc.height() if anc is not None else self.height()
        except Exception:
            group_h = self.height()
        box = max(64, min(320, int(group_h - 32)))
        scaled = self._base_pix.scaled(box, box,
                                       QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                       QtCore.Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

class Worker(QtCore.QThread):
    tick = QtCore.Signal(object)
    def __init__(self, group:str, selector:str|None, device_idx:int|None, baud:int|None):
        super().__init__()
        self.group=group; self.selector=selector; self.device_idx=device_idx; self.baud=baud
        self._stop=False
    def stop(self): self._stop=True
    def run(self):
        # For Decibel, keep a persistent audio stream to avoid device blink on each sample
        if self.group == "Decibel":
            try:
                self._run_decibel_stream(self.device_idx)
            except Exception as e:
                # Fall back to periodic sampling on error
                while not self._stop:
                    try:
                        data = self._sample_decibel(self.device_idx)
                    except Exception as ee:
                        data = {"err": str(ee)}
                    self.tick.emit(data)
                    self.msleep(2000)
            return
        while not self._stop:
            try:
                if self.group in ("Bandwidth","AIEdge"):
                    data = self._sample_bandwidth(self.selector or "")
                elif self.group=="Satellite":
                    data = self._sample_gnss(self.selector or "", self.baud or 9600)
                else:
                    data = {}
            except Exception as e:
                data = {"err": str(e)}
            self.tick.emit(data)
            self.msleep(2000)

    def _sample_bandwidth(self, iface: str):
        import psutil, time
        nic0 = psutil.net_io_counters(pernic=True).get(iface)
        if not nic0: return {"dl":0.0,"ul":0.0,"iface":iface}
        r0,t0 = nic0.bytes_recv, nic0.bytes_sent
        tstart=time.time()
        time.sleep(1.0)
        nic1 = psutil.net_io_counters(pernic=True).get(iface)
        if not nic1: return {"dl":0.0,"ul":0.0,"iface":iface}
        r1,t1 = nic1.bytes_recv, nic1.bytes_sent
        dt = max(1e-3, time.time()-tstart)
        dl_mbps = (max(0, r1-r0)*8.0/1e6)/dt
        ul_mbps = (max(0, t1-t0)*8.0/1e6)/dt
        return {"dl":round(dl_mbps,2),"ul":round(ul_mbps,2),"iface":iface}

    def _sample_decibel(self, idx: int|None):
        if not HAVE_SD: return {"dbfs": None}
        import numpy as np, sounddevice as sd
        sr=16000; dur=0.25
        try:
            audio=sd.rec(int(sr*dur), samplerate=sr, channels=1, dtype="float32", device=idx)
            sd.wait()
            rms=float(np.sqrt(np.mean(audio**2))+1e-12)
            dbfs=20*np.log10(rms)
            dbfs=max(-90.0, min(0.0, dbfs))
            return {"dbfs": round(dbfs,1)}
        except Exception as e:
            return {"err": str(e)}

    def _run_decibel_stream(self, idx: int|None):
        if not HAVE_SD:
            while not self._stop:
                self.tick.emit({"dbfs": None})
                self.msleep(1000)
            return
        import time as _t
        import numpy as np, sounddevice as sd
        sr = 16000
        win_sec = 0.25   # analysis window
        tick_sec = 1.0   # emit frequency
        chunk_sec = 0.05 # continuous read chunk
        win_frames = int(sr * win_sec)
        chunk_frames = max(1, int(sr * chunk_sec))
        try:
            with sd.InputStream(device=idx, channels=1, samplerate=sr, dtype="float32") as stream:
                # Rolling buffer of last window
                buf = np.zeros((win_frames, 1), dtype=np.float32)
                pos = 0
                filled = 0
                last_emit = _t.monotonic()
                while not self._stop:
                    try:
                        chunk, _ = stream.read(chunk_frames)
                        n = chunk.shape[0]
                        # Write chunk into rolling buffer (circular)
                        if n <= win_frames:
                            end = pos + n
                            if end <= win_frames:
                                buf[pos:end, 0] = chunk[:, 0]
                            else:
                                first = win_frames - pos
                                buf[pos:win_frames, 0] = chunk[:first, 0]
                                buf[0:end - win_frames, 0] = chunk[first:, 0]
                            pos = end % win_frames
                            filled = min(win_frames, filled + n)
                        else:
                            # Oversized read; keep the last window
                            buf[:, 0] = chunk[-win_frames:, 0]
                            pos = 0
                            filled = win_frames

                        now = _t.monotonic()
                        if (now - last_emit) >= tick_sec and filled > 0:
                            # Compute RMS over the current window
                            if filled < win_frames:
                                window = buf[:filled, 0]
                            else:
                                window = np.concatenate((buf[pos:, 0], buf[:pos, 0]))
                            rms = float(np.sqrt(np.mean(window**2)) + 1e-12)
                            dbfs = 20 * np.log10(rms)
                            dbfs = max(-90.0, min(0.0, dbfs))
                            self.tick.emit({"dbfs": round(dbfs, 1)})
                            last_emit = now
                    except Exception as e:
                        self.tick.emit({"err": str(e)})
                        _t.sleep(0.05)
        except Exception:
            # Propagate to caller for fallback to non-stream method
            raise

    def _sample_gnss(self, port: str, baud:int):
        return {}

class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._liveWorker=None
        self.setWindowTitle(f"FRY {DISPLAY_NAME} - v{VERSION}")
        self.setWindowIcon(QtGui.QIcon(str(miner_icon_path())))
        # Larger default and resizable; let content autoscale with the window
        self.setMinimumSize(1280,900)

        # Banner (TopBanner draws image + centered title)
        bp = image_path("background.png")
        self.banner = TopBanner(f"FRY {DISPLAY_NAME} - v{VERSION}", str(bp) if bp.exists() else None, height=120)

        # Inputs
        self.keyEdit=QtWidgets.QLineEdit(); self.keyEdit.setPlaceholderText(f"{MINER_CODE}-[A-Z0-9]{{32}}")
        self.regexHint=QtWidgets.QLabel(''); self.regexHint.setObjectName("hint")

        form=QtWidgets.QFormLayout()
        # Tighter spacing and no extra margins to reduce the gap above Settings
        try:
            form.setContentsMargins(8, 0, 8, 0)
            form.setVerticalSpacing(2)
        except Exception:
            pass
        form.addRow("miner_key", self.keyEdit); form.addRow("", self.regexHint)

        self.activeNetworkName = None
        self.activeMacAddress = None
        self._persistedMacValue = None
        self._prunedOldServiceBinaries = False
        self._downloadedUpdatePath: str = ''

        # --- Selectors depending on group ---
        if GROUP in ("Bandwidth","AIEdge"):
            self.networkLabel = QtWidgets.QLabel("Active network")
            self.networkValueLabel = QtWidgets.QLabel("-")
            self.macTitle = QtWidgets.QLabel("MAC")
            self.macValueLabel = QtWidgets.QLabel("-")
            self.macRegisteredTitle = QtWidgets.QLabel("Registered")
            self.macRegisteredValue = QtWidgets.QLabel("-")
            self.macMatchCheck = QtWidgets.QCheckBox("match")
            self.macMatchCheck.setEnabled(False)
            self.macMatchCheck.setVisible(False)
            self.macMismatchLabel = QtWidgets.QLabel("[!] mismatch")
            try:
                self.macMismatchLabel.setStyleSheet("color: #c75c1e; font-weight: 600;")
            except Exception:
                pass
            self.macMismatchLabel.setVisible(False)

            self.settingsGb = QtWidgets.QGroupBox("Settings")
            try:
                self.settingsGb.setObjectName("layerBox")
            except Exception:
                pass
            sLay = QtWidgets.QHBoxLayout(self.settingsGb); sLay.setContentsMargins(8,4,8,8)
            try:
                self.settingsGb.setStyleSheet("QGroupBox { margin-top: 0px; }")
            except Exception:
                pass
            sLay.addWidget(self.networkLabel)
            sLay.addWidget(self.networkValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macTitle)
            sLay.addWidget(self.macValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macRegisteredTitle)
            sLay.addWidget(self.macRegisteredValue)
            sLay.addSpacing(6)
            sLay.addWidget(self.macMatchCheck)
            sLay.addWidget(self.macMismatchLabel)
            sLay.addStretch(1)

        elif GROUP=="Decibel":
            self.networkLabel = QtWidgets.QLabel("Active network")
            self.networkValueLabel = QtWidgets.QLabel("-")
            self.macTitle = QtWidgets.QLabel("MAC")
            self.macValueLabel = QtWidgets.QLabel("-")
            self.macRegisteredTitle = QtWidgets.QLabel("Registered")
            self.macRegisteredValue = QtWidgets.QLabel("-")
            self.macMatchCheck = QtWidgets.QCheckBox("match")
            self.macMatchCheck.setEnabled(False)
            self.macMatchCheck.setVisible(False)
            self.macMismatchLabel = QtWidgets.QLabel("[!] mismatch")
            try:
                self.macMismatchLabel.setStyleSheet("color: #c75c1e; font-weight: 600;")
            except Exception:
                pass
            self.macMismatchLabel.setVisible(False)

            self.deviceLabel=QtWidgets.QLabel("Microphone")
            self.deviceCombo=QtWidgets.QComboBox(); self.deviceCombo.setFixedWidth(360)
            self.deviceHelp=QtWidgets.QLabel("")
            self.btnApplyMic = QtWidgets.QPushButton("Update"); self.btnApplyMic.setVisible(False)
            self.btnApplyMic.clicked.connect(self._apply_microphone_selection)  # type: ignore[attr-defined]
            self._populate_microphones()  # type: ignore[attr-defined]
            self.deviceCombo.currentIndexChanged.connect(lambda _: self._on_microphone_selection_changed())  # type: ignore[attr-defined]

            self.settingsGb = QtWidgets.QGroupBox("Settings")
            try:
                self.settingsGb.setObjectName("layerBox")
            except Exception:
                pass
            sLay = QtWidgets.QHBoxLayout(self.settingsGb); sLay.setContentsMargins(8,4,8,8)
            try:
                self.settingsGb.setStyleSheet("QGroupBox { margin-top: 0px; }")
            except Exception:
                pass
            sLay.addWidget(self.networkLabel)
            sLay.addWidget(self.networkValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macTitle)
            sLay.addWidget(self.macValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macRegisteredTitle)
            sLay.addWidget(self.macRegisteredValue)
            sLay.addSpacing(6)
            sLay.addWidget(self.macMatchCheck)
            sLay.addWidget(self.macMismatchLabel)
            sLay.addSpacing(24)
            sLay.addWidget(self.deviceLabel)
            sLay.addWidget(self.deviceCombo)
            sLay.addSpacing(12)
            sLay.addWidget(self.deviceHelp)
            sLay.addSpacing(12)
            try:
                policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
                self.btnApplyMic.setSizePolicy(policy)
            except Exception:
                pass
            sLay.addWidget(self.btnApplyMic)
            sLay.addStretch(1)
        elif GROUP=="Satellite":
            self.networkLabel = QtWidgets.QLabel("Active network")
            self.networkValueLabel = QtWidgets.QLabel("-")
            self.macTitle = QtWidgets.QLabel("MAC")
            self.macValueLabel = QtWidgets.QLabel("-")
            self.macRegisteredTitle = QtWidgets.QLabel("Registered")
            self.macRegisteredValue = QtWidgets.QLabel("-")
            self.macMatchCheck = QtWidgets.QCheckBox("match")
            self.macMatchCheck.setEnabled(False)
            self.macMatchCheck.setVisible(False)
            self.macMismatchLabel = QtWidgets.QLabel("[!] mismatch")
            try:
                self.macMismatchLabel.setStyleSheet("color: #c75c1e; font-weight: 600;")
            except Exception:
                pass
            self.macMismatchLabel.setVisible(False)

            self.deviceLabel=QtWidgets.QLabel("GNSS")
            self.deviceCombo=QtWidgets.QComboBox(); self.deviceCombo.setFixedWidth(360)
            self.deviceHelp=QtWidgets.QLabel("")
            self.btnApplyGnss = QtWidgets.QPushButton("Update"); self.btnApplyGnss.setVisible(False)
            self.btnApplyGnss.clicked.connect(self._apply_gnss_selection)  # type: ignore[attr-defined]
            self._populate_gnss()  # type: ignore[attr-defined]
            self.deviceCombo.currentIndexChanged.connect(lambda _: self._on_gnss_selection_changed())  # type: ignore[attr-defined]

            self.settingsGb = QtWidgets.QGroupBox("Settings")
            try:
                self.settingsGb.setObjectName("layerBox")
            except Exception:
                pass
            sLay = QtWidgets.QHBoxLayout(self.settingsGb); sLay.setContentsMargins(8,4,8,8)
            try:
                self.settingsGb.setStyleSheet("QGroupBox { margin-top: 0px; }")
            except Exception:
                pass
            sLay.addWidget(self.networkLabel)
            sLay.addWidget(self.networkValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macTitle)
            sLay.addWidget(self.macValueLabel)
            sLay.addSpacing(12)
            sLay.addWidget(self.macRegisteredTitle)
            sLay.addWidget(self.macRegisteredValue)
            sLay.addSpacing(6)
            sLay.addWidget(self.macMatchCheck)
            sLay.addWidget(self.macMismatchLabel)
            sLay.addSpacing(24)
            sLay.addWidget(self.deviceLabel)
            sLay.addWidget(self.deviceCombo)
            sLay.addSpacing(12)
            sLay.addWidget(self.deviceHelp)
            sLay.addSpacing(12)
            try:
                policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
                self.btnApplyGnss.setSizePolicy(policy)
            except Exception:
                pass
            sLay.addWidget(self.btnApplyGnss)
            sLay.addStretch(1)
        if hasattr(self, 'networkValueLabel'):
            self._refresh_network_info()  # type: ignore[attr-defined]

        # Rolling 24h chart header and widget
        self.online24Label = QtWidgets.QLabel("Online last 24h: -")
        self.online24Label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        try:
            self.online24Label.setStyleSheet("font-size: 24px; font-weight: 700;")
            policy_label = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            self.online24Label.setSizePolicy(policy_label)
            self.online24Label.setMinimumHeight(26)
        except Exception:
            pass
        try:
            self.online24Label.setStyleSheet("font-size: 24px; font-weight: 700;")
        except Exception:
            pass
        self.chart=HourlyBar(self)
        try:
            policy_chart = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
            self.chart.setSizePolicy(policy_chart)
        except Exception:
            pass
        try:
            # Slightly smaller so x-axis labels are fully visible
            self.chart.setMinimumHeight(140)
        except Exception:
            pass

        self.chkService=QtWidgets.QLabel("Service: -")
        self.chkInternet=QtWidgets.QLabel("Internet: -")
        self.chkLocal=QtWidgets.QLabel("Local cache: -")
        self.btnSelfCheck=QtWidgets.QPushButton("Run Self-check")

        icon = QtGui.QIcon(str(miner_icon_path()))
        self.tray = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray.setToolTip(f"FRY {DISPLAY_NAME}")
        menu = QtWidgets.QMenu()
        try:
            act_clean = menu.addAction("Clean previous versions...")
            act_clean.triggered.connect(self._on_clean_clicked)  # type: ignore[attr-defined]
        except Exception:
            pass
        act_quit = menu.addAction("Quit"); act_quit.triggered.connect(self._on_tray_quit)
        self.tray.setContextMenu(menu); self.tray.show()
        self.tray.activated.connect(self._on_tray_activated)

        dashboard=QtWidgets.QWidget(); dashLay=QtWidgets.QVBoxLayout(dashboard)
        try:
            dashLay.setContentsMargins(8, 4, 8, 8)
            # Slightly tighter spacing between stacked sections
            dashLay.setSpacing(4)
        except Exception:
            pass
        dashLay.addWidget(self.banner)
        # Exclusive-pair conflict banner (hidden by default)
        self.conflictBanner = QtWidgets.QLabel("")
        try:
            self.conflictBanner.setStyleSheet("background:#7c2d12; color:#fff; padding:8px; border-radius:8px; font-weight:600;")
            self.conflictBanner.setWordWrap(True)
            self.conflictBanner.hide()
        except Exception:
            pass
        dashLay.addWidget(self.conflictBanner)
        dashLay.addLayout(form)
        # Update status label (auto-updater messages)
        self.updateMsg = QtWidgets.QLabel("")
        try:
            self.updateMsg.setStyleSheet("color:#fbbf24; font-weight:600;")
            self.updateMsg.setWordWrap(True)
            # Keep hidden until there is a message to show, so it doesn't add extra space
            self.updateMsg.setVisible(False)
        except Exception:
            pass
        dashLay.addWidget(self.updateMsg)
        # Inline notice area: reuse the form's second row (regexHint) directly beneath miner_key
        self.noticeMsg = self.regexHint
        try:
            # Single line, left + vertical center, themed like the Update button
            self.noticeMsg.setText("")
            self.noticeMsg.setWordWrap(False)
            self.noticeMsg.setVisible(False)
            self.noticeMsg.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
            self.noticeMsg.setMinimumHeight(20)
            self.noticeMsg.setStyleSheet("background:#7c2d12; color:#ffffff; font-weight:600; border-radius:12px; padding:6px 12px;")
        except Exception:
            pass
        self.btnRestartUpdate = QtWidgets.QPushButton('Restart to Update')
        self.btnRestartUpdate.setVisible(False)
        try:
            self.btnRestartUpdate.setStyleSheet('font-weight:600;')
            policy_restart = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
            self.btnRestartUpdate.setSizePolicy(policy_restart)
        except Exception:
            pass
        try:
            self.btnRestartUpdate.clicked.connect(self._on_restart_update)  # type: ignore[attr-defined]
        except Exception:
            pass
        dashLay.addWidget(self.btnRestartUpdate)
        # (Removed duplicate updateMsg + button block to reduce spacing)
        # Insert Settings layer (row with Network / MAC / Update) if present
        try:
            if hasattr(self, 'settingsGb'):
                dashLay.addWidget(self.settingsGb)
        except Exception:
            pass
        # uniform spacing handled by layout spacing
        # Rolling 24h + 7d layer (Online status), split vertically (two columns)
        onlineGb = QtWidgets.QGroupBox("Online status"); QtWidgets.QHBoxLayout(onlineGb)
        self.onlineGb = onlineGb
        try:
            onlineGb.setObjectName("layerBox")
        except Exception:
            pass
        # Prepare 7-day widgets
        self.online7Label = QtWidgets.QLabel("Online last 7d: -")
        self.online7Label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        try:
            self.online7Label.setStyleSheet("font-size: 24px; font-weight: 700;")
            self.online7Label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            self.online7Label.setMinimumHeight(26)
        except Exception:
            pass
        self.chart7 = Rolling7Bar(self)
        try:
            self.chart7.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
            self.chart7.setMinimumHeight(140)
        except Exception:
            pass
        # Left: 7-day rolling
        leftPane = QtWidgets.QWidget(); leftLay = QtWidgets.QVBoxLayout(leftPane)
        leftLay.addWidget(self.online7Label)
        leftLay.addWidget(self.chart7)
        # Right: actual 24h status
        rightPane = QtWidgets.QWidget(); rightLay = QtWidgets.QVBoxLayout(rightPane)
        rightLay.addWidget(self.online24Label)
        rightLay.addWidget(self.chart)
        # Add panes to layout safely even if the local variable was optimized away
        try:
            lay = onlineGb.layout() or QtWidgets.QHBoxLayout(onlineGb)
        except Exception:
            lay = QtWidgets.QHBoxLayout(onlineGb)
        lay.addWidget(leftPane)
        lay.addWidget(rightPane)
        try:
            onlineGb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        dashLay.addWidget(onlineGb)
        try:
            # Scale charts with group height
            self.onlineGb.installEventFilter(self)
        except Exception:
            pass
        # uniform spacing handled by layout spacing
        # Live data layer (moved after online status)
        liveGb = QtWidgets.QGroupBox("Live data"); liveLay = QtWidgets.QHBoxLayout(liveGb)
        try:
            liveGb.setObjectName("layerBox")
        except Exception:
            pass
        # Left: miner_type logo centered
        leftLogoPane = QtWidgets.QWidget(); leftLogoLay = QtWidgets.QVBoxLayout(leftLogoPane)
        leftLogoLay.setContentsMargins(8, 8, 8, 8)
        try:
            pm = QtGui.QPixmap(str(miner_icon_path()))
        except Exception:
            pm = QtGui.QPixmap()
        self.logoLabel = LogoLabel(pm, self)
        leftLogoLay.addStretch(1)
        leftLogoLay.addWidget(self.logoLabel, 1, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        leftLogoLay.addStretch(1)
        liveLay.addWidget(leftLogoPane)

        # Right: live data content
        rightLivePane = QtWidgets.QWidget(); rightLiveLay = QtWidgets.QVBoxLayout(rightLivePane)
        # Add a top stretch so content block can be vertically centered
        try:
            rightLiveLay.addStretch(1)
        except Exception:
            pass
        self.liveInfo=QtWidgets.QLabel('')
        rightLiveLay.addWidget(self.liveInfo, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        # Load pluggable live data panel for this miner group
        self.livePanel = None
        try:
            from LiveData import load_live_panel
            self.livePanel = load_live_panel(GROUP, width=800)
            if self.livePanel is not None:
                try:
                    panel = getattr(self, 'livePanel', None)
                    if GROUP == "Decibel" and panel is not None and hasattr(panel, 'set_device_label') and hasattr(self, 'deviceCombo'):
                        cast(Any, panel).set_device_label(self.deviceCombo.currentText())
                    if GROUP == "Satellite" and panel is not None and hasattr(panel, 'set_device_label') and hasattr(self, 'deviceCombo'):
                        cast(Any, panel).set_device_label(self.deviceCombo.currentText())
                except Exception:
                    pass
                # Show the panel for all groups; hide the old label to keep appearance
                try:
                    # Constrain panel vertically so it doesn't consume all space; allow horizontal expansion
                    try:
                        self.livePanel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
                        self.livePanel.setMaximumHeight(max(80, int(self.livePanel.sizeHint().height())))
                    except Exception:
                        pass
                    rightLiveLay.addWidget(self.livePanel, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
                    if GROUP in ("Decibel", "Satellite"):
                        self.liveInfo.setVisible(False)
                except Exception:
                    pass
        except Exception:
            self.livePanel = None
        try:
            # Bottom stretch to balance top stretch and center the content block
            rightLiveLay.addStretch(1)
        except Exception:
            pass
        try:
            # Let live data expand to full available width
            liveGb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        try:
            # Remove previous max-width cap
            liveGb.setMaximumWidth(16777215)
        except Exception:
            pass
        # Add right pane and set stretch 1:2
        liveLay.addWidget(rightLivePane)
        try:
            liveLay.setStretch(0, 1)
            liveLay.setStretch(1, 2)
        except Exception:
            pass
        try:
            dashLay.addWidget(liveGb)
        except Exception:
            dashLay.addWidget(liveGb)

        # Service controls: Install (when NOT INSTALLED) and Start (when STOPPED)
        self.btnInstall = QtWidgets.QPushButton("Install service")
        self.btnInstall.setVisible(False)
        self.btnInstall.clicked.connect(self._on_install_clicked)  # type: ignore[attr-defined]
        self.btnStart = QtWidgets.QPushButton("Start service")
        self.btnStart.setVisible(False)
        self.btnStart.clicked.connect(self._on_start_clicked)  # type: ignore[attr-defined]
        grid=QtWidgets.QGridLayout()
        grid.addWidget(self.chkService,0,0); grid.addWidget(self.chkInternet,0,1)
        grid.addWidget(self.chkLocal,1,0); grid.addWidget(self.btnInstall,0,2); grid.addWidget(self.btnStart,1,2)
        if DEV or os.environ.get("FRY_DEV")=="1":
            self.btnViewCache = QtWidgets.QPushButton("View cache")
            self.btnViewCache.clicked.connect(open_today_cache)
            grid.addWidget(self.btnViewCache,1,2)
        gb=QtWidgets.QGroupBox("Self-check"); gb.setLayout(grid)
        try:
            gb.setObjectName("layerBox")
        except Exception:
            pass
        try:
            gb.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        except Exception:
            pass
        dashLay.addWidget(gb)

        # (Live area moved above)

        root=QtWidgets.QVBoxLayout(self); root.addWidget(dashboard)

        # no manual self-check button; refresh automatically

        # --- auto-updater ---
        self._init_auto_update(reason="initial")

        # Start periodic version monitor to surface backend requirement changes
        try:
            self._start_version_monitor()  # type: ignore[attr-defined]
        except Exception:
            pass

        # Miner key first-run (skipped if pre-checked in main())
        if not _PRECHECK_OK:
            ex = read_miner_key()
            if ex:
                self.keyEdit.setText(ex); self.keyEdit.setReadOnly(True)
                # Re-validate existing key on startup; exit if invalid or not found
                try:
                    if not KEY_PATTERN.match(ex):
                        raise RuntimeError('bad format')
                    if not self._check_key_exists(ex):
                        raise RuntimeError('key_not_found')
                    ok, det = self._check_key_concurrency(ex)
                    if not ok and isinstance(det, dict) and det:
                        raise RuntimeError('key_in_use' + _format_conflict_details(det))
                    vok, needed, installed = self._check_key_version(ex)
                    if vok is False and (needed or installed):
                        fry_warn(self, 'Update Recommended', f'This device requires version {needed}, but you have {installed}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update.')
                except Exception as e:
                    msg = 'The saved miner_key is invalid. Please relaunch and enter a valid key.'
                    if str(e) == 'key_not_found':
                        msg = 'The saved miner_key was not found. Please relaunch and enter a valid key.'
                    elif str(e).startswith('key_in_use'):
                        msg = _in_use_message(ex, str(e).removeprefix('key_in_use'))
                    fry_error(self, 'Miner Key', msg)
                    QtWidgets.QApplication.quit(); return
            else:
                key, ok = ask_miner_key(self)
                if not ok or not key:
                    fry_error(self, 'Miner Key', 'Miner key is required. Exiting.')
                    QtWidgets.QApplication.quit(); return
                self.keyEdit.setText(key)
                try:
                    self._validated_key()  # type: ignore[attr-defined]
                    self.keyEdit.setReadOnly(True)
                    # Warn (do not block) if a newer version is required
                    vok, needed, installed = self._check_key_version(key.strip())
                    if vok is False and (needed or installed):
                        fry_warn(self, 'Update Recommended', f'This device requires version {needed}, but you have {installed}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update.')
                except Exception as e:
                    msg = 'The miner_key format is invalid. Please relaunch and try again.'
                    if str(e) == 'key_not_found':
                        msg = 'The miner_key was not found. Please verify your key and relaunch.'
                    elif str(e).startswith('key_in_use'):
                        msg = _in_use_message(key.strip(), str(e).removeprefix('key_in_use'))
                    elif str(e) == 'key_check_error':
                        # Proceed, but make it clear we could not verify pre-start.
                        fry_warn(self, 'Miner Key', 'Could not verify miner_key status (network/database error). Proceeding to start; the service will enforce single-instance if needed.')
                        self.keyEdit.setReadOnly(True)
                        # Do not quit here; allow the flow to continue
                        return
                    fry_error(self, 'Miner Key', msg)
                    QtWidgets.QApplication.quit(); return
        else:
            try:
                self.keyEdit.setText(read_miner_key())
                self.keyEdit.setReadOnly(True)
            except Exception:
                pass

        # On launch: proactively clean older versions for this miner type
        if sys.platform.startswith('win'):
            try:
                if self._has_old_services_or_processes():  # type: ignore[attr-defined]
                    if ensure_admin_windows():
                        self._cleanup_old_versions()  # type: ignore[attr-defined]
                    else:
                        # Relaunch elevated once to perform cleanup
                        if relaunch_as_admin():
                            QtWidgets.QApplication.quit(); return
                # If service is missing, show Install button
                if not service_exists(MINER_CODE):
                    self.btnInstall.setVisible(True)
            except Exception:
                # Best-effort; continue
                pass

        QtCore.QTimer.singleShot(200, self.run_selfcheck)  # type: ignore[attr-defined]
        self._poller = QtCore.QTimer(self); self._poller.timeout.connect(self.run_selfcheck)  # type: ignore[attr-defined]; self._poller.start(30000)

        # Start live worker
        self._start_live()  # type: ignore[attr-defined]

    # ----- tray restore -----
    def _on_tray_activated(self, reason):
        if reason in (QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                      QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick):
            try:
                self.showNormal()
                self.setWindowState(self.windowState() & ~QtCore.Qt.WindowState.WindowMinimized)
                self.raise_()
                self.activateWindow()
            except Exception:
                self.show()

    def closeEvent(self, event):
        """Minimize to tray instead of closing when user clicks the X."""
        try:
            if self.tray and self.tray.isVisible():
                self.hide()
                try:
                    # Best-effort friendly hint (only once per session)
                    if not getattr(self, "_trayHintShown", False):
                        self.tray.showMessage(
                            f"FRY {DISPLAY_NAME}",
                            "Still running in the system tray. Use Quit to exit.",
                            QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                            2500,
                        )
                        self._trayHintShown = True
                except Exception:
                    pass
                event.ignore(); return
        except Exception:
            pass
        super().closeEvent(event)

    def _on_tray_quit(self):
        """Quit from tray: stop service/process for this miner type, then exit."""
        try:
            # Try to stop the service gracefully first
            if sys.platform.startswith('win'):
                try:
                    subprocess.run(["sc", "stop", APP_SERVICE_WIN], capture_output=True, text=True)
                    # Give SCM a moment, then delete the service registration
                    try:
                        for _ in range(10):
                            q = subprocess.run(["sc", "query", APP_SERVICE_WIN], capture_output=True, text=True)
                            if "STOPPED" in (q.stdout or "") or q.returncode != 0:
                                break
                            QtCore.QThread.msleep(200)
                    except Exception:
                        pass
                    subprocess.run(["sc", "delete", APP_SERVICE_WIN], capture_output=True, text=True)
                except Exception:
                    pass
            else:
                try:
                    subprocess.run(["systemctl", "disable", "--now", APP_SERVICE_LIN], capture_output=True, text=True)
                    try:
                        subprocess.run(["systemctl", "reset-failed", APP_SERVICE_LIN], capture_output=True, text=True)
                    except Exception:
                        pass
                except Exception:
                    pass
            # Kill any remaining processes for this miner type; also remove local lock
            try:
                self._force_local_cleanup_current_type()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Also remove scheduled autostart task so GUI won't relaunch automatically
            try:
                remove_gui_autostart_task()
            except Exception:
                pass
        except Exception:
            pass
        QtWidgets.QApplication.quit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # TopBanner handles painting/scaling internally

    # ---- helpers ----
    def _preflight_service_files(self) -> bool:
        """Ensure required files exist in the ProgramData service directory.
        - Ensures minerkey.txt exists and has a valid format; attempts to write from UI field if missing/invalid.
        Returns True if everything looks OK, False if user must fix input.
        """
        try:
            base = data_dir_gui()
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            key_path = base / 'minerkey.txt'
            cur = ''
            try:
                if key_path.exists():
                    cur = key_path.read_text(encoding='utf-8', errors='ignore').strip()
            except Exception:
                cur = ''
            ui_key = (self.keyEdit.text() or '').strip()
            chosen = None
            # Prefer a valid UI-entered key; fall back to existing ProgramData key
            if KEY_PATTERN.match(ui_key or ''):
                chosen = ui_key
            elif KEY_PATTERN.match(cur or ''):
                chosen = cur
            else:
                QtWidgets.QMessageBox.critical(self, 'Miner key required', f'Enter a valid miner_key (pattern {MINER_CODE}-[A-Z0-9]{{32}}) before starting the service.')
                return False
            # Persist/refresh ProgramData key file to match the chosen key
            try:
                key_path.write_text(chosen + "\n", encoding='utf-8')
            except Exception:
                pass
            # Block if miner_key is already active on another device (global lease held)
            try:
                okc, det = _check_key_concurrency_global(chosen)
                if not okc:
                    _cleanup_local_identity_and_logs()
                    fry_error(self, 'Miner Key In Use', _in_use_message(chosen, _format_conflict_details(det)))
                    return False
            except Exception:
                pass
            return True
        except Exception:
            return True
    def _check_key_exists(self, key: str) -> bool:
        """Check backend for miner_key existence using service's check mode."""
        try:
            cmd: list[str] = []
            if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
                svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
                if svc.exists():
                    cmd = [str(svc), "--check-key", key]
            if not cmd:
                svc_py = app_dir() / "miner_online_simple.py"
                if svc_py.exists():
                    cmd = [sys.executable, str(svc_py), "--check-key", key]
            if not cmd:
                log_step("check_key_exists: no checker", {"key": key})
                return False
            log_step("check_key_exists: running", {"cmd": cmd})
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            ok = (p.returncode == 0)
            log_step("check_key_exists: done", {"rc": p.returncode, "ok": ok})
            return ok
        except Exception:
            log_step("check_key_exists: error")
            return False

    def _check_key_concurrency(self, key: str) -> tuple[bool, dict | None]:
        """Return (ok, err). ok=False if miner_key is active elsewhere."""
        try:
            cmd: list[str] = []
            if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
                svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
                if svc.exists():
                    cmd = [str(svc), "--check-concurrency", key]
            if not cmd:
                svc_py = app_dir() / "miner_online_simple.py"
                if svc_py.exists():
                    cmd = [sys.executable, str(svc_py), "--check-concurrency", key]
            if not cmd:
                log_step("check_concurrency: no checker", {"key": key})
                return True, None  # best-effort: don't block if checker missing
            log_step("check_concurrency: running", {"cmd": cmd})
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            try:
                doc = json.loads((p.stdout or "").strip() or "{}")
            except Exception:
                doc = {}
            if p.returncode == 0:
                log_step("check_concurrency: clear", {"rc": p.returncode})
                return True, doc if doc else None
            if p.returncode == 8:
                log_step("check_concurrency: conflict", {"rc": p.returncode, "doc": doc})
                return False, (doc.get("conflict") if isinstance(doc, dict) else {"reason": "conflict"})
            log_step("check_concurrency: error", {"rc": p.returncode})
            return False, (doc if doc else {"reason": "error"})
        except Exception:
            log_step("check_concurrency: exception")
            return False, {"reason": "exception"}

    def _check_key_version(self, key: str) -> tuple[bool | None, str | None, str | None]:
        """Return (ok, needed, installed) using service's version check.
        ok=False means current binary is below software_version_needed.
        Returns (None, None, None) if check is unavailable.
        """
        try:
            cmd: list[str] = []
            if getattr(sys, "frozen", False) and sys.platform.startswith("win"):
                svc = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
                if svc.exists():
                    cmd = [str(svc), "--check-version", key]
            if not cmd:
                svc_py = app_dir() / "miner_online_simple.py"
                if svc_py.exists():
                    cmd = [sys.executable, str(svc_py), "--check-version", key]
            if not cmd:
                return None, None, None
            log_step("check_version: running", {"cmd": cmd})
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            needed = installed = None
            ok: bool | None = None
            try:
                doc = json.loads(p.stdout.strip() or "{}")
                ok = bool(doc.get("ok")) if "ok" in doc else (p.returncode == 0)
                needed = doc.get("needed")
                installed = doc.get("installed") or VERSION
            except Exception:
                ok = (p.returncode == 0)
            log_step("check_version: done", {"rc": p.returncode, "ok": ok, "needed": needed, "installed": installed})
            return ok, needed, installed
        except Exception:
            return None, None, None

    def _init_auto_update(self, *, reason: str = "initial") -> None:
        global _FORCE_UPDATE_REQUIRED
        try:
            cfg = load_config() or {}
            repo_s = cfg.get('update_repo')
            token_cfg = cfg.get('github_token')
            token_present = isinstance(token_cfg, str) and bool(token_cfg.strip())
            if token_present and not os.environ.get('GITHUB_TOKEN'):
                os.environ['GITHUB_TOKEN'] = cast(str, token_cfg)
            use_github = bool(cfg.get('use_github'))
            sw_flag_raw = cfg.get('software_uptodate')
            sw_flag = None
            if isinstance(sw_flag_raw, str):
                sw_flag_norm = sw_flag_raw.strip().lower()
                if sw_flag_norm in ('false', '0', 'no', 'off'):
                    sw_flag = False
                elif sw_flag_norm in ('true', '1', 'yes', 'on'):
                    sw_flag = True
            elif isinstance(sw_flag_raw, bool):
                sw_flag = sw_flag_raw
            if sw_flag is None:
                sw_flag = True
            force_required = bool(_FORCE_UPDATE_REQUIRED)
            if force_required:
                sw_flag = False
            log_step("auto_update: config", {
                "use_github": use_github,
                "software_uptodate_raw": sw_flag_raw if sw_flag_raw is not None else None,
                "software_uptodate_effective": sw_flag,
                "force_required": force_required,
                "repo": repo_s or "-",
                "token_present": token_present,
                "context": reason,
            })
            if sw_flag:
                log_step("auto_update: skip", {"reason": "already_uptodate", "context": reason})
                return
            if not use_github:
                log_step("auto_update: skip", {"reason": "updates_disabled", "context": reason})
                return
            owner = repo = None
            if isinstance(repo_s, str) and '/' in repo_s:
                parts = repo_s.split('/', 1)
                owner, repo = parts[0].strip(), parts[1].strip()
            log_step("auto_update: prepared", {
                "owner": owner or "default",
                "repo": repo or "default",
                "force_required": force_required,
                "context": reason,
            })

            if getattr(self, 'updater', None):
                log_step("auto_update: reuse", {
                    "owner": owner or "default",
                    "repo": repo or "default",
                    "context": reason,
                })
                try:
                    if hasattr(self.updater, 'check_now'):
                        QtCore.QTimer.singleShot(0, lambda: self.updater.check_now(download_if_newer=True))
                except Exception:
                    pass
                return

            def _on_status(msg: str):
                try:
                    msg_text = str(msg or '')
                    self.updateMsg.setText(msg_text)
                    log_step("auto_update: status", {"message": msg_text, "context": reason})
                except Exception:
                    pass

            def _on_progress(got: int, total: int | None):
                try:
                    if total:
                        self.updateMsg.setText(f"Downloading update: {got//1024} / {total//1024} KB")
                    else:
                        self.updateMsg.setText(f"Downloading update: {got//1024} KB")
                except Exception:
                    pass

            def _on_downloaded(path, ver):
                try:
                    self._downloadedUpdatePath = str(getattr(path, 'absolute', lambda: path)()) if hasattr(path, 'absolute') else str(path)
                except Exception:
                    try:
                        self._downloadedUpdatePath = str(path)
                    except Exception:
                        self._downloadedUpdatePath = ''
                try:
                    display_name = getattr(path, 'name', str(path))
                    self.updateMsg.setText(f"Update {ver} downloaded: {display_name}")
                    log_step("auto_update: downloaded", {
                        "version": ver,
                        "path": self._downloadedUpdatePath or str(path),
                        "context": reason,
                    })
                    if self._downloadedUpdatePath:
                        self.btnRestartUpdate.setVisible(True)
                except Exception:
                    pass

            try:
                interval_env = os.environ.get('FRY_UPDATE_INTERVAL_SEC')
                interval_sec = int(interval_env) if interval_env and interval_env.isdigit() else None
            except Exception:
                interval_sec = None
            log_step("auto_update: starting", {
                "interval_sec": interval_sec or "default",
                "owner": owner or "default",
                "repo": repo or "default",
                "context": reason,
            })
            self.updater = GuiAutoUpdater(MINER_CODE, VERSION, owner=owner, repo=repo,
                                          interval_sec=interval_sec,
                                          on_status=_on_status,
                                          on_progress=_on_progress,
                                          on_downloaded=_on_downloaded)
            self.updater.start()
            log_step("auto_update: started", {
                "interval_sec": getattr(self.updater, 'interval_sec', interval_sec or "default"),
                "owner": owner or "default",
                "repo": repo or "default",
                "context": reason,
            })
            try:
                if reason != "initial" and hasattr(self.updater, 'check_now'):
                    QtCore.QTimer.singleShot(0, lambda: self.updater.check_now(download_if_newer=True))
            except Exception:
                pass
        except Exception as e:
            log_step("auto_update: init failed", {
                "error": str(e),
                "context": reason,
            })
            pass

    def _on_restart_update(self):
        path = getattr(self, '_downloadedUpdatePath', '') or ''
        if path and os.path.exists(path):
            log_step('auto_update: restart', {'path': path})
            try:
                if sys.platform.startswith('win'):
                    os.startfile(path)
                elif sys.platform.startswith('darwin'):
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
            except Exception as exc:
                safe_msg = f'Failed to launch update: {exc}'
                log_step('auto_update: restart failed', {'error': safe_msg})
                fry_error(self, 'Update', safe_msg)
                return
            QtWidgets.QApplication.quit()
        else:
            fry_warn(self, 'Update', 'Update package is no longer available. Please check for updates again.')
    def _start_version_monitor(self):
        self._lastNeeded = cast(Optional[str], None)
        try:
            # Poll interval (seconds). Prefer builder variable in config_profile (VERSION_CHECK_SEC),
            # fall back to env FRY_VERSION_CHECK_SEC, then default 600s. Minimum 60s.
            try:
                import config_profile as _cp
                sec_cfg = int(getattr(_cp, 'VERSION_CHECK_SEC', 600))
            except Exception:
                sec_cfg = 600
            try:
                sec_env = os.environ.get('FRY_VERSION_CHECK_SEC')
                sec_env_i = int(sec_env) if (sec_env and str(sec_env).isdigit()) else None
            except Exception:
                sec_env_i = None
            sec = sec_env_i if sec_env_i else sec_cfg
            interval_ms = max(60_000, int(sec) * 1000)
            self._verTimer = QtCore.QTimer(self)
            self._verTimer.setInterval(interval_ms)
            self._verTimer.timeout.connect(self._poll_required_version)
            self._verTimer.start()
            # Initial check shortly after startup
            QtCore.QTimer.singleShot(2000, self._poll_required_version)
        except Exception:
            pass

    def _poll_required_version(self):
        try:
            global _FORCE_UPDATE_REQUIRED
            # Obtain current miner key from UI or disk
            key = ''
            try:
                key = (self.keyEdit.text() or '').strip()
            except Exception:
                key = ''
            if not key:
                try:
                    key = read_miner_key().strip()
                except Exception:
                    key = ''
            if not key or not KEY_PATTERN.match(key or ''):
                return
            # Use service-driven check for consistency with backend policy
            vok, needed, installed = self._check_key_version(key)
            # Only react to non-empty requirements; show inline notice instead of popup
            if isinstance(needed, str) and needed:
                changed = (getattr(self, '_lastNeeded', None) != needed)
                # Remember latest requirement
                self._lastNeeded = needed
                try:
                    # Ensure label exists
                    if not hasattr(self, 'noticeMsg'):
                        self.noticeMsg = QtWidgets.QLabel("")
                    # If outdated, display persistent notice in the header area
                    if (vok is False):
                        msg = f"This device requires version {needed}, but you have {installed or VERSION}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update."
                        try:
                            self.noticeMsg.setText(msg)
                            # Keep the same theme as the Update button
                            self.noticeMsg.setStyleSheet("background:#7c2d12; color:#ffffff; font-weight:600; border-radius:12px; padding:6px 12px;")
                            self.noticeMsg.setWordWrap(True)
                            self.noticeMsg.setVisible(True)
                        except Exception:
                            pass
                        if not _FORCE_UPDATE_REQUIRED:
                            _FORCE_UPDATE_REQUIRED = True
                            log_step("auto_update: force", {"needed": needed, "installed": installed, "context": "version_monitor"})
                            try:
                                self._init_auto_update(reason="version_monitor")
                            except Exception:
                                pass
                        elif not getattr(self, 'updater', None):
                            try:
                                self._init_auto_update(reason="version_monitor")
                            except Exception:
                                pass
                    else:
                        # Clear message when no longer outdated
                        try:
                            self.noticeMsg.clear(); self.noticeMsg.setVisible(False)
                        except Exception:
                            pass
                        if _FORCE_UPDATE_REQUIRED:
                            _FORCE_UPDATE_REQUIRED = False
                            log_step("auto_update: force_cleared", {"needed": needed, "installed": installed, "context": "version_monitor"})
                except Exception:
                    pass
        except Exception:
            pass

    def _validated_key(self)->str:
        key=self.keyEdit.text().strip()
        if not KEY_PATTERN.match(key):
            raise RuntimeError("bad key")
        if not self._check_key_exists(key):
            raise RuntimeError("key_not_found")
        ok, det = self._check_key_concurrency(key)
        if not ok:
            # Distinguish a real conflict (details present) from check error
            if isinstance(det, dict) and det:
                raise RuntimeError("key_in_use" + _format_conflict_details(det))
            raise RuntimeError("key_check_error")
        write_miner_key(key); return key

    def service_status_str(self) -> str:
        try:
            if sys.platform.startswith("win"):
                out = subprocess.run(["sc","query",APP_SERVICE_WIN], capture_output=True, text=True)
                s = (out.stdout or "")
                if "RUNNING" in s: return "RUNNING"
                # Detect transitional state to avoid false negatives during startup
                if "START_PENDING" in s or "START PENDING" in s: return "START_PENDING"
                if "STOPPED" in s: return "STOPPED"
                return "NOT INSTALLED"
            else:
                out = subprocess.run(["systemctl","is-active",APP_SERVICE_LIN], capture_output=True, text=True)
                return out.stdout.strip() if out.stdout.strip() else "inactive/not installed"
        except Exception as e:
            return f"error: {e}"

    # --- network display helpers ---
    def _refresh_network_info(self, *, restart_live: bool = False):
        if not hasattr(self, 'networkValueLabel'):
            return
        try:
            iface, mac = self._detect_active_network()
        except Exception:
            iface, mac = ("", "")
        changed = bool(iface and iface != (self.activeNetworkName or ""))
        self.activeNetworkName = iface or ""
        self.activeMacAddress = mac or ""
        try:
            self.networkValueLabel.setText(self.activeNetworkName or "-")
        except Exception:
            pass
        try:
            self.macValueLabel.setText(self.activeMacAddress or "-")
        except Exception:
            pass
        if self.activeMacAddress:
            self._persist_active_mac(self.activeMacAddress)
        registered, mismatch_flag = self._load_registered_mac_info()
        try:
            if hasattr(self, 'macRegisteredValue'):
                self.macRegisteredValue.setText(registered or "-")
        except Exception:
            pass
        self._update_mac_match_indicator(registered, self.activeMacAddress, mismatch_flag)
        if restart_live and changed and GROUP in ("Bandwidth", "AIEdge") and getattr(self, '_liveWorker', None):
            try:
                self._restart_live()
            except Exception:
                pass

    def _detect_active_network(self) -> tuple[str, str]:
        local_ip = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = ""
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
        except Exception:
            return ("", "")
        if local_ip:
            for name, addr_list in addrs.items():
                try:
                    if any(getattr(a, "family", None) == socket.AF_INET and a.address == local_ip for a in addr_list):
                        mac = self._get_mac_for_iface(name, addrs)
                        if mac or getattr(stats.get(name), "isup", False):
                            return (name, mac)
                except Exception:
                    continue
        candidates: list[tuple[str, str, float]] = []
        for name, st in stats.items():
            try:
                if not getattr(st, "isup", False):
                    continue
                lname = name.lower()
                if lname.startswith("lo") or "loopback" in lname:
                    continue
                mac = self._get_mac_for_iface(name, addrs)
                speed = float(getattr(st, "speed", 0.0) or 0.0)
                candidates.append((name, mac, speed))
            except Exception:
                continue
        if not candidates:
            for name in stats.keys():
                mac = self._get_mac_for_iface(name, addrs)
                if mac:
                    return (name, mac)
            return ("", "")
        candidates.sort(key=lambda item: item[2], reverse=True)
        name, mac, _ = candidates[0]
        return (name, mac)

    def _get_mac_for_iface(self, iface: str, addrs=None) -> str:
        try:
            if addrs is None:
                addrs = psutil.net_if_addrs()
            for addr in addrs.get(iface, []):
                fam = getattr(addr, "family", None)
                if fam is None:
                    continue
                link_family = getattr(psutil, "AF_LINK", None)
                if link_family is not None and fam == link_family:
                    return addr.address
                try:
                    if fam == getattr(socket, "AF_PACKET", None):
                        return addr.address
                except Exception:
                    pass
                try:
                    if fam == getattr(socket, "AF_LINK", None):
                        return addr.address
                except Exception:
                    pass
                if isinstance(fam, str) and fam.endswith("AF_LINK"):
                    return addr.address
                name_attr = getattr(fam, 'name', None)
                if name_attr == 'AF_LINK':
                    return addr.address
        except Exception:
            pass
        return ""

    def _persist_active_mac(self, mac: str):
        if not mac:
            return
        if mac == getattr(self, '_persistedMacValue', None):
            return
        try:
            p = data_dir_gui() / "miner_mac.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(mac.strip() + "\n")
            self._persistedMacValue = mac
        except Exception:
            pass

    def _load_registered_mac_info(self) -> tuple[str, bool | None]:
        key = (self.keyEdit.text() or '').strip()
        if not key:
            return ('', None)
        registered = ''
        mismatch_flag: bool | None = None
        client = None
        try:
            cfg = load_config()
            mongo_uri = cfg.get('mongo_uri', 'mongodb://localhost:27017/PoC')
            tlsCAFile = cfg.get('tlsCAFile')
            client = connect_mongo(mongo_uri, tlsCAFile)
            try:
                doc = client['PoC']['hardware'].find_one(
                    {'miner_key': key},
                    {'mac_registered': 1, 'mac_mismatch': 1, 'lastUpdated': 1},
                    sort=[('lastUpdated', -1)]
                )
                if isinstance(doc, dict):
                    val = doc.get('mac_registered')
                    if isinstance(val, str) and val.strip():
                        registered = val.strip()
                    mismatch = doc.get('mac_mismatch')
                    if isinstance(mismatch, bool):
                        mismatch_flag = mismatch
                if not registered:
                    reg = registered_mac_from_devices(client, key)
                    if isinstance(reg, str) and reg.strip():
                        registered = reg.strip()
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
        if not registered:
            try:
                import datetime as _dt
                path = date_to_cache_path(_dt.datetime.utcnow().date())
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        doc = json.load(f)
                    if isinstance(doc, dict) and doc.get('miner_key') == key:
                        val = doc.get('mac_registered')
                        mismatch = doc.get('mac_mismatch')
                        if isinstance(val, str) and val.strip():
                            registered = registered or val.strip()
                        if isinstance(mismatch, bool):
                            mismatch_flag = mismatch
            except Exception:
                pass
        return (registered, mismatch_flag)
    def _update_mac_match_indicator(self, registered: str, active: str, mismatch_flag: bool | None):
        if not hasattr(self, 'macMatchCheck'):
            return
        reg_norm = self._norm_mac(registered)
        active_norm = self._norm_mac(active)
        match = False
        have_values = bool(reg_norm) and bool(active_norm)
        if have_values:
            match = (reg_norm == active_norm)
        elif mismatch_flag is not None:
            match = not mismatch_flag
        try:
            self.macMatchCheck.blockSignals(True)
            self.macMatchCheck.setChecked(match)
            self.macMatchCheck.blockSignals(False)
        except Exception:
            pass
        show_check = match and have_values
        show_warn = not match and (have_values or mismatch_flag)
        try:
            self.macMatchCheck.setVisible(bool(show_check))
        except Exception:
            pass
        try:
            self.macMismatchLabel.setVisible(bool(show_warn))
        except Exception:
            pass

    @staticmethod
    def _norm_mac(val: str) -> str:
        if not isinstance(val, str):
            return ""
        return re.sub(r"[^0-9a-f]", "", val.lower())

    # --- decibel & satellite population ---
    def _populate_microphones(self):
        if not HAVE_SD:
            self.deviceCombo.clear(); self.deviceCombo.addItem("No audio API"); return
        try:
            self.deviceCombo.clear()
            devices = sd.query_devices()
            # List only usable input devices
            for idx, dev in enumerate(devices):
                if not isinstance(dev, dict):
                    continue
                try:
                    if int(dev.get('max_input_channels', 0)) <= 0:
                        continue
                    # Validate the device can accept basic input settings without opening a stream
                    try:
                        sd.check_input_settings(device=idx, channels=1)
                    except Exception:
                        continue
                    name = str(dev.get('name', 'input'))
                    display = f"{name} (#{idx})"
                    self.deviceCombo.addItem(display, idx)
                except Exception:
                    continue
        except Exception as e:
            self.deviceCombo.addItem(f"Audio error: {e}")

    def _populate_gnss(self):
        if not HAVE_SERIAL:
            self.deviceCombo.clear(); self.deviceCombo.addItem("No serial API"); return
        try:
            self.deviceCombo.clear()
            ports = serial.tools.list_ports.comports() if hasattr(serial, 'tools') else []
            for p in ports:
                device_name = getattr(p, 'device', '')
                desc = getattr(p, 'description', '')
                label = f"{device_name} - {desc}" if device_name and desc else str(device_name or desc or 'serial')
                if device_name:
                    self.deviceCombo.addItem(label, device_name)
        except Exception as e:
            self.deviceCombo.addItem(f"Serial error: {e}")

    def _on_microphone_selection_changed(self):
        try:
            if hasattr(self, 'btnApplyMic'):
                self.btnApplyMic.setVisible(True)
        except Exception:
            pass

    def _apply_microphone_selection(self):
        try:
            # Apply selected microphone and restart live view only when approved
            self._restart_live()
            if hasattr(self, 'btnApplyMic'):
                self.btnApplyMic.setVisible(False)
            # Update live panel label if present
            try:
                panel = getattr(self, 'livePanel', None)
                if panel is not None and hasattr(panel, 'set_device_label') and hasattr(self, 'deviceCombo'):
                    cast(Any, panel).set_device_label(self.deviceCombo.currentText())
            except Exception:
                pass
        except Exception:
            pass

    def _on_gnss_selection_changed(self):
        try:
            if hasattr(self, 'btnApplyGnss'):
                self.btnApplyGnss.setVisible(True)
        except Exception:
            pass

    def _apply_gnss_selection(self):
        try:
            # Apply selected GNSS and restart live view only when approved
            self._restart_live()
            if hasattr(self, 'btnApplyGnss'):
                self.btnApplyGnss.setVisible(False)
            try:
                panel = getattr(self, 'livePanel', None)
                if panel is not None and hasattr(panel, 'set_device_label') and hasattr(self, 'deviceCombo'):
                    cast(Any, panel).set_device_label(self.deviceCombo.currentText())
            except Exception:
                pass
        except Exception:
            pass

    # --- live worker mgmt ---
    def _start_live(self):
        if self._liveWorker:
            self._liveWorker.stop(); self._liveWorker.wait(1000)
        selector = None; dev_idx = None
        if GROUP in ("Bandwidth","AIEdge"):
            self._refresh_network_info()
            selector = self.activeNetworkName or ""
        elif GROUP=="Decibel":
            dev_idx = self.deviceCombo.currentData()
        elif GROUP=="Satellite":
            selector = self.deviceCombo.currentData()
        self._liveWorker = Worker(GROUP, selector, dev_idx, None)
        self._liveWorker.tick.connect(self._on_live); self._liveWorker.start()

    def _restart_live(self):
        self._start_live()  # type: ignore[attr-defined]

    # --- actions ---
    def refresh_chart(self):
        try:
            counts, labels = rolling_24h_counts_and_labels()
        except Exception:
            counts, labels = ([0]*24, [f"{h:02d}" for h in range(24)])
        try:
            slots = slots_per_hour_today()
        except Exception:
            slots = 6
        try:
            percents = [round(100.0 * c / max(1, slots), 1) for c in counts]
            self.chart.draw_counts(percents, labels)
        except Exception:
            pass
        try:
            pct24 = round(100.0 * sum(counts) / max(1, 24*max(1, slots)), 1)
            self.online24Label.setText(f"Online last 24h: {pct24}%")
        except Exception:
            pass
        # 7-day panel
        try:
            pcts7, lbl7, avg7 = rolling_7d_percents_and_labels()
            self.chart7.draw_percents(pcts7, lbl7)
            self.online7Label.setText(f"Online last 7d: {avg7}%")
        except Exception:
            pass

    def run_selfcheck(self):
        # Service status and controls
        try:
            st = self.service_status_str()
            self.chkService.setText(f"Service: {st}")
            try:
                if st == 'RUNNING' and sys.platform.startswith('win') and not self._prunedOldServiceBinaries:
                    self._prune_old_service_binaries()
                    self._prunedOldServiceBinaries = True
            except Exception:
                pass
            is_win = sys.platform.startswith('win')
            try:
                self.btnInstall.setVisible(bool(is_win and st == 'NOT INSTALLED'))
                self.btnStart.setVisible(bool(is_win and st == 'STOPPED'))
            except Exception:
                pass
        except Exception:
            try:
                self.chkService.setText("Service: error")
            except Exception:
                pass
        # Internet check
        try:
            self.chkInternet.setText(f"Internet: {'UP' if is_internet_up() else 'DOWN'}")
        except Exception:
            pass
        try:
            self._refresh_network_info(restart_live=True)
        except Exception:
            pass
        # Local cache status
        try:
            import datetime as dt, json as _json
            today_path = date_to_cache_path(dt.datetime.utcnow().date())
            if today_path.exists():
                with open(today_path,"r",encoding="utf-8") as f:
                    doc=_json.load(f)
                self.chkLocal.setText(f"Local cache: lastUpdated={doc.get('lastUpdated','-')}")
            else:
                self.chkLocal.setText("Local cache: no file yet")
        except Exception:
            try:
                self.chkLocal.setText("Local cache: error")
            except Exception:
                pass
        # Charts and banners
        try:
            self.refresh_chart()
        except Exception:
            pass
        try:
            self._update_conflict_banner()
        except Exception:
            pass

    def _on_live(self, data: dict):
        # Forward data to pluggable live panel (if present). Do not change labels here;
        # labels are updated only on explicit Apply to avoid premature changes.
        try:
            pnl = getattr(self, 'livePanel', None)
            if pnl is not None and hasattr(pnl, 'on_tick'):
                pnl.on_tick(data)
        except Exception:
            pass
        if GROUP in ("Bandwidth","AIEdge"):
            try:
                self.liveInfo.setText("")
            except Exception:
                pass
            pnl = getattr(self, 'livePanel', None)
            if pnl is not None and hasattr(pnl, 'on_tick'):
                try:
                    pnl.on_tick(data)
                except Exception:
                    pass
        elif GROUP=="Decibel":
            val = data.get('dbfs')
            if val is None and 'err' in data:
                self.liveInfo.setText(f"Device: {self.deviceCombo.currentText()} - error: {data['err']}")
            else:
                self.liveInfo.setText(f"Device: {self.deviceCombo.currentText()} - {val} dBFS")
        elif GROUP=="Satellite":
            self.liveInfo.setText(f"GNSS: {self.deviceCombo.currentText()}")

    # ---- service install ----
    def _install_service_silent(self):
        # Install to a stable location, independent of GUI path
        base = data_dir_gui()
        if sys.platform.startswith('win'):
            nssm_emb = embedded_path('nssm.exe')
            svc_emb  = embedded_path(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe")
            if not nssm_emb.exists() or not svc_emb.exists():
                return
            import shutil
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            nssm = base / 'nssm.exe'; exe  = base / f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe"
            try:
                shutil.copyfile(nssm_emb, nssm); shutil.copyfile(svc_emb, exe)
            except Exception:
                return
            # Ensure the service has access to the miner key at its AppDirectory (ProgramData path)
            if not (base / 'minerkey.txt').exists():
                try:
                    (base / 'minerkey.txt').write_text((self.keyEdit.text() or '').strip() + "\n", encoding="utf-8")
                except Exception:
                    pass
            subprocess.run([str(nssm), 'install', APP_SERVICE_WIN, str(exe)], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppDirectory', str(base)], check=False)
            logs = base / "logs"; logs.mkdir(exist_ok=True)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppStdout', str(logs / 'service.out.log')], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppStderr', str(logs / 'service.err.log')], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppRotateFiles', '1'], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppRotateOnline', '1'], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppRotateBytes', '1048576'], check=False)
            subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'Start', 'SERVICE_AUTO_START'], check=False)
            # Harden: auto-restart on exit (so it won't remain STOPPED)
            try:
                subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppExit', 'Default', 'Restart'], check=False)
                subprocess.run([str(nssm), 'set', APP_SERVICE_WIN, 'AppRestartDelay', '5000'], check=False)
            except Exception:
                pass
            try:
                subprocess.run(["sc", "failure", APP_SERVICE_WIN, "reset=", "0", "actions=", "restart/5000"], capture_output=True)
            except Exception:
                pass

    def start_service(self):
        if sys.platform.startswith('win'):
            # Ensure service points to the stable ProgramData path before starting
            try:
                base = data_dir_gui()
                exe  = str((base / f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe"))
                # Prefer local nssm.exe in ProgramData; fallback to installed service's nssm from sc qc
                nssm_local = str(base / 'nssm.exe')
                nssm_path = nssm_local if os.path.exists(nssm_local) else _parse_sc_qc_binary_path(APP_SERVICE_WIN)
                if nssm_path and os.path.exists(nssm_path):
                    try:
                        res = subprocess.run([nssm_path, 'get', APP_SERVICE_WIN, 'Application'], capture_output=True, text=True)
                        cur = (res.stdout or '').strip()
                    except Exception:
                        cur = ''
                    if exe and (not cur or exe not in cur):
                        # Align Application and AppDirectory to ProgramData base
                        subprocess.run([nssm_path, 'set', APP_SERVICE_WIN, 'Application', exe], capture_output=True)
                        subprocess.run([nssm_path, 'set', APP_SERVICE_WIN, 'AppDirectory', str(base)], capture_output=True)
            except Exception:
                pass
            subprocess.run(["sc","start",APP_SERVICE_WIN], capture_output=True)
            # Re-check soon; if still STOPPED, surface likely cause via logs
            try:
                def _post_check():
                    st = self.service_status_str()
                    if st == 'STOPPED':
                        base = data_dir_gui()
                        errp = base / 'logs' / 'service.err.log'
                        # Default message; may be replaced by a more explicit cause below
                        msg = 'Service stopped immediately.'
                        explicit_conflict = False
                        try:
                            if errp.exists():
                                lines = (errp.read_text(encoding='utf-8', errors='ignore').splitlines()[-10:])
                                tail = "\n".join(lines)
                                if tail:
                                    # If logs indicate a global lease conflict, show a clearer message
                                    if 'holds the lease' in tail.lower():
                                        explicit_conflict = True
                                    msg += f"\nLast error lines:\n{tail}"
                        except Exception:
                            pass
                        if explicit_conflict:
                            k = (self.keyEdit.text() or '').strip()
                            fry_error(self, 'Miner Key In Use', _in_use_message(k))
                        else:
                            # Include diagnostics when we cannot infer a clear cause
                            try:
                                diag = _collect_start_failure_details(self)
                                if diag:
                                    msg = msg + "\n\n" + diag
                            except Exception:
                                pass
                            fry_error(self, 'Service Stopped', msg)
                QtCore.QTimer.singleShot(1800, _post_check)
            except Exception:
                pass

    def auto_start_service_or_exit(self):
        """On launch, attempt to start the Windows service automatically.
        If it cannot be started, show a FryNetworks error and exit the app.
        """
        if not sys.platform.startswith('win'):
            return
        try:
            # Ensure required files exist and key is valid (ProgramData)
            if not self._preflight_service_files():
                fry_error(self, 'Start Failed', 'Miner key is missing or invalid. Please relaunch and enter a valid key.')
                QtWidgets.QApplication.quit(); return
            # Block if miner_key is active elsewhere; do not start
            try:
                key = (self.keyEdit.text() or '').strip()
                if key and KEY_PATTERN.match(key):
                    okc, det = _check_key_concurrency_global(key)
                    if not okc:
                        _cleanup_local_identity_and_logs()
                        fry_error(self, 'Miner Key In Use', _in_use_message(key, _format_conflict_details(det if isinstance(det, dict) else {})))
                        QtWidgets.QApplication.quit(); return
            except Exception:
                # Continue regardless; we verify service status below
                pass
            # Block on exclusive-pair conflict
            conflict = self._exclusive_conflict_running()
            if conflict:
                fry_error(self, 'Blocked', f'{MINER_CODE} cannot run while {conflict} is running (shared hardware). Please stop {conflict} first.')
                QtWidgets.QApplication.quit(); return
            # Best-effort cleanup of stale instances/old services
            try:
                self._force_local_cleanup_current_type()  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                if self._has_old_services_or_processes():  # type: ignore[attr-defined]
                    self._cleanup_old_versions()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Install silently if not present
            try:
                st = self.service_status_str()
            except Exception:
                st = 'NOT INSTALLED'
            if st == 'NOT INSTALLED':
                try:
                    self._install_service_silent()
                except Exception:
                    fry_error(self, 'Start Failed', 'Service is not installed and could not be installed automatically.')
                    QtWidgets.QApplication.quit(); return
            # Attempt start
            self.start_service()
            # Verify a few times; only report failure on the last attempt
            def _gather_failure_message() -> tuple[bool, str]:
                base = data_dir_gui()
                errp = base / 'logs' / 'service.err.log'
                msg = 'Could not start the FryNetworks service.'
                explicit_conflict = False
                try:
                    if errp.exists():
                        lines = errp.read_text(encoding='utf-8', errors='ignore').splitlines()[-10:]
                        tail = "\n".join(lines)
                        if tail:
                            if 'holds the lease' in tail.lower():
                                explicit_conflict = True
                            if any(k in tail.lower() for k in ('error', 'exception', 'traceback', 'failed', 'denied')):
                                msg += f"\nLast error lines:\n{tail}"
                except Exception:
                    pass
                # Double-check concurrency to be explicit, even if logs were missing
                try:
                    key = (self.keyEdit.text() or '').strip()
                    if key and KEY_PATTERN.match(key):
                        okc, _ = _check_key_concurrency_global(key)
                        if not okc:
                            explicit_conflict = True
                except Exception:
                    pass
                return explicit_conflict, msg

            def _schedule_verifications(delays_ms: list[int]):
                if not delays_ms:
                    return
                d0, rest = delays_ms[0], delays_ms[1:]
                def _runner():
                    st2 = self.service_status_str()
                    if st2 == 'RUNNING':
                        try:
                            if sys.platform.startswith('win') and not self._prunedOldServiceBinaries:
                                self._prune_old_service_binaries()
                                self._prunedOldServiceBinaries = True
                        except Exception:
                            pass
                        if rest:
                            _schedule_verifications(rest)
                        return
                    # If still starting, keep waiting without error
                    if st2 == 'START_PENDING' and rest:
                        _schedule_verifications(rest)
                        return
                    if rest:
                        _schedule_verifications(rest)
                        return
                    # Last attempt and not running: report
                    explicit_conflict, msg = _gather_failure_message()
                    if explicit_conflict:
                        k = (self.keyEdit.text() or '').strip()
                        fry_error(self, 'Miner Key In Use', _in_use_message(k))
                    else:
                        try:
                            diag = _collect_start_failure_details(self)
                            if diag:
                                msg = msg + "\n\n" + diag
                        except Exception:
                            pass
                        fry_error(self, 'Start Failed', msg)
                    QtWidgets.QApplication.quit(); return
                QtCore.QTimer.singleShot(d0, _runner)

            _schedule_verifications([2000, 5000, 9000])
        except Exception as e:
            fry_error(self, 'Start Failed', f'Unexpected error while starting the service: {e}')
            QtWidgets.QApplication.quit(); return

    def _on_start_clicked(self):
        if not sys.platform.startswith('win'):
            return
        if not ensure_admin_windows():
            if not relaunch_as_admin():
                QtWidgets.QMessageBox.information(self, 'Administrator required', 'Please re-run as Administrator to start the service.')
                return
            QtWidgets.QApplication.quit(); return
        try:
            # Preflight: ensure minerkey.txt exists/valid in ProgramData
            if not self._preflight_service_files():
                return
            # Validate miner_key format and show version warning, but do not block on concurrency
            try:
                key = (self.keyEdit.text() or '').strip()
                if key and KEY_PATTERN.match(key):
                    # Version warning (non-blocking)
                    try:
                        vok, needed, installed = self._check_key_version(key)
                        if vok is False and (needed or installed):
                            fry_warn(self, 'Update Recommended', f'This device requires version {needed}, but you have {installed}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update.')
                    except Exception:
                        pass
                    # Skip miner_key concurrency enforcement to start immediately
            except Exception:
                pass
            # Cross-check: block if an exclusive miner type is running
            conflict = self._exclusive_conflict_running()
            if conflict:
                QtWidgets.QMessageBox.critical(self, 'Blocked', f'{MINER_CODE} cannot run while {conflict} is running (shared hardware). Please stop {conflict} first.')
                return
            # Proactively kill any other local instances for this miner type and clear lock
            try:
                self._force_local_cleanup_current_type()  # type: ignore[attr-defined]
            except Exception:
                pass
            # Also ensure older services are removed
            try:
                self._cleanup_old_versions()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.start_service()
            QtCore.QTimer.singleShot(1500, self.run_selfcheck)  # type: ignore[attr-defined]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Start failed', f'Could not start service: {e}')

    def _has_old_services_or_processes(self) -> bool:
        try:
            # Look for other services for this miner code that are not the current name
            current = APP_SERVICE_WIN.upper()
            out = subprocess.run(["sc","query","type=","service","state=","all"], capture_output=True, text=True)
            svc_names = []
            for line in (out.stdout or '').splitlines():
                lu = line.strip().upper()
                if lu.startswith('SERVICE_NAME:'):
                    nm = lu.split(':',1)[1].strip(); svc_names.append(nm)
            bases = [f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}", f"MinerOnline10min_{MINER_CODE}"]
            bases_u = [b.upper() for b in bases]
            has_old = any((nm != current) and any(nm.startswith(bu) for bu in bases_u) for nm in svc_names)
            if has_old:
                return True
            # Also check for stray old-version processes
            keep_suffix = f"_v{VERSION}.exe".lower()
            for p in psutil.process_iter(["name"]):
                nm = (p.info.get('name') or '').lower()
                if (
                    (nm.startswith(f"{APP_SERVICE_WIN_BASENAME.lower()}_{MINER_CODE.lower()}_v") and not nm.endswith(keep_suffix))
                    or nm.startswith(f"mineronline10min_{MINER_CODE.lower()}")
                    or (nm.startswith(f"{APP_SERVICE_BIN_BASE.lower()}_{MINER_CODE.lower()}_v") and not nm.endswith(keep_suffix))
                   ):
                    return True
        except Exception:
            pass
        return False

    def _on_install_clicked(self):
        if not sys.platform.startswith('win'):
            return
        if not ensure_admin_windows():
            if not relaunch_as_admin():
                QtWidgets.QMessageBox.information(self, 'Administrator required', 'Please re-run as Administrator to install the service.')
                return
            QtWidgets.QApplication.quit(); return
        try:
            # Validate miner key presence/format and block if in use elsewhere
            if not self._preflight_service_files():
                return
            try:
                key = (self.keyEdit.text() or '').strip()
                if key and KEY_PATTERN.match(key):
                    okc, det = _check_key_concurrency_global(key)
                    if not okc:
                        fry_error(self, 'Miner Key In Use', _in_use_message(key, _format_conflict_details(det)))
                        return
            except Exception:
                pass
            self._cleanup_old_versions()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self._install_service_silent()
            self.start_service()
            QtCore.QTimer.singleShot(1500, self.run_selfcheck)  # type: ignore[attr-defined]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Install failed', f'Could not install/start service: {e}')

    def _cleanup_old_versions(self):
        if not sys.platform.startswith('win'):
            return
        try:
            current = APP_SERVICE_WIN.upper()
            out = subprocess.run(["sc","query","type=","service","state=","all"], capture_output=True, text=True)
            svc_names = []
            for line in (out.stdout or '').splitlines():
                lu = line.strip().upper()
                if lu.startswith('SERVICE_NAME:'):
                    nm = lu.split(':',1)[1].strip()
                    svc_names.append(nm)
            # Identify legacy and old versioned names
            bases = [f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}", f"MinerOnline10min_{MINER_CODE}"]
            bases_u = [b.upper() for b in bases]
            for nm in svc_names:
                # Keep current and newer versions; remove legacy/no-version and lower versions
                if any(nm.startswith(bu) for bu in bases_u):
                    if nm == current:
                        continue
                    ver = _extract_service_version(nm)
                    if (ver is None) or (_cmp_ver(ver, VERSION) < 0):
                        try:
                            subprocess.run(["sc", "failure", nm, "reset=", "0", "actions=", ""], capture_output=True)
                            subprocess.run(["sc", "config", nm, "start=", "disabled"], capture_output=True)
                        except Exception:
                            pass
                        try:
                            subprocess.run(["sc", "stop", nm], capture_output=True)
                        except Exception:
                            pass
                        try:
                            for _ in range(20):
                                q = subprocess.run(["sc", "query", nm], capture_output=True, text=True)
                                if "STOPPED" in (q.stdout or ""):
                                    break
                                QtCore.QThread.msleep(250)
                        except Exception:
                            pass
                        try:
                            subprocess.run(["sc", "delete", nm], capture_output=True)
                        except Exception:
                            pass
            # Kill stray old-version processes by name patterns
            patterns = [
                f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}_v",
                f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v",
                f"mineronline10min_{MINER_CODE}".lower(),
                f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}".lower(),
                f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}".lower(),
            ]
            keep_suffix = f"_v{VERSION}.exe".lower()
            for p in psutil.process_iter(["pid","name"]):
                nm = (p.info.get('name') or '').lower()
                if any(nm.startswith(pref.lower()) for pref in patterns) and not nm.endswith(keep_suffix):
                    try:
                        p.terminate(); p.wait(2)
                    except Exception:
                        subprocess.run(["taskkill","/F","/PID", str(p.info.get('pid'))], capture_output=True)
        except Exception:
            pass

    def _prune_old_service_binaries(self):
        if not sys.platform.startswith('win'):
            return
        try:
            base = data_dir_gui()
            current = f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v{VERSION}.exe".lower()
            for exe in base.glob(f"{APP_SERVICE_BIN_BASE}_{MINER_CODE}_v*.exe"):
                try:
                    if exe.name.lower() != current:
                        exe.unlink()
                except Exception:
                    pass
        except Exception:
            pass


    def _on_clean_clicked(self):
        if not sys.platform.startswith('win'):
            return
        if not ensure_admin_windows():
            if not relaunch_as_admin():
                QtWidgets.QMessageBox.information(self, 'Administrator required', 'Please re-run as Administrator to clean older versions.')
                return
            QtWidgets.QApplication.quit(); return
        try:
            self._cleanup_old_versions()  # type: ignore[attr-defined]
            QtWidgets.QMessageBox.information(self, 'Cleanup', 'Cleaned older services/processes (if any).')
            QtCore.QTimer.singleShot(1000, self.run_selfcheck)  # type: ignore[attr-defined]
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Cleanup failed', f'Cleanup error: {e}')

    def _exclusive_conflict_running(self) -> str | None:
        """Return conflicting miner code if an exclusive pair is active, else None."""
        try:
            other = EXCLUSIVE_PAIRS.get(MINER_CODE)
            if not other:
                return None
            # Check services first
            try:
                out = subprocess.run(["sc","query","type=","service","state=","all"], capture_output=True, text=True)
                nm = f"{APP_SERVICE_WIN_BASENAME}_{other}".upper()
                cur = None
                for line in (out.stdout or '').splitlines():
                    t = line.strip().upper()
                    if t.startswith('SERVICE_NAME:'):
                        cur = t.split(':',1)[1].strip()
                    elif cur and t.startswith('STATE'):
                        if cur.startswith(nm) and 'RUNNING' in t:
                            return other
                        cur = None
            except Exception:
                pass
            # Check processes as fallback
            prefs = [
                f"{APP_SERVICE_WIN_BASENAME.lower()}_{other.lower()}_v",
                f"{APP_SERVICE_BIN_BASE.lower()}_{other.lower()}_v",
            ]
            for p in psutil.process_iter(["name"]):
                nm = (p.info.get('name') or '').lower()
                if any(nm.startswith(pref) for pref in prefs):
                    return other
        except Exception:
            return None
        return None

    def _update_conflict_banner(self):
        other = self._exclusive_conflict_running()
        if other:
            try:
                self.conflictBanner.setText(f"Blocked: {MINER_CODE} cannot run while {other} is running (shared hardware). Please stop {other} first.")
                self.conflictBanner.show()
            except Exception:
                pass
            # Disable start/install while conflict present
            try:
                if hasattr(self, 'btnStart'): self.btnStart.setEnabled(False)
                if hasattr(self, 'btnInstall'): self.btnInstall.setEnabled(False)
            except Exception:
                pass
        else:
            try:
                self.conflictBanner.hide()
                if hasattr(self, 'btnStart'): self.btnStart.setEnabled(True)
                if hasattr(self, 'btnInstall'): self.btnInstall.setEnabled(True)
            except Exception:
                pass

    def _force_local_cleanup_current_type(self):
        """Kill any running service binaries for this miner type and remove group lock.
        Does not touch other miner types.
        Requires admin to kill services' processes reliably.
        """
        try:
            # Remove local lock file
            try:
                lockp = data_dir_gui() / 'service.lock'
                if lockp.exists():
                    lockp.unlink()
            except Exception:
                pass
            # Stop and delete any running services for this miner type (regardless of version)
            try:
                out = subprocess.run(["sc","query","type=","service","state=","all"], capture_output=True, text=True)
                for line in (out.stdout or '').splitlines():
                    lu = line.strip().upper()
                    if lu.startswith('SERVICE_NAME:'):
                        nm = lu.split(':',1)[1].strip()
                        if nm.upper().startswith(f"{APP_SERVICE_WIN_BASENAME}_{MINER_CODE}".upper()):
                            try:
                                subprocess.run(["sc","stop", nm], capture_output=True)
                            except Exception:
                                pass
                            # best-effort: wait briefly for STOPPED, then delete
                            try:
                                for _ in range(10):
                                    q = subprocess.run(["sc","query", nm], capture_output=True, text=True)
                                    if "STOPPED" in (q.stdout or "").upper():
                                        break
                                    QtCore.QThread.msleep(200)
                            except Exception:
                                pass
                            try:
                                subprocess.run(["sc","delete", nm], capture_output=True)
                            except Exception:
                                pass
            except Exception:
                pass
            # Kill processes by name pattern for this miner type
            base_prefs = [
                f"{APP_SERVICE_WIN_BASENAME.lower()}_{MINER_CODE.lower()}_v",
                f"{APP_SERVICE_BIN_BASE.lower()}_{MINER_CODE.lower()}_v",
            ]
            for p in psutil.process_iter(["pid","name"]):
                try:
                    nm = (p.info.get('name') or '').lower()
                    if any(nm.startswith(pref) for pref in base_prefs):
                        try:
                            p.terminate(); p.wait(2)
                        except Exception:
                            subprocess.run(["taskkill","/F","/PID", str(p.info.get('pid'))], capture_output=True)
                except Exception:
                    pass
        except Exception:
            pass

def data_dir_gui() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / "FryNetworks" / f"miner-{MINER_CODE}"
    else:
        return Path(f"/var/lib/frynetworks/miner-{MINER_CODE}")

def date_to_cache_path(d) -> Path:
    return data_dir_gui() / f"status-{d.strftime('%Y%m%d')}.json"

def date_to_lock_path(d) -> Path:
    return data_dir_gui() / f"status-{d.strftime('%Y%m%d')}.lock"

class _DayReadLock:
    """Best-effort advisory read lock on a day's cache (non-blocking with short retry).
    Works with the writer's Windows msvcrt lock. Falls back to simple existence checks.
    """
    def __init__(self, lock_path: Path, block_ms: int = 300):
        self.lock_path = lock_path
        self.block_ms = max(0, int(block_ms))
        self._fh = None
    def __enter__(self):
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self.lock_path, 'a+b')
            self._fh = fh
            try:
                import msvcrt  # type: ignore
                deadline = time.time() + (self.block_ms / 1000.0)
                while True:
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except Exception:
                        if time.time() >= deadline:
                            break
                        time.sleep(0.03)
            except Exception:
                try:
                    import fcntl  # type: ignore
                    flock_fn = getattr(fcntl, 'flock', None)
                    lock_sh = getattr(fcntl, 'LOCK_SH', None)
                    lock_nb = getattr(fcntl, 'LOCK_NB', None)
                    if callable(flock_fn) and lock_sh is not None and lock_nb is not None:
                        deadline = time.time() + (self.block_ms / 1000.0)
                        while True:
                            try:
                                flock_fn(fh.fileno(), lock_sh | lock_nb)
                                break
                            except Exception:
                                if time.time() >= deadline:
                                    break
                                time.sleep(0.03)
                except Exception:
                    pass
                else:
                    # Fallback could not lock; proceed without advisory lock
                    pass
        except Exception:
            self._fh = None
        return self
    def __exit__(self, exc_type, exc, tb):
        fh = self._fh; self._fh = None
        if not fh: return False
        try:
            try:
                import msvcrt  # type: ignore
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                try:
                    import fcntl  # type: ignore
                    flock_fn = getattr(fcntl, 'flock', None)
                    lock_un = getattr(fcntl, 'LOCK_UN', None)
                    if callable(flock_fn) and lock_un is not None:
                        flock_fn(fh.fileno(), lock_un)
                except Exception:
                    pass
        finally:
            try:
                fh.close()
            except Exception:
                pass

def counts_for_day(d) -> list[int]:
    try:
        p = date_to_cache_path(d)
        lp = date_to_lock_path(d)
        with _DayReadLock(lp):
            with open(p, "r", encoding="utf-8") as f:
                doc = json.load(f)
        # Verify signature (anti-tamper); if invalid, ignore
        if not (isinstance(doc, dict) and verify_cache_signature(doc, None, allow_if_no_key=True)):
            return [0]*24
        counts = [0]*24
        hours = doc.get("hours", {})
        for h in range(24):
            x = hours.get(str(h))
            if isinstance(x, dict):
                counts[h] = int(x.get("onlineCount", 0))
        return counts
    except Exception:
        return [0]*24

def rolling_24h_counts_and_labels() -> tuple[list[int], list[str]]:
    import datetime as dt
    now_local = dt.datetime.now().astimezone()
    end_local = now_local.replace(minute=0, second=0, microsecond=0)
    counts, labels = [], []
    for i in range(23, -1, -1):
        h_local = end_local - dt.timedelta(hours=i)
        labels.append(h_local.strftime("%H"))
        h_utc = h_local.astimezone(dt.timezone.utc)
        day_counts = counts_for_day(h_utc.date())
        counts.append(day_counts[h_utc.hour])
    return counts, labels

def slots_per_hour_today() -> int:
    import datetime as dt
    try:
        today = dt.datetime.utcnow().date()
        p = date_to_cache_path(today)
        lp = date_to_lock_path(today)
        if p.exists():
            with _DayReadLock(lp):
                with open(p, 'r', encoding='utf-8') as f:
                    doc = json.load(f)
            if not (isinstance(doc, dict) and verify_cache_signature(doc, None, allow_if_no_key=True)):
                return 6
            hours = doc.get('hours', {})
            # find first hour entry with totalSlots
            for h in range(24):
                hd = hours.get(str(h))
                if isinstance(hd, dict) and isinstance(hd.get('totalSlots'), int):
                    return int(hd['totalSlots'])
    except Exception:
        pass
    return 6

def _rolling7_path_gui() -> Path:
    return data_dir_gui() / "status-rolling7.json"

def _percent_for_day_doc(doc: dict) -> float | None:
    try:
        if isinstance(doc.get('onlinePercentDay'), (int, float)):
            return float(doc['onlinePercentDay'])
        oc = doc.get('onlineCountDay'); ts = doc.get('totalSlotsDay')
        if isinstance(oc, int) and isinstance(ts, int) and ts > 0:
            return round(100.0 * oc / ts, 1)
        hours = doc.get('hours', {})
        if isinstance(hours, dict):
            day_total = 0; day_online = 0
            for h in range(24):
                hd = hours.get(str(h))
                if isinstance(hd, dict):
                    slots = hd.get('slots') or []
                    if isinstance(slots, list) and slots:
                        day_total += len(slots)
                        day_online += sum(1 for s in slots if s == 'online')
            if day_total > 0:
                return round(100.0 * day_online / day_total, 1)
    except Exception:
        pass
    return None

def rolling_7d_percents_and_labels() -> tuple[list[float], list[str], float]:
    """Return (percents, labels, average_percent) for last up to 7 completed days.

    Prefers the rolling file if present; otherwise reconstructs from daily caches.
    Labels are MM-DD.
    """
    import datetime as dt
    p = _rolling7_path_gui()
    days = []
    if p.exists():
        try:
            with open(p, 'r', encoding='utf-8') as f:
                doc = json.load(f)
            if isinstance(doc, dict) and isinstance(doc.get('days'), list):
                # Verify signature of rolling file; if invalid, ignore and rebuild from daily caches
                if not verify_cache_signature(doc, None, allow_if_no_key=True):
                    raise RuntimeError('bad_sig')
                for d in doc['days']:
                    if isinstance(d, dict) and isinstance(d.get('date'), str):
                        days.append(d)
        except Exception:
            days = []
    # Fallback: build from last 7 finished days
    if not days:
        today_utc = dt.datetime.utcnow().date()
        for i in range(7, 0, -1):
            d = today_utc - dt.timedelta(days=i)
            try:
                pp = date_to_cache_path(d)
                if not pp.exists():
                    continue
                with open(pp, 'r', encoding='utf-8') as f:
                    doc = json.load(f)
                doc['date'] = d.strftime('%Y-%m-%d')
                days.append(doc)
            except Exception:
                continue
    # Normalize and sort by date
    def _dkey(x: dict) -> str:
        try:
            return str(x.get('date') or '')
        except Exception:
            return ''
    days = sorted(days, key=_dkey)[-7:]
    # Build outputs
    percents: list[float] = []
    labels: list[str] = []
    for d in days:
        ds = str(d.get('date'))
        try:
            dtobj = dt.datetime.strptime(ds, '%Y-%m-%d')
            labels.append(dtobj.strftime('%m-%d'))
        except Exception:
            labels.append(ds)
        pct = _percent_for_day_doc(d)
        percents.append(round(float(pct), 1) if isinstance(pct, (int, float)) else 0.0)
    avg = round(sum(percents)/max(1, len(percents)), 1) if percents else 0.0
    return percents, labels, avg

def open_today_cache():
    import datetime as dt, subprocess
    try:
        p = date_to_cache_path(dt.datetime.utcnow().date())
        if not p.exists():
            QtWidgets.QMessageBox.information(None, "Cache", "No cache file for today yet.")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(p))
        elif sys.platform.startswith("darwin"):
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])
    except Exception as e:
        QtWidgets.QMessageBox.warning(None, "Cache", f"Failed to open cache: {e}")


def main():
    class StartupScreen(QtWidgets.QDialog):
        def __init__(self):
            super().__init__(None, QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Dialog)
            self.setModal(False)
            self.setObjectName("StartupScreen")
            self.resize(520, 220)
            lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(24, 24, 24, 24); lay.setSpacing(12)
            self.setStyleSheet(self.styleSheet() + "\n"
                               "#StartupScreen { background-color: #000000; }\n"
                               "QLabel { color: white; }\n"
                               "QProgressBar { border: 1px solid white; background-color: black; color: white; height: 12px; }\n"
                               "QProgressBar::chunk { background-color: #E10600; }\n")
            self.title = QtWidgets.QLabel(f"FRY {MINER_CODE} Miner")
            f = self.title.font(); f.setPointSize(f.pointSize()+2); f.setBold(True); self.title.setFont(f)
            self.msg = QtWidgets.QLabel("Initializing..."); self.msg.setWordWrap(True)
            self.keyLbl = QtWidgets.QLabel("")
            self.bar = QtWidgets.QProgressBar(); self.bar.setRange(0, 100); self.bar.setValue(0)
            logo = None
            for name in (f"images/{MINER_CODE}.png", f"images/{MINER_CODE}.jpg", f"images/{MINER_CODE}.ico", f"images/{MINER_CODE}.bmp", "images/frynetworks_logo.png"):
                p = resource_path(name)
                if os.path.exists(p):
                    pix = QtGui.QPixmap(p)
                    if not pix.isNull():
                        logo = QtWidgets.QLabel(); logo.setPixmap(pix.scaledToHeight(56, QtCore.Qt.TransformationMode.SmoothTransformation))
                    break
            if logo is not None:
                lay.addWidget(logo, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
                try:
                    eff = QtWidgets.QGraphicsOpacityEffect(logo)
                    logo.setGraphicsEffect(eff)
                    anim = QtCore.QPropertyAnimation(eff, b"opacity", self)
                    anim.setDuration(1200); anim.setStartValue(0.6); anim.setEndValue(1.0)
                    anim.setEasingCurve(QtCore.QEasingCurve.Type.InOutSine); anim.setLoopCount(-1); anim.start()
                    self._logo_anim = anim
                except Exception:
                    pass
            lay.addWidget(self.title)
            lay.addWidget(self.msg)
            lay.addWidget(self.keyLbl)
            lay.addWidget(self.bar)
        def step(self, text: str, value: int):
            try:
                self.msg.setText(text)
                self.bar.setValue(max(0, min(100, value)))
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass
        def set_key(self, key: str | None):
            try:
                k = (key or "").strip()
                if k:
                    self.keyLbl.setText(f"Key: {k}")
                else:
                    self.keyLbl.clear()
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

    def _excepthook(exctype, value, tb):
        import traceback
        logp = resource_path("miner_gui.log")
        with open(logp, "a", encoding="utf-8") as f:
            f.write("Uncaught exception:\\n")
            traceback.print_exception(exctype, value, tb, file=f)
        QtWidgets.QMessageBox.critical(None, "FRY Miner", f"An unexpected error occurred. Details were written to {logp}.")

    app = QtWidgets.QApplication(sys.argv)
    sys.excepthook = _excepthook
    try:
        log_step("GUI launch", {"version": VERSION, "minerCode": MINER_CODE, "platform": sys.platform})
    except Exception:
        pass

    # IPC single-instance (per miner type) - relaxed: do not block GUI launch
    instance_key = f"FRY_{MINER_CODE}_Single"
    # Best-effort cleanup of older versions, but do not exit if a newer one exists
    try:
        _close_older_gui_instances()
    except Exception:
        pass
    # Skip SingleInstance gating to allow immediate launch even if another instance is running
    # Still create a SingleInstance to wire wakeRequested so secondary launches can focus this window.
    try:
        single = SingleInstance(instance_key)
        try:
            if single.server.listen(instance_key):
                single.server.newConnection.connect(single._on_new_connection)
        except Exception:
            pass
    except Exception:
        single = None

    # Auto-elevate on Windows for service install/control
    if sys.platform.startswith('win') and not ensure_admin_windows():
        if not relaunch_as_admin():
            QtWidgets.QMessageBox.information(None, "Administrator required", "Please re-run as Administrator to complete setup.")
        return
    # Register autostart on Windows (best-effort)
    try:
        ensure_gui_autostart_windows()
    except Exception:
        pass

    try:
        # Prefer Task Scheduler (highest privileges, no UAC at logon); fallback to HKCU Run
        ensure_gui_autostart_task()
    except Exception:
        pass
    try:
        ensure_gui_autostart_windows()
    except Exception:
        pass

    splash = FrySplash()
    try:
        theme_obj = Theme() if callable(Theme) else None
    except Exception:
        theme_obj = None
    try:
        # Apply same theme to splash to ensure consistent dark background
        if theme_obj is not None:
            splash.setStyleSheet(theme_obj.qss())
    except Exception:
        pass
    splash.show()
    def _prestart_gate() -> bool:
        global _PRECHECK_OK, _FORCE_UPDATE_REQUIRED
        ex = read_miner_key()
        log_step("prestart: begin", {"have_saved_key": bool(ex)})
        if ex:
            try:
                splash.step('Validating miner key format...', 20)
                if not KEY_PATTERN.match(ex):
                    log_step("prestart: saved key bad format", {"key": ex})
                    fry_error(None, 'Miner Key', 'The saved miner_key is invalid. Please relaunch and enter a valid key.')
                    return False
                splash.step('Checking key validity...', 35)
                if not _check_key_exists_global(ex):
                    log_step("prestart: saved key not found", {"key": ex})
                    fry_error(None, 'Miner Key', 'The saved miner_key was not found. Please relaunch and enter a valid key.')
                    return False
                splash.step('Global cross-checking...', 55)
                ok, det = _check_key_concurrency_global(ex)
                log_step("prestart: concurrency(saved)", {"ok": ok, "details": det})
                if not ok:
                    if isinstance(det, dict) and det:
                        fry_error(None, 'Miner Key', _in_use_message(ex, _format_conflict_details(det)))
                    else:
                        fry_error(None, 'Miner Key', 'Could not verify miner_key status (network/database error). Please check your connection and try again.')
                    return False
                # Non-blocking update warning
                splash.step('Version check...', 70)
                vok, needed, installed = _check_key_version_global(ex)
                log_step("prestart: version(saved)", {"ok": vok, "needed": needed, "installed": installed})
                if vok is False and (needed or installed):
                    _FORCE_UPDATE_REQUIRED = True
                    fry_warn(None, 'Update Recommended', f'This device requires version {needed}, but you have {installed}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update.')
                _PRECHECK_OK = True
                return True
            except Exception:
                fry_error(None, 'Miner Key', 'An error occurred validating the miner_key. Please try again.')
                return False
        else:
            key, ok = ask_miner_key(splash)
            log_step("prestart: prompt key", {"ok": bool(ok), "len": len(key or '')})
            if not ok or not key:
                fry_error(None, 'Miner Key', 'Miner key is required. Exiting.')
                return False
            key = key.strip()
            if not KEY_PATTERN.match(key):
                log_step("prestart: entered key bad format", {"key": key})
                fry_error(None, 'Miner Key', 'The miner_key format is invalid. Please relaunch and try again.')
                return False
            if not _check_key_exists_global(key):
                log_step("prestart: entered key not found", {"key": key})
                fry_error(None, 'Miner Key', 'The miner_key was not found. Please verify your key and relaunch.')
                return False
            okc, det = _check_key_concurrency_global(key)
            log_step("prestart: concurrency(entered)", {"ok": okc, "details": det})
            if not okc:
                if isinstance(det, dict) and det:
                    fry_error(None, 'Miner Key', _in_use_message(key, _format_conflict_details(det)))
                else:
                    fry_error(None, 'Miner Key', 'Could not verify miner_key status (network/database error). Please check your connection and try again.')
                return False
            try:
                write_miner_key(key)
                log_step("prestart: wrote minerkey.txt", {"key": key, "path": str((data_dir_gui()/ 'minerkey.txt'))})
            except Exception:
                pass
            # Non-blocking update warning
            try:
                vok, needed, installed = _check_key_version_global(key)
                log_step("prestart: version(entered)", {"ok": vok, "needed": needed, "installed": installed})
                if vok is False and (needed or installed):
                    _FORCE_UPDATE_REQUIRED = True
                    fry_warn(None, 'Update Recommended', f'This device requires version {needed}, but you have {installed}. A new FryNetworks miner is rolling out shortly; please keep this device online for the update.')
            except Exception:
                pass
            _PRECHECK_OK = True
            return True
    ok_gate = _prestart_gate()
    if not ok_gate:
        splash.close()
        return

    splash.step('Starting service...', 85)
    w = MainWindow()

    try:
        theme_obj = Theme() if callable(Theme) else None
    except Exception:
        theme_obj = None
    try:
        # Reapply theme to main window to avoid any style resets
        if theme_obj is not None:
            w.setStyleSheet(theme_obj.qss())
            w.setAutoFillBackground(True)
    except Exception:
        pass

    try:
        # Start service (errors are shown by the UI)
        w.auto_start_service_or_exit()
    except Exception:
        pass

    splash.step('Ready', 100)

    # --- keep the wake handler for single-instance wakeups ---
    def _wake():
        try:
            w.showNormal()
            w.setWindowState(w.windowState() & ~QtCore.Qt.WindowState.WindowMinimized)
            w.raise_()
            w.activateWindow()
        except Exception:
            w.show()

    try:
        if single is not None:
            single.wakeRequested.connect(_wake)
    except Exception:
        pass

    # --- show the main window on the next event-loop tick, after the splash closes ---
    def _reveal_main():
        try:
            splash.close()  # let the close happen once the loop is running
        except Exception:
            pass
        try:
            w.showNormal()
            w.setWindowState(w.windowState() & ~QtCore.Qt.WindowState.WindowMinimized)
            w.raise_()
            w.activateWindow()
        except Exception:
            w.show()

    QtCore.QTimer.singleShot(0, _reveal_main)

    # enter the event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
