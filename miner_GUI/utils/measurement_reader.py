"""Measurement reader for autonomous service integration.

Reads real-time and historical measurements written by the autonomous service
to ProgramData (Windows) or /opt/frynetworks (Linux/macOS). No legacy fallbacks
remain; if the service has not produced data yet, callers receive explicit
errors and should surface them in the UI.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config_profile import MINER_CODE
from miner_GUI.utils.data import log_step


def _get_measurements_dir() -> Path:
    r"""Return the shared measurements directory created by the service.

    Windows: %PROGRAMDATA%\FryNetworks\miner-{MINER_CODE}\measurements\
    Linux/macOS: /opt/frynetworks/miner-{MINER_CODE}/measurements/
    """
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
        return base / "FryNetworks" / f"miner-{MINER_CODE}" / "measurements"
    return Path("/opt/frynetworks") / f"miner-{MINER_CODE}" / "measurements"


def read_latest_measurements() -> Tuple[bool, Dict[str, Any] | str]:
    """Read plaintext measurements written by the autonomous service.

    Returns:
        (True, dict) on success
        (False, "error message") on failure
    """
    try:
        measurements_dir = _get_measurements_dir()
        latest_path = measurements_dir / "latest.json"

        if not latest_path.exists():
            return False, f"Measurements file not found: {latest_path}"

        with open(latest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return True, data
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON in measurements/latest.json: {exc}"
        log_step("measurements_read_json_error", {"error": str(exc)})
        return False, msg
    except Exception as exc:  # pragma: no cover - best-effort logging
        log_step("measurements_read_failed", {"error": str(exc), "error_type": type(exc).__name__})
        return False, f"Failed to read measurements: {exc}"


def get_pod_status() -> Dict[str, Any]:
    """Extract PoD status block from measurements.

    Returns empty dict on failure/missing data; the caller can decide UX.
    """
    success, data = read_latest_measurements()
    if not success or not isinstance(data, dict):
        return {}

    pod = data.get("pod_status")
    pod_timestamp = data.get("pod_timestamp")
    pod_version = data.get("pod_version")
    result: Dict[str, Any] = {}
    if pod is not None:
        result["pod_status"] = pod
    if pod_timestamp is not None:
        result["pod_timestamp"] = pod_timestamp
    if pod_version is not None:
        result["pod_version"] = pod_version
    return result


def get_hardware_stats() -> Dict[str, Any]:
    """Extract hardware statistics from measurements.

    Returns empty dict on failure/missing data.
    """
    success, data = read_latest_measurements()
    if not success or not isinstance(data, dict):
        return {}
    hw = data.get("hardware_stats")
    return hw if isinstance(hw, dict) else {}


def get_poc_status(poc_name: str) -> Optional[Dict[str, Any]]:
    """Return status for a named PoC (e.g., "Mysterium")."""
    success, data = read_latest_measurements()
    if not success or not isinstance(data, dict):
        return None
    poc_apps = data.get("poc_applications")
    if isinstance(poc_apps, dict):
        return poc_apps.get(poc_name)
    return None


def list_historical_measurements() -> List[str]:
    """List encrypted historical measurement files (names only)."""
    try:
        measurements_dir = _get_measurements_dir()
        if not measurements_dir.exists():
            return []
        encrypted_files = sorted(measurements_dir.glob("measurements_*.enc"))
        return [f.name for f in encrypted_files]
    except Exception:
        return []


def get_measurement_timestamp() -> Optional[datetime]:
    """Return the timestamp of the latest measurements as a datetime."""
    success, data = read_latest_measurements()
    if not success or not isinstance(data, dict):
        return None
    raw = data.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def is_measurement_stale(max_age_seconds: float = 60) -> bool:
    """Return True if measurements are older than max_age_seconds."""
    ts = get_measurement_timestamp()
    if ts is None:
        return True
    now = datetime.now(timezone.utc)
    ts_utc = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    age = (now - ts_utc).total_seconds()
    return age > max_age_seconds
