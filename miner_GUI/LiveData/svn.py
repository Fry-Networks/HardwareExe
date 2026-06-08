"""LiveData panel for SVN (Storage Validator Node) miners.

Displays XMRig mining status. Always-on, no user toggle.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt


class MiningStatsTab(QtWidgets.QGroupBox):
    """Tab panel for XMRig mining status (read-only, no toggle)."""

    refresh_clicked = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("", parent)
        self._mac_mismatch = False
        self._is_pending = False
        self._is_unavailable = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        layout.setColumnStretch(0, 1)

        # Large status display area
        self._status_label = QtWidgets.QLabel("Checking status...")
        self._status_label.setAccessibleName("livedata_svn_label_status")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        self._status_label.setMinimumHeight(60)
        layout.addWidget(self._status_label, 0, 0, 1, 2)

    def _can_update(self) -> bool:
        return not self._mac_mismatch and not self._is_pending and not self._is_unavailable

    def update_status(self, status_text: str) -> None:
        """Update the large status display area."""
        if self._can_update():
            self._status_label.setText(status_text)

    def set_busy(self, busy: bool) -> None:
        """Set busy state (no toggle to disable)."""
        pass

    def show_status_message(self, message: str) -> None:
        """Show a simple status message."""
        if self._can_update():
            self._status_label.setText(message)

    def set_unavailable(self, message: str) -> None:
        """Mark panel as permanently unavailable."""
        self._is_unavailable = True
        self._is_pending = False
        self._status_label.setText(message)

    def set_mac_mismatch_state(self, is_mismatched: bool, warning_message: str = "") -> None:
        """Show warning when MAC is mismatched."""
        self._mac_mismatch = is_mismatched
        if is_mismatched:
            if warning_message:
                self._status_label.setText(warning_message)
                self._status_label.setStyleSheet("color: #DC2626; font-weight: 600;")
        else:
            self._status_label.setStyleSheet("")

    def set_pending_state(self, is_pending: bool) -> None:
        """Set pending state when waiting for miner configuration."""
        self._is_pending = is_pending


class SvnPanel(QtWidgets.QWidget):
    """LiveData panel for SVN miners with XMRig mining tab."""

    # Signals for external handlers
    xmrig_refresh_clicked = QtCore.Signal()

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
        """Build tabbed interface matching RDN panel style."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Create tab widget
        tabs = QtWidgets.QTabWidget()
        tabs.setAccessibleName("livedata_svn_tabwidget")
        tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(False)
        tabs.setElideMode(QtCore.Qt.TextElideMode.ElideRight)
        tabs.setFixedWidth(self._width)

        # XMRig tab
        self.xmrig_panel = MiningStatsTab()
        self.xmrig_panel.refresh_clicked.connect(self.xmrig_refresh_clicked.emit)
        self.xmrig_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        xmrig_container = QtWidgets.QWidget()
        xmrig_layout = QtWidgets.QVBoxLayout(xmrig_container)
        xmrig_layout.setContentsMargins(0, 0, 0, 0)
        xmrig_layout.setSpacing(4)
        xmrig_layout.addWidget(self.xmrig_panel, 0, Qt.AlignmentFlag.AlignTop)
        self.xmrig_panel.show_status_message("Loading XMRig status...")
        tabs.addTab(xmrig_container, "XMRig")

        layout.addWidget(tabs)

    # XMRig methods
    def update_xmrig_status(self, status) -> None:
        """Update XMRig tab with status object."""
        status_text = self._build_xmrig_summary(status)
        self.xmrig_panel.update_status(status_text)

    def set_xmrig_unavailable(self, message: str) -> None:
        """Disable XMRig panel and show a persistent warning."""
        self.xmrig_panel.set_unavailable(message)

    def set_xmrig_busy(self, busy: bool) -> None:
        """Set XMRig tab busy state."""
        self.xmrig_panel.set_busy(busy)

    def _build_xmrig_summary(self, status) -> str:
        """Build XMRig status summary for large display."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD

        if status.running and status.connected:
            algo = status.algorithm or "mining"
            return (
                f"Great! XMRig is running ({algo}, {status.hashrate_10s:.1f} H/s) "
                f"and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
            )
        elif status.running:
            return "XMRig is starting... connecting to mining pool."
        else:
            return (
                f"Status: Stopped. Mining will restart automatically "
                f"to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
            )

    def on_tick(self, data: dict) -> None:
        """Handle tick updates (for LiveData compatibility).

        SVN doesn't have sensor data, so this is mostly a no-op.
        Status updates come via update_xmrig_status.
        """
        pass
