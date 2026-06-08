"""Qt widget presenting XMRig mining status (read-only, no toggle)."""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from miner_GUI.services.xmrig import XMRigStatus


class XMRigPanel(QtWidgets.QGroupBox):
    """Panel showing XMRig mining status. Always-on, no user toggle."""

    refresh_clicked = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("", parent)
        self._last_status: Optional[XMRigStatus] = None
        self._mac_mismatch = False
        self._is_pending = False
        self._is_offline = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 1)

        # Status label
        self._status_label = QtWidgets.QLabel("XMRig: checking status...")
        self._status_label.setAccessibleName("xmrig_label_status")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Minimum,
        )
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label, 0, 0, 1, 2)

        # Stats row
        self._stats_label = QtWidgets.QLabel("")
        self._stats_label.setAccessibleName("xmrig_label_stats")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label, 1, 0, 1, 2)

        # Button row
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.setAccessibleName("xmrig_button_refresh")
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._refresh_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        btn_row.addWidget(self._refresh_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        layout.addLayout(btn_row, 2, 0, 1, 2)

    def update_status(self, status: XMRigStatus) -> None:
        """Update panel with current status."""
        self._last_status = status

        from miner_GUI.utils.status_week import load_status_week_for_date
        from datetime import date

        today = date.today()
        week_doc = load_status_week_for_date(today)

        mac_mismatch = None
        online_status = None
        if isinstance(week_doc, dict):
            mac_mismatch = week_doc.get("mac_mismatch")
            online_status = week_doc.get("online_status")

        mac_unknown = mac_mismatch is None
        online_unknown = not online_status
        gates_null = mac_unknown or online_unknown
        status.pending = gates_null

        self._is_pending = status.pending

        if self._mac_mismatch:
            return
        summary = self._build_summary(status)
        self._status_label.setText(summary)

        # Color status based on mining state
        if status.running and status.connected:
            self._status_label.setStyleSheet("color: #22c55e;")  # green
        elif status.running:
            self._status_label.setStyleSheet("color: #eab308;")  # yellow
        else:
            self._status_label.setStyleSheet("color: #E5E7EB;")  # default

        self._stats_label.setText(self._build_stats(status))

    def show_status_message(self, message: str) -> None:
        """Show a status message."""
        self._last_status = None
        if self._mac_mismatch or self._is_pending or self._is_offline:
            return
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #E5E7EB;")
        self._stats_label.setText("")

    def set_pending_state(self, is_pending: bool) -> None:
        """Set or clear pending state."""
        self._is_pending = is_pending
        if is_pending and not self._mac_mismatch:
            self._status_label.setStyleSheet("color: #E5E7EB;")

    def set_offline_state(self, is_offline: bool, message: str = "") -> None:
        """Show warning when device is offline."""
        self._is_offline = is_offline
        if is_offline:
            if not self._mac_mismatch and message:
                self._status_label.setText(message)
                self._status_label.setStyleSheet("color: #E5E7EB;")
        else:
            if not self._mac_mismatch:
                self._status_label.setStyleSheet("color: #E5E7EB;")

    def set_mac_mismatch_state(self, is_mismatched: bool, warning_message: str = "") -> None:
        """Show warning when MAC is mismatched."""
        self._mac_mismatch = is_mismatched
        if is_mismatched:
            if warning_message:
                self._status_label.setText(warning_message)
                self._status_label.setStyleSheet("color: #DC2626; font-weight: 600;")
            self._stats_label.setText("")
        else:
            if self._last_status:
                summary = self._build_summary(self._last_status)
                self._status_label.setText(summary)
                self._stats_label.setText(self._build_stats(self._last_status))
            self._status_label.setStyleSheet("color: #E5E7EB;")

    def set_busy(self, busy: bool) -> None:
        """Set busy state."""
        self._refresh_btn.setEnabled(not busy)

    def _on_refresh_clicked(self) -> None:
        self.refresh_clicked.emit()

    def _build_summary(self, status: XMRigStatus) -> str:
        """Build status summary text."""
        from miner_GUI.ui.main_window import PENDING_MESSAGE

        if status.pending:
            return PENDING_MESSAGE
        if not status.configured:
            return "XMRig not configured. Awaiting service setup."

        if status.running:
            if status.connected:
                algo = status.algorithm or "mining"
                return f"Mining ({algo}) \u2014 {status.hashrate_10s:.1f} H/s"
            else:
                return "Starting miner... connecting to pool"
        else:
            if status.last_error:
                return f"Stopped \u2014 {status.last_error[:60]}"
            return "Stopped \u2014 restarting..."

    def _build_stats(self, status: XMRigStatus) -> str:
        """Build statistics text."""
        parts = []

        if status.shares_total > 0:
            parts.append(f"Shares: {status.shares_good}/{status.shares_total}")

        if status.uptime_seconds > 0:
            hours = status.uptime_seconds / 3600
            if hours >= 24:
                parts.append(f"Uptime: {hours / 24:.1f} days")
            elif hours >= 1:
                parts.append(f"Uptime: {hours:.1f} hrs")
            else:
                parts.append(f"Uptime: {status.uptime_seconds // 60} min")

        if status.cpu_temp is not None:
            parts.append(f"CPU: {status.cpu_temp:.0f}\u00b0C")

        if status.diff_current > 0:
            if status.diff_current >= 1_000_000:
                parts.append(f"Diff: {status.diff_current / 1_000_000:.1f}M")
            elif status.diff_current >= 1_000:
                parts.append(f"Diff: {status.diff_current / 1_000:.1f}K")
            else:
                parts.append(f"Diff: {status.diff_current:,}")

        if status.hashrate_max > 0:
            parts.append(f"Max: {status.hashrate_max:.1f} H/s")

        return " | ".join(parts) if parts else ""
