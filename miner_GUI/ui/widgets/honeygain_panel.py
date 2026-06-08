"""Qt widget presenting Honeygain runtime information."""

from __future__ import annotations

import json
import logging
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from miner_GUI.services.honeygain import HoneygainStatus, HoneygainConfig, load_config
from miner_GUI.utils.gui import apply_fry_theme_to_dialog
from .toggle_switch import ToggleSwitch

HONEYGAIN_DOC_URL = (
    "https://github.com/FryNetworks/HardwareExe/blob/main/docs/HoneygainIntegration.md"
)

logger = logging.getLogger(__name__)


class HoneygainPanel(QtWidgets.QGroupBox):
    """Compact panel that surfaces Honeygain SDK state and metrics."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)

    def __init__(self, parent=None):
        super().__init__("Honeygain", parent)
        self._details_dialog: Optional[_HoneygainDetailsDialog] = None
        self._last_status: Optional[HoneygainStatus] = None
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False  # Track if panel is in pending state
        self._is_offline = False  # Track if device is offline
        self._config: Optional[HoneygainConfig] = None
        try:
            self._config = load_config()
        except Exception:
            pass
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
        self._toggle.setAccessibleName("honeygain_toggle_switch")
        self._toggle.stateChanged.connect(self._on_toggle_state)

        self._status_label = QtWidgets.QLabel("Honeygain status: unavailable")
        self._status_label.setAccessibleName("honeygain_label_status")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self._status_label.setMinimumHeight(36)
        layout.addWidget(self._status_label, 1, 0, 1, 2)
        # Add breathing room above the button row on narrow screens
        layout.setRowMinimumHeight(2, 14)

        #self._consent_hint = self._create_consent_hint(
        #    "Honeygain keeps using the consent you granted during install."
        #)
        #layout.addWidget(self._consent_hint, 2, 0, 1, 1)

        self._learn_more_btn = QtWidgets.QPushButton("Learn more")
        self._learn_more_btn.setAccessibleName("honeygain_button_learn_more")
        self._learn_more_btn.clicked.connect(self._open_external_learn_more)
        self._learn_more_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)

        self._details_btn = QtWidgets.QPushButton("Details")
        self._details_btn.setAccessibleName("honeygain_button_details")
        self._details_btn.clicked.connect(self._show_details_dialog)
        self._details_btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)
        # Add spacer row to push button down on narrow layouts
        layout.setRowStretch(2, 1)
        layout.setRowMinimumHeight(3, 34)
        layout.addWidget(self._learn_more_btn, 3, 0, 1, 1, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._details_btn, 3, 1, 1, 1, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

    def _create_consent_hint(self, message: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(f"{message}")
        label.setObjectName("hint")
        label.setWordWrap(True)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        label.linkActivated.connect(self._open_learn_more_link)  # type: ignore[arg-type]
        return label

    def update_status(self, status: HoneygainStatus) -> None:
        """Populate panel with latest HoneygainStatus."""
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
        summary = _build_summary(status)
        self._status_label.setText(summary)
        self._status_label.setStyleSheet("color: #E5E7EB;")  # Clear any previous warning styling
        logger.debug(
            "HoneygainPanel.update_status sdk_loaded=%s configured=%s enabled=%s api_key=%s summary=%s",
            status.sdk_loaded,
            status.configured,
            status.enabled,
            status.api_key_present,
            summary,
        )

        if self._details_dialog:
            self._details_dialog.update_status(status)

        self._suspend_toggle = True
        try:
            self._toggle.setChecked(status.enabled)
            self._sync_toggle_enabled()
        finally:
            self._suspend_toggle = False

    def set_busy(self, busy: bool) -> None:
        """Temporarily disable controls while work is happening."""
        logger.debug("HoneygainPanel.set_busy busy=%s last_status_exists=%s", busy, self._last_status is not None)
        if not busy and self._last_status:
            self._suspend_toggle = True
            try:
                self._toggle.setChecked(self._last_status.enabled)
            finally:
                self._suspend_toggle = False
        self._sync_toggle_enabled()
        if self._details_dialog:
            self._details_dialog.set_busy(busy)

    def update_with_measurements(self, measurements: dict) -> None:
        """Update panel with fresh measurement data from service.
        
        Called by main_window when new measurements are polled.
        Future: Could display PoC-specific earnings/status from measurements.
        
        Args:
            measurements: Measurement dict with pod_status, hardware_stats, poc_applications, etc.
        """
        # Future: Extract Honeygain-specific data from poc_applications if available
        pass

    def show_status_message(self, message: str) -> None:
        """Display a plain status string when no Honeygain data is available."""
        logger.debug("HoneygainPanel.show_status_message message=%s", message)
        self._last_status = None
        # Guard against overwriting MAC warning, pending, or offline message
        if self._mac_mismatch or self._is_pending or self._is_offline:
            return
        self._status_label.setText(message)
        self._status_label.setStyleSheet("color: #E5E7EB;")
        self._sync_toggle_enabled()
        if self._details_dialog:
            self._details_dialog.show_status_message(message)
    
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
        else:
            self._status_label.setStyleSheet("color: #E5E7EB;")  # Clear red first
            if self._last_status:
                self._suspend_toggle = True
                try:
                    self._toggle.setChecked(self._last_status.enabled)
                finally:
                    self._suspend_toggle = False
                summary = _build_summary(self._last_status)
                self._status_label.setText(summary)
        self._sync_toggle_enabled()

    def _on_toggle_state(self, state: int) -> None:
        if self._suspend_toggle:
            return
        enabled = bool(state)
        # Only emit signal - the controller's enable()/opt_out() will persist config
        # and the integration handler will send the reload signal if needed.
        # Persisting here would cause duplicate write_config requests.
        self.toggle_changed.emit(enabled)

    def _open_external_learn_more(self) -> None:
        try:
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl("https://www.honeygain.com/privacy-policy/")
            )
        except Exception:
            pass

    def _show_details_dialog(self) -> None:
        dialog = self._ensure_details_dialog()
        if self._last_status:
            dialog.update_status(self._last_status)
        else:
            dialog.show_status_message(self._status_label.text())
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _ensure_details_dialog(self) -> "_HoneygainDetailsDialog":
        if self._details_dialog is None:
            self._details_dialog = _HoneygainDetailsDialog(self)
            self._details_dialog.refresh_clicked.connect(self.refresh_clicked)  # type: ignore[arg-type]
        return self._details_dialog

    @QtCore.Slot(str)
    def _open_learn_more_link(self, link: str) -> None:
        if link == "#learn-more":
            self._show_details_dialog()
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(HONEYGAIN_DOC_URL))


class _HoneygainDetailsDialog(QtWidgets.QDialog):
    """Dialog that surfaces the full Honeygain diagnostics grid."""

    refresh_clicked = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Honeygain details")
        self.setModal(False)
        self._build_ui()
        # Apply FryNetworks theme to this dialog
        apply_fry_theme_to_dialog(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._status_label = QtWidgets.QLabel("Honeygain details unavailable")
        self._status_label.setAccessibleName("honeygain_label_status")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        self._configured_val = self._add_row(grid, 0, "Configured")
        self._enabled_val = self._add_row(grid, 1, "Enabled")
        self._running_val = self._add_row(grid, 2, "SDK running")
        self._consent_val = self._add_row(grid, 3, "Consent")
        self._traffic_val = self._add_row(grid, 4, "Traffic (total)")
        self._traffic24_val = self._add_row(grid, 5, "Traffic (24h)")
        self._device_val = self._add_row(grid, 6, "Device ID")
        self._session_val = self._add_row(grid, 7, "Session ID")
        self._library_val = self._add_row(grid, 8, "SDK library")
        self._config_val = self._add_row(grid, 9, "Config file")
        self._updated_val = self._add_row(grid, 10, "Last update")
        self._error_val = self._add_row(grid, 11, "Last error")
        layout.addLayout(grid)

        self._details = QtWidgets.QPlainTextEdit()
        self._details.setAccessibleName("honeygain_plaintextedit_details")
        self._details.setReadOnly(True)
        self._details.setMaximumHeight(160)
        self._details.hide()
        layout.addWidget(self._details)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.setAccessibleName("honeygain_button_refresh")
        self._refresh_btn.clicked.connect(self.refresh_clicked.emit)  # type: ignore[arg-type]
        btn_row.addWidget(self._refresh_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setAccessibleName("honeygain_button_close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen and screen.availableGeometry().width() <= 800:
                self.setMinimumWidth(360)
                self.setMaximumWidth(420)
        except Exception:
            pass

    def _add_row(self, layout: QtWidgets.QGridLayout, row: int, label: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(label)
        lbl.setObjectName("label")
        value = QtWidgets.QLabel("-")
        value.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(lbl, row, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(value, row, 1)
        return value

    def update_status(self, status: HoneygainStatus) -> None:
        self._status_label.setText(_build_summary(status))
        self._configured_val.setText("Yes" if status.configured else "No")
        self._enabled_val.setText("Yes" if status.enabled else "No")
        # When disabled, surface an explicit "No"/"false" instead of "Unknown"
        running_text = "No" if not status.enabled else _format_bool(status.running)
        consent_text = "false" if not status.enabled else _format_bool(status.opted_in)
        self._running_val.setText(running_text)
        self._consent_val.setText(consent_text)
        self._traffic_val.setText(_format_bytes(status.traffic_total_bytes))
        self._traffic24_val.setText(_format_bytes(status.traffic_24h_bytes))
        self._device_val.setText(status.device_id or "-")
        self._session_val.setText(status.session_id or "-")

        if status.library_path:
            self._library_val.setText(str(status.library_path))
        elif status.sdk_loaded:
            self._library_val.setText("Loaded (path hidden)")
        else:
            self._library_val.setText("Not found")

        if status.config_path:
            path_str = str(status.config_path)
            display = path_str
            if len(path_str) > 48:
                parts = path_str.replace("\\", "/").split("/")
                display = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
            self._config_val.setText(display)
            self._config_val.setToolTip(path_str)
        else:
            self._config_val.setText("-")
        if status.last_error:
            self._error_val.setText(status.last_error)
            self._error_val.setStyleSheet("color: #c75c1e;")
        else:
            self._error_val.setText("-")
            self._error_val.setStyleSheet("")

        if status.last_refresh:
            ts = status.last_refresh.strftime("%Y-%m-%d %H:%M:%S UTC")
            self._updated_val.setText(ts)
        else:
            self._updated_val.setText("-")

        if status.identify_raw:
            pretty = json.dumps(status.identify_raw, indent=2, sort_keys=True)
            self._details.setPlainText(pretty)
            self._details.show()
        else:
            self._details.clear()
            self._details.hide()

        self._refresh_btn.setEnabled(True)

    def show_status_message(self, message: str) -> None:
        self._status_label.setText(message)
        for label in (
            self._configured_val,
            self._enabled_val,
            self._running_val,
            self._consent_val,
            self._traffic_val,
            self._traffic24_val,
            self._device_val,
            self._session_val,
            self._library_val,
            self._config_val,
            self._updated_val,
            self._error_val,
        ):
            label.setText("-")
        self._details.clear()
        self._details.hide()
        self._refresh_btn.setEnabled(False)

    def set_busy(self, busy: bool) -> None:
        self._refresh_btn.setEnabled(not busy)


def _build_summary(status: HoneygainStatus) -> str:
    from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
    from miner_GUI.ui.main_window import PENDING_MESSAGE
    if status.pending:
        return PENDING_MESSAGE
    if not status.sdk_loaded:
        return "Honeygain SDK not available"
    if not status.configured or not status.api_key_present:
        return "Honeygain installer data missing"
    if not status.enabled:
        return f"Honeygain is disabled. Enable it to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards!"
    if status.running:
        return f"Great! Honeygain is enabled and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
    if status.enabled and status.opted_in is False:
        return "Honeygain waiting for consent"
    return "Honeygain enabled but not running"


def _format_bool(value: Optional[bool]) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def _format_bytes(value: Optional[int]) -> str:
    if value is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(value)
    idx = 0
    while amount >= 1024 and idx < len(units) - 1:
        amount /= 1024.0
        idx += 1
    return f"{amount:.2f} {units[idx]}"
