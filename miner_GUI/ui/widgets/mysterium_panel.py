"""Qt widget presenting Mysterium runtime information."""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from miner_GUI.services.mysterium import MysteriumStatus
from .toggle_switch import ToggleSwitch


class MysteriumPanel(QtWidgets.QGroupBox):
    """Compact panel for Mysterium with toggle and warning popup."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)
    warning_clicked = QtCore.Signal()
    diagnose_clicked = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Mysterium", parent)
        self._last_status: Optional[MysteriumStatus] = None
        self._last_known_running: Optional[bool] = None
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False  # Track if panel is in pending state
        self._is_offline = False  # Track if device is offline
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 1)

        # Toggle switch (hidden — all integrations are forced ON)
        self._toggle = ToggleSwitch(width=58, height=28)
        self._toggle.stateChanged.connect(self._on_toggle_state)

        self._status_label = QtWidgets.QLabel("Mysterium status: unavailable")
        self._status_label.setWordWrap(True)
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label, 1, 0, 1, 2)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self._warn_btn = QtWidgets.QPushButton("Warnings")
        self._warn_btn.setVisible(False)
        self._warn_btn.clicked.connect(self._on_warning_clicked)
        btn_row.addWidget(self._warn_btn, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self._diagnose_btn = QtWidgets.QPushButton("Diagnose")
        self._diagnose_btn.clicked.connect(self._on_diagnose_clicked)
        btn_row.addWidget(self._diagnose_btn, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        self._details_btn = QtWidgets.QPushButton("Refresh")
        self._details_btn.clicked.connect(self._on_refresh_clicked)
        btn_row.addWidget(self._details_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        layout.addLayout(btn_row, 2, 0, 1, 2)

    # ---------- public API ----------
    def update_status(self, status: MysteriumStatus) -> None:
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
        self._suspend_toggle = True
        try:
            # If API check failed, preserve last known state instead of assuming stopped
            if not status.api_ok and self._last_known_running is not None:
                # Network/API issue - keep last known state, but show warning
                self._toggle.setChecked(self._last_known_running)
                if not status.warning and not status.last_error:
                    summary += " | Status check failed - showing last known state"
                    self._status_label.setText(summary)
            else:
                # API responded or first check - update state
                self._toggle.setChecked(bool(status.running))
                if status.api_ok:
                    self._last_known_running = bool(status.running)
            self._sync_toggle_enabled()
        finally:
            self._suspend_toggle = False
        # Warning button visibility
        has_warn = bool(status.enabled and (status.warning or status.last_error or not status.port_ok or not status.api_ok))
        self._warn_btn.setVisible(has_warn)

    def show_status_message(self, message: str) -> None:
        self._last_status = None
        if self._mac_mismatch or self._is_pending or self._is_offline:
            return
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()
        self._warn_btn.setVisible(False)
    
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
            self._warn_btn.setVisible(False)
        else:
            if self._last_status:
                self._suspend_toggle = True
                try:
                    self._toggle.setChecked(bool(self._last_status.running))
                finally:
                    self._suspend_toggle = False
                summary = self._build_summary(self._last_status)
                self._status_label.setText(summary)
            self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()

    def set_busy(self, busy: bool) -> None:
        self._sync_toggle_enabled()
        self._details_btn.setEnabled(not busy)
        self._diagnose_btn.setEnabled(not busy)

    def update_with_measurements(self, measurements: dict) -> None:
        """Update panel with fresh measurement data from service.
        
        Called by main_window when new measurements are polled.
        Future: Could display PoC-specific earnings/status from measurements.
        
        Args:
            measurements: Measurement dict with pod_status, hardware_stats, poc_applications, etc.
        """
        # Future: Extract Mysterium-specific data from poc_applications if available
        pass

    # ---------- signals ----------
    def _on_toggle_state(self, state: int) -> None:
        if self._suspend_toggle:
            return
        self.toggle_changed.emit(bool(state))

    def _on_refresh_clicked(self) -> None:
        self.refresh_clicked.emit()

    def _on_warning_clicked(self) -> None:
        self.warning_clicked.emit()

    def _on_diagnose_clicked(self) -> None:
        self.diagnose_clicked.emit()

    # ---------- helpers ----------
    def _build_summary(self, status: MysteriumStatus) -> str:
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        from miner_GUI.ui.main_window import PENDING_MESSAGE
        if status.pending:
            return PENDING_MESSAGE
        # If user has disabled Mysterium, show clear UX message
        if not status.enabled:
            return f"Mysterium is disabled. Enable it to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards!"
        if status.running:
            return f"Great! Mysterium is enabled and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
        # Only surface API warnings when enabled (user expects it to run)
        if status.enabled:
            if not status.port_ok:
                return "Mysterium enabled | API port unreachable"
            if not status.api_ok:
                return "Mysterium enabled | API not responding"
        return "Mysterium enabled"
