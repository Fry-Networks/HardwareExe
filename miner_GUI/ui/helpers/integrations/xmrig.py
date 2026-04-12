"""XMRig integration helper functions.

Always-on mining: no toggle, auto-start, watchdog auto-restart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore

from config_profile import MINER_CODE
from miner_GUI.services.xmrig import XMRigController
from miner_GUI.utils.gui import fry_error

if TYPE_CHECKING:
    from miner_GUI.ui.main_window import MainWindow


def _get_xmrig_panel(self: "MainWindow"):
    """Get the XMRig panel, either from live_panel (SvnPanel) or standalone."""
    live_panel = getattr(self, 'live_panel', None)
    if live_panel is not None and hasattr(live_panel, 'xmrig_refresh_clicked'):
        return live_panel
    return getattr(self, 'xmrig_panel', None)


def _is_svn_live_panel(panel) -> bool:
    """Check if panel is an SvnPanel (LiveData version)."""
    return panel is not None and hasattr(panel, 'xmrig_refresh_clicked')


def init_xmrig_support(self: "MainWindow") -> None:
    """Initialize XMRig controller for SVN miners. Auto-starts mining."""
    if MINER_CODE != "SVN" or not self._allow_xmrig:
        return

    panel = _get_xmrig_panel(self)
    if panel is None:
        return

    # No Docker pre-flight — XMRig is a local binary
    try:
        self.xmrig_controller = XMRigController()
    except Exception as exc:
        msg = f"XMRig unavailable: {exc}"
        if _is_svn_live_panel(panel):
            panel.set_xmrig_unavailable(msg)
        else:
            panel.show_status_message(msg)
        return

    if not self.xmrig_controller.binary_available:
        msg = "XMRig binary not found.\nAwaiting installation by the miner service."
        if _is_svn_live_panel(panel):
            panel.set_xmrig_unavailable(msg)
        else:
            panel.show_status_message(msg)
        return

    # Connect signals based on panel type
    if _is_svn_live_panel(panel):
        panel.xmrig_refresh_clicked.connect(lambda: refresh_xmrig_status(self))
    else:
        panel.refresh_clicked.connect(lambda: refresh_xmrig_status(self))

    QtCore.QTimer.singleShot(0, lambda: bootstrap_xmrig_status(self))


def bootstrap_xmrig_status(self: "MainWindow") -> None:
    """Bootstrap initial XMRig status check and auto-start."""
    if not self.xmrig_controller:
        return
    panel = _get_xmrig_panel(self)
    if panel is None:
        return

    is_svn = _is_svn_live_panel(panel)

    if is_svn:
        panel.set_xmrig_busy(True)
    else:
        panel.set_busy(True)

    try:
        status = self.xmrig_controller.refresh_status()

        if is_svn:
            panel.update_xmrig_status(status)
            panel.set_xmrig_busy(False)
        else:
            panel.update_status(status)
            panel.set_busy(False)

        # Auto-start: if configured but not running, start mining
        if status.configured and not status.running:
            self.xmrig_controller.start()
            # Refresh again after short delay to show updated state
            QtCore.QTimer.singleShot(3000, lambda: refresh_xmrig_status(self))

    except Exception as exc:
        msg = f"Status check failed: {exc}"
        if is_svn:
            panel.set_xmrig_busy(False)
        else:
            panel.show_status_message(msg)
            panel.set_busy(False)

    start_xmrig_timer(self)


def start_xmrig_timer(self: "MainWindow") -> None:
    """Start periodic XMRig status polling."""
    if self._xmrig_timer is not None:
        return

    self._xmrig_timer = QtCore.QTimer(self)
    self._xmrig_timer.timeout.connect(lambda: refresh_xmrig_status(self))
    self._xmrig_timer.start(5000)


def refresh_xmrig_status(self: "MainWindow") -> None:
    """Poll XMRig status and update panel. Includes watchdog auto-restart."""
    if not self.xmrig_controller:
        return
    panel = _get_xmrig_panel(self)
    if panel is None:
        return

    is_svn = _is_svn_live_panel(panel)

    try:
        status = self.xmrig_controller.refresh_status()

        if is_svn:
            panel.update_xmrig_status(status)
        else:
            panel.update_status(status)

        # Watchdog: if configured but not running, auto-restart
        if status.configured and not status.running and not status.pending:
            self.xmrig_controller.start()

    except Exception:
        pass
