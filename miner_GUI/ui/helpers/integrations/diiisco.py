"""Diiisco integration helper functions"""

from typing import TYPE_CHECKING

from PySide6 import QtCore

from config_profile import MINER_CODE
from miner_GUI.services.diiisco import DiiiscoController
from miner_GUI.ui.helpers.docker_progress import poll_docker_operation, show_docker_progress
from miner_GUI.utils.gui import fry_error
from miner_GUI.utils.ops_queue_client import (
    enqueue_start_docker_container,
    enqueue_stop_docker_container,
)

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow


def _get_diiisco_panel(self: "MainWindow"):
    """Get the Diiisco panel, either from live_panel (RdnPanel) or standalone."""
    # Check if live_panel is an RdnPanel with Diiisco support
    live_panel = getattr(self, 'live_panel', None)
    if live_panel is not None and hasattr(live_panel, 'diiisco_refresh_clicked'):
        return live_panel
    # Fall back to standalone diiisco_panel
    return getattr(self, 'diiisco_panel', None)


def _is_rdn_live_panel(panel) -> bool:
    """Check if panel is an RdnPanel (LiveData version)."""
    return panel is not None and hasattr(panel, 'diiisco_refresh_clicked')


import os
import shutil


def _find_docker() -> str:
    """Return the path to docker.exe, searching common Windows locations first."""
    if os.name == "nt":
        for candidate in [
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            r"C:\Program Files\Docker\Docker\docker.exe",
        ]:
            if os.path.exists(candidate):
                return candidate
    docker = shutil.which("docker")
    return docker if docker else "docker"


def _check_docker_available() -> tuple[bool, str]:
    """Pre-flight: read current reward week's status JSON and check for docker status."""
    try:
        import datetime
        from miner_GUI.utils.status_week import load_status_week_for_date

        today = datetime.datetime.utcnow().date()
        week_doc = load_status_week_for_date(today)
        if isinstance(week_doc, dict):
            docker_status = week_doc.get("docker")
            if docker_status is True:
                return (True, "")
            elif docker_status is False:
                # Fall back to direct check rather than trusting stale JSON
                pass
            else:
                pass
    except Exception:
        pass
    # Fallback: direct subprocess check
    try:
        import os
        import subprocess
        import traceback
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [_find_docker(), "--version"],
            capture_output=True,
            timeout=5,
            creationflags=creationflags,
        )
        if result.returncode == 0:
            return (True, "")
        else:
            with open(r"C:\tmp\docker_debug_diiisco.log", "a", encoding="utf-8") as f:
                f.write(f"docker --version rc={result.returncode} stderr={result.stderr!r}\n")
    except Exception as exc:
        with open(r"C:\tmp\docker_debug_diiisco.log", "a", encoding="utf-8") as f:
            f.write(f"docker --version exc={exc}\n{traceback.format_exc()}\n")
        pass
    return (False, "Unable to determine Docker status.\nPlease check that the miner service is running.")


def init_diiisco_support(self: "MainWindow") -> None:
    """Initialize Diiisco controller for RDN miners."""
    if MINER_CODE != "RDN" or not self._allow_diiisco:
        return

    panel = _get_diiisco_panel(self)
    if panel is None:
        return

    # Pre-flight: check docker availability from weekly JSON
    docker_available, docker_msg = _check_docker_available()
    if not docker_available:
        if _is_rdn_live_panel(panel):
            panel.set_diiisco_unavailable(docker_msg)
        else:
            panel.show_status_message(docker_msg)
        return

    try:
        self.diiisco_controller = DiiiscoController()
    except Exception as exc:
        if _is_rdn_live_panel(panel):
            panel.set_diiisco_unavailable(f"Diiisco unavailable: {exc}")
        else:
            panel.show_status_message(f"Diiisco unavailable: {exc}")
        return

    # Connect refresh signal (toggle removed — all integrations are forced ON)
    if _is_rdn_live_panel(panel):
        panel.diiisco_refresh_clicked.connect(lambda: refresh_diiisco_status(self))
    else:
        panel.refresh_clicked.connect(lambda: refresh_diiisco_status(self))

    QtCore.QTimer.singleShot(0, lambda: bootstrap_diiisco_status(self))


def bootstrap_diiisco_status(self: "MainWindow") -> None:
    """Bootstrap initial Diiisco status check"""
    if not self.diiisco_controller:
        return
    panel = _get_diiisco_panel(self)
    if panel is None:
        return

    is_rdn = _is_rdn_live_panel(panel)

    if is_rdn:
        panel.set_diiisco_busy(True)
    else:
        panel.set_busy(True)

    try:
        status = self.diiisco_controller.refresh_status()
        if is_rdn:
            panel.update_diiisco_status(status)
        else:
            panel.update_status(status)

        # Auto-start: if configured but not running, start automatically
        if status.configured and not status.running:
            try:
                enqueue_start_docker_container("diiisco-node")
            except Exception:
                pass
    except Exception as exc:
        if is_rdn:
            panel.set_diiisco_unavailable(f"Diiisco error: {exc}")
        else:
            panel.show_status_message(f"Diiisco error: {exc}")
        return
    finally:
        if is_rdn:
            panel.set_diiisco_busy(False)
        else:
            panel.set_busy(False)

    start_diiisco_timer(self)


def start_diiisco_timer(self: "MainWindow") -> None:
    """Start periodic Diiisco status refresh timer"""
    if not self.diiisco_controller:
        return
    if self._diiisco_timer:
        try:
            self._diiisco_timer.stop()
        except Exception:
            pass
    self._diiisco_timer = QtCore.QTimer(self)
    self._diiisco_timer.setInterval(5000)  # TESTING: was 30000 (30s)
    self._diiisco_timer.timeout.connect(lambda: refresh_diiisco_status(self))
    self._diiisco_timer.start()


def refresh_diiisco_status(self: "MainWindow") -> None:
    """Refresh Diiisco status display"""
    if not self.diiisco_controller:
        return
    panel = _get_diiisco_panel(self)
    if panel is None:
        return

    is_rdn = _is_rdn_live_panel(panel)

    if is_rdn:
        panel.set_diiisco_busy(True)
    else:
        panel.set_busy(True)

    try:
        status = self.diiisco_controller.refresh_status()

        # Watchdog: if configured but not running, auto-restart
        if status.configured and not status.running and not status.pending:
            try:
                enqueue_start_docker_container("diiisco-node")
            except Exception:
                pass

        if is_rdn:
            panel.update_diiisco_status(status)
        else:
            panel.update_status(status)
    except Exception as exc:
        if is_rdn:
            panel.set_diiisco_unavailable(f"Diiisco error: {exc}")
        else:
            panel.show_status_message(f"Diiisco error: {exc}")
    finally:
        if is_rdn:
            panel.set_diiisco_busy(False)
        else:
            panel.set_busy(False)


def _revert_toggle(panel, is_rdn: bool, state: bool) -> None:
    """Programmatically set the Diiisco toggle without emitting signals."""
    if is_rdn:
        panel.diiisco_panel.set_toggle_state(state)
    else:
        panel._suspend_toggle = True
        try:
            panel._toggle.setChecked(state)
        finally:
            panel._suspend_toggle = False


def handle_diiisco_toggle(self: "MainWindow", enabled: bool) -> None:
    """Handle Diiisco toggle switch changes via Docker ops queue.

    Enable:  write_config → start_docker_container("diiisco-node")
    Disable: stop_docker_container("diiisco-node") → write_config

    Shows a progress dialog during enable (Docker pull can take minutes).
    Reverts the toggle on timeout or error.
    """
    if not self.diiisco_controller:
        return
    panel = _get_diiisco_panel(self)
    if panel is None:
        return

    is_rdn = _is_rdn_live_panel(panel)

    if is_rdn:
        panel.set_diiisco_busy(True)
    else:
        panel.set_busy(True)

    # Show progress dialog for enable (Docker pull can be slow on first run)
    progress = show_docker_progress(self, "Diiisco") if enabled else None

    request_id = None
    try:
        if enabled:
            request_id = _activate_diiisco(self)
        else:
            _deactivate_diiisco(self)
    except Exception as exc:
        if progress:
            progress.close()
        # Revert in-memory state so periodic refresh doesn't flip the toggle back
        self.diiisco_controller.config.enabled = not enabled
        fry_error(self, "Diiisco", str(exc))
        try:
            status = self.diiisco_controller.refresh_status()
            if is_rdn:
                panel.update_diiisco_status(status)
            else:
                panel.update_status(status)
        except Exception:
            pass
        if is_rdn:
            panel.set_diiisco_busy(False)
        else:
            panel.set_busy(False)
        return

    # --- helpers shared by both approval and docker-ops callbacks ----------

    def _finish_ok() -> None:
        status = self.diiisco_controller.refresh_status()
        if is_rdn:
            panel.update_diiisco_status(status)
            panel.set_diiisco_busy(False)
        else:
            panel.update_status(status)
            panel.set_busy(False)

    def _finish_error(message: str) -> None:
        self.diiisco_controller.config.enabled = not enabled
        status = self.diiisco_controller.refresh_status()
        if is_rdn:
            panel.update_diiisco_status(status)
            panel.set_diiisco_busy(False)
        else:
            panel.update_status(status)
            panel.set_busy(False)
        _revert_toggle(panel, is_rdn, not enabled)
        fry_error(self, "Diiisco", message)

    # --- enable path: poll service progress/done files ---------------------

    if enabled and progress and request_id:
        def _on_docker_ready(_done_data: dict) -> None:
            _finish_ok()

        def _on_docker_error(message: str) -> None:
            _finish_error(message)

        def _on_docker_timeout() -> None:
            _finish_error("Container did not start within the expected time.")

        self._diiisco_ready_timer = poll_docker_operation(
            parent=self,
            request_id=request_id,
            progress=progress,
            partner_name="Diiisco",
            on_ready=_on_docker_ready,
            on_error=_on_docker_error,
            on_timeout=_on_docker_timeout,
        )

        # Approval poll runs in parallel — just records the approval flag
        def _on_confirmed() -> None:
            self._set_partner_approval("diiisco", enabled)

        def _on_approval_timeout() -> None:
            # Docker poller is the primary flow; if approval also times out
            # just log it — docker poller will handle UI cleanup.
            pass

        self._poll_gui_config_approval(
            partner="diiisco",
            expected=enabled,
            on_confirmed=_on_confirmed,
            on_timeout=_on_approval_timeout,
            max_seconds=900,
        )
        return

    # --- disable path: approval poll only ----------------------------------

    def _on_confirmed() -> None:
        self._set_partner_approval("diiisco", enabled)
        _finish_ok()

    def _on_timeout() -> None:
        _finish_error("Service did not confirm the approval change in time.")

    self._poll_gui_config_approval(
        partner="diiisco",
        expected=enabled,
        on_confirmed=_on_confirmed,
        on_timeout=_on_timeout,
        max_seconds=900,
    )


def _activate_diiisco(self: "MainWindow") -> str:
    """Enable flow: write_config → start container (fire-and-forget).

    Returns:
        The ops-queue request ID for progress polling.
    """
    # Step 1: Persist config (diiisco enabled: true)
    self.diiisco_controller.enable()

    # Step 2: Start container via IPC ops_queue (non-blocking; progress
    #         is polled by poll_docker_operation in the toggle handler)
    ok, request_id = enqueue_start_docker_container("diiisco-node", wait_for_result=False)
    if not ok:
        raise RuntimeError(f"Failed to enqueue Diiisco container start: {request_id}")
    return request_id


def _deactivate_diiisco(self: "MainWindow") -> None:
    """Disable flow: stop container → write_config."""
    # Step 1: Stop container via IPC ops_queue
    ok, msg = enqueue_stop_docker_container("diiisco-node")
    if not ok:
        raise RuntimeError(f"Failed to stop Diiisco container: {msg}")

    # Step 2: Persist config (diiisco enabled: false)
    self.diiisco_controller.disable()
