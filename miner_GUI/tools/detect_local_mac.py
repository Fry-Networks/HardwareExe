"""
Standalone MAC detection helper for quick local testing.
Tries psutil.net_if_addrs() if psutil is available, otherwise falls back to uuid.getnode().
Prints the first non-empty MAC found in conventional colon-separated upper-case format, or empty string.
"""
import re
import uuid

def format_mac_int(mac_int: int) -> str:
    if not isinstance(mac_int, int) or mac_int == 0:
        return ""
    try:
        mac = ":".join(f"{(mac_int >> ele) & 0xff:02X}" for ele in range(40, -1, -8))
        # validate
        if re.match(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
            return mac
    except Exception:
        pass
    return ""


def detect_local_mac() -> str:
    # Try psutil first
    try:
        import psutil
        addrs = psutil.net_if_addrs()
        for ifname, s in addrs.items():
            for addr in s:
                # AF_LINK on BSD/Mac, AF_PACKET on Linux; psutil uses family name attribute
                fam = getattr(addr, 'family', None)
                if fam is None:
                    continue
                # On Windows, addr.family == -1 for MAC addresses; rely on presence of address with typical format
                mac = getattr(addr, 'address', '') or ''
                if not mac:
                    continue
                # Normalize to hex string
                norm = re.sub(r"[^0-9A-Fa-f]", "", mac)
                if len(norm) == 12 and norm != "000000000000":
                    return ":".join(norm[i:i+2].upper() for i in range(0, 12, 2))
    except Exception:
        pass
    # Fallback to uuid.getnode()
    try:
        node = uuid.getnode()
        mac = format_mac_int(node)
        if mac and mac != "00:00:00:00:00:00":
            return mac
    except Exception:
        pass
    return ""

if __name__ == '__main__':
    print(detect_local_mac())
