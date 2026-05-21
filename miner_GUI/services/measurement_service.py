"""Autonomous measurement collection loop for the service.

Runs sensor-specific loops on background threads, writes append-only CSV logs,
and optionally forwards each sample to a backend sender callback.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from miner_GUI.services.service_csv_writer import ServiceCsvWriter
from miner_GUI.services import measurement_sources as sources
from miner_GUI.utils.data import data_dir_gui, log_step
from miner_GUI.utils.device_config import read_device_config, save_serial_settings

BackendSender = Callable[[str, Dict[str, Any]], None]


def _first(cfg: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in cfg and cfg[key] not in (None, ""):
            return cfg[key]
    return default


@dataclass
class SensorLoop:
    name: str
    interval: float
    sampler: Callable[[], Dict[str, Any]]
    fields: List[str]


class MeasurementService:
    """Coordinate sensor sampling, CSV logging, and backend forwarding."""

    def __init__(self, writer: Optional[ServiceCsvWriter] = None, backend_sender: Optional[BackendSender] = None) -> None:
        self.writer = writer or ServiceCsvWriter()
        self.backend_sender = backend_sender
        self.stop_event = threading.Event()
        self.threads: List[threading.Thread] = []
        self._last_error: Dict[str, float] = {}

    def start(self) -> None:
        if self.threads:
            return  # Already running
        loops = self._build_loops()
        for loop in loops:
            t = threading.Thread(target=self._run_loop, args=(loop,), daemon=True)
            t.start()
            self.threads.append(t)
        log_step("measurement_service_started", {"loops": [l.name for l in loops]})

    def stop(self, timeout: float = 5.0) -> None:
        self.stop_event.set()
        for t in self.threads:
            t.join(timeout=timeout)
        self.threads = []
        log_step("measurement_service_stopped", {})

    def run_forever(self) -> None:
        self.start()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.stop()

    def _build_loops(self) -> List[SensorLoop]:
        cfg = read_device_config()
        iface_pref = _first(cfg, ["interface", "network_interface"], None)

        gps_port = _first(cfg, ["gps_port", "gps_device", "serial_port_gps", "serial_port"], "")
        gps_baud = int(_first(cfg, ["gps_baud", "gps_baud_rate", "gps_baudrate", "baud_rate"], 9600) or 9600)

        geiger_port = _first(cfg, ["geiger_port", "radiation_port", "serial_port_geiger", "serial_port"], "")
        geiger_baud = int(_first(cfg, ["geiger_baud", "radiation_baud", "geiger_baud_rate", "baud_rate"], 9600) or 9600)

        mic_idx = cfg.get("microphone_index")

        return [
            SensorLoop(
                name="bm",
                interval=2.0,
                sampler=lambda iface=iface_pref: sources.sample_bandwidth(iface),
                fields=["timestamp", "dl", "ul", "iface"],
            ),
            SensorLoop(
                name="satellite",
                interval=10.0,
                sampler=lambda port=gps_port, baud=gps_baud: sources.sample_gnss(port, baud),
                fields=["timestamp", "sats", "fix", "lat", "lon", "alt", "hdop"],
            ),
            SensorLoop(
                name="radiation",
                interval=10.0,
                sampler=lambda port=geiger_port, baud=geiger_baud: sources.sample_geiger(port, baud),
                fields=["timestamp", "cpm", "usv", "usv_hour", "mr", "cps"],
            ),
            SensorLoop(
                name="decibel",
                interval=2.0,
                sampler=lambda idx=mic_idx: sources.sample_decibel(idx),
                fields=["timestamp", "dbfs"],
            ),
            SensorLoop(
                name="aem",
                interval=600.0,
                sampler=sources.sample_aem,
                fields=["timestamp", "poi"],
            ),
        ]

    def _run_loop(self, loop: SensorLoop) -> None:
        while not self.stop_event.is_set():
            err_msg: Optional[str] = None
            data: Any = None
            try:
                data = loop.sampler()
                if data and "err" not in data:
                    ts = datetime.utcnow().isoformat() + "Z"
                    row = {"timestamp": ts}
                    row.update({k: v for k, v in data.items() if not k.startswith("_")})
                    self.writer.append_row(loop.name, row, loop.fields)
                    self._send_to_backend(loop.name, row)
                    self._clear_status_sidecar(loop.name)
                    if data.get("_detected_baud"):
                        try:
                            cfg = read_device_config()
                            port = cfg.get("serial_port") or cfg.get("gps_port") or cfg.get("geiger_port") or ""
                            if port:
                                save_serial_settings(port, data["_detected_baud"])
                        except Exception:
                            pass
                else:
                    err_msg = data.get("err") if isinstance(data, dict) else "unknown error"
                    self._log_throttled_error(loop.name, err_msg)
            except Exception as exc:
                err_msg = str(exc)
                self._log_throttled_error(loop.name, err_msg)
            if err_msg:
                extra: Optional[Dict[str, Any]] = None
                if isinstance(data, dict) and data.get("_detected_baud"):
                    extra = {"_detected_baud": data["_detected_baud"]}
                self._write_status_sidecar(loop.name, err_msg, extra)
            self.stop_event.wait(loop.interval)

    def _log_throttled_error(self, sensor: str, message: Optional[str]) -> None:
        if not message:
            return
        now = time.time()
        last = self._last_error.get(sensor, 0)
        if now - last < 30:
            return
        self._last_error[sensor] = now
        log_step("measurement_loop_error", {"sensor": sensor, "error": message})

    def _send_to_backend(self, sensor: str, row: Dict[str, Any]) -> None:
        if not self.backend_sender:
            return
        try:
            self.backend_sender(sensor, row)
        except Exception as exc:
            log_step("measurement_backend_send_failed", {"sensor": sensor, "error": str(exc)})

    def _status_sidecar_path(self, sensor: str) -> Path:
        return self.writer.log_dir / f"{sensor}_status.json"

    def _write_status_sidecar(self, sensor: str, err: str, extra: Optional[Dict[str, Any]] = None) -> None:
        try:
            path = self._status_sidecar_path(sensor)
            payload: Dict[str, Any] = {"err": err, "ts": datetime.utcnow().isoformat() + "Z"}
            if extra:
                payload.update(extra)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
        except Exception:
            pass

    def _clear_status_sidecar(self, sensor: str) -> None:
        try:
            path = self._status_sidecar_path(sensor)
            if path.exists():
                path.unlink()
        except Exception:
            pass
