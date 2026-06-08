from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class SatellitePanel(QtWidgets.QWidget):
    """GNSS panel showing selected device and sats/fix if available.
    Exposes on_tick(data) and set_device_label(text).
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        self._size_hint = width
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.deviceLbl = QtWidgets.QLabel("")
        self.deviceLbl.setAccessibleName("livedata_gps_label_device_lbl")
        self.statusLbl = QtWidgets.QLabel("waiting for data…")
        self.statusLbl.setAccessibleName("livedata_gps_label_status_lbl")
        self.detailsLbl = QtWidgets.QLabel("")
        self.detailsLbl.setAccessibleName("livedata_gps_label_details_lbl")
        try:
            self.deviceLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.statusLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.detailsLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            try:
                small = width <= 520
                dev_size = "10pt" if small else "11pt"
                stat_size = "9pt" if small else "10pt"
                det_size = "8.5pt" if small else "9pt"
                max_w = 260 if small else None
                self.deviceLbl.setStyleSheet(f"font-weight: 600; font-size: {dev_size};")
                self.statusLbl.setStyleSheet(f"font-size: {stat_size};")
                self.detailsLbl.setStyleSheet(f"font-size: {det_size}; color: #666;")
                if max_w:
                    for lbl in (self.deviceLbl, self.statusLbl, self.detailsLbl):
                        lbl.setWordWrap(True)
                        lbl.setMaximumWidth(max_w)
            except Exception:
                pass
        except Exception:
            pass

        lay.addWidget(self.deviceLbl)
        lay.addWidget(self.statusLbl)
        lay.addWidget(self.detailsLbl)
        lay.addStretch(1)

    def set_device_label(self, text: str):
        try:
            self.deviceLbl.setText(f"GNSS: {text}")
        except Exception:
            pass

    def on_tick(self, data: dict):
        try:
            # Expect data like {'sats': int, 'fix': str/int, 'lat': float, 'lon': float, 'alt': float, 'err': str}
            err = data.get('err')
            if err:
                hints = []
                err_lower = str(err).lower()
                if "baud" in err_lower:
                    hints.append("Try a different baud rate (e.g., 57600).")
                if "port open" in err_lower:
                    hints.append("Check that the device is connected.")
                if "sky view" in err_lower:
                    hints.append("Move antenna to open sky.")
                detected = data.get('detected_baud') or data.get('_detected_baud')
                if detected:
                    hints.append(f"Auto-detected baud: {detected}")
                hint_text = "  ".join(hints)
                self.statusLbl.setText(f"⚠ {err}")
                self.detailsLbl.setText(hint_text)
                return
            
            sats = data.get('sats')
            fix = data.get('fix')
            lat = data.get('lat')
            lon = data.get('lon')
            alt = data.get('alt')
            hdop = data.get('hdop')
            
            parts = []
            if sats is not None:
                parts.append(f"Satellites: {sats}")
            if fix is not None:
                fix_str = str(fix).upper() if fix else "NONE"
                parts.append(f"Fix: {fix_str}")
            
            status_text = " | ".join(parts) if parts else "waiting for data…"
            self.statusLbl.setText(status_text)
            
            # Show coordinates and accuracy
            details = []
            if lat is not None and lon is not None:
                details.append(f"Lat: {lat:.6f}°  Lon: {lon:.6f}°")
            if alt is not None:
                details.append(f"Alt: {alt:.1f}m")
            if hdop is not None:
                details.append(f"HDOP: {hdop:.1f}")
            
            self.detailsLbl.setText(" | ".join(details))
        except Exception as e:
            self.statusLbl.setText(f"⚠ Parse error: {e}")
            self.detailsLbl.setText("")
