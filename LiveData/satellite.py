from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class SatellitePanel(QtWidgets.QWidget):
    """GNSS panel showing selected device and sats/fix if available.
    Exposes on_tick(data) and set_device_label(text).
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.deviceLbl = QtWidgets.QLabel("")
        self.statusLbl = QtWidgets.QLabel("waiting for data…")
        try:
            self.deviceLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.statusLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        except Exception:
            pass

        lay.addWidget(self.deviceLbl)
        lay.addWidget(self.statusLbl)

    def set_device_label(self, text: str):
        try:
            self.deviceLbl.setText(f"GNSS: {text}")
        except Exception:
            pass

    def on_tick(self, data: dict):
        try:
            # Expect data like {'sats': int, 'fix': str/int}
            sats = data.get('sats')
            fix = data.get('fix')
            parts = []
            if sats is not None:
                parts.append(f"sats={sats}")
            if fix is not None:
                parts.append(f"fix={fix}")
            self.statusLbl.setText(" | ".join(parts) if parts else "waiting for data…")
        except Exception:
            pass
