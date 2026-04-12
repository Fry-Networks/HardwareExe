"""Qt widget presenting Diiisco Node status."""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from miner_GUI.services.diiisco import DiiiscoStatus, DiiiscoController
from .toggle_switch import ToggleSwitch


class DiiiscoPanel(QtWidgets.QGroupBox):
    """Panel showing Diiisco Node status with toggle."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self._last_status: Optional[DiiiscoStatus] = None
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False  # Track if panel is in pending state
        self._is_offline = False  # Track if device is offline
        self._controller: Optional[DiiiscoController] = None
        try:
            self._controller = DiiiscoController()
        except Exception:
            pass
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 120)

        # Toggle switch (hidden — all integrations are forced ON)
        self._toggle = ToggleSwitch(width=58, height=28)
        self._toggle.stateChanged.connect(self._on_toggle_state)

        # Status label
        self._status_label = QtWidgets.QLabel("Diiisco Node: checking status...")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum
        )
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label, 1, 0, 1, 2)

        # Stats row
        self._stats_label = QtWidgets.QLabel("")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label, 2, 0, 1, 2)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._refresh_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed
        )
        btn_row.addWidget(self._refresh_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        layout.addLayout(btn_row, 3, 0, 1, 2)

    def update_status(self, status: DiiiscoStatus) -> None:
        """Update panel with current status."""
        self._last_status = status
        
        # Check if ANY gate is unknown (null) in main window to determine pending state
        # Read directly from rewards JSON to get authoritative gate values
        from miner_GUI.utils.status_week import load_status_week_for_date
        from datetime import date
        today = date.today()
        week_doc = load_status_week_for_date(today)
        
        mac_mismatch = None
        online_status = None
        if isinstance(week_doc, dict):
            mac_mismatch = week_doc.get("mac_mismatch")
            online_status = week_doc.get("online_status")

        # Only trigger pending when a gate is null/empty (not yet set by backend)
        mac_unknown = mac_mismatch is None
        online_unknown = not online_status  # None or ""
        gates_null = mac_unknown or online_unknown
        
        # Show pending if at least one gate is unknown
        status.pending = gates_null

        # Sync panel's pending flag with status
        self._is_pending = status.pending

        # Only skip update if MAC is mismatched (to preserve warning message)
        # Allow pending status through so _build_summary can show pending message
        if self._mac_mismatch:
            return
        summary = self._build_summary(status)
        self._status_label.setText(summary)
        self._status_label.setStyleSheet("color: #E5E7EB;")  # Clear any previous warning styling
        self._stats_label.setText(self._build_stats(status))

        self._suspend_toggle = True
        try:
            self._toggle.setChecked(status.running)
            self._sync_toggle_enabled()
        finally:
            self._suspend_toggle = False

    def show_status_message(self, message: str) -> None:
        """Show a status message."""
        self._last_status = None
        if self._mac_mismatch or self._is_pending or self._is_offline:
            return
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #E5E7EB;")  # Clear any previous warning styling
        self._stats_label.setText("")
        self._sync_toggle_enabled()

    def _sync_toggle_enabled(self) -> None:
        """Unified toggle enable/disable based on all blocking flags."""
        should_disable = self._mac_mismatch or self._is_pending or self._is_offline
        self._toggle.setEnabled(not should_disable)

    def set_pending_state(self, is_pending: bool) -> None:
        """Set or clear pending state."""
        self._is_pending = is_pending
        if is_pending and not self._mac_mismatch:
            self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()

    def set_offline_state(self, is_offline: bool, message: str = "") -> None:
        """Disable toggle and show warning when device is offline."""
        self._is_offline = is_offline
        if is_offline:
            if not self._mac_mismatch and message:
                self._status_label.setText(message)
                self._status_label.setStyleSheet("color: #E5E7EB;")
        else:
            if not self._mac_mismatch:
                self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()

    def set_mac_mismatch_state(self, is_mismatched: bool, warning_message: str = "") -> None:
        """Disable toggle and show warning when MAC is mismatched."""
        self._mac_mismatch = is_mismatched
        if is_mismatched:
            if warning_message:
                self._status_label.setText(warning_message)
                self._status_label.setStyleSheet("color: #DC2626; font-weight: 600;")
            self._stats_label.setText("")
        else:
            if self._last_status:
                self._suspend_toggle = True
                try:
                    self._toggle.setChecked(self._last_status.enabled)
                finally:
                    self._suspend_toggle = False
                summary = self._build_summary(self._last_status)
                self._status_label.setText(summary)
                self._stats_label.setText(self._build_stats(self._last_status))
            self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()

    def set_busy(self, busy: bool) -> None:
        """Set busy state."""
        self._sync_toggle_enabled()
        self._refresh_btn.setEnabled(not busy)

    def _on_toggle_state(self, state: int) -> None:
        if self._suspend_toggle:
            return
        enabled = bool(state)
        # Only emit signal - the integration handler will call controller.enable()/disable()
        # which handles persistence. Persisting/calling here would cause duplicate operations.
        self.toggle_changed.emit(enabled)

    def _on_refresh_clicked(self) -> None:
        self.refresh_clicked.emit()

    def _build_summary(self, status: DiiiscoStatus) -> str:
        """Build status summary text."""
        from miner_GUI.ui.main_window import PENDING_MESSAGE
        if status.pending:
            return PENDING_MESSAGE
        if not status.configured:
            return "Diiisco Node not configured."

        parts = []
        if status.running:
            if status.connected:
                parts.append("Connected")
            else:
                parts.append("Running (connecting...)")
        else:
            parts.append("Stopped")

        if status.network:
            parts.append(f"Network: {status.network}")

        if status.last_error:
            parts.append(f"Error: {status.last_error[:50]}")

        return " | ".join(parts) if parts else "Status unknown"

    def _build_stats(self, status: DiiiscoStatus) -> str:
        """Build statistics text."""
        parts = []

        if status.peer_count > 0:
            parts.append(f"Peers: {status.peer_count}")

        if status.discoveries_count > 0:
            parts.append(f"Discoveries: {status.discoveries_count:,}")

        if status.uptime_seconds > 0:
            hours = status.uptime_seconds / 3600
            if hours >= 24:
                days = hours / 24
                parts.append(f"Uptime: {days:.1f} days")
            elif hours >= 1:
                parts.append(f"Uptime: {hours:.1f} hrs")
            else:
                mins = status.uptime_seconds / 60
                parts.append(f"Uptime: {mins:.0f} min")

        if status.node_id:
            node_id = status.node_id
            if len(node_id) > 16:
                node_id = f"{node_id[:8]}..."
            parts.append(f"ID: {node_id}")

        if status.version:
            parts.append(f"v{status.version}")

        return " | ".join(parts) if parts else ""
