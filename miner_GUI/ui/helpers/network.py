import re
from typing import Optional

from miner_GUI.utils.data import log_step

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # type: ignore


def populate_network_interfaces(self) -> None:
    """Populate network interface information on the MainWindow instance."""
    def _normalize_mac(raw: str) -> str:
        if not raw:
            return ""
        cleaned = re.sub(r"[^0-9A-Fa-f]", "", raw)
        if len(cleaned) != 12:
            return ""
        mac = ":".join(cleaned[i:i+2] for i in range(0, 12, 2)).upper()
        if mac == "00:00:00:00:00:00":
            return ""
        return mac

    try:
        chosen_mac: Optional[str] = None
        chosen_iface: Optional[str] = None

        if psutil:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            # 1) Try to identify the actual internet-facing interface via active local IP
            primary_ip = None
            try:
                import socket as _sock
                s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
                try:
                    s.connect(("8.8.8.8", 80))
                    primary_ip = s.getsockname()[0]
                finally:
                    try:
                        s.close()
                    except Exception:
                        pass
            except Exception:
                primary_ip = None

            if primary_ip:
                for name, lst in addrs.items():
                    has_primary_ip = any(getattr(a, 'family', None) == 2 and getattr(a, 'address', '') == primary_ip for a in lst)
                    if not has_primary_ip:
                        continue
                    chosen_iface = name
                    for a in lst:
                        mac_norm = _normalize_mac(getattr(a, 'address', '') or '')
                        if mac_norm:
                            chosen_mac = mac_norm
                            break
                    if chosen_mac:
                        break

        if chosen_iface:
            self.activeNetworkName = chosen_iface
        else:
            self.activeNetworkName = None
        if chosen_mac:
            self.activeMacAddress = chosen_mac
        else:
            self.activeMacAddress = None

        # Update labels: show detected values or "-" when offline
        if hasattr(self, 'networkValueLabel'):
            self.networkValueLabel.setText(self.activeNetworkName if self.activeNetworkName else "-")
        if hasattr(self, 'macValueLabel'):
            self.macValueLabel.setText(self.activeMacAddress if self.activeMacAddress else "-")

        # When no MAC is available (offline), flag as mismatch so the UI
        # clearly indicates the critical parameter is missing.
        if not self.activeMacAddress:
            if hasattr(self, '_style_mac_unknown'):
                try:
                    self._style_mac_unknown()
                except Exception:
                    pass

        log_step("mac_detection", {
            "iface": getattr(self, 'activeNetworkName', None),
            "mac": getattr(self, 'activeMacAddress', None),
            "method": "primary_ip" if chosen_mac else "none_offline"
        })
    except Exception as e:
        log_step("Error populating network interfaces", {"error": str(e)})
