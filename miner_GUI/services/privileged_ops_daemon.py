"""Daemon service that processes queued privileged operations.

Runs under NSSM as LocalSystem (admin). Watches the ProgramData ops_queue
for JSON requests and executes them using privileged_ops.

Processing model:
- Poll ops_queue every 500ms
- For each *.json file, parse and validate
- Execute operation
- Move to ops_processed/<id>.done.json with result metadata
- Log all errors via log_step

Installer must ensure Users: Modify on ops_queue so GUI can enqueue.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Tuple

from miner_GUI.utils.data import data_dir_gui, log_step
from miner_GUI.services import privileged_ops

# Callbacks invoked when the GUI sends a reload_config signal.
# Service components (e.g. MeasurementService, future tool managers) can
# register here so they are notified when config files change on disk.
_reload_callbacks: list = []


def register_reload_callback(fn) -> None:
    """Register a callable to be invoked on reload_config ops."""
    _reload_callbacks.append(fn)


QUEUE_DIR_NAME = "ops_queue"
PROCESSED_DIR_NAME = "ops_processed"
SLEEP_MS = 500
ALLOWED_CONFIG_PREFIXES = ("config/", "status/")


def _is_allowed_relative(rel: str, prefixes: Tuple[str, ...]) -> bool:
    try:
        # Normalize separators
        rel_norm = rel.replace("\\", "/")
        # Must start with one of the allowed prefixes
        if not any(rel_norm.startswith(p) for p in prefixes):
            return False
        # Prevent traversal and absolute paths
        p = Path(rel_norm)
        if p.is_absolute():
            return False
        if any(part == ".." for part in p.parts):
            return False
        return True
    except Exception:
        return False


def _queue_dir() -> Path:
    return data_dir_gui() / QUEUE_DIR_NAME


def _processed_dir() -> Path:
    return data_dir_gui() / PROCESSED_DIR_NAME


def _ensure_dirs() -> None:
    _queue_dir().mkdir(parents=True, exist_ok=True)
    _processed_dir().mkdir(parents=True, exist_ok=True)


def _safe_move(src: Path, dst: Path) -> None:
    try:
        src.rename(dst)
    except Exception:
        # Fallback copy+remove
        try:
            shutil.copy2(src, dst)
            src.unlink(missing_ok=True)
        except Exception:
            pass


def _process_write_config(payload: Dict[str, Any]) -> Tuple[bool, str]:
    # Support both keys: "relative_path" and "path"
    rel = str(payload.get("relative_path") or payload.get("path") or "")
    content = str(payload.get("content") or "")
    if not rel or not content:
        return False, "relative_path and content required"
    # Only permit writes under config/ or status/
    if not _is_allowed_relative(rel, ALLOWED_CONFIG_PREFIXES):
        return False, "path not allowed"
    # Optionally require .json extension for config/status
    if not rel.lower().endswith(".json"):
        return False, "only .json files allowed for config/status"
    return privileged_ops.write_config_file(rel, content)


def _process_write_measurement(payload: Dict[str, Any]) -> Tuple[bool, str]:
    group = str(payload.get("group") or "")
    data_b64 = str(payload.get("data_b64") or "")
    if not group or not data_b64:
        return False, "group and data_b64 required"
    # Sanitize group: allow only letters, digits, dash, underscore
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]+", group or ""):
        return False, "invalid group"
    try:
        import base64
        encrypted = base64.b64decode(data_b64)
    except Exception as exc:
        return False, f"Invalid base64: {exc}"
    return privileged_ops.write_measurement_file(group, encrypted)


def _process_reload_config(payload: Dict[str, Any]) -> Tuple[bool, str]:
    errors: list = []
    for fn in _reload_callbacks:
        try:
            fn()
        except Exception as exc:
            errors.append(str(exc))
            log_step("reload_config_callback_error", {"error": str(exc)})
    if errors:
        return True, f"Configuration reload signalled ({len(errors)} callback error(s))"
    return True, "Configuration reload signalled"


def _process_add_firewall_rule(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Add Windows firewall rule via privileged_ops."""
    port = payload.get("port")
    protocol = str(payload.get("protocol", "tcp"))
    direction = str(payload.get("direction", "in"))
    rule_name = payload.get("rule_name")

    if not isinstance(port, int) or port <= 0 or port > 65535:
        return False, "valid port number required"
    if protocol not in ("tcp", "udp"):
        return False, "protocol must be tcp or udp"
    if direction not in ("in", "out", "in,out"):
        return False, "direction must be in, out, or in,out"

    return privileged_ops.add_firewall_rule(
        port=port,
        protocol=protocol,
        direction=direction,
        rule_name=rule_name,
    )


# Allowed Windows service names that can be managed via the daemon
ALLOWED_SERVICE_NAMES = frozenset({"MysteriumNode"})

# Allowed Docker container names that can be managed via the daemon
ALLOWED_DOCKER_CONTAINERS = frozenset({"presearch-node"})

# Docker container specs — daemon owns image/volume/restart-policy knowledge
_DOCKER_CONTAINER_SPECS: Dict[str, Dict[str, Any]] = {
    "presearch-node": {
        "image": "presearch/node",
        "volumes": ["presearch-node-storage:/app/node"],
        "restart_policy": "unless-stopped",
    },
}


def _process_start_service(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Start a Windows service via sc/nssm."""
    import subprocess

    service_name = str(payload.get("service_name", ""))
    if not service_name:
        return False, "service_name required"
    if service_name not in ALLOWED_SERVICE_NAMES:
        return False, f"service {service_name} not in allowed list"

    # Try NSSM first (if available), then fall back to sc
    try:
        nssm_path = data_dir_gui() / "nssm.exe"
        if nssm_path.exists():
            result = subprocess.run(
                [str(nssm_path), "start", service_name],
                capture_output=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            if result.returncode == 0:
                log_step("privileged_service_started", {"service": service_name, "method": "nssm"})
                return True, f"Service {service_name} started via nssm"
            # Log but continue to try sc
            log_step("privileged_service_start_nssm_failed", {
                "service": service_name,
                "returncode": result.returncode,
                "stderr": (result.stderr or "")[:200],
            })
    except Exception as exc:
        log_step("privileged_service_start_nssm_exception", {"service": service_name, "error": str(exc)})

    # Fallback to sc
    try:
        result = subprocess.run(
            ["sc", "start", service_name],
            capture_output=True,
            timeout=30,
            encoding="utf-8",
            errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        if result.returncode == 0:
            log_step("privileged_service_started", {"service": service_name, "method": "sc"})
            return True, f"Service {service_name} started via sc"
        log_step("privileged_service_start_failed", {
            "service": service_name,
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[:200],
            "stderr": (result.stderr or "")[:200],
        })
        return False, f"Failed to start service: {(result.stderr or result.stdout or '')[:200]}"
    except Exception as exc:
        log_step("privileged_service_start_exception", {"service": service_name, "error": str(exc)})
        return False, f"Exception starting service: {exc}"


def _process_stop_service(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Stop a Windows service via sc/nssm."""
    import subprocess

    service_name = str(payload.get("service_name", ""))
    if not service_name:
        return False, "service_name required"
    if service_name not in ALLOWED_SERVICE_NAMES:
        return False, f"service {service_name} not in allowed list"

    # Try NSSM first, then fall back to sc
    try:
        nssm_path = data_dir_gui() / "nssm.exe"
        if nssm_path.exists():
            result = subprocess.run(
                [str(nssm_path), "stop", service_name],
                capture_output=True,
                timeout=30,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
            )
            if result.returncode == 0:
                log_step("privileged_service_stopped", {"service": service_name, "method": "nssm"})
                return True, f"Service {service_name} stopped via nssm"
    except Exception as exc:
        log_step("privileged_service_stop_nssm_exception", {"service": service_name, "error": str(exc)})

    # Fallback to sc
    try:
        result = subprocess.run(
            ["sc", "stop", service_name],
            capture_output=True,
            timeout=30,
            encoding="utf-8",
            errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        if result.returncode == 0:
            log_step("privileged_service_stopped", {"service": service_name, "method": "sc"})
            return True, f"Service {service_name} stopped via sc"
        log_step("privileged_service_stop_failed", {
            "service": service_name,
            "returncode": result.returncode,
            "stdout": (result.stdout or "")[:200],
            "stderr": (result.stderr or "")[:200],
        })
        return False, f"Failed to stop service: {(result.stderr or result.stdout or '')[:200]}"
    except Exception as exc:
        log_step("privileged_service_stop_exception", {"service": service_name, "error": str(exc)})
        return False, f"Exception stopping service: {exc}"


def _process_start_docker_container(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Start a Docker container. Daemon owns image/volume/env config."""
    import subprocess

    container_name = str(payload.get("container_name", ""))
    if not container_name:
        return False, "container_name required"
    if container_name not in ALLOWED_DOCKER_CONTAINERS:
        return False, f"container {container_name} not in allowed list"

    spec = _DOCKER_CONTAINER_SPECS.get(container_name)
    if not spec:
        return False, f"no spec for container {container_name}"

    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    # Check if container already running
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{{{.Names}}}}"],
            capture_output=True, text=True, timeout=10, creationflags=creationflags,
        )
        if result.returncode == 0 and container_name in result.stdout:
            log_step("docker_container_already_running", {"container": container_name})
            return True, f"Container {container_name} already running"
    except Exception:
        pass

    # Check if container exists but stopped → docker start
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{{{.Names}}}}"],
            capture_output=True, text=True, timeout=10, creationflags=creationflags,
        )
        if result.returncode == 0 and container_name in result.stdout:
            result = subprocess.run(
                ["docker", "start", container_name],
                capture_output=True, text=True, timeout=30, creationflags=creationflags,
            )
            if result.returncode == 0:
                log_step("docker_container_started", {"container": container_name})
                return True, f"Container {container_name} started"
            return False, f"Failed to start existing container: {(result.stderr or '')[:200]}"
    except Exception as exc:
        log_step("docker_start_check_failed", {"container": container_name, "error": str(exc)})

    # Container doesn't exist — read registration code from config and create
    reg_code = ""
    try:
        config_path = data_dir_gui() / "config" / "presearch_config.json"
        if config_path.exists():
            import json as _json
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            reg_code = str(cfg.get("registration_code", "") or "")
    except Exception:
        pass

    args = [
        "docker", "run", "-d",
        "--name", container_name,
        "--restart", spec.get("restart_policy", "unless-stopped"),
    ]
    for vol in spec.get("volumes", []):
        args.extend(["-v", vol])
    if reg_code:
        args.extend(["-e", f"REGISTRATION_CODE={reg_code}"])
    args.append(spec["image"])

    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=120, creationflags=creationflags,
        )
        if result.returncode == 0:
            log_step("docker_container_created", {"container": container_name})
            return True, f"Container {container_name} created and started"
        log_step("docker_container_create_failed", {
            "container": container_name,
            "returncode": result.returncode,
            "stderr": (result.stderr or "")[:200],
        })
        return False, f"Failed to create container: {(result.stderr or '')[:200]}"
    except Exception as exc:
        log_step("docker_container_create_exception", {"container": container_name, "error": str(exc)})
        return False, f"Exception creating container: {exc}"


def _process_stop_docker_container(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Stop a Docker container."""
    import subprocess

    container_name = str(payload.get("container_name", ""))
    if not container_name:
        return False, "container_name required"
    if container_name not in ALLOWED_DOCKER_CONTAINERS:
        return False, f"container {container_name} not in allowed list"

    creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    try:
        result = subprocess.run(
            ["docker", "stop", container_name],
            capture_output=True, text=True, timeout=30, creationflags=creationflags,
        )
        if result.returncode == 0:
            log_step("docker_container_stopped", {"container": container_name})
            return True, f"Container {container_name} stopped"
        log_step("docker_container_stop_failed", {
            "container": container_name,
            "returncode": result.returncode,
            "stderr": (result.stderr or "")[:200],
        })
        return False, f"Failed to stop container: {(result.stderr or '')[:200]}"
    except Exception as exc:
        log_step("docker_container_stop_exception", {"container": container_name, "error": str(exc)})
        return False, f"Exception stopping container: {exc}"


def _process_setup_presearch_firewall(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """Set up firewall rules for Presearch node (TCP 4099 inbound)."""
    return privileged_ops.add_firewall_rule(
        port=4099,
        protocol="tcp",
        direction="in",
        rule_name="Presearch Node",
    )


def _handle_file(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        op = str(payload.get("op") or "")
        req_id = str(payload.get("id") or path.stem)
        success = False
        msg = "unsupported op"

        if op == "write_config":
            success, msg = _process_write_config(payload)
        elif op == "write_measurement":
            success, msg = _process_write_measurement(payload)
        elif op == "reload_config":
            success, msg = _process_reload_config(payload)
        elif op == "add_firewall_rule":
            success, msg = _process_add_firewall_rule(payload)
        elif op == "start_service":
            success, msg = _process_start_service(payload)
        elif op == "stop_service":
            success, msg = _process_stop_service(payload)
        elif op == "start_docker_container":
            success, msg = _process_start_docker_container(payload)
        elif op == "stop_docker_container":
            success, msg = _process_stop_docker_container(payload)
        elif op == "setup_presearch_firewall":
            success, msg = _process_setup_presearch_firewall(payload)

        result = {
            "id": req_id,
            "op": op,
            "success": bool(success),
            "message": str(msg),
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_file": str(path.name),
        }
        done_path = _processed_dir() / f"{req_id}.done.json"
        done_path.write_text(json.dumps(result), encoding="utf-8")
        _safe_move(path, _processed_dir() / f"{path.name}.processed")
        log_step("ops_daemon_processed", {"op": op, "success": success})
    except Exception as exc:
        log_step("ops_daemon_handle_failed", {"file": str(path), "error": str(exc)})
        # Move to processed with error suffix
        err_path = _processed_dir() / f"{path.name}.error"
        _safe_move(path, err_path)


def run() -> None:
    log_step("ops_daemon_start", {})
    _ensure_dirs()
    while True:
        try:
            for path in sorted(_queue_dir().glob("*.json")):
                _handle_file(path)
        except Exception as exc:
            log_step("ops_daemon_loop_error", {"error": str(exc)})
        time.sleep(SLEEP_MS / 1000.0)


if __name__ == "__main__":
    run()
