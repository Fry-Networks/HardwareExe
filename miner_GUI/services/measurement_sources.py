"""Pure sensor sampling helpers for the autonomous service.

These functions have no Qt dependencies and can be used by a Windows service
or CLI loop to gather measurements before writing CSV files or posting to the
backend.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Optional dependency shims for type checkers
psutil: Any | None = None
sd: Any | None = None
serial: Any | None = None

from miner_GUI.utils.data import data_dir_gui

try:  # Optional dependencies
    import psutil  # type: ignore
    HAVE_PSUTIL = True
except Exception:
    HAVE_PSUTIL = False
    psutil = None

try:
    import sounddevice as sd  # type: ignore
    HAVE_SD = True
except Exception:
    HAVE_SD = False
    sd = None

try:
    import serial  # type: ignore
    HAVE_SERIAL = True
except Exception:
    HAVE_SERIAL = False
    serial = None


def _resolve_interface(preferred: Optional[str]) -> Optional[str]:
    if not HAVE_PSUTIL or psutil is None:
        return None
    assert psutil is not None
    try:
        pernic = psutil.net_io_counters(pernic=True)
        if preferred and preferred in pernic:
            return preferred
        for name, counters in pernic.items():
            if name.lower().startswith("lo"):
                continue
            # Pick the first non-loopback with any traffic
            if counters.bytes_recv or counters.bytes_sent:
                return name
        # Fallback to first interface
        return next(iter(pernic.keys()), None)
    except Exception:
        return None


def sample_bandwidth(preferred_iface: Optional[str]) -> Dict[str, Any]:
    """Sample network bandwidth for the given or inferred interface."""
    if not HAVE_PSUTIL or psutil is None:
        return {"err": "psutil not available"}
    assert psutil is not None

    iface = _resolve_interface(preferred_iface)
    if not iface:
        return {"err": "no interface available"}

    try:
        nic0 = psutil.net_io_counters(pernic=True).get(iface)
        if not nic0:
            return {"err": "interface not found", "iface": iface}

        r0, t0 = nic0.bytes_recv, nic0.bytes_sent
        start = time.time()
        time.sleep(1.0)

        nic1 = psutil.net_io_counters(pernic=True).get(iface)
        if not nic1:
            return {"err": "interface not found", "iface": iface}

        r1, t1 = nic1.bytes_recv, nic1.bytes_sent
        dt = max(1e-3, time.time() - start)
        dl_mbps = (max(0, r1 - r0) * 8.0 / 1e6) / dt
        ul_mbps = (max(0, t1 - t0) * 8.0 / 1e6) / dt

        return {"dl": round(dl_mbps, 2), "ul": round(ul_mbps, 2), "iface": iface}
    except Exception as exc:
        return {"err": str(exc), "iface": iface}


def sample_decibel(idx: Optional[int]) -> Dict[str, Any]:
    """Sample audio decibel level from a microphone device."""
    if not HAVE_SD or sd is None:
        return {"err": "sounddevice not available"}
    assert sd is not None

    try:
        import numpy as np

        sr = 16000
        dur = 0.25
        frames_needed = int(sr * dur)
        frames = []

        def _audio_callback(indata, _frames, _time_info, _status):
            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=sr, channels=1, dtype="float32", device=idx, callback=_audio_callback
        ):
            # Stream runs in background thread; poll until we have enough samples
            deadline = time.time() + dur + 0.1
            while sum(f.shape[0] for f in frames) < frames_needed and time.time() < deadline:
                time.sleep(0.005)

        if not frames:
            return {"err": "no audio frames captured"}

        audio = np.concatenate(frames)[:frames_needed]
        rms = float(np.sqrt(np.mean(audio**2)) + 1e-12)
        dbfs = 20 * np.log10(rms)
        dbfs = max(-90.0, min(0.0, dbfs))
        return {"dbfs": round(dbfs, 1)}
    except Exception as exc:
        return {"err": str(exc)}


def _validate_nmea_checksum(sentence: str) -> bool:
    """Validate NMEA 0183 checksum (XOR of all chars between $ and *)."""
    if not sentence.startswith("$"):
        return False
    if "*" not in sentence:
        return False
    try:
        body = sentence[1:sentence.index("*")]
        expected_hex = sentence[sentence.index("*") + 1:].strip()
        if len(expected_hex) < 2:
            return False
        computed = 0
        for ch in body:
            computed ^= ord(ch)
        return f"{computed:02X}" == expected_hex.upper()[:2]
    except Exception:
        return False


def _probe_gnss_baud(port: str, skip_baud: int = 0) -> Optional[int]:
    """Probe common GNSS baud rates and return first that yields valid NMEA."""
    if not HAVE_SERIAL or serial is None:
        return None
    candidates = [9600, 57600, 38400, 115200, 4800, 19200]
    for candidate in candidates:
        if candidate == skip_baud:
            continue
        try:
            ser = serial.Serial(port, candidate, timeout=1.0)
        except Exception:
            continue
        try:
            ser.reset_input_buffer()
            valid = 0
            for _ in range(30):
                line = ser.readline()
                if not line:
                    continue
                try:
                    text = line.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if text.startswith("$") and _validate_nmea_checksum(text):
                    valid += 1
                    if valid >= 2:
                        return candidate
        except Exception:
            pass
        finally:
            try:
                ser.close()
            except Exception:
                pass
    return None


def sample_gnss(port: str, baud: int) -> Dict[str, Any]:
    """Sample GNSS data from a serial port (NMEA GGA/RMC)."""
    if not HAVE_SERIAL:
        return {"err": "serial support not available"}
    assert serial is not None
    if not port:
        return {"err": "no port specified"}

    lines_read = 0
    valid_nmea = 0
    checksum_fail = 0
    baud_used = baud
    detected_baud: Optional[int] = None

    def _attempt_read(baud_rate: int) -> Dict[str, Any]:
        nonlocal lines_read, valid_nmea, checksum_fail
        data: Dict[str, Any] = {}
        ser = None
        try:
            ser = serial.Serial(port, baud_rate, timeout=1.0)
            for _ in range(20):
                line = ser.readline()
                if not line:
                    continue
                lines_read += 1
                try:
                    text = line.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not text or not text.startswith("$"):
                    continue
                if not _validate_nmea_checksum(text):
                    checksum_fail += 1
                    continue
                valid_nmea += 1

                if text.startswith("$GPGGA") or text.startswith("$GNGGA"):
                    parts = text.split(",")
                    if len(parts) >= 9:
                        try:
                            fix_quality = int(parts[6]) if parts[6] else 0
                            fix_map = {0: "NONE", 1: "GPS", 2: "DGPS", 3: "PPS", 4: "RTK", 5: "FLOAT RTK"}
                            data["fix"] = fix_map.get(fix_quality, f"FIX{fix_quality}")
                            if parts[7]:
                                data["sats"] = int(parts[7])
                            if len(parts) > 9 and parts[9]:
                                data["alt"] = float(parts[9])
                            if len(parts) > 2 and parts[2] and parts[3]:
                                lat_str, lat_dir = parts[2], parts[3]
                                if len(lat_str) >= 5:
                                    deg = float(lat_str[:2]); minutes = float(lat_str[2:])
                                    lat = deg + minutes / 60.0
                                    if lat_dir == "S":
                                        lat = -lat
                                    data["lat"] = lat
                            if len(parts) > 5 and parts[4] and parts[5]:
                                lon_str, lon_dir = parts[4], parts[5]
                                if len(lon_str) >= 6:
                                    deg = float(lon_str[:3]); minutes = float(lon_str[3:])
                                    lon = deg + minutes / 60.0
                                    if lon_dir == "W":
                                        lon = -lon
                                    data["lon"] = lon
                            if len(parts) > 8 and parts[8]:
                                data["hdop"] = float(parts[8])
                        except Exception:
                            pass

                elif text.startswith("$GPRMC") or text.startswith("$GNRMC"):
                    parts = text.split(",")
                    if len(parts) >= 3:
                        try:
                            status = parts[2] if len(parts) > 2 else "V"
                            if "fix" not in data:
                                data["fix"] = "GPS" if status == "A" else "NONE"
                        except Exception:
                            pass
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
        return data

    for attempt in range(2):
        try:
            result = _attempt_read(baud_used)
        except Exception as exc:
            result = {"err": f"port open failed: {str(exc)[:60]}"}
        if result.get("sats") is not None or result.get("fix") is not None:
            result["_detected_baud"] = detected_baud
            result["_diag"] = {"lines_read": lines_read, "valid_nmea": valid_nmea, "checksum_fail": checksum_fail, "baud_used": baud_used}
            return result
        if attempt == 0:
            time.sleep(0.15)

    if valid_nmea == 0:
        detected_baud = _probe_gnss_baud(port, skip_baud=baud)
        if detected_baud:
            baud_used = detected_baud
            try:
                result = _attempt_read(baud_used)
            except Exception as exc:
                result = {"err": f"port open failed: {str(exc)[:60]}"}
            if result.get("sats") is not None or result.get("fix") is not None:
                result["_detected_baud"] = detected_baud
                result["_diag"] = {"lines_read": lines_read, "valid_nmea": valid_nmea, "checksum_fail": checksum_fail, "baud_used": baud_used}
                return result
            return {"err": "NMEA received but no valid fix — GPS may need sky view", "_detected_baud": detected_baud, "_diag": {"lines_read": lines_read, "valid_nmea": valid_nmea, "checksum_fail": checksum_fail, "baud_used": baud_used}}

    if valid_nmea == 0:
        return {"err": "no NMEA data received (try changing baud rate)", "_diag": {"lines_read": lines_read, "valid_nmea": valid_nmea, "checksum_fail": checksum_fail, "baud_used": baud_used}}
    return {"err": "NMEA received but no valid fix — GPS may need sky view", "_diag": {"lines_read": lines_read, "valid_nmea": valid_nmea, "checksum_fail": checksum_fail, "baud_used": baud_used}}


def sample_geiger(port: str, baud: int) -> Dict[str, Any]:
    """Sample Geiger counter data from serial port."""
    if not HAVE_SERIAL:
        return {"err": "serial support not available"}
    assert serial is not None
    if not port:
        return {"err": "no port specified"}

    try:
        import re
        import struct

        for attempt in range(2):
            try:
                ser = serial.Serial(port, baud, timeout=1.0)
                break
            except Exception as exc:
                if attempt == 1:
                    return {"err": f"open failed: {str(exc)[:50]}"}
                time.sleep(0.15)
        else:
            return {"err": "open failed"}

        data: Dict[str, Any] = {}
        try:
            if baud == 57600:
                try:
                    ser.reset_input_buffer()
                    ser.write(b"<GETCPM>>")
                    ser.flush()
                    time.sleep(0.08)
                    waiting = getattr(ser, "in_waiting", 0)
                    if waiting >= 2:
                        response = ser.read(2)
                        if len(response) == 2:
                            cpm = struct.unpack('>H', response)[0]
                            if 0 <= cpm <= 10000:
                                usv_hour = cpm * 0.0065
                                mr_hour = usv_hour * 0.1
                                data.update({
                                    "cpm": float(cpm),
                                    "usv": round(usv_hour, 4),
                                    "usv_hour": round(usv_hour, 4),
                                    "mr": round(mr_hour, 4),
                                })
                                try:
                                    ser.reset_input_buffer()
                                    ser.write(b"<GETCPS>>")
                                    ser.flush()
                                    time.sleep(0.12)
                                    if getattr(ser, "in_waiting", 0) >= 2:
                                        cps_bytes = ser.read(2)
                                        if len(cps_bytes) == 2:
                                            cps = struct.unpack('>H', cps_bytes)[0]
                                            if 0 < cps < 200:
                                                data["cps"] = float(cps)
                                except Exception:
                                    pass
                                return data
                except Exception:
                    pass

            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            for _ in range(8):
                try:
                    line = ser.readline()
                except Exception:
                    break
                if not line:
                    continue
                try:
                    text = line.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not text:
                    continue
                cpm_match = re.search(r"(\d+\.?\d*)\s*(cpm|counts?)", text, re.IGNORECASE)
                if cpm_match:
                    try:
                        cpm_val = float(cpm_match.group(1))
                        data["cpm"] = cpm_val
                        data["usv"] = round(cpm_val / 333.0, 4)
                        data["usv_hour"] = data["usv"]
                    except Exception:
                        pass
                usv_match = re.search(r"(\d+\.?\d*)\s*[uµ]s?v(/h)?", text, re.IGNORECASE)
                if usv_match:
                    try:
                        usv_val = float(usv_match.group(1))
                        data["usv"] = usv_val
                        data["usv_hour"] = usv_val
                        if "cpm" not in data:
                            data["cpm"] = round(usv_val * 333.0, 1)
                    except Exception:
                        pass
            if data.get("cpm") is not None or data.get("usv") is not None:
                return data
            return {"err": "no Geiger data"}
        except Exception as exc:
            return {"err": f"Geiger read failed: {str(exc)[:55]}"}
        finally:
            try:
                ser.close()
            except Exception:
                pass
    except Exception as exc:
        return {"err": str(exc)}


def sample_aem(status_path: Optional[Path] = None) -> Dict[str, Any]:
    """Read PoI status from today's status JSON (service-written)."""
    try:
        path = status_path
        if path is None:
            today = datetime.now()
            path = data_dir_gui() / "status" / f"status-{today.strftime('%Y%m%d')}.json"
        if not path.exists():
            return {"poi": None}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if "PoI" in data:
                return {"poi": data.get("PoI")}
            if "poi" in data:
                return {"poi": data.get("poi")}
            if "POI" in data:
                return {"poi": data.get("POI")}
        return {"poi": None}
    except Exception:
        return {"poi": None}


def real_bandwidth_test() -> Dict[str, Any]:
    """Run real bandwidth test (download/upload)."""
    try:
        import requests
    except Exception:
        return {"err": "requests not available"}

    if not HAVE_PSUTIL:
        return {"err": "psutil not available"}

    try:
        result: Dict[str, Any] = {}
        download_urls = [
            "https://proof.ovh.net/files/10Mb.dat",
            "https://speed.hetzner.de/10MB.bin",
            "https://proof.ovh.net/files/1Mb.dat",
        ]
        for url in download_urls:
            try:
                start = time.time()
                resp = requests.get(url, stream=True, timeout=30)
                resp.raise_for_status()
                total = 0
                for chunk in resp.iter_content(chunk_size=131072):
                    if chunk:
                        total += len(chunk)
                elapsed = time.time() - start
                dl_mbps = (total * 8) / 1e6 / elapsed if elapsed > 0 else 0
                result.update({
                    "download_mbps": round(dl_mbps, 2),
                    "download_bytes": total,
                    "download_seconds": round(elapsed, 2),
                    "download_url": url,
                })
                break
            except Exception:
                continue
        if not result:
            result["download_error"] = "all download URLs failed"

        upload_urls = [
            "https://httpbin.org/post",
            "https://postman-echo.com/post",
        ]
        for url in upload_urls:
            try:
                data_size = 5 * 1024 * 1024
                payload = b"0" * data_size
                start = time.time()
                resp = requests.post(url, data=payload, timeout=30)
                resp.raise_for_status()
                elapsed = time.time() - start
                ul_mbps = (data_size * 8) / 1e6 / elapsed if elapsed > 0 else 0
                result.update({
                    "upload_mbps": round(ul_mbps, 2),
                    "upload_bytes": data_size,
                    "upload_seconds": round(elapsed, 2),
                    "upload_url": url,
                })
                break
            except Exception:
                continue
        if "upload_mbps" not in result:
            result["upload_error"] = "all upload URLs failed"

        return result if result else {"err": "bandwidth test failed"}
    except Exception as exc:
        return {"err": str(exc)}
