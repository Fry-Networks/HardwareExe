"""Mysterium Network integration helper functions"""

from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtWidgets
import shiboken6

from config_profile import MINER_CODE
from miner_GUI.services.mysterium import (
    MysteriumController, MysteriumStatus,
    _MysteriumStatusWorker, _MysteriumStartWorker,
)
from miner_GUI.utils.gui import fry_error
from miner_GUI.ui.helpers import rewards as rewards_helpers

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow

RETRY_DELAYS_MS = [5_000, 10_000, 30_000, 60_000, 300_000]
CACHE_FRESH_AFTER_SECONDS = 60


def init_mysterium_support(self: "MainWindow") -> None:
    """Initialize Mysterium controller and periodic refresh"""
    if MINER_CODE != "BM" or not self.mysterium_panel or not self._allow_mysterium:
        return
    # Reuse existing controller if already created to avoid duplicate bootstraps
    already_initialized = getattr(self, "mysterium_controller", None) is not None
    if not already_initialized:
        try:
            self.mysterium_controller = MysteriumController()
        except Exception as exc:
            self.mysterium_panel.show_status_message(f"Mysterium unavailable: {exc}")
            return

    # Reconnect signals (safe even if already connected - we disconnect first)
    try:
        self.mysterium_panel.refresh_clicked.disconnect()
    except Exception:
        pass
    try:
        self.mysterium_panel.toggle_changed.disconnect()
    except Exception:
        pass
    try:
        self.mysterium_panel.warning_clicked.disconnect()
    except Exception:
        pass
    try:
        self.mysterium_panel.diagnose_clicked.disconnect()
    except Exception:
        pass
    self.mysterium_panel.refresh_clicked.connect(lambda: _on_manual_refresh_clicked(self))
    # toggle_changed not connected — all integrations are forced ON
    self.mysterium_panel.warning_clicked.connect(lambda: show_mysterium_warning(self))
    try:
        self.mysterium_panel.diagnose_clicked.connect(lambda: diagnose_mysterium(self))
    except Exception:
        pass

    if not already_initialized:
        QtCore.QTimer.singleShot(0, lambda: bootstrap_mysterium_status(self))
    else:
        # Panel was rebuilt - ensure timer is restarted
        start_mysterium_timer(self)


def bootstrap_mysterium_status(self: "MainWindow") -> None:
    """Bootstrap initial Mysterium status check — non-blocking."""
    if not self.mysterium_controller or not self.mysterium_panel:
        return
    if not shiboken6.isValid(self.mysterium_panel):
        return
    _ensure_retry_state(self)

    # Paint cached status immediately (zero-blocking GUI startup)
    cached = self.mysterium_controller.load_cached_status()
    if cached is not None:
        status, age = cached
        self.mysterium_panel.update_status(status)
        update_mysterium_warning(self, status)
        if age > CACHE_FRESH_AFTER_SECONDS:
            self.mysterium_panel.show_status_message(
                f"Mysterium: last seen {int(age)}s ago, refreshing..."
            )
    else:
        self.mysterium_panel.show_status_message("Mysterium: checking...")

    self.mysterium_panel.set_busy(True)
    _dispatch_status_worker(self)
    start_mysterium_timer(self)
    rewards_helpers.update_rewards_hint(self)


def deferred_mysterium_auto_enable(self: "MainWindow") -> None:
    """Complete Mysterium setup after GUI is initialized (runs in background)."""
    if not self.mysterium_controller or not self.mysterium_panel:
        return
    try:
        # Check if still needs enabling
        if bool(self._mysterium_enabled):
            return
        # Trigger enable flow (will show progress dialog)
        apply_mysterium_state(self, enable=True)
    except Exception as exc:
        if self.mysterium_panel:
            self.mysterium_panel.show_status_message(f"Auto-enable failed: {exc}")


def start_mysterium_timer(self: "MainWindow") -> None:
    """Start periodic Mysterium status refresh timer"""
    if not self.mysterium_controller:
        return
    if self._mysterium_timer:
        try:
            self._mysterium_timer.stop()
        except Exception:
            pass
    self._mysterium_timer = QtCore.QTimer(self)
    self._mysterium_timer.setInterval(5000)  # TESTING: was 30000 (30s)
    self._mysterium_timer.timeout.connect(lambda: refresh_mysterium_status(self))
    self._mysterium_timer.start()


def stop_mysterium_timer(self: "MainWindow") -> None:
    """Stop Mysterium status refresh timer"""
    try:
        if self._mysterium_timer:
            self._mysterium_timer.stop()
    except Exception:
        pass
    self._mysterium_timer = None


# --------------- async dispatch helpers ---------------


def _ensure_retry_state(self: "MainWindow") -> None:
    """Lazy-init retry tracking on MainWindow."""
    if not hasattr(self, "_mysterium_retry_index"):
        self._mysterium_retry_index = 0
    if not hasattr(self, "_mysterium_retry_timer"):
        self._mysterium_retry_timer = None
    if not hasattr(self, "_mysterium_status_worker"):
        self._mysterium_status_worker = None
    if not hasattr(self, "_mysterium_start_worker"):
        self._mysterium_start_worker = None


def _reset_mysterium_retry(self: "MainWindow") -> None:
    self._mysterium_retry_index = 0
    t = getattr(self, "_mysterium_retry_timer", None)
    if t is not None:
        try:
            t.stop()
        except Exception:
            pass
        self._mysterium_retry_timer = None


def _schedule_mysterium_retry(self: "MainWindow") -> None:
    idx = min(self._mysterium_retry_index, len(RETRY_DELAYS_MS) - 1)
    delay = RETRY_DELAYS_MS[idx]
    self._mysterium_retry_index += 1
    self._mysterium_retry_timer = QtCore.QTimer(self)
    self._mysterium_retry_timer.setSingleShot(True)
    self._mysterium_retry_timer.setInterval(delay)
    self._mysterium_retry_timer.timeout.connect(lambda: refresh_mysterium_status(self))
    self._mysterium_retry_timer.start()


def _dispatch_status_worker(self: "MainWindow") -> bool:
    """Spawn _MysteriumStatusWorker. Skip if one already running."""
    existing = getattr(self, "_mysterium_status_worker", None)
    if existing is not None and existing.isRunning():
        return False
    worker = _MysteriumStatusWorker(self.mysterium_controller, parent=self)
    self._mysterium_status_worker = worker
    worker.status_ready.connect(
        lambda status: _on_status_ready(self, status),
        QtCore.Qt.ConnectionType.QueuedConnection,
    )
    worker.status_error.connect(
        lambda err: _on_status_error(self, err),
        QtCore.Qt.ConnectionType.QueuedConnection,
    )
    worker.finished.connect(worker.deleteLater)
    worker.start()
    QtCore.QTimer.singleShot(
        MysteriumController.STATUS_WORKER_HARD_TIMEOUT_MS,
        lambda w=worker: _enforce_worker_timeout(self, w, "status"),
    )
    return True


def _dispatch_start_worker(self: "MainWindow") -> None:
    """Spawn _MysteriumStartWorker. Skip if one already running."""
    existing = getattr(self, "_mysterium_start_worker", None)
    if existing is not None and existing.isRunning():
        return
    worker = _MysteriumStartWorker(self.mysterium_controller, parent=self)
    self._mysterium_start_worker = worker
    worker.start_done.connect(
        lambda ok, msg: _on_start_done(self, ok, msg),
        QtCore.Qt.ConnectionType.QueuedConnection,
    )
    worker.finished.connect(worker.deleteLater)
    worker.start()
    QtCore.QTimer.singleShot(
        MysteriumController.START_WORKER_HARD_TIMEOUT_MS,
        lambda w=worker: _enforce_worker_timeout(self, w, "start"),
    )


def _enforce_worker_timeout(self: "MainWindow", worker, kind: str) -> None:
    """If worker still running after hard ceiling, terminate + treat as error."""
    if worker is None:
        return
    try:
        if worker.isRunning():
            worker.terminate()
            worker.wait(2000)
            if kind == "status":
                self._mysterium_status_worker = None
                _on_status_error(self, "timeout (hard ceiling)")
            else:
                self._mysterium_start_worker = None
                _on_start_done(self, False, "start timeout (hard ceiling)")
    except Exception:
        pass


def _on_status_ready(self: "MainWindow", status: MysteriumStatus) -> None:
    self._mysterium_status_worker = None  # clear ref before any dispatch
    if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
        return
    try:
        self.mysterium_controller.save_cached_status(status)
    except Exception:
        pass
    # Align enabled flag to user preference
    try:
        status.enabled = bool(self._mysterium_enabled) if self._mysterium_enabled is not None else False
    except Exception:
        pass
    self.mysterium_panel.update_status(status)
    update_mysterium_warning(self, status)
    _reset_mysterium_retry(self)
    # Watchdog: if enabled but not running, dispatch start worker
    if bool(self._mysterium_enabled) and not status.running:
        _dispatch_start_worker(self)
    self.mysterium_panel.set_busy(False)
    rewards_helpers.update_rewards_hint(self)


def _on_status_error(self: "MainWindow", err: str) -> None:
    self._mysterium_status_worker = None  # clear ref before any dispatch
    if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
        return
    self.mysterium_panel.show_status_message(f"Mysterium status check failed: {err}")
    self.mysterium_panel.set_busy(False)
    _schedule_mysterium_retry(self)


def _on_start_done(self: "MainWindow", ok: bool, msg: str) -> None:
    self._mysterium_start_worker = None  # clear ref before any dispatch
    if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
        return
    if not ok:
        self.mysterium_panel.show_status_message(f"Mysterium start failed: {msg}")
        _schedule_mysterium_retry(self)
    else:
        _dispatch_status_worker(self)


def _on_manual_refresh_clicked(self: "MainWindow") -> None:
    """Wired to panel.refresh_clicked. Resets backoff and dispatches immediately."""
    _ensure_retry_state(self)
    _reset_mysterium_retry(self)
    if self.mysterium_panel and shiboken6.isValid(self.mysterium_panel):
        self.mysterium_panel.set_busy(True)
    _dispatch_status_worker(self)


def refresh_mysterium_status(self: "MainWindow") -> None:
    """Refresh Mysterium status display — non-blocking dispatch."""
    panel = self.mysterium_panel
    if not self.mysterium_controller or not panel:
        return
    if not shiboken6.isValid(panel):
        stop_mysterium_timer(self)
        return
    # If user has not enabled Mysterium, show disabled state without network calls
    if not bool(self._mysterium_enabled):
        status = MysteriumStatus(
            enabled=False,
            running=False,
            warning=None,
            last_error=None,
            port_ok=False,
            api_ok=False,
        )
        panel.update_status(status)
        update_mysterium_warning(self, status)
        return
    _ensure_retry_state(self)
    _dispatch_status_worker(self)


def handle_mysterium_toggle(self: "MainWindow", enabled: bool) -> None:
    """Handle Mysterium toggle switch changes"""
    current_state = bool(self._mysterium_enabled) if self._mysterium_enabled is not None else False
    if self.mysterium_panel:
        panel = self.mysterium_panel
        panel._suspend_toggle = True
        panel._toggle.setChecked(current_state)
        panel._suspend_toggle = False
    
    # If enabling, check consent first
    if enabled:
        needs_consent = True
        if self.mysterium_controller:
            try:
                status = self.mysterium_controller.refresh_status()
                if status.consent_given:
                    needs_consent = False
            except Exception:
                pass
        
        if needs_consent and not show_mysterium_consent_dialog(self):
            if self.mysterium_panel:
                panel = self.mysterium_panel
                panel._suspend_toggle = True
                panel._toggle.setChecked(False)
                panel._suspend_toggle = False
            return
    else:
        # Confirm disable
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Confirm Disable",
            f"Are you sure you want to disable Mysterium Sharing?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            if self.mysterium_panel:
                panel = self.mysterium_panel
                panel._suspend_toggle = True
                panel._toggle.setChecked(True)
                panel._suspend_toggle = False
            return
    apply_mysterium_state(self, enable=enabled)


def show_mysterium_consent_dialog(self: "MainWindow") -> bool:
    """Show Mysterium consent disclaimer and return True if user agrees."""
    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle("Mysterium Network Sharing Consent")
    dialog.setModal(True)
    
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(16)
    
    # Disclaimer text
    disclaimer = QtWidgets.QLabel(
        "By enabling Mysterium, you agree to share your unused internet bandwidth "
        "with the Mysterium Network. This allows others to route their internet traffic "
        "through your connection to get more fVPN tokens.<br><br>"
        "Your participation is voluntary and you can opt-out at any time by toggling "
        "this setting off.<br><br>"
        "Please review the <a href='https://mysterium.network/terms-conditions/'>Mysterium Terms &amp; Conditions</a> "
        "and <a href='https://mysterium.network/privacy-policy/'>Privacy Policy</a> for more information."
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
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


class _MysteriumSetupWorker(QtCore.QThread):
    """Runs blocking Mysterium enable sequence off the GUI thread."""
    progress_text = QtCore.Signal(str)
    finished = QtCore.Signal(bool, str)  # (success, error_message)

    def __init__(self, controller, payout: str, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._payout = payout

    def run(self):
        try:
            self.progress_text.emit("Verifying firewall and installing service...")
            self._controller.ensure_installed(payout_addr=self._payout)

            self.progress_text.emit("Starting Mysterium service...")
            self._controller.start()

            self.progress_text.emit("Configuring identity and payout...")
            if self._payout:
                try:
                    ident = self._controller._current_identity()
                    if ident:
                        self._controller._set_beneficiary(ident, self._payout)
                except Exception:
                    pass

            self.progress_text.emit("Starting WireGuard service...")
            self._controller._start_wireguard_service()

            self.progress_text.emit("Starting provider services...")
            try:
                self._controller.start_additional_services()
            except Exception:
                pass

            self.progress_text.emit("Accepting terms and verifying...")
            try:
                status = self._controller.refresh_status()
                if not status.consent_given:
                    self._controller.accept_terms()
            except Exception:
                pass

            self.finished.emit(True, "")
        except Exception as exc:
            self.finished.emit(False, str(exc))


def apply_mysterium_state(self: "MainWindow", enable: bool) -> None:
    """Apply Mysterium enable/disable state.

    After the controller action (which enqueues a config write via ops_queue),
    we poll gui_config.enc until the service confirms the new approval state
    before updating the toggle.  The panel stays busy during polling.
    """
    if not self.mysterium_controller or not self.mysterium_panel:
        return

    # Show progress dialog during enable
    progress: Optional[QtWidgets.QProgressDialog] = None
    if enable:
        progress = QtWidgets.QProgressDialog(
            "Initializing Mysterium service. This may take a moment while we verify connectivity...",
            "",
            0,
            0,
            self,
        )
        progress.setWindowTitle("Mysterium Setup")
        progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QtWidgets.QApplication.processEvents()

    self.mysterium_panel.set_busy(True)

    if enable:
        # Read payout address from encrypted config; require presence
        try:
            from miner_GUI.utils.data import read_mysterium_secrets
            payout, _, _ = read_mysterium_secrets()
        except Exception:
            payout = None
        if not payout:
            if progress:
                progress.close()
            fry_error(self, "Mysterium", "MYST_PAYOUT_ADDR missing in miner_config.enc. Please install a valid config.")
            self.mysterium_panel.set_busy(False)
            return

        # Run blocking setup in background thread (avoids GUI freeze)
        worker = _MysteriumSetupWorker(self.mysterium_controller, payout, parent=self)
        if progress and shiboken6.isValid(progress):
            worker.progress_text.connect(
                lambda text: progress.setLabelText(text) if shiboken6.isValid(progress) else None,
                QtCore.Qt.ConnectionType.QueuedConnection,
            )

        def _on_worker_done(success: bool, error: str) -> None:
            # --- ADDED 2026-04-24: shiboken6 guard ---
            if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
                if progress and shiboken6.isValid(progress):
                    progress.close()
                return
            # --- END ADDED 2026-04-24 ---
            if progress and shiboken6.isValid(progress):
                progress.close()
            if not success:
                fry_error(self, "Mysterium", error)
                try:
                    status = self.mysterium_controller.refresh_status()
                    self._mysterium_enabled = False
                    try:
                        status.enabled = False
                    except Exception:
                        pass
                    self.mysterium_panel.update_status(status)
                    update_mysterium_warning(self, status)
                    try:
                        panel = self.mysterium_panel
                        panel._suspend_toggle = True
                        panel._toggle.setChecked(False)
                        panel._suspend_toggle = False
                    except Exception:
                        pass
                except Exception:
                    pass
                self.mysterium_panel.set_busy(False)
                return
            # Success — start approval polling (defined below)
            _start_polling()

        worker.finished.connect(_on_worker_done, QtCore.Qt.ConnectionType.QueuedConnection)
        self._mysterium_setup_worker = worker  # prevent GC
        worker.start()
    else:
        try:
            self.mysterium_controller.stop()
        except Exception as exc:
            if progress:
                progress.close()
            fry_error(self, "Mysterium", str(exc))
            self.mysterium_panel.set_busy(False)
            return
        if progress:
            progress.close()
        # Disable path falls through to polling below

    def _on_confirmed() -> None:
        # --- ADDED 2026-04-24: shiboken6 guard ---
        if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
            return
        # --- END ADDED 2026-04-24 ---
        status = self.mysterium_controller.refresh_status()
        self._mysterium_enabled = bool(status.running) if enable else False
        try:
            status.enabled = bool(self._mysterium_enabled)
            if not enable:
                status.running = False
        except Exception:
            pass
        self.mysterium_panel.update_status(status)
        self._set_partner_approval("mysterium", status.enabled)
        update_mysterium_warning(self, status)
        if not enable:
            try:
                panel = self.mysterium_panel
                panel._suspend_toggle = True
                panel._toggle.setChecked(False)
                panel._suspend_toggle = False
            except Exception:
                pass
        self.mysterium_panel.set_busy(False)
        rewards_helpers.update_rewards_hint(self)
        logger.info("Mysterium approval confirmed by service (enable=%s)", enable)

    def _on_timeout() -> None:
        # --- ADDED 2026-04-24: shiboken6 guard ---
        if not self.mysterium_panel or not shiboken6.isValid(self.mysterium_panel):
            return
        # --- END ADDED 2026-04-24 ---
        status = self.mysterium_controller.refresh_status()
        self._mysterium_enabled = bool(status.running) if enable else False
        try:
            status.enabled = bool(self._mysterium_enabled)
            if not enable:
                status.running = False
        except Exception:
            pass
        self.mysterium_panel.update_status(status)
        update_mysterium_warning(self, status)
        if not enable:
            try:
                panel = self.mysterium_panel
                panel._suspend_toggle = True
                panel._toggle.setChecked(False)
                panel._suspend_toggle = False
            except Exception:
                pass
        self.mysterium_panel.set_busy(False)
        rewards_helpers.update_rewards_hint(self)
        logger.warning("Mysterium approval poll timed out (expected enable=%s)", enable)
        fry_error(self, "Mysterium", "Service did not confirm the approval change in time.")

    def _start_polling() -> None:
        self._poll_gui_config_approval(
            partner="mysterium",
            expected=enable,
            on_confirmed=_on_confirmed,
            on_timeout=_on_timeout,
        )

    # For enable path, polling is started by _on_worker_done after background work completes.
    # For disable path, start polling immediately since stop() already ran above.
    if not enable:
        _start_polling()


def update_mysterium_warning(self: "MainWindow", status: Optional[MysteriumStatus]) -> None:
    """Update Mysterium warning messages based on status"""
    if not status:
        self._mysterium_warning = None
        return
    
    # If disabled, show clean disabled message only
    if not status.enabled:
        self._mysterium_warning = None
        return
    
    warnings = []
    if status.warning:
        warnings.append(status.warning)
    if status.last_error:
        warnings.append(status.last_error)
    
    # Only show port/API errors if enabled but not running
    if status.enabled and not status.running:
        if not status.port_ok:
            warnings.append("Mysterium API port is not reachable.")
        if not status.api_ok:
            warnings.append("Mysterium API did not respond.")
    
    self._mysterium_warning = "\n".join(warnings) if warnings else None
    
    # Update JSON file when Mysterium is offline
    if self.mysterium_controller and not status.running:
        self.mysterium_controller.mark_offline()


def show_mysterium_warning(self: "MainWindow") -> None:
    """Show Mysterium warning dialog"""
    message = self._mysterium_warning or "No warnings detected."
    QtWidgets.QMessageBox.warning(self, "Mysterium", message)


def diagnose_mysterium(self: "MainWindow") -> None:
    """Run and display Mysterium diagnostics"""
    if not self.mysterium_controller:
        QtWidgets.QMessageBox.information(self, "Mysterium", "Mysterium controller not initialized.")
        return
    try:
        if self.mysterium_panel:
            self.mysterium_panel.set_busy(True)
    except Exception:
        pass
    try:
        report = self.mysterium_controller.diagnose()
        env = report.get("env", {})
        pc = report.get("port_check", {})
        hh = report.get("http_health", {})
        cs = report.get("cli_status", {})
        ss = report.get("service_status", {})

        def yn(b):
            return "✓" if b else "✗"

        lines = []
        lines.append("═══ ENVIRONMENT ═══")
        lines.append(f"Port: {env.get('port')}")
        myst_bin = env.get('myst_bin')
        if myst_bin:
            lines.append(f"Binary: {myst_bin}")
        else:
            lines.append("Binary: not found")
        
        lines.append("")
        lines.append("═══ CONNECTIVITY ═══")
        lines.append(f"{yn(pc.get('ok'))} Port {env.get('port')} reachable")
        if pc.get('error'):
            lines.append(f"  Error: {pc.get('error')}")
        
        lines.append(f"{yn(hh.get('ok'))} HTTP /healthcheck responds")
        if hh.get('status'):
            lines.append(f"  HTTP Status: {hh.get('status')}")
        if hh.get('error'):
            lines.append(f"  Error: {hh.get('error')}")
        
        lines.append("")
        lines.append("═══ SERVICE STATUS ═══")
        lines.append(f"{yn(ss.get('ok'))} Windows service check (exit code: {ss.get('code')})")
        
        # Parse service output for meaningful info
        service_out = str(ss.get('out', ''))
        if 'Version:' in service_out:
            # Extract version line
            for line in service_out.split('\n'):
                if 'Version:' in line or 'Build info:' in line:
                    lines.append(f"  {line.strip()}")
        
        # Show service errors if they exist and are meaningful
        service_err = str(ss.get('err', '')).strip()
        if service_err and 'config' not in service_err.lower():
            # Skip config errors (they're usually harmless warnings)
            lines.append(f"  Service output: {service_err[:200]}")
        
        # CLI status is less useful but include it compactly
        if cs.get('code') != 3:  # Don't show if it's just "command not found"
            lines.append("")
            lines.append(f"CLI status check: {yn(cs.get('ok'))} (exit code: {cs.get('code')})")
            if cs.get('err') and 'No help topic' not in str(cs.get('err')):
                lines.append(f"  {str(cs.get('err'))[:200]}")

        msg = "\n".join(lines)
        QtWidgets.QMessageBox.information(self, "Mysterium Diagnostics", msg)
    except Exception as exc:
        QtWidgets.QMessageBox.warning(self, "Mysterium Diagnostics", str(exc))
    finally:
        try:
            if self.mysterium_panel:
                self.mysterium_panel.set_busy(False)
        except Exception:
            pass
