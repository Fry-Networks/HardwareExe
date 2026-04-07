"""Bright Data integration helper functions"""

import sys
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets, QtGui

import logging
from config_profile import MINER_CODE
from miner_GUI.utils.data import log_step

logger = logging.getLogger(__name__)
from miner_GUI.services.bright import (
    BrightController,
    BrightConfigError,
    BrightError,
)
from miner_GUI.utils.gui import fry_error

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow


def init_bright_support(self: "MainWindow") -> None:
    """Initialize Bright controller and periodic refresh"""
    if MINER_CODE != "BM" or not self.bright_panel or not sys.platform.startswith("win") or not self._allow_bright:
        return
    # Reuse existing controller if already created to avoid duplicate bootstraps
    if not getattr(self, "bright_controller", None):
        try:
            self.bright_controller = BrightController()
        except BrightConfigError as exc:
            self.bright_panel.show_status_message(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            self.bright_panel.show_status_message(f"Bright unavailable: {exc}")
            return

    if not self.bright_controller or not self.bright_controller.sdk_loaded:
        self.bright_panel.show_status_message("Bright SDK library not found in SDK folder.")
        return

    # Managed path: no additional info text available
    # Ensure signals are not connected multiple times
    try:
        self.bright_panel.refresh_clicked.disconnect()
    except Exception:
        pass
    try:
        self.bright_panel.toggle_changed.disconnect()
    except Exception:
        pass
    self.bright_panel.refresh_clicked.connect(lambda: refresh_bright_status(self))
    self.bright_panel.toggle_changed.connect(lambda enabled: handle_bright_toggle(self, enabled))
    # Only bootstrap once at startup; subsequent panel rebuilds just restart the timer
    if not getattr(self, "_bright_bootstrapped_once", False):
        QtCore.QTimer.singleShot(0, lambda: bootstrap_bright_status(self))
    else:
        # Panel was rebuilt - ensure timer is restarted
        start_bright_timer(self)


def bootstrap_bright_status(self: "MainWindow") -> None:
    """Bootstrap initial Bright status check"""
    if not self.bright_controller or not self.bright_panel:
        return
    self.bright_panel.set_busy(True)
    try:
        log_step("bright_bootstrap_begin")
        self.bright_controller.ensure_started()
        status = self.bright_controller.refresh_status()
        self.bright_panel.update_status(status)
        self._bright_enabled = bool(getattr(status, "enabled", False))
        # Apply partner opt-in from installer config (this may enable Bright)
        self._apply_partner_opt_in("bright", status.enabled)
        # Note: Don't call ensure_consent_from_flag here as it can override the opt-in state
        # Consent will be handled when user manually toggles Bright
        log_step("bright_bootstrap_ok", {"enabled": bool(status.enabled), "running": bool(getattr(status, "running", None))})
        self._bright_bootstrapped_once = True
    except Exception as exc:  # pragma: no cover - defensive
        self.bright_panel.show_status_message(f"Bright error: {exc}")
        log_step("bright_bootstrap_failed", {"error": str(exc)})
        return
    finally:
        self.bright_panel.set_busy(False)
    start_bright_timer(self)
    from miner_GUI.ui.helpers import rewards as rewards_helpers
    rewards_helpers.update_rewards_hint(self)


def start_bright_timer(self: "MainWindow") -> None:
    """Start periodic Bright status refresh timer"""
    if not self.bright_controller:
        return
    if self._bright_timer:
        try:
            self._bright_timer.stop()
        except Exception:
            pass
    self._bright_timer = QtCore.QTimer(self)
    interval = 5000  # TESTING: match main GUI refresh rate (was max(10000, poll_interval_ms))
    self._bright_timer.setInterval(interval)
    self._bright_timer.timeout.connect(lambda: refresh_bright_status(self))
    self._bright_timer.start()


def stop_bright_timer(self: "MainWindow") -> None:
    """Stop Bright status refresh timer"""
    try:
        if self._bright_timer:
            self._bright_timer.stop()
    except Exception:
        pass
    self._bright_timer = None


def refresh_bright_status(self: "MainWindow") -> None:
    """Refresh Bright status display"""
    panel = self.bright_panel
    if not self.bright_controller or not panel:
        return
    try:
        import shiboken6
        if hasattr(shiboken6, 'isValid') and not shiboken6.isValid(panel):
            stop_bright_timer(self)
            return
    except Exception:
        pass
    panel.set_busy(True)
    try:
        status = self.bright_controller.refresh_status()
        try:
            panel.update_status(status)
        except Exception:
            pass
        # Update JSON file when Bright is offline
        if not status.running:
            self.bright_controller.mark_offline()
    except Exception as exc:  # pragma: no cover - defensive
        panel.show_status_message(f"Bright error: {exc}")
    finally:
        panel.set_busy(False)


def handle_bright_toggle(self: "MainWindow", enabled: bool) -> None:
    """Handle Bright toggle switch changes"""
    logger.debug(
        "Bright toggle requested enabled=%s panel_enabled=%s controller=%s",
        enabled,
        bool(self.bright_panel and self.bright_panel._toggle.isEnabled()),
        bool(self.bright_controller),
    )
    current_state = bool(self._bright_enabled) if self._bright_enabled is not None else False
    if self.bright_panel:
        # Keep the toggle reflecting the last confirmed state until user decision completes
        panel = self.bright_panel
        if panel:
            panel._suspend_toggle = True
            try:
                panel._toggle.setChecked(current_state)
            finally:
                panel._suspend_toggle = False

    # If enabling, show Bright's native consent dialog
    if enabled:
        if not self.bright_controller:
            return
        if self.bright_panel:
            self.bright_panel.set_busy(True)
        
        # Use our custom consent dialog
        choice = show_bright_consent_dialog(self)
        logger.info(f"Bright native consent choice: {choice}")
        
        try:
            applied = self.bright_controller.record_consent(bool(choice))
            status = self.bright_controller.refresh_status()
            if self.bright_panel:
                self.bright_panel.update_status(status)
            self._bright_enabled = bool(getattr(status, "enabled", False))
            self._set_partner_approval("bright", self._bright_enabled)
        except Exception as exc:
            logger.error(f"Bright consent recording failed: {exc}")
            applied = False
        
        final_state = applied and bool(choice)
        self._bright_enabled = bool(final_state)
        panel = self.bright_panel
        if panel:
            panel._suspend_toggle = True
            try:
                panel._toggle.setChecked(final_state)
            finally:
                panel._suspend_toggle = False
        
        if self.bright_panel:
            self.bright_panel.set_busy(False)
        from miner_GUI.ui.helpers import rewards as rewards_helpers
        rewards_helpers.update_rewards_hint(self)
        return
    else:
        # Warn user before disabling
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        per_pct = int(BM_PER_TOOL_REWARD * 100)
        msg = (
            f"Turning off Web Indexing will reduce your base fVPN rewards by {per_pct}%.\n\n"
            "Are you sure you want to disable it?"
        )
        from PySide6 import QtWidgets, QtCore
        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle("Disable Web Indexing Sharing?")
        dlg.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dlg.setText(msg)
        dlg.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        dlg.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Yes
        )
        dlg.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
        if dlg.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info("Bright disable cancelled, reverting toggle.")
            panel = self.bright_panel
            if panel:
                panel._suspend_toggle = True
                try:
                    panel._toggle.setChecked(True)
                finally:
                    panel._suspend_toggle = False
            return
    apply_bright_state(self, enable=enabled)


def show_bright_consent_dialog(self: "MainWindow") -> bool:
    """Show Bright consent dialog (custom, per Bright requirements)."""
    from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle("Enable Web Indexing by Bright Data")
    dialog.setModal(True)

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(10)

    text = (
        f"To add {int(BM_PER_TOOL_REWARD * 100)}% to the base rewards, please allow Web Indexing by "
        "<a href='https://brightdata.com/'>Bright Data</a> to use your device's free "
        "resources and IP address to download public web data from the Internet. "
        "Bright Data values your trust and takes every measure possible to protect your privacy and personal data. "
        "Bright Data understands the security matters at stake in sharing your IP address and monitors all of its network traffic to ensure your safety. "
        "Bright Data will <a href='#will-only-use'>only use</a> your IP address for approved business-related use cases and "
        "<a href='#never'>never</a> for unauthorized cases. None of your personal information is accessed or collected except your IP address.<br><br>"
        "Learn more about web indexing by Bright Data<br>"
        "<a href='https://bright-sdk.com/users#learn-more-about-bright-sdk-web-indexing'>Learn more</a><br>"
        "<a href='https://bright-sdk.com/privacy-policy'>Privacy Policy</a><br>"
        "Bright Data runs in the background even after closing the application.<br>"
        "Updates will be automatically downloaded and are subject to the "
        "<a href='https://bright-sdk.com/eula'>End User License Agreement</a>."
    )
    body = QtWidgets.QLabel(text)
    body.setWordWrap(True)
    body.setTextFormat(QtCore.Qt.TextFormat.RichText)
    body.setOpenExternalLinks(False)
    body.setStyleSheet("a { color: #4ea3ff; }")
    body.linkActivated.connect(lambda link: handle_bright_consent_link(self, link))
    layout.addWidget(body)

    btn_row = QtWidgets.QHBoxLayout()
    btn_row.addStretch(1)
    decline_btn = QtWidgets.QPushButton("Decline")
    decline_btn.clicked.connect(dialog.reject)
    btn_row.addWidget(decline_btn)
    accept_btn = QtWidgets.QPushButton("Accept")
    accept_btn.setDefault(True)
    accept_btn.clicked.connect(dialog.accept)
    btn_row.addWidget(accept_btn)
    layout.addLayout(btn_row)

    if getattr(self, "_screen_size_pref", "") == "mobile":
        taller = dialog.sizeHint().height() + 60
        dialog.resize(440, taller)
        dialog.setMinimumHeight(taller)
        dialog.setMinimumWidth(360)
        dialog.setMaximumWidth(520)
    else:
        dialog.resize(520, dialog.sizeHint().height())
        dialog.setMinimumWidth(420)
        dialog.setMaximumWidth(560)
    dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
    dialog.move(self.frameGeometry().center() - dialog.rect().center())
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


def handle_bright_consent_link(self: "MainWindow", link: str) -> None:
    """Handle clicks on Bright consent dialog links"""
    if link == "#will-only-use":
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Approved uses")
        box.setText(
            "Your IP address WILL be used for cases such as:\n\n"
            "• Support academic research\n"
            "• Help brands track sites selling fake products\n"
            "• Collect public web data like product prices and reviews\n"
            "• Aggregate travel information like flights and hotel prices"
        )
        if getattr(self, "_screen_size_pref", "") == "mobile":
            box.setMinimumWidth(320)
        box.exec()
    elif link == "#never":
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("Never used for")
        box.setText(
            "Your IP address will NEVER be misused:\n\n"
            "• Never to steal, encrypt, or delete sensitive data\n"
            "• Never to alter or hijack core computing functions\n"
            "• Never to monitor users' computer activity\n"
            "• Never to access illegal sites (dark web, porn, etc.)\n"
            "• Never to perform DDOS attacks"
        )
        if getattr(self, "_screen_size_pref", "") == "mobile":
            box.setMinimumWidth(320)
        box.exec()
    else:
        try:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(link))
        except Exception:
            pass


def apply_bright_state(self: "MainWindow", enable: bool) -> None:
    """Apply Bright enable/disable state.

    After the controller action (which enqueues a config write via ops_queue),
    we poll gui_config.enc until the service confirms the new approval state
    before updating the toggle.  The panel stays busy during polling.
    """
    if not self.bright_controller or not self.bright_panel:
        logger.warning("Bright state change skipped (controller or panel missing).")
        return
    logger.debug("Applying Bright state enable=%s", enable)
    self.bright_panel.set_busy(True)
    try:
        if enable:
            self.bright_controller.enable()
        else:
            self.bright_controller.opt_out()
    except (BrightConfigError, BrightError) as exc:
        fry_error(self, "Bright", str(exc))
        status = self.bright_controller.refresh_status()
        self.bright_panel.update_status(status)
        self.bright_panel.set_busy(False)
        return
    except Exception as exc:  # pragma: no cover - defensive
        fry_error(self, "Bright", str(exc))
        status = self.bright_controller.refresh_status()
        self.bright_panel.update_status(status)
        self.bright_panel.set_busy(False)
        return

    def _on_confirmed() -> None:
        from miner_GUI.ui.helpers import rewards as rewards_helpers
        status = self.bright_controller.refresh_status()
        self.bright_panel.update_status(status)
        self._set_partner_approval("bright", status.enabled)
        self._bright_enabled = bool(getattr(status, "enabled", False))
        rewards_helpers.update_rewards_hint(self)
        self.bright_panel.set_busy(False)
        logger.info("Bright approval confirmed by service (enable=%s)", enable)

    def _on_timeout() -> None:
        from miner_GUI.ui.helpers import rewards as rewards_helpers
        status = self.bright_controller.refresh_status()
        self.bright_panel.update_status(status)
        self._bright_enabled = bool(getattr(status, "enabled", False))
        rewards_helpers.update_rewards_hint(self)
        self.bright_panel.set_busy(False)
        logger.warning("Bright approval poll timed out (expected enable=%s)", enable)
        fry_error(self, "Bright", "Service did not confirm the approval change in time.")

    self._poll_gui_config_approval(
        partner="bright",
        expected=enable,
        on_confirmed=_on_confirmed,
        on_timeout=_on_timeout,
    )
