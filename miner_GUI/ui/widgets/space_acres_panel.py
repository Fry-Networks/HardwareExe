"""Qt widget presenting Space Acres (Autonomy) farming status."""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from miner_GUI.services.space_acres import SpaceAcresStatus
from .toggle_switch import ToggleSwitch


class SpaceAcresPanel(QtWidgets.QGroupBox):
    """Panel showing Space Acres farming status with toggle."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self._last_status: Optional[SpaceAcresStatus] = None
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False  # Track if panel is in pending state
        self._is_offline = False  # Track if device is offline
        self._was_syncing = False
        self._was_finalizing = False
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
        self._status_label = QtWidgets.QLabel("Space Acres: checking status...")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum
        )
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label, 1, 0, 1, 2)

        # Sync progress bar (hidden by default)
        self._sync_bar = QtWidgets.QProgressBar()
        self._sync_bar.setRange(0, 10000)
        self._sync_bar.setValue(0)
        self._sync_bar.setTextVisible(True)
        self._sync_bar.setFixedHeight(20)
        self._sync_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #374151; border-radius: 4px;"
            " background: #1F2937; text-align: center; color: #E5E7EB; }"
            "QProgressBar::chunk { background: #2563EB; border-radius: 3px; }"
        )
        self._sync_bar.hide()
        layout.addWidget(self._sync_bar, 2, 0, 1, 2)

        # Stats row
        self._stats_label = QtWidgets.QLabel("")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label, 3, 0, 1, 2)

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

        layout.addLayout(btn_row, 4, 0, 1, 2)

    def update_status(self, status: SpaceAcresStatus) -> None:
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

        # Update sync progress bar based on syncPhase
        if status.syncing:
            if status.sync_phase == "dsn_download":
                # DSN snap sync — blocks jump suddenly, bar would be misleading
                self._sync_bar.hide()
            elif status.sync_phase == "finalization":
                self._sync_bar.setValue(10000)
                self._sync_bar.setFormat("100%")
                self._sync_bar.show()
            elif status.sync_percent is not None:
                self._sync_bar.setValue(int(status.sync_percent * 100))
                self._sync_bar.setFormat(f"{status.sync_percent:.2f}%")
                self._sync_bar.show()
            else:
                self._sync_bar.hide()
        elif status.finalizing:
            self._sync_bar.setValue(10000)
            self._sync_bar.setFormat("100%")
            self._sync_bar.show()
        else:
            self._sync_bar.hide()

        self._was_syncing = status.syncing
        self._was_finalizing = status.finalizing
        self._toggle.set_syncing(
            status.syncing or status.finalizing or status.node_starting or status.stalled
        )

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
        self.toggle_changed.emit(bool(state))

    def _on_refresh_clicked(self) -> None:
        self.refresh_clicked.emit()

    def _build_summary(self, status: SpaceAcresStatus) -> str:
        """Build status summary text."""
        from miner_GUI.ui.main_window import PENDING_MESSAGE
        if status.pending:
            return PENDING_MESSAGE
        if not status.configured:
            return "Space Acres not configured. Install from docs.autonomys.xyz"

        if status.stalled:
            return "Restarting node..."

        if status.degraded:
            return "Degraded - check logs"

        if status.node_starting:
            return "Starting node..."

        if status.syncing:
            return self._sync_phase_text(status)

        if status.finalizing:
            gap = f"{status.finalization_gap:,}" if status.finalization_gap is not None else "?"
            return f"Finalizing: {gap} blocks remaining"

        if status.running:
            if self._was_syncing or self._was_finalizing:
                return "Sync complete! Fully synced."
            if status.farming:
                return "Farming active"
            return "Running - Fully synced"

        if status.last_error:
            return f"Error: {status.last_error[:80]}"

        return "Stopped"

    def _sync_phase_text(self, status: SpaceAcresStatus) -> str:
        """Return display text based on syncPhase."""
        phase = status.sync_phase
        if phase == "dsn_download":
            return "Downloading blockchain data..."
        if phase == "finalization":
            gap = f"{status.finalization_gap:,}" if status.finalization_gap is not None else "?"
            return f"Finalizing: {gap} blocks remaining"
        # "block_sync" or unknown
        if status.sync_percent is not None:
            cb = f"{status.best_block:,}" if status.best_block else "?"
            hb = f"{status.highest_block:,}" if status.highest_block else "?"
            return f"Syncing blockchain: {status.sync_percent:.2f}% ({cb} / {hb} blocks)"
        return "Syncing blockchain..."

    def _build_stats(self, status: SpaceAcresStatus) -> str:
        """Build statistics text."""
        parts = []

        if status.plotted_space_gb > 0:
            parts.append(f"Plotted: {status.plotted_space_gb:.1f} GB")

        if status.best_block:
            parts.append(f"Block: #{status.best_block:,}")

        if status.peers > 0:
            parts.append(f"Peers: {status.peers}")

        if status.reward_address:
            addr = status.reward_address
            if len(addr) > 20:
                addr = f"{addr[:8]}...{addr[-8:]}"
            parts.append(f"Reward: {addr}")

        return " | ".join(parts) if parts else ""
