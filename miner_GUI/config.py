"""
Core configuration and constants for the Miner GUI application.
"""

import os
import sys
import re
from pathlib import Path
from typing import cast, Any

from config_profile import MINER_CODE, VERSION, DISPLAY_NAME

# Miner types that are mutually exclusive at runtime (shared hardware)
EXCLUSIVE_PAIRS = {
    "ISM": "OSM",
    "OSM": "ISM",
    "IDM": "ODM",
    "ODM": "IDM",
}

# Hardware capability flags
try:
    import sounddevice as sd
    HAVE_SD = True
except Exception:
    sd = cast(Any, None)
    HAVE_SD = False

try:
    import serial
    import serial.tools.list_ports
    HAVE_SERIAL = True
except Exception:
    serial = cast(Any, None)
    HAVE_SERIAL = False

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    HAVE_MPL = True
except Exception:
    FigureCanvas = cast(Any, None)
    Figure = cast(Any, None)
    HAVE_MPL = False


def app_dir() -> Path:
    """Get the application directory."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).resolve().parent.parent.parent  # Adjust for miner_GUI/core structure


def resource_path(name: str) -> Path:
    """Get path to a bundled resource."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and isinstance(bundle_root, str):
        return Path(bundle_root) / name
    return app_dir() / name


def image_path(name: str) -> Path:
    """Return path to an image under the bundled 'images' directory, with fallback to root.
    This supports a transition where images may still be at repo root during migration.
    """
    # Prefer images/<name>
    bundle_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    if isinstance(bundle_root, str):
        p = Path(bundle_root) / 'images' / name
    else:
        p = app_dir() / 'images' / name
    if p.exists():
        return p
    # Fallback to legacy root location
    return resource_path(name)


def miner_icon_path() -> Path:
    """Return the per-miner icon path under images/ based on MINER_CODE."""
    try:
        code = (MINER_CODE or "").upper()
    except Exception:
        code = ""
    base = None
    if code == "BM":
        base = "BM.png"
    elif code == "AEM":
        base = "AEM.png"
    elif code == "IRM":
        base = "RAD.png"
    elif code in ("IDM", "ODM"):
        base = "DB.png"
    elif code in ("ISM", "OSM"):
        base = "GNSS.png"
    elif code in ("RDN", "SVN", "SDN"):
        base = "NODE.png"
    else:
        base = "frynetworks_logo.png"
    return image_path(base)


def embedded_path(name: str) -> Path:
    """Get path to an embedded resource."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and isinstance(bundle_root, str):
        return Path(bundle_root) / 'embedded' / name
    return app_dir() / 'embedded' / name


# Key validation pattern
def make_key_pattern(prefix: str) -> re.Pattern:
    """Create a regex pattern for validating miner keys."""
    return re.compile(rf"^{re.escape(prefix)}-[A-Z0-9]{{32}}$")

KEY_PATTERN = make_key_pattern(MINER_CODE)