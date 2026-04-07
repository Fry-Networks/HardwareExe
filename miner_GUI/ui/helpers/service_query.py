import os


def service_query_health(self) -> None:
    """Query Windows service health for the PoC and update the status strip."""
    from config_profile import MINER_CODE
    miner_code = str(MINER_CODE).upper()
    try:
        from miner_GUI.utils.system import query_best_service

        pattern = str(getattr(self, "_service_name", "") or f"FRY_PoC_{miner_code}_v*")
        svc = query_best_service(pattern)
        self._service_target_name = str(svc.get("name")) if isinstance(svc, dict) and svc.get("name") else None

        check_html = "<span style='color:#0fb94b; font-size:14pt;'>✓</span>"
        warn_html = "<span style='color:#c75c1e; font-size:14pt;'>⚠</span>"
        pend_html = "<span style='color:#6f7a88; font-size:14pt;'>⏳</span>"

        if not isinstance(svc, dict):
            # Service missing (deleted / not installed / never registered)
            try:
                exe_path = self._service_resolve_exe()
                expected = os.path.splitext(os.path.basename(exe_path))[0] if exe_path else f"FRY_PoC_{miner_code}_v?"
            except Exception:
                expected = f"FRY_PoC_{miner_code}_v?"
            self.service_status.setText(f"{warn_html} {expected} not present")
            self.service_start_btn.setEnabled(False)
            self.service_restart_btn.setEnabled(False)
            try:
                self._service_running = None
                self._refresh_footer_status()
            except Exception:
                pass
            return

        status = str(svc.get("status") or "").lower()
        name = str(svc.get("name") or f"FRY_PoC_{miner_code}_v?")

        if status == "running":
            self.service_status.setText(f"{check_html} {name} running")
            self.service_start_btn.setEnabled(False)
            self.service_restart_btn.setEnabled(True)
            self._service_running = True
        elif status == "stopped":
            self.service_status.setText(f"{warn_html} {name} stopped")
            self.service_start_btn.setEnabled(True)
            self.service_restart_btn.setEnabled(False)
            self._service_running = False
        elif status:
            self.service_status.setText(f"{pend_html} {name} {status.replace('_', ' ')}")
            self.service_start_btn.setEnabled(False)
            self.service_restart_btn.setEnabled(False)
            self._service_running = None
        else:
            self.service_status.setText(f"{pend_html} {name} unknown")
            self.service_start_btn.setEnabled(False)
            self.service_restart_btn.setEnabled(False)
            self._service_running = None

        try:
            self._refresh_footer_status()
        except Exception:
            pass
    except Exception:
        self.service_status.setText("query failed")
        try:
            self._service_running = None
            self._refresh_footer_status()
        except Exception:
            pass
