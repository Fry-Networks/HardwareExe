"""Main window for the miner GUI application."""

import sys
import os
import base64

from PySide6 import QtWidgets, QtCore, QtGui
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# Build-time default for BM sharing mode if no environment override is present.
# Set this before packaging to bake in a default ("all", "honeygain", "bright", "none").
BM_SHARING_MODE_DEFAULT = "all"

# Pending message shown when miner is not fully configured
PENDING_MESSAGE = (
    "⏳ Waiting for miner to be fully configured...\n\n"
    "This tool will be available once your device is online, "
    "MAC address is registered, and data is flowing."
)
try:
    import shiboken6  # type: ignore
except Exception:  # pragma: no cover
    shiboken6 = None  # type: ignore
import logging
import json
import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

# Import our modular components
from config_profile import (DISPLAY_NAME, VERSION, MINER_CODE, GROUP)
from miner_GUI.config import ( miner_icon_path,image_path, HAVE_SD, HAVE_SERIAL)
from miner_GUI.utils.data import read_miner_key, log_step, data_dir_gui, read_ui_prefs
from miner_GUI.utils.gui import apply_fry_theme_to_dialog
from miner_GUI.utils.device_config import (
    get_saved_serial_port, get_saved_baud_rate, get_saved_microphone,
    save_serial_settings, save_microphone_settings
)
from .widgets.charts import HourlyBar, Rolling7Bar
from .widgets.honeygain_panel import HoneygainPanel
from .widgets.bright_panel import BrightPanel
from .widgets.mysterium_panel import MysteriumPanel
from .widgets.space_acres_panel import SpaceAcresPanel
from .widgets.presearch_panel import PresearchPanel
from .widgets.diiisco_panel import DiiiscoPanel
from .widgets.xmrig_panel import XMRigPanel
from miner_GUI.LiveData.satellite import SatellitePanel
from miner_GUI.LiveData.geiger import GeigerPanel
from .history.data_history import DataHistoryWidget
from .history.rewards_history import RewardsHistoryWidget
from miner_GUI.services.honeygain import HoneygainController
from miner_GUI.services.bright import BrightController
from miner_GUI.services.mysterium import MysteriumController
from miner_GUI.services.space_acres import SpaceAcresController
from miner_GUI.services.presearch import PresearchController
from miner_GUI.services.diiisco import DiiiscoController
from miner_GUI.services.xmrig import XMRigController
from miner_GUI.ui.helpers.integrations import bright as bright_helpers
from miner_GUI.ui.helpers.integrations import diiisco as diiisco_helpers
from miner_GUI.ui.helpers.integrations import honeygain as honeygain_helpers
from miner_GUI.ui.helpers.integrations import mysterium as mysterium_helpers
from miner_GUI.ui.helpers.integrations import mysterium_catchup
from miner_GUI.ui.helpers.integrations import presearch as presearch_helpers
from miner_GUI.ui.helpers.integrations import space_acres as space_acres_helpers
from miner_GUI.ui.helpers.integrations import xmrig as xmrig_helpers
from miner_GUI.ui.helpers import rewards as rewards_helpers
from miner_GUI.ui.helpers import pod_badge as pod_badge_helpers
from miner_GUI.ui.helpers import network as network_helpers
from miner_GUI.ui.helpers import measurement_display
from miner_GUI.utils.csv_reader import read_last_line_for_sensor, parse_float, parse_int

# Import FryNetworks theme
try:
    from miner_GUI.tools.theme import Theme
except ImportError:
    Theme = None

# Import external dependencies
try:
    from miner_GUI.tools.banner import TopBanner
except ImportError:
    TopBanner = None

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None  # type: ignore

logger = logging.getLogger(__name__)

# Import LiveData panels
try:
    from LiveData import load_live_panel
    HAVE_LIVEDATA = True
except ImportError:
    load_live_panel = None
    HAVE_LIVEDATA = False


class MainWindow(QtWidgets.QWidget):
    """Main window for the miner GUI application."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize state variables
        # Live data polling timer (replaces legacy worker thread)
        self._live_poll_timer: Optional[QtCore.QTimer] = None
        # Rewards/MAC status refresh timer (checks weekly status file periodically)
        self._rewards_refresh_timer: Optional[QtCore.QTimer] = None
        self._tray = None
        self._trayNotified = False
        self.activeNetworkName = None
        self.activeMacAddress = None
        self._persistedMacValue = None
        self._partner_approvals: Dict[str, Any] = {}
        self._partner_approvals_applied: set[str] = set()
        self._honeygain_enabled: Optional[bool] = None
        self._bright_enabled: Optional[bool] = None
        self._mysterium_enabled: Optional[bool] = None
        self._prunedOldServiceBinaries = False
        self._downloadedUpdatePath: str = ''
        self._serviceStatusRefreshScheduled = False
        self._mysterium_warning: Optional[str] = None
        self._bright_bootstrapped_once: bool = False
        self._last_pod_ok: Optional[bool] = None
        self._last_pod_error: Optional[str] = None
        self._latest_measurements: Optional[Dict[str, Any]] = None
        self._last_measurement_timestamp: Optional[str] = None
        self._has_received_live_data: bool = False  # Set True once we receive valid live data
        self._has_received_any_status: bool = False  # Set True once any tool receives a status update
        self.live_panel = None
        self.space_acres_panel = None
        self.presearch_panel = None
        self.diiisco_panel = None

        self.service_manager = None
        # Type annotation for live_panel (can be SatellitePanel, GeigerPanel, BandwidthPanel, DecibelPanel, or None)
        self.live_panel: Optional[Any] = None
        self.honeygain_panel: Optional[HoneygainPanel] = None
        self.honeygain_controller: Optional[HoneygainController] = None
        self._honeygain_timer: Optional[QtCore.QTimer] = None
        self.bright_panel: Optional[BrightPanel] = None
        self.bright_controller: Optional[BrightController] = None
        self._bright_timer: Optional[QtCore.QTimer] = None
        self.mysterium_panel: Optional[MysteriumPanel] = None
        self.mysterium_controller: Optional[MysteriumController] = None
        self._mysterium_timer: Optional[QtCore.QTimer] = None
        self._mac_mismatch: Optional[bool] = None  # None=unknown, False=no mismatch, True=mismatch exists
        self._pol_mismatch: bool = False
        self._verified: Optional[bool] = None  # Read from weekly JSON; gates PoL display
        self._api_available: bool = True  # Tracks API availability from weekly JSON
        
        # SDN integrations (Space Acres)
        self.space_acres_panel: Optional[SpaceAcresPanel] = None
        self.space_acres_controller: Optional[SpaceAcresController] = None
        self._space_acres_timer: Optional[QtCore.QTimer] = None

        # RDN integrations (Presearch, Diiisco)
        self.presearch_panel: Optional[PresearchPanel] = None
        self.presearch_controller: Optional[PresearchController] = None
        self._presearch_timer: Optional[QtCore.QTimer] = None
        self.diiisco_panel: Optional[DiiiscoPanel] = None
        self.diiisco_controller: Optional[DiiiscoController] = None
        self._diiisco_timer: Optional[QtCore.QTimer] = None

        # SVN integrations (XMRig mining)
        self.xmrig_panel: Optional[XMRigPanel] = None
        self.xmrig_controller: Optional[XMRigController] = None
        self._xmrig_timer: Optional[QtCore.QTimer] = None

        # Theme instance (initialized by _apply_fry_theme)
        self._theme: Optional[Any] = None
        
        # Optional UI elements (conditionally created)
        self.conn_status_badge: Optional[QtWidgets.QLabel] = None
        self.conn_today_label: Optional[QtWidgets.QLabel] = None
        self.conn_7day_label: Optional[QtWidgets.QLabel] = None
        self.conn_updated_label: Optional[QtWidgets.QLabel] = None
        self.history_widget: Optional[Any] = None
        self.data_history_widget: Optional[Any] = None
        self.api_warning_banner: Optional[QtWidgets.QWidget] = None
        self.stale_data_banner: Optional[QtWidgets.QWidget] = None

        # Bandwidth sharing mode (BM only): all, honeygain, bright, none
        mode_env = os.getenv("BM_SHARING_MODE")
        build_default = BM_SHARING_MODE_DEFAULT
        self._sharing_mode = (mode_env or build_default or "all").lower()
        if MINER_CODE != "BM":
            self._sharing_mode = "all"
        self._allow_honeygain = MINER_CODE == "BM" and self._sharing_mode in ("all", "honeygain")
        self._allow_bright = MINER_CODE == "BM" and self._sharing_mode in ("all", "bright")
        self._allow_mysterium = MINER_CODE == "BM" and self._sharing_mode in ("all", "mysterium")
        
        # SDN integrations (Space Acres for storage nodes)
        self._allow_space_acres = MINER_CODE == "SDN"

        # RDN integrations (Presearch and Diiisco for rewards decentralization nodes)
        self._allow_presearch = MINER_CODE == "RDN"
        self._allow_diiisco = MINER_CODE == "RDN"

        # SVN integrations (XMRig for storage validation nodes)
        self._allow_xmrig = MINER_CODE == "SVN"

        try:
            log_step("bm_sharing_mode", {"mode": self._sharing_mode})
        except Exception:
            pass
        
        logging.getLogger(__name__).info("About to call _setup_window")
        self._setup_window()
        logging.getLogger(__name__).info("_setup_window completed")
        
        logging.getLogger(__name__).info("About to call _create_ui")
        self._create_ui()
        logging.getLogger(__name__).info("_create_ui completed")

        # Post-UI setup: layouts, signals, theme, tray, and initial loads
        logging.getLogger(__name__).info("About to call _setup_layouts")
        self._setup_layouts()
        logging.getLogger(__name__).info("_setup_layouts completed")

        logging.getLogger(__name__).info("About to call _connect_signals")
        self._connect_signals()
        logging.getLogger(__name__).info("_connect_signals completed")

        # Apply FryNetworks black theme
        self._apply_fry_theme()
        # Track 1.7: re-disable Honeygain/Web Indexing tabs after stylesheet
        # polish. Synchronous call + deferred calls at 0ms and 500ms to cover
        # all polish timing: immediate, next-iteration, and post-show.
        self._reapply_sharing_tab_disabled_state()
        QtCore.QTimer.singleShot(0, self._reapply_sharing_tab_disabled_state)
        QtCore.QTimer.singleShot(500, self._reapply_sharing_tab_disabled_state)

        # Initialize system tray icon/menu
        self._init_tray()

        # Load initial data
        self._load_miner_key()
        self._populate_device_selectors()
        self._load_partner_approvals()

        # Measurements now read via CSV polling in LiveData/DataHistory; no JSON polling timer needed
        self._load_status_data()

        # Update rewards hint and MAC info (all miners need this for MAC registration display)
        from .helpers.rewards import update_rewards_hint
        update_rewards_hint(self)
        
        # Start periodic refresh of rewards/MAC status (every 2 minutes)
        self._rewards_refresh_timer = QtCore.QTimer(self)
        self._rewards_refresh_timer.setInterval(5000)  # TESTING: was 120000 (2 minutes)
        self._rewards_refresh_timer.timeout.connect(lambda: update_rewards_hint(self))
        self._rewards_refresh_timer.start()
        
        # Start periodic API status check for warning banner (every 30 seconds)
        self._api_status_timer = QtCore.QTimer(self)
        self._api_status_timer.setInterval(5000)  # TESTING: was 30000 (30 seconds)
        self._api_status_timer.timeout.connect(self._check_api_status)
        self._api_status_timer.start()
        # Check immediately on startup
        self._check_api_status()

        # Auto-start live data monitoring
        QtCore.QTimer.singleShot(1000, self._start_live_monitoring)
        
        # Note: Honeygain/Bright/Mysterium support is initialized in _attach_sharing_panels
        # SDN panels (Space Acres) initialized in _attach_sdn_panels
        # RDN panels (Presearch, Diiisco) initialized in _attach_service_node_panels

    def _is_widget_alive(self, widget: Optional[QtWidgets.QWidget]) -> bool:
        """Best-effort guard against using deleted Qt objects."""
        if widget is None:
            return False
        try:
            if shiboken6 and hasattr(shiboken6, "isValid"):
                if not shiboken6.isValid(widget):  # type: ignore[attr-defined]
                    return False
        except Exception:
            # If shiboken6 is unavailable or throws, fall through
            pass
        try:
            widget.metaObject()  # Will raise if underlying C++ object is gone
        except RuntimeError:
            return False
        except Exception:
            pass
        return True

    def apply_pending_state_to_status(self, panel_name: str, status: Any) -> None:
        """Apply pending state to status object before panel display."""
        # Check if the corresponding panel is in pending state
        panel = getattr(self, f"{panel_name}_panel", None)
        if panel and hasattr(panel, "_is_pending") and panel._is_pending:
            # Force pending=True on the status object so it displays pending message
            if hasattr(status, "pending"):
                status.pending = True

    # ---------------- System tray -----------------
    def _init_tray(self) -> None:
        """Create a system tray icon with a context menu for Show/Exit."""
        try:
            if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
                return
            # Build tray icon
            try:
                icon_path = miner_icon_path()
                icon = QtGui.QIcon(str(icon_path)) if icon_path else self.windowIcon()
            except Exception:
                icon = self.windowIcon()

            tray = QtWidgets.QSystemTrayIcon(icon, self)
            tray.setToolTip(f"FRY {DISPLAY_NAME} - v{VERSION}")

            # Context menu
            menu = QtWidgets.QMenu()
            action_show = menu.addAction("Show")
            action_show.triggered.connect(self._restore_from_tray)
            action_exit = menu.addAction("Exit")
            action_exit.setIconVisibleInMenu(False)
            action_exit.triggered.connect(self._exit_app)
            tray.setContextMenu(menu)

            # Double click to restore
            def _on_tray_activated(reason: QtWidgets.QSystemTrayIcon.ActivationReason):
                try:
                    if reason in (
                        QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
                        QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
                    ):
                        self._restore_from_tray()
                except Exception:
                    pass

            tray.activated.connect(_on_tray_activated)
            # Only show tray if icon is valid
            if not icon.isNull():
                tray.show()
            else:
                print("Warning: System tray icon is null; not calling setVisible.")
            self._tray = tray
        except Exception:
            self._tray = None

    def _restore_from_tray(self) -> None:
        """Restore the window from the system tray."""
        try:
            self.showNormal()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def _exit_app(self) -> None:
        """Fully stop background work and exit the application."""
        try:
            self._stop_live_worker()
        except Exception:
            pass
        try:
            if self._tray:
                self._tray.hide()
        except Exception:
            pass
        
        # Stop SDK timers
        try:
            honeygain_helpers.stop_honeygain_timer(self)
        except Exception:
            pass
        try:
            bright_helpers.stop_bright_timer(self)
        except Exception:
            pass
        try:
            mysterium_helpers.stop_mysterium_timer(self)
        except Exception:
            pass
        
        # Properly close SDKs before exit
        try:
            if self.honeygain_controller:
                logger.info("Stopping Honeygain SDK")
                try:
                    self.honeygain_controller.opt_out()
                    self.honeygain_controller.mark_offline()
                except Exception as exc:
                    logger.warning(f"Failed to stop Honeygain: {exc}")
        except Exception as exc:
            logger.warning(f"Failed to close Honeygain SDK: {exc}")
        
        try:
            if self.bright_controller:
                logger.info("Stopping Bright SDK")
                try:
                    self.bright_controller.shutdown()
                    self.bright_controller.mark_offline()
                except Exception as exc:
                    logger.warning(f"Failed to stop Bright: {exc}")
                # Call BrightData.Api.Close() to prevent SDK from keeping app process alive
                if hasattr(self.bright_controller, '_managed') and self.bright_controller._managed:
                    try:
                        self.bright_controller._managed.close()
                    except Exception:
                        pass
        except Exception as exc:
            logger.warning(f"Failed to close Bright SDK: {exc}")
        
        try:
            if self.mysterium_controller:
                logger.info("Stopping Mysterium service")
                try:
                    self.mysterium_controller.stop()
                    self.mysterium_controller.mark_offline()
                except Exception as exc:
                    logger.warning(f"Failed to stop Mysterium: {exc}")
        except Exception as exc:
            logger.warning(f"Failed to close Mysterium SDK: {exc}")
        
        app = QtWidgets.QApplication.instance()
        if app:
            app.quit()
        
    def _setup_window(self) -> None:
        """Set up window properties."""
        full_title = f"FRY {DISPLAY_NAME} - v{VERSION}"
        self.setWindowTitle(full_title)
        self._screen_size_pref = "desktop"
        
        try:
            icon_path = miner_icon_path()
            if icon_path:
                self.setWindowIcon(QtGui.QIcon(str(icon_path)))
        except Exception:
            pass
            
        # Larger default and resizable; let content autoscale with the window
        self.setMinimumSize(1280, 900)
        self._apply_screen_size_pref()

    def _apply_screen_size_pref(self) -> None:
        """Resize/min-size the window based on installer-provided screen_size preference."""
        try:
            prefs = read_ui_prefs()
            choice = str(prefs.get("screen_size", "")).strip().lower()

            # Auto-detect based on primary screen width if not specified
            def _auto_choice() -> str:
                try:
                    screen = QtGui.QGuiApplication.primaryScreen()
                    geom = screen.availableGeometry() if screen else None
                    w = geom.width() if geom else 0
                    if w and w < 800:
                        return "mobile"
                    if w and w < 1100:
                        return "tablet"
                    if w and w < 1450:
                        return "laptop"
                    if w and w < 2000:
                        return "desktop"
                    if w and w >= 2000:
                        return "ultrawide"
                except Exception:
                    pass
                return "desktop"

            if not choice or choice == "auto":
                choice = _auto_choice()

            presets = {
                "mobile": {"min": (320, 480), "target": (480, 820)},
                "tablet": {"min": (680, 760), "target": (900, 980)},
                "laptop": {"min": (1100, 780), "target": (1280, 900)},
                "desktop": {"min": (1280, 900), "target": (1440, 950)},
                "ultrawide": {"min": (1440, 950), "target": (1800, 1000)},
            }

            preset = presets.get(choice)
            if not preset:
                self._screen_size_pref = "desktop"
                return

            self._screen_size_pref = choice

            min_w, min_h = preset["min"]
            target_w, target_h = preset["target"]

            # Clamp target to available screen size
            try:
                screen = QtGui.QGuiApplication.primaryScreen()
                geom = screen.availableGeometry() if screen else None
                if geom:
                    target_w = min(target_w, max(min_w, geom.width()))
                    target_h = min(target_h, max(min_h, geom.height()))
            except Exception:
                pass

            self.setMinimumSize(min_w, min_h)
            self.resize(target_w, target_h)

            # Shorten window title for compact screens
            try:
                if choice in ("mobile", "tablet"):
                    short_title = f"{DISPLAY_NAME} v{VERSION}"
                    if len(short_title) > 32:
                        short_title = short_title[:29] + "..."
                    self.setWindowTitle(short_title)
            except Exception:
                pass
        except Exception:
            pass
        
    def _create_ui(self) -> None:
        """Create the main UI components."""
        logging.getLogger(__name__).info("_create_ui starting")
        
        # Banner
        logging.getLogger(__name__).info("Creating banner")
        self._create_banner()
        logging.getLogger(__name__).info("Banner created")
        
        # API warning banner (initially hidden)
        self._create_api_warning_banner()

        # Stale-data warning banner (initially hidden)
        self._create_stale_data_banner()

        # Input form
        logging.getLogger(__name__).info("Creating input form")
        self._create_input_form()
        logging.getLogger(__name__).info("Input form created")
        
        # Settings section (depends on miner type)
        logging.getLogger(__name__).info("Creating settings section")
        self._create_settings_section()
        logging.getLogger(__name__).info("Settings section created")
        
        # Live data section
        logging.getLogger(__name__).info("About to create live data section")
        self._create_live_data_section()
        logging.getLogger(__name__).info("Live data section created")
        
        # Historical data section
        logging.getLogger(__name__).info("About to create historical data section")
        self._create_historical_data_section()
        logging.getLogger(__name__).info("Historical data section created")
        
        # Status section
        self._create_status_section()
        
    def _create_banner(self) -> None:
        """Create the top banner."""
        title_text = f"FRY {DISPLAY_NAME} - v{VERSION}"
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        if TopBanner:
            try:
                bp = image_path("background.png")
                banner_img = str(bp) if bp and bp.exists() else None
            except Exception:
                banner_img = None
            
            # Reduce height and allow wrapping on mobile
            height = 100 if is_mobile else 120
            # Insert newline before version to allow two-line display when long
            if is_mobile and len(title_text) > 24:
                if " - v" in title_text:
                    title_text = title_text.replace(" - v", "\n v", 1)
            # Hint a smaller font for extra-long names on small screens
            _font_size = 18 if is_mobile else 22
            try:
                self.banner = TopBanner(title_text, banner_img, height=height)
            except Exception:
                self.banner = TopBanner(title_text, banner_img, height=height)
        else:
            # Fallback banner
            self.banner = QtWidgets.QLabel(title_text)
            self.banner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            size = 18 if is_mobile else 24
            pad = 14 if is_mobile else 20
            self.banner.setStyleSheet(f"font-size: {size}px; font-weight: bold; padding: {pad}px;")

    def _create_api_warning_banner(self) -> None:
        """Create the API unavailable warning banner (initially hidden)."""
        self.api_warning_banner = QtWidgets.QFrame()
        self.api_warning_banner.setObjectName("apiWarningBanner")
        
        layout = QtWidgets.QHBoxLayout(self.api_warning_banner)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # Warning icon
        icon_label = QtWidgets.QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)
        
        # Warning message
        message = QtWidgets.QLabel(
            "<b>Hardware API Unavailable</b> — Your miner is still working and collecting data locally. "
            "Reward syncing will resume automatically when the backend API recovers."
        )
        message.setWordWrap(True)
        message.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(message, 1)
        
        # Style the banner with orange/yellow warning colors
        self.api_warning_banner.setStyleSheet("""
            #apiWarningBanner {
                background-color: #FF9800;
                border: 2px solid #F57C00;
                border-radius: 4px;
                color: #000000;
            }
            #apiWarningBanner QLabel {
                background: transparent;
                color: #000000;
            }
        """)
        
        # Initially hidden
        self.api_warning_banner.hide()

    def _create_stale_data_banner(self) -> None:
        """Create the stale-data warning banner (initially hidden)."""
        self.stale_data_banner = QtWidgets.QFrame()
        self.stale_data_banner.setObjectName("staleDataBanner")

        layout = QtWidgets.QHBoxLayout(self.stale_data_banner)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Warning icon
        icon_label = QtWidgets.QLabel("\u26a0\ufe0f")
        icon_label.setStyleSheet("font-size: 24px;")
        layout.addWidget(icon_label)

        # Warning message
        self._stale_data_message = QtWidgets.QLabel(
            "<b>Status Data Is Stale</b> \u2014 The local status file has not been updated in over 15 minutes. "
            "The miner service may need attention."
        )
        self._stale_data_message.setWordWrap(True)
        self._stale_data_message.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(self._stale_data_message, 1)

        self.stale_data_banner.setStyleSheet("""
            #staleDataBanner {
                background-color: #FF9800;
                border: 2px solid #F57C00;
                border-radius: 4px;
                color: #000000;
            }
            #staleDataBanner QLabel {
                background: transparent;
                color: #000000;
            }
        """)

        self.stale_data_banner.hide()

    def _create_input_form(self) -> None:
        """Create the miner key input form."""
        self.keyEdit = QtWidgets.QLineEdit()
        self.keyEdit.setPlaceholderText(f"{MINER_CODE}-[A-Z0-9]{{32}}")
        self.keyEdit.setReadOnly(True)  # Miner key is read-only, set by installer
        
        self.regexHint = QtWidgets.QLabel('')
        self.regexHint.setObjectName("hint")
        
        self.form = QtWidgets.QFormLayout()
        try:
            is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
            self.form.setContentsMargins(6 if is_mobile else 8, 0, 6 if is_mobile else 8, 0)
            self.form.setVerticalSpacing(1 if is_mobile else 2)
        except Exception:
            pass
            
        self.form.addRow("miner_key", self.keyEdit)
        self.form.addRow("", self.regexHint)
        
    def _create_settings_section(self) -> None:
        """Create settings section based on miner type."""
        self.settingsGb = QtWidgets.QGroupBox("Settings")
        if getattr(self, "_screen_size_pref", "") == "mobile":
            self.settingsGb.setStyleSheet(
                """
                QGroupBox {
                    margin-top: 6px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 6px;
                    padding: 0px 2px;
                }
                """
            )
        # Always include network/MAC discovery across all miner types per requirement
        self._create_network_settings()

        # Miner-specific device settings follow
        if GROUP == "Decibel":
            self._create_audio_settings()
        elif GROUP == "Satellite":
            self._create_serial_settings("GNSS Receiver")
        elif GROUP == "Radiation":
            self._create_serial_settings("Geiger Counter")
            
    def _create_network_settings(self) -> None:
        """Create network-related settings."""
        self.networkLabel = QtWidgets.QLabel("Active network")
        self.networkValueLabel = QtWidgets.QLabel("-")
        self.macTitle = QtWidgets.QLabel("MAC")
        self.macValueLabel = QtWidgets.QLabel("-")
        self.macRegisteredTitle = QtWidgets.QLabel("Registered")
        self.macRegisteredValue = QtWidgets.QLabel("-")
        self.macMatchCheck = QtWidgets.QCheckBox("match")
        self.macMatchCheck.setEnabled(False)
        self.macMatchCheck.setVisible(False)
        # Unified registration status label (MAC + Location combined)
        self.registrationStatusLabel = QtWidgets.QLabel("")
        self.registrationStatusLabel.setToolTip("Active MAC matches your registered MAC address.")
        self.registrationStatusIcon = QtWidgets.QLabel()
        self.registrationStatusIcon.setToolTip(self.registrationStatusLabel.toolTip())
        try:
            warn_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning)
            self.registrationStatusIcon.setPixmap(warn_icon.pixmap(18, 18))
        except Exception:
            self.registrationStatusIcon.setText("!")
        self.registrationStatusIcon.setVisible(False)
        self.registrationStatusLabel.setVisible(False)
        # Optional info panel (hidden by default) for richer instructions
        self.macInfoLabel = QtWidgets.QLabel("Tip: If you changed network adapters or PCs, log in to your Fry Networks dashboard and update the MAC for this miner key.")
        self.macInfoLabel.setWordWrap(True)
        self.macInfoLabel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.macInfoLabel.setVisible(False)
        
    def _create_audio_settings(self) -> None:
        """Create audio device settings."""
        self.deviceLabel = QtWidgets.QLabel("Microphone")
        self.deviceCombo = QtWidgets.QComboBox()
        self.deviceCombo.setFixedWidth(360)
        self.deviceHelp = QtWidgets.QLabel("")
        self.btnApplyMic = QtWidgets.QPushButton("Update")
        self.btnApplyMic.setVisible(False)
        
        self._populate_microphones()
        
    def _create_serial_settings(self, device_type: str) -> None:
        """Create serial port settings."""
        self.deviceLabel = QtWidgets.QLabel(device_type)
        self.deviceCombo = QtWidgets.QComboBox()
        self.deviceCombo.setFixedWidth(240)
        
        self.baudLabel = QtWidgets.QLabel("Baud Rate")
        self.baudCombo = QtWidgets.QComboBox()
        self.baudCombo.setFixedWidth(120)
        
        # Common baud rates
        baud_rates = ["9600", "19200", "38400", "57600", "115200"]
        self.baudCombo.addItems(baud_rates)
        # Default to 57600 for Radiation (Geiger counters like GMC-300S/300E Plus)
        # Default to 9600 for Satellite (GNSS modules)
        if GROUP == "Radiation":
            self.baudCombo.setCurrentText("57600")
        else:
            self.baudCombo.setCurrentText("9600")
        
        self._populate_serial_ports()
    
    def _miner_fully_set(self) -> bool:
        """
        Miner is fully set ONLY if:
        - device is online
        - data has been received (or no LiveData available)
        - MAC is valid / not mismatched
        """
        pod_ok = getattr(self, "_last_pod_ok", None)
        if pod_ok is True:
            online_ok = True
        elif pod_ok is None and not self._pod_supported():
            # Sensor-less miners: infer online from non-zero multiplier
            mult = getattr(self, "_current_multiplier", None)
            online_ok = mult is not None and mult > 0
        else:
            online_ok = False
        mac_ok = not bool(getattr(self, "_mac_mismatch", False))
        # Data flowing = we have received at least one valid live data update.
        # If LiveData is not available on this build, treat data_ok as True
        # to avoid gating sharing unnecessarily.
        # Note: We use _has_received_live_data instead of _live_poll_timer because
        # the timer is stopped when switching away from Live Data tab (normal behavior).
        if not HAVE_LIVEDATA:
            data_ok = True
        else:
            data_ok = bool(getattr(self, "_has_received_live_data", False))

        return online_ok and mac_ok and data_ok

    def _refresh_sharing_gate(self) -> None:
        """Clear pending state on all sharing panels once gates are satisfied.

        BM panels self-clear pending inside their own update_status(), but
        RDN/SDN LiveData inner panels (StorageNodeTab) do not — they guard
        against overwriting the pending message but never clear the flag.
        This method reads the weekly status JSON and clears pending for all
        panels when mac_mismatch and online_status are set.
        """
        try:
            from miner_GUI.utils.status_week import load_status_week_for_date
            from datetime import date
            week_doc = load_status_week_for_date(date.today())
        except Exception:
            return

        if not isinstance(week_doc, dict):
            return

        mac_mismatch = week_doc.get("mac_mismatch")
        online_status = week_doc.get("online_status")

        # Gates are satisfied when both fields have been set by the backend
        mac_known = mac_mismatch is not None
        online_known = bool(online_status)  # not None and not ""

        if mac_known and online_known:
            self._clear_all_sharing_pending()

    def _set_all_sharing_pending(self) -> None:
        """Disable all sharing tool toggles and show pending warning."""
        # BM sharing tools
        if self.honeygain_panel:
            try:
                if hasattr(self.honeygain_panel, "_status_label"):
                    self.honeygain_panel._status_label.setText(PENDING_MESSAGE)
                self.honeygain_panel.set_pending_state(True)
            except Exception:
                pass

        if self.bright_panel:
            try:
                if hasattr(self.bright_panel, "_status_label"):
                    self.bright_panel._status_label.setText(PENDING_MESSAGE)
                self.bright_panel.set_pending_state(True)
            except Exception:
                pass

        if self.mysterium_panel:
            try:
                if hasattr(self.mysterium_panel, "_status_label"):
                    self.mysterium_panel._status_label.setText(PENDING_MESSAGE)
                self.mysterium_panel.set_pending_state(True)
            except Exception:
                pass

        # SDN tools
        if self.space_acres_panel:
            try:
                if hasattr(self.space_acres_panel, "_status_label"):
                    self.space_acres_panel._status_label.setText(PENDING_MESSAGE)
                self.space_acres_panel.set_pending_state(True)
            except Exception:
                pass
        # Also handle LiveData SDN panel
        elif self.live_panel is not None:
            sa = getattr(self.live_panel, 'space_acres_panel', None)
            if sa is not None:
                try:
                    sa._status_label.setText(PENDING_MESSAGE)
                    sa.set_pending_state(True)
                except Exception:
                    pass

        # RDN tools
        if self.presearch_panel:
            try:
                if hasattr(self.presearch_panel, "_status_label"):
                    self.presearch_panel._status_label.setText(PENDING_MESSAGE)
                self.presearch_panel.set_pending_state(True)
            except Exception:
                pass
        # Also handle LiveData RDN panel (Presearch)
        elif self.live_panel is not None:
            pr = getattr(self.live_panel, 'presearch_panel', None)
            if pr is not None:
                try:
                    pr._status_label.setText(PENDING_MESSAGE)
                    pr.set_pending_state(True)
                except Exception:
                    pass

        if self.diiisco_panel:
            try:
                if hasattr(self.diiisco_panel, "_status_label"):
                    self.diiisco_panel._status_label.setText(PENDING_MESSAGE)
                self.diiisco_panel.set_pending_state(True)
            except Exception:
                pass
        # Also handle LiveData RDN panel (Diiisco)
        elif self.live_panel is not None:
            di = getattr(self.live_panel, 'diiisco_panel', None)
            if di is not None:
                try:
                    di._status_label.setText(PENDING_MESSAGE)
                    di.set_pending_state(True)
                except Exception:
                    pass
    
    def _clear_all_sharing_pending(self) -> None:
        """Re-enable all sharing tool toggles and clear pending warnings."""
        # BM sharing tools
        if self.honeygain_panel:
            try:
                self.honeygain_panel.set_pending_state(False)
            except Exception:
                pass

        if self.bright_panel:
            try:
                self.bright_panel.set_pending_state(False)
            except Exception:
                pass

        if self.mysterium_panel:
            try:
                self.mysterium_panel.set_pending_state(False)
            except Exception:
                pass

        # SDN tools
        if self.space_acres_panel:
            try:
                self.space_acres_panel.set_pending_state(False)
            except Exception:
                pass
        # Also handle LiveData SDN panel
        elif self.live_panel is not None:
            sa = getattr(self.live_panel, 'space_acres_panel', None)
            if sa is not None:
                try:
                    sa.set_pending_state(False)
                except Exception:
                    pass

        # RDN tools
        if self.presearch_panel:
            try:
                self.presearch_panel.set_pending_state(False)
            except Exception:
                pass
        # Also handle LiveData RDN panel (Presearch)
        elif self.live_panel is not None:
            pr = getattr(self.live_panel, 'presearch_panel', None)
            if pr is not None:
                try:
                    pr.set_pending_state(False)
                except Exception:
                    pass

        if self.diiisco_panel:
            try:
                self.diiisco_panel.set_pending_state(False)
            except Exception:
                pass
        # Also handle LiveData RDN panel (Diiisco)
        elif self.live_panel is not None:
            di = getattr(self.live_panel, 'diiisco_panel', None)
            if di is not None:
                try:
                    di.set_pending_state(False)
                except Exception:
                    pass

    def _build_sharing_tabs_widget(self) -> QtWidgets.QWidget:
        """Build the original sharing QTabWidget body (Honeygain/Bright/Mysterium)."""
        tabs = QtWidgets.QTabWidget()
        tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(False)
        tabs.setElideMode(QtCore.Qt.TextElideMode.ElideRight)

        # Honeygain tab
        if self._allow_honeygain:
            self.honeygain_panel = HoneygainPanel()
            self._flatten_groupbox(self.honeygain_panel)
            self.honeygain_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.honeygain_panel._status_label.setText(PENDING_MESSAGE)
            self.honeygain_panel.set_pending_state(True)
            hg_container = QtWidgets.QWidget()
            hg_layout = QtWidgets.QVBoxLayout(hg_container)
            hg_layout.setContentsMargins(0, 0, 0, 0)
            hg_layout.setSpacing(4)
            hg_layout.addWidget(self.honeygain_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            hg_idx = tabs.addTab(hg_container, "Honeygain")
            tabs.setTabEnabled(hg_idx, False)
            tabs.setTabToolTip(hg_idx, "Coming soon \u2014 pending partnership approval")

        # Bright tab (Windows only)
        if sys.platform.startswith("win") and self._allow_bright:
            self.bright_panel = BrightPanel()
            self._flatten_groupbox(self.bright_panel)
            self.bright_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.bright_panel._status_label.setText(PENDING_MESSAGE)
            self.bright_panel.set_pending_state(True)
            br_container = QtWidgets.QWidget()
            br_layout = QtWidgets.QVBoxLayout(br_container)
            br_layout.setContentsMargins(0, 0, 0, 0)
            br_layout.setSpacing(4)
            br_layout.addWidget(self.bright_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            br_idx = tabs.addTab(br_container, "Web Indexing")
            tabs.setTabEnabled(br_idx, False)
            tabs.setTabToolTip(br_idx, "Coming soon \u2014 pending partnership approval")

        # Mysterium tab
        if self._allow_mysterium:
            self.mysterium_panel = MysteriumPanel()
            self._flatten_groupbox(self.mysterium_panel)
            self.mysterium_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.mysterium_panel._status_label.setText(PENDING_MESSAGE)
            self.mysterium_panel.set_pending_state(True)
            myst_container = QtWidgets.QWidget()
            myst_layout = QtWidgets.QVBoxLayout(myst_container)
            myst_layout.setContentsMargins(0, 0, 0, 0)
            myst_layout.setSpacing(4)
            myst_layout.addWidget(self.mysterium_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            tabs.addTab(myst_container, "Mysterium")

        # Track 1.7: select first enabled tab (Mysterium) so a disabled tab
        # doesn't remain current. setTabEnabled(False) on the auto-selected
        # first tab does not auto-advance currentIndex in Qt6.
        for i in range(tabs.count()):
            if tabs.isTabEnabled(i):
                tabs.setCurrentIndex(i)
                break

        return tabs

    def _reapply_sharing_tab_disabled_state(self) -> None:
        """Track 1.7: re-apply disabled state to Honeygain/Web Indexing tabs.

        Defence-in-depth: re-applies setTabEnabled(False) and setTabToolTip
        after theme/style application, in case a future Qt/PySide6 update
        resets per-tab state during stylesheet polish. Idempotent.
        """
        tabs = getattr(self, "_sharing_body_widget", None)
        if not isinstance(tabs, QtWidgets.QTabWidget):
            return
        coming_soon_labels = ("Honeygain", "Web Indexing")
        coming_soon_tooltip = "Coming soon \u2014 pending partnership approval"
        first_enabled = -1
        for i in range(tabs.count()):
            label = tabs.tabText(i)
            if label in coming_soon_labels:
                tabs.setTabEnabled(i, False)
                tabs.setTabToolTip(i, coming_soon_tooltip)
            elif first_enabled < 0 and tabs.isTabEnabled(i):
                first_enabled = i
        if first_enabled >= 0:
            tabs.setCurrentIndex(first_enabled)

    def _create_live_data_section(self) -> None:
        """Create live data display section. On mobile, use full width (no logo column)."""
        # Don't use a GroupBox title since the tab already says "Live Data"
        self.liveGb = QtWidgets.QGroupBox("")

        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"

        if is_mobile:
            # Full-width live data on mobile
            main_layout = QtWidgets.QVBoxLayout(self.liveGb)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(6)
            
            data_layout = QtWidgets.QVBoxLayout()
            data_layout.setContentsMargins(0, 0, 0, 0)
            data_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            if HAVE_LIVEDATA and load_live_panel:
                live_width = self._live_panel_width_hint()
                self.live_panel = load_live_panel(GROUP, width=live_width, screen_size="mobile")
                if self.live_panel:
                    data_layout.addWidget(self.live_panel, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
                else:
                    self._create_fallback_live_display_in_layout(data_layout)
            else:
                self._create_fallback_live_display_in_layout(data_layout)

            data_widget = QtWidgets.QWidget()
            data_widget.setLayout(data_layout)
            main_layout.addWidget(data_widget)

            if MINER_CODE == "BM":
                self._attach_sharing_panels(data_layout)
            elif MINER_CODE == "SDN":
                self._attach_sdn_panels(data_layout)
            elif MINER_CODE == "RDN":
                self._attach_service_node_panels(data_layout)
            elif MINER_CODE == "SVN":
                self._attach_svn_panels(data_layout)
        else:
            # Original split layout for larger screens
            main_layout = QtWidgets.QHBoxLayout(self.liveGb)

            # Left side: Logo (1/3 width)
            logo_widget = QtWidgets.QWidget()
            logo_layout = QtWidgets.QVBoxLayout(logo_widget)
            logo_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            logo_layout.setContentsMargins(0, 0, 0, 0)
            logo_layout.setSpacing(6)
            logo_layout.addStretch(1)

            # Load and display logo
            logo_label = QtWidgets.QLabel()
            logo_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            try:
                icon_path = miner_icon_path()
                if icon_path.exists():
                    pixmap = QtGui.QPixmap(str(icon_path))
                    if not pixmap.isNull():
                        size_map = {
                            "mobile": 70 if MINER_CODE == "BM" else 100,
                            "tablet": 130,
                            "laptop": 150,
                            "desktop": 150,
                            "ultrawide": 170,
                        }
                        target_size = size_map.get(getattr(self, "_screen_size_pref", "desktop"), 150)
                        scaled_pixmap = pixmap.scaled(
                            target_size, target_size,
                            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                            QtCore.Qt.TransformationMode.SmoothTransformation
                        )
                        logo_label.setPixmap(scaled_pixmap)
                    else:
                        logo_label.setText("Logo\nUnavailable")
                else:
                    logo_label.setText("Logo\nNot Found")
            except Exception as e:
                logo_label.setText("Logo\nError")
                logging.warning(f"Failed to load logo: {e}")

            logo_layout.addWidget(logo_label, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
            logo_layout.addStretch(1)

            # Right side: Live data panel (2/3 width)
            data_widget = QtWidgets.QWidget()
            data_layout = QtWidgets.QVBoxLayout(data_widget)
            data_layout.setContentsMargins(0, 0, 0, 0)
            data_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            if HAVE_LIVEDATA and load_live_panel:
                live_width = self._live_panel_width_hint()
                screen_pref = getattr(self, "_screen_size_pref", "desktop")
                if MINER_CODE == "BM" and screen_pref == "mobile":
                    live_width = int(live_width * 0.9)
                self.live_panel = load_live_panel(GROUP, width=live_width, screen_size=screen_pref)
                if self.live_panel:
                    data_layout.addStretch(1)
                    data_layout.addWidget(self.live_panel, 0, QtCore.Qt.AlignmentFlag.AlignCenter)
                    data_layout.addStretch(1)
                else:
                    self._create_fallback_live_display_in_layout(data_layout)
            else:
                self._create_fallback_live_display_in_layout(data_layout)

            main_layout.addWidget(logo_widget, 1, QtCore.Qt.AlignmentFlag.AlignVCenter)
            main_layout.addWidget(data_widget, 2)

            if MINER_CODE == "BM":
                self._attach_sharing_panels(data_layout)
            elif MINER_CODE == "SDN":
                self._attach_sdn_panels(data_layout)
            elif MINER_CODE == "RDN":
                self._attach_service_node_panels(data_layout)
            elif MINER_CODE == "SVN":
                self._attach_svn_panels(data_layout)

    def _attach_sharing_panels(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Add combined Earnings & Sharing section with Honeygain and Bright rows."""
        # Hide sharing UI entirely if sharing mode is "none"
        if self._sharing_mode == "none":
            return

        container = QtWidgets.QGroupBox("Bandwidth Sharing")
        container_layout = QtWidgets.QVBoxLayout(container)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        container_layout.setContentsMargins(6 if is_mobile else 12, 6 if is_mobile else 2, 6 if is_mobile else 12, 6)
        container_layout.setSpacing(8 if is_mobile else 14)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        self.rewards_hint = QtWidgets.QLabel()
        self.rewards_hint.setObjectName("hint")
        self.rewards_hint.setWordWrap(True)
        self.rewards_hint.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        container_layout.addWidget(self.rewards_hint)
        if not is_mobile:
            container_layout.addSpacing(4)

        # Store layout reference for dynamic refresh
        self._sharing_container_layout = container_layout
        
        # Build tabs immediately so UI appears instantly (optimistic)
        tabs = self._build_sharing_tabs_widget()
        container_layout.addWidget(tabs)
        self._sharing_body_widget = tabs
        self._sharing_ui_state = "tabs"
        
        # Initialize support timers immediately
        if self._allow_honeygain:
            honeygain_helpers.init_honeygain_support(self)
        if self._allow_bright:
            bright_helpers.init_bright_support(self)
        if self._allow_mysterium:
            tos_ok = mysterium_catchup.check_mysterium_tos_on_startup(self)
            if tos_ok:
                mysterium_helpers.init_mysterium_support(self)
                if getattr(self, '_mysterium_catchup_just_accepted', False):
                    self._mysterium_catchup_just_accepted = False
                    mysterium_helpers.apply_mysterium_state(self, enable=True)
            else:
                if self.mysterium_panel:
                    # Track 3.1: fix V11 — clear pending so show_status_message
                    # doesn't early-return (mysterium_panel.py:159 _is_pending guard)
                    self.mysterium_panel.set_pending_state(False)
                    # Override stale cached_status.json toggle state
                    self.mysterium_panel._suspend_toggle = True
                    self.mysterium_panel._toggle.setChecked(False)
                    self.mysterium_panel._suspend_toggle = False
                    self.mysterium_panel.show_status_message("Mysterium: TOS not accepted")
                    # Connect toggle for re-consent path (init_mysterium_support
                    # not called — controller doesn't exist yet)
                    self.mysterium_panel.toggle_changed.connect(
                        lambda enabled: mysterium_helpers.handle_mysterium_toggle(self, enabled)
                    )
        
        # Check readiness after status data loads (pending already set at panel creation)
        QtCore.QTimer.singleShot(2500, self._refresh_sharing_gate)

        layout.addSpacing(6)
        layout.addWidget(container, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        rewards_helpers.update_rewards_hint(self)

    def _attach_sdn_panels(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Add SDN mining integrations (Space Acres for Autonomy farming)."""
        # Check if live_panel is already an SdnPanel (LiveData version with embedded toggles)
        live_panel = getattr(self, 'live_panel', None)
        if live_panel is not None and hasattr(live_panel, 'space_acres_refresh_clicked'):
            # LiveData SdnPanel handles the UI; set pending state before initializing
            if self._allow_space_acres:
                # Set pending message and state on the embedded StorageNodeTab
                live_panel.space_acres_panel._status_label.setText(PENDING_MESSAGE)
                live_panel.space_acres_panel.set_pending_state(True)
                
                # Now initialize controller support
                space_acres_helpers.init_space_acres_support(self)
            return

        # Fallback: create standalone panels (legacy mode)
        container = QtWidgets.QGroupBox("Storage Mining")
        container_layout = QtWidgets.QVBoxLayout(container)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        container_layout.setContentsMargins(6 if is_mobile else 12, 6 if is_mobile else 2, 6 if is_mobile else 12, 6)
        container_layout.setSpacing(8 if is_mobile else 14)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        # Build tabs for SDN integrations
        tabs = QtWidgets.QTabWidget()

        # Space Acres tab
        if self._allow_space_acres:
            self.space_acres_panel = SpaceAcresPanel()
            self._flatten_groupbox(self.space_acres_panel)
            self.space_acres_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.space_acres_panel._status_label.setText(PENDING_MESSAGE)
            self.space_acres_panel._stats_label.setText("")
            self.space_acres_panel.set_pending_state(True)
            tabs.addTab(self.space_acres_panel, "Space Acres")

        container_layout.addWidget(tabs)

        # Initialize support
        if self._allow_space_acres:
            space_acres_helpers.init_space_acres_support(self)
        
        # Check readiness after status data loads (pending already set at panel creation)
        QtCore.QTimer.singleShot(2500, self._refresh_sharing_gate)

        layout.addSpacing(6)
        layout.addWidget(container, 0, QtCore.Qt.AlignmentFlag.AlignTop)

    def _attach_service_node_panels(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Add RDN service node integrations (Presearch, Diiisco)."""
        # Check if live_panel is already an RdnPanel (LiveData version with embedded toggles)
        live_panel = getattr(self, 'live_panel', None)
        if live_panel is not None and hasattr(live_panel, 'presearch_refresh_clicked'):
            # LiveData RdnPanel handles the UI; set pending state before initializing
            pending_msg = (
                "⏳ Waiting for miner to be fully configured...\n\n"
                "This tool will be available once your device is online, "
                "MAC address is registered, and data is flowing."
            )
            
            if self._allow_presearch:
                live_panel.presearch_panel._status_label.setText(pending_msg)
                live_panel.presearch_panel.set_pending_state(True)
                presearch_helpers.init_presearch_support(self)

            if self._allow_diiisco:
                live_panel.diiisco_panel._status_label.setText(pending_msg)
                live_panel.diiisco_panel.set_pending_state(True)
                diiisco_helpers.init_diiisco_support(self)
            return

        # Fallback: create standalone panels (legacy mode)
        container = QtWidgets.QGroupBox("Service Nodes")
        container_layout = QtWidgets.QVBoxLayout(container)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        container_layout.setContentsMargins(6 if is_mobile else 12, 6 if is_mobile else 2, 6 if is_mobile else 12, 6)
        container_layout.setSpacing(8 if is_mobile else 14)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        # Build tabs for SVN integrations
        tabs = QtWidgets.QTabWidget()

        # Presearch tab
        if self._allow_presearch:
            self.presearch_panel = PresearchPanel()
            self._flatten_groupbox(self.presearch_panel)
            self.presearch_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.presearch_panel._status_label.setText(PENDING_MESSAGE)
            self.presearch_panel._stats_label.setText("")
            self.presearch_panel.set_pending_state(True)
            tabs.addTab(self.presearch_panel, "Presearch")

        # Diiisco tab
        if self._allow_diiisco:
            self.diiisco_panel = DiiiscoPanel()
            self._flatten_groupbox(self.diiisco_panel)
            self.diiisco_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred
            )
            # Set pending state immediately before controller init
            # Must set message on label directly BEFORE setting pending flag
            self.diiisco_panel._status_label.setText(PENDING_MESSAGE)
            self.diiisco_panel._stats_label.setText("")
            self.diiisco_panel.set_pending_state(True)
            tabs.addTab(self.diiisco_panel, "Diiisco")

        container_layout.addWidget(tabs)

        # Initialize support
        if self._allow_presearch:
            presearch_helpers.init_presearch_support(self)
        if self._allow_diiisco:
            diiisco_helpers.init_diiisco_support(self)
        
        # Check readiness after status data loads (pending already set at panel creation)
        QtCore.QTimer.singleShot(2500, self._refresh_sharing_gate)

        layout.addSpacing(6)
        layout.addWidget(container, 0, QtCore.Qt.AlignmentFlag.AlignTop)

    def _attach_svn_panels(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Add SVN mining integrations (XMRig for storage validation)."""
        # Check if live_panel is already an SvnPanel (LiveData version)
        live_panel = getattr(self, 'live_panel', None)
        if live_panel is not None and hasattr(live_panel, 'xmrig_refresh_clicked'):
            # LiveData SvnPanel handles the UI; set pending state before initializing
            if self._allow_xmrig:
                live_panel.xmrig_panel._status_label.setText(PENDING_MESSAGE)
                live_panel.xmrig_panel.set_pending_state(True)

                xmrig_helpers.init_xmrig_support(self)
            return

        # Fallback: create standalone panels (legacy mode)
        container = QtWidgets.QGroupBox("Mining")
        container_layout = QtWidgets.QVBoxLayout(container)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        container_layout.setContentsMargins(6 if is_mobile else 12, 6 if is_mobile else 2, 6 if is_mobile else 12, 6)
        container_layout.setSpacing(8 if is_mobile else 14)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)

        # Build tabs for SVN integrations
        tabs = QtWidgets.QTabWidget()

        # XMRig tab
        if self._allow_xmrig:
            self.xmrig_panel = XMRigPanel()
            self._flatten_groupbox(self.xmrig_panel)
            self.xmrig_panel.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            self.xmrig_panel._status_label.setText(PENDING_MESSAGE)
            self.xmrig_panel._stats_label.setText("")
            self.xmrig_panel.set_pending_state(True)
            tabs.addTab(self.xmrig_panel, "XMRig")

        container_layout.addWidget(tabs)

        # Initialize support
        if self._allow_xmrig:
            xmrig_helpers.init_xmrig_support(self)

        # Check readiness after status data loads
        QtCore.QTimer.singleShot(2500, self._refresh_sharing_gate)

        layout.addSpacing(6)
        layout.addWidget(container, 0, QtCore.Qt.AlignmentFlag.AlignTop)

    def _flatten_groupbox(self, box: QtWidgets.QGroupBox) -> None:
        """Remove outer chrome from embedded group boxes to look like rows."""
        try:
            box.setTitle("")
            box.setFlat(True)
            box.setStyleSheet(
                "QGroupBox{margin:0; padding:0; border:0;} "
                "QGroupBox::title{padding:0; margin:0;}"
            )
        except Exception:
            pass

    def _multiplier_badge(self, mult: Optional[float] = None) -> str:
        """Return HTML badge for current multiplier."""
        if mult is None:
            mult = getattr(self, "_current_multiplier", None)
        if mult is None:
            return ""
        if mult >= 0.99:
            color = "#0fb94b"
        elif mult >= 0.74:
            color = "#c75c1e"
        else:
            color = "#d94d4d"
        return (
            f"<span style='background:{color}; color:#fff; padding:2px 8px; "
            f"border-radius:10px; font-weight:600;'>"
            f"{mult:.2f}x</span>"
        )

    def _refresh_footer_status(self) -> None:
        """Update footer text with device status and rewards badge."""
        mult = getattr(self, "_current_multiplier", None)
        # Don't assume any multiplier at startup; only use actual data from weekly JSON
        icon = ""
        status_text = "Device status unknown"
        effective_mult = mult
        
        # Show "Status pending..." only when a gate is literally null (not yet set)
        # Gates are: _mac_mismatch (None=not set), _last_pod_ok (None=not set)
        mac_unknown = getattr(self, "_mac_mismatch", None) is None
        online_unknown = getattr(self, "_last_pod_ok", None) is None

        if mac_unknown or online_unknown:
            # At least one gate is still null - show pending
            icon = "<span style='color:#6f7a88; font-size:14pt;'>●</span>"
            status_text = "Status pending..."
            effective_mult = 0.0
        else:
            # All gates have values - show real status
            mac_mismatch = bool(getattr(self, "_mac_mismatch", False))
            if mac_mismatch:
                icon = "<span style='color:#c75c1e; font-size:14pt;'>⚠</span>"
                status_text = "Registration mismatch"
                effective_mult = 0.0
            elif getattr(self, "_last_pod_ok", None) is True:
                icon = "<span style='color:#0fb94b; font-size:14pt;'>✓</span>"
                status_text = "Device online"
            elif getattr(self, "_last_pod_ok", None) is False:
                icon = "<span style='color:#c75c1e; font-size:14pt;'>⚠</span>"
                status_text = "Device offline" if not getattr(self, "_last_pod_error", None) else f"Device offline - {self._last_pod_error}"
                effective_mult = 0.0  # No rewards when offline
            else:
                # Shouldn't happen — _last_pod_ok is only True/False/None
                icon = "<span style='color:#6f7a88; font-size:14pt;'>●</span>"
                status_text = "Status pending..."

        badge = self._multiplier_badge(effective_mult)
        mult_text = f"{effective_mult:.2f}x" if effective_mult is not None else ""
        rewards = ""
        if badge:
            rewards = f"Current Rewards Multiplier: <span style='color:transparent;'>X</span> {badge}"
        elif mult_text:
            rewards = f"Current Rewards Multiplier: {mult_text}"

        # Add week multiplier if available
        week_mult = getattr(self, "_week_multiplier", None)
        week_mult_text = ""
        if week_mult is not None:
            week_badge = self._multiplier_badge(week_mult)
            if week_badge:
                week_mult_text = f"Week Multiplier: <span style='color:transparent;'>X</span> {week_badge}"
            else:
                week_mult_text = f"Week Multiplier: {week_mult:.2f}x"

        footer = f"{icon} {status_text}"
        # Only add rewards/multiplier text if NOT in pending mode
        any_pending = mac_unknown or online_unknown
        if not any_pending:
            if rewards:
                footer = f"{footer} - {rewards}"
            if week_mult_text:
                footer = f"{footer} | {week_mult_text}"
        
        # Add hardware stats if available from measurements
        if hasattr(self, '_latest_measurements') and self._latest_measurements:
            hw_stats = self._latest_measurements.get('hardware_stats', {})
            if hw_stats:
                hw_text = measurement_display.format_hardware_stats(hw_stats)
                if hw_text and hw_text != "Hardware stats unavailable":
                    footer = f"{footer} | {hw_text}"
        
        footer = f"<span style='white-space: nowrap;'>{footer}</span>"
        self.statusLabel.setText(footer)

        # Propagate offline state to all tool panels
        self._update_panel_offline_state()

        # Refresh sharing panel gate when miner status changes
        self._refresh_sharing_gate()

    # ---------------- Configuration and approvals -----------------
    def _load_partner_approvals(self) -> None:
        """Load approvals and reward parameters from gui_config.enc.
        
        gui_config.enc (service-managed) contains:
        - SDK approvals for BM tools (BM only)
        - Reward multipliers for all miner types
        """
        candidates: list[Path] = []
        try:
            candidates.append(data_dir_gui() / "config")
        except Exception:
            pass
        try:
            from miner_GUI.config import app_dir

            candidates.append(app_dir() / "config")
        except Exception:
            pass
        candidates.append(Path.cwd() / "config")

        target: Optional[Path] = None
        # Load only from gui_config.enc (service-managed, no fallback)
        for base in candidates:
            cand = base / "gui_config.enc"
            if cand.exists():
                target = cand
                break

        if target is None:
            log_step("gui_config_not_found", {"searched": [str(b / "gui_config.enc") for b in candidates]})
            return
        log_step("gui_config_found", {"path": str(target)})

        try:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            from cryptography.fernet import Fernet
        except ImportError:
            log_step("gui_config_no_cryptography")
            return

        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            token = payload.get("data")
            if not isinstance(token, str):
                log_step("gui_config_bad_token")
                return
            # Cache the Fernet instance — salt and key_material are constants so
            # PBKDF2 (100k iterations) only needs to run once per process.
            if not hasattr(self, "_gui_config_fernet"):
                salt = b"gui_config_salt_v1"
                key_material = b"gui_config_encryption_key_v1"
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                self._gui_config_fernet = Fernet(
                    base64.urlsafe_b64encode(kdf.derive(key_material))
                )
            data = json.loads(self._gui_config_fernet.decrypt(token.encode("utf-8")).decode("utf-8"))

            # Load partner approvals from gui_config.enc
            # Service stores approval booleans as top-level keys (e.g. "honeygain": true)
            # and may also nest them under an "approvals" dict for legacy compatibility.
            _approval_keys = {
                "BM": ("honeygain", "bright", "mysterium"),
                "RDN": ("presearch", "diiisco"),
                "SDN": ("space_acres",),
                "SVN": ("xmrig",),
            }
            known = _approval_keys.get(MINER_CODE, ())
            approvals: Dict[str, Any] = {}

            # Try nested "approvals" dict first (legacy BM format)
            nested = data.get("approvals")
            if isinstance(nested, dict):
                approvals.update(nested)

            # Then overlay top-level keys (service-managed format)
            for k in known:
                if k in data and isinstance(data[k], bool):
                    approvals[k] = data[k]

            if approvals:
                self._partner_approvals = approvals
                log_step("approvals_loaded", {"keys": list(approvals.keys())})

            # Load reward multipliers (all miner types) - service-managed only
            # Use gui_config field names (base_reward, per_tool_reward)
            _base = data.get("base_reward")
            _per = data.get("per_tool_reward")
            if _base is not None and _per is not None:
                try:
                    from miner_GUI.ui.helpers.rewards import load_from_gui_config
                    load_from_gui_config(float(_base), float(_per))
                    log_step("reward_multipliers_loaded", {"base": float(_base), "per_tool": float(_per)})
                except Exception as exc:
                    log_step("reward_multipliers_error", {"error": str(exc)})
            else:
                log_step("gui_config_missing_fields", {"base": _base, "per": _per, "keys": list(data.keys())})
        except Exception as exc:
            log_step("gui_config_decrypt_error", {"error": str(exc)})

    def _refresh_approval_from_enc(self, partner: str) -> None:
        """Lightweight approval-only read used by the poll tick.

        Uses the cached Fernet key so PBKDF2 never re-runs.
        Does NOT reload reward multipliers or emit any log entries.
        """
        candidates: list[Path] = []
        try:
            candidates.append(data_dir_gui() / "config")
        except Exception:
            pass
        try:
            from miner_GUI.config import app_dir
            candidates.append(app_dir() / "config")
        except Exception:
            pass
        candidates.append(Path.cwd() / "config")

        target: Optional[Path] = None
        for base in candidates:
            cand = base / "gui_config.enc"
            if cand.exists():
                target = cand
                break

        if target is None or not hasattr(self, "_gui_config_fernet"):
            return

        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            token = payload.get("data")
            if not isinstance(token, str):
                return
            data = json.loads(self._gui_config_fernet.decrypt(token.encode("utf-8")).decode("utf-8"))
            if not isinstance(getattr(self, "_partner_approvals", None), dict):
                self._partner_approvals = {}
            # Update only the specific partner's approval
            nested = data.get("approvals")
            if isinstance(nested, dict) and partner in nested:
                self._partner_approvals[partner] = nested[partner]
            if partner in data and isinstance(data[partner], bool):
                self._partner_approvals[partner] = data[partner]
        except Exception:
            pass

    def _desired_approval(self, partner: str) -> Optional[bool]:
        val = self._partner_approvals.get(partner) if isinstance(self._partner_approvals, dict) else None
        if isinstance(val, dict):
            val = val.get("approved")
        if isinstance(val, bool):
            return val
        return None

    def _apply_partner_opt_in(self, partner: str, current_enabled: Optional[bool]) -> None:
        """Apply installer-provided opt-in defaults once per partner."""
        desired = self._desired_approval(partner)
        if desired is None or partner in self._partner_approvals_applied:
            return
        if current_enabled is None:
            return

        if partner == "honeygain" and self.honeygain_controller and self.honeygain_panel:
            if current_enabled != desired:
                honeygain_helpers.apply_honeygain_state(self, enable=desired)
            self._partner_approvals_applied.add(partner)
            return

        if partner == "bright" and self.bright_controller and self.bright_panel:
            if current_enabled != desired:
                bright_helpers.apply_bright_state(self, enable=desired)
            self._partner_approvals_applied.add(partner)
            return

        if partner == "mysterium" and self.mysterium_controller and self.mysterium_panel:
            # Defensive gate: check TOS state before auto-enabling (Track 3)
            from miner_GUI.utils.tos_state import read_tos_state, is_resolved_accept
            from miner_GUI.utils.data import data_dir_gui
            tos = read_tos_state(data_dir_gui() / "config")
            if not is_resolved_accept(tos):
                return  # TOS not resolved — don't auto-enable from sdk_config opt-in
            # Short-circuit if daemon already running (avoid progress dialog)
            try:
                import requests as _req
                r = _req.get("http://127.0.0.1:4050/healthcheck", timeout=2)
                if r.status_code == 200:
                    self._mysterium_enabled = True
                    if self.mysterium_panel:
                        self.mysterium_panel._suspend_toggle = True
                        self.mysterium_panel._toggle.setChecked(True)
                        self.mysterium_panel._suspend_toggle = False
                    self._partner_approvals_applied.add(partner)
                    return
            except Exception:
                pass
            if current_enabled != desired:
                mysterium_helpers.apply_mysterium_state(self, enable=desired)
            self._partner_approvals_applied.add(partner)

    def _set_partner_approval(self, partner: str, enabled: bool) -> None:
        """Update in-memory approvals map (service persists gui_config.enc)."""
        prev = self._partner_approvals.get(partner)
        prev_val = prev.get("approved") if isinstance(prev, dict) else prev
        logger.info(
            "_set_partner_approval: partner=%s, enabled=%s, prev=%s, prev_val=%s",
            partner, enabled, prev, prev_val
        )
        if isinstance(prev_val, bool) and prev_val == bool(enabled):
            logger.info("_set_partner_approval: skipping (value unchanged)")
            return
        self._partner_approvals[partner] = bool(enabled)
        logger.info("_set_partner_approval: updated in-memory approvals=%s", self._partner_approvals)

    def _poll_gui_config_approval(
        self,
        partner: str,
        expected: bool,
        on_confirmed: Callable[[], None],
        on_timeout: Callable[[], None],
        max_seconds: int = 15,
        interval_ms: int = 500,
    ) -> None:
        """Poll gui_config.enc until the service confirms the approval state.

        The service is the canonical writer of gui_config.enc.  After the GUI
        enqueues an ops-queue request (via the controller), this method polls
        the encrypted config file until the partner's approval matches
        *expected*, then calls *on_confirmed*.  If *max_seconds* elapses
        without a match the timer stops and *on_timeout* is called instead.
        """
        elapsed_ms = 0

        timer = QtCore.QTimer(self)
        timer.setInterval(interval_ms)

        def _tick() -> None:
            nonlocal elapsed_ms
            elapsed_ms += interval_ms

            # Re-read only this partner's approval (no PBKDF2, no reward reload)
            self._refresh_approval_from_enc(partner)
            current = self._desired_approval(partner)

            if current is not None and bool(current) == expected:
                timer.stop()
                log_step("approval_poll_confirmed", {
                    "partner": partner, "expected": expected,
                    "elapsed_ms": elapsed_ms,
                })
                on_confirmed()
                return

            if elapsed_ms >= max_seconds * 1000:
                timer.stop()
                log_step("approval_poll_timeout", {
                    "partner": partner, "expected": expected,
                    "elapsed_ms": elapsed_ms,
                })
                on_timeout()

        timer.timeout.connect(_tick)
        timer.start()
        log_step("approval_poll_started", {
            "partner": partner, "expected": expected,
            "max_seconds": max_seconds,
        })

    def _create_fallback_live_display_in_layout(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Create fallback live data display when LiveData panels not available."""
        # Only create displays for specific miner codes
        if MINER_CODE not in ("BM", "IDM", "ODM", "ISM", "OSM", "IRM"):
            return
        
        # Create data display based on miner type
        if GROUP in ("BM", "Bandwidth"):  # keep Bandwidth as legacy alias
            self._create_bandwidth_display_in_layout(layout)
        elif GROUP == "Decibel":
            self._create_audio_display_in_layout(layout)
        elif GROUP == "Satellite":
            self._create_gnss_display_in_layout(layout)
        elif GROUP == "Radiation":
            self._create_radiation_display_in_layout(layout)

    # Helper method that's not a simple wrapper
    def _set_panel_toggle_state(
        self,
        panel: Optional[Union[HoneygainPanel, BrightPanel, MysteriumPanel]],
        checked: bool,
    ) -> None:
        if not panel:
            return
        logger.debug(
            "Force toggle state panel=%s checked=%s currently_enabled=%s",
            type(panel).__name__,
            checked,
            panel._toggle.isEnabled() if hasattr(panel, "_toggle") else None,  # type: ignore[attr-defined]
        )
        panel._suspend_toggle = True  # type: ignore[attr-defined]
        try:
            panel._toggle.setChecked(checked)  # type: ignore[attr-defined]
        finally:
            panel._suspend_toggle = False  # type: ignore[attr-defined]

    def _confirm_disable_sharing(self, service_label: str) -> bool:
        """Warn the user that disabling sharing reduces base rewards."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        per_pct = int(BM_PER_TOOL_REWARD * 100)
        if getattr(self, "_screen_size_pref", "") == "mobile":
            message = (
                f"Turning off {service_label} will reduce your base \n"
                f"fVPN rewards by {per_pct}%.\n\n"
                "Are you sure you want to disable it?"
            )
        else:
            message = (
                f"Turning off {service_label} will reduce your base fVPN rewards by {per_pct}%.\n\n"
                "Are you sure you want to disable it?"
            )

        logger.debug("Prompting disable confirmation for %s", service_label)

        dlg = QtWidgets.QMessageBox(self)
        dlg.setWindowTitle(f"Disable {service_label} Sharing?")
        dlg.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dlg.setText(message)
        dlg.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        dlg.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Yes
        )
        dlg.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)

        # Apply FryNetworks theme to dialog
        apply_fry_theme_to_dialog(dlg)

        if getattr(self, "_screen_size_pref", "") == "mobile":
            # Clamp width and allow text wrapping on small screens
            dlg.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, False)
            dlg.setSizeGripEnabled(False)
            dlg.setStyleSheet(
                "QLabel{min-width:0px; max-width:340px;}"
                "QPushButton{min-width:60px; max-width:140px;}"
                "QMessageBox{min-width:380px; max-width:380px;}"
            )
            dlg.setMinimumWidth(380)
            dlg.setMaximumWidth(380)
            dlg.setFixedWidth(380)

        return dlg.exec() == QtWidgets.QMessageBox.StandardButton.Yes

    def _create_bandwidth_display_in_layout(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Create bandwidth monitoring display."""
        self.dlLabel = QtWidgets.QLabel("DL: - Mbps")
        self.ulLabel = QtWidgets.QLabel("UL: - Mbps")

        for lbl in (self.dlLabel, self.ulLabel):
            lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Fixed)

        container = QtWidgets.QWidget()
        if getattr(self, "_screen_size_pref", "") == "mobile":
            inner: QtWidgets.QBoxLayout = QtWidgets.QHBoxLayout(container)
            inner.setContentsMargins(0, 0, 0, 2)
            inner.setSpacing(6)
            font = self.dlLabel.font()
            font.setPointSize(max(font.pointSize() - 1, 9))
            self.dlLabel.setFont(font)
            self.ulLabel.setFont(font)
        else:
            inner = QtWidgets.QVBoxLayout(container)
            inner.setContentsMargins(0, 0, 0, 4)
            inner.setSpacing(2)
        inner.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(self.dlLabel, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(self.ulLabel, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(container, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        
        # Add charts
        try:
            self.hourlyChart = HourlyBar()
            self.rollingChart = Rolling7Bar()
            layout.addWidget(self.hourlyChart)
            layout.addWidget(self.rollingChart)
        except Exception:
            self.hourlyChart = QtWidgets.QLabel("Chart unavailable")
            self.rollingChart = QtWidgets.QLabel("Chart unavailable")
            layout.addWidget(self.hourlyChart)
            layout.addWidget(self.rollingChart)
            
    def _create_audio_display_in_layout(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Create audio level display."""
        self.dbLabel = QtWidgets.QLabel("Level: - dBFS")
        layout.addWidget(self.dbLabel)
        
        # Create level indicator
        self.levelBar = QtWidgets.QProgressBar()
        self.levelBar.setRange(-90, 0)
        self.levelBar.setValue(-90)
        layout.addWidget(self.levelBar)
        
    def _create_gnss_display_in_layout(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Create GNSS data display using SatellitePanel."""
        self.live_panel = SatellitePanel(width=800)
        try:
            # If the panel is destroyed (e.g., by layout changes), clear the reference
            self.live_panel.destroyed.connect(lambda: setattr(self, 'live_panel', None))  # type: ignore[attr-defined]
        except Exception:
            pass
        layout.addWidget(self.live_panel)
        
    def _create_radiation_display_in_layout(self, layout: QtWidgets.QVBoxLayout) -> None:
        """Create radiation monitoring display using GeigerPanel."""
        self.live_panel = GeigerPanel(width=800)
        try:
            self.live_panel.destroyed.connect(lambda: setattr(self, 'live_panel', None))  # type: ignore[attr-defined]
        except Exception:
            pass
        layout.addWidget(self.live_panel)
        
    def _create_historical_data_section(self) -> None:
        """Create historical data visualization section using rewards history."""
        try:
            # Start and ensure we create the tab widget first so UI never disappears
            try:
                log_step("historical_section_begin")
            except Exception:
                pass

            # Create tab widget to hold live (and optional history) data
            if not hasattr(self, 'data_tabs'):
                self.data_tabs = QtWidgets.QTabWidget()
                logging.getLogger(__name__).info("data_tabs QTabWidget created")

                # Live Data tab (skip for miners without live panels)
                # Note: SDN and RDN have LiveData panels (SdnPanel, RdnPanel)
                live_skips: set[str] = set()
                if MINER_CODE.upper() not in live_skips:
                    live_tab = QtWidgets.QWidget()
                    live_layout = QtWidgets.QVBoxLayout(live_tab)
                    if hasattr(self, 'liveGb'):
                        live_layout.addWidget(self.liveGb)
                    self.data_tabs.addTab(live_tab, "Live Data")
                else:
                    placeholder = QtWidgets.QLabel("Live data is not available for this miner type.")
                    placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                    placeholder_tab = QtWidgets.QWidget()
                    ph_layout = QtWidgets.QVBoxLayout(placeholder_tab)
                    ph_layout.addWidget(placeholder)
                    self.data_tabs.addTab(placeholder_tab, "Live Data")
                try:
                    log_step("data_tabs_live_added")
                except Exception:
                    pass

                # Add Data History tab for miners with sensor data (BM, IDM, ODM, ISM, OSM, IRM)
                if MINER_CODE.upper() in ("BM", "IDM", "ODM", "ISM", "OSM", "IRM"):
                    try:
                        self.data_history_widget = DataHistoryWidget()
                        self.data_tabs.addTab(self.data_history_widget, "Data History")
                        try:
                            log_step("data_history_tab_added")
                        except Exception:
                            pass
                    except Exception as dh_exc:
                        try:
                            log_step("data_history_tab_failed", {"error": str(dh_exc)})
                        except Exception:
                            pass

            # Create the new Rewards History widget (after tabs exist so failure won't hide UI)
            is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
            screen_pref = "mobile" if is_mobile else ""
            rewards_widget: QtWidgets.QWidget
            try:
                self.history_widget = RewardsHistoryWidget(screen_size_pref=screen_pref)
                rewards_widget = self.history_widget
                logging.getLogger(__name__).info("RewardsHistoryWidget created successfully")
                try:
                    log_step("rewards_history_widget_ok")
                except Exception:
                    pass
            except Exception as rh_exc:
                logging.getLogger(__name__).error(f"RewardsHistoryWidget failed: {rh_exc}")
                # Fallback if rewards history creation fails
                fallback = QtWidgets.QLabel(
                    "Rewards History\n"
                    f"Error: {str(rh_exc)}\n\n"
                    "Install matplotlib for chart functionality."
                )
                fallback.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                fallback.setStyleSheet("""
                    QLabel {
                        background-color: #FEF3C7;
                        border: 1px solid #F59E0B;
                        border-radius: 6px;
                        padding: 20px;
                        color: #92400E;
                        font-size: 12px;
                    }
                """)
                rewards_widget = fallback
                self.history_widget = fallback
                try:
                    log_step("rewards_history_widget_failed", {"error": str(rh_exc)})
                except Exception:
                    pass

            # Add Rewards History tab (replaces old Connectivity History)
            try:
                self.data_tabs.addTab(rewards_widget, "Rewards History")
                logging.getLogger(__name__).info("Rewards History tab added")
                try:
                    log_step("rewards_history_tab_added")
                except Exception:
                    pass
            except Exception as tab_exc:
                logging.getLogger(__name__).error(f"Adding Rewards History tab failed: {tab_exc}")
                try:
                    log_step("rewards_history_tab_failed", {"error": str(tab_exc)})
                except Exception:
                    pass

            # Auto-refresh when tabs become active
            try:
                self.data_tabs.currentChanged.connect(self._on_tab_changed)
            except Exception:
                pass

            try:
                log_step("data_tabs_created", {"tabs": [self.data_tabs.tabText(i) for i in range(self.data_tabs.count())]})
            except Exception:
                logging.getLogger(__name__).info("data_tabs created (could not enumerate tabs)")
            
        except Exception as e:
            logging.getLogger(__name__).error(f"_create_historical_data_section failed: {e}", exc_info=True)
            try:
                log_step("historical_section_failed", {"error": str(e)})
            except Exception:
                pass
        
    def _create_status_section(self) -> None:
        """Create status display section."""
        self.statusLabel = QtWidgets.QLabel("")
        self.statusLabel.setWordWrap(False)
        self.statusLabel.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.statusLabel.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.statusLabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        
    def _setup_layouts(self) -> None:
        """Set up the main layout structure."""
        main_layout = QtWidgets.QVBoxLayout(self)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        main_layout.setSpacing(1 if is_mobile else 8)
        
        # Add banner
        main_layout.addWidget(self.banner)
        
        # Add API warning banner (shown only when API is unavailable)
        if self.api_warning_banner:
            main_layout.addWidget(self.api_warning_banner)

        # Add stale-data warning banner (shown when lastUpdated > 15 min old)
        if self.stale_data_banner:
            main_layout.addWidget(self.stale_data_banner)

        # Add form
        form_widget = QtWidgets.QWidget()
        form_widget.setLayout(self.form)
        main_layout.addWidget(form_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        
        # Add settings
        self._setup_settings_layout()
        if getattr(self, "_screen_size_pref", "") == "mobile":
            main_layout.addWidget(self.settingsGb, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        else:
            main_layout.addWidget(self.settingsGb)
        
        # Add data tabs (Live Data + Connectivity History)
        if hasattr(self, 'data_tabs'):
            main_layout.addWidget(self.data_tabs, 1)
        
        # Add status bar (removed manual Start/Stop buttons - service runs automatically)
        status_layout = QtWidgets.QHBoxLayout()
        status_layout.addWidget(self.statusLabel)
        status_layout.addStretch()
        
        status_widget = QtWidgets.QWidget()
        status_widget.setLayout(status_layout)
        main_layout.addWidget(status_widget, 0, QtCore.Qt.AlignmentFlag.AlignBottom)
        
    def _setup_settings_layout(self) -> None:
        """Set up the settings section layout."""
        layout = QtWidgets.QVBoxLayout(self.settingsGb)
        is_mobile = getattr(self, "_screen_size_pref", "") == "mobile"
        if is_mobile:
            layout.setContentsMargins(6, 2, 6, 6)
            layout.setSpacing(1)
        else:
            layout.setContentsMargins(8, 4, 8, 8)
            layout.setSpacing(4)

        if is_mobile:
            # Mobile: stack network/MAC info and device selectors vertically to avoid overlap
            info_grid = QtWidgets.QGridLayout()
            info_grid.setContentsMargins(0, 0, 0, 0)
            info_grid.setHorizontalSpacing(6)
            info_grid.setVerticalSpacing(2)
            if hasattr(self, 'networkLabel'):
                info_grid.addWidget(self.networkLabel, 0, 0)
                info_grid.addWidget(self.networkValueLabel, 0, 1)
                info_grid.addWidget(self.macTitle, 1, 0)
                info_grid.addWidget(self.macValueLabel, 1, 1)
                info_grid.addWidget(self.macRegisteredTitle, 2, 0)
                info_grid.addWidget(self.macRegisteredValue, 2, 1)
            warn_row = QtWidgets.QHBoxLayout()
            warn_row.setContentsMargins(0, 0, 0, 0)
            warn_row.setSpacing(4)
            warn_row.addWidget(self.macMatchCheck)
            warn_row.addWidget(self.registrationStatusIcon)
            warn_row.addWidget(self.registrationStatusLabel, 1)
            if hasattr(self, 'deviceLabel'):
                device_row = QtWidgets.QHBoxLayout()
                device_row.setContentsMargins(0, 0, 0, 0)
                device_row.setSpacing(6)
                self.deviceLabel.setWordWrap(True)
                self.deviceLabel.setMaximumWidth(120)
                device_row.addWidget(self.deviceLabel)
                self.deviceCombo.setMinimumContentsLength(12)
                self.deviceCombo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                device_row.addWidget(self.deviceCombo, 1)
                layout.addLayout(device_row)

                if hasattr(self, 'baudLabel'):
                    baud_row = QtWidgets.QHBoxLayout()
                    baud_row.setContentsMargins(0, 0, 0, 0)
                    baud_row.setSpacing(6)
                    self.baudLabel.setWordWrap(True)
                    self.baudLabel.setMaximumWidth(60)
                    baud_row.addWidget(self.baudLabel)
                    self.baudCombo.setMinimumContentsLength(3)
                    self.baudCombo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                    self.baudCombo.setMaximumWidth(80)
                    size_pol = self.baudCombo.sizePolicy()
                    size_pol.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Fixed)
                    self.baudCombo.setSizePolicy(size_pol)
                    baud_row.addWidget(self.baudCombo, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
                    layout.addLayout(baud_row)

                if hasattr(self, 'btnApplyMic'):
                    device_row.addWidget(self.btnApplyMic)
            else:
                device_row = None

            layout.addLayout(info_grid)
            layout.addLayout(warn_row)
        else:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            if hasattr(self, 'networkLabel'):
                row.addWidget(self.networkLabel)
                row.addWidget(self.networkValueLabel)
                row.addSpacing(12)
                row.addWidget(self.macTitle)
                row.addWidget(self.macValueLabel)
                row.addSpacing(12)
                row.addWidget(self.macRegisteredTitle)
                row.addWidget(self.macRegisteredValue)
                row.addSpacing(6)
                row.addWidget(self.macMatchCheck)
                row.addWidget(self.registrationStatusIcon)
                row.addWidget(self.registrationStatusLabel)

                sep = QtWidgets.QFrame()
                sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
                sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
                row.addSpacing(12)
                row.addWidget(sep)

            if hasattr(self, 'deviceLabel'):
                row.addWidget(self.deviceLabel)
                row.addWidget(self.deviceCombo)

            if hasattr(self, 'baudLabel'):
                row.addSpacing(12)
                row.addWidget(self.baudLabel)
                row.addWidget(self.baudCombo)

            if hasattr(self, 'btnApplyMic'):
                row.addWidget(self.btnApplyMic)

            row.addStretch(1)
            layout.addLayout(row)

        if hasattr(self, 'macInfoLabel'):
            if is_mobile:
                self.registrationStatusLabel.setWordWrap(True)
                self.registrationStatusLabel.setMaximumWidth(360)
                self.registrationStatusIcon.setContentsMargins(0, 4, 0, 0)
                self.macInfoLabel.setWordWrap(True)
                self.macInfoLabel.setMaximumWidth(480)
            self.macInfoLabel.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.macInfoLabel)
        
    def _setup_live_data_layout(self) -> None:
        """Set up the live data section layout."""
        # If we have a LiveData panel, layout is already handled
        if hasattr(self, 'live_panel') and self.live_panel:
            return
            
        # Otherwise set up fallback layout
        layout = QtWidgets.QVBoxLayout(self.liveGb)
        
        # Data labels
        data_layout = QtWidgets.QHBoxLayout()
        
        if hasattr(self, 'dlLabel'):
            data_layout.addWidget(self.dlLabel)
            data_layout.addWidget(self.ulLabel)
        elif hasattr(self, 'dbLabel'):
            data_layout.addWidget(self.dbLabel)
            if hasattr(self, 'levelBar'):
                data_layout.addWidget(self.levelBar)
        elif self.live_panel is not None:
            # For Satellite and Radiation miners using modern panel widgets
            data_layout.addWidget(self.live_panel)
            
        data_layout.addStretch()
        layout.addLayout(data_layout)
        
        # Charts (for bandwidth miners)
        if hasattr(self, 'hourlyChart'):
            layout.addWidget(QtWidgets.QLabel("24-Hour Chart:"))
            layout.addWidget(self.hourlyChart)
            layout.addWidget(QtWidgets.QLabel("7-Day Rolling Chart:"))
            layout.addWidget(self.rollingChart)
            
    def _connect_signals(self) -> None:
        """Connect UI signals to slots."""
        if hasattr(self, 'btnApplyMic'):
            self.btnApplyMic.clicked.connect(self._apply_microphone_selection)
            self.deviceCombo.currentIndexChanged.connect(self._on_microphone_selection_changed)
        
        # Connect serial port and baud rate changes for Satellite/Radiation miners
        if GROUP in ("Satellite", "Radiation") and hasattr(self, 'deviceCombo'):
            self.deviceCombo.currentIndexChanged.connect(self._on_serial_device_changed)
            if hasattr(self, 'baudCombo'):
                self.baudCombo.currentIndexChanged.connect(self._on_serial_device_changed)

        # No refresh/register buttons per product decision; comparison happens automatically on status load
    
    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change and trigger refresh on Data History and Rewards History tabs."""
        try:
            if hasattr(self, 'data_tabs'):
                tab_name = self.data_tabs.tabText(index)
                # Pause live polling when not on Live Data tab
                if tab_name == "Live Data":
                    self._start_live_monitoring()
                else:
                    self._stop_live_worker()
                if tab_name == "Data History" and hasattr(self, 'data_history_widget'):
                    # Auto-refresh when opening Data History tab
                    if self.data_history_widget is not None and hasattr(self.data_history_widget, '_load_data'):
                        self.data_history_widget._load_data()
                elif tab_name == "Rewards History":
                    # Auto-refresh when opening Rewards History tab
                    if hasattr(self, 'history_widget') and self.history_widget is not None and hasattr(self.history_widget, '_load_data'):
                        self.history_widget._load_data()
        except Exception:
            pass
            
    def _load_miner_key(self) -> None:
        """Load the miner key from storage."""
        try:
            key = read_miner_key()
            if key:
                self.keyEdit.setText(key)
        except Exception as e:
            log_step("Error loading miner key", {"error": str(e)})
            
    def _populate_device_selectors(self) -> None:
        """Populate device selector dropdowns."""
        # Always populate network interfaces first for MAC discovery
        network_helpers.populate_network_interfaces(self)

        if GROUP == "Decibel":
            self._populate_microphones()
        elif GROUP in ("Satellite", "Radiation"):
            self._populate_serial_ports()
        elif GROUP in ("BM", "Bandwidth"):  # keep Bandwidth as legacy alias
            # Already populated network interfaces; nothing extra
            pass
            
    def _populate_microphones(self) -> None:
        """Populate microphone selector."""
        if not HAVE_SD or not hasattr(self, 'deviceCombo'):
            return

        try:
            import sounddevice as sd
            devices = sd.query_devices()

            self.deviceCombo.clear()
            self.deviceCombo.addItem("Default input", None)

            # Get saved microphone and host default input
            saved_mic_index = get_saved_microphone()
            default_input_idx = None
            try:
                default_device = sd.default.device
                if isinstance(default_device, (list, tuple)) and default_device:
                    cand = default_device[0]
                    if isinstance(cand, int) and cand >= 0:
                        default_input_idx = cand
                elif isinstance(default_device, int) and default_device >= 0:
                    default_input_idx = default_device
                if default_input_idx is None:
                    try:
                        default_info = sd.query_devices(None, 'input')
                        if isinstance(default_info, dict):
                            cand = default_info.get('index')
                            if isinstance(cand, int) and cand >= 0:
                                default_input_idx = cand
                    except Exception:
                        pass
            except Exception:
                pass

            index_map: Dict[int, int] = {}
            combo_idx = 1  # Start at 1 because "Default input" is at 0
            for i, device in enumerate(devices):
                # Handle sounddevice device info (dict format)
                try:
                    # Devices are returned as dictionaries
                    if isinstance(device, dict):
                        max_channels = device.get('max_input_channels', 0)
                        device_name = device.get('name', 'Unknown')
                        host_api = str(device.get('hostapi', 'Unknown'))
                    else:
                        # Fallback for non-dict format
                        max_channels = getattr(device, 'max_input_channels', 0)
                        device_name = getattr(device, 'name', 'Unknown')
                        host_api = str(getattr(device, 'hostapi', 'Unknown'))

                    if max_channels > 0:
                        # Filter out virtual/system devices - only show real microphones
                        device_name_lower = device_name.lower()
                        skip_patterns = [
                            'mapper', 'capture driver', 'sound driver',
                            'mixage', 'stereo mix', 'wave out mix',
                            'ligne', 'line in', 'what u hear'
                        ]
                        if any(pattern in device_name_lower for pattern in skip_patterns):
                            continue
                            
                        name = f"{device_name} (API {host_api})"
                        self.deviceCombo.addItem(name, i)
                        index_map[i] = combo_idx
                        combo_idx += 1
                except Exception:
                    # Fallback: just add device index
                    self.deviceCombo.addItem(f"Device {i}", i)
                    index_map[i] = combo_idx
                    combo_idx += 1

            # Restore saved selection, otherwise choose default input, otherwise first item
            selected_combo_index = None
            if saved_mic_index is not None and saved_mic_index in index_map:
                selected_combo_index = index_map[saved_mic_index]
                log_step("restored_microphone", {"index": saved_mic_index})
            elif default_input_idx is not None and default_input_idx in index_map:
                selected_combo_index = index_map[default_input_idx]
                log_step("default_microphone_selected", {"index": default_input_idx})
            elif index_map:
                selected_combo_index = 0
                log_step("auto_microphone_first_available", {"index": list(index_map.keys())[0]})
            else:
                selected_combo_index = 0  # Default input placeholder

            if selected_combo_index is not None:
                self.deviceCombo.setCurrentIndex(selected_combo_index)

        except Exception as e:
            log_step("Error populating microphones", {"error": str(e)})
        
    def _populate_serial_ports(self) -> None:
        """Populate serial port selector."""
        if not HAVE_SERIAL or not hasattr(self, 'deviceCombo'):
            return
            
        try:
            import serial.tools.list_ports  # type: ignore
            ports = serial.tools.list_ports.comports()
            
            self.deviceCombo.clear()
            self.deviceCombo.addItem("Select port...", None)
            
            # Get saved port
            saved_port = get_saved_serial_port()
            saved_index = 0
            
            for idx, port in enumerate(ports, start=1):
                desc = str(port.description or "").strip()
                # Avoid duplicating COM port name and trailing (COMx)
                dev = str(port.device)
                if desc.upper().startswith(dev.upper()):
                    desc = desc[len(dev):].lstrip(" -")
                if desc.endswith(f"({dev})"):
                    desc = desc[: -len(f"({dev})")].rstrip(" -")
                label = f"{port.device}"
                if desc:
                    label = f"{label} - {desc}"
                if getattr(self, "_screen_size_pref", "") == "mobile":
                    label = (label[:38] + "…") if len(label) > 39 else label
                self.deviceCombo.addItem(label, port.device)
                
                # Check if this matches saved port
                if saved_port and port.device == saved_port:
                    saved_index = idx
            
            # Restore saved selection
            if saved_index > 0:
                self.deviceCombo.setCurrentIndex(saved_index)
                log_step("restored_serial_port", {"port": saved_port})
            
            # Restore saved baud rate
            if hasattr(self, 'baudCombo'):
                saved_baud = get_saved_baud_rate()
                if saved_baud:
                    baud_text = str(saved_baud)
                    for i in range(self.baudCombo.count()):
                        if self.baudCombo.itemText(i) == baud_text:
                            self.baudCombo.setCurrentIndex(i)
                            log_step("restored_baud_rate", {"baud": saved_baud})
                            break
                            
        except Exception as e:
            log_step("Error populating serial ports", {"error": str(e)})

    def _load_status_data(self) -> None:
        """Placeholder: status JSON path deprecated; use CSV LiveData instead."""
        # With CSV-only architecture, we no longer read measurements/latest.json.
        # Keep badges neutral and avoid raising dialogs.
        self._latest_measurements = None
        self._last_measurement_timestamp = None
        self._last_pod_ok = None
        self._last_pod_error = None
        try:
            pod_badge_helpers.update_pod_badge(self, None, None)
        except Exception:
            pass
        self._refresh_footer_status()

    def _propagate_measurements_to_widgets(self) -> None:
        """Propagate measurement data to child widgets that support it."""
        if not self._latest_measurements:
            return
        
        # Update panels that have update_with_measurements method
        widgets_to_update = [
            self.honeygain_panel,
            self.bright_panel,
            self.mysterium_panel,
            self.history_widget,
            self.data_history_widget,
        ]
        
        for widget in widgets_to_update:
            if widget is not None:
                measurement_display.update_widget_with_measurements(
                    widget, self._latest_measurements
                )

    def _check_measurement_freshness(self) -> None:
        """Staleness check disabled for CSV-only architecture."""
        self._last_pod_error = None
        self._refresh_footer_status()

    def _pod_supported(self) -> bool:
        """Return True if this miner type should show PoD badge (measurement-based)."""
        code = str(MINER_CODE).upper()
        group = str(GROUP).lower()
        code_ok = code in {"BM", "IRM", "ISM", "OSM", "IDM", "ODM"}
        group_ok = group in {"bandwidth", "radiation", "satellite", "decibel"}
        return bool(code_ok or group_ok)
     
    def _on_microphone_selection_changed(self) -> None:
        """Handle microphone selection change."""
        if hasattr(self, 'btnApplyMic'):
            self.btnApplyMic.setVisible(True)
    
    def _apply_microphone_selection(self) -> None:
        """Apply microphone selection and restart monitoring."""
        if hasattr(self, 'btnApplyMic'):
            self.btnApplyMic.setVisible(False)
        
        # Save selection
        if hasattr(self, 'deviceCombo'):
            device_idx = self.deviceCombo.currentData()
            device_name = self.deviceCombo.currentText()
            if device_idx is not None:
                save_microphone_settings(device_idx, device_name)
                log_step("saved_microphone_selection", {"index": device_idx, "name": device_name})
        
        # Restart live monitoring with new device
        self._start_live_monitoring()
    
    def _on_serial_device_changed(self) -> None:
        """Handle serial device or baud rate selection change."""
        # Immediately block worker signals and stop current worker to avoid
        # any pending UI updates while selection changes
        self._stop_live_worker()

        # Persist selection early to ProgramData
        try:
            if hasattr(self, 'deviceCombo'):
                sel = self.deviceCombo.currentData()
                port = str(sel) if sel is not None else None
                baud_val = None
                if hasattr(self, 'baudCombo'):
                    try:
                        baud_val = int(self.baudCombo.currentText())
                    except Exception:
                        baud_val = None
                if port:
                    # Persist only valid baud values; default to 9600 if unknown
                    save_serial_settings(port, int(baud_val) if isinstance(baud_val, int) else 9600)
        except Exception:
            pass

        # Use a timer to delay restart slightly - prevents UI freezing
        # when user is quickly changing selections
        if hasattr(self, '_restart_timer'):
            try:
                self._restart_timer.stop()
            except Exception:
                pass
        
        self._restart_timer = QtCore.QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._restart_monitoring_after_delay)
        self._restart_timer.start(350)  # shorter delay for responsiveness
    
    def _restart_monitoring_after_delay(self) -> None:
        """Actually restart monitoring after delay."""
        if hasattr(self, 'deviceCombo') and self.deviceCombo.currentData() is not None:
            self._start_live_monitoring()
        
    def _start_live_monitoring(self) -> None:
        """Start live data polling (CSV-based) for the active sensor group."""
        self._stop_live_worker()

        sensor = self._sensor_name_for_group()
        if not sensor:
            return

        interval_ms = self._live_poll_interval_ms(sensor)
        try:
            self._live_poll_timer = QtCore.QTimer(self)
            self._live_poll_timer.setInterval(interval_ms)
            self._live_poll_timer.timeout.connect(lambda: self._poll_live_data(sensor))
            self._live_poll_timer.start()
            self._set_live_panel_device_label()
            # Poll immediately so UI updates without waiting for first interval
            self._poll_live_data(sensor)
        except Exception as exc:
            log_step("live_poll_timer_start_failed", {"error": str(exc)})

    def _live_poll_interval_ms(self, sensor: str) -> int:
        """Return polling interval in milliseconds for a sensor name."""
        sensor_lower = sensor.lower()
        if sensor_lower in ("bm", "decibel"):
            return 2000
        if sensor_lower in ("satellite", "radiation"):
            return 10000
        if sensor_lower == "aem":
            return 15000
        return 5000

    def _sensor_name_for_group(self) -> Optional[str]:
        """Map GROUP to sensor name used in CSV filenames."""
        g = str(GROUP).lower()
        if g in ("bm", "bandwidth"):
            return "bm"
        if g == "satellite":
            return "satellite"
        if g == "radiation":
            return "radiation"
        if g == "decibel":
            return "decibel"
        if g == "aem":
            return "aem"
        return None

    def _poll_live_data(self, sensor: str) -> None:
        """Read last line from service CSV and push to UI updater."""
        try:
            # AEM reads from weekly JSON (data gate) instead of CSV
            if sensor.lower() == "aem":
                self._poll_aem_live_data()
                return
            
            # Read API availability + lastUpdated from weekly JSON (applies to all miners)
            api_available = None
            last_updated = None
            try:
                import datetime
                from miner_GUI.utils.status_week import load_status_week_for_date
                today = datetime.datetime.utcnow().date()
                week_doc = load_status_week_for_date(today)
                if isinstance(week_doc, dict):
                    api_available = week_doc.get("api_available")
                    last_updated = week_doc.get("lastUpdated")
            except Exception:
                pass

            row = read_last_line_for_sensor(sensor)
            if not row:
                err = None
                detected_baud = None
                try:
                    import json
                    from pathlib import Path
                    for subdir in ("measurements", "logs"):
                        sidecar = data_dir_gui() / subdir / f"{sensor}_status.json"
                        if sidecar.exists():
                            with open(sidecar, "r", encoding="utf-8") as f:
                                payload = json.load(f)
                            err = payload.get("err")
                            detected_baud = payload.get("_detected_baud")
                            if err:
                                break
                except Exception:
                    pass
                live_data = {"err": err or "no data", "api_available": api_available, "lastUpdated": last_updated}
                if detected_baud:
                    live_data["detected_baud"] = detected_baud
                self._update_live_data(live_data)
                return
            data = self._map_row_to_live_data(sensor, row)
            data["api_available"] = api_available
            data["lastUpdated"] = last_updated
            self._update_live_data(data)
        except Exception as exc:
            self._update_live_data({"err": str(exc)})

    def _poll_aem_live_data(self) -> None:
        """Poll AEM status from CSV (fast updates) + weekly JSON (mac_mismatch, api_available)."""
        try:
            import datetime
            from miner_GUI.utils.status_week import load_status_week_for_date
            from miner_GUI.utils.csv_reader import read_last_line
            from miner_GUI.utils.data import data_dir_gui

            # Get mac_mismatch, api_available, and lastUpdated from weekly JSON
            mac_mismatch = None
            api_available = None
            last_updated = None
            today = datetime.datetime.utcnow().date()
            week_doc = load_status_week_for_date(today)
            if isinstance(week_doc, dict):
                mac_mismatch = week_doc.get("mac_mismatch")
                api_available = week_doc.get("api_available")
                last_updated = week_doc.get("lastUpdated")

            # Read live status from CSV for faster updates (every 15 seconds)
            # CSV columns: timestamp, olostep_running, olostep_enabled, status
            online_val = None
            data_val = None
            date_str = datetime.datetime.now().strftime('%Y%m%d')
            csv_path = data_dir_gui() / "measurements" / f"aem_live_{date_str}.csv"
            row = read_last_line(csv_path)
            if row:
                # olostep_running AND olostep_enabled = Olostep Browser is working
                olostep_running = self._csv_bool(row.get("olostep_running"))
                olostep_enabled = self._csv_bool(row.get("olostep_enabled"))
                status = (row.get("status") or "").strip().lower()

                # data gate: both running and enabled
                data_val = olostep_running and olostep_enabled
                # online gate: status is "online"
                online_val = (status == "online")

            self._update_live_data({
                "mac_mismatch": mac_mismatch,
                "api_available": api_available,
                "lastUpdated": last_updated,
                "online": online_val,
                "data": data_val,
            })
        except Exception as exc:
            self._update_live_data({"err": str(exc)})

    @staticmethod
    def _csv_bool(value) -> bool:
        """Parse CSV boolean value (handles 'true', 'false', '1', '0', etc.)."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        s = str(value).strip().lower()
        return s in ("true", "1", "yes", "y")

    def _map_row_to_live_data(self, sensor: str, row: dict) -> dict:
        """Normalize CSV row values to UI-friendly data dict."""
        s = sensor.lower()
        if s == "bm":
            return {
                "dl": parse_float(row.get("dl")),
                "ul": parse_float(row.get("ul")),
                "iface": row.get("iface"),
            }
        if s == "decibel":
            return {
                "dbfs": parse_float(row.get("dbfs"), default=0.0),
            }
        if s == "satellite":
            return {
                "sats": parse_int(row.get("sats")),
                "fix": row.get("fix"),
                "lat": parse_float(row.get("lat")) if row.get("lat") not in (None, "") else None,
                "lon": parse_float(row.get("lon")) if row.get("lon") not in (None, "") else None,
                "alt": parse_float(row.get("alt")) if row.get("alt") not in (None, "") else None,
                "hdop": parse_float(row.get("hdop")) if row.get("hdop") not in (None, "") else None,
            }
        if s == "radiation":
            return {
                "cpm": parse_float(row.get("cpm")),
                "usv": parse_float(row.get("usv")),
                "usv_hour": parse_float(row.get("usv_hour")),
                "mr": parse_float(row.get("mr")),
                "cps": parse_float(row.get("cps")),
            }
        if s == "aem":
            # AEM uses "data" gate (PoD) as proof of Olostep Browser running
            data_val = row.get("data")
            return {"data": data_val if data_val not in ("", None) else None}
        return row

    def _set_live_panel_device_label(self) -> None:
        """Update device label on LiveData panel (if supported)."""
        try:
            if hasattr(self, 'live_panel') and self.live_panel is not None and hasattr(self.live_panel, 'set_device_label'):
                device_label = None
                if GROUP == "Decibel" and hasattr(self, 'deviceCombo'):
                    device_label = self.deviceCombo.currentText() or "Default input"
                elif GROUP in ("Satellite", "Radiation") and hasattr(self, 'deviceCombo'):
                    device_label = self.deviceCombo.currentText() or "No device"
                if not device_label:
                    device_label = "Auto-detected"
                self.live_panel.set_device_label(device_label)  # type: ignore[attr-defined]
        except Exception:
            pass
    
    def _live_panel_width_hint(self) -> int:
        """Return width hint for LiveData panels based on screen size preference."""
        pref = getattr(self, "_screen_size_pref", "desktop")
        if pref == "mobile":
            return 520
        if pref == "tablet":
            return 700
        if pref == "laptop":
            return 820
        if pref == "desktop":
            return 900
        return 1000

    def _check_api_status(self) -> None:
        """Check API availability and data staleness from weekly JSON."""
        try:
            import datetime
            from miner_GUI.utils.status_week import load_status_week_for_date

            today = datetime.datetime.utcnow().date()
            week_doc = load_status_week_for_date(today)
            if isinstance(week_doc, dict):
                api_available = week_doc.get("api_available")
                api_last_updated = week_doc.get("api_last_updated")
                last_updated = week_doc.get("lastUpdated")
                
                # Banner priority: Stale > API > Other
                # First check stale data (highest priority)
                stale_showing = self._update_stale_data_banner(last_updated)
                
                # Only show API banner if stale banner is NOT showing
                if not stale_showing:
                    self._update_api_warning_banner(api_available, api_last_updated)
                else:
                    # Hide API banner when stale banner is showing (priority)
                    if self.api_warning_banner and not self.api_warning_banner.isHidden():
                        self.api_warning_banner.hide()
        except Exception as exc:
            logger.debug(f"Failed to check API status: {exc}")

    def _update_api_warning_banner(self, api_available: Optional[bool], api_last_updated: Optional[str] = None) -> None:
        """Show or hide the API warning banner based on api_available status or stale api_last_updated."""
        try:
            if not self.api_warning_banner:
                return
            
            # Update internal state
            if api_available is not None:
                self._api_available = api_available
            
            # Check if api_last_updated is stale (>15 min old)
            api_stale = False
            if api_last_updated:
                import datetime
                try:
                    api_ts = datetime.datetime.strptime(api_last_updated, "%Y-%m-%dT%H:%M:%SZ")
                    age = datetime.datetime.utcnow() - api_ts
                    api_stale = age.total_seconds() > 15 * 60  # 15 minutes
                except (ValueError, TypeError):
                    pass
            
            # Show banner when API is explicitly False OR api_last_updated is stale
            if api_available is False or api_stale:
                if self.api_warning_banner.isHidden():
                    self.api_warning_banner.show()
            else:
                # Hide banner when API is available or status is unknown
                if not self.api_warning_banner.isHidden():
                    self.api_warning_banner.hide()
        except Exception as exc:
            logger.warning(f"Failed to update API warning banner: {exc}")

    def _update_stale_data_banner(self, last_updated_str: Optional[str]) -> bool:
        """Show or hide the stale-data banner when lastUpdated is >15 min old.
        
        Returns True if stale banner is showing (for banner priority logic).
        """
        try:
            if not self.stale_data_banner:
                return False

            if not last_updated_str:
                # No timestamp available – hide banner (don't warn on missing data)
                if not self.stale_data_banner.isHidden():
                    self.stale_data_banner.hide()
                return False

            import datetime
            try:
                last_updated = datetime.datetime.strptime(last_updated_str, "%Y-%m-%dT%H:%M:%SZ")
            except (ValueError, TypeError):
                if not self.stale_data_banner.isHidden():
                    self.stale_data_banner.hide()
                return False

            age = datetime.datetime.utcnow() - last_updated
            stale = age.total_seconds() > 15 * 60  # 15 minutes

            if stale:
                mins = int(age.total_seconds() // 60)
                self._stale_data_message.setText(
                    f"<b>Status Data Is Stale</b> \u2014 The local status file has not been updated in "
                    f"{mins} minutes. The miner service may need attention."
                )
                if self.stale_data_banner.isHidden():
                    self.stale_data_banner.show()
                return True
            else:
                if not self.stale_data_banner.isHidden():
                    self.stale_data_banner.hide()
                return False
        except Exception as exc:
            logger.warning(f"Failed to update stale-data banner: {exc}")
            return False

    def _update_live_data(self, data: dict) -> None:
        """Update live data display."""
        try:
            # Update banners - use the same priority logic as _check_api_status()
            # Banner priority: Stale > API > Other
            stale_showing = False
            if "lastUpdated" in data:
                stale_showing = self._update_stale_data_banner(data.get("lastUpdated"))
            
            # Update API warning banner ONLY if both api_available AND api_last_updated are present
            # This prevents live data (which may not have api_last_updated) from overriding
            # the timer-based check that reads the full weekly JSON
            if "api_available" in data and "api_last_updated" in data:
                if not stale_showing:
                    self._update_api_warning_banner(
                        data.get("api_available"),
                        data.get("api_last_updated")
                    )
                else:
                    # Hide API banner when stale banner is showing (priority)
                    if self.api_warning_banner and not self.api_warning_banner.isHidden():
                        self.api_warning_banner.hide()

            # If tab widget exists and Live Data tab not active, skip ticking panel to avoid hidden/deleted widget access
            if hasattr(self, 'data_tabs'):
                try:
                    current_tab_name = self.data_tabs.tabText(self.data_tabs.currentIndex())
                    if current_tab_name != "Live Data":
                        return
                except Exception:
                    pass

            # First, check if we have a LiveData panel and update it safely
            if self._safe_live_panel_tick(data):
                # Update status label based on errors
                if "err" in data:
                    try:
                        pod_badge_helpers.update_pod_badge(self, False, False, data.get("err"))
                    except Exception:
                        pass
                else:
                    # Mark that we've received valid live data at least once
                    self._has_received_live_data = True
                    try:
                        pod_badge_helpers.update_pod_badge(self, True, True, None)
                    except Exception:
                        pass
                return
            
            # Fallback: update traditional labels if no LiveData panel
            if "err" in data:
                try:
                    pod_badge_helpers.update_pod_badge(self, False, False, data.get("err"))
                except Exception:
                    pass
                return
                
            if GROUP in ("BM", "Bandwidth"):  # keep Bandwidth as legacy alias
                self._update_bandwidth_data(data)
            elif GROUP == "Decibel":
                self._update_audio_data(data)
            elif GROUP == "Satellite":
                self._update_gnss_data(data)
            elif GROUP == "Radiation":
                self._update_radiation_data(data)
            # Mark that we've received valid live data at least once
            self._has_received_live_data = True
            try:
                pod_badge_helpers.update_pod_badge(self, True, True, None)
            except Exception:
                pass

        except Exception as e:
            log_step("Error updating live data", {"error": str(e)})
            
    def _update_bandwidth_data(self, data: dict) -> None:
        """Update bandwidth display."""
        dl = data.get("dl", 0)
        ul = data.get("ul", 0)
        
        if hasattr(self, 'dlLabel'):
            self.dlLabel.setText(f"DL: {dl:.2f} Mbps")
        if hasattr(self, 'ulLabel'):
            self.ulLabel.setText(f"Upload: {ul:.2f} Mbps")

        # Treat successful bandwidth update as online signal for footer
        try:
            pod_badge_helpers.update_pod_badge(self, True, True, None)
        except Exception:
            pass
            
    def _update_audio_data(self, data: dict) -> None:
        """Update audio level display."""
        dbfs = data.get("dbfs")
        
        if dbfs is not None and hasattr(self, 'dbLabel'):
            self.dbLabel.setText(f"Level: {dbfs:.1f} dBFS")
            
            if hasattr(self, 'levelBar'):
                self.levelBar.setValue(int(dbfs))
                
    def _update_gnss_data(self, data: dict) -> None:
        """Update GNSS display using SatellitePanel."""
        self._safe_live_panel_tick(data)
                
    def _update_radiation_data(self, data: dict) -> None:
        """Update radiation display using GeigerPanel."""
        self._safe_live_panel_tick(data)

    def _safe_live_panel_tick(self, data: dict) -> bool:
        """Safely call on_tick on the live_panel if it is valid.

        Returns True if the tick was dispatched, False otherwise.
        Guards against RuntimeError from deleted underlying C++ Qt objects
        and missing on_tick attribute.
        """
        panel = getattr(self, 'live_panel', None)
        if panel is None:
            return False
        # Validate underlying C++ object if shiboken6 available
        try:
            if shiboken6 and hasattr(shiboken6, 'isValid'):
                try:
                    if not shiboken6.isValid(panel):  # type: ignore[attr-defined]
                        return False
                except Exception:
                    # If isValid itself errors, continue with best-effort
                    pass
            if not hasattr(panel, 'on_tick'):
                return False
            try:
                panel.on_tick(data)  # type: ignore[call-arg]
                return True
            except RuntimeError as re:  # deleted C++ object
                log_step("live_panel_invalid", {"error": str(re)})
                return False
            except Exception as e:
                log_step("live_panel_tick_error", {"error": str(e)})
                return False
        except Exception as outer:
            log_step("live_panel_tick_outer_error", {"error": str(outer)})
            return False
       
    def _apply_fry_theme(self) -> None:
        """Apply the FryNetworks black theme to the window and application."""
        try:
            if Theme:
                self._theme = Theme()
                qss = self._theme.qss()
                # Apply to QApplication so all dialogs/child windows inherit it
                app = QtWidgets.QApplication.instance()
                if isinstance(app, QtWidgets.QApplication):
                    app.setStyleSheet(qss)
                # Also apply to main window for redundancy
                self.setStyleSheet(qss)
                log_step("FryNetworks theme applied to application and main window")
            else:
                self._theme = None
                log_step("Theme module not available, using default styling")
        except Exception as e:
            self._theme = None
            log_step("Error applying FryNetworks theme", {"error": str(e)})
            
    def closeEvent(self, event) -> None:
        """Handle window close: minimize to tray instead of exiting."""
        try:
            if self._tray and self._tray.isVisible():
                # Hide window and keep service running
                event.ignore()
                self.hide()
                # Inform the user once
                if not getattr(self, "_trayNotified", False):
                    try:
                        self._tray.showMessage(
                            f"FRY {DISPLAY_NAME}",
                            "Running in background. Right-click tray icon to Exit.",
                            QtWidgets.QSystemTrayIcon.MessageIcon.Information,
                            3500,
                        )
                    except Exception:
                        pass
                    self._trayNotified = True
                return
        except Exception:
            pass
        # Fallback: if no tray, exit normally
        self._stop_live_worker()
        event.accept()

    def _stop_live_worker(self) -> None:
        """Stop live polling timer (replacement for legacy worker thread)."""
        try:
            if self._live_poll_timer:
                try:
                    self._live_poll_timer.stop()
                except Exception:
                    pass
                try:
                    self._live_poll_timer.deleteLater()
                except Exception:
                    pass
                self._live_poll_timer = None
        except Exception:
            pass

    # ---------------- Connectivity summary helpers -----------------
    def _set_status_badge(self, text: str, bg: str, fg: str = "#FFFFFF") -> None:
        try:
            if hasattr(self, 'conn_status_badge') and self.conn_status_badge:
                self.conn_status_badge.setText(text)
                self.conn_status_badge.setStyleSheet(
                    f"border-radius: 10px; padding: 4px 10px; background-color: {bg}; color: {fg}; font-weight: 600;"
                )
        except Exception:
            pass

    # MAC styling helpers
    def _style_mac_match(self, matched: bool) -> None:
        self._mac_mismatch = not matched
        try:
            if hasattr(self, 'macMatchCheck'):
                self.macMatchCheck.setChecked(matched)
        except Exception:
            pass
        self._refresh_registration_status()

    def _style_mac_unknown(self) -> None:
        self._mac_mismatch = None
        self._refresh_registration_status()

    def _update_pol_state(self, pol_verified: Optional[bool]) -> None:
        """Store PoL state and refresh the unified registration status label.

        Args:
            pol_verified: True = verified, False = mismatch, None = unknown
        """
        if pol_verified is None:
            self._pol_mismatch = None
        else:
            self._pol_mismatch = not pol_verified
        self._refresh_registration_status()

    # Combined registration status (MAC + Location)
    def _refresh_registration_status(self) -> None:
        """Update the unified registration status label using MAC + Location state.

        Each part is independently coloured via HTML rich text:
          ok      → green #059669  with ✓ prefix
          mismatch→ red   #DC2626  with ⚠ prefix
          unknown → amber #CA8A04  (no icon prefix)

        When mac_mismatch is None (pending): label hidden.
        """
        mac_mismatch = getattr(self, "_mac_mismatch", None)
        verified = getattr(self, "_verified", None)
        pol_mismatch = getattr(self, "_pol_mismatch", None)  # True/False/None

        GREEN = "#059669"
        RED = "#DC2626"
        AMBER = "#CA8A04"

        try:
            if hasattr(self, 'registrationStatusLabel') and self.registrationStatusLabel:
                # Pending state — mac_mismatch not yet known
                if mac_mismatch is None:
                    self.registrationStatusLabel.setVisible(False)
                    if hasattr(self, "registrationStatusIcon"):
                        self.registrationStatusIcon.setVisible(False)
                else:
                    # --- MAC part ---
                    if mac_mismatch:
                        mac_html = f'<span style="color:{RED};font-weight:600;">\u26a0 MAC Mismatch</span>'
                    else:
                        mac_html = f'<span style="color:{GREEN};font-weight:600;">\u2714 MAC Match</span>'

                    if verified is True:
                        # --- Location part ---
                        if pol_mismatch is True:
                            loc_html = f'<span style="color:{RED};font-weight:600;">\u26a0 Location Mismatch</span>'
                        elif pol_mismatch is False:
                            loc_html = f'<span style="color:{GREEN};font-weight:600;">\u2714 Location Verified</span>'
                        else:
                            loc_html = f'<span style="color:{AMBER};font-weight:600;">Location Unknown</span>'
                        display_html = f'{mac_html} \u00b7 {loc_html}'
                    else:
                        display_html = mac_html

                    self.registrationStatusLabel.setText(display_html)
                    # Clear stylesheet colour so HTML spans take effect
                    self.registrationStatusLabel.setStyleSheet("")
                    self.registrationStatusLabel.setVisible(True)

                    any_mismatch = bool(mac_mismatch) or (
                        bool(pol_mismatch) if verified is True else False
                    )
                    location_unknown = verified is True and pol_mismatch is None
                    if any_mismatch:
                        self.registrationStatusLabel.setToolTip(
                            "Please update your registration in the Fry Networks dashboard to receive full rewards."
                        )
                    elif location_unknown:
                        self.registrationStatusLabel.setToolTip(
                            "Location verification is pending. The proof-of-location check has not completed yet."
                        )
                    else:
                        self.registrationStatusLabel.setToolTip(
                            "Active MAC matches your registered MAC address."
                        )

                    # Icon widget no longer needed — icons are inline in text
                    if hasattr(self, "registrationStatusIcon"):
                        self.registrationStatusIcon.setVisible(False)
        except Exception:
            pass
        try:
            self._refresh_footer_status()
        except Exception:
            pass
        self._update_panel_toggles_for_mac_status()

    def _update_panel_toggles_for_mac_status(self) -> None:
        """Disable all integration panel toggles when MAC is mismatched."""
        mac_bad = bool(getattr(self, "_mac_mismatch", False))
        warning_msg = "⚠ MAC mismatch — Please update your registration in the Fry Networks dashboard before enabling this tool."

        # Bandwidth sharing panels
        for panel_name in ('honeygain_panel', 'bright_panel', 'mysterium_panel'):
            panel = getattr(self, panel_name, None)
            if panel:
                try:
                    panel.set_mac_mismatch_state(mac_bad, warning_msg if mac_bad else "")
                except Exception:
                    pass

        # Space Acres panel (standalone)
        if self.space_acres_panel is not None:
            try:
                self.space_acres_panel.set_mac_mismatch_state(mac_bad, warning_msg if mac_bad else "")
            except Exception:
                pass

        # Presearch and Diiisco panels (standalone)
        for panel_name in ('presearch_panel', 'diiisco_panel'):
            panel = getattr(self, panel_name, None)
            if panel:
                try:
                    panel.set_mac_mismatch_state(mac_bad, warning_msg if mac_bad else "")
                except Exception:
                    pass

        # LiveData embedded panels (space_acres, presearch, diiisco)
        live_panel = getattr(self, 'live_panel', None)
        if live_panel:
            for panel_name in ('space_acres_panel', 'presearch_panel', 'diiisco_panel'):
                panel = getattr(live_panel, panel_name, None)
                if panel:
                    try:
                        panel.set_mac_mismatch_state(mac_bad, warning_msg if mac_bad else "")
                    except Exception:
                        pass


    def _update_panel_offline_state(self) -> None:
        """Disable all integration panel toggles when device is offline."""
        is_offline = getattr(self, "_last_pod_ok", None) is False
        offline_msg = "\u26a0 Device is offline \u2014 tool controls are disabled until the device comes back online."

        # Bandwidth sharing panels
        for panel_name in ('honeygain_panel', 'bright_panel', 'mysterium_panel'):
            panel = getattr(self, panel_name, None)
            if panel:
                try:
                    panel.set_offline_state(is_offline, offline_msg if is_offline else "")
                except Exception:
                    pass

        # Space Acres panel (standalone)
        if self.space_acres_panel is not None:
            try:
                self.space_acres_panel.set_offline_state(is_offline, offline_msg if is_offline else "")
            except Exception:
                pass

        # Presearch and Diiisco panels (standalone)
        for panel_name in ('presearch_panel', 'diiisco_panel'):
            panel = getattr(self, panel_name, None)
            if panel:
                try:
                    panel.set_offline_state(is_offline, offline_msg if is_offline else "")
                except Exception:
                    pass

        # LiveData embedded panels (space_acres, presearch, diiisco)
        live_panel = getattr(self, 'live_panel', None)
        if live_panel:
            for panel_name in ('space_acres_panel', 'presearch_panel', 'diiisco_panel'):
                panel = getattr(live_panel, panel_name, None)
                if panel:
                    try:
                        panel.set_offline_state(is_offline, offline_msg if is_offline else "")
                    except Exception:
                        pass

    def _update_connectivity_summary(self, online_now: Optional[bool], today_percent: Optional[float], seven_day_avg: Optional[float]) -> None:
        """Update the summary box values and styles."""
        # Status badge
        if online_now is True:
            self._set_status_badge("Online", "#059669")  # emerald-600
        elif online_now is False:
            self._set_status_badge("Offline", "#DC2626")  # red-600
        else:
            self._set_status_badge("Unknown", "#374151", "#E5E7EB")  # gray-700

        # Today uptime
        try:
            if hasattr(self, 'conn_today_label') and self.conn_today_label:
                if isinstance(today_percent, (int, float)):
                    self.conn_today_label.setText(f"{today_percent:.1f}%")
                else:
                    self.conn_today_label.setText("-")
        except Exception:
            pass

        # 7-day average
        try:
            if hasattr(self, 'conn_7day_label') and self.conn_7day_label:
                if isinstance(seven_day_avg, (int, float)):
                    self.conn_7day_label.setText(f"{seven_day_avg:.1f}%")
                else:
                    self.conn_7day_label.setText("-")
        except Exception:
            pass

        # Last refresh timestamp
        try:
            if hasattr(self, 'conn_updated_label') and self.conn_updated_label:
                now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.conn_updated_label.setText(now_str)
        except Exception:
            pass

