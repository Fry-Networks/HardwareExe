"""Splash screen dialog for miner GUI application startup."""

from PySide6 import QtWidgets, QtCore

# Import configuration with fallbacks
from miner_GUI.config import DISPLAY_NAME, VERSION, image_path, resource_path

from miner_GUI.tools.banner import TopBanner

from theme import Theme


class FrySplash(QtWidgets.QDialog):
    """Startup splash screen with progress bar."""
    
    def __init__(self):
        super().__init__(None, QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.Dialog)
        self.setModal(False)
        self.setObjectName("StartupScreen")
        
        # Increased width to accommodate long miner names like "Outdoor Satellite Miner - v5.5.0"
        try:
            self.setFixedSize(580, 170)
        except Exception:
            self.resize(580, 170)
        
        # Setup layout
        lay = QtWidgets.QVBoxLayout(self)
        try:
            lay.setContentsMargins(16, 16, 16, 16)
            lay.setSpacing(10)
        except Exception:
            pass
        
        # Apply dark theme styling
        try:
            self.setStyleSheet(self.styleSheet() + "\n"
                               "#StartupScreen { background-color: #000000; }\n"
                               "QLabel { color: white; }\n"
                               "QProgressBar { border: 1px solid white; background-color: black; color: white; height: 12px; }\n"
                               "QProgressBar::chunk { background-color: #E10600; }\n")
        except Exception:
            pass
        
        # Setup banner image
        banner_img = None
        try:
            bp = image_path("background.png")
            if bp and hasattr(bp, 'exists') and bp.exists():
                banner_img = str(bp)
            elif isinstance(bp, str):
                banner_img = bp
        except Exception:
            try:
                bp = resource_path("images/background.png")
                if bp and hasattr(bp, 'exists') and bp.exists():
                    banner_img = str(bp)
                elif isinstance(bp, str):
                    banner_img = bp
            except Exception:
                pass
        
        try:
            self._theme = Theme() if callable(Theme) else None
        except Exception:
            self._theme = None

        # Create banner
        if TopBanner:
            self.banner = TopBanner(f"FRY {DISPLAY_NAME} - v{VERSION}", banner_img, height=80)
            try:
                # Slightly smaller title font on splash to fit compact width
                self.banner.setStyleSheet(self.banner.styleSheet() + "#bannerTitle { font-size: 24px; }")
            except Exception:
                pass
        else:
            # Fallback if TopBanner not available
            self.banner = QtWidgets.QLabel(f"FRY {DISPLAY_NAME} - v{VERSION}")
            self.banner.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.banner.setStyleSheet("font-size: 24px; color: white; font-weight: bold;")
        
        # Create UI elements
        self.msg = QtWidgets.QLabel("Initializing...")
        try:
            self.msg.setWordWrap(True)
        except Exception:
            pass
        
        self.keyLbl = QtWidgets.QLabel("")
        
        self.bar = QtWidgets.QProgressBar()
        try:
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
        except Exception:
            pass
        
        # Add widgets to layout
        lay.addWidget(self.banner)
        lay.addWidget(self.msg)
        lay.addWidget(self.keyLbl)
        lay.addWidget(self.bar)

    def step(self, text: str, value: int) -> None:
        """Update splash screen progress."""
        try:
            self.msg.setText(text)
            self.bar.setValue(max(0, min(100, value)))
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def set_key(self, key: str | None) -> None:
        """Set the miner key display."""
        try:
            k = (key or "").strip()
            if k:
                self.keyLbl.setText(f"Key: {k}")
            else:
                self.keyLbl.clear()
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass