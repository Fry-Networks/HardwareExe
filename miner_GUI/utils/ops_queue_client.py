"""Lightweight client for enqueuing privileged operations to the service.

The GUI runs without admin rights. To perform privileged file writes under
ProgramData, it enqueues requests into an `ops_queue` directory that the
installer configures with Users: Modify permissions.

The NSSM service runs a daemon (`privileged_ops_daemon.py`) that watches
this queue and executes the requested operations with admin privileges.

Queue file format (JSON):
{
  "id": "<uuid>",
  "op": "write_config" | "write_measurement" | "reload_config",
  "relative_path": "config/bright.json",        # for write_config
  "content": "{...}",                           # JSON string content
  "group": "mysterium",                         # for write_measurement
  "data_b64": "<base64-encoded bytes>",         # encrypted bytes
  "created_at": "2026-01-08T12:34:56Z"
}

Filenames: `op_<timestamp>_<uuid>.json`
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from miner_GUI.utils.data import data_dir_gui, log_step

QUEUE_DIR_NAME = "ops_queue"
PROCESSED_DIR_NAME = "ops_processed"


def _queue_dir() -> Path:
    base = data_dir_gui()
    return base / QUEUE_DIR_NAME


def _processed_dir() -> Path:
    base = data_dir_gui()
    return base / PROCESSED_DIR_NAME


def _ensure_queue_dirs() -> bool:
    try:
        _queue_dir().mkdir(parents=True, exist_ok=True)
        _processed_dir().mkdir(parents=True, exist_ok=True)
        return True
    except Exception as exc:
        log_step("ops_queue_mkdir_failed", {"error": str(exc)})
        return False


def _make_queue_file(op: str) -> Path:
    ts = int(time.time() * 1000)
    uid = uuid.uuid4().hex
    return _queue_dir() / f"op_{ts}_{uid}_{op}.json"


def enqueue_write_config(relative_path: str, content: str) -> Tuple[bool, str]:
    """Enqueue a request to write JSON config to ProgramData via the service.
    
    Args:
        relative_path: Path relative to data_dir_gui(), e.g., "config/bright.json"
        content: JSON string content
    Returns:
        (success, message)
    """
    if not isinstance(relative_path, str) or not relative_path:
        return False, "relative_path must be a non-empty string"
    if not isinstance(content, str) or not content:
        return False, "content must be a non-empty JSON string"

    # Normalize and sanitize the incoming path so the service receives only the filename
    # (no leading directories). The service layer already decides where to place the file.
    try:
        base_dir = data_dir_gui()
        rel_path_obj = Path(relative_path)

        # If caller accidentally passed an absolute path, make it relative to data_dir_gui
        if rel_path_obj.is_absolute():
            try:
                rel_path_obj = rel_path_obj.relative_to(base_dir)
            except Exception:
                return False, "relative_path must be under ProgramData miner directory"

        # Drop all leading directories; keep only the file name.
        # This prevents callers from sending paths like "config/config/foo.json"
        # or "status/status-20260109.json". Service side will place the file.
        relative_path = rel_path_obj.name
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"Failed to normalize relative_path: {exc}"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable (installer must set ACLs)"

    payload: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "op": "write_config",
        "relative_path": relative_path.replace("\\", "/"),
        "content": content,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _make_queue_file("write_config")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_write_config", {"file": str(path), "rel": relative_path})
        return True, "Enqueued write_config"
    except Exception as exc:
        log_step("ops_enqueue_write_config_failed", {"error": str(exc)})
        return False, f"Failed to enqueue write_config: {exc}"


def enqueue_write_measurement(group: str, encrypted_bytes: bytes) -> Tuple[bool, str]:
    """Enqueue a request to write encrypted measurement via the service.
    
    Args:
        group: Measurement group identifier (e.g., "mysterium")
        encrypted_bytes: Already-encrypted bytes
    Returns:
        (success, message)
    """
    if not isinstance(group, str) or not group:
        return False, "group must be a non-empty string"
    if not isinstance(encrypted_bytes, (bytes, bytearray)) or not encrypted_bytes:
        return False, "encrypted_bytes must be non-empty"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable (installer must set ACLs)"

    data_b64 = base64.b64encode(encrypted_bytes).decode("ascii")

    payload: Dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "op": "write_measurement",
        "group": group,
        "data_b64": data_b64,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _make_queue_file("write_measurement")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_write_measurement", {"file": str(path), "group": group})
        return True, "Enqueued write_measurement"
    except Exception as exc:
        log_step("ops_enqueue_write_measurement_failed", {"error": str(exc)})
        return False, f"Failed to enqueue write_measurement: {exc}"


def write_status_file(relative_path: str, content: str) -> Tuple[bool, str]:
    """Write status file directly to the data_dir without going through ops_queue.
    
    Status files (like status-YYYYMMDD.json) don't require privilege elevation
    when written directly to data_dir, unlike config files in subdirectories.
    
    Args:
        relative_path: Path relative to data_dir_gui(), e.g., "status/status-20260109.json"
        content: JSON string content
        
    Returns:
        (success, message)
    """
    try:
        if not isinstance(relative_path, str) or not relative_path:
            return False, "relative_path must be a non-empty string"
        if not isinstance(content, str) or not content:
            return False, "content must be a non-empty JSON string"
        
        base_dir = data_dir_gui()
        # Drop any leading directories; write into status directory at ProgramData
        filename = Path(relative_path).name
        full_path = base_dir / "status" / filename
        
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write atomically: temp file + rename
        temp_path = full_path.with_suffix(full_path.suffix + '.tmp')
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(full_path)
        
        log_step("write_status_file", {"path": str(full_path)})
        return True, f"Status file written: {relative_path}"
    except Exception as exc:
        error_str = str(exc)
        log_step("write_status_file_failed", {"path": relative_path, "error": error_str})
        return False, f"Failed to write status file {relative_path}: {error_str}"


def enqueue_add_firewall_rule(
    port: int,
    protocol: str = "tcp",
    direction: str = "in",
    rule_name: Optional[str] = None,
    wait_for_result: bool = True,
    timeout_seconds: int = 15,
) -> Tuple[bool, str]:
    """Enqueue a request to add a Windows firewall rule via the service.

    Args:
        port: Port number to open
        protocol: 'tcp' or 'udp'
        direction: 'in', 'out', or 'in,out'
        rule_name: Optional custom rule name
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result (if wait_for_result=True)

    Returns:
        (success, message)
    """
    if not isinstance(port, int) or port <= 0 or port > 65535:
        return False, "Invalid port number"
    if protocol not in ("tcp", "udp"):
        return False, "Protocol must be tcp or udp"
    if direction not in ("in", "out", "in,out"):
        return False, "Direction must be in, out, or in,out"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "add_firewall_rule",
        "port": port,
        "protocol": protocol,
        "direction": direction,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if rule_name:
        payload["rule_name"] = rule_name

    path = _make_queue_file("add_firewall_rule")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_add_firewall_rule", {"file": str(path), "port": port, "protocol": protocol})
    except Exception as exc:
        log_step("ops_enqueue_add_firewall_rule_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued add_firewall_rule"

    # Wait for result
    return _wait_for_result(request_id, timeout_seconds, "add_firewall_rule")


def enqueue_start_service(
    service_name: str,
    wait_for_result: bool = True,
    timeout_seconds: int = 45,
) -> Tuple[bool, str]:
    """Enqueue a request to start a Windows service via the daemon.

    Args:
        service_name: Name of the Windows service (e.g., 'MysteriumNode')
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not service_name:
        return False, "service_name required"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "start_service",
        "service_name": service_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("start_service")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_start_service", {"file": str(path), "service": service_name})
    except Exception as exc:
        log_step("ops_enqueue_start_service_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued start_service"

    return _wait_for_result(request_id, timeout_seconds, "start_service")


def enqueue_stop_service(
    service_name: str,
    wait_for_result: bool = True,
    timeout_seconds: int = 30,
) -> Tuple[bool, str]:
    """Enqueue a request to stop a Windows service via the daemon.

    Args:
        service_name: Name of the Windows service (e.g., 'MysteriumNode')
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not service_name:
        return False, "service_name required"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "stop_service",
        "service_name": service_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("stop_service")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_stop_service", {"file": str(path), "service": service_name})
    except Exception as exc:
        log_step("ops_enqueue_stop_service_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued stop_service"

    return _wait_for_result(request_id, timeout_seconds, "stop_service")


def enqueue_start_docker_container(
    container_name: str,
    wait_for_result: bool = True,
    timeout_seconds: int = 120,
) -> Tuple[bool, str]:
    """Enqueue a request to start a Docker container via the daemon.

    The daemon knows the image, volumes, and env for allowed containers.

    Args:
        container_name: Name of the Docker container (e.g., 'presearch-node')
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait (default 120s — Docker pull can be slow)

    Returns:
        (success, message)
    """
    if not container_name:
        return False, "container_name required"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "start_docker_container",
        "container_name": container_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("start_docker_container")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_start_docker_container", {"file": str(path), "container": container_name})
    except Exception as exc:
        log_step("ops_enqueue_start_docker_container_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, request_id

    return _wait_for_result(request_id, timeout_seconds, "start_docker_container")


def enqueue_stop_docker_container(
    container_name: str,
    wait_for_result: bool = True,
    timeout_seconds: int = 30,
) -> Tuple[bool, str]:
    """Enqueue a request to stop a Docker container via the daemon.

    Args:
        container_name: Name of the Docker container (e.g., 'presearch-node')
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not container_name:
        return False, "container_name required"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "stop_docker_container",
        "container_name": container_name,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("stop_docker_container")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_stop_docker_container", {"file": str(path), "container": container_name})
    except Exception as exc:
        log_step("ops_enqueue_stop_docker_container_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued stop_docker_container"

    return _wait_for_result(request_id, timeout_seconds, "stop_docker_container")


def enqueue_setup_presearch_firewall(
    wait_for_result: bool = True,
    timeout_seconds: int = 15,
) -> Tuple[bool, str]:
    """Enqueue a request to set up Presearch firewall rules via the daemon.

    The daemon knows the port (4099 TCP inbound). No parameters needed.

    Args:
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "setup_presearch_firewall",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("setup_presearch_firewall")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_setup_presearch_firewall", {"file": str(path)})
    except Exception as exc:
        log_step("ops_enqueue_setup_presearch_firewall_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued setup_presearch_firewall"

    return _wait_for_result(request_id, timeout_seconds, "setup_presearch_firewall")


def enqueue_configure_spaceacres(
    farm_path: str,
    farm_size: str,
    wait_for_result: bool = True,
    timeout_seconds: int = 15,
) -> Tuple[bool, str]:
    """Enqueue a request to configure Space Acres farm settings via the daemon.

    Must be called before start_docker_container("spaceacres-node").
    The daemon writes the config to gui_config.enc → spaceacres_config.

    Args:
        farm_path: Full folder path on the selected SSD (e.g. "D:\\autonomys-farm")
        farm_size: Allocated size with unit suffix (e.g. "100G", "500G", "1T")
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not farm_path:
        return False, "farm_path required"
    if not farm_size:
        return False, "farm_size required"

    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "configure_spaceacres",
        "farm_path": farm_path,
        "farm_size": farm_size,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("configure_spaceacres")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_configure_spaceacres", {"file": str(path), "farm_path": farm_path, "farm_size": farm_size})
    except Exception as exc:
        log_step("ops_enqueue_configure_spaceacres_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued configure_spaceacres"

    return _wait_for_result(request_id, timeout_seconds, "configure_spaceacres")


def enqueue_setup_spaceacres_firewall(
    wait_for_result: bool = True,
    timeout_seconds: int = 15,
) -> Tuple[bool, str]:
    """Enqueue a request to set up Space Acres firewall rules via the daemon.

    Opens ports 30333/TCP (Node P2P), 30433/TCP (Farmer DSN), 9944/TCP (Node RPC).

    Args:
        wait_for_result: If True, wait for daemon to process and return result
        timeout_seconds: How long to wait for result

    Returns:
        (success, message)
    """
    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"

    request_id = uuid.uuid4().hex
    payload: Dict[str, Any] = {
        "id": request_id,
        "op": "setup_spaceacres_firewall",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    path = _make_queue_file("setup_spaceacres_firewall")
    try:
        path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_enqueue_setup_spaceacres_firewall", {"file": str(path)})
    except Exception as exc:
        log_step("ops_enqueue_setup_spaceacres_firewall_failed", {"error": str(exc)})
        return False, f"Failed to enqueue: {exc}"

    if not wait_for_result:
        return True, "Enqueued setup_spaceacres_firewall"

    return _wait_for_result(request_id, timeout_seconds, "setup_spaceacres_firewall")


def _wait_for_result(request_id: str, timeout_seconds: int, op_name: str) -> Tuple[bool, str]:
    """Wait for a daemon operation result."""
    processed_path = _processed_dir() / f"{request_id}.done.json"
    poll_interval = 0.2  # 200ms
    max_polls = int(timeout_seconds / poll_interval)

    for _ in range(max_polls):
        if processed_path.exists():
            try:
                result_data = json.loads(processed_path.read_text(encoding="utf-8"))
                success = result_data.get("success", False)
                message = result_data.get("message", f"{op_name} complete")

                if success:
                    log_step(f"ops_{op_name}_success", {"request_id": request_id})
                    return True, message
                else:
                    log_step(f"ops_{op_name}_failed", {"request_id": request_id, "message": message})
                    return False, message
            except Exception as e:
                log_step(f"ops_{op_name}_parse_error", {"error": str(e)})
                return False, f"Failed to parse result: {e}"

        time.sleep(poll_interval)

    log_step(f"ops_{op_name}_timeout", {"request_id": request_id, "timeout_seconds": timeout_seconds})
    return False, f"Service did not respond within {timeout_seconds} seconds"


def send_reload_config_signal(timeout_seconds: int = 10) -> Tuple[bool, str]:
    """Send reload_config signal to service via IPC queue.
    
    After writing configuration files, GUI sends this signal to notify
    the service to reload configuration from disk.
    
    Args:
        timeout_seconds: How long to wait for service acknowledgment (default: 10)
        
    Returns:
        (success, message)
    """
    if not _ensure_queue_dirs():
        return False, "Queue directory is not writable"
    
    try:
        # Generate unique request ID
        request_id = uuid.uuid4().hex
        
        # Create request payload
        payload: Dict[str, Any] = {
            "id": request_id,
            "op": "reload_config",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        
        # Write request to ops_queue
        queue_path = _queue_dir() / f"{request_id}.json"
        queue_path.write_text(json.dumps(payload), encoding="utf-8")
        log_step("ops_send_reload_config", {"request_id": request_id})
        
        # Poll for result in ops_processed
        processed_path = _processed_dir() / f"{request_id}.done.json"
        poll_interval = 0.1  # 100ms
        max_polls = int(timeout_seconds / poll_interval)
        
        for _ in range(max_polls):
            if processed_path.exists():
                try:
                    result_data = json.loads(processed_path.read_text(encoding="utf-8"))
                    success = result_data.get("success", False)
                    message = result_data.get("message", "Configuration reload complete")
                    
                    if success:
                        log_step("ops_reload_config_success", {"request_id": request_id})
                        return True, message
                    else:
                        error = result_data.get("error", "Unknown error")
                        log_step("ops_reload_config_failed", {"request_id": request_id, "error": error})
                        return False, f"Service error: {error}"
                except Exception as e:
                    log_step("ops_reload_config_parse_error", {"error": str(e)})
                    return False, f"Failed to parse result: {e}"
            
            time.sleep(poll_interval)
        
        # Timeout
        log_step("ops_reload_config_timeout", {"request_id": request_id, "timeout_seconds": timeout_seconds})
        return False, f"Service did not acknowledge reload_config within {timeout_seconds} seconds"
        
    except Exception as exc:
        log_step("ops_send_reload_config_exception", {"error": str(exc)})
        return False, f"Failed to send reload_config signal: {exc}"
