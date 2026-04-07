"""Space Acres integration helper functions.

Handles the Space Acres farming lifecycle for SDN miners:
  1. configure_spaceacres (pick SSD + size)
  2. write_config + reload_config (enable toggle)
  3. setup_spaceacres_firewall (first time only)
  4. start / stop via ops queue (backward-compatible container ops)
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from PySide6 import QtCore

from config_profile import MINER_CODE
from miner_GUI.services.space_acres import SpaceAcresController
from miner_GUI.ui.helpers.docker_progress import poll_docker_operation, show_docker_progress
from miner_GUI.utils.gui import fry_error
from miner_GUI.utils.ops_queue_client import (
    enqueue_configure_spaceacres,
    enqueue_setup_spaceacres_firewall,
    enqueue_start_docker_container,
    enqueue_stop_docker_container,
)

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow


def _get_space_acres_panel(self: "MainWindow"):
    """Get the Space Acres panel, either from live_panel (SdnPanel) or standalone."""
    live_panel = getattr(self, 'live_panel', None)
    if live_panel is not None and hasattr(live_panel, 'space_acres_refresh_clicked'):
        return live_panel
    return getattr(self, 'space_acres_panel', None)


def _is_sdn_live_panel(panel) -> bool:
    """Check if panel is an SdnPanel (LiveData version)."""
    return panel is not None and hasattr(panel, 'space_acres_refresh_clicked')


def init_space_acres_support(self: "MainWindow") -> None:
    """Initialize Space Acres controller for SDN miners."""
    if MINER_CODE != "SDN" or not self._allow_space_acres:
        return

    panel = _get_space_acres_panel(self)
    if panel is None:
        return

    try:
        self.space_acres_controller = SpaceAcresController()
    except Exception as exc:
        if _is_sdn_live_panel(panel):
            panel.set_space_acres_unavailable(f"Space Acres unavailable: {exc}")
        else:
            panel.show_status_message(f"Space Acres unavailable: {exc}")
        return

    # Load available_ssds and spaceacres_config from gui_config.enc
    _load_ssd_config_from_gui_config(self, panel)

    # Connect signals based on panel type
    if _is_sdn_live_panel(panel):
        panel.space_acres_refresh_clicked.connect(lambda: refresh_space_acres_status(self))
        panel.space_acres_toggle_changed.connect(lambda enabled: handle_space_acres_toggle(self, enabled))
        panel.space_acres_configure_requested.connect(
            lambda path, size: handle_configure_request(self, path, size)
        )
    else:
        panel.refresh_clicked.connect(lambda: refresh_space_acres_status(self))
        panel.toggle_changed.connect(lambda enabled: handle_space_acres_toggle(self, enabled))

    QtCore.QTimer.singleShot(0, lambda: bootstrap_space_acres_status(self))


def _load_ssd_config_from_gui_config(self: "MainWindow", panel) -> None:
    """Read available_ssds and spaceacres_config from gui_config.enc and push to panel.

    NOTE: This may run BEFORE _load_partner_approvals() caches the Fernet key,
    so we derive our own Fernet instance if needed.
    """
    if not _is_sdn_live_panel(panel):
        return

    try:
        from miner_GUI.utils.data import data_dir_gui, log_step
        from miner_GUI.config import app_dir
        from pathlib import Path
        import json
        import base64

        # Locate gui_config.enc
        candidates = []
        try:
            candidates.append(data_dir_gui() / "config")
        except Exception:
            pass
        try:
            candidates.append(app_dir() / "config")
        except Exception:
            pass
        candidates.append(Path.cwd() / "config")

        target = None
        for base in candidates:
            cand = base / "gui_config.enc"
            if cand.exists():
                target = cand
                break

        if target is None:
            return

        payload = json.loads(target.read_text(encoding="utf-8"))
        token = payload.get("data")
        if not isinstance(token, str):
            return

        # Use cached Fernet if available, otherwise derive our own
        fernet = getattr(self, "_gui_config_fernet", None)
        if fernet is None:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            from cryptography.fernet import Fernet

            salt = b"gui_config_salt_v1"
            key_material = b"gui_config_encryption_key_v1"
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000)
            fernet = Fernet(base64.urlsafe_b64encode(kdf.derive(key_material)))
            # Cache it on MainWindow so _load_partner_approvals won't re-derive
            self._gui_config_fernet = fernet

        data = json.loads(fernet.decrypt(token.encode("utf-8")).decode("utf-8"))

        # Push available_ssds to panel
        available_ssds = data.get("available_ssds", [])
        if isinstance(available_ssds, list) and available_ssds:
            panel.set_space_acres_ssds(available_ssds)
            log_step("ssd_config_loaded", {"count": len(available_ssds)})

        # Push existing config to panel
        spaceacres_config = data.get("spaceacres_config", {})
        if isinstance(spaceacres_config, dict) and spaceacres_config:
            panel.set_space_acres_config(spaceacres_config)

    except Exception as exc:
        try:
            from miner_GUI.utils.data import log_step
            log_step("load_ssd_config_error", {"error": str(exc), "type": type(exc).__name__})
        except Exception:
            pass


def bootstrap_space_acres_status(self: "MainWindow") -> None:
    """Bootstrap initial Space Acres status check."""
    if not self.space_acres_controller:
        return
    panel = _get_space_acres_panel(self)
    if panel is None:
        return

    is_sdn = _is_sdn_live_panel(panel)

    if is_sdn:
        panel.set_space_acres_busy(True)
    else:
        panel.set_busy(True)

    try:
        status = self.space_acres_controller.refresh_status()
        if is_sdn:
            panel.update_space_acres_status(status)
        else:
            panel.update_status(status)
    except Exception as exc:
        if is_sdn:
            panel.set_space_acres_unavailable(f"Space Acres error: {exc}")
        else:
            panel.show_status_message(f"Space Acres error: {exc}")
        return
    finally:
        if is_sdn:
            panel.set_space_acres_busy(False)
        else:
            panel.set_busy(False)

    start_space_acres_timer(self)


def start_space_acres_timer(self: "MainWindow") -> None:
    """Start periodic Space Acres status refresh timer."""
    if not self.space_acres_controller:
        return
    if self._space_acres_timer:
        try:
            self._space_acres_timer.stop()
        except Exception:
            pass
    self._space_acres_timer = QtCore.QTimer(self)
    self._space_acres_timer.setInterval(5000)  # TESTING: was 30000 (30s)
    self._space_acres_timer.timeout.connect(lambda: refresh_space_acres_status(self))
    self._space_acres_timer.start()


def refresh_space_acres_status(self: "MainWindow") -> None:
    """Refresh Space Acres status display and SSD list."""
    if not self.space_acres_controller:
        return
    panel = _get_space_acres_panel(self)
    if panel is None:
        return

    is_sdn = _is_sdn_live_panel(panel)

    # Refresh SSD list from gui_config.enc (service rescans periodically)
    if is_sdn:
        _refresh_ssd_list(self, panel)

    if is_sdn:
        panel.set_space_acres_busy(True)
    else:
        panel.set_busy(True)

    try:
        status = self.space_acres_controller.refresh_status()
        if is_sdn:
            panel.update_space_acres_status(status)
        else:
            panel.update_status(status)
    except Exception as exc:
        if is_sdn:
            panel.set_space_acres_unavailable(f"Space Acres error: {exc}")
        else:
            panel.show_status_message(f"Space Acres error: {exc}")
    finally:
        if is_sdn:
            panel.set_space_acres_busy(False)
        else:
            panel.set_busy(False)


def _refresh_ssd_list(self: "MainWindow", panel) -> None:
    """Re-read available_ssds from gui_config.enc and update the SSD combo if changed."""
    try:
        from miner_GUI.utils.data import data_dir_gui
        from miner_GUI.config import app_dir
        from pathlib import Path
        import json

        candidates = []
        try:
            candidates.append(data_dir_gui() / "config")
        except Exception:
            pass
        try:
            candidates.append(app_dir() / "config")
        except Exception:
            pass
        candidates.append(Path.cwd() / "config")

        target = None
        for base in candidates:
            cand = base / "gui_config.enc"
            if cand.exists():
                target = cand
                break

        if target is None:
            return

        fernet = getattr(self, "_gui_config_fernet", None)
        if fernet is None:
            return

        payload = json.loads(target.read_text(encoding="utf-8"))
        token = payload.get("data")
        if not isinstance(token, str):
            return

        data = json.loads(fernet.decrypt(token.encode("utf-8")).decode("utf-8"))
        new_ssds = data.get("available_ssds", [])
        if not isinstance(new_ssds, list):
            return

        # Only update if the list actually changed (avoid resetting user selection)
        old_ssds = getattr(panel.space_acres_panel, "_available_ssds", [])
        if new_ssds != old_ssds:
            panel.set_space_acres_ssds(new_ssds)

    except Exception:
        pass


def handle_configure_request(self: "MainWindow", farm_path: str, farm_size: str) -> None:
    """Handle the 'Save Configuration' button — send configure_spaceacres IPC op."""
    panel = _get_space_acres_panel(self)
    if panel is None:
        return

    is_sdn = _is_sdn_live_panel(panel)
    if is_sdn:
        panel.set_space_acres_busy(True)
    else:
        panel.set_busy(True)

    try:
        ok, msg = enqueue_configure_spaceacres(farm_path, farm_size)
        if not ok:
            raise RuntimeError(f"Configuration failed: {msg}")

        if is_sdn:
            panel.space_acres_panel.show_status_message(
                f"Configuration saved: {farm_path} ({farm_size})"
            )
        else:
            panel.show_status_message(f"Configuration saved: {farm_path} ({farm_size})")
    except Exception as exc:
        fry_error(self, "Space Acres", str(exc))
    finally:
        if is_sdn:
            panel.set_space_acres_busy(False)
        else:
            panel.set_busy(False)


def _revert_toggle(panel, is_sdn: bool, state: bool) -> None:
    """Programmatically set the Space Acres toggle without emitting signals."""
    if is_sdn:
        panel.space_acres_panel.set_toggle_state(state)
    else:
        panel._suspend_toggle = True
        try:
            panel._toggle.setChecked(state)
        finally:
            panel._suspend_toggle = False


def handle_space_acres_toggle(self: "MainWindow", enabled: bool) -> None:
    """Handle Space Acres toggle switch changes via ops queue.

    Enable:  configure_spaceacres → write_config → reload → firewall → start
    Disable: stop → write_config → reload

    Shows a progress dialog during enable (first start may take time).
    Reverts the toggle on timeout or error.
    """
    if not self.space_acres_controller:
        return
    panel = _get_space_acres_panel(self)
    if panel is None:
        return

    is_sdn = _is_sdn_live_panel(panel)

    if is_sdn:
        panel.set_space_acres_busy(True)
    else:
        panel.set_busy(True)

    # Show progress dialog for enable (first start may take time)
    progress = show_docker_progress(self, "Space Acres") if enabled else None

    request_id = None
    try:
        if enabled:
            request_id = _activate_space_acres(self, panel, is_sdn)
        else:
            _deactivate_space_acres(self)
    except Exception as exc:
        if progress:
            progress.close()
        # Revert in-memory state so periodic refresh doesn't flip the toggle back
        self.space_acres_controller.config.enabled = not enabled
        fry_error(self, "Space Acres", str(exc))
        try:
            status = self.space_acres_controller.refresh_status()
            if is_sdn:
                panel.update_space_acres_status(status)
            else:
                panel.update_status(status)
        except Exception:
            pass
        if is_sdn:
            panel.set_space_acres_busy(False)
        else:
            panel.set_busy(False)
        return

    # --- helpers shared by both approval and ops callbacks -----------------

    def _finish_ok() -> None:
        status = self.space_acres_controller.refresh_status()
        if is_sdn:
            panel.update_space_acres_status(status)
            panel.set_space_acres_busy(False)
        else:
            panel.update_status(status)
            panel.set_busy(False)

    def _finish_error(message: str) -> None:
        self.space_acres_controller.config.enabled = not enabled
        status = self.space_acres_controller.refresh_status()
        if is_sdn:
            panel.update_space_acres_status(status)
            panel.set_space_acres_busy(False)
        else:
            panel.update_status(status)
            panel.set_busy(False)
        _revert_toggle(panel, is_sdn, not enabled)
        fry_error(self, "Space Acres", message)

    # --- enable path: poll service progress/done files ---------------------

    if enabled and progress and request_id:
        def _on_start_ready(done_data: dict) -> None:
            # Process is up. If the node is already syncing, the periodic
            # refresh timer will pick it up and show the sync progress bar.
            # _finish_ok() does a refresh_status() which reads spaceacres_sync.json.
            initial = done_data.get("initial_status", "")
            if initial == "syncing":
                from miner_GUI.utils.data import log_step
                log_step("space_acres_start_done_syncing", {
                    "initial_status": initial,
                })
            _finish_ok()

        def _on_start_error(message: str) -> None:
            _finish_error(message)

        def _on_start_timeout() -> None:
            _finish_error("Space Acres did not start within the expected time.")

        self._space_acres_ready_timer = poll_docker_operation(
            parent=self,
            request_id=request_id,
            progress=progress,
            partner_name="Space Acres",
            on_ready=_on_start_ready,
            on_error=_on_start_error,
            on_timeout=_on_start_timeout,
        )

        # Approval poll runs in parallel — just records the approval flag
        def _on_confirmed() -> None:
            self._set_partner_approval("space_acres", enabled)

        def _on_approval_timeout() -> None:
            # Start poller is the primary flow; if approval also times out
            # just log it — start poller will handle UI cleanup.
            pass

        self._poll_gui_config_approval(
            partner="space_acres",
            expected=enabled,
            on_confirmed=_on_confirmed,
            on_timeout=_on_approval_timeout,
            max_seconds=900,
        )
        return

    # --- disable path: approval poll only ----------------------------------

    def _on_confirmed() -> None:
        self._set_partner_approval("space_acres", enabled)
        _finish_ok()

    def _on_timeout() -> None:
        _finish_error("Service did not confirm the approval change in time.")

    self._poll_gui_config_approval(
        partner="space_acres",
        expected=enabled,
        on_confirmed=_on_confirmed,
        on_timeout=_on_timeout,
        max_seconds=900,
    )


def _activate_space_acres(self: "MainWindow", panel, is_sdn: bool) -> str:
    """Enable flow: configure → write_config → firewall (parallel) → start.

    Returns:
        The ops-queue request ID for progress polling.
    """
    # Step 1: Send farm configuration (if SdnPanel, read from UI; otherwise skip)
    if is_sdn:
        farm_path, farm_size = panel.get_space_acres_farm_config()
        if farm_path and farm_size:
            ok, msg = enqueue_configure_spaceacres(farm_path, farm_size)
            if not ok:
                raise RuntimeError(f"Failed to configure Space Acres: {msg}")

    # Step 2: Persist config (spaceacres_enabled: true)
    self.space_acres_controller.enable()

    # Step 3: Firewall (can fire while config write is being processed)
    enqueue_setup_spaceacres_firewall(wait_for_result=False)

    # Step 4: Start Space Acres (non-blocking; progress is polled
    #         by poll_docker_operation in the toggle handler).
    #         Uses backward-compatible container op name.
    ok, request_id = enqueue_start_docker_container("spaceacres-node", wait_for_result=False)
    if not ok:
        raise RuntimeError(f"Failed to enqueue Space Acres start: {request_id}")
    return request_id


def _deactivate_space_acres(self: "MainWindow") -> None:
    """Disable flow: stop → write_config."""
    # Step 1: Stop Space Acres (backward-compatible container op name)
    ok, msg = enqueue_stop_docker_container("spaceacres-node")
    if not ok:
        raise RuntimeError(f"Failed to stop Space Acres: {msg}")

    # Step 2: Persist config (spaceacres_enabled: false)
    self.space_acres_controller.disable()
