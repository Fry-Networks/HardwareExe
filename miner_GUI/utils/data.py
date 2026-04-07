"""Data management utilities for miner GUI application.

This module handles:
- Miner key validation (encrypted miner_config.enc only)
- GUI logging and status tracking
- Data directory management
- Day-based cache file operations
- Local identity and log cleanup

Note: Legacy plaintext minerkey.txt files are NO LONGER SUPPORTED.
Use tools/create_miner_config.py to create encrypted miner_config.enc files.
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from miner_GUI.config import MINER_CODE, VERSION, app_dir

# Import encryption libraries for miner_config.enc decryption
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    if TYPE_CHECKING:
        # Type stubs for Pylance when cryptography is not available
        from cryptography.fernet import Fernet  # type: ignore
        from cryptography.hazmat.primitives import hashes  # type: ignore
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore

app_dir = lambda: Path.cwd()


def data_dir_gui() -> Path:
    """Get the GUI data directory (ProgramData on Windows, /var/lib on Linux)."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        return base / "FryNetworks" / f"miner-{MINER_CODE}"
    else:
        return Path(f"/var/lib/frynetworks/miner-{MINER_CODE}")


def make_key_pattern(prefix: str) -> re.Pattern:
    """Create regex pattern for validating miner keys with given prefix."""
    return re.compile(rf'^{re.escape(prefix)}[A-Za-z0-9_-]{{8,80}}$')


# Global key pattern for current miner code
KEY_PATTERN = make_key_pattern(MINER_CODE)

# Logging verbosity (default: minimal to keep gui_start.log lean)
VERBOSE_GUI_LOG = str(os.environ.get("FRY_GUI_VERBOSE", "0")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Noisy messages that repeat every refresh; skipped unless verbose is enabled
NOISY_MSG_PREFIXES = {
    "_load_status_data",
    "loaded_today_data",
    "hourly_data_prepared",
    "drawing_hourly_chart",
    "rolling7_data_prepared",
    "drawing_rolling7_chart",
    "Connectivity check",
    "mac_detection",
    "read_miner_key: valid key found",
    "update_rewards_hint",
    "mac_registered_from_week",
    "FryNetworks theme applied",
    "Theme module not available",
    "bm_sharing_mode",
    "prestart:",
}


def decrypt_miner_config(encrypted_data: dict) -> dict:
    """Decrypt miner configuration data from miner_config.enc file.
    
    Uses the same encryption parameters as create_miner_config.py:
    - Algorithm: Fernet (AES 128 CBC + HMAC SHA256)
    - Key Derivation: PBKDF2 with 100,000 iterations
    - Fixed salt for deployment obfuscation
    """
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("Cryptography library not available for config decryption")
    
    try:
        # Use the same parameters as encryption (from create_miner_config.py)
        salt = b'miner_config_salt_v1'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        password = "miner_config_encryption_key_v1".encode()
        key = base64.urlsafe_b64encode(kdf.derive(password))
        
        # Decrypt
        f = Fernet(key)
        decrypted_data = f.decrypt(encrypted_data['data'].encode())
        config_data = json.loads(decrypted_data)
        
        return config_data
    
    except Exception as e:
        raise RuntimeError(f"Failed to decrypt miner config: {e}")


def read_encrypted_miner_config() -> Optional[str]:
    """Read and decrypt miner key from miner_config.enc file.
    
    Returns:
        Miner key string if found and successfully decrypted, None otherwise.
    """
    # Try to find miner_config.enc in multiple locations
    config_paths = [
        data_dir_gui() / "config" / "miner_config.enc",  # ProgramData config folder
        app_dir() / "miner_config.enc",                   # App directory
        Path.cwd() / "miner_config.enc",                  # Current working directory
    ]
    
    # Try frozen bundle location if running as PyInstaller executable
    try:
        if hasattr(sys, '_MEIPASS'):
            config_paths.insert(0, Path(getattr(sys, '_MEIPASS')) / "miner_config.enc")
    except Exception:
        pass
    
    for config_path in config_paths:
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    encrypted_data = json.load(f)
                
                # Decrypt the config
                config_data = decrypt_miner_config(encrypted_data)
                miner_key = config_data.get('miner_key')
                
                if miner_key and isinstance(miner_key, str):
                    return miner_key.strip()
        
        except Exception:
            # Continue trying other locations
            continue
    
    return None


def read_mysterium_secrets() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Read Mysterium secrets from miner_config.enc.

    Returns a tuple of (payout_addr, reg_token, api_key). If the file
    is missing or a field is absent, the corresponding value will be None.
    """
    # Try to find miner_config.enc in multiple locations (same as read_encrypted_miner_config)
    config_paths = [
        data_dir_gui() / "config" / "miner_config.enc",
        app_dir() / "miner_config.enc",
        Path.cwd() / "miner_config.enc",
    ]

    try:
        if hasattr(sys, '_MEIPASS'):
            config_paths.insert(0, Path(getattr(sys, '_MEIPASS')) / "miner_config.enc")
    except Exception:
        pass

    for config_path in config_paths:
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    encrypted_data = json.load(f)
                config_data = decrypt_miner_config(encrypted_data)
                payout = config_data.get('mysterium_payout_addr') or config_data.get('MYST_PAYOUT_ADDR')
                reg_token = config_data.get('mysterium_reg_token') or config_data.get('MYST_REG_TOKEN')
                api_key = config_data.get('mysterium_api_key') or config_data.get('MYST_API_KEY')
                # Normalize to stripped strings
                payout = payout.strip() if isinstance(payout, str) else None
                reg_token = reg_token.strip() if isinstance(reg_token, str) else None
                api_key = api_key.strip() if isinstance(api_key, str) else None
                return (payout, reg_token, api_key)
        except Exception:
            continue

    return (None, None, None)


def write_miner_key(miner_key: str) -> None:
    """Deprecated: Miner keys should be stored in encrypted miner_config.enc files.
    
    This function is maintained for API compatibility but does nothing.
    Use tools/create_miner_config.py to create encrypted configuration files.
    """
    log_step("write_miner_key: deprecated function called", {"key_prefix": miner_key[:10] if miner_key else ""})
    # No-op: encrypted configs should be created by installer tools


def read_miner_key() -> str:
    """Read miner_key from encrypted miner_config.enc file only.
    
    Validates that:
    - Config file exists and can be decrypted
    - Key matches the expected format
    - Key prefix matches the expected MINER_CODE (e.g., BM key for BM GUI)
    
    Returns:
        Miner key string if found and valid, empty string otherwise.
    """
    if not CRYPTO_AVAILABLE:
        log_step("read_miner_key: cryptography library not available", {})
        return ""
    
    try:
        encrypted_key = read_encrypted_miner_config()
        
        if not encrypted_key:
            log_step("read_miner_key: no key found in encrypted config", {})
            return ""
        
        # Validate key format and prefix match
        if KEY_PATTERN.match(encrypted_key):
            # Extract the miner code from the key (e.g., "BM" from "BM-ABC123...")
            key_prefix = encrypted_key.split('-')[0] if '-' in encrypted_key else ""
            
            if key_prefix == MINER_CODE:
                log_step("read_miner_key: valid key found", {"miner_code": MINER_CODE})
                return encrypted_key
            else:
                log_step(
                    "read_miner_key: miner code mismatch", 
                    {
                        "expected": MINER_CODE, 
                        "found": key_prefix,
                        "key_prefix": encrypted_key[:15] + "..."
                    }
                )
                return ""
        else:
            log_step("read_miner_key: key format invalid", {"key_prefix": encrypted_key[:15] + "..."})
            return ""
            
    except Exception as e:
        log_step("read_miner_key: failed to read encrypted config", {"error": str(e)})
    
    return ""


def gui_log_path() -> Path:
    """Get the path for GUI startup logs."""
    try:
        base = data_dir_gui()
        p = base / 'logs'
        p.mkdir(parents=True, exist_ok=True)
        return p / 'gui_start.log'
    except Exception:
        return app_dir() / 'gui_start.log'


def log_step(msg: str, data: Optional[dict] = None) -> None:
    """Log a message with optional data to the GUI log file."""
    # Drop noisy entries unless verbose logging is explicitly enabled
    if not VERBOSE_GUI_LOG:
        for prefix in NOISY_MSG_PREFIXES:
            if msg.startswith(prefix):
                return

    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        line = f"{ts} | {msg}"
        path = gui_log_path()
        
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
            if isinstance(data, dict):
                try:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
                except Exception:
                    f.write(str(data) + "\n")
    except Exception:
        pass


def read_ui_prefs() -> dict:
    """Read optional UI preferences written by the installer (e.g., screen_size).

    Location: data_dir_gui()/config/ui_prefs.json
    Returns empty dict if not present or invalid.
    """
    try:
        cfg_path = data_dir_gui() / "config" / "ui_prefs.json"
        if not cfg_path.exists():
            return {}
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def date_to_cache_path(d) -> Path:
    """Get the cache file path for a given date."""
    return data_dir_gui() / "status" / f"status-{d.strftime('%Y%m%d')}.json"


def date_to_lock_path(d) -> Path:
    """Get the lock file path for a given date."""
    return data_dir_gui() / "status" / f"status-{d.strftime('%Y%m%d')}.lock"


class _DayReadLock:
    """Best-effort advisory read lock on a day's cache (non-blocking with short retry).
    Works with the writer's Windows msvcrt lock. Falls back to simple existence checks.
    """
    
    def __init__(self, lock_path: Path, block_ms: int = 300):
        self.lock_path = lock_path
        self.block_ms = max(0, int(block_ms))
        self._fh = None
    
    def __enter__(self):
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(self.lock_path, 'a+b')
            self._fh = fh
            
            try:
                import msvcrt  # type: ignore
                deadline = time.time() + (self.block_ms / 1000.0)
                while True:
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                        return self
                    except OSError:
                        if time.time() >= deadline:
                            break
                        time.sleep(0.01)
                # Timeout or no msvcrt - proceed anyway
                return self
            except ImportError:
                # Not Windows - proceed anyway
                return self
        except Exception:
            return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass


def cleanup_local_identity_and_logs() -> None:
    """Minimal cleanup on conflict: do NOT delete install_id; only trim error logs.

    Rationale: This device may legitimately run another miner_key of the same type.
    Keeping install_id preserves its identity for future runs. We only remove
    high-churn error logs to avoid confusing the user on subsequent attempts.
    """
    try:
        base = data_dir_gui()
        # Keep install_id.txt intact
        # Remove only transient error/output logs if present
        for rel in (('logs', 'service.err.log'), ('logs', 'service.out.log')):
            try:
                p = base
                for part in rel:
                    p = p / part
                if p.exists():
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def trim_text(s: str, max_len: int = 1200) -> str:
    """Trim text to maximum length with ellipsis if needed."""
    try:
        if not isinstance(s, str):
            return ''
        if len(s) <= max_len:
            return s
        return s[:max_len] + '...'
    except Exception:
        return ''


def collect_start_failure_details(key: str) -> str:
    """Collect diagnostic information for service start failures."""
    try:
        # Service diagnostics are intentionally handled by the external
        # installer project. The GUI does not perform NSSM/sc queries.
        return (
            "Service diagnostics are handled by the external installer project. "
            "Please run the installer or consult its logs for start/registration issues."
        )
    
    except Exception:
        return "Failed to collect diagnostic details"
