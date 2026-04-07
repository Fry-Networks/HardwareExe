"""Custom chart widgets for displaying mining data."""

from typing import Sequence
from PySide6 import QtWidgets, QtCore, QtGui

# Detect matplotlib availability
HAVE_MPL = False
Figure = None
FigureCanvas = None

try:
    from matplotlib.figure import Figure
    # Try different backend import patterns
    try:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        HAVE_MPL = True
    except ImportError:
        try:
            # For older matplotlib versions, use Qt-agnostic backend
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            HAVE_MPL = True
        except ImportError:
            pass
except ImportError:
    pass


def ensure_qapplication():
    """Ensure QApplication exists for widget creation."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


class _SimpleBarChart(QtWidgets.QWidget):
    """Lightweight Qt-based bar chart used when matplotlib is unavailable."""

    def __init__(
        self,
        parent=None,
        *,
        max_value: float = 100.0,
        bar_color: str = "#ef4444",
        bg_color: str = "#111827",
        plot_color: str = "#172135",
        tick_color: str = "#94a3b8",
        tick_step: int | None = None,
        compact: bool = False,
    ):
        super().__init__(parent)
        self._values: list[float] = []
        self._labels: list[str] = []
        self._max_value = max(1.0, float(max_value))
        self._bar_color = QtGui.QColor(bar_color)
        self._bg_color = QtGui.QColor(bg_color)
        self._plot_color = QtGui.QColor(plot_color)
        self._tick_color = QtGui.QColor(tick_color)
        self._tick_step = tick_step
        self._compact = compact
        self.setMinimumHeight(140 if compact else 160)
        self.setMouseTracking(True)

    def set_data(self, values: Sequence[float], labels: Sequence[str]) -> None:
        """Store data and trigger a repaint."""
        try:
            self._values = [max(0.0, float(v)) for v in values]
        except Exception:
            self._values = []
        self._labels = list(labels)
        self.update()

    def _bar_geometry(self):
        """Return (plot_rect, bar_width, spacing)."""
        rect = self.rect()
        plot_rect = rect.adjusted(12, 12, -12, -28)
        n = max(1, len(self._values))
        spacing = 4 if self._compact else 6
        bar_width = max(4, (plot_rect.width() - spacing * (n - 1)) / max(1, n))
        return plot_rect, bar_width, spacing

    def _x_tick_step(self) -> int:
        """Determine how often to show x-axis labels to avoid overlap."""
        if self._tick_step:
            return max(1, self._tick_step)
        n = max(1, len(self._values))
        # Aim for ~8 visible labels
        return max(1, int(round(n / 8)))

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # type: ignore[override]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        rect = self.rect()
        painter.fillRect(rect, self._bg_color)

        plot_rect = rect.adjusted(12, 12, -12, -28)
        painter.fillRect(plot_rect, self._plot_color)

        if not self._values:
            painter.setPen(self._tick_color)
            painter.drawText(plot_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "Chart unavailable")
            return

        max_val = max(self._max_value, max(self._values))
        base_y = plot_rect.bottom()
        height = plot_rect.height()
        n = len(self._values)
        spacing = 6
        bar_width = max(4, (plot_rect.width() - spacing * (n - 1)) / max(1, n))

        # Grid / y ticks at 0, 50%, 100%
        painter.setPen(QtGui.QPen(self._tick_color, 1, QtCore.Qt.PenStyle.SolidLine))
        for frac in (0.0, 0.5, 1.0):
            y = base_y - frac * height
            painter.setOpacity(0.35)
            painter.drawLine(plot_rect.left(), int(y), plot_rect.right(), int(y))
            painter.setOpacity(1.0)
            label = f"{int(frac * max_val)}"
            painter.drawText(plot_rect.left() + 2, int(y) - 2, label)

        # Bars
        painter.setBrush(self._bar_color)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for idx, val in enumerate(self._values):
            x = plot_rect.left() + idx * (bar_width + spacing)
            bar_h = 0 if max_val <= 0 else (val / max_val) * height
            y = base_y - bar_h
            painter.drawRoundedRect(QtCore.QRectF(x, y, bar_width, bar_h), 2, 2)

        # X labels
        painter.setPen(self._tick_color)
        tick_step = self._x_tick_step()
        for idx, label in enumerate(self._labels):
            if idx % tick_step != 0:
                continue
            x = plot_rect.left() + idx * (bar_width + spacing) + bar_width / 2
            painter.drawText(
                QtCore.QPointF(x - 12, rect.bottom() - 8),
                str(label),
            )

        painter.end()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        """Show tooltip with percentage when hovering a bar."""
        if not self._values:
            return super().mouseMoveEvent(event)
        plot_rect, bar_width, spacing = self._bar_geometry()
        if not plot_rect.contains(event.pos()):
            self.setToolTip("")
            return super().mouseMoveEvent(event)
        relative_x = event.pos().x() - plot_rect.left()
        denom = bar_width + spacing
        if denom <= 0:
            return super().mouseMoveEvent(event)
        idx = int(relative_x // denom)
        if 0 <= idx < len(self._values):
            label = self._labels[idx] if idx < len(self._labels) else ""
            val = self._values[idx]
            self.setToolTip(f"{label}: {val:.1f}%")
        else:
            self.setToolTip("")
        return super().mouseMoveEvent(event)


class HourlyBar(QtWidgets.QWidget):
    """24-hour bar chart widget showing hourly mining data."""
    
    def __init__(self, parent=None, *, small_fonts: bool = False):
        # Ensure QApplication exists for testing
        ensure_qapplication()
        super().__init__(parent)
        self._small_fonts = bool(small_fonts)
        self._fallback_chart: _SimpleBarChart | None = None
        self._hover_cid = None
        self._hover_annotation = None

        if HAVE_MPL and Figure is not None and FigureCanvas is not None:
            self.fig = Figure(figsize=(6, 2), dpi=100, constrained_layout=False)
            self.ax = self.fig.add_subplot(111)
            self.canvas = FigureCanvas(self.fig)
            try:
                self.canvas.setMouseTracking(True)
            except Exception:
                pass

            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(self.canvas)
        else:
            self.fig = None
            self.ax = None
            self.canvas = None
            lay = QtWidgets.QVBoxLayout(self)
            self._fallback_chart = _SimpleBarChart(self, tick_step=3, compact=bool(self._small_fonts))
            lay.addWidget(self._fallback_chart)
        
        # Initialize with empty data
        self.draw_counts([0]*24, [f"{h:02d}" for h in range(24)])
    
    def draw_counts(self, counts: Sequence[float], labels: Sequence[str]) -> None:
        """Draw hourly count data as bar chart."""
        if HAVE_MPL and self.fig is not None and self.ax is not None and self.canvas is not None:
            self.ax.clear()
            # Use FryNetworks theme colors
            self.ax.set_facecolor("#172135")  # bg_alt from theme
            self.fig.patch.set_facecolor("#111827")  # bg_panel from theme
            
            values = [float(c) for c in counts]
            values = (values + [0.0]*24)[:24]  # Ensure exactly 24 values
            
            bars = self.ax.bar(range(24), values, color="#ef4444", alpha=0.9)  # accent_primary from theme
            
            # Display y-axis as percentage (0..100) like the 7-day view
            self.ax.set_ylim(0, 100)
            try:
                self.ax.set_yticks([0, 25, 50, 75, 100])
            except Exception:
                pass
            
            # Style axes with theme colors
            label_size = 8 if self._small_fonts else None
            self.ax.tick_params(axis="x", colors="#94a3b8", labelsize=label_size)  # text_muted
            self.ax.tick_params(axis="y", colors="#94a3b8", labelsize=label_size)
            for spine in self.ax.spines.values():
                spine.set_color("#1f2a3d")  # border
            
            # Set x-axis labels (every 3 hours to avoid crowding)
            xticks = list(range(0, 24, 3))
            self.ax.set_xticks(xticks)
            label_list = list(labels)
            xlabels = [label_list[i] if i < len(label_list) else str(i) for i in xticks]
            self.ax.set_xticklabels(
                xlabels,
                color="#94a3b8",
                fontsize=(8 if self._small_fonts else 9),
            )
            self.ax.set_xlabel("Hour (UTC)", fontsize=(9 if not self._small_fonts else 8), color="#94a3b8", labelpad=8)

            try:
                # Increase bottom margin to ensure x-axis labels are visible
                self.fig.subplots_adjust(bottom=0.28, left=0.10, right=0.98, top=0.96)
            except Exception:
                pass
            
            self._attach_hover(bars, values, labels)
            self.canvas.draw()
        elif self._fallback_chart:
            # Fallback painter-based bars when matplotlib is missing
            self._fallback_chart.set_data(counts, labels)

    def _attach_hover(self, bars, values, labels) -> None:
        """Show percentage tooltip when hovering bars (matplotlib backend)."""
        if not hasattr(self, "canvas") or self.canvas is None or self.ax is None:
            return
        ann = getattr(self, "_hover_annotation", None)
        if ann is None:
            ann = self.ax.annotate(
                "",
                xy=(0, 0),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="#111827", ec="#1f2a3d", alpha=0.9),
                color="#e5e7eb",
                fontsize=9,
            )
            ann.set_visible(False)
            self._hover_annotation = ann

        def _on_move(event):
            try:
                if event.inaxes != self.ax:
                    if ann.get_visible():
                        ann.set_visible(False)
                        if self.canvas:
                            self.canvas.draw_idle()
                    QtWidgets.QToolTip.hideText()
                    return
                for bar, val, label in zip(bars, values, labels):
                    contains, _ = bar.contains(event)
                    if contains:
                        x = bar.get_x() + bar.get_width() / 2
                        y = bar.get_height()
                        ann.xy = (x, y)
                        text = f"{label}: {float(val):.1f}%"
                        ann.set_text(text)
                        ann.set_visible(True)
                        if self.canvas:
                            self.canvas.draw_idle()
                        try:
                            ge = event.guiEvent
                            if ge is not None:
                                QtWidgets.QToolTip.showText(ge.globalPosition().toPoint(), text, self.canvas)
                        except Exception:
                            pass
                        return
                if ann.get_visible():
                    ann.set_visible(False)
                    if self.canvas:
                        self.canvas.draw_idle()
                QtWidgets.QToolTip.hideText()
            except Exception:
                pass

        if self._hover_cid is None:
            self._hover_cid = self.canvas.mpl_connect("motion_notify_event", _on_move)
        else:
            # Reuse existing connection; handler closes over bars/values
            self.canvas.mpl_disconnect(self._hover_cid)
            self._hover_cid = self.canvas.mpl_connect("motion_notify_event", _on_move)


class Rolling7Bar(QtWidgets.QWidget):
    """7-day rolling bar chart widget showing daily percentages."""
    
    def __init__(self, parent=None, *, small_fonts: bool = False):
        # Ensure QApplication exists for testing
        ensure_qapplication()
        super().__init__(parent)
        self._small_fonts = bool(small_fonts)
        self._fallback_chart: _SimpleBarChart | None = None
        self._hover_cid = None
        self._hover_annotation = None

        if HAVE_MPL and Figure is not None and FigureCanvas is not None:
            self.fig = Figure(figsize=(4.5, 2), dpi=100, constrained_layout=False)
            self.ax = self.fig.add_subplot(111)
            self.canvas = FigureCanvas(self.fig)
            try:
                self.canvas.setMouseTracking(True)
            except Exception:
                pass

            lay = QtWidgets.QVBoxLayout(self)
            lay.addWidget(self.canvas)
        else:
            self.fig = None
            self.ax = None
            self.canvas = None
            lay = QtWidgets.QVBoxLayout(self)
            self._fallback_chart = _SimpleBarChart(self, tick_step=None, compact=bool(self._small_fonts))
            lay.addWidget(self._fallback_chart)
        
        # Initialize with empty data
        self.draw_percents([0]*7, [""]*7)

    def draw_percents(self, percents: list[float], labels: list[str]) -> None:
        """Draw daily percentage data as bar chart."""
        if HAVE_MPL and self.fig is not None and self.ax is not None and self.canvas is not None:
            self.ax.clear()
            # Use FryNetworks theme colors
            self.ax.set_facecolor("#172135")  # bg_alt from theme
            self.fig.patch.set_facecolor("#111827")  # bg_panel from theme
            
            n = max(1, len(percents))
            bars = self.ax.bar(range(n), percents, color="#ef4444", alpha=0.9)  # accent_primary from theme
            self.ax.set_ylim(0, 100)
            
            # Style axes with theme colors
            label_size = 8 if self._small_fonts else None
            self.ax.tick_params(axis="x", colors="#94a3b8", labelsize=label_size)  # text_muted
            self.ax.tick_params(axis="y", colors="#94a3b8", labelsize=label_size)
            for spine in self.ax.spines.values():
                spine.set_color("#1f2a3d")  # border
            
            try:
                self.ax.set_xticks(range(n))
                self.ax.set_xticklabels(
                    labels,
                    rotation=0,
                    color="#94a3b8",
                    fontsize=(8 if self._small_fonts else None),
                )
                self.fig.subplots_adjust(bottom=0.22, left=0.08, right=0.98, top=0.96)
            except Exception:
                pass
            
            self._attach_hover(bars, percents, labels)
            self.canvas.draw()
        elif self._fallback_chart:
            self._fallback_chart.set_data(percents, labels)

    def _attach_hover(self, bars, values, labels) -> None:
        """Show percentage tooltip when hovering bars (matplotlib backend)."""
        if not hasattr(self, "canvas") or self.canvas is None or self.ax is None:
            return
        ann = getattr(self, "_hover_annotation", None)
        if ann is None:
            ann = self.ax.annotate(
                "",
                xy=(0, 0),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                va="bottom",
                bbox=dict(boxstyle="round,pad=0.2", fc="#111827", ec="#1f2a3d", alpha=0.9),
                color="#e5e7eb",
                fontsize=9,
            )
            ann.set_visible(False)
            self._hover_annotation = ann

        def _on_move(event):
            try:
                if event.inaxes != self.ax:
                    if ann.get_visible():
                        ann.set_visible(False)
                        if self.canvas:
                            self.canvas.draw_idle()
                    QtWidgets.QToolTip.hideText()
                    return
                for bar, val, label in zip(bars, values, labels):
                    contains, _ = bar.contains(event)
                    if contains:
                        x = bar.get_x() + bar.get_width() / 2
                        y = bar.get_height()
                        ann.xy = (x, y)
                        text = f"{label}: {float(val):.1f}%"
                        ann.set_text(text)
                        ann.set_visible(True)
                        if self.canvas:
                            self.canvas.draw_idle()
                        try:
                            ge = event.guiEvent
                            if ge is not None:
                                QtWidgets.QToolTip.showText(ge.globalPosition().toPoint(), text, self.canvas)
                        except Exception:
                            pass
                        return
                if ann.get_visible():
                    ann.set_visible(False)
                    if self.canvas:
                        self.canvas.draw_idle()
                QtWidgets.QToolTip.hideText()
            except Exception:
                pass

        if self._hover_cid is None:
            self._hover_cid = self.canvas.mpl_connect("motion_notify_event", _on_move)
        else:
            self.canvas.mpl_disconnect(self._hover_cid)
            self._hover_cid = self.canvas.mpl_connect("motion_notify_event", _on_move)


class LogoLabel(QtWidgets.QLabel):
    """Scalable logo label that maintains aspect ratio."""
    
    def __init__(self, pix: QtGui.QPixmap | None = None, parent=None):
        # Ensure QApplication exists for testing
        ensure_qapplication()
        super().__init__(parent)
        self._base_pix = pix
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        
        try:
            policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, 
                                         QtWidgets.QSizePolicy.Policy.Expanding)
            self.setSizePolicy(policy)
        except Exception:
            pass
        
        # Remove fixed minimum size to allow dynamic scaling
        try:
            self.setMinimumSize(200, 200)
        except Exception:
            pass
        
        if pix is not None:
            self._apply_scaled()

    def set_base_pixmap(self, pix: QtGui.QPixmap) -> None:
        """Set the base pixmap and update display."""
        self._base_pix = pix
        self._apply_scaled()

    def resizeEvent(self, ev) -> None:  # type: ignore[override]
        """Handle resize events by rescaling the pixmap."""
        try:
            self._apply_scaled()
        except Exception:
            pass
        return super().resizeEvent(ev)

    def _apply_scaled(self) -> None:
        """Apply scaled pixmap based on current widget size."""
        if self._base_pix is None:
            return
        
        # Scale to fill the entire widget area
        try:
            # Get full widget dimensions
            w = max(50, self.width() - 2)
            h = max(50, self.height() - 2)
            # Scale to fill space while maintaining aspect ratio
            scaled = self._base_pix.scaled(w, h,
                                           QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                           QtCore.Qt.TransformationMode.SmoothTransformation)
        except Exception:
            scaled = self._base_pix.scaledToWidth(300, QtCore.Qt.TransformationMode.SmoothTransformation)
        
        self.setPixmap(scaled)
