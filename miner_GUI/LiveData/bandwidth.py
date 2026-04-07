from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class BandwidthPanel(QtWidgets.QWidget):
    """Simple UP/DOWN bandwidth progress bars with autoscaling.
    Exposes on_tick(data: dict) for updates from the worker.
    """
    def __init__(self, width: int = 800, parent=None, screen_size: str = "desktop"):
        super().__init__(parent)
        self._max = 100
        self._screen_size = screen_size or "desktop"
        width = self._compute_width(width)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.dl = QtWidgets.QProgressBar()
        self.ul = QtWidgets.QProgressBar()
        try:
            if self._screen_size == "mobile":
                fmt_dl, fmt_ul = "Download: %v Mbps", "Upload: %v Mbps"
                bar_h = 18
            elif self._screen_size == "tablet":
                fmt_dl, fmt_ul = "Download: %v Mbps", "Upload: %v Mbps"
                bar_h = 22
            else:
                fmt_dl, fmt_ul = "Download: %v Mbps", "Upload: %v Mbps"
                bar_h = 28
            self.dl.setFormat(fmt_dl)
            self.ul.setFormat(fmt_ul)
        except Exception:
            bar_h = 28
        try:
            self.dl.setFixedWidth(int(width)); self.ul.setFixedWidth(int(width))
            self.dl.setFixedHeight(int(bar_h)); self.ul.setFixedHeight(int(bar_h))
        except Exception:
            pass
        try:
            self.dl.setMaximum(self._max); self.ul.setMaximum(self._max)
        except Exception:
            pass
        try:
            red_dark = "#7f1d1d"
            self.dl.setStyleSheet(f"QProgressBar::chunk {{ background-color: {red_dark}; border-radius: 10px; }}")
            self.ul.setStyleSheet(f"QProgressBar::chunk {{ background-color: {red_dark}; border-radius: 10px; }}")
        except Exception:
            pass
        # Vertically center the two bars by adding stretch above and below
        try:
            lay.addStretch(1)
        except Exception:
            pass
        lay.addWidget(self.dl, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.ul, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        try:
            lay.addStretch(1)
        except Exception:
            pass

    def _compute_width(self, base: int) -> int:
        """Scale the requested width based on screen size preference."""
        size = (self._screen_size or "desktop").lower()
        if size == "mobile":
            return int(base * 0.55)
        if size == "tablet":
            return int(base * 0.75)
        return base

    def _color_for_pct(self, pct: int) -> str:
        """Return a red hex color from dark to bright based on 0..100 (matches Decibel)."""
        try:
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
            dl = float(data.get('dl') or 0.0)
            ul = float(data.get('ul') or 0.0)
            mx = max(dl, ul)
            if mx > self._max * 0.95:
                import math
                self._max = int(max(20, math.ceil(mx * 1.5)))
                self.dl.setMaximum(self._max); self.ul.setMaximum(self._max)
            self.dl.setValue(int(dl)); self.ul.setValue(int(ul))
            color_dl = self._color_for_pct(int(min(100, (dl / self._max) * 100))) if self._max else "#7f1d1d"
            color_ul = self._color_for_pct(int(min(100, (ul / self._max) * 100))) if self._max else "#7f1d1d"
            self.dl.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color_dl}; border-radius: 10px; }}")
            self.ul.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color_ul}; border-radius: 10px; }}")
        except Exception:
            pass
