"""Honeygain integration helper functions"""

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets
import shiboken6

import logging
from config_profile import MINER_CODE

logger = logging.getLogger(__name__)
from miner_GUI.services.honeygain import (
    HoneygainController,
    HoneygainConfigError,
    HoneygainError,
)
from miner_GUI.utils.gui import fry_error
from miner_GUI.ui.helpers import rewards as rewards_helpers

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow


def init_honeygain_support(self: "MainWindow") -> None:
    """Initialize Honeygain controller and periodic refresh."""
    if MINER_CODE != "BM" or not self.honeygain_panel or not self._allow_honeygain:
        return
    # Reuse existing controller if already created to avoid duplicate bootstraps
    already_initialized = getattr(self, "honeygain_controller", None) is not None
    if not already_initialized:
        try:
            self.honeygain_controller = HoneygainController()
        except HoneygainConfigError as exc:
            self.honeygain_panel.show_status_message(str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            self.honeygain_panel.show_status_message(f"Honeygain unavailable: {exc}")
            return

    assert self.honeygain_controller is not None
    if not self.honeygain_controller.sdk_loaded:
        self.honeygain_panel.show_status_message("Honeygain SDK library not found in SDK folder.")
        return

    # Reconnect signals (safe even if already connected - we disconnect first)
    try:
        self.honeygain_panel.refresh_clicked.disconnect()
    except Exception:
        pass
    try:
        self.honeygain_panel.toggle_changed.disconnect()
    except Exception:
        pass
    self.honeygain_panel.refresh_clicked.connect(lambda: refresh_honeygain_status(self))
    self.honeygain_panel.toggle_changed.connect(lambda enabled: handle_honeygain_toggle(self, enabled))

    if not already_initialized:
        QtCore.QTimer.singleShot(0, lambda: bootstrap_honeygain_status(self))
    else:
        # Panel was rebuilt - ensure timer is restarted
        start_honeygain_timer(self)


def bootstrap_honeygain_status(self: "MainWindow") -> None:
    """Bootstrap initial Honeygain status check"""
    if not self.honeygain_controller or not self.honeygain_panel:
        return
    self.honeygain_panel.set_busy(True)
    try:
        # Only refresh status at startup - don't auto-start Honeygain
        # User must explicitly enable it via the toggle
        # Note: Don't call _apply_partner_opt_in here - respect the user's
        # explicit preference stored in honeygain.json config
        status = self.honeygain_controller.refresh_status()
        self.honeygain_panel.update_status(status)
        self._honeygain_enabled = bool(getattr(status, "enabled", False))
    except Exception as exc:  # pragma: no cover - defensive
        self.honeygain_panel.show_status_message(f"Honeygain error: {exc}")
        return
    finally:
        self.honeygain_panel.set_busy(False)
    start_honeygain_timer(self)
    rewards_helpers.update_rewards_hint(self)


def start_honeygain_timer(self: "MainWindow") -> None:
    """Start periodic Honeygain status refresh timer"""
    if not self.honeygain_controller:
        return
    if self._honeygain_timer:
        try:
            self._honeygain_timer.stop()
        except Exception:
            pass
    self._honeygain_timer = QtCore.QTimer(self)
    interval = 5000  # TESTING: match main GUI refresh rate (was max(10000, poll_interval_ms))
    self._honeygain_timer.setInterval(interval)
    self._honeygain_timer.timeout.connect(lambda: refresh_honeygain_status(self))
    self._honeygain_timer.start()


def stop_honeygain_timer(self: "MainWindow") -> None:
    """Stop Honeygain status refresh timer"""
    try:
        if self._honeygain_timer:
            self._honeygain_timer.stop()
    except Exception:
        pass
    self._honeygain_timer = None


def refresh_honeygain_status(self: "MainWindow") -> None:
    """Refresh Honeygain status display"""
    panel = self.honeygain_panel
    if not self.honeygain_controller or not panel:
        return
    if not shiboken6.isValid(panel):
        stop_honeygain_timer(self)
        return
    panel.set_busy(True)
    try:
        status = self.honeygain_controller.refresh_status()
        panel.update_status(status)
        # Update JSON file when Honeygain is offline
        if not status.running:
            self.honeygain_controller.mark_offline()
    except Exception as exc:  # pragma: no cover - defensive
        panel.show_status_message(f"Honeygain error: {exc}")
    finally:
        panel.set_busy(False)


def handle_honeygain_toggle(self: "MainWindow", enabled: bool) -> None:
    """Handle Honeygain toggle switch changes"""
    logger.debug(
        "Honeygain toggle requested enabled=%s panel_enabled=%s controller=%s",
        enabled,
        bool(self.honeygain_panel and self.honeygain_panel._toggle.isEnabled()),
        bool(self.honeygain_controller),
    )
    current_state = bool(self._honeygain_enabled) if self._honeygain_enabled is not None else False
    if self.honeygain_panel:
        panel = self.honeygain_panel
        panel._suspend_toggle = True
        panel._toggle.setChecked(current_state)
        panel._suspend_toggle = False
    # If enabling, check if consent is needed
    if enabled:
        # Check current opt-in status
        needs_consent = True
        if self.honeygain_controller:
            try:
                status = self.honeygain_controller.refresh_status()
                # If already opted in, no need to show dialog again
                if status.opted_in is True:
                    needs_consent = False
            except Exception:
                pass
        
        # Show consent dialog only if not already opted in
        if needs_consent and not show_honeygain_consent_dialog(self):
            logger.info("Honeygain consent declined, reverting toggle.")
            panel = self.honeygain_panel
            assert panel is not None
            panel._suspend_toggle = True
            panel._toggle.setChecked(False)
            panel._suspend_toggle = False
            return
    else:
        # Confirm disable
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Confirm Disable",
            f"Are you sure you want to disable Honeygain Sharing?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            logger.info("Honeygain disable cancelled, reverting toggle.")
            panel = self.honeygain_panel
            assert panel is not None
            panel._suspend_toggle = True
            panel._toggle.setChecked(True)
            panel._suspend_toggle = False
            return
    apply_honeygain_state(self, enable=enabled)


def show_honeygain_consent_dialog(self: "MainWindow") -> bool:
    """Show Honeygain consent disclaimer and return True if user agrees."""
    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle("Honeygain Bandwidth Sharing Consent")
    dialog.setModal(True)
    
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(16)
    
    # Disclaimer text
    disclaimer = QtWidgets.QLabel(
        "By enabling Honeygain, you agree to share your unused internet bandwidth "
        "with the Honeygain network. This allows Honeygain to use your connection "
        "for legitimate business purposes.<br><br>"
        "Your participation is voluntary and you can opt-out at any time by toggling "
        "this setting off.<br><br>"
        "Please review the <a href='https://www.honeygain.com/terms-of-use/'>Honeygain Terms of Service</a> "
        "and <a href='https://www.honeygain.com/privacy-policy/'>Privacy Policy</a> for more information."
    )
    disclaimer.setWordWrap(True)
    disclaimer.setTextFormat(QtCore.Qt.TextFormat.RichText)
    disclaimer.setOpenExternalLinks(True)
    disclaimer.setStyleSheet("a { color: #4ea3ff; }")
    layout.addWidget(disclaimer)
    
    # Buttons
    button_layout = QtWidgets.QHBoxLayout()
    button_layout.addStretch(1)
    
    decline_btn = QtWidgets.QPushButton("Decline")
    decline_btn.clicked.connect(dialog.reject)
    button_layout.addWidget(decline_btn)
    
    agree_btn = QtWidgets.QPushButton("I Agree")
    agree_btn.setDefault(True)
    agree_btn.clicked.connect(dialog.accept)
    button_layout.addWidget(agree_btn)
    
    layout.addLayout(button_layout)
    
    if getattr(self, "_screen_size_pref", "") == "mobile":
        dialog.setMinimumWidth(320)
        dialog.resize(420, dialog.sizeHint().height())
    else:
        dialog.setMinimumWidth(400)
        dialog.resize(500, dialog.sizeHint().height())
    
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


def apply_honeygain_state(self: "MainWindow", enable: bool) -> None:
    """Apply Honeygain enable/disable state.

    After the controller action (which enqueues a config write via ops_queue),
    we poll gui_config.enc until the service confirms the new approval state
    before updating the toggle.  The panel stays busy during polling.
    """
    if not self.honeygain_controller or not self.honeygain_panel:
        logger.warning("Honeygain state change skipped (controller or panel missing).")
        return
    logger.debug("Applying Honeygain state enable=%s", enable)
    self.honeygain_panel.set_busy(True)
    try:
        if enable:
            self.honeygain_controller.enable()
        else:
            self.honeygain_controller.opt_out()
    except (HoneygainConfigError, HoneygainError) as exc:
        fry_error(self, "Honeygain", str(exc))
        status = self.honeygain_controller.refresh_status()
        self.honeygain_panel.update_status(status)
        self.honeygain_panel.set_busy(False)
        return
    except Exception as exc:  # pragma: no cover - defensive
        fry_error(self, "Honeygain", str(exc))
        status = self.honeygain_controller.refresh_status()
        self.honeygain_panel.update_status(status)
        self.honeygain_panel.set_busy(False)
        return

    def _on_confirmed() -> None:
        status = self.honeygain_controller.refresh_status()
        self.honeygain_panel.update_status(status)
        self._set_partner_approval("honeygain", status.enabled)
        self._honeygain_enabled = bool(getattr(status, "enabled", False))
        rewards_helpers.update_rewards_hint(self)
        self.honeygain_panel.set_busy(False)
        logger.info("Honeygain approval confirmed by service (enable=%s)", enable)

    def _on_timeout() -> None:
        status = self.honeygain_controller.refresh_status()
        self.honeygain_panel.update_status(status)
        self._honeygain_enabled = bool(getattr(status, "enabled", False))
        rewards_helpers.update_rewards_hint(self)
        self.honeygain_panel.set_busy(False)
        logger.warning("Honeygain approval poll timed out (expected enable=%s)", enable)
        fry_error(self, "Honeygain", "Service did not confirm the approval change in time.")

    self._poll_gui_config_approval(
        partner="honeygain",
        expected=enable,
        on_confirmed=_on_confirmed,
        on_timeout=_on_timeout,
    )
