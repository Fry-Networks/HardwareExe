"""Main entry point for the modular miner GUI application."""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict
import faulthandler
try:
    faulthandler.enable()
except Exception:
    pass  # continue even if faulthandler cannot enable (unlikely)

# Dump trace if process hangs > 120s (diagnostic for silent native crash)
try:
    faulthandler.dump_traceback_later(120, repeat=True)
except Exception:
    pass

# Setup Python paths first
# Try a normal import first; if running from a PyInstaller onefile or the
# module isn't on the default path, attempt to load the tools/setup_paths.py
# file from either the frozen bundle (sys._MEIPASS) or the repository layout.
try:
    import setup_paths  # type: ignore
except Exception:
    # Fallback: attempt to load tools/setup_paths.py by path
    try:
        import sys
        import importlib.util
        from pathlib import Path

        base = getattr(sys, '_MEIPASS', None)
        candidates = []
        if base:
            candidates.append(Path(base) / 'tools' / 'setup_paths.py')
            candidates.append(Path(base) / 'miner_GUI' / 'tools' / 'setup_paths.py')

        # Repository relative paths (support repo-root tools/ and miner_GUI/tools/)
        candidates.append(Path(__file__).parent / 'tools' / 'setup_paths.py')
        candidates.append(Path(__file__).parent / 'miner_GUI' / 'tools' / 'setup_paths.py')

        for cand in candidates:
            try:
                if cand and cand.exists():
                    spec = importlib.util.spec_from_file_location('setup_paths', str(cand))
                    if not spec or not spec.loader:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore[attr-defined]
                    # Insert into sys.modules so other imports can find it as "setup_paths"
                    sys.modules['setup_paths'] = module
                    break
            except Exception:
                continue
    except Exception:
        # If all fallbacks fail, let the original ImportError surface later
        pass

# Add the miner_GUI directory to Python path
gui_dir = Path(__file__).parent / "miner_GUI"
sys.path.insert(0, str(gui_dir))

# Import PySide6 and check availability
try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    print("Error: PySide6 is not installed. Please install it with: pip install PySide6")
    sys.exit(1)

# Import our modular components
from miner_GUI.config import (MINER_CODE, VERSION, KEY_PATTERN)
from miner_GUI.utils.data import log_step, read_miner_key
from miner_GUI.utils.gui import fry_error
from miner_GUI.ui.dialogs.splash import FrySplash
from miner_GUI.services.single_instance import SingleInstance

# Import theme and banner if available
try:
    from theme import Theme
except ImportError:
    Theme = None

# TopBanner import removed - not used in main.py

# Global state variables
_PRECHECK_OK = False


def _detect_virtual_machine() -> Dict[str, Any]:
    """Detect whether the current host is a virtual machine.

    Returns:
        dict: {
            'vm': bool|None,    # True if VM detected, False if confidently physical, None if unknown
            'evidence': list[str],  # Indicators found
            'method': str            # Primary detection method used
        }
    Notes:
        This function uses a best-effort, multi-layer heuristic approach:
        1. Platform-specific commands (systemd-detect-virt, WMI, sysctl)
        2. DMI / SMBIOS product/vendor strings
        3. MAC OUI prefixes common to hypervisor virtual NICs
        4. Process / device artifact hints
    """
    info: Dict[str, Any] = {"vm": None, "evidence": [], "method": "heuristic"}
    try:
        sys_name = platform.system()
        sys_lower = sys_name.lower()

        vm_markers = [
            "virtual", "vmware", "hyper-v", "xen", "qemu", "kvm",
            "parallels", "virtualbox", "vbox", "bochs"
        ]

        # --- Windows ---
        if sys_lower == "windows":
            try:
                wmi_cmd = ["powershell", "-NoLogo", "-WindowStyle", "Hidden", "-NoProfile", "-Command",
                           "Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model"]
                r = subprocess.run(wmi_cmd, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                out = (r.stdout + r.stderr).lower()
                if any(m in out for m in vm_markers):
                    info["vm"] = True
                    info["evidence"].append(f"WMI Manufacturer/Model: {out.strip()[:120]}")
                    info["method"] = "wmi"
                    return info
            except Exception:
                pass
            # BIOS vendor / product via wmic (fallback)
            try:
                r = subprocess.run(["wmic", "computersystem", "get", "manufacturer,model"],
                                    capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                out = (r.stdout + r.stderr).lower()
                if any(m in out for m in vm_markers):
                    info["vm"] = True
                    info["evidence"].append(f"WMIC manufacturer/model: {out.strip()[:120]}")
                    info["method"] = "wmic"
                    return info
            except Exception:
                pass
            # MAC OUI heuristic
            try:
                import uuid
                mac = uuid.getnode()
                oui = f"{(mac >> 40) & 0xff:02x}:{(mac >> 32) & 0xff:02x}:{(mac >> 24) & 0xff:02x}"
                vm_ouis = {"00:05:69", "00:0c:29", "00:1c:14", "00:50:56"}  # VMware ranges
                if oui.lower() in vm_ouis:
                    info["vm"] = True
                    info["evidence"].append(f"VM OUI prefix detected: {oui}")
                    info["method"] = "mac_oui"
            except Exception:
                pass
            if info["vm"] is None:
                info["vm"] = False  # Default to physical if no evidence
            return info

        # --- Linux ---
        if sys_lower == "linux":
            # systemd-detect-virt
            try:
                r = subprocess.run(["systemd-detect-virt"], capture_output=True, text=True, timeout=5)
                if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != "none":
                    info["vm"] = True
                    info["evidence"].append(f"systemd-detect-virt: {r.stdout.strip()}")
                    info["method"] = "systemd-detect-virt"
                    return info
            except Exception:
                pass
            # DMI product name / sys vendor
            dmi_paths = [
                "/sys/class/dmi/id/product_name",
                "/sys/class/dmi/id/sys_vendor",
                "/sys/class/dmi/id/bios_vendor"
            ]
            for p in dmi_paths:
                try:
                    if os.path.exists(p):
                        content = Path(p).read_text(encoding="utf-8", errors="ignore").lower()
                        if any(m in content for m in vm_markers):
                            info["vm"] = True
                            info["evidence"].append(f"DMI {os.path.basename(p)}: {content.strip()[:80]}")
                            info["method"] = "dmi"
                            return info
                except Exception:
                    pass
            # /proc/cpuinfo hypervisor flag
            try:
                cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
                if "hypervisor" in cpuinfo:
                    info["vm"] = True
                    info["evidence"].append("CPU hypervisor flag present")
                    info["method"] = "cpuinfo"
                    return info
            except Exception:
                pass
            if info["vm"] is None:
                info["vm"] = False
            return info

        # --- macOS ---
        if sys_lower == "darwin":
            try:
                r = subprocess.run(["sysctl", "-a"], capture_output=True, text=True, timeout=8)
                out = r.stdout.lower()
                if any(m in out for m in vm_markers):
                    info["vm"] = True
                    info["evidence"].append("sysctl hypervisor indicators present")
                    info["method"] = "sysctl"
                    return info
            except Exception:
                pass
            # Apple Silicon / hardware model seldom virtualized publicly; default False if no evidence
            info["vm"] = False if info["vm"] is None else info["vm"]
            return info

        # Other/unknown OS
        info["vm"] = None
        return info
    except Exception as e:
        info["vm"] = None
        info["evidence"].append(f"vm-detect-error: {e}")
        return info


def _excepthook(exctype, value, tb):
    """Global exception handler."""
    import traceback
    from miner_GUI.config import resource_path
    
    logp = resource_path("miner_gui.log")
    with open(logp, "a", encoding="utf-8") as f:
        f.write("Uncaught exception:\n")
        traceback.print_exception(exctype, value, tb, file=f)
    QtWidgets.QMessageBox.critical(None, "FRY Miner", f"An unexpected error occurred. Details were written to {logp}.")


def _prestart_gate(splash: FrySplash) -> bool:
    """Pre-startup validation gate."""
    global _PRECHECK_OK

    try:
        splash.step('Loading miner configuration...', 25)
    except Exception:
        pass

    miner_key = read_miner_key()
    log_step("prestart: begin", {"have_saved_key": bool(miner_key), "expected_code": MINER_CODE})

    if not miner_key:
        fry_error(
            None,
            'Miner Configuration Missing or Invalid',
            f'This is a {MINER_CODE} FryNetworks miner and requires a {MINER_CODE} miner key.\n\n'
            f'Please run the FryNetworks installer to configure the FryNetworks miner.'
        )
        return False

    if not KEY_PATTERN.match(miner_key):
        log_step("prestart: saved key bad format", {"key": miner_key})
        fry_error(
            None,
            'Miner Key Invalid',
            'The stored miner_key does not match the expected format. Please re-run the installer.'
        )
        return False

    _PRECHECK_OK = True
    return True


def ensure_gui_autostart_windows():
    """Ensure GUI starts automatically on Windows (placeholder)."""
    # TODO: Implement autostart functionality
    pass


def ensure_gui_autostart_task():
    """Ensure GUI autostart via Task Scheduler (placeholder)."""
    # TODO: Implement task scheduler functionality
    pass


def _close_older_gui_instances():
    """Close older GUI instances (placeholder)."""
    # TODO: Implement cleanup of older instances
    pass


def main():
    """Main application entry point."""
    app = QtWidgets.QApplication(sys.argv)
    # Ensure crash diagnostics flush promptly
    try:
        os.environ.setdefault("PYTHONFAULTHANDLER", "1")
    except Exception:
        pass
    
    # Prevent QApplication from quitting when the last window is closed
    QtWidgets.QApplication.setQuitOnLastWindowClosed(False)
    sys.excepthook = _excepthook
    
    # Block virtual machines before any further initialization (before logging)
    try:
        vm_info = _detect_virtual_machine()
        if vm_info.get("vm") is True:
            fry_error(
                None,
                "Unsupported Environment",
                "Install on physical hardware. VMs are not supported for FryNetworks miners/nodes."
            )
            return
    except Exception:
        pass
    
    # VM check and logging happen early
    try:
        vm_info = _detect_virtual_machine()
        log_step("GUI_started", {
            "version": VERSION,
            "minerCode": MINER_CODE,
            "platform": sys.platform,
            "vm": vm_info.get("vm", None)
        })
    except Exception:
        try:
            log_step("GUI_started", {"version": VERSION, "minerCode": MINER_CODE, "platform": sys.platform})
        except Exception:
            pass
    
    # IPC single-instance (per miner type)
    instance_key = f"FRY_{MINER_CODE}_Single"
    
    # Best-effort cleanup of older versions
    try:
        _close_older_gui_instances()
    except Exception:
        pass
    
    single = None
    try:
        single = SingleInstance(instance_key)
        if not single.start_or_signal():
            # Another instance is running, exit immediately
            sys.exit(0)
    except Exception as e:
        # If single instance check fails, log it but don't continue
        print(f"Single instance check failed: {e}")
        sys.exit(1)
    
    # Register autostart on Windows (best-effort)
    try:
        ensure_gui_autostart_task()
    except Exception:
        pass
    
    try:
        ensure_gui_autostart_windows()
    except Exception:
        pass
    
    # Create and show splash screen
    splash = FrySplash()
    
    try:
        theme_obj = Theme() if callable(Theme) else None
        if theme_obj is not None and hasattr(theme_obj, 'qss'):
            splash.setStyleSheet(theme_obj.qss())  # type: ignore[misc]
    except Exception:
        pass
    
    splash.show()
    
    # Pre-startup validation
    ok_gate = _prestart_gate(splash)
    if not ok_gate:
        splash.close()
        return
    
    splash.step('Starting service...', 85)
    
    # Import and create main window (theme is applied internally)
    from miner_GUI.ui.main_window import MainWindow
    w = MainWindow()
    
    try:
        # Start service (errors are shown by the UI)
        w.auto_start_service_or_exit()
    except Exception:
        pass
    
    splash.step('Ready', 100)
    
    # Wake handler for single-instance wakeups
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
    
    # Show the main window on the next event-loop tick, after the splash closes
    def _reveal_main():
        try:
            splash.close()
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
    
    # Enter the event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
