from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class DecibelPanel(QtWidgets.QWidget):
    """Decibel live panel with auto-scaled bar and red intensity by level.
    Exposes on_tick(data) and set_device_label(text).
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        self._min_db = -90.0
        self._max_db = 0.0
        self._device = ""

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # One-line info to match previous look
        self.infoLbl = QtWidgets.QLabel("")
        try:
            self.infoLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        except Exception:
            pass

        # Visible bar showing level; width is configurable
        self.bar = QtWidgets.QProgressBar()
        try:
            self.bar.setFixedWidth(int(width))
            self.bar.setFixedHeight(22)
            self.bar.setRange(0, 100)
            self.bar.setTextVisible(False)
            # Initial darker red
            self.bar.setStyleSheet("QProgressBar::chunk { background-color: #7f1d1d; border-radius: 12px; }")
        except Exception:
            pass

        lay.addWidget(self.infoLbl)
        lay.addWidget(self.bar, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)

    def set_device_label(self, text: str):
        try:
            self._device = text or ""
            if self.infoLbl.text().strip() == "":
                self.infoLbl.setText(f"Device: {self._device}")
        except Exception:
            pass

    def _color_for_pct(self, pct: int) -> str:
        """Return a red hex color from dark to bright based on 0..100."""
        try:
            # Interpolate between dark red (127,29,29) and bright red (239,68,68)
            t = max(0, min(100, pct)) / 100.0
            r0, g0, b0 = 127, 29, 29
            r1, g1, b1 = 239, 68, 68
            r = int(r0 + (r1 - r0) * t)
            g = int(g0 + (g1 - g0) * t)
            b = int(b0 + (b1 - b0) * t)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return "#7f1d1d"

    def on_tick(self, data: dict):
        try:
            if 'err' in data and data.get('dbfs') is None:
                self.infoLbl.setText(f"Device: {self._device}  •  error: {data.get('err')}")
                self.bar.setValue(0)
                self.bar.setStyleSheet("QProgressBar::chunk { background-color: #7f1d1d; border-radius: 12px; }")
                return
            val = data.get('dbfs')
            if val is None:
                return
            try:
                v = float(val)
            except Exception:
                return
            # Update text to mirror original behavior
            self.infoLbl.setText(f"Device: {self._device}  •  {v:.1f} dBFS")
            # Map -90..0 dBFS → 0..100 %
            pct = int(max(0.0, min(100.0, 100.0 * (v - self._min_db) / (self._max_db - self._min_db))))
            self.bar.setValue(pct)
            self.bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {self._color_for_pct(pct)}; border-radius: 12px; }}")
        except Exception:
            pass
