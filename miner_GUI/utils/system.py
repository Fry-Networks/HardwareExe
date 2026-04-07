"""
System utilities for Windows services, admin privileges, and version management.
"""

import fnmatch
import re
import sys
import subprocess
from typing import Optional, Any

import psutil

# Import configuration with fallbacks
from config_profile import MINER_CODE, VERSION


def parse_sc_qc_binary_path(service_name: str) -> Optional[str]:
    """Return the BINARY_PATH_NAME from `sc qc` for a service (Windows only)."""
    # Service inspection via `sc qc` is a service-management concern and is
    # intentionally disabled in the GUI package. Return None to indicate
    # that the GUI must not probe or modify service binaries.
    return None


def ensure_admin_windows() -> bool:
    """Check if running with admin privileges on Windows."""
    if not sys.platform.startswith('win'):
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Relaunch the current process with admin privileges."""
    if not sys.platform.startswith('win'):
        return False
    try:
        import ctypes
        params = ' '.join([f'"{p}"' for p in sys.argv])
        ret = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable, params, None, 1)
        return ret and ret > 32
    except Exception:
        return False


def parse_ver_list(s: str) -> list[int]:
    """Parse version string into list of integers."""
    try:
        return [int(x) for x in re.split(r"[^0-9]+", s or "") if x]
    except Exception:
        return [0]


def cmp_ver(a: str, b: str) -> int:
    """Compare two version strings. Returns -1, 0, or 1."""
    A = parse_ver_list(a)
    B = parse_ver_list(b)
    L = max(len(A), len(B))
    A += [0] * (L - len(A))
    B += [0] * (L - len(B))
    return (A > B) - (A < B)


def extract_service_version(name: str) -> Optional[str]:
    """Extract version from service name."""
    try:
        m = re.search(r"_V(\d+(?:\.\d+)*)$", name, re.IGNORECASE)
        return m.group(1) if m else None
    except Exception:
        return None


def extract_process_version(name: str) -> Optional[str]:
    """Extract version from process name."""
    try:
        m = re.search(r"_V(\d+(?:\.\d+)*)\.exe$", name, re.IGNORECASE)
        return m.group(1) if m else None
    except Exception:
        return None


def make_key_pattern(prefix: str) -> re.Pattern:
    """Create regex pattern for miner keys."""
    return re.compile(rf"^{re.escape(prefix)}-[A-Z0-9]{{32}}$")


def close_older_gui_instances() -> bool:
    """Terminate older GUI processes for this miner type if present.
    
    Returns True if a newer GUI version is already running (so caller should exit).
    
    This function attempts graceful termination first, then requests the service
    to force-kill via taskkill if needed.
    """
    try:
        from miner_GUI.services import privileged_ops
        
        base_pref = f"fry_{MINER_CODE.lower()}_v"
        newer_running = False
        for p in psutil.process_iter(["pid", "name"]):
            try:
                nm_full = p.info.get("name") or ""
                nm = nm_full.lower()
                if not nm.startswith(base_pref):
                    continue
                ver = extract_process_version(nm_full) or ""
                if not ver:
                    continue
                cmp = cmp_ver(ver, VERSION)
                if cmp < 0:
                    # Older GUI instance: try graceful termination first
                    pid = p.info.get('pid')
                    try:
                        p.terminate()
                        p.wait(2)
                    except Exception:
                        # Graceful termination failed; request service to force-kill
                        try:
                            success, msg = privileged_ops.kill_process(pid, force=True)
                            if not success:
                                # Service may not be available; try direct taskkill as fallback
                                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        except Exception:
                            pass
                elif cmp > 0:
                    newer_running = True
            except Exception:
                continue
        return newer_running
    except Exception:
        return False


def service_exists(miner_code: str) -> bool:
    """Return True if any FRY PoC service exists for a given miner code (Windows only)."""
    if not sys.platform.startswith("win"):
        return False
    pattern = f"FRY_PoC_{str(miner_code).upper()}_v*"
    try:
        return query_best_service(pattern) is not None
    except Exception:
        return False


def _extract_trailing_version_tuple(name: str) -> tuple[int, ...]:
    """Extract a comparable version tuple from names like FRY_PoC_BM_v2 or _v2.3."""
    try:
        m = re.search(r"_v(\d+(?:[._-]\d+)*)", str(name), re.IGNORECASE)
        if not m:
            return ()
        raw = m.group(1).replace("_", ".").replace("-", ".")
        parts = [p for p in raw.split(".") if p.strip()]
        out: list[int] = []
        for p in parts:
            try:
                out.append(int(p))
            except Exception:
                break
        return tuple(out)
    except Exception:
        return ()


def list_windows_services(name_pattern: str) -> list[dict[str, Any]]:
    """List Windows services matching a wildcard pattern (best-effort, Windows only)."""
    if not sys.platform.startswith("win"):
        return []

    pat = str(name_pattern or "").strip()
    if not pat:
        return []

    # Prefer psutil's service iterator to avoid invoking PowerShell.
    services: list[dict[str, Any]] = []
    try:
        for svc in psutil.win_service_iter():
            try:
                nm = svc.name()
                if not fnmatch.fnmatch(nm.lower(), pat.lower()):
                    continue
                try:
                    info = svc.as_dict()
                except Exception:
                    info = {"name": nm}
                    try:
                        info["display_name"] = svc.display_name()
                    except Exception:
                        pass
                    try:
                        info["status"] = svc.status()
                    except Exception:
                        pass
                services.append(info)
            except Exception:
                continue
        return services
    except Exception:
        services = []

    # Fallback: PowerShell Get-Service (still read-only for detection).
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"$svcs=@(Get-Service -Name '{pat}' -ErrorAction SilentlyContinue); "
                f"if ($svcs.Count -eq 0) {{ '' }} else {{ "
                f"$svcs | Select-Object Name, DisplayName, Status | ConvertTo-Json -Compress }}"
            ),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        out = (res.stdout or "").strip()
        if not out:
            return []
        import json as _json

        parsed = _json.loads(out)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if isinstance(parsed, list):
            for d in parsed:
                if isinstance(d, dict) and d.get("Name"):
                    services.append(
                        {
                            "name": d.get("Name"),
                            "display_name": d.get("DisplayName"),
                            "status": str(d.get("Status") or "").lower(),
                        }
                    )
        return services
    except Exception:
        return []


def query_best_service(name_pattern: str) -> Optional[dict[str, Any]]:
    """Return the best matching service dict for a wildcard pattern.

    Selection prefers the highest parsed `_vX[.Y]` suffix when present, otherwise
    uses case-insensitive name sort order.
    """
    svcs = list_windows_services(name_pattern)
    if not svcs:
        return None

    def _key(d: dict[str, Any]) -> tuple[tuple[int, ...], str]:
        nm = str(d.get("name") or "")
        return (_extract_trailing_version_tuple(nm), nm.lower())

    return sorted(svcs, key=_key)[-1]
