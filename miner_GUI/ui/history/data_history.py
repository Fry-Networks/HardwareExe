"""Data History tab for viewing logged sensor measurements over time."""

import os
import json
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from typing import List, Dict, Optional, TYPE_CHECKING, Any

from PySide6 import QtWidgets, QtCore, QtGui
from config_profile import GROUP
from miner_GUI.utils.data import data_dir_gui
from miner_GUI.utils.csv_reader import read_full_csv, get_csv_path_for_date

# Matplotlib imports with typing support
try:
    # Use QtAgg backend compatible with PySide6
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    HAVE_MATPLOTLIB = True
except Exception:
    HAVE_MATPLOTLIB = False
    if TYPE_CHECKING:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure


class DataHistoryWidget(QtWidgets.QWidget):
    """Widget to display historical sensor data from daily log files."""
    
    def __init__(self, parent=None, screen_size_pref: str = ""):
        super().__init__(parent)
        self.group = GROUP
        self.current_date = datetime.now().date()
        self._bandwidth_groups = ("BM", "Bandwidth")  # Bandwidth miners (BM); keep legacy alias
        # Prefer explicit screen size preference; fallback to detection
        self._mobile_hint = bool(screen_size_pref == "mobile") or self._detect_mobile()
        # Track the last maximum date applied to the date picker to avoid navigation past today
        try:
            self._last_max_date = QtCore.QDate.currentDate()
        except Exception:
            self._last_max_date = None
        # Try to load FryNetworks theme for consistent styling
        try:
            from theme import Theme  # type: ignore
            self._theme = Theme()
        except Exception:
            self._theme = None
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8 if self._is_mobile() else 10)
        
        # Title + "Open CSV" button
        title_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"📊 {self.group} Data History")
        title_size = "12pt" if self._is_mobile() else "14pt"
        title.setStyleSheet(f"font-size: {title_size}; font-weight: bold; padding: 4px;")
        title_row.addWidget(title)

        self.open_btn = QtWidgets.QPushButton("Open CSV")
        self.open_btn.setAccessibleName("history_data_button_open")
        if self._is_mobile():
            self.open_btn.setMinimumWidth(80)
        self.open_btn.clicked.connect(self._open_csv_file)
        title_row.addStretch(1)
        title_row.addWidget(self.open_btn)
        layout.addLayout(title_row)
        
        # Date selector
        date_layout = QtWidgets.QHBoxLayout()
        date_layout.addWidget(QtWidgets.QLabel("Select Date:"))
        
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setAccessibleName("history_data_dateedit_date")
        self.date_edit.setObjectName("dataHistoryDateEdit")
        self.date_edit.setDate(QtCore.QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMaximumDate(QtCore.QDate.currentDate())
        if self._theme:
            try:
                radius = max(4, int(self._theme.radius / 2))
                font_size = "10pt" if self._is_mobile() else "12pt"
                self.date_edit.setStyleSheet(
                    f"""
                    QDateEdit#dataHistoryDateEdit {{
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
                    QCalendarWidget QWidget {{
                        background-color: {self._theme.bg_panel};
                        color: {self._theme.text_primary};
                    }}
                    """
                )
            except Exception:
                # Styling is best-effort; fall back to default palette if Qt rejects the sheet.
                pass
        self.date_edit.dateChanged.connect(self._on_date_changed)
        date_layout.addWidget(self.date_edit)
        
        # Prev/Next day controls (text arrows for desktop, compact on mobile)
        is_mobile = self._is_mobile()
        self.prev_btn = QtWidgets.QPushButton("◀ Prev" if not is_mobile else "◀")
        self.prev_btn.setAccessibleName("history_data_button_prev")
        self.prev_btn.setToolTip("Previous day")
        self.prev_btn.clicked.connect(self._prev_day)
        if is_mobile:
            self.prev_btn.setFixedSize(36, 28)
        else:
            self.prev_btn.setMinimumWidth(70)
        date_layout.addWidget(self.prev_btn)
        
        self.next_btn = QtWidgets.QPushButton("Next ▶" if not is_mobile else "▶")
        self.next_btn.setAccessibleName("history_data_button_next")
        self.next_btn.setToolTip("Next day")
        self.next_btn.clicked.connect(self._next_day)
        if is_mobile:
            self.next_btn.setFixedSize(36, 28)
        else:
            self.next_btn.setMinimumWidth(70)
        date_layout.addWidget(self.next_btn)
        
        self.refresh_btn = QtWidgets.QPushButton("🔄" if is_mobile else "🔄 Refresh")
        self.refresh_btn.setAccessibleName("history_data_button_refresh")
        self.refresh_btn.setToolTip("Reload data for selected date")
        self.refresh_btn.clicked.connect(self._load_data)
        if is_mobile:
            self.refresh_btn.setFixedSize(36, 28)
        else:
            self.refresh_btn.setMinimumWidth(90)
        date_layout.addWidget(self.refresh_btn)

        date_layout.addStretch()
        layout.addLayout(date_layout)
        
        # Status label (muted text color from theme)
        self.status_label = QtWidgets.QLabel("Loading data...")
        self.status_label.setAccessibleName("history_data_label_status")
        if hasattr(self, '_theme') and self._theme:
            self.status_label.setStyleSheet(f"color: {self._theme.text_muted}; font-size: 10pt;")
        layout.addWidget(self.status_label)
        
        # Chart area
        if HAVE_MATPLOTLIB:
            self.figure = Figure(figsize=(10, 6), facecolor=(self._theme.bg_panel if hasattr(self, '_theme') and self._theme else None))
            self.canvas = FigureCanvasQTAgg(self.figure)
            layout.addWidget(self.canvas)
        else:
            error_label = QtWidgets.QLabel(
                "📉 Matplotlib not available\n\n"
                "Install matplotlib to view charts:\n"
                "pip install matplotlib"
            )
            error_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("""
                QLabel {
                    background-color: #FEF3C7;
                    border: 1px solid #F59E0B;
                    border-radius: 6px;
                    padding: 20px;
                    color: #92400E;
                    font-size: 12px;
                }
            """)
            layout.addWidget(error_label)
        
        # Initial load
        if HAVE_MATPLOTLIB:
            self._load_data()

    # ---- Styling helpers -------------------------------------------------
    def _style_axes(self, ax):
        """Apply FryNetworks theme styling to a matplotlib Axes."""
        if not hasattr(self, '_theme') or not self._theme:
            return
        t = self._theme
        try:
            ax.set_facecolor(t.bg_alt)
            ax.grid(True, alpha=0.2, color=t.border)
            for spine in ax.spines.values():
                spine.set_color(t.border)
            ax.tick_params(colors=t.text_primary)
            ax.xaxis.label.set_color(t.text_primary)
            ax.yaxis.label.set_color(t.text_primary)
            ax.title.set_color(t.text_primary)
        except Exception:
            pass
        self._apply_mobile_fonts(ax)

    def _style_legend(self, legend):
        if not legend or not hasattr(self, '_theme') or not self._theme:
            return
        t = self._theme
        try:
            frame = legend.get_frame()
            frame.set_facecolor(t.bg_alt)
            frame.set_edgecolor(t.border)
            for txt in legend.get_texts():
                txt.set_color(t.text_primary)
        except Exception:
            pass
        self._apply_mobile_fonts(None, legend)
    
    def _on_date_changed(self):
        """Handle date change from date picker."""
        qdate = self.date_edit.date()
        self.current_date = datetime(qdate.year(), qdate.month(), qdate.day()).date()
        self._load_data()
    
    def _prev_day(self):
        """Go to previous day."""
        self.current_date -= timedelta(days=1)
        self.date_edit.setDate(QtCore.QDate(
            self.current_date.year,
            self.current_date.month,
            self.current_date.day
        ))
    
    def _next_day(self):
        """Go to next day."""
        today = datetime.now().date()
        today_q = QtCore.QDate.currentDate()
        self.date_edit.setMaximumDate(today_q)
        self._last_max_date = today_q
        new_date = self.current_date + timedelta(days=1)
        if new_date <= today:
            self.current_date = new_date
            self.date_edit.setDate(QtCore.QDate(
                self.current_date.year,
                self.current_date.month,
                self.current_date.day
            ))
    
    def _load_data(self):
        """Load and display data for the selected date."""
        if not HAVE_MATPLOTLIB:
            return

        # Update max date; if day rolled over and we were on the previous max, advance to today.
        today_q = QtCore.QDate.currentDate()
        self.date_edit.setMaximumDate(today_q)
        if getattr(self, "_last_max_date", None) is not None and today_q != self._last_max_date and self.date_edit.date() == self._last_max_date:
            self.current_date = datetime.now().date()
            self.date_edit.setDate(today_q)
        self._last_max_date = today_q

        if self.group == "AEM":
            events = self._load_aem_poi_events()
            if not events:
                self.status_label.setText(
                    f"No PoI history for {self.current_date.strftime('%Y-%m-%d')}"
                )
                self.figure.clear()
                self.canvas.draw()
                return
            self.status_label.setText(
                f"Loaded {len(events)} PoI events for {self.current_date.strftime('%Y-%m-%d')}"
            )
            self._plot_aem_history(events)
            return

        # Determine which measurement file to load.
        # Use the *_real_YYYYMMDD.csv files for history (graph + Open CSV button)
        sensor_mapping = {
            "bm": "bandwidth",
            "satellite": "satellite",
            "radiation": "radiation",
            "decibel": "decibel",
            "aem": "aem",
            "idm": "decibel",
            "ism": "satellite",
            "irm": "radiation",
        }

        sensor_lower = self.group.lower()
        filename = sensor_mapping.get(sensor_lower, sensor_lower)
        log_file = get_csv_path_for_date(filename, day=self.current_date, suffix="real")

        if not log_file.exists():
            self.status_label.setText(f"No data for {self.current_date.strftime('%Y-%m-%d')}")
            self.figure.clear()
            self.canvas.draw()
            return

        # Remember the log file used for UI actions
        self._current_log_file = log_file

        # Read CSV data
        try:
            data = read_full_csv(log_file)
            if not data:
                self.status_label.setText("No valid data in log file")
                self.figure.clear()
                self.canvas.draw()
                return

            self.status_label.setText(f"Loaded {len(data)} records from {self.current_date.strftime('%Y-%m-%d')}")
            try:
                self._plot_data(data)
            except Exception as pe:
                # Guard against any plotting error bringing down the app
                self.status_label.setText(f"Plot error: {pe}")
                self.figure.clear()
                self.canvas.draw()
        except Exception as e:
            self.status_label.setText(f"Error loading data: {e}")
            self.figure.clear()
            self.canvas.draw()
            self._current_log_file = None

    def _load_aem_poi_events(self) -> List[Dict[str, Any]]:
        """Load PoI timeline from daily status JSON."""
        status_dir = data_dir_gui() / "status"
        path = status_dir / f"status-{self.current_date.strftime('%Y%m%d')}.json"
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                doc = json.load(handle)
        except Exception:
            return []

        def _normalize_events(entries: Any) -> List[Dict[str, Any]]:
            norm: List[Dict[str, Any]] = []
            if isinstance(entries, dict):
                entries = list(entries.values())
            if not isinstance(entries, list):
                return norm
            for idx, entry in enumerate(entries):
                if isinstance(entry, dict):
                    timestamp = entry.get("ts") or entry.get("timestamp") or entry.get("time")
                    status = entry.get("poi") or entry.get("status") or entry.get("value")
                else:
                    timestamp = None
                    status = entry
                if not status:
                    continue
                dt_obj = self._parse_timestamp(timestamp, fallback_index=idx)
                norm.append({"timestamp": dt_obj, "value": str(status)})
            return norm

        events: List[Dict[str, Any]] = []
        for key in (
            "poi_history",
            "PoIHistory",
            "poiTimeline",
            "PoITimeline",
            "poi_log",
            "poiLog",
        ):
            if key in doc:
                events = _normalize_events(doc.get(key))
                if events:
                    break

        if not events:
            poi_value = doc.get("PoI") or doc.get("poi") or doc.get("POI")
            if poi_value is not None:
                dt_obj = datetime.combine(self.current_date, dt_time(hour=12))
                events = [{"timestamp": dt_obj, "value": str(poi_value)}]

        events = [ev for ev in events if ev.get("timestamp")]
        events.sort(key=lambda ev: ev["timestamp"])  # type: ignore[arg-type]
        return events

    def _parse_timestamp(self, ts_value: Optional[str], fallback_index: int) -> datetime:
        if isinstance(ts_value, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(ts_value, fmt)
                except Exception:
                    continue
            try:
                return datetime.fromisoformat(ts_value)
            except Exception:
                pass
        base = datetime.combine(self.current_date, dt_time.min)
        return base + timedelta(minutes=10 * fallback_index)

    @QtCore.Slot()
    def _open_csv_file(self) -> None:
        """Open the currently loaded CSV file in the default app, if it exists."""
        log_file = getattr(self, "_current_log_file", None)
        if not log_file:
            QtWidgets.QMessageBox.information(self, "Open CSV", "No CSV file loaded for this date.")
            return
        try:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(log_file)))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Open CSV", f"Could not open file:\n{exc}")
    
    def _plot_data(self, data: List[Dict]):
        """Plot the data based on sensor type."""
        self.figure.clear()
        
        if self.group == "Radiation":
            self._plot_radiation(data)
        elif self.group == "Satellite":
            self._plot_satellite(data)
        elif self.group == "Decibel":
            self._plot_decibel(data)
        elif self.group in self._bandwidth_groups:
            # Always plot real bandwidth test data (10min interval)
            self._plot_bandwidth_realtest(data)
        elif self.group == "AEM":
            self._plot_aem_history(data)
        
        self.canvas.draw()
    
    def _plot_radiation(self, data: List[Dict]):
        """Plot Geiger counter data (CPM, μSv/h, mR/h)."""
        
        # Determine mobile-friendly sizing
        if self._is_mobile():
            lw = 1       # thinner lines on mobile
            ms = 2       # smaller markers
        else:
            lw = 2       # desktop defaults
            ms = 4

        ax = self.figure.add_subplot(111)
        self._style_axes(ax)
        
        # Build aligned time/value pairs to avoid length mismatches
        t_vals, y_vals = [], []
        for row in data:
            v = row.get('cpm')
            if v is None or v == "":
                continue
            try:
                y_vals.append(float(v))
                t_vals.append(row['timestamp'])
            except Exception:
                continue

        if not t_vals:
            ax.text(0.5, 0.5, 'No CPM data', transform=ax.transAxes, ha='center', va='center', color='#666')
        else:
            ax.plot(t_vals, y_vals, 'o-', color='#EF4444', linewidth=lw, markersize=ms, label='CPM')
        ax.set_xlabel('Time')
        ax.set_ylabel('CPM (Counts Per Minute)', color='#EF4444')
        ax.tick_params(axis='y', labelcolor='#EF4444')
        leg = ax.legend(loc='upper left')
        self._style_legend(leg)
        ax.set_title(f'Radiation Levels - {self.current_date.strftime("%Y-%m-%d")}')
        self.figure.autofmt_xdate()
    
    def _plot_satellite(self, data: List[Dict]):
        """Plot GNSS data (satellites, HDOP)."""
        ax1 = self.figure.add_subplot(111)
        self._style_axes(ax1)
        
        # Satellites timeline (aligned)
        t_sats, v_sats = [], []
        for row in data:
            v = row.get('sats')
            if v is None or v == "":
                continue
            try:
                v_sats.append(int(v))
                t_sats.append(row['timestamp'])
            except Exception:
                continue

        if not t_sats:
            ax1.text(0.5, 0.5, 'No satellite data', transform=ax1.transAxes, ha='center', va='center', color='#666')
        else:
            ax1.plot(t_sats, v_sats, 'o-', color='#3B82F6', linewidth=2, markersize=4, label='Satellites')
        ax1.set_xlabel('Time')
        ax1.set_ylabel('Satellites in View', color='#3B82F6')
        ax1.tick_params(axis='y', labelcolor='#3B82F6')
        ax1.grid(True, alpha=0.3)
        ax1.set_title(f'GNSS Data - {self.current_date.strftime("%Y-%m-%d")}')
        
        # Add HDOP on second axis if available (aligned)
        t_hdop, v_hdop = [], []
        for row in data:
            v = row.get('hdop')
            if v is None or v == "":
                continue
            try:
                v_hdop.append(float(v))
                t_hdop.append(row['timestamp'])
            except Exception:
                continue
        if t_hdop:
            ax2 = ax1.twinx()
            self._style_axes(ax2)
            ax2.plot(t_hdop, v_hdop, 's-', color='#F59E0B', linewidth=2, markersize=4, label='HDOP')
            ax2.set_ylabel('HDOP (Accuracy)', color='#F59E0B')
            ax2.tick_params(axis='y', labelcolor='#F59E0B')
            self._apply_mobile_fonts(ax2)
        
        self.figure.autofmt_xdate()
        self._apply_mobile_fonts(ax1)
    
    def _plot_decibel(self, data: List[Dict]):
        """Plot audio level data (dBFS)."""
        # Determine mobile-friendly sizing
        if self._is_mobile():
            lw = 1       # thinner lines on mobile
            ms = 2       # smaller markers
        else:
            lw = 2       # desktop defaults
            ms = 4
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)
        
        t_vals, y_vals = [], []
        for row in data:
            v = row.get('dbfs')
            if v is None or v == "":
                continue
            try:
                y_vals.append(float(v))
                t_vals.append(row['timestamp'])
            except Exception:
                continue

        if not t_vals:
            ax.text(0.5, 0.5, 'No audio data', transform=ax.transAxes, ha='center', va='center', color='#666')
        else:
            ax.plot(t_vals, y_vals, 'o-', color='#8B5CF6', linewidth=lw, markersize=ms, label='Audio Level')
        ax.set_xlabel('Time')
        ax.set_ylabel('dBFS (Decibels Full Scale)', color='#8B5CF6')
        ax.tick_params(axis='y', labelcolor='#8B5CF6')
        leg = ax.legend(loc='upper left')
        self._style_legend(leg)
        ax.set_title(f'Audio Levels - {self.current_date.strftime("%Y-%m-%d")}')
        ax.axhline(y=-60, color='orange', linestyle='--', alpha=0.5, label='Moderate')
        ax.axhline(y=-30, color='red', linestyle='--', alpha=0.5, label='Loud')
        self._apply_mobile_fonts(ax, leg)
        self._apply_mobile_fonts(ax, leg)
        self.figure.autofmt_xdate()
    
    def _plot_bandwidth(self, data: List[Dict]):
        """Plot instantaneous bandwidth data (download/upload)."""
        # Determine mobile-friendly sizing
        if self._is_mobile():
            lw = 1       # thinner lines on mobile
            ms = 2       # smaller markers
        else:
            lw = 2       # desktop defaults
            ms = 4
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)
        
        t_dl, v_dl = [], []
        t_ul, v_ul = [], []
        for row in data:
            dv = row.get('dl')
            if dv not in (None, ""):
                try:
                    v_dl.append(float(dv))
                    t_dl.append(row['timestamp'])
                except Exception:
                    pass
            uv = row.get('ul')
            if uv not in (None, ""):
                try:
                    v_ul.append(float(uv))
                    t_ul.append(row['timestamp'])
                except Exception:
                    pass

        if t_dl:
            pairs = sorted(zip(t_dl, v_dl), key=lambda tv: tv[0])
            x_dl, y_dl = zip(*pairs)
            ax.plot(x_dl, y_dl, color='#10B981', linewidth=lw, marker='o', linestyle='-', markersize=ms, label='Download')
        if t_ul:
            pairs = sorted(zip(t_ul, v_ul), key=lambda tv: tv[0])
            x_ul, y_ul = zip(*pairs)
            ax.plot(x_ul, y_ul, color='#F59E0B', linewidth=lw, marker='s', linestyle='-', markersize=ms, label='Upload')
        ax.set_xlabel('Time')
        ax.set_ylabel('Speed (Mbps)')
        ax.grid(True, alpha=0.3)
        leg = ax.legend(loc='upper left')
        self._apply_mobile_fonts(ax, leg)
        ax.set_title(f'Network Bandwidth - {self.current_date.strftime("%Y-%m-%d")}')
        self.figure.autofmt_xdate()
    
    def _plot_bandwidth_realtest(self, data: List[Dict]):
        """Plot real bandwidth test data (download/upload)."""
        # Determine mobile-friendly sizing
        if self._is_mobile():
            lw = 1       # thinner lines on mobile
            ms = 2       # smaller markers
        else:
            lw = 2       # desktop defaults
            ms = 4
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)
        
        t_dl, v_dl = [], []
        t_ul, v_ul = [], []
        for row in data:
            # Support both old (dl/ul) and new (download_mbps/upload_mbps) column names
            dv = row.get('download_mbps') or row.get('dl')
            if dv not in (None, ""):
                try:
                    v_dl.append(float(dv))
                    t_dl.append(row['timestamp'])
                except Exception:
                    pass
            uv = row.get('upload_mbps') or row.get('ul')
            if uv not in (None, ""):
                try:
                    v_ul.append(float(uv))
                    t_ul.append(row['timestamp'])
                except Exception:
                    pass

        if t_dl:
            pairs = sorted(zip(t_dl, v_dl), key=lambda tv: tv[0])
            x_dl, y_dl = zip(*pairs)
            # Use plot_date for proper datetime handling
            ax.plot_date(x_dl, y_dl, color='#10B981', linewidth=lw, marker='o', linestyle='-', markersize=ms, label='Download (Real Test)', xdate=True)
        if t_ul:
            pairs = sorted(zip(t_ul, v_ul), key=lambda tv: tv[0])
            x_ul, y_ul = zip(*pairs)
            # Use plot_date for proper datetime handling
            ax.plot_date(x_ul, y_ul, color='#F59E0B', linewidth=lw, marker='s', linestyle='-', markersize=ms, label='Upload (Real Test)', xdate=True)
        ax.set_xlabel('Time')
        ax.set_ylabel('Speed (Mbps)')
        leg = ax.legend(loc='upper left')
        self._style_legend(leg)
        self._apply_mobile_fonts(ax, leg)
        ax.set_title(f'Real Bandwidth Test Results - {self.current_date.strftime("%Y-%m-%d")}')
        self.figure.autofmt_xdate()

    def _plot_aem_history(self, events: List[Dict[str, Any]]):
        """Plot PoI state transitions for AEM devices."""
        ax = self.figure.add_subplot(111)
        self._style_axes(ax)

        filtered = [ev for ev in events if ev.get("timestamp") and ev.get("value")]
        if not filtered:
            ax.text(
                0.5,
                0.5,
                'No PoI events recorded',
                transform=ax.transAxes,
                ha='center',
                va='center',
                color='#666',
            )
            self.canvas.draw()
            return

        filtered.sort(key=lambda ev: ev["timestamp"])  # type: ignore[arg-type]
        status_to_idx: Dict[str, int] = {}
        idx_labels: List[str] = []
        times = []
        values = []
        for ev in filtered:
            status = str(ev["value"])
            if status not in status_to_idx:
                status_to_idx[status] = len(status_to_idx)
                idx_labels.append(status)
            times.append(ev["timestamp"])
            values.append(status_to_idx[status])

        ax.step(times, values, where='post', color='#f59e0b', linewidth=2)
        ax.scatter(times, values, color='#f97316', s=32, zorder=10)
        ax.set_xlabel('Time')
        ax.set_ylabel('PoI state')
        ax.set_title(f'PoI History - {self.current_date.strftime("%Y-%m-%d")}')
        ax.set_yticks(list(status_to_idx.values()))
        ax.set_yticklabels(idx_labels)
        ax.set_ylim(-0.5, max(values) + 0.5 if values else 0.5)
        self.figure.autofmt_xdate()

    def _detect_mobile(self) -> bool:
        """Best-effort mobile detection based on available screen width."""
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                if geom and geom.width() < 800:
                    return True
        except Exception:
            return False
        return False

    def _is_mobile(self) -> bool:
        """Return cached mobile hint."""
        return bool(getattr(self, "_mobile_hint", False))

    def update_with_measurements(self, measurements: Dict[str, Any]) -> None:
        """Update widget with fresh measurement data from service.
        
        This is called by main_window when new measurements are polled.
        Currently a no-op placeholder for future live data integration.
        
        Args:
            measurements: Measurement dict with pod_status, hardware_stats, poc_applications, etc.
        """
        # Future: Could display live sensor readings alongside historical data
        # For now, data history relies on daily CSV log files
        pass

    def _apply_mobile_fonts(self, ax, legend=None) -> None:
        """Shrink fonts on mobile-sized screens."""
        try:
            if not getattr(self, "_mobile_hint", False):
                return
            if ax:
                try:
                    ax.title.set_fontsize(8)
                    ax.xaxis.label.set_fontsize(8)
                    ax.yaxis.label.set_fontsize(8)
                    ax.tick_params(labelsize=7)
                    ax.margins(x=0.15)
                    self.figure.subplots_adjust(bottom=0.22, left=0.15, right=0.95, top=0.85)
                except Exception:
                    pass
            if legend:
                try:
                    for txt in legend.get_texts():
                        txt.set_fontsize(8)
                except Exception:
                    pass
        except Exception:
            pass





