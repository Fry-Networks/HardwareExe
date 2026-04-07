"""Configuration file writer for autonomous service integration.

Writes configuration files atomically to the shared config/ directory.
Service reads from here and applies settings.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


def _get_config_dir() -> Path:
    r"""Get the shared configuration directory.
    
    Windows: %PROGRAMDATA%\FryNetworks\miner-{MINER_CODE}\config\
    Linux: /var/lib/frynetworks/miner-{MINER_CODE}/config/
    """
    try:
        from config_profile import MINER_CODE
    except Exception:
        MINER_CODE = "BM"
    
    if sys.platform.startswith("win"):
        # Windows: PROGRAMDATA directory
        try:
            program_data = os.environ.get("PROGRAMDATA", "C:\\ProgramData")
            return Path(program_data) / "FryNetworks" / f"miner-{MINER_CODE}" / "config"
        except Exception:
            pass
    else:
        # Linux: /var/lib/frynetworks
        return Path("/var/lib/frynetworks") / f"miner-{MINER_CODE}" / "config"
    
    # Fallback
    return Path.cwd() / "config"


def write_config_json(config_name: str, data: Dict[str, Any]) -> Tuple[bool, str]:
    """Write configuration file atomically to config/ directory.
    
    Args:
        config_name: Name of config file (e.g., 'mysterium_config.json')
        data: Configuration data dictionary
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        config_dir = _get_config_dir()
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_path = config_dir / config_name
        
        # Write atomically: temp file → rename
        temp_path = config_path.with_suffix('.tmp')
        
        # Write to temp file with UTF-8 encoding
        try:
            # Try using utf8NoBOM (Python 3.7+)
            with open(temp_path, 'w', encoding='utf-8-sig') as f:
                json.dump(data, f, indent=2)
            # Remove BOM if added
            with open(temp_path, 'rb') as f:
                content = f.read()
            if content.startswith(b'\xef\xbb\xbf'):
                with open(temp_path, 'wb') as f:
                    f.write(content[3:])
        except Exception:
            # Fallback: write without BOM
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        
        # Atomic rename
        temp_path.replace(config_path)
        
        from miner_GUI.utils.data import log_step
        log_step("config_written", {
            "file": config_name,
            "path": str(config_path)
        })
        
        return True, f"Written {config_name}"
        
    except Exception as exc:
        from miner_GUI.utils.data import log_step
        log_step("config_write_failed", {
            "file": config_name,
            "error": str(exc)
        })
        return False, f"Failed to write {config_name}: {exc}"


def read_config_json(config_name: str) -> Optional[Dict[str, Any]]:
    """Read configuration file from config/ directory.
    
    Args:
        config_name: Name of config file (e.g., 'mysterium_config.json')
        
    Returns:
        dict: Configuration data, or None if read/parse fails
    """
    try:
        config_dir = _get_config_dir()
        config_path = config_dir / config_name
        
        if not config_path.exists():
            return None
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except Exception:
        return None
