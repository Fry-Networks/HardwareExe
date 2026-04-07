"""Helpers for reading weekly status JSON files (vNext).

The backend writes one file per rewards week:
  status-week-YYYY-MM-DD.json  (YYYY-MM-DD is the week start date, UTC)

The GUI reads and renders only what the backend computed. Missing data should
be treated as unknown/empty (render as grayed/no value).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional, Tuple

from miner_GUI.utils.data import data_dir_gui


def status_dir() -> Path:
    return data_dir_gui() / "status"


def rewards_week_start_date(day_utc: dt.date) -> dt.date:
    """Return the start date (UTC) for the rewards week containing `day_utc`.

    Week boundary is Friday 00:00 UTC (start) through the next Friday 00:00 UTC (end, exclusive).
    """
    # Python: Monday=0 ... Sunday=6; Friday=4
    friday = 4
    delta_days = (day_utc.weekday() - friday) % 7
    return day_utc - dt.timedelta(days=delta_days)


def status_week_path_for_start(week_start_utc: dt.date, base_dir: Optional[Path] = None) -> Path:
    base = base_dir or status_dir()
    # Use compact YYYYMMDD format to match backend file naming
    date_str = week_start_utc.strftime("%Y%m%d")
    return base / f"status-week-{date_str}.json"


def status_week_path_for_date(day_utc: dt.date, base_dir: Optional[Path] = None) -> Path:
    return status_week_path_for_start(rewards_week_start_date(day_utc), base_dir=base_dir)


def _parse_iso_dt(value: Any) -> Optional[dt.datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    try:
        # Support common "Z" suffix.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(s)
        # If timezone-naive, treat as UTC.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def week_bounds_from_doc(doc: Any) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    """Return (week_start_date, week_end_date_exclusive) from a parsed weekly doc."""
    if not isinstance(doc, dict):
        return None, None
    start_dt = _parse_iso_dt(doc.get("week_start"))
    end_dt = _parse_iso_dt(doc.get("week_end"))
    start_date = start_dt.date() if start_dt else None
    end_date = end_dt.date() if end_dt else None
    return start_date, end_date


def load_status_week_from_path(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
        return doc if isinstance(doc, dict) else None
    except Exception:
        return None


def load_status_week_for_date(day_utc: dt.date, *, allow_scan: bool = True) -> Optional[dict]:
    """Load the weekly status file that contains `day_utc` (UTC date).

    Primary lookup uses the deterministic filename for the computed week start.
    If not found and `allow_scan` is True, scans `status-week-*.json` and picks
    the file whose (week_start <= day < week_end) matches.
    """
    base = status_dir()
    primary = status_week_path_for_date(day_utc, base_dir=base)
    doc = load_status_week_from_path(primary)
    if doc is not None:
        start_date, end_date = week_bounds_from_doc(doc)
        if start_date and end_date:
            if start_date <= day_utc < end_date:
                return doc
        else:
            return doc

    if not allow_scan:
        return None

    try:
        candidates = sorted(base.glob("status-week-*.json"))
    except Exception:
        return None

    for path in candidates:
        doc = load_status_week_from_path(path)
        if not isinstance(doc, dict):
            continue
        start_date, end_date = week_bounds_from_doc(doc)
        if start_date is None or end_date is None:
            continue
        if start_date <= day_utc < end_date:
            return doc
    return None


def day_doc_from_week(week_doc: Any, day_utc: dt.date) -> Optional[dict]:
    if not isinstance(week_doc, dict):
        return None
    days = week_doc.get("days")
    if not isinstance(days, dict):
        return None
    doc = days.get(day_utc.isoformat())
    return doc if isinstance(doc, dict) else None


def hour_doc_from_day(day_doc: Any, hour: int) -> Optional[dict]:
    if not isinstance(day_doc, dict):
        return None
    hours = day_doc.get("hours")
    if not isinstance(hours, dict):
        return None
    doc = hours.get(str(int(hour)))
    return doc if isinstance(doc, dict) else None


def counted_slots_from_day(day_doc: Any) -> int:
    if not isinstance(day_doc, dict):
        return 0
    try:
        return max(0, int(day_doc.get("counted_slots", 0)))
    except Exception:
        return 0
