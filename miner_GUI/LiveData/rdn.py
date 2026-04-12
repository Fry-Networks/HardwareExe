"""LiveData panel for RDN (Rewards Decentralization Node) miners.

Displays Presearch and Diiisco node status with toggle controls in tabbed layout.
"""

from __future__ import annotations

from typing import Optional

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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setChecked(False)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
    
    def setChecked(self, checked: bool) -> None:
        """Set the checked state programmatically without emitting stateChanged."""
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            super().setChecked(checked)
            self.update()
        finally:
            self.blockSignals(was_blocked)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Override mouse press to control when toggle actually changes."""
        pass
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release - trigger state change and emit signal."""
        if not self.isEnabled():
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if not self.rect().contains(event.pos()):
            return
        
        new_state = not self.isChecked()
        super().setChecked(new_state)
        self.update()
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
            bg_color = QtGui.QColor("#22c55e" if self.isChecked() else "#555b6d")
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


PRESEARCH_DOC_URL = "https://docs.presearch.io/nodes/setup"
DIIISCO_DOC_URL = "https://github.com/FrysCrypto/diiisco-node"


class ServiceNodeTab(QtWidgets.QGroupBox):
    """Individual tab panel for a service node (Presearch or Diiisco)."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)

    def __init__(self, _title: str = "", _doc_url: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("", parent)
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False    # Track if waiting for miner configuration
        self._is_unavailable = False  # Track if tool is permanently unavailable (e.g. Docker missing)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 120)

        # Toggle switch (hidden — all integrations are forced ON)
        self._toggle = ToggleSwitch(width=58, height=28)
        self._toggle.stateChanged.connect(self._on_toggle_state)

        # Large status display area
        self._status_label = QtWidgets.QLabel("Checking status...")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self._status_label.setMinimumHeight(60)
        layout.addWidget(self._status_label, 1, 0, 1, 2)

    def _can_enable_toggle(self) -> bool:
        return not self._mac_mismatch and not self._is_pending and not self._is_unavailable

    def update_status(self, status_text: str) -> None:
        """Update the large status display area."""
        if not self._mac_mismatch and not self._is_pending and not self._is_unavailable:
            self._status_label.setText(status_text)

    def set_toggle_state(self, enabled: bool) -> None:
        """Set toggle state without emitting signal."""
        self._suspend_toggle = True
        try:
            self._toggle.setChecked(enabled)
            if self._can_enable_toggle():
                self._toggle.setEnabled(True)
        finally:
            self._suspend_toggle = False

    def set_busy(self, busy: bool) -> None:
        """Set busy state."""
        should_enable = not busy and self._can_enable_toggle()
        self._toggle.setEnabled(should_enable)

    def show_status_message(self, message: str) -> None:
        """Show a simple status message."""
        if not self._mac_mismatch and not self._is_pending and not self._is_unavailable:
            self._status_label.setText(message)

    def set_unavailable(self, message: str) -> None:
        """Mark panel as permanently unavailable (e.g. Docker not installed).

        Clears pending so the message is shown, disables toggle, and prevents
        any subsequent set_pending_state(False) from re-enabling the toggle.
        """
        self._is_unavailable = True
        self._is_pending = False
        self._status_label.setText(message)
        self._toggle.setChecked(False)
        self._toggle.setEnabled(False)

    def set_mac_mismatch_state(self, is_mismatched: bool, warning_message: str = "") -> None:
        """Disable toggle and show warning when MAC is mismatched."""
        self._mac_mismatch = is_mismatched
        if is_mismatched:
            self._toggle.setEnabled(False)
            if warning_message:
                self._status_label.setText(warning_message)
                self._status_label.setStyleSheet("color: #DC2626; font-weight: 600;")
        else:
            if self._can_enable_toggle():
                self._toggle.setEnabled(True)
            self._status_label.setStyleSheet("")

    def set_pending_state(self, is_pending: bool) -> None:
        """Set pending state when waiting for miner configuration.

        When pending=True, disables the toggle and prevents status updates
        from overwriting the pending message.
        """
        self._is_pending = is_pending
        if is_pending:
            self._toggle.setEnabled(False)
        else:
            # Clear pending — only re-enable if not unavailable/mismatched
            if self._can_enable_toggle():
                self._toggle.setEnabled(True)

    def _on_toggle_state(self, state: int) -> None:
        if self._suspend_toggle:
            return
        self.toggle_changed.emit(bool(state))


class RdnPanel(QtWidgets.QWidget):
    """LiveData panel for RDN miners with tabbed Presearch and Diiisco panels."""

    # Signals for external handlers
    presearch_refresh_clicked = QtCore.Signal()
    presearch_toggle_changed = QtCore.Signal(bool)
    diiisco_refresh_clicked = QtCore.Signal()
    diiisco_toggle_changed = QtCore.Signal(bool)

    def __init__(
        self,
        width: int = 800,
        parent: Optional[QtWidgets.QWidget] = None,
        screen_size: str = "desktop",
    ) -> None:
        super().__init__(parent)
        self._screen_size = screen_size or "desktop"
        self._width = self._compute_width(width)
        self._build_ui()

    def _compute_width(self, base: int) -> int:
        """Scale width based on screen size preference."""
        size = (self._screen_size or "desktop").lower()
        if size == "mobile":
            return int(base * 0.55)
        if size == "tablet":
            return int(base * 0.75)
        return base

    def _build_ui(self) -> None:
        """Build tabbed interface matching bandwidth panel style."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Create tab widget
        tabs = QtWidgets.QTabWidget()
        tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(False)
        tabs.setElideMode(QtCore.Qt.TextElideMode.ElideRight)
        tabs.setFixedWidth(self._width)

        # Presearch tab
        self.presearch_panel = ServiceNodeTab("Node", PRESEARCH_DOC_URL)
        self.presearch_panel.refresh_clicked.connect(self.presearch_refresh_clicked.emit)
        self.presearch_panel.toggle_changed.connect(self.presearch_toggle_changed.emit)
        self.presearch_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        
        presearch_container = QtWidgets.QWidget()
        presearch_layout = QtWidgets.QVBoxLayout(presearch_container)
        presearch_layout.setContentsMargins(0, 0, 0, 0)
        presearch_layout.setSpacing(4)
        presearch_layout.addWidget(self.presearch_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.presearch_panel.show_status_message("Loading Presearch status...")
        tabs.addTab(presearch_container, "Presearch")

        # Diiisco tab
        self.diiisco_panel = ServiceNodeTab("Node", DIIISCO_DOC_URL)
        self.diiisco_panel.refresh_clicked.connect(self.diiisco_refresh_clicked.emit)
        self.diiisco_panel.toggle_changed.connect(self.diiisco_toggle_changed.emit)
        self.diiisco_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        
        diiisco_container = QtWidgets.QWidget()
        diiisco_layout = QtWidgets.QVBoxLayout(diiisco_container)
        diiisco_layout.setContentsMargins(0, 0, 0, 0)
        diiisco_layout.setSpacing(4)
        diiisco_layout.addWidget(self.diiisco_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.diiisco_panel.show_status_message("Loading Diiisco status...")
        tabs.addTab(diiisco_container, "Diiisco")

        layout.addWidget(tabs)

    # Presearch methods
    def update_presearch_status(self, status) -> None:
        """Update Presearch tab with status object."""
        status_text = self._build_presearch_summary(status)
        self.presearch_panel.update_status(status_text)
        self.presearch_panel.set_toggle_state(status.running)

    def set_presearch_unavailable(self, message: str) -> None:
        """Disable Presearch toggle and show a persistent warning."""
        self.presearch_panel.set_unavailable(message)

    def set_presearch_busy(self, busy: bool) -> None:
        """Set Presearch tab busy state."""
        self.presearch_panel.set_busy(busy)

    def _build_presearch_summary(self, status) -> str:
        """Build Presearch status summary for large display."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        
        if status.running:
            return f"Great! Presearch is running and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
        else:
            return f"Status: Stopped. Enable it to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards!"

    # Diiisco methods
    def update_diiisco_status(self, status) -> None:
        """Update Diiisco tab with status object."""
        status_text = self._build_diiisco_summary(status)
        self.diiisco_panel.update_status(status_text)
        self.diiisco_panel.set_toggle_state(status.running)

    def set_diiisco_unavailable(self, message: str) -> None:
        """Disable Diiisco toggle and show a persistent warning."""
        self.diiisco_panel.set_unavailable(message)

    def set_diiisco_busy(self, busy: bool) -> None:
        """Set Diiisco tab busy state."""
        self.diiisco_panel.set_busy(busy)

    def _build_diiisco_summary(self, status) -> str:
        """Build Diiisco status summary for large display."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        
        if status.running:
            return f"Great! Diiisco is running and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
        else:
            return f"Status: Stopped. Enable it to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards!"

    def on_tick(self, data: dict) -> None:
        """Handle tick updates (for LiveData compatibility).
        
        SVN doesn't have sensor data, so this is mostly a no-op.
        Status updates come via update_presearch_status/update_diiisco_status.
        """
        pass
