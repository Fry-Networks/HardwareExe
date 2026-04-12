"""LiveData panel for SDN (Storage Node) miners.

Displays Space Acres farming status with toggle control, SSD selection,
farm path, and farm size configuration in tabbed layout.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter


class ToggleSwitch(QtWidgets.QCheckBox):
    """Simple toggle rendered as a pill with a circular knob.

    Emits stateChanged only when user interaction is confirmed (not blocked).
    Use setChecked() to update programmatically without triggering handlers.
    """

    def __init__(self, parent=None, width: int = 58, height: int = 28):
        super().__init__(parent)
        self._width = width
        self._height = height
        self._programmatic = False
        self._syncing = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setChecked(False)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)

    def set_syncing(self, syncing: bool) -> None:
        """Switch to blue pill when syncing/in-progress, green when fully OK."""
        if self._syncing != syncing:
            self._syncing = syncing
            self.update()

    def setChecked(self, checked: bool) -> None:
        """Set the checked state programmatically without emitting stateChanged."""
        was_blocked = self.signalsBlocked()
        self.blockSignals(True)
        try:
            super().setChecked(checked)
            self.update()
        finally:
            self.blockSignals(was_blocked)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Override mouse press to control when toggle actually changes."""
        pass

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release - trigger state change and emit signal."""
        if not self.isEnabled():
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if not self.rect().contains(event.pos()):
            return

        new_state = not self.isChecked()
        super().setChecked(new_state)
        self.update()
        event.accept()

    def sizeHint(self):  # type: ignore[override]
        return QtCore.QSize(self._width, self._height)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        radius = self._height / 2
        offset = radius
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(0, 0, self._width, self._height)

        if self.isEnabled():
            if self.isChecked():
                bg_color = QtGui.QColor("#2563EB" if self._syncing else "#22c55e")
            else:
                bg_color = QtGui.QColor("#555b6d")
        else:
            bg_color = QtGui.QColor("#2a3142")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, radius, radius)

        knob_radius = radius - 4
        if self.isChecked():
            center_x = self._width - offset
        else:
            center_x = offset

        if not self.isEnabled():
            knob_color = QtGui.QColor("#4a5162")
        else:
            knob_color = QtGui.QColor("#0b101a") if self.isChecked() else QtGui.QColor("#1f2430")
        painter.setBrush(knob_color)
        painter.drawEllipse(QtCore.QPointF(center_x, radius), knob_radius, knob_radius)


# Minimum free space (GB) for an SSD to be selectable
MIN_SSD_FREE_GB = 100
# Minimum farm size (GB)
MIN_FARM_SIZE_GB = 50
# Reserved space for node + OS (GB)
RESERVED_GB = 100


def _format_size(gb: float) -> str:
    """Format a size in GB to human-readable string."""
    if gb >= 1000:
        return f"{gb / 1000:.1f} TB"
    return f"{gb:.0f} GB"


def _farm_size_to_string(gb: int) -> str:
    """Convert farm size in GB to the string format the service expects (e.g. '100G', '1T')."""
    if gb >= 1000 and gb % 1000 == 0:
        return f"{gb // 1000}T"
    return f"{gb}G"


class StorageNodeTab(QtWidgets.QGroupBox):
    """Individual tab panel for a storage node (Space Acres)."""

    refresh_clicked = QtCore.Signal()
    toggle_changed = QtCore.Signal(bool)
    # Emitted when user clicks "Save Configuration" with (farm_path, farm_size_string)
    configure_requested = QtCore.Signal(str, str)

    def __init__(self, _title: str = "", _doc_url: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__("", parent)
        self._suspend_toggle = False
        self._mac_mismatch = False
        self._is_pending = False
        self._available_ssds: List[Dict[str, Any]] = []
        self._is_configured = False
        self._was_syncing = False
        self._was_finalizing = False
        self._is_busy = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Toggle row ---
        toggle_row = QtWidgets.QHBoxLayout()
        toggle_row.addStretch(1)

        # Toggle switch (hidden — all integrations are forced ON)
        self._toggle = ToggleSwitch(width=58, height=28)
        self._toggle.stateChanged.connect(self._on_toggle_state)
        layout.addLayout(toggle_row)

        # --- Status label ---
        self._status_label = QtWidgets.QLabel("Checking status...")
        self._status_label.setWordWrap(True)
        self._status_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self._status_label.setMinimumHeight(40)
        layout.addWidget(self._status_label)

        # --- Sync progress bar (hidden by default) ---
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
        layout.addWidget(self._sync_bar)

        # --- SSD Config section (always visible) ---
        self._config_widget = QtWidgets.QWidget()
        config_layout = QtWidgets.QVBoxLayout(self._config_widget)
        config_layout.setContentsMargins(0, 4, 0, 4)
        config_layout.setSpacing(8)

        # SSD selection
        ssd_label = QtWidgets.QLabel("Select SSD drive:")
        ssd_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        config_layout.addWidget(ssd_label)

        self._ssd_combo = QtWidgets.QComboBox()
        self._ssd_combo.setMinimumHeight(32)
        self._ssd_combo.addItem("Scanning for SSD drives...")
        self._ssd_combo.setEnabled(False)
        self._ssd_combo.currentIndexChanged.connect(self._on_ssd_changed)
        config_layout.addWidget(self._ssd_combo)

        # Farm path (read-only display + Browse button, locked to selected SSD)
        path_label = QtWidgets.QLabel("Farm folder path:")
        path_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        config_layout.addWidget(path_label)

        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(6)
        self._path_input = QtWidgets.QLineEdit()
        self._path_input.setMinimumHeight(30)
        self._path_input.setReadOnly(True)
        self._path_input.setPlaceholderText("Select a folder on the SSD drive")
        self._path_input.setStyleSheet("background-color: #1a2030;")
        path_row.addWidget(self._path_input, 1)

        self._browse_btn = QtWidgets.QPushButton("Browse")
        self._browse_btn.setFixedHeight(30)
        self._browse_btn.setFixedWidth(80)
        self._browse_btn.clicked.connect(self._on_browse_path)
        path_row.addWidget(self._browse_btn)
        config_layout.addLayout(path_row)

        # Farm size
        size_header = QtWidgets.QHBoxLayout()
        size_label = QtWidgets.QLabel("Farm size:")
        size_label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        size_header.addWidget(size_label)
        size_header.addStretch(1)
        self._size_value_label = QtWidgets.QLabel("")
        self._size_value_label.setStyleSheet("color: #E5E7EB; font-weight: 600;")
        size_header.addWidget(self._size_value_label)
        config_layout.addLayout(size_header)

        self._size_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self._size_slider.setMinimum(MIN_FARM_SIZE_GB)
        self._size_slider.setMaximum(500)
        self._size_slider.setSingleStep(10)
        self._size_slider.setPageStep(50)
        self._size_slider.valueChanged.connect(self._on_size_changed)
        config_layout.addWidget(self._size_slider)

        # Size presets row
        presets_row = QtWidgets.QHBoxLayout()
        presets_row.setSpacing(6)
        for preset_name, preset_gb in [("Small (100G)", 100), ("Medium (500G)", 500), ("Large (1T)", 1000)]:
            btn = QtWidgets.QPushButton(preset_name)
            btn.setFixedHeight(26)
            btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
            btn.clicked.connect(lambda checked=False, g=preset_gb: self._apply_preset(g))
            presets_row.addWidget(btn)
        self._max_preset_btn = QtWidgets.QPushButton("Maximum")
        self._max_preset_btn.setFixedHeight(26)
        self._max_preset_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self._max_preset_btn.clicked.connect(self._apply_max_preset)
        presets_row.addWidget(self._max_preset_btn)
        presets_row.addStretch(1)
        config_layout.addLayout(presets_row)

        # Network ports info
        ports_label = QtWidgets.QLabel(
            "Ports 30333/TCP and 30433/TCP will be opened for P2P networking."
        )
        ports_label.setStyleSheet("color: #6B7280; font-size: 11px;")
        ports_label.setWordWrap(True)
        config_layout.addWidget(ports_label)

        # Save config button
        self._save_config_btn = QtWidgets.QPushButton("Save Configuration")
        self._save_config_btn.setMinimumHeight(34)
        self._save_config_btn.setStyleSheet(
            "QPushButton { background-color: #22c55e; color: #0b101a; font-weight: 600; "
            "border-radius: 6px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #16a34a; }"
            "QPushButton:disabled { background-color: #2a3142; color: #6B7280; }"
        )
        self._save_config_btn.clicked.connect(self._on_save_config)
        config_layout.addWidget(self._save_config_btn)

        layout.addWidget(self._config_widget)
        self._config_widget.hide()  # Config managed by PoC service, not user

        layout.addStretch(1)

    # --- SSD config methods ---

    def set_available_ssds(self, ssds: List[Dict[str, Any]]) -> None:
        """Populate SSD selection from gui_config.enc → available_ssds."""
        self._available_ssds = ssds or []
        self._ssd_combo.clear()

        if not self._available_ssds:
            self._ssd_combo.addItem("No SSD drives detected")
            self._ssd_combo.setEnabled(False)
            self._toggle.setToolTip("No SSD drives detected. Space Acres requires an SSD for farming.")
        else:
            self._ssd_combo.setEnabled(True)
            self._toggle.setToolTip("")

            # Populate combo, grey out SSDs with < MIN_SSD_FREE_GB free
            best_idx = 0
            best_free = 0.0
            for i, ssd in enumerate(self._available_ssds):
                path = ssd.get("path", "?")
                free_gb = ssd.get("free_gb", 0.0)
                total_gb = ssd.get("total_gb", 0.0)
                label = f"[{path}]  {free_gb:.1f} GB free / {total_gb:.1f} GB total"
                self._ssd_combo.addItem(label, userData=ssd)

                if free_gb < MIN_SSD_FREE_GB:
                    model = self._ssd_combo.model()
                    if model:
                        item = model.item(i)
                        if item:
                            item.setEnabled(False)
                elif free_gb > best_free:
                    best_free = free_gb
                    best_idx = i

            self._ssd_combo.setCurrentIndex(best_idx)

            # Show motivational message if config hasn't been saved yet
            if not self._is_configured:
                self._status_label.setText(self._unconfigured_message())

        self._sync_toggle_enabled()
        self._update_config_visibility()

    def set_spaceacres_config(self, config: Dict[str, Any]) -> None:
        """Populate config UI from existing spaceacres_config in gui_config.enc."""
        if not config:
            self._is_configured = False
            self._sync_toggle_enabled()
            return

        farm_path = config.get("farm_path", "")
        farm_size = config.get("farm_size", "")

        if farm_path:
            self._path_input.setText(farm_path)
            self._is_configured = True

        if farm_size:
            # Parse "400G" or "1T" to GB
            gb = self._parse_farm_size(farm_size)
            if gb > 0:
                self._size_slider.setValue(min(gb, self._size_slider.maximum()))

        self._sync_toggle_enabled()

    def get_farm_config(self) -> tuple[str, str]:
        """Return (farm_path, farm_size_string) from current UI state."""
        farm_path = self._path_input.text().strip()
        farm_size_gb = self._size_slider.value()
        return farm_path, _farm_size_to_string(farm_size_gb)

    @property
    def is_configured(self) -> bool:
        """Whether a valid farm configuration has been saved."""
        return self._is_configured

    def _selected_ssd_root(self) -> str:
        """Return the root path of the currently selected SSD, or ''."""
        idx = self._ssd_combo.currentIndex()
        if idx < 0 or idx >= len(self._available_ssds):
            return ""
        return self._available_ssds[idx].get("path", "")

    def _on_ssd_changed(self, index: int) -> None:
        """Update farm path default when SSD selection changes."""
        if index < 0 or index >= len(self._available_ssds):
            return
        ssd = self._available_ssds[index]
        ssd_path = ssd.get("path", "")
        free_gb = ssd.get("free_gb", 0.0)

        # Set default farm path
        if os.name == "nt":
            default_path = f"{ssd_path}autonomys-farm"
        else:
            sep = "" if ssd_path.endswith("/") else "/"
            default_path = f"{ssd_path}{sep}autonomys-farm"
        self._path_input.setText(default_path)

        # Update slider range based on SSD free space
        max_gb = max(int(free_gb - RESERVED_GB), MIN_FARM_SIZE_GB)
        self._size_slider.setMaximum(max_gb)

        # Default: 50% of free space, rounded to nearest 50G
        default_gb = int(free_gb * 0.5)
        default_gb = max(MIN_FARM_SIZE_GB, (default_gb // 50) * 50)
        default_gb = min(default_gb, max_gb)
        self._size_slider.setValue(default_gb)

    def _on_browse_path(self) -> None:
        """Open a folder dialog locked to the selected SSD root."""
        ssd_root = self._selected_ssd_root()
        if not ssd_root:
            return

        # Start browsing from the current path or the SSD root
        start_dir = self._path_input.text().strip() or ssd_root

        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select farm folder",
            start_dir,
            QtWidgets.QFileDialog.Option.ShowDirsOnly,
        )
        if not chosen:
            return

        # Normalize both to compare (handle trailing slashes, case on Windows)
        chosen_norm = os.path.normcase(os.path.normpath(chosen))
        root_norm = os.path.normcase(os.path.normpath(ssd_root))

        if not chosen_norm.startswith(root_norm):
            self._status_label.setText(
                f"Folder must be on the selected SSD ({ssd_root}). Please choose a folder on that drive."
            )
            self._status_label.setStyleSheet("color: #F59E0B;")
            return

        self._status_label.setStyleSheet("")
        self._path_input.setText(chosen)

    def _on_size_changed(self, value: int) -> None:
        """Update size display label."""
        self._size_value_label.setText(_format_size(value))

    def _apply_preset(self, gb: int) -> None:
        """Apply a size preset."""
        gb = min(gb, self._size_slider.maximum())
        gb = max(gb, self._size_slider.minimum())
        self._size_slider.setValue(gb)

    def _apply_max_preset(self) -> None:
        """Apply maximum size preset."""
        self._size_slider.setValue(self._size_slider.maximum())

    def _on_save_config(self) -> None:
        """Validate and emit configure_requested signal."""
        farm_path = self._path_input.text().strip()
        if not farm_path:
            self._status_label.setText("Please select a farm folder using Browse.")
            self._status_label.setStyleSheet("color: #F59E0B;")
            return

        # Validate path is on the selected SSD
        ssd_root = self._selected_ssd_root()
        if ssd_root:
            path_norm = os.path.normcase(os.path.normpath(farm_path))
            root_norm = os.path.normcase(os.path.normpath(ssd_root))
            if not path_norm.startswith(root_norm):
                self._status_label.setText(
                    f"Farm path must be on the selected SSD ({ssd_root})."
                )
                self._status_label.setStyleSheet("color: #F59E0B;")
                return

        farm_size_gb = self._size_slider.value()
        if farm_size_gb < MIN_FARM_SIZE_GB:
            self._status_label.setText(f"Farm size must be at least {MIN_FARM_SIZE_GB} GB.")
            self._status_label.setStyleSheet("color: #F59E0B;")
            return

        farm_size_str = _farm_size_to_string(farm_size_gb)
        self._is_configured = True
        self._status_label.setStyleSheet("")
        self._sync_toggle_enabled()
        self.configure_requested.emit(farm_path, farm_size_str)

    @staticmethod
    def _parse_farm_size(size_str: str) -> int:
        """Parse '400G' or '1T' to GB."""
        size_str = size_str.strip().upper()
        try:
            if size_str.endswith("T"):
                return int(float(size_str[:-1]) * 1000)
            if size_str.endswith("G"):
                return int(float(size_str[:-1]))
            return int(float(size_str))
        except (ValueError, TypeError):
            return 0

    # --- Status / toggle methods (unchanged API) ---

    def update_status(self, status_text: str) -> None:
        """Update the large status display area."""
        if not self._mac_mismatch and not self._is_pending:
            self._status_label.setText(status_text)

    def update_full_status(self, status) -> None:
        """Update status text and sync progress bar from a SpaceAcresStatus.

        Lifecycle: node_starting → syncing (dsn_download → block_sync →
        finalization) → running.
        Stalled: sync or finalization stuck, service auto-restarting.
        """
        if self._mac_mismatch or self._is_pending:
            return

        if status.stalled:
            self._status_label.setText("Restarting node...")
            self._sync_bar.hide()
        elif status.degraded:
            self._status_label.setText("Degraded - check logs")
            self._sync_bar.hide()
        elif status.node_starting:
            self._status_label.setText("Starting node...")
            self._sync_bar.hide()
        elif status.syncing:
            self._show_sync_phase(status)
        elif status.finalizing:
            gap = f"{status.finalization_gap:,}" if status.finalization_gap is not None else "?"
            self._status_label.setText(f"Finalizing: {gap} blocks remaining")
            self._sync_bar.setValue(10000)
            self._sync_bar.setFormat("100%")
            self._sync_bar.show()
        elif status.running:
            if self._was_syncing or self._was_finalizing:
                self._status_label.setText("Sync complete! Fully synced.")
            else:
                self._status_label.setText("Running - Fully synced")
            self._sync_bar.hide()
        else:
            if not self._is_configured and self._available_ssds:
                self._status_label.setText(self._unconfigured_message())
            else:
                self._status_label.setText("Stopped")
            self._sync_bar.hide()

        self._was_syncing = status.syncing
        self._was_finalizing = status.finalizing
        self._toggle.set_syncing(
            status.syncing or status.finalizing or status.node_starting or status.stalled
        )

    def _show_sync_phase(self, status) -> None:
        """Display the correct UI for the current syncPhase."""
        phase = status.sync_phase

        if phase == "dsn_download":
            # DSN snap sync — blocks jump from 0 to ~99% suddenly; no bar.
            self._status_label.setText("Downloading blockchain data...")
            self._sync_bar.hide()
        elif phase == "finalization":
            gap = f"{status.finalization_gap:,}" if status.finalization_gap is not None else "?"
            self._status_label.setText(f"Finalizing: {gap} blocks remaining")
            self._sync_bar.setValue(10000)
            self._sync_bar.setFormat("100%")
            self._sync_bar.show()
        else:
            # "block_sync" or unknown — show progress bar
            if status.sync_percent is not None:
                cb = f"{status.best_block:,}" if status.best_block else "?"
                hb = f"{status.highest_block:,}" if status.highest_block else "?"
                self._status_label.setText(
                    f"Syncing blockchain: {status.sync_percent:.2f}%"
                    f" ({cb} / {hb} blocks)"
                )
                self._sync_bar.setValue(int(status.sync_percent * 100))
                self._sync_bar.setFormat(f"{status.sync_percent:.2f}%")
                self._sync_bar.show()
            else:
                self._status_label.setText("Syncing blockchain...")
                self._sync_bar.hide()

    def _unconfigured_message(self) -> str:
        """Motivational message when SSDs are detected but config isn't saved."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD
        boost = int(BM_PER_TOOL_REWARD * 100)
        return f"Configure Space Acres to add a +{boost}% boost to your base rewards!"

    def _sync_toggle_enabled(self) -> None:
        """Single source of truth for toggle enable/disable state."""
        should_enable = (
            not self._mac_mismatch
            and not self._is_pending
            and not self._is_busy
            and self._is_configured
            and bool(self._available_ssds)
        )
        self._toggle.setEnabled(should_enable)

    def _update_config_visibility(self) -> None:
        """Show/hide the SSD config section based on current state."""
        if not self._available_ssds or self._toggle.isChecked() or self._is_busy:
            self._config_widget.hide()
        else:
            self._config_widget.show()

    def set_toggle_state(self, enabled: bool) -> None:
        """Set toggle state without emitting signal, then reconcile UI."""
        self._suspend_toggle = True
        try:
            self._toggle.setChecked(enabled)
            self._sync_toggle_enabled()
            self._update_config_visibility()
        finally:
            self._suspend_toggle = False

    def set_busy(self, busy: bool) -> None:
        """Set busy state — disables toggle and save button during async ops."""
        self._is_busy = busy
        self._sync_toggle_enabled()
        self._update_config_visibility()
        self._save_config_btn.setEnabled(not busy)

    def show_status_message(self, message: str) -> None:
        """Show a simple status message."""
        if not self._mac_mismatch and not self._is_pending:
            self._status_label.setText(message)

    def set_mac_mismatch_state(self, is_mismatched: bool, warning_message: str = "") -> None:
        """Disable toggle and show warning when MAC is mismatched."""
        self._mac_mismatch = is_mismatched
        if is_mismatched:
            if warning_message:
                self._status_label.setText(warning_message)
                self._status_label.setStyleSheet("color: #DC2626; font-weight: 600;")
        else:
            self._status_label.setStyleSheet("")
        self._sync_toggle_enabled()

    def set_pending_state(self, is_pending: bool) -> None:
        """Set pending state when waiting for miner configuration."""
        self._is_pending = is_pending
        self._sync_toggle_enabled()

    def _on_toggle_state(self, state: int) -> None:
        if self._suspend_toggle:
            return
        self._update_config_visibility()
        self.toggle_changed.emit(bool(state))



class SdnPanel(QtWidgets.QWidget):
    """LiveData panel for SDN miners with tabbed Space Acres panel."""

    # Signals for external handlers
    space_acres_refresh_clicked = QtCore.Signal()
    space_acres_toggle_changed = QtCore.Signal(bool)
    space_acres_configure_requested = QtCore.Signal(str, str)

    def __init__(
        self,
        width: int = 800,
        parent: Optional[QtWidgets.QWidget] = None,
        screen_size: str = "desktop",
    ) -> None:
        super().__init__(parent)
        self._screen_size = screen_size or "desktop"
        self._width = self._compute_width(width)
        self._build_ui()

    def _compute_width(self, base: int) -> int:
        """Scale width based on screen size preference."""
        size = (self._screen_size or "desktop").lower()
        if size == "mobile":
            return int(base * 0.55)
        if size == "tablet":
            return int(base * 0.75)
        return base

    def _build_ui(self) -> None:
        """Build tabbed interface matching bandwidth panel style."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Create tab widget
        tabs = QtWidgets.QTabWidget()
        tabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.North)
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(False)
        tabs.setElideMode(QtCore.Qt.TextElideMode.ElideRight)
        tabs.setFixedWidth(self._width)

        # Space Acres tab
        self.space_acres_panel = StorageNodeTab()
        self.space_acres_panel.refresh_clicked.connect(self.space_acres_refresh_clicked.emit)
        self.space_acres_panel.toggle_changed.connect(self.space_acres_toggle_changed.emit)
        self.space_acres_panel.configure_requested.connect(self.space_acres_configure_requested.emit)
        self.space_acres_panel.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

        space_acres_container = QtWidgets.QWidget()
        space_acres_layout = QtWidgets.QVBoxLayout(space_acres_container)
        space_acres_layout.setContentsMargins(0, 0, 0, 0)
        space_acres_layout.setSpacing(4)
        space_acres_layout.addWidget(self.space_acres_panel, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.space_acres_panel.show_status_message("Loading Space Acres status...")
        tabs.addTab(space_acres_container, "Space Acres")

        layout.addWidget(tabs)

    # --- Space Acres methods ---

    def set_space_acres_ssds(self, ssds: List[Dict[str, Any]]) -> None:
        """Pass available SSDs to the Space Acres panel for selection."""
        self.space_acres_panel.set_available_ssds(ssds)

    def set_space_acres_config(self, config: Dict[str, Any]) -> None:
        """Pass existing spaceacres_config to pre-fill the config UI."""
        self.space_acres_panel.set_spaceacres_config(config)

    def get_space_acres_farm_config(self) -> tuple[str, str]:
        """Read current farm config from the panel UI."""
        return self.space_acres_panel.get_farm_config()

    def update_space_acres_status(self, status) -> None:
        """Update Space Acres tab with status object."""
        # Use full status for sync progress bar + text
        if status.syncing or status.node_starting or status.finalizing or status.stalled or status.degraded or (status.running and not status.last_error):
            self.space_acres_panel.update_full_status(status)
        else:
            status_text = self._build_space_acres_summary(status)
            self.space_acres_panel.update_status(status_text)
            self.space_acres_panel._toggle.set_syncing(False)
        self.space_acres_panel.set_toggle_state(status.running)

    def set_space_acres_busy(self, busy: bool) -> None:
        """Set Space Acres tab busy state."""
        self.space_acres_panel.set_busy(busy)

    def set_space_acres_unavailable(self, message: str) -> None:
        """Show unavailable message and disable controls."""
        self.space_acres_panel.show_status_message(message)
        self.space_acres_panel._toggle.setEnabled(False)

    def _build_space_acres_summary(self, status) -> str:
        """Build Space Acres status summary for large display."""
        from miner_GUI.ui.helpers.rewards import BM_PER_TOOL_REWARD

        if status.last_error:
            return f"Error: {status.last_error[:80]}"
        if status.running:
            return f"Space Acres is running and adding a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards."
        return f"Status: Stopped. Enable it to add a +{int(BM_PER_TOOL_REWARD * 100)}% boost to your base rewards!"

    def on_tick(self, data: dict) -> None:
        """Handle tick updates (for LiveData compatibility).

        SDN doesn't have sensor data, so this is mostly a no-op.
        Status updates come via update_space_acres_status.
        """
        pass
