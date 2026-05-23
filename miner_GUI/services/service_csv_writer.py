"""Append-only CSV writer for service measurement logs."""

from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from miner_GUI.utils.data import data_dir_gui, log_step


class ServiceCsvWriter:
    """Simple CSV writer that appends measurement rows to daily files.

    Files are named `{sensor}_live_YYYYMMDD.csv` under ProgramData measurements.
    Thread-safe across multiple sensor loops.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self.log_dir = Path(log_dir) if log_dir else data_dir_gui() / "measurements"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}

    def path_for(self, sensor: str, ts: Optional[datetime] = None) -> Path:
        sensor_safe = (sensor or "sensor").strip().lower() or "sensor"
        dt = ts or datetime.utcnow()
        return self.log_dir / f"{sensor_safe}_live_{dt.strftime('%Y%m%d')}.csv"

    def append_row(self, sensor: str, row: Dict[str, Any], field_order: Optional[List[str]] = None) -> Optional[Path]:
        """Append a single measurement row to the sensor CSV.

        Args:
            sensor: Sensor name (e.g., "bm", "satellite")
            row: Measurement dict; should include a timestamp key
            field_order: Optional explicit field order for headers
        """
        if not row:
            return None

        try:
            ts_raw = row.get("timestamp")
            dt_for_path: Optional[datetime] = None
            if isinstance(ts_raw, str):
                try:
                    dt_for_path = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except Exception:
                    dt_for_path = None

            path = self.path_for(sensor, dt_for_path)
            fieldnames = list(field_order) if field_order else list(row.keys())
            if "timestamp" in row and "timestamp" not in fieldnames:
                fieldnames = ["timestamp"] + fieldnames
            # Deduplicate while preserving order
            seen = set()
            ordered_fields = []
            for name in fieldnames:
                if name in seen:
                    continue
                seen.add(name)
                ordered_fields.append(name)

            lock = self._locks.setdefault(sensor, threading.Lock())
            with lock:
                write_header = not path.exists()
                with open(path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=ordered_fields, extrasaction="ignore")
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)
            return path
        except Exception as exc:  # pragma: no cover - best effort logging only
            log_step("service_csv_append_failed", {"sensor": sensor, "error": str(exc)})
            return None
