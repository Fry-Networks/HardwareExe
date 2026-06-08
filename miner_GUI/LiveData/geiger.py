from __future__ import annotations

from PySide6 import QtCore, QtWidgets

class GeigerPanel(QtWidgets.QWidget):
    """Geiger counter panel showing radiation dose rate.
    Exposes on_tick(data) and set_device_label(text).
    """
    def __init__(self, width: int = 800, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.deviceLbl = QtWidgets.QLabel("")
        self.deviceLbl.setAccessibleName("livedata_geiger_label_device_lbl")
        self.cpmLbl = QtWidgets.QLabel("-- CPM")
        self.cpmLbl.setAccessibleName("livedata_geiger_label_cpm_lbl")
        self.doseLbl = QtWidgets.QLabel("")
        self.doseLbl.setAccessibleName("livedata_geiger_label_dose_lbl")
        self.totalLbl = QtWidgets.QLabel("")
        self.totalLbl.setAccessibleName("livedata_geiger_label_total_lbl")
        self.statusLbl = QtWidgets.QLabel("waiting for data…")
        self.statusLbl.setAccessibleName("livedata_geiger_label_status_lbl")
        
        try:
            self.deviceLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.cpmLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.doseLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.totalLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            self.statusLbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
            
            try:
                # Large, bold CPM display
                self.cpmLbl.setStyleSheet("font-size: 28pt; font-weight: bold; color: #2E7D32;")
                # Device and dose labels
                self.deviceLbl.setStyleSheet("font-weight: 600; font-size: 11pt;")
                self.doseLbl.setStyleSheet("font-size: 10pt; color: #1565C0;")
                self.totalLbl.setStyleSheet("font-size: 9pt; color: #757575;")
                self.statusLbl.setStyleSheet("font-size: 9pt; color: #666;")
            except Exception:
                pass
        except Exception:
            pass

        lay.addWidget(self.deviceLbl)
        lay.addWidget(self.cpmLbl)
        lay.addWidget(self.doseLbl)
        lay.addWidget(self.totalLbl)
        lay.addWidget(self.statusLbl)
        lay.addStretch(1)

        # Expose a destroyed hook that external owners can connect to.
        # MainWindow already does lambda: setattr(self, 'live_panel', None) for Satellite/Geiger.
        # This comment clarifies intent and ensures future maintainers keep lifecycle clean.
        try:
            # Nothing needed here; connection done in MainWindow. We keep try for parity.
            pass
        except Exception:
            pass

    def set_device_label(self, text: str):
        try:
            self.deviceLbl.setText(f"Geiger Counter: {text}")
        except Exception:
            pass

    def on_tick(self, data: dict):
        try:
            # Expect data like {'cpm': float, 'cps': float, 'usv': float, 'usv_hour': float, 'mr': float, 'total_count': int, 'err': str}
            err = data.get('err')
            if err:
                self.cpmLbl.setText("-- CPM")
                self.doseLbl.setText(f"⚠ Error: {err}")
                self.totalLbl.setText("")
                self.statusLbl.setText("")
                return
            
            cpm = data.get('cpm')
            cps = data.get('cps')
            usv = data.get('usv')
            usv_hour = data.get('usv_hour')
            mr = data.get('mr')
            total_count = data.get('total_count')
            
            # Display CPM prominently (with CPS if available)
            if cpm is not None:
                if cps is not None:
                    self.cpmLbl.setText(f"{cpm:.1f} CPM ({cps:.0f} CPS)")
                else:
                    self.cpmLbl.setText(f"{cpm:.1f} CPM")
                    
                # Color code based on radiation level (normal background ~30-50 CPM)
                if cpm < 50:
                    self.cpmLbl.setStyleSheet("font-size: 28pt; font-weight: bold; color: #2E7D32;")  # Green - normal
                elif cpm < 150:
                    self.cpmLbl.setStyleSheet("font-size: 28pt; font-weight: bold; color: #F57F17;")  # Orange - elevated
                else:
                    self.cpmLbl.setStyleSheet("font-size: 28pt; font-weight: bold; color: #D32F2F;")  # Red - high
            else:
                self.cpmLbl.setText("-- CPM")
            
            # Show dose rate conversions
            details = []
            if usv_hour is not None:
                details.append(f"Dose rate: {usv_hour:.3f} μSv/h")
            if mr is not None:
                details.append(f"{mr:.4f} mR/h")
            if usv_hour is not None:
                details.append(f"Annual: {usv_hour*8.76:.1f} mSv")
            
            self.doseLbl.setText(" | ".join(details) if details else "")
            
            # Show total count if available (not supported on all devices)
            if total_count is not None and total_count > 0:
                self.totalLbl.setText(f"Total counts: {total_count:,}")
            else:
                self.totalLbl.setText("")
            
            self.statusLbl.setText("● Online")
        except Exception as e:
            self.statusLbl.setText(f"⚠ Parse error: {e}")
            self.doseLbl.setText("")
            self.totalLbl.setText("")
