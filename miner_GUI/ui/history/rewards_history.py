"""Rewards History widget showing 24h and 7-day multiplier visualizations."""

import math
import os
import sys
from datetime import datetime, timedelta, date, timezone
from typing import List, Dict, Optional, Tuple, Any, TYPE_CHECKING

from PySide6 import QtWidgets, QtCore
from config_profile import GROUP
import miner_GUI.ui.helpers.rewards as _rewards_mod
from miner_GUI.utils.status_week import (
    counted_slots_from_day,
    day_doc_from_week,
    load_status_week_for_date,
    rewards_week_start_date,
    week_bounds_from_doc,
)

# Matplotlib imports
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.patches as mpatches
    HAVE_MATPLOTLIB = True
except Exception:
    HAVE_MATPLOTLIB = False
    if TYPE_CHECKING:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        import matplotlib.patches as mpatches


class RewardsHistoryWidget(QtWidgets.QWidget):
    """Widget displaying rewards multiplier history with gate status breakdown."""
    
    def __init__(self, parent=None, screen_size_pref: str = ""):
        super().__init__(parent)
        self.group = GROUP
        self._bandwidth_groups = ("BM", "Bandwidth")
        self._node_groups = ("SVN",)  # bare nodes (no tools, no sensors)
        self._tools_groups = ("BM", "Bandwidth", "RDN", "SDN")
        self._mobile_hint = bool(screen_size_pref == "mobile") or self._detect_mobile()
        self._use_local_time = False  # Default to UTC
        
        # Load theme
        try:
            from theme import Theme  # type: ignore
            self._theme = Theme()
        except Exception:
            self._theme = None
        
        layout = QtWidgets.QVBoxLayout(self)
        is_mobile = self._is_mobile()
        # Reduce top margin to shift content up
        layout.setContentsMargins(4 if is_mobile else 10, 2 if is_mobile else 4, 4 if is_mobile else 10, 4 if is_mobile else 10)
        layout.setSpacing(2 if is_mobile else 4)
        
        # Title
        title = QtWidgets.QLabel(f"🏆 {self.group} Rewards History")
        title_size = "11pt" if is_mobile else "14pt"
        title.setStyleSheet(f"font-size: {title_size}; font-weight: bold; padding: 2px;")
        layout.addWidget(title)
        
        # View mode selector (24h vs 7d)
        utc_today_qdate = self._current_utc_qdate()

        if is_mobile:
            # Compact single row layout for mobile
            mode_layout = QtWidgets.QHBoxLayout()
            mode_layout.setSpacing(4)
            
            # View mode selector (compact)
            mode_layout.addWidget(QtWidgets.QLabel("View:"))
            self.view_mode_combo = QtWidgets.QComboBox()
            self.view_mode_combo.setAccessibleName("history_rewards_combobox_view_mode")
            self.view_mode_combo.addItem("📊 24h", "24h")
            self.view_mode_combo.addItem("📅 Week", "7d")
            self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
            mode_layout.addWidget(self.view_mode_combo)
            
            # Date navigation (for 24h view) - all on same line
            self.date_label = QtWidgets.QLabel("Date:")
            self.date_label.setAccessibleName("history_rewards_label_date")
            mode_layout.addWidget(self.date_label)
            
            self.prev_btn = QtWidgets.QPushButton("◀")
            self.prev_btn.setAccessibleName("history_rewards_button_prev")
            self.prev_btn.setMaximumWidth(32)
            self.prev_btn.setMinimumWidth(32)
            self.prev_btn.setMaximumHeight(32)
            self.prev_btn.setMinimumHeight(32)
            self.prev_btn.setStyleSheet("QPushButton { font-size: 12pt; font-weight: bold; padding: 0px; }")
            self.prev_btn.clicked.connect(self._prev_day)
            mode_layout.addWidget(self.prev_btn)
            
            self.date_edit = QtWidgets.QDateEdit()
            self.date_edit.setAccessibleName("history_rewards_dateedit_date")
            self.date_edit.setCalendarPopup(True)
            self.date_edit.dateChanged.connect(self._load_data)
            self.date_edit.setDisplayFormat("MM/dd")
            self.date_edit.setMaximumWidth(65)
            mode_layout.addWidget(self.date_edit)
            
            self.next_btn = QtWidgets.QPushButton("▶")
            self.next_btn.setAccessibleName("history_rewards_button_next")
            self.next_btn.setMaximumWidth(32)
            self.next_btn.setMinimumWidth(32)
            self.next_btn.setMaximumHeight(32)
            self.next_btn.setMinimumHeight(32)
            self.next_btn.setStyleSheet("QPushButton { font-size: 12pt; font-weight: bold; padding: 0px; }")
            self.next_btn.clicked.connect(self._next_day)
            mode_layout.addWidget(self.next_btn)
            
            self.refresh_btn = QtWidgets.QPushButton("🔄")
            self.refresh_btn.setAccessibleName("history_rewards_button_refresh")
            self.refresh_btn.setMaximumWidth(32)
            self.refresh_btn.setMinimumWidth(32)
            self.refresh_btn.setMaximumHeight(32)
            self.refresh_btn.setMinimumHeight(32)
            self.refresh_btn.setStyleSheet("QPushButton { font-size: 12pt; font-weight: bold; padding: 0px; }")
            self.refresh_btn.clicked.connect(self._load_data)
            mode_layout.addWidget(self.refresh_btn)
            
            mode_layout.addStretch()
            
            # Time zone toggle (compact icon button)
            self.tz_toggle_btn = QtWidgets.QPushButton("🌐UTC")
            self.tz_toggle_btn.setAccessibleName("history_rewards_button_tz_toggle")
            self.tz_toggle_btn.setMaximumWidth(60)
            self.tz_toggle_btn.setMinimumWidth(60)
            self.tz_toggle_btn.setMaximumHeight(32)
            self.tz_toggle_btn.setMinimumHeight(32)
            self.tz_toggle_btn.setStyleSheet("QPushButton { font-size: 9pt; font-weight: bold; padding: 0px; }")
            self.tz_toggle_btn.setToolTip("Toggle between UTC and Local time")
            self.tz_toggle_btn.clicked.connect(self._toggle_timezone)
            mode_layout.addWidget(self.tz_toggle_btn)
        else:
            # Original horizontal layout for desktop
            mode_layout = QtWidgets.QHBoxLayout()
            mode_layout.addWidget(QtWidgets.QLabel("View:"))
            
            self.view_mode_combo = QtWidgets.QComboBox()
            self.view_mode_combo.setAccessibleName("history_rewards_combobox_view_mode")
            self.view_mode_combo.addItem("📊 24 Hours (Detailed)", "24h")
            self.view_mode_combo.addItem("📅 Week (Rewards)", "7d")
            self.view_mode_combo.currentIndexChanged.connect(self._on_view_mode_changed)
            mode_layout.addWidget(self.view_mode_combo)
            
            # Date navigation (for 24h view)
            self.date_label = QtWidgets.QLabel("Date:")
            self.date_label.setAccessibleName("history_rewards_label_date")
            mode_layout.addWidget(self.date_label)
            
            self.date_edit = QtWidgets.QDateEdit()
            self.date_edit.setAccessibleName("history_rewards_dateedit_date")
            self.date_edit.setObjectName("rewardsHistoryDateEdit")
            self.date_edit.setCalendarPopup(True)
            self.date_edit.dateChanged.connect(self._load_data)
            if self._theme:
                try:
                    radius = max(4, int(self._theme.radius / 2))
                    font_size = "12pt"
                    self.date_edit.setStyleSheet(
                        f"""
                        QDateEdit#rewardsHistoryDateEdit {{
                            background: rgba(255,255,255,0.08);
                            border: 1px solid {self._theme.border};
                            border-radius: {radius}px;
                            padding: 4px 10px;
                            color: {self._theme.text_primary};
                            font-size: {font_size};
                            selection-background-color: {self._theme.accent_primary_hover};
                            selection-color: #ffffff;
                        }}
                        QDateEdit::drop-down {{
                            border: none;
                            width: 22px;
                            background: rgba(0,0,0,0.25);
                        }}
                        /* Show default calendar arrow */
                        QDateEdit::down-arrow {{
                            width: 14px;
                            height: 14px;
                        }}
                        QCalendarWidget QWidget {{
                            background-color: {self._theme.bg_panel};
                            color: {self._theme.text_primary};
                        }}
                        """
                    )
                except Exception:
                    pass
            mode_layout.addWidget(self.date_edit)
            
            self.prev_btn = QtWidgets.QPushButton("◀ Prev")
            self.prev_btn.setAccessibleName("history_rewards_button_prev")
            self.prev_btn.setToolTip("Previous day")
            self.prev_btn.setMinimumWidth(70)
            self.prev_btn.clicked.connect(self._prev_day)
            mode_layout.addWidget(self.prev_btn)
            
            self.next_btn = QtWidgets.QPushButton("Next ▶")
            self.next_btn.setAccessibleName("history_rewards_button_next")
            self.next_btn.setToolTip("Next day")
            self.next_btn.setMinimumWidth(70)
            self.next_btn.clicked.connect(self._next_day)
            mode_layout.addWidget(self.next_btn)
            
            self.refresh_btn = QtWidgets.QPushButton("🔄 Refresh")
            self.refresh_btn.setAccessibleName("history_rewards_button_refresh")
            self.refresh_btn.setToolTip("Reload data for selected date/range")
            self.refresh_btn.setMinimumWidth(90)
            self.refresh_btn.clicked.connect(self._load_data)
            mode_layout.addWidget(self.refresh_btn)
            
            # Time zone toggle button
            self.tz_toggle_btn = QtWidgets.QPushButton("🌐 UTC")
            self.tz_toggle_btn.setAccessibleName("history_rewards_button_tz_toggle")
            self.tz_toggle_btn.setToolTip("Toggle between UTC and Local time")
            self.tz_toggle_btn.setCheckable(True)
            self.tz_toggle_btn.setMinimumWidth(80)
            self.tz_toggle_btn.clicked.connect(self._toggle_timezone)
            mode_layout.addWidget(self.tz_toggle_btn)
            
            mode_layout.addStretch()
        # Clamp selected/allowed dates to UTC "today" without triggering signals prematurely
        try:
            self.date_edit.blockSignals(True)
        except Exception:
            pass
        self.date_edit.setDate(utc_today_qdate)
        self.date_edit.setMaximumDate(utc_today_qdate)
        try:
            self.date_edit.blockSignals(False)
        except Exception:
            pass
        layout.addLayout(mode_layout)
        
        # Summary cards (compact spacing)
        self.summary_widget = self._create_summary_cards()
        layout.addWidget(self.summary_widget)
        
        # Chart area
        if HAVE_MATPLOTLIB:
            # Adjust figure size for mobile
            if is_mobile:
                fig_width, fig_height = 6, 7
            else:
                fig_width, fig_height = 12, 8
            self.figure = Figure(figsize=(fig_width, fig_height), facecolor=(self._theme.bg_panel if self._theme else "#111827"))
            self.canvas = FigureCanvasQTAgg(self.figure)
            layout.addWidget(self.canvas, 1)  # Stretch factor 1
        else:
            error_label = QtWidgets.QLabel(
                "📉 Matplotlib required\n\nInstall: pip install matplotlib"
            )
            error_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("""
                background-color: #FEF3C7; border: 1px solid #F59E0B;
                border-radius: 6px; padding: 20px; color: #92400E; font-size: 12px;
            """)
            layout.addWidget(error_label)

        # Status line (always present, used for load/warning messages)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setAccessibleName("history_rewards_label_status")
        self.status_label.setWordWrap(False)
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        try:
            if self._theme:
                self.status_label.setStyleSheet(f"color: {self._theme.text_primary}; font-size: {'8pt' if is_mobile else '10pt'};")
            else:
                self.status_label.setStyleSheet("color: #E5E7EB; font-size: 10pt;")
        except Exception:
            pass
        layout.addWidget(self.status_label)
        
        # Initial load
        self._update_date_controls_visibility()
        if HAVE_MATPLOTLIB:
            self._load_data()

        # Auto-refresh timer (started/stopped in showEvent/hideEvent)
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setInterval(3000)  # 3-second periodic refresh
        self._refresh_timer.timeout.connect(self._load_data)

    def _current_utc_qdate(self) -> QtCore.QDate:
        """Return today's date in UTC for date clamps."""
        try:
            utc_today = datetime.now(timezone.utc).date()
        except Exception:
            utc_today = datetime.utcnow().date()
        return QtCore.QDate(utc_today.year, utc_today.month, utc_today.day)
    
    def _toggle_timezone(self) -> None:
        """Toggle between UTC and Local time display."""
        self._use_local_time = not self._use_local_time
        is_mobile = self._is_mobile()
        
        # Update button text
        if self._use_local_time:
            self.tz_toggle_btn.setText("🌐Local" if is_mobile else "🌐 Local")
        else:
            self.tz_toggle_btn.setText("🌐UTC" if is_mobile else "🌐 UTC")
        
        # Reload chart with new timezone
        self._load_data()
    
    def _get_local_offset_hours(self) -> int:
        """Get the offset in hours between local time and UTC."""
        try:
            # Use aware datetimes and round to the nearest hour to avoid truncation errors
            now = datetime.now(timezone.utc).astimezone()
            offset = now.utcoffset() or timedelta(0)
            return int(round(offset.total_seconds() / 3600))
        except Exception:
            return 0

    def _max_tools_available(self) -> int:
        """Return the max number of sharing tools available in this build/env."""
        if self.group == "RDN":
            # RDN: 2 tools (Presearch + Diiisco)
            return 2
        if self.group == "SDN":
            # SDN: 1 tool (Space Acres)
            return 1
        if self.group not in self._bandwidth_groups:
            return 0
        mode = str(os.getenv("BM_SHARING_MODE") or "all").strip().lower()
        if mode == "none":
            return 0
        if mode in ("honeygain", "bright", "mysterium"):
            # Single-tool builds
            return 1
        # "all" or unknown -> infer availability. Bright is Windows-only.
        is_windows = sys.platform.startswith("win")
        allow_hg = mode in ("all", "honeygain")
        allow_bright = is_windows and mode in ("all", "bright")
        allow_mys = mode in ("all", "mysterium")
        return int(allow_hg) + int(allow_bright) + int(allow_mys)
    
    def _create_summary_cards(self) -> QtWidgets.QWidget:
        """Create summary statistics cards."""
        container = QtWidgets.QWidget()
        is_mobile = self._is_mobile()
        
        if is_mobile:
            # Horizontal layout for all cards in one row on mobile
            card_layout = QtWidgets.QHBoxLayout(container)
            card_layout.setSpacing(2)
            card_layout.setContentsMargins(0, 0, 0, 0)
        else:
            # Original horizontal layout for desktop
            card_layout = QtWidgets.QHBoxLayout(container)
            card_layout.setSpacing(10)
        
        # Card style
        card_style = f"""
            QGroupBox {{
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: {'4px' if is_mobile else '8px'};
                padding: {'4px' if is_mobile else '12px'};
                font-weight: bold;
                font-size: {'8pt' if is_mobile else '12pt'};
            }}
        """
        
        value_size = "11pt" if is_mobile else "18pt"
        
        # Average Multiplier card
        self.avg_mult_card = QtWidgets.QGroupBox("Avg" if is_mobile else "Avg Multiplier")
        self.avg_mult_card.setAccessibleName("history_rewards_groupbox_avg_mult_card")
        self.avg_mult_card.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.avg_mult_card.setStyleSheet(card_style)
        avg_layout = QtWidgets.QVBoxLayout(self.avg_mult_card)
        avg_layout.setContentsMargins(2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8)
        self.avg_mult_value = QtWidgets.QLabel("--")
        self.avg_mult_value.setAccessibleName("history_rewards_label_avg_mult_value")
        self.avg_mult_value.setStyleSheet(f"font-size: {value_size}; font-weight: bold; color: #10B981;")
        self.avg_mult_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        avg_layout.addWidget(self.avg_mult_value)
        
        # Full Reward Hours card
        self.full_hours_card = QtWidgets.QGroupBox("Full" if is_mobile else "Full Reward")
        self.full_hours_card.setAccessibleName("history_rewards_groupbox_full_hours_card")
        self.full_hours_card.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.full_hours_card.setStyleSheet(card_style)
        full_layout = QtWidgets.QVBoxLayout(self.full_hours_card)
        full_layout.setContentsMargins(2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8)
        self.full_hours_value = QtWidgets.QLabel("--")
        self.full_hours_value.setAccessibleName("history_rewards_label_full_hours_value")
        self.full_hours_value.setStyleSheet(f"font-size: {value_size}; font-weight: bold; color: #3B82F6;")
        self.full_hours_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        full_layout.addWidget(self.full_hours_value)
        
        # Zero Reward Hours card
        self.zero_hours_card = QtWidgets.QGroupBox("Zero" if is_mobile else "Zero Reward")
        self.zero_hours_card.setAccessibleName("history_rewards_groupbox_zero_hours_card")
        self.zero_hours_card.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.zero_hours_card.setStyleSheet(card_style)
        zero_layout = QtWidgets.QVBoxLayout(self.zero_hours_card)
        zero_layout.setContentsMargins(2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8)
        self.zero_hours_value = QtWidgets.QLabel("--")
        self.zero_hours_value.setAccessibleName("history_rewards_label_zero_hours_value")
        self.zero_hours_value.setStyleSheet(f"font-size: {value_size}; font-weight: bold; color: #EF4444;")
        self.zero_hours_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        zero_layout.addWidget(self.zero_hours_value)
        
        # Primary Issue card
        self.issue_card = QtWidgets.QGroupBox("Issue" if is_mobile else "Primary Issue")
        self.issue_card.setAccessibleName("history_rewards_groupbox_issue_card")
        self.issue_card.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.issue_card.setStyleSheet(card_style)
        issue_layout = QtWidgets.QVBoxLayout(self.issue_card)
        issue_layout.setContentsMargins(2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8, 2 if is_mobile else 8)
        self.issue_value = QtWidgets.QLabel("--")
        self.issue_value.setAccessibleName("history_rewards_label_issue_value")
        # Match other cards: use same value size and center alignment
        self.issue_value.setStyleSheet(f"font-size: {value_size}; font-weight: bold; color: #F59E0B;")
        self.issue_value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # Avoid wrap to keep consistent single-line appearance
        self.issue_value.setWordWrap(False)
        issue_layout.addWidget(self.issue_value)
        
        # Add all cards to layout (horizontal for both mobile and desktop)
        card_layout.addWidget(self.avg_mult_card)
        card_layout.addWidget(self.full_hours_card)
        card_layout.addWidget(self.zero_hours_card)
        card_layout.addWidget(self.issue_card)
        
        return container
    
    def _update_date_controls_visibility(self):
        """Show/hide date controls based on view mode."""
        view_mode = self.view_mode_combo.currentData()
        is_week = view_mode == "7d"

        try:
            self.date_label.setText("Week:" if is_week else "Date:")
        except Exception:
            pass

        # Keep navigation visible in both modes; week mode jumps by 7 days.
        for w in (self.date_label, self.date_edit, self.prev_btn, self.next_btn):
            try:
                w.setVisible(True)
            except Exception:
                pass

        try:
            if is_week:
                self.prev_btn.setToolTip("Previous week")
                self.next_btn.setToolTip("Next week")
            else:
                self.prev_btn.setToolTip("Previous day")
                self.next_btn.setToolTip("Next day")
        except Exception:
            pass
    
    def _on_view_mode_changed(self):
        """Handle view mode change."""
        self._update_date_controls_visibility()
        self._load_data()
    
    def _prev_day(self):
        """Navigate to previous day (or previous week in week mode)."""
        current = self.date_edit.date()
        if self.view_mode_combo.currentData() == "7d":
            # Navigate to previous rewards week (Friday-to-Friday boundary)
            current_date = datetime(current.year(), current.month(), current.day()).date()
            current_week_start = rewards_week_start_date(current_date)
            # Go to previous week's start
            prev_week_start = current_week_start - timedelta(days=7)
            qdate = QtCore.QDate(prev_week_start.year, prev_week_start.month, prev_week_start.day)
            self.date_edit.setDate(qdate)
        else:
            self.date_edit.setDate(current.addDays(-1))
    
    def _next_day(self):
        """Navigate to next day (or next week in week mode)."""
        current = self.date_edit.date()
        max_date = self._current_utc_qdate()
        if self.view_mode_combo.currentData() == "7d":
            # Navigate to next rewards week (Friday-to-Friday boundary)
            current_date = datetime(current.year(), current.month(), current.day()).date()
            current_week_start = rewards_week_start_date(current_date)
            # Go to next week's start
            next_week_start = current_week_start + timedelta(days=7)
            qdate = QtCore.QDate(next_week_start.year, next_week_start.month, next_week_start.day)
            if qdate > max_date:
                qdate = max_date
            if qdate != current:
                self.date_edit.setDate(qdate)
        else:
            next_date = current.addDays(1)
            if next_date > max_date:
                next_date = max_date
            if next_date != current:
                self.date_edit.setDate(next_date)
    
    def _load_data(self):
        """Load and display rewards data."""
        if not HAVE_MATPLOTLIB:
            return
        
        try:
            self.date_edit.setMaximumDate(self._current_utc_qdate())
        except Exception:
            pass
        
        view_mode = self.view_mode_combo.currentData()
        
        if view_mode == "24h":
            self._load_24h_data()
        else:
            self._load_7d_data()
    
    def _combine_daily_rewards(self, data1: List[Dict[str, Any]], data2: List[Dict[str, Any]], offset_hours: int) -> List[Dict[str, Any]]:
        """Combine rewards data from two days, accounting for timezone offset.
        
        Filters and marks data so that only hours that will fall within 00:00-23:59 local time are included.
        """
        result = []
        
        # For positive offset (ahead of UTC, e.g. UTC+1):
        #   Local 00:00 = UTC 23:00 previous day, so data2 = previous UTC day.
        #   data1 (target UTC day) hours 0..(23-offset) map to local offset..23
        #   data2 (previous UTC day) hours (24-offset)..23 map to local 0..(offset-1)
        # For negative offset (behind UTC, e.g. UTC-1):
        #   Local 23:00 = UTC 00:00 next day, so data2 = next UTC day.
        #   data1 (target UTC day) hours (-offset)..23 map to local 0..(23+offset)
        #   data2 (next UTC day) hours 0..(-offset-1) map to local (24+offset)..23

        if offset_hours > 0:
            # Positive offset: data1=target day (UTC), data2=previous day (UTC)
            for slot in data1:
                h_utc = int(slot.get("hour", -1))
                if 0 <= h_utc < 24:
                    h_local = h_utc + offset_hours
                    if 0 <= h_local < 24:  # Only include if it stays in today's display
                        slot_copy = slot.copy()
                        slot_copy["_display_hour"] = h_local
                        result.append(slot_copy)
            
            for slot in data2:
                h_utc = int(slot.get("hour", -1))
                if 0 <= h_utc < 24:
                    h_local = h_utc + offset_hours - 24  # Shift back one day
                    if 0 <= h_local < 24:  # Only include if it falls in today's display
                        slot_copy = slot.copy()
                        slot_copy["_display_hour"] = h_local
                        result.append(slot_copy)
        else:
            # Negative offset: data1=target day (UTC), data2=next day (UTC)
            for slot in data1:
                h_utc = int(slot.get("hour", -1))
                if 0 <= h_utc < 24:
                    h_local = h_utc + offset_hours
                    if 0 <= h_local < 24:  # Only include if it stays in today's display
                        slot_copy = slot.copy()
                        slot_copy["_display_hour"] = h_local
                        result.append(slot_copy)
            
            for slot in data2:
                h_utc = int(slot.get("hour", -1))
                if 0 <= h_utc < 24:
                    h_local = h_utc + offset_hours + 24  # Shift forward one day
                    if 0 <= h_local < 24:  # Only include if it falls in today's display
                        slot_copy = slot.copy()
                        slot_copy["_display_hour"] = h_local
                        result.append(slot_copy)
        
        return result
    
    def _load_24h_data(self):
        """Load and plot 24-hour detailed view."""
        from datetime import timedelta
        
        qdate = self.date_edit.date()
        target_date = datetime(qdate.year(), qdate.month(), qdate.day()).date()
        
        # Get timezone offset
        offset_hours = self._get_local_offset_hours() if self._use_local_time else 0
        
        # When displaying in local time, we may need data from adjacent UTC days
        # to show a complete local day (midnight to midnight in the user's timezone)
        if self._use_local_time and offset_hours != 0:
            # Load the target date and adjacent date needed to fill a full local day.
            # For UTC+1: local 00:00 = UTC 23:00 *previous* day, so fetch day before.
            # For UTC-1: local 23:00 = UTC 00:00 *next* day, so fetch day after.
            if offset_hours > 0:
                # Positive offset (ahead of UTC) - need previous day's late UTC hours
                rewards_data1, day_doc, week_doc = self._load_rewards_for_date(target_date)
                rewards_data2, _, _ = self._load_rewards_for_date(target_date - timedelta(days=1))
                rewards_data = self._combine_daily_rewards(rewards_data1, rewards_data2, offset_hours)
                display_date_str = target_date.strftime('%Y-%m-%d')
            else:
                # Negative offset (behind UTC) - need next day's early UTC hours
                rewards_data1, day_doc, week_doc = self._load_rewards_for_date(target_date)
                rewards_data2, _, _ = self._load_rewards_for_date(target_date + timedelta(days=1))
                rewards_data = self._combine_daily_rewards(rewards_data1, rewards_data2, offset_hours)
                display_date_str = target_date.strftime('%Y-%m-%d')
        else:
            rewards_data, day_doc, week_doc = self._load_rewards_for_date(target_date)
            display_date_str = target_date.strftime('%Y-%m-%d')
        
        if not rewards_data:
            self.status_label.setText(f"No rewards data for {display_date_str}")
            self.figure.clear()
            self.canvas.draw()
            self._update_summary_cards([], 24, aggregate=day_doc)
            return
        
        # Update summary cards
        self._update_summary_cards(rewards_data, 24, aggregate=day_doc)
        
        # Plot 24h view with actual display date
        self._plot_24h_view(rewards_data, target_date, display_date=display_date_str)
        week_start, week_end = week_bounds_from_doc(week_doc)
        tz_label = " (Local)" if self._use_local_time else ""
        if week_start and week_end:
            self.status_label.setText(
                f"Loaded {len(rewards_data)} hourly slots for {display_date_str}{tz_label} "
                f"(week {week_start.isoformat()}…{week_end.isoformat()})"
            )
        else:
            self.status_label.setText(f"Loaded {len(rewards_data)} hourly slots for {display_date_str}{tz_label}")
    
    def _load_7d_data(self):
        """Load and plot the current rewards week overview."""
        qdate = self.date_edit.date()
        anchor_date = datetime(qdate.year(), qdate.month(), qdate.day()).date()

        week_doc = load_status_week_for_date(anchor_date)
        if not isinstance(week_doc, dict):
            self.status_label.setText("No rewards week data found")
            self.figure.clear()
            self.canvas.draw()
            self._update_summary_cards([], 168, aggregate=None)
            return

        week_start, week_end = week_bounds_from_doc(week_doc)
        if week_start is None:
            week_start = rewards_week_start_date(anchor_date)
        if week_end is None:
            week_end = week_start + timedelta(days=7)

        all_rewards: List[Dict[str, Any]] = []
        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            day_doc = day_doc_from_week(week_doc, day)
            day_rewards = self._rewards_data_from_day_doc(day_doc)
            all_rewards.append({"date": day, "rewards": day_rewards, "day_doc": day_doc})

        # Update summary cards using week aggregate when present.
        all_slots: List[Dict[str, Any]] = []
        for day_data in all_rewards:
            all_slots.extend(day_data["rewards"])
        week_so_far = week_doc.get("week_so_far") if isinstance(week_doc, dict) else None
        self._update_summary_cards(all_slots, 168, aggregate=week_so_far)

        # Plot week view
        self._plot_7d_view(all_rewards)
        self.status_label.setText(
            f"Loaded rewards week {week_start.isoformat()}…{week_end.isoformat()} "
            f"({len(all_slots)} hourly slots)"
        )
    
    def _rewards_data_from_day_doc(self, day_doc: Optional[dict]) -> List[Dict[str, Any]]:
        """Convert a vNext day doc into the internal per-hour list used by the plots."""
        if not isinstance(day_doc, dict):
            return []
        if counted_slots_from_day(day_doc) <= 0:
            return []

        hours = day_doc.get("hours")
        if not isinstance(hours, dict) or not hours:
            return []

        result: List[Dict[str, Any]] = []
        for hour_str, hour_doc in hours.items():
            if not isinstance(hour_doc, dict):
                continue
            try:
                hour = int(hour_str)
            except Exception:
                continue
            if hour < 0 or hour > 23:
                continue

            # Backend may store hour aggregates directly (hour_doc.gates), or may store
            # slot-level docs in hour_doc.slots (each slot contains gates/multiplier).
            source_doc: Dict[str, Any] = hour_doc
            raw_gates = source_doc.get("gates")
            if not isinstance(raw_gates, dict):
                raw_slots = source_doc.get("slots")
                if isinstance(raw_slots, list):
                    for slot in reversed(raw_slots):
                        if isinstance(slot, dict):
                            source_doc = slot
                            break

            raw_gates = source_doc.get("gates")
            gates: Dict[str, Any] = raw_gates if isinstance(raw_gates, dict) else {}

            raw_tools = source_doc.get("tools_active")
            tools_active: List[str] = [str(t) for t in raw_tools] if isinstance(raw_tools, list) else []

            def _gate(key: str) -> int:
                v = gates.get(key)
                return 1 if v is True else 0

            try:
                multiplier = float(source_doc.get("multiplier", 0.0))
            except Exception:
                multiplier = 0.0

            try:
                tools_count = int(source_doc.get("number_of_tools", len(tools_active)))
            except Exception:
                tools_count = len(tools_active)

            result.append(
                {
                    "hour": hour,
                    "multiplier": multiplier,
                    "mac_match": _gate("mac"),
                    "PoC": _gate("online"),
                    "PoD": _gate("data"),
                    "PoI": _gate("poi") if self.group == "AEM" else 1,
                    "tools_gate": _gate("tools"),
                    "tools": tools_active,
                    "tools_count": tools_count,
                }
            )

        result.sort(key=lambda x: x["hour"])
        return result

    def _load_rewards_for_date(self, day: date) -> Tuple[List[Dict[str, Any]], Optional[dict], Optional[dict]]:
        """Load per-hour rewards data and the associated day/week aggregates from vNext weekly JSON."""
        week_doc = load_status_week_for_date(day)
        day_doc = day_doc_from_week(week_doc, day)
        rewards = self._rewards_data_from_day_doc(day_doc)
        return rewards, (day_doc if isinstance(day_doc, dict) else None), (week_doc if isinstance(week_doc, dict) else None)
    
    def _update_summary_cards(
        self,
        rewards_data: List[Dict[str, Any]],
        total_hours: int,
        *,
        aggregate: Optional[Dict[str, Any]] = None,
    ):
        """Update summary statistic cards (prefers backend-provided aggregates)."""

        def _has_agg_data(doc: Optional[Dict[str, Any]]) -> bool:
            if not isinstance(doc, dict):
                return False
            try:
                if int(doc.get("counted_slots", 0)) > 0:
                    return True
            except Exception:
                pass
            try:
                if float(doc.get("avg_multiplier", 0.0)) > 0.0:
                    return True
            except Exception:
                pass
            return isinstance(doc.get("issue_counts"), dict)

        if not rewards_data and not _has_agg_data(aggregate):
            self.avg_mult_value.setText("--")
            self.full_hours_value.setText("-- / --")
            self.zero_hours_value.setText("-- / --")
            self.issue_value.setText("No data")
            return

        multipliers = [float(r.get("multiplier", 0.0)) for r in rewards_data if isinstance(r, dict)]
        _full_thresh = _rewards_mod.BM_BASE_REWARD + _rewards_mod.BM_PER_TOOL_REWARD * self._max_tools_available()
        full_hours = sum(1 for m in multipliers if m >= _full_thresh - 0.001) if multipliers else None
        zero_hours = sum(1 for m in multipliers if m == 0.0) if multipliers else None

        if isinstance(aggregate, dict) and "avg_multiplier" in aggregate:
            try:
                avg_mult = float(aggregate.get("avg_multiplier", 0.0))
            except Exception:
                avg_mult = (sum(multipliers) / len(multipliers)) if multipliers else 0.0
        else:
            avg_mult = (sum(multipliers) / len(multipliers)) if multipliers else 0.0

        issue_counts: Dict[str, int] = {"mac": 0, "online": 0, "data": 0, "tools": 0, "poi": 0}
        agg_counts = aggregate.get("issue_counts") if isinstance(aggregate, dict) else None
        if isinstance(agg_counts, dict):
            def _as_int(key: str) -> int:
                try:
                    return max(0, int(agg_counts.get(key, 0)))
                except Exception:
                    return 0

            issue_counts["mac"] = _as_int("mac")
            issue_counts["online"] = _as_int("online")
            issue_counts["data"] = _as_int("data")
            issue_counts["tools"] = _as_int("tools")
            issue_counts["poi"] = _as_int("poi") or _as_int("PoI")
        else:
            for r in rewards_data:
                try:
                    if int(r.get("mac_match", 1)) == 0:
                        issue_counts["mac"] += 1
                    if int(r.get("PoC", 1)) == 0:
                        issue_counts["online"] += 1
                    if int(r.get("PoD", 1)) == 0:
                        issue_counts["data"] += 1
                    if self.group in self._tools_groups and int(r.get("tools_gate", 1)) == 0:
                        issue_counts["tools"] += 1
                except Exception:
                    continue

        # For AEM, "data" gate is displayed as "Olostep"
        if self.group == "AEM":
            display_names = {"mac": "mac", "online": "Online", "data": "Olostep", "tools": "Tools"}
            relevant = ["data", "online", "mac"]  # Olostep, Online, mac
        else:
            display_names = {"mac": "MAC", "online": "Online", "data": "Data", "tools": "Tools"}
            relevant = ["mac", "online", "data"]
            if self.group in self._tools_groups:
                relevant.append("tools")

        best_key = None
        best_count = 0
        for k in relevant:
            c = int(issue_counts.get(k, 0) or 0)
            if c > best_count:
                best_key = k
                best_count = c
        
        # Check if all tools are active (BM, RDN, SDN)
        all_tools_active = True
        max_tools = self._max_tools_available()
        if self.group in self._tools_groups and rewards_data:
            # Check average tools count across the period
            tools_counts = [int(r.get("tools_count", 0)) for r in rewards_data if isinstance(r, dict)]
            if tools_counts:
                avg_tools = sum(tools_counts) / len(tools_counts)
                all_tools_active = avg_tools >= max_tools - 0.1  # Allow small variance
        
        # Determine issue text
        if best_key and best_count > 0:
            issue_text = f"{display_names.get(best_key, str(best_key))}: {best_count}x"
        elif self.group in self._tools_groups and not all_tools_active:
            issue_text = "Not all tools enabled"
        else:
            issue_text = "✓ All good"

        self.avg_mult_value.setText(f"{avg_mult:.2f}")
        if full_hours is None or zero_hours is None:
            self.full_hours_value.setText("-- / --")
            self.zero_hours_value.setText("-- / --")
        else:
            self.full_hours_value.setText(f"{full_hours} / {total_hours}h")
            self.zero_hours_value.setText(f"{zero_hours} / {total_hours}h")
        self.issue_value.setText(issue_text)

        # Color for average multiplier (based on performance)
        if avg_mult >= 0.9:
            mult_color = "#10B981"  # Green
        elif avg_mult >= 0.5:
            mult_color = "#F59E0B"  # Orange
        else:
            mult_color = "#EF4444"  # Red
        self.avg_mult_value.setStyleSheet(f"font-size: 18pt; font-weight: bold; color: {mult_color};")
        
        # Color for issue card (based on actual issues, not multiplier)
        if best_key and best_count > 0:
            # There are issues - color based on severity
            issue_color = "#EF4444"  # Red for issues
        elif self.group in self._tools_groups and not all_tools_active:
            # Not all tools enabled - warning
            issue_color = "#F59E0B"  # Orange
        else:
            # All good - always green
            issue_color = "#10B981"  # Green
        self.issue_value.setStyleSheet(f"font-size: 18pt; font-weight: bold; color: {issue_color};")
    
    def _plot_24h_view(self, rewards_data: List[Dict[str, Any]], date: date, display_date: str | None = None):
        """Plot detailed 24-hour rewards view with three panels."""
        self.figure.clear()
        is_mobile = self._is_mobile()
        no_data = len(rewards_data) == 0
        
        # Create three subplots
        hspace = 0.4 if is_mobile else 0.3
        gs = self.figure.add_gridspec(3, 1, height_ratios=[2, 1.5, 1], hspace=hspace)
        ax1 = self.figure.add_subplot(gs[0])  # Multiplier timeline
        ax2 = self.figure.add_subplot(gs[1])  # Gate status heatmap
        ax3 = self.figure.add_subplot(gs[2])  # Tool activity (BM only)
        
        # Prepare data arrays
        hours = list(range(24))
        multipliers = [math.nan] * 24  # missing hour -> no value (breaks line)
        mac_status = [0] * 24
        poc_status = [0] * 24
        pod_status = [0] * 24
        poi_status = [0] * 24
        tools_status = [0] * 24
        tool_counts = [0] * 24
        hours_with_data = set()  # Track which hours have actual data
        
        for slot in rewards_data:
            # Use pre-calculated display hour if available (from _combine_daily_rewards),
            # otherwise fall back to hour directly
            h = int(slot.get("_display_hour", slot.get("hour", -1)))
            
            if 0 <= h < 24:
                hours_with_data.add(h)
                try:
                    multipliers[h] = float(slot.get("multiplier", 0.0))
                except Exception:
                    multipliers[h] = 0.0
                mac_status[h] = int(slot.get("mac_match", 0))
                poc_status[h] = int(slot.get("PoC", 0))
                pod_status[h] = int(slot.get("PoD", 0))
                poi_status[h] = int(slot.get("PoI", 0))
                tools_status[h] = int(slot.get("tools_gate", 0))
                try:
                    tool_counts[h] = int(slot.get("tools_count", len(slot.get("tools", []))))
                except Exception:
                    tool_counts[h] = len(slot.get("tools", []))
        
        # Panel 1: Multiplier Timeline
        self._style_axes(ax1)
        marker_size = 3 if is_mobile else 4
        line_width = 1.5 if is_mobile else 2
        _chart_max = _rewards_mod.BM_BASE_REWARD + _rewards_mod.BM_PER_TOOL_REWARD * self._max_tools_available()
        if not no_data:
            ax1.plot(hours, multipliers, 'o-', color="#10B981", linewidth=line_width, markersize=marker_size)
        ax1.axhline(y=_chart_max, color="#3B82F6", linestyle="--", alpha=0.5, linewidth=1)
        ax1.axhline(y=_chart_max * 0.5, color="#F59E0B", linestyle="--", alpha=0.3, linewidth=1)
        ax1.set_ylim(-0.05, _chart_max + 0.1)
        ax1.set_xlim(-0.5, 23.5)
        ylabel_size = 9 if is_mobile else 10
        ax1.set_ylabel("Multiplier", fontsize=ylabel_size)
        ax1.set_xticks([])
        ax1.grid(True, alpha=0.2, axis='y')
        if no_data:
            ax1.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax1.transAxes,
                     fontsize=9 if is_mobile else 10, color=self._theme.text_muted if self._theme else "#9CA3AF")
        
        # Panel 2: Gate Status Heatmap
        self._style_axes(ax2)
        max_tools = self._max_tools_available()
        if self.group == "AEM":
            # AEM uses simplified gates: Olostep (linked to data), Online, mac
            gate_names = ["Olostep", "Online", "mac"]
            gate_data = [pod_status, poc_status, mac_status]
        else:
            gate_names = ["mac", "Online", "Data"]
            gate_data = [mac_status, poc_status, pod_status]
            if self.group in self._tools_groups and max_tools > 0:
                gate_names.append("Tools")
                gate_data.append(tools_status)
        
        # Create heatmap
        for i, (name, status) in enumerate(zip(gate_names, gate_data)):
            for h in hours:
                if h not in hours_with_data:
                    # Hour not in data -> neutral gray
                    color = "#374151"
                elif no_data:
                    color = "#374151"  # neutral gray for unknown
                else:
                    if name == "Tools" and max_tools > 0:
                        # Tools are tri-state:
                        # 0 tools = red, 0 < tools < max = orange, tools == max = green.
                        n_tools = int(tool_counts[h])
                        if n_tools <= 0:
                            color = "#EF4444"
                        elif n_tools < max_tools:
                            color = "#F59E0B"
                        else:
                            color = "#10B981"
                    else:
                        color = "#10B981" if status[h] == 1 else "#EF4444"
                ax2.add_patch(mpatches.Rectangle((h - 0.4, i - 0.4), 0.8, 0.8,
                                                 facecolor=color, edgecolor="none", alpha=0.8))
        
        ax2.set_xlim(-0.5, 23.5)
        ax2.set_ylim(-0.5, len(gate_names) - 0.5)
        ax2.set_yticks(range(len(gate_names)))
        label_size = 8 if is_mobile else 9
        ylabel_size = 9 if is_mobile else 10
        ax2.set_yticklabels(gate_names, fontsize=label_size)

        # Add hour labels to x-axis only if Panel 3 (Tools) won't be shown
        # Tools groups show Tools panel with hour labels, so skip labels here
        if not (self.group in self._tools_groups and max_tools > 0):
            # Miners without tools: show hour labels on Gates panel
            tick_step = 6 if is_mobile else 3
            tz_label = "Local" if self._use_local_time else "UTC"
            ax2.set_xticks(range(0, 24, tick_step))
            tick_size = 8 if is_mobile else 9
            ax2.set_xticklabels([f"{h:02d}" for h in range(0, 24, tick_step)], fontsize=tick_size)
            ax2.set_xlabel(f"Hour ({tz_label})", fontsize=ylabel_size)
        else:
            # Tools groups: no labels on Gates panel (Tools panel below will show them)
            ax2.set_xticks([])

        ax2.set_ylabel("Gates", fontsize=ylabel_size)
        ax2.grid(False)

        # Panel 3: Tool Activity (BM, RDN, SDN) or hide
        if self.group in self._tools_groups and max_tools > 0:
            self._style_axes(ax3)
            colors = []
            for h in hours:
                if h not in hours_with_data or no_data:
                    colors.append("#374151")  # neutral gray for missing hours
                else:
                    n_tools = int(tool_counts[h])
                    if n_tools <= 0:
                        colors.append("#EF4444")  # red for 0 tools
                    elif n_tools < max_tools:
                        colors.append("#F59E0B")  # orange for partial tools
                    else:
                        colors.append("#10B981")  # green for full tools
            ax3.bar(hours, tool_counts, color=colors, alpha=0.8, width=0.8)
            ax3.set_xlim(-0.5, 23.5)
            ax3.set_ylim(0, max(1.0, float(max_tools) + 0.5))
            ax3.set_yticks(list(range(0, max_tools + 1)))
            xlabel_size = 9 if is_mobile else 10
            ylabel_size = 9 if is_mobile else 10
            tick_size = 8 if is_mobile else 9
            tick_step = 6 if is_mobile else 3
            tz_label = "Local" if self._use_local_time else "UTC"
            ax3.set_xlabel(f"Hour ({tz_label})", fontsize=xlabel_size)
            ax3.set_ylabel("Tools" if is_mobile else "Active Tools", fontsize=ylabel_size)
            ax3.set_xticks(range(0, 24, tick_step))
            # Use local-hour positions directly (data already shifted), so labels stay 00-23
            ax3.set_xticklabels([f"{h:02d}" for h in range(0, 24, tick_step)], fontsize=tick_size)
            ax3.grid(True, alpha=0.2, axis='y')
        else:
            ax3.set_visible(False)
            # Adjust layout to use the space
            gs.set_height_ratios([2.5, 2, 0.5])
        
        # Adjust margins for more space - ensure x-axis labels are visible
        # Use tight_layout first then fine-tune
        try:
            self.figure.tight_layout()
        except Exception:
            pass
        # Additional padding at bottom for x-axis label
        if is_mobile:
            self.figure.subplots_adjust(bottom=0.14, top=0.94)
        else:
            self.figure.subplots_adjust(bottom=0.12, top=0.95)
        
        self.canvas.draw()
    
    def _plot_7d_view(self, all_rewards: List[Dict[str, Any]]):
        """Plot 7-day overview with daily bars and trend."""
        self.figure.clear()
        is_mobile = self._is_mobile()
        
        # Create two subplots
        hspace = 0.35 if is_mobile else 0.25
        gs = self.figure.add_gridspec(2, 1, height_ratios=[2, 1], hspace=hspace)
        ax1 = self.figure.add_subplot(gs[0])  # Daily average multiplier
        ax2 = self.figure.add_subplot(gs[1])  # Issue frequency heatmap
        
        # Calculate daily stats (week-based) from backend-provided aggregates.
        dates: List[date] = []
        daily_avgs: List[float] = []        # bar heights (missing day -> 0 and gray)
        trend_avgs: List[float] = []        # line values (missing day -> NaN to break)
        daily_labels: List[str] = []
        issue_matrix: List[List[int]] = []  # [day][gate_type]
        has_data: List[bool] = []

        if self.group == "AEM":
            # AEM uses simplified gates: Olostep (linked to data), Online, mac
            gate_names = ["Olostep", "Online", "mac"]
        else:
            gate_names = ["mac", "Online", "Data"]
            if self.group in self._tools_groups:
                gate_names.append("Tools")

        for day_data in all_rewards:
            d = day_data["date"]
            raw_rewards = day_data.get("rewards")
            rewards: List[Dict[str, Any]] = [r for r in raw_rewards if isinstance(r, dict)] if isinstance(raw_rewards, list) else []
            ddoc = day_data.get("day_doc")

            dates.append(d)
            daily_labels.append(d.strftime("%m/%d"))

            day_has_data = isinstance(ddoc, dict) and counted_slots_from_day(ddoc) > 0
            has_data.append(day_has_data)

            if day_has_data:
                try:
                    avg = float(ddoc.get("avg_multiplier", 0.0))  # type: ignore[union-attr]
                except Exception:
                    avg = 0.0
                if avg <= 0.0 and rewards:
                    try:
                        avg = sum(float(r.get("multiplier", 0.0)) for r in rewards) / max(1, len(rewards))
                    except Exception:
                        avg = 0.0
                daily_avgs.append(avg)
                trend_avgs.append(avg)

                counts = ddoc.get("issue_counts") if isinstance(ddoc, dict) else None
                issues: List[int] = [0] * len(gate_names)
                if isinstance(counts, dict):
                    # vNext daily aggregates use: tools/data/online/mac
                    # For AEM, "Olostep" maps to "data" field
                    key_map = {"mac": "mac", "Online": "online", "Data": "data", "Tools": "tools", "Olostep": "data"}
                    for idx, name in enumerate(gate_names):
                        src_key = key_map.get(name, name)
                        try:
                            issues[idx] = max(0, int(counts.get(src_key, 0)))
                        except Exception:
                            issues[idx] = 0
                else:
                    # Fallback: count failing hours using the gate booleans (still no multiplier recompute).
                    for r in rewards:
                        try:
                            if self.group == "AEM":
                                # AEM gates: Olostep (data), Online, mac
                                if int(r.get("PoD", 1)) == 0:
                                    issues[0] += 1  # Olostep
                                if int(r.get("PoC", 1)) == 0:
                                    issues[1] += 1  # Online
                                if int(r.get("mac_match", 1)) == 0:
                                    issues[2] += 1  # mac
                            else:
                                # Other groups: mac, Online, Data, [Tools]
                                if int(r.get("mac_match", 1)) == 0:
                                    issues[0] += 1
                                if int(r.get("PoC", 1)) == 0:
                                    issues[1] += 1
                                if int(r.get("PoD", 1)) == 0:
                                    issues[2] += 1
                                if self.group in self._tools_groups:
                                    tools_idx = gate_names.index("Tools")
                                    if int(r.get("tools_gate", 1)) == 0:
                                        issues[tools_idx] += 1
                        except Exception:
                            continue
                issue_matrix.append(issues)
            else:
                daily_avgs.append(0.0)
                trend_avgs.append(math.nan)
                issue_matrix.append([0] * len(gate_names))
        
        # Panel 1: Daily Average Multiplier
        self._style_axes(ax1)
        x_pos = list(range(len(dates)))
        colors = ["#374151" if not has_data[i] else ("#10B981" if avg >= 0.9 else "#F59E0B" if avg >= 0.5 else "#EF4444") for i, avg in enumerate(daily_avgs)]
        ax1.bar(x_pos, daily_avgs, color=colors, alpha=0.8, width=0.7)
        line_width = 1.5 if is_mobile else 2
        marker_size = 5 if is_mobile else 6
        _chart_max = _rewards_mod.BM_BASE_REWARD + _rewards_mod.BM_PER_TOOL_REWARD * self._max_tools_available()
        ax1.plot(x_pos, trend_avgs, 'o-', color="#3B82F6", linewidth=line_width, markersize=marker_size, alpha=0.7)
        ax1.axhline(y=_chart_max, color="#3B82F6", linestyle="--", alpha=0.5, linewidth=1)
        ax1.set_ylim(0, _chart_max + 0.1)
        ylabel_size = 9 if is_mobile else 10
        tick_size = 8 if is_mobile else 9
        ax1.set_ylabel("Avg" if is_mobile else "Avg Multiplier", fontsize=ylabel_size)
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(daily_labels, fontsize=tick_size)
        ax1.grid(True, alpha=0.2, axis='y')
        
        # Panel 2: Issue Frequency Heatmap
        self._style_axes(ax2)
        max_issues = max(max(day_issues) for day_issues in issue_matrix) if issue_matrix else 1
        
        for day_idx, day_issues in enumerate(issue_matrix):
            for gate_idx, issue_count in enumerate(day_issues):
                if max_issues > 0:
                    intensity = issue_count / max_issues
                else:
                    intensity = 0
                # Missing day -> neutral gray
                if not has_data[day_idx]:
                    color = "#374151"
                else:
                    # Color gradient: green (no issues) to red (many issues)
                    if issue_count == 0:
                        color = "#10B981"
                    elif intensity < 0.5:
                        color = "#F59E0B"
                    else:
                        color = "#EF4444"
                
                ax2.add_patch(mpatches.Rectangle((day_idx - 0.4, gate_idx - 0.4), 0.8, 0.8,
                                                 facecolor=color, edgecolor="#1f2a3d", alpha=0.8))
                # Add count text
                if issue_count > 0 and has_data[day_idx]:
                    text_size = 7 if is_mobile else 8
                    ax2.text(day_idx, gate_idx, str(issue_count), ha="center", va="center",
                            fontsize=text_size, color="#ffffff", fontweight="bold")
        
        ax2.set_xlim(-0.5, len(dates) - 0.5)
        ax2.set_ylim(-0.5, len(gate_names) - 0.5)
        ax2.set_yticks(range(len(gate_names)))
        label_size = 8 if is_mobile else 9
        ylabel_size = 9 if is_mobile else 10
        ax2.set_yticklabels(gate_names, fontsize=label_size)
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(daily_labels, fontsize=label_size)
        ax2.set_ylabel("Issues" if is_mobile else "Issue Count", fontsize=ylabel_size)
        ax2.set_xlabel("Date", fontsize=ylabel_size)
        ax2.grid(False)
        
        # Adjust margins for more space - ensure x-axis labels are visible
        try:
            self.figure.tight_layout()
        except Exception:
            pass
        # Additional padding at bottom for x-axis label
        if is_mobile:
            self.figure.subplots_adjust(bottom=0.14, top=0.94)
        else:
            self.figure.subplots_adjust(bottom=0.12, top=0.95)
        
        self.canvas.draw()
    
    def _style_axes(self, ax):
        """Apply theme styling to axes."""
        if not self._theme:
            return
        try:
            is_mobile = self._is_mobile()
            tick_size = 8 if is_mobile else 9
            ax.set_facecolor(self._theme.bg_alt)
            ax.tick_params(colors=self._theme.text_primary, labelsize=tick_size)
            for spine in ax.spines.values():
                spine.set_color(self._theme.border)
            if hasattr(ax, 'xaxis'):
                ax.xaxis.label.set_color(self._theme.text_primary)
            if hasattr(ax, 'yaxis'):
                ax.yaxis.label.set_color(self._theme.text_primary)
            if hasattr(ax, 'title'):
                ax.title.set_color(self._theme.text_primary)
        except Exception:
            pass
    
    def _detect_mobile(self) -> bool:
        """Detect mobile screen size."""
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                if geom and geom.width() < 800:
                    return True
        except Exception:
            pass
        return False
    
    def set_service_warning(self, warning: Optional[str]):
        """Update status label with service warning (e.g., Mysterium offline)."""
        if warning:
            # Append warning to current status
            current = self.status_label.text() or ""
            if current and not current.endswith(warning):
                self.status_label.setText(f"{current} ⚠ {warning}")
            elif not current:
                self.status_label.setText(f"⚠ {warning}")
        else:
            # Clear warning by reloading current data
            self._load_data()
    
    def _is_mobile(self) -> bool:
        """Check if mobile mode."""
        return self._mobile_hint

    def showEvent(self, event) -> None:
        """Jump to today and start periodic auto-refresh when the tab becomes visible."""
        super().showEvent(event)
        if not HAVE_MATPLOTLIB:
            return
        # Keep max date current (handles midnight rollover)
        utc_today = self._current_utc_qdate()
        self.date_edit.setMaximumDate(utc_today)
        # Jump to today; dateChanged signal will trigger _load_data automatically.
        # If already on today, manually refresh instead.
        if self.date_edit.date() != utc_today:
            self.date_edit.setDate(utc_today)
        else:
            self._load_data()
        self._refresh_timer.start()

    def hideEvent(self, event) -> None:
        """Stop auto-refresh when the tab is hidden."""
        super().hideEvent(event)
        self._refresh_timer.stop()

    def update_with_measurements(self, measurements: Dict[str, Any]) -> None:
        """Update widget with fresh measurement data from service.
        
        This is called by main_window when new measurements are polled.
        Currently a no-op placeholder for future reward tracking integration.
        
        Args:
            measurements: Measurement dict with pod_status, hardware_stats, poc_applications, etc.
        """
        # Future: Extract current earnings from PoC applications and update live display
        # For now, rewards history relies on historical status_week files
        pass
