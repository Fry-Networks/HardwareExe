"""FryNetworks desktop theme shared by miner GUI entrypoint.

The theme keeps the dark brand palette used across the installer
while providing richer styling for common widgets so the GUI
does not fall back to plain Qt defaults when bundled.
"""

from dataclasses import dataclass


@dataclass(slots=True)
class Theme:
    bg_window: str = "#0b101a"
    bg_panel: str = "#111827"
    bg_alt: str = "#172135"
    border: str = "#1f2a3d"
    border_focus: str = "#2f4aa0"
    text_primary: str = "#e5e7eb"
    text_muted: str = "#94a3b8"
    accent_primary: str = "#ef4444"
    accent_primary_hover: str = "#f97316"
    accent_success: str = "#22c55e"
    radius: int = 10
    font_family: str = "Segoe UI, 'Nunito Sans', Arial, sans-serif"
    font_size: int = 13

    def qss(self) -> str:
        r = self.radius
        ff = self.font_family
        fs = self.font_size
        return f"""
* {{
    font-family: {ff};
    font-size: {fs}px;
    color: {self.text_primary};
    background-color: transparent;
}}

QMainWindow {{
    background-color: {self.bg_window};
}}

QWidget#rootPanel, QWidget#mainPanel {{
    background-color: {self.bg_panel};
}}

QGroupBox {{
    border: 1px solid {self.border};
    border-radius: {r}px;
    margin-top: 12px;
    padding: 12px;
    background-color: {self.bg_panel};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {self.text_muted};
}}

QLabel#hint, QLabel[objectName="hint"] {{
    color: {self.text_muted};
}}

QTabWidget::pane {{
    border: 1px solid {self.border};
    border-radius: {r}px;
    padding: 4px;
    background: {self.bg_panel};
}}

QTabBar::tab {{
    background: {self.bg_alt};
    color: {self.text_muted};
    border: 1px solid {self.border};
    border-radius: {r}px {r}px 0 0;
    padding: 8px 18px;
    margin-right: 6px;
}}

QTabBar::tab:selected {{
    background: {self.accent_primary};
    color: #ffffff;
    border-color: {self.accent_primary};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {self.bg_alt};
    border: 1px solid {self.border};
    border-radius: {r}px;
    padding: 7px 12px;
    selection-background-color: {self.accent_primary};
    selection-color: #ffffff;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {self.border_focus};
}}

QLineEdit::placeholder-text, QComboBox QAbstractItemView {{
    color: {self.text_muted};
}}

QPushButton {{
    background-color: {self.accent_primary};
    color: #ffffff;
    border: none;
    border-radius: {r}px;
    padding: 8px 20px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {self.accent_primary_hover};
}}

QPushButton:disabled {{
    background-color: {self.border};
    color: {self.text_muted};
}}

QProgressBar {{
    border: 1px solid {self.border};
    border-radius: {r}px;
    background-color: {self.bg_alt};
    text-align: center;
    height: 22px;
}}

QProgressBar::chunk {{
    border-radius: {r}px;
    background-color: {self.accent_success};
}}

QScrollBar:vertical {{
    background: {self.bg_alt};
    width: 12px;
    margin: 4px;
    border-radius: {r}px;
}}

QScrollBar::handle:vertical {{
    background: {self.border_focus};
    border-radius: {r}px;
}}

QToolTip {{
    background: {self.bg_alt};
    color: {self.text_primary};
    border: 1px solid {self.border_focus};
    border-radius: {r}px;
    padding: 6px 10px;
}}
"""
