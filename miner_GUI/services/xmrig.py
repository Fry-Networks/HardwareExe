"""XMRig mining integration for SVN miners.

Controls an XMRig-based mining process that validates storage transactions
via Monero proof-of-work. The binary runs locally (no Docker).

References:
- XMRig HTTP API: https://xmrig.com/docs/miner/api
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config_profile import GROUP
from miner_GUI.config import app_dir
from miner_GUI.utils.data import data_dir_gui, log_step

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


CONFIG_FILE_NAME = "xmrig_config.json"
BINARY_NAME = "fry-validator.exe" if os.name == "nt" else "fry-validator"
XMRIG_CONFIG_NAME = "xmrig-runtime.json"


@dataclass
class XMRigStatus:
    """Status surface for XMRig mining UI."""

    configured: bool
    running: bool
    connected: bool
    hashrate_10s: float
    hashrate_60s: float
    hashrate_15m: float
    hashrate_max: float
    shares_good: int
    shares_total: int
    diff_current: int
    pool_connected: bool
    algorithm: Optional[str]
    uptime_seconds: int
    cpu_temp: Optional[float]
    cpu_usage: Optional[float]
    last_error: Optional[str]
    last_refresh: datetime
    pending: bool = False


class XMRigConfig:
    """Configuration for XMRig mining integration."""

    def __init__(self, path: Path, existed: bool, raw: Optional[Dict[str, Any]] = None):
        self.path = path
        self._raw = raw or {}
        self._existed = existed
        self._pool_url = str(self._raw.get("pool_url", "") or "")
        self._wallet_address = str(self._raw.get("wallet_address", "") or "")
        self._worker_name = str(self._raw.get("worker_name", "") or "")
        self._api_port = int(self._raw.get("api_port", 18080) or 18080)
        self._cpu_max_threads_hint = int(self._raw.get("cpu_max_threads_hint", 75) or 75)

    @property
    def existed(self) -> bool:
        return self._existed

    @property
    def pool_url(self) -> str:
        return self._pool_url

    @property
    def wallet_address(self) -> str:
        return self._wallet_address

    @property
    def worker_name(self) -> str:
        return self._worker_name

    @property
    def api_port(self) -> int:
        return self._api_port

    @property
    def cpu_max_threads_hint(self) -> int:
        return self._cpu_max_threads_hint

    def persist(self) -> None:
        try:
            from miner_GUI.utils.data import data_dir_gui
            from miner_GUI.utils.ops_queue_client import enqueue_write_config

            content = json.dumps(self._raw, indent=2, sort_keys=True)

            try:
                base_dir = data_dir_gui()
                rel_path = str(self.path.relative_to(base_dir))
                success, msg = enqueue_write_config(rel_path, content)
                if not success:
                    log_step("xmrig_config_save_failed", {"error": msg})
                    return
            except (ValueError, OSError):
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "w", encoding="utf-8") as handle:
                    json.dump(self._raw, handle, indent=2, sort_keys=True)
        except Exception as exc:
            log_step("xmrig_config_save_failed", {"error": str(exc)})


def _candidate_config_dirs() -> list[Path]:
    """Get candidate directories for configuration files."""
    candidates: list[Path] = []
    try:
        candidates.append(data_dir_gui() / "config")
    except Exception:
        pass
    candidates.append(app_dir() / "config")
    candidates.append(Path.cwd() / "config")
    return candidates


def locate_config_file() -> Tuple[Path, bool, Dict[str, Any]]:
    """Locate and load XMRig configuration file."""
    candidate_dirs = _candidate_config_dirs()
    candidate_files = [p / CONFIG_FILE_NAME for p in candidate_dirs if p]

    for file_path in candidate_files:
        if file_path.exists():
            try:
                data = json.load(open(file_path, "r", encoding="utf-8"))
            except Exception:
                data = {}
            return file_path, True, data

    fallback = candidate_files[0] if candidate_files else (Path.cwd() / "config" / CONFIG_FILE_NAME)
    return fallback, False, {}


def load_config() -> XMRigConfig:
    """Load XMRig configuration."""
    path, existed, data = locate_config_file()
    return XMRigConfig(path=path, existed=existed, raw=data)


class XMRigController:
    """Controller to manage XMRig mining lifecycle."""

    def __init__(self) -> None:
        self.config = load_config()
        self._last_error: Optional[str] = None
        self._binary_path = self._find_binary()
        self._pid: Optional[int] = None

    def _find_binary(self) -> Optional[Path]:
        """Locate the XMRig binary."""
        # Check environment variable first
        env_path = os.environ.get("XMRIG_BIN")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p

        # Check standard install locations
        candidates = []
        try:
            candidates.append(data_dir_gui() / "SDK" / "xmrig" / BINARY_NAME)
        except Exception:
            pass
        candidates.append(app_dir() / "SDK" / "xmrig" / BINARY_NAME)
        candidates.append(Path.cwd() / "SDK" / "xmrig" / BINARY_NAME)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _generate_xmrig_config(self) -> Optional[Path]:
        """Generate XMRig runtime config JSON in the miner directory."""
        if not self.config.pool_url or not self.config.wallet_address:
            return None

        config_data = {
            "autosave": False,
            "cpu": {
                "enabled": True,
                "max-threads-hint": self.config.cpu_max_threads_hint,
            },
            "opencl": False,
            "cuda": False,
            "pools": [
                {
                    "url": self.config.pool_url,
                    "user": self.config.wallet_address,
                    "pass": self.config.worker_name or "x",
                    "keepalive": True,
                    "tls": False,
                }
            ],
            "http": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": self.config.api_port,
                "access-token": None,
                "restricted": True,
            },
            "donate-level": 0,
            "log-file": None,
            "print-time": 60,
            "background": False,
        }

        try:
            config_dir = self.config.path.parent
            config_dir.mkdir(parents=True, exist_ok=True)
            config_path = config_dir / XMRIG_CONFIG_NAME
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
            return config_path
        except Exception as exc:
            log_step("xmrig_config_generate_failed", {"error": str(exc)})
            return None

    def is_running(self) -> bool:
        """Check if XMRig process is running."""
        if self._pid is not None:
            try:
                if os.name == "nt":
                    result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {self._pid}", "/NH"],
                        capture_output=True, text=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    return str(self._pid) in result.stdout
                else:
                    os.kill(self._pid, 0)
                    return True
            except Exception:
                self._pid = None

        # Fallback: check by process name
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {BINARY_NAME}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return BINARY_NAME.lower() in result.stdout.lower()
            else:
                result = subprocess.run(
                    ["pgrep", "-f", BINARY_NAME],
                    capture_output=True, text=True, timeout=5,
                )
                return result.returncode == 0
        except Exception:
            return False

    def start(self) -> bool:
        """Start XMRig mining process."""
        if self._binary_path is None:
            self._last_error = "XMRig binary not found"
            log_step("xmrig_start_failed", {"reason": "binary_not_found"})
            return False

        if not self.config.pool_url or not self.config.wallet_address:
            self._last_error = "Pool URL or wallet address not configured"
            log_step("xmrig_start_failed", {"reason": "not_configured"})
            return False

        if self.is_running():
            log_step("xmrig_already_running")
            return True

        config_path = self._generate_xmrig_config()
        if config_path is None:
            self._last_error = "Failed to generate XMRig config"
            return False

        try:
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
            proc = subprocess.Popen(
                [str(self._binary_path), f"--config={config_path}"],
                cwd=str(self._binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self._pid = proc.pid
            log_step("xmrig_started", {"pid": self._pid})
            return True
        except Exception as exc:
            self._last_error = str(exc)
            log_step("xmrig_start_failed", {"error": str(exc)})
            return False

    def stop(self) -> bool:
        """Stop XMRig mining process."""
        if not self.is_running():
            return True

        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/IM", BINARY_NAME],
                    capture_output=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", BINARY_NAME],
                    capture_output=True, timeout=10,
                )
            self._pid = None
            log_step("xmrig_stopped")
            return True
        except Exception as exc:
            log_step("xmrig_stop_failed", {"error": str(exc)})
            return False

    def _api_call(self) -> Optional[Dict[str, Any]]:
        """Call XMRig HTTP API for status."""
        if not HAVE_REQUESTS:
            return None

        try:
            resp = requests.get(
                f"http://127.0.0.1:{self.config.api_port}/1/summary",
                timeout=5,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def refresh_status(self) -> XMRigStatus:
        """Poll XMRig status via HTTP API."""
        running = self.is_running()
        connected = False
        hashrate_10s = 0.0
        hashrate_60s = 0.0
        hashrate_15m = 0.0
        hashrate_max = 0.0
        shares_good = 0
        shares_total = 0
        diff_current = 0
        pool_connected = False
        algorithm = None
        uptime_seconds = 0
        cpu_temp = None
        cpu_usage = None

        if running:
            data = self._api_call()
            if data:
                connected = True
                hr = data.get("hashrate", {})
                totals = hr.get("total", [0, 0, 0])
                hashrate_10s = float(totals[0] or 0) if len(totals) > 0 else 0.0
                hashrate_60s = float(totals[1] or 0) if len(totals) > 1 else 0.0
                hashrate_15m = float(totals[2] or 0) if len(totals) > 2 else 0.0
                hashrate_max = float(hr.get("highest", 0) or 0)

                results = data.get("results", {})
                shares_good = int(results.get("shares_good", 0) or 0)
                shares_total = int(results.get("shares_total", 0) or 0)
                diff_current = int(results.get("diff_current", 0) or 0)

                conn = data.get("connection", {})
                pool_connected = bool(conn.get("pool"))
                algorithm = conn.get("algo")
                uptime_seconds = int(conn.get("uptime", 0) or 0)

                cpu = data.get("cpu", {})
                cpu_temp = cpu.get("temperature") if isinstance(cpu.get("temperature"), (int, float)) else None
            else:
                self._last_error = "API unreachable"

        return XMRigStatus(
            configured=self.config.existed and bool(self.config.pool_url) and bool(self.config.wallet_address),
            running=running,
            connected=connected,
            hashrate_10s=hashrate_10s,
            hashrate_60s=hashrate_60s,
            hashrate_15m=hashrate_15m,
            hashrate_max=hashrate_max,
            shares_good=shares_good,
            shares_total=shares_total,
            diff_current=diff_current,
            pool_connected=pool_connected,
            algorithm=algorithm,
            uptime_seconds=uptime_seconds,
            cpu_temp=cpu_temp,
            cpu_usage=cpu_usage,
            last_error=self._last_error,
            last_refresh=datetime.utcnow(),
        )

    @property
    def binary_available(self) -> bool:
        return self._binary_path is not None

    def _update_status_json_on_offline(self) -> None:
        """Update today's status JSON to remove XMRig from tools."""
        try:
            status_dir = data_dir_gui() / "status"
            now = datetime.utcnow()
            current_hour = now.hour
            json_path = status_dir / f"status-{now.strftime('%Y%m%d')}.json"

            if not json_path.exists():
                return

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            rewards_slots = data.get("rewards_multiplier_slots", {})
            if rewards_slots:
                for hour_str, slot_data in rewards_slots.items():
                    try:
                        hour = int(hour_str)
                        if hour >= current_hour and isinstance(slot_data, dict):
                            tools = slot_data.get("tools", [])
                            if isinstance(tools, list) and "XMRig" in tools:
                                tools.remove("XMRig")
                                slot_data["tools"] = tools
                    except (ValueError, TypeError):
                        continue

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as exc:
            log_step("status_json_update_failed", {"error": str(exc)})

    def mark_offline(self) -> None:
        """Call this when XMRig is detected as offline."""
        self._update_status_json_on_offline()
