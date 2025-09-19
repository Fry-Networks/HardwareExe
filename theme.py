from dataclasses import dataclass

@dataclass
class Theme:
    bg_window: str = "#000000"
    text_high: str = "rgba(229,229,229,0.92)"
    text_low:  str = "#7e7e7e"
    border:    str = "#787a7e"  # light gray layer/tool borders
    primary:   str = "#7c2d12"  # red-toned button
    primary_hover: str = "#9a3412"
    accent_red: str = "#dc2626"  # bar/gauge red
    font_family: str = "Segoe UI, Arial, Helvetica, sans-serif"
    font_size_base: int = 13
    radius: int = 12
    pad: int = 12
    # Layer box (group sections) styling
    layer_border_color: str = "#9ca3af"  # light gray
    layer_border_width: int = 1          # thinner

    def qss(self) -> str:
        r = self.radius; p = self.pad; ff = self.font_family; fs = self.font_size_base
        return f"""
* {{ font-family: {ff}; font-size: {fs}px; color: {self.text_high}; }}
QWidget {{ background-color: {self.bg_window}; }}
QGroupBox {{
    background: transparent; /* keep overall background pure black */
    border: 1px solid {self.border}; /* light gray lines only */
    border-radius: {r}px;
    margin-top: 4px; padding: {p}px;
}}
/* Prominent section boxes (Settings, Online status, Live data, Self-check) */
QGroupBox#layerBox {{
    border: {self.layer_border_width}px solid {self.layer_border_color};
    border-radius: {r}px;
    margin-top: 8px; padding: {p}px;
}}
QGroupBox#layerBox::title {{
    subcontrol-origin: margin; left: 8px; padding: 0 4px;
}}
QLineEdit, QComboBox {{
    background: rgba(255,255,255,0.04);
    border: 1px solid #2a2a2a;
    border-radius: {r}px;
    padding: {int(p/1.5)}px {p}px;
    color: {self.text_high};
}}
QLineEdit::placeholder {{ color: {self.text_low}; }}
QPushButton {{
    background: {self.primary}; color: #ffffff; border: none;
    border-radius: {r}px; padding: {p}px {int(p*1.5)}px;
}}
QPushButton:hover {{ background: {self.primary_hover}; }}
QPushButton:disabled {{ background: #3a3a3a; color: {self.text_low}; }}
QLabel#hint {{ color: {self.text_low}; }}
QProgressBar {{
    background: rgba(255,255,255,0.04);
    border: 1px solid #2a2a2a;
    border-radius: {r}px; text-align: center; height: 22px;
}}
QProgressBar::chunk {{ background-color: {self.accent_red}; border-radius: {r}px; }}
QToolTip {{
    background: rgba(255,255,255,0.06);
    border: 1px solid {self.border};
    border-radius: {r}px; color: {self.text_high};
}}
"""
