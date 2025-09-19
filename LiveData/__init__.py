from __future__ import annotations

from typing import Optional

def load_live_panel(group: str, width: int = 800):
    """Return a QWidget implementing a live panel for the given miner group.
    Known groups: 'Bandwidth', 'AIEdge' -> bandwidth panel.
    Returns None if no panel is available.
    """
    try:
        grp = (group or "").strip()
        if grp in ("Bandwidth", "AIEdge"):
            from .bandwidth import BandwidthPanel
            return BandwidthPanel(width=width)
        if grp == "Decibel":
            from .decibel import DecibelPanel
            return DecibelPanel(width=width)
        if grp == "Satellite":
            from .satellite import SatellitePanel
            return SatellitePanel(width=width)
    except Exception:
        return None
    return None
