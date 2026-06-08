from typing import Optional, Any, Tuple
from PySide6 import QtWidgets, QtCore, QtGui


def build_pod_pixmaps(size: QtCore.QSize) -> Tuple[QtGui.QPixmap, QtGui.QPixmap, QtGui.QPixmap]:
    """Return (ok, warn, unknown) pixmaps scaled to the desired size (AEM-style)."""
    width = max(48, size.width())
    height = max(48, size.height())

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


def init_pod_badge(self, parent_layout: QtWidgets.QBoxLayout, compact: bool = False) -> None:
    """Create PoD badge UI (icon + text), styled similar to AEM PoI indicator."""
    self.podStatusWidget = QtWidgets.QWidget()
    self.podStatusWidget.setAccessibleName("pod_widget_pod_status_widget")
    layout_cls = QtWidgets.QHBoxLayout if compact else QtWidgets.QVBoxLayout
    v = layout_cls(self.podStatusWidget)
    if compact:
        v.setContentsMargins(4, 0, 4, 0)
        v.setSpacing(6)
        v.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    else:
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(6)
        v.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignHCenter)

    size = QtCore.QSize(32, 32) if compact else QtCore.QSize(84, 84)
    self._pod_icons = build_pod_pixmaps(size)
    self.podStatusIcon = QtWidgets.QLabel()
    self.podStatusIcon.setAccessibleName("pod_label_pod_status_icon")
    self.podStatusIcon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    self.podStatusIcon.setFixedSize(size)
    if self._pod_icons and self._pod_icons[2] is not None:
        self.podStatusIcon.setPixmap(self._pod_icons[2])

    self.podStatusText = QtWidgets.QLabel("")
    self.podStatusText.setAccessibleName("pod_label_pod_status_text")
    self.podStatusText.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignCenter if not compact else QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    self.podStatusText.setWordWrap(not compact)
    self.podStatusText.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Preferred,
        QtWidgets.QSizePolicy.Policy.Maximum
    )

    if compact:
        v.addWidget(self.podStatusIcon, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(self.podStatusText, alignment=QtCore.Qt.AlignmentFlag.AlignVCenter)
    else:
        v.addWidget(self.podStatusIcon, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self.podStatusText, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
    # Always show badge; non-PoD devices use connectivity status
    self.podStatusWidget.setVisible(True)
    parent_layout.addWidget(self.podStatusWidget, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


def update_pod_badge(self, raw_value: Any, online_status: Optional[bool] = None, err_msg: Optional[str] = None) -> None:
    """Update PoD warning/check badge shown under the logo (measurement health)."""
    if not hasattr(self, "podStatusWidget"):
        self.podStatusWidget = None
    # Badge UI is optional; state is used for footer regardless
    if self.podStatusWidget:
        self.podStatusWidget.setVisible(True)

    def _normalize(val: Any) -> Optional[bool]:
        try:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val > 0
            if isinstance(val, str):
                s = val.strip().lower()
                if "mining" in s:
                    return True
                if "error" in s:
                    return False
                try:
                    return float(s) > 0
                except Exception:
                    return None
        except Exception:
            return None
        return None

    pod_source = raw_value
    if pod_source is None and hasattr(self, "statusLabel"):
        try:
            pod_source = self.statusLabel.text()
        except Exception:
            pod_source = None

    # If an explicit online_status is provided, trust it; otherwise normalize the raw value.
    if isinstance(online_status, bool):
        pod_ok = online_status
    elif self._pod_supported():
        pod_ok = _normalize(pod_source)
    else:
        pod_ok = _normalize(pod_source)

    icon_ok, icon_warn, icon_unknown = getattr(self, "_pod_icons", (None, None, None))
    is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
    was_online = self._last_pod_ok
    self._last_pod_ok = pod_ok
    self._last_pod_error = err_msg

    # When transitioning to online and MAC is still missing, re-discover
    # the active network interface now that connectivity is available.
    if pod_ok is True and not getattr(self, 'activeMacAddress', None):
        try:
            from miner_GUI.ui.helpers import network as network_helpers
            network_helpers.populate_network_interfaces(self)
            # Refresh rewards/MAC-match display with the newly discovered MAC
            if getattr(self, 'activeMacAddress', None):
                from miner_GUI.ui.helpers.rewards import update_rewards_hint
                update_rewards_hint(self)
        except Exception:
            pass

    if pod_ok is True:
        if self.podStatusWidget and icon_ok is not None:
            self.podStatusIcon.setPixmap(icon_ok)
            self.podStatusText.setText("Device online" if is_mobile else "Device online and mining.")
            self.podStatusText.setStyleSheet("color: #0fb94b; font-size: 11pt; font-weight: 600;")
    elif pod_ok is False:
        if self.podStatusWidget and icon_warn is not None:
            self.podStatusIcon.setPixmap(icon_warn)
            offline_msg = "Device offline"
            if err_msg:
                offline_msg += f" - {err_msg}"
            elif not is_mobile:
                offline_msg += " - Error."
            self.podStatusText.setText(offline_msg)
            self.podStatusText.setStyleSheet("color: #c75c1e; font-size: 11pt; font-weight: 600;")
    else:
        # For sensor-less miners (SVN/SDN/RDN), use weekly JSON gates
        from miner_GUI.utils.status_week import load_status_week_for_date
        from datetime import date
        week_doc = load_status_week_for_date(date.today())
        _mac = week_doc.get("mac_mismatch") if isinstance(week_doc, dict) else None
        _online = week_doc.get("online_status") if isinstance(week_doc, dict) else None
        if _mac is None or not _online:  # None or ""
            # Gates not yet set — show pending
            if self.podStatusWidget and icon_unknown is not None:
                self.podStatusIcon.setPixmap(icon_unknown)
                self.podStatusText.setText("Unknown" if is_mobile else "Device status unknown")
                self.podStatusText.setStyleSheet("color: #6f7a88; font-size: 11pt; font-weight: 600;")
        elif _online == "online":
            if self.podStatusWidget and icon_ok is not None:
                self.podStatusIcon.setPixmap(icon_ok)
                self.podStatusText.setText("Device online" if is_mobile else "Device online and mining.")
                self.podStatusText.setStyleSheet("color: #0fb94b; font-size: 11pt; font-weight: 600;")
        elif _online == "offline":
            if self.podStatusWidget and icon_warn is not None:
                self.podStatusIcon.setPixmap(icon_warn)
                self.podStatusText.setText("Device offline")
                self.podStatusText.setStyleSheet("color: #c75c1e; font-size: 11pt; font-weight: 600;")
        else:
            # online_status has a value but is not "online"/"offline" (e.g. "unknown")
            # Infer from multiplier as fallback
            mult = getattr(self, "_current_multiplier", None)
            if mult is not None and mult > 0:
                if self.podStatusWidget and icon_ok is not None:
                    self.podStatusIcon.setPixmap(icon_ok)
                    self.podStatusText.setText("Device online" if is_mobile else "Device online and mining.")
                    self.podStatusText.setStyleSheet("color: #0fb94b; font-size: 11pt; font-weight: 600;")
            elif self.podStatusWidget and icon_unknown is not None:
                self.podStatusIcon.setPixmap(icon_unknown)
                self.podStatusText.setText("Status unknown")
                self.podStatusText.setStyleSheet("color: #6f7a88; font-size: 11pt; font-weight: 600;")

    try:
        self._refresh_footer_status()
    except Exception:
        pass
