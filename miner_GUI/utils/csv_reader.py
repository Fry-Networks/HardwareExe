"""Efficient CSV reader for polling service-written measurement files.

This module provides utilities for GUI to read service-written CSV files:
1. Read last line efficiently (for live display polling)
2. Read full file (for Data History tab)

The service writes append-only CSV files under `measurements/`:
- measurements/bm_live_20260115.csv
- measurements/satellite_live_20260115.csv
- measurements/radiation_live_20260115.csv
- measurements/decibel_live_20260115.csv
- etc.

GUI polls the last line every 2-10 seconds for LiveData panel updates.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from miner_GUI.utils.data import data_dir_gui, log_step


def get_today_csv_path(sensor_type: str) -> Path:
    """Get path to today's CSV file for a sensor type.
    
    Args:
        sensor_type: "BM", "Satellite", "Radiation", "Decibel", "AEM", etc.
        
    Returns:
        Path to today's CSV file (may not exist if service hasn't written yet)
    """
    # Development mode: write/read from measurements directory only
    measurements_dir = data_dir_gui() / "measurements"
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Map sensor types to service file naming convention
    sensor_mapping = {
        "bm": "bandwidth",
        "satellite": "satellite",
        "radiation": "radiation",
        "decibel": "decibel",
        "aem": "aem",
        "idm": "decibel",
        "ism": "satellite",
        "irm": "radiation",
    }
    
    sensor_lower = sensor_type.lower()
    filename = sensor_mapping.get(sensor_lower, sensor_lower)
    # Default to live CSV for today's live polling
    measurements_dir.mkdir(parents=True, exist_ok=True)
    return measurements_dir / f"{filename}_live_{date_str}.csv"


def get_csv_path_for_date(sensor_type: str, day: Optional[datetime] = None, suffix: str = "real") -> Path:
    """Get path to a CSV file for a given sensor type and date.

    Args:
        sensor_type: sensor key (e.g., "BM", "bm", "bandwidth")
        day: datetime.date or datetime to use; defaults to today
        suffix: one of 'live' or 'real' to select filename variant

    Returns:
        Path to the CSV file
    """
    # Accept either date or datetime
    if day is None:
        day_dt = datetime.now()
    elif isinstance(day, datetime):
        day_dt = day
    else:
        # Assume date-like
        day_dt = datetime.combine(day, datetime.min.time())

    date_str = day_dt.strftime('%Y%m%d')
    measurements_dir = data_dir_gui() / "measurements"

    sensor_mapping = {
        "bm": "bandwidth",
        "satellite": "satellite",
        "radiation": "radiation",
        "decibel": "decibel",
        "aem": "aem",
        "idm": "decibel",
        "ism": "satellite",
        "irm": "radiation",
    }
    sensor_lower = sensor_type.lower()
    filename = sensor_mapping.get(sensor_lower, sensor_lower)

    return measurements_dir / f"{filename}_{suffix}_{date_str}.csv"


def read_last_line(csv_file: Path) -> Optional[Dict[str, Any]]:
    """Efficiently read the last line of a CSV file without loading entire file.
    
    This is optimized for polling: seeks to end, reads last few KB, parses last line.
    
    Args:
        csv_file: Path to CSV file
        
    Returns:
        Dictionary with column names as keys, or None if file doesn't exist/is empty
        
    Example:
        >>> read_last_line(Path("logs/bm_20260115.csv"))
        {'timestamp': '2026-01-15T12:30:45', 'dl': '125.42', 'ul': '23.15'}
    """
    if not csv_file.exists():
        return None
    
    try:
        with open(csv_file, 'r', encoding='utf-8-sig', newline='') as f:
            # Read header first (needed for DictReader mapping)
            header = f.readline()
            if not header:
                return None

            # Tail-seek: read last ~4 KB to avoid O(n) full-file read
            tail_size = 4096
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            seek_pos = max(0, file_size - tail_size)
            f.seek(seek_pos)
            tail = f.read()

            # Split tail into lines; drop first because it may be partial
            tail_lines = tail.splitlines()
            if seek_pos > 0 and tail_lines:
                tail_lines = tail_lines[1:]

            # Find last non-empty data line
            last_data_line = None
            for line in reversed(tail_lines):
                stripped = line.strip()
                if stripped:
                    last_data_line = stripped
                    break

            if last_data_line is None:
                return None

            # Parse header + last line as a single two-row CSV
            two_row_text = header.strip() + '\n' + last_data_line + '\n'
            reader = csv.DictReader(two_row_text.splitlines())
            last_row = next(reader, None)

            if last_row:
                last_row = {k.lstrip('\ufeff'): v for k, v in last_row.items()}
                try:
                    if 'timestamp' in last_row and isinstance(last_row['timestamp'], str):
                        ts_raw = last_row['timestamp']
                        parsed = datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        last_row['timestamp'] = parsed
                except Exception:
                    pass
            return last_row

    except Exception as exc:
        log_step("csv_read_last_line_failed", {
            "file": str(csv_file),
            "error": str(exc)
        })
        return None


def read_last_line_for_sensor(sensor_type: str) -> Optional[Dict[str, Any]]:
    """Convenience function: read last line from today's CSV for a sensor.
    
    Args:
        sensor_type: "BM", "Satellite", "Radiation", "Decibel", etc.
        
    Returns:
        Dictionary with latest measurement values, or None if unavailable
        
    Example:
        >>> read_last_line_for_sensor("BM")
        {'timestamp': '2026-01-15T12:30:45', 'dl': '125.42', 'ul': '23.15'}
    """
    csv_path = get_today_csv_path(sensor_type)
    return read_last_line(csv_path)


def read_full_csv(csv_file: Union[str, Path]) -> List[Dict[str, Any]]:
    """Read entire CSV file and return all rows as list of dictionaries.
    
    Used by Data History tab to load all measurements for charting.
    
    Args:
        csv_file: Path to CSV file (str or Path object)
        
    Returns:
        List of dictionaries (one per row), empty list if file doesn't exist
        
    Example:
        >>> read_full_csv(Path("logs/satellite_20260115.csv"))
        [
            {'timestamp': '2026-01-15T12:00:00', 'sats': '8', 'hdop': '1.2'},
            {'timestamp': '2026-01-15T12:00:10', 'sats': '9', 'hdop': '1.1'},
            ...
        ]
    """
    if not Path(csv_file).exists():
        return []
    
    try:
        data = []
        with open(csv_file, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Strip BOM from any field names if present
                row = {k.lstrip('\ufeff'): v for k, v in row.items()}
                
                # Parse timestamp if present and normalize to timezone-aware UTC datetimes
                if 'timestamp' in row:
                    try:
                        ts_val = row['timestamp']
                        if isinstance(ts_val, str):
                            parsed = datetime.fromisoformat(ts_val.replace('Z', '+00:00'))
                            if parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            row['timestamp'] = parsed
                    except (ValueError, TypeError, Exception):
                        # Keep as original value if parsing fails
                        pass
                data.append(row)
        return data
        
    except Exception as exc:
        log_step("csv_read_full_failed", {
            "file": str(csv_file),
            "error": str(exc)
        })
        return []


def parse_float(value: Any, default: float = 0.0) -> float:
    """Safely parse a value to float, return default if parsing fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    """Safely parse a value to int, return default if parsing fails."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
