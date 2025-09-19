from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class BandwidthPanel(QtWidgets.QWidget):
    """Simple UP/DOWN bandwidth progress bars with autoscaling.
    Exposes on_tick(data: dict) for updates from the worker.
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        self._max = 100
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.dl = QtWidgets.QProgressBar()
        self.ul = QtWidgets.QProgressBar()
        try:
            self.dl.setFormat('Download: %v Mbps'); self.ul.setFormat('Upload: %v Mbps')
        except Exception:
            pass
        try:
            self.dl.setFixedWidth(int(width)); self.ul.setFixedWidth(int(width))
            self.dl.setFixedHeight(28); self.ul.setFixedHeight(28)
        except Exception:
            pass
        try:
            self.dl.setMaximum(self._max); self.ul.setMaximum(self._max)
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
        except Exception:
            pass
