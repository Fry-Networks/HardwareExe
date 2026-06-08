"""Reusable toggle switch widget rendered as a sliding checkbox."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter


class ToggleSwitch(QtWidgets.QCheckBox):
    """Simple toggle rendered as a pill with a circular knob.
    
    Emits stateChanged only when user interaction is confirmed (not blocked).
    Use setChecked() to update programmatically without triggering handlers.
    """

    def __init__(self, parent=None, width: int = 58, height: int = 28):
        super().__init__(parent)
        self._width = width
        self._height = height
        self._programmatic = False
        self._syncing = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setChecked(False)
        self.setAccessibleName("toggle_switch")
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

    def set_syncing(self, syncing: bool) -> None:
        """Switch to blue pill when syncing/in-progress, green when fully OK."""
        if self._syncing != syncing:
            self._syncing = syncing
            self.update()
    
    def setChecked(self, checked: bool) -> None:
        """Set the checked state programmatically without emitting stateChanged."""
        # Block all signals while we update the state
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            super().setChecked(checked)
            self.update()  # Force repaint
        finally:
            self.blockSignals(was_blocked)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Override mouse press to control when toggle actually changes."""
        # Don't call super() - we handle the toggle manually after confirmation
        pass
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release - trigger state change and emit signal."""
        if not self.isEnabled():
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if not self.rect().contains(event.pos()):
            return
        
        # Toggle and emit - handlers will revert if needed
        new_state = not self.isChecked()
        # Use base class setChecked to ensure Qt emits stateChanged exactly once
        super().setChecked(new_state)
        self.update()
        # Accept the event to prevent further propagation
        event.accept()

    def sizeHint(self):  # type: ignore[override]
        return QtCore.QSize(self._width, self._height)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        radius = self._height / 2
        offset = radius
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._width, self._height)

        if self.isEnabled():
            if self.isChecked():
                bg_color = QtGui.QColor("#2563EB" if self._syncing else "#22c55e")
            else:
                bg_color = QtGui.QColor("#555b6d")
        else:
            bg_color = QtGui.QColor("#2a3142")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, radius, radius)

        knob_radius = radius - 4
        if self.isChecked():
            center_x = self._width - offset
        else:
            center_x = offset

        if not self.isEnabled():
            knob_color = QtGui.QColor("#4a5162")
        else:
            knob_color = QtGui.QColor("#0b101a") if self.isChecked() else QtGui.QColor("#1f2430")
        painter.setBrush(knob_color)
        painter.drawEllipse(QtCore.QPointF(center_x, radius), knob_radius, knob_radius)
