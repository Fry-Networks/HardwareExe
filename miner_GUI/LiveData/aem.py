from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from miner_GUI.config import image_path


class AemPanel(QtWidgets.QWidget):
    """Live panel for AEM miners showing MAC, online, and Olostep Browser status.

    Worker emits {'mac_mismatch': bool, 'online': gate, 'data': gate} updates.
    Status priority: MAC mismatch > unknown > all OK > internet down > Olostep down > both down.
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        self._size_hint = width
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setAccessibleName("livedata_aem_label_icon")
        self.icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.status_label = QtWidgets.QLabel("Loading status...")
        self.status_label.setAccessibleName("livedata_aem_label_status")
        try:
            self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.status_label.setWordWrap(True)
            target_w = max(160, min(int(width), 360))
            if width <= 520:
                target_w = 220
            elif width <= 700:
                target_w = 260
            self.status_label.setFixedWidth(int(target_w))
            self.status_label.setMaximumWidth(int(target_w))
            self.status_label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Minimum
            )
        except Exception:
            pass

        font = self.status_label.font()
        try:
            font.setPointSize(max(11, font.pointSize()))
            font.setBold(True)
            self.status_label.setFont(font)
        except Exception:
            pass

        icon_size = self._status_icon_size()
        try:
            if icon_size.isValid():
                self.icon_label.setFixedSize(icon_size)
        except Exception:
            pass
        self._ok_pixmap, self._warn_pixmap, self._unknown_pixmap = self._build_status_pixmaps(icon_size)
        self.icon_label.setPixmap(self._unknown_pixmap)

        lay.addStretch(1)
        lay.addWidget(self.icon_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.status_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)

    def on_tick(self, tick_data: dict):
        """Update display from worker tick data.

        Expected tick_data keys:
        - mac_mismatch: bool or None (from weekly JSON)
        - online: gate value (1/0/True/False or None)
        - data: gate value (1/0/True/False or None) - Olostep Browser status
        """
        try:
            mac_mismatch = tick_data.get('mac_mismatch')
            online = tick_data.get('online')
            data = tick_data.get('data')
            narrow = getattr(self, "_size_hint", 800) <= 700

            # Priority 1: MAC mismatch
            if self._is_truthy(mac_mismatch):
                txt = (
                    "MAC address mismatch\nPlease update your registration in the FryNetworks dashboard."
                    if narrow
                    else "MAC address mismatch - Please update your registration in the FryNetworks dashboard."
                )
                icon = self._warn_pixmap
            # Priority 2: A gate is still null — show pending
            elif mac_mismatch is None or online is None:
                txt = "Device status unknown"
                icon = self._unknown_pixmap
            # Priority 3: Both gates OK - all good
            elif self._is_truthy(online) and self._is_truthy(data):
                txt = (
                    "Olostep Browser is running\nAEM miner is online and earning rewards."
                    if narrow
                    else "Olostep Browser is running - AEM miner is online and earning rewards."
                )
                icon = self._ok_pixmap
            # Priority 4: Internet down, Olostep running
            elif not self._is_truthy(online) and self._is_truthy(data):
                txt = "No internet connection"
                icon = self._warn_pixmap
            # Priority 5: Internet up, Olostep not running
            elif self._is_truthy(online) and not self._is_truthy(data):
                txt = "Olostep Browser not detected or not enabled.\nInstall/enable Olostep Browser to keep earning rewards."
                icon = self._warn_pixmap
            # Priority 6: Both down
            else:
                txt = (
                    "No internet connection\nOlostep Browser not running"
                    if narrow
                    else "No internet connection and Olostep Browser not running"
                )
                icon = self._warn_pixmap

            self.status_label.setText(txt)
            if icon is not None:
                self.icon_label.setPixmap(icon)
        except Exception:
            pass

    @staticmethod
    def _is_truthy(value) -> bool:
        """Return True for typical 'true' values from services."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized in {"true", "1", "yes", "y", "ok", "pass"}
        return False

    def _status_icon_size(self) -> QtCore.QSize:
        """Match Olostep logo size so the icon feels native."""
        default = QtCore.QSize(180, 180)
        # Scale down for small layouts
        hint = max(0, int(self._size_hint)) if hasattr(self, "_size_hint") else 800
        if hint <= 520:
            default = QtCore.QSize(140, 140)
        elif hint <= 700:
            default = QtCore.QSize(160, 160)
        try:
            pix = QtGui.QPixmap(str(image_path("olostep_logo.png")))
            if pix and not pix.isNull():
                # Scale pixmap directly to a target size
                target = QtCore.QSize(140, 140) if hint <= 520 else QtCore.QSize(160, 160) if hint <= 700 else None
                if target is not None:
                    scaled = pix.scaled(
                        target,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                    return scaled.size()
                return pix.size()
        except Exception:
            pass
        return default

    def _build_status_pixmaps(self, size: QtCore.QSize) -> tuple[QtGui.QPixmap, QtGui.QPixmap, QtGui.QPixmap]:
        """Return (ok, warn, unknown) pixmaps scaled to the desired size."""
        width = max(32, size.width())
        height = max(32, size.height())

        def make_base() -> QtGui.QPixmap:
            pix = QtGui.QPixmap(width, height)
            pix.fill(QtCore.Qt.GlobalColor.transparent)
            return pix

        ok_pix = make_base()
        painter = QtGui.QPainter(ok_pix)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#0fb94b"))
        pen.setWidthF(max(width, height) * 0.09)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(
            QtCore.QPointF(width * 0.18, height * 0.55),
            QtCore.QPointF(width * 0.4, height * 0.78),
        )
        painter.drawLine(
            QtCore.QPointF(width * 0.4, height * 0.78),
            QtCore.QPointF(width * 0.84, height * 0.28),
        )
        painter.end()

        warn_pix = make_base()
        painter = QtGui.QPainter(warn_pix)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        triangle = QtGui.QPainterPath()
        triangle.moveTo(width * 0.5, height * 0.1)
        triangle.lineTo(width * 0.9, height * 0.9)
        triangle.lineTo(width * 0.1, height * 0.9)
        triangle.closeSubpath()
        painter.fillPath(triangle, QtGui.QColor("#ffdf7d"))
        pen = QtGui.QPen(QtGui.QColor("#cc9800"))
        pen.setWidthF(max(width, height) * 0.04)
        painter.setPen(pen)
        painter.drawPath(triangle)
        painter.setPen(QtGui.QPen(QtGui.QColor("#874b00"), max(width, height) * 0.05))
        painter.drawLine(
            QtCore.QPointF(width * 0.5, height * 0.32),
            QtCore.QPointF(width * 0.5, height * 0.63),
        )
        painter.setBrush(QtGui.QColor("#874b00"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        dot_radius = max(width, height) * 0.035
        painter.drawEllipse(QtCore.QPointF(width * 0.5, height * 0.78), dot_radius, dot_radius)
        painter.end()

        unknown_pix = make_base()
        painter = QtGui.QPainter(unknown_pix)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#6f7a88"))
        pen.setWidthF(max(width, height) * 0.05)
        painter.setPen(pen)
        painter.drawEllipse(QtCore.QPointF(width / 2, height / 2), width * 0.35, height * 0.35)
        painter.setPen(QtGui.QPen(QtGui.QColor("#6f7a88"), max(width, height) * 0.07))
        painter.drawArc(
            QtCore.QRectF(width * 0.35, height * 0.25, width * 0.3, height * 0.45),
            30 * 16,
            120 * 16,
        )
        painter.setPen(QtGui.QPen(QtGui.QColor("#6f7a88"), max(width, height) * 0.06))
        painter.drawPoint(int(width / 2), int(height * 0.78))
        painter.end()

        return ok_pix, warn_pix, unknown_pix
