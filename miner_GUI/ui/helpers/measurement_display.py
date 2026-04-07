"""UI helpers for displaying measurement data from the autonomous service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from PySide6 import QtWidgets


def format_hardware_stats(hw_stats: Optional[Dict[str, Any]]) -> str:
    """Format hardware stats for display.
    
    Args:
        hw_stats: Hardware stats dict from measurement data
        
    Returns:
        Formatted string for display
    """
    if not hw_stats or not isinstance(hw_stats, dict):
        return "Hardware stats unavailable"
    
    parts = []
    
    cpu_temp = hw_stats.get('cpu_temp')
    if cpu_temp is not None:
        parts.append(f"CPU: {cpu_temp:.1f}°C")
    
    ram_usage = hw_stats.get('ram_usage_percent')
    if ram_usage is not None:
        parts.append(f"RAM: {ram_usage:.1f}%")
    
    disk_usage = hw_stats.get('disk_usage_percent')
    if disk_usage is not None:
        parts.append(f"Disk: {disk_usage:.1f}%")
    
    if not parts:
        return "Hardware stats unavailable"
    
    return " | ".join(parts)


def format_poc_status(poc_data: Optional[Dict[str, Any]]) -> str:
    """Format PoC application status for display.
    
    Args:
        poc_data: PoC application data from measurements
        
    Returns:
        Formatted string with status and earnings
    """
    if not poc_data or not isinstance(poc_data, dict):
        return "Status unavailable"
    
    status = poc_data.get('status', 'unknown')
    earnings = poc_data.get('earnings', 0)
    
    status_icon = {
        'running': '▶️',
        'stopped': '⏹️',
        'error': '⚠️',
    }.get(status, '❓')
    
    return f"{status_icon} {status.capitalize()} (${earnings:.4f})"


def get_ram_usage_color(ram_percent: Optional[float]) -> str:
    """Get color for RAM usage display based on percentage.
    
    Args:
        ram_percent: RAM usage percentage (0-100)
        
    Returns:
        Color string (green/orange/red)
    """
    if ram_percent is None:
        return "gray"
    
    if ram_percent > 80:
        return "#d94d4d"  # red
    elif ram_percent > 60:
        return "#f5a623"  # orange
    else:
        return "#0fb94b"  # green


def format_timestamp(timestamp_str: Optional[str]) -> str:
    """Format ISO 8601 timestamp for display.
    
    Args:
        timestamp_str: ISO 8601 timestamp string
        
    Returns:
        Formatted datetime string or "Unknown"
    """
    if not timestamp_str:
        return "Unknown"
    
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp_str)


def handle_measurement_error(error: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
    """Handle measurement read errors gracefully.
    
    Args:
        error: Error message string from measurement source
        parent: Parent widget for error dialog
    """
    # Only show critical errors to user
    error_lower = error.lower()
    
    if 'file not found' in error_lower or 'no such file' in error_lower:
        # Service hasn't written yet - normal during startup
        # Don't show dialog, just log silently
        return
    elif 'permission denied' in error_lower:
        # Likely ProgramData permission issue
        if parent:
            QtWidgets.QMessageBox.warning(
                parent,
                "Permission Error",
                "Cannot read measurements. Check ProgramData permissions."
            )
    else:
        # Generic error
        if parent:
            QtWidgets.QMessageBox.warning(
                parent,
                "Data Error",
                f"Failed to read measurements: {error}"
            )


def update_widget_with_measurements(
    widget: QtWidgets.QWidget,
    measurements: Optional[Dict[str, Any]]
) -> None:
    """Update a widget with fresh measurement data if it has an update method.
    
    Args:
        widget: Widget to update (must have update_with_measurements method)
        measurements: Measurement data dict
    """
    if not measurements or not isinstance(measurements, dict):
        return
    
    # Check if widget has the update method
    if hasattr(widget, 'update_with_measurements') and callable(widget.update_with_measurements):  # type: ignore[attr-defined]
        try:
            widget.update_with_measurements(measurements)  # type: ignore[attr-defined]
        except Exception:
            # Silently ignore widget update failures
            pass
