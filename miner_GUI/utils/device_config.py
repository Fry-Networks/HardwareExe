"""Device configuration persistence for miner GUI.

Stores and retrieves device selections (serial ports, microphones, network interfaces)
across application restarts.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from miner_GUI.config import MINER_CODE
from .data import data_dir_gui, log_step


def get_device_config_path() -> Path:
    """Get the path to the device configuration file."""
    return data_dir_gui() / "device_config.json"


def read_device_config() -> Dict[str, Any]:
    """Read device configuration from disk.
    
    Returns:
        Dictionary with device settings, or empty dict if file doesn't exist.
        
    Structure:
        {
            "serial_port": "COM3",
            "baud_rate": 57600,
            "microphone_index": 0,
            "microphone_name": "Default Microphone",
            "last_updated": "2025-11-06T12:00:00Z"
        }
    """
    config_path = get_device_config_path()
    
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            log_step("read_device_config", {"config_keys": list(config.keys())})
            return config
    except Exception as e:
        log_step("read_device_config_error", {"error": str(e)})
    
    return {}


def write_device_config(config: Dict[str, Any]) -> bool:
    """Write device configuration to disk.
    
    Args:
        config: Dictionary with device settings
        
    Returns:
        True if successful, False otherwise
    """
    config_path = get_device_config_path()
    
    try:
        from datetime import datetime
        from miner_GUI.utils.data import data_dir_gui
        from miner_GUI.utils.ops_queue_client import enqueue_write_config
        
        # Add timestamp
        config['last_updated'] = datetime.utcnow().isoformat() + 'Z'
        content = json.dumps(config, indent=2)
        
        # If file is in ProgramData, enqueue for service to write
        try:
            base_dir = data_dir_gui()
            rel_path = str(config_path.relative_to(base_dir))
            success, msg = enqueue_write_config(rel_path, content)
            if success:
                log_step("write_device_config", {"config_keys": list(config.keys())})
            else:
                log_step("write_device_config_error", {"error": msg})
            return success
        except (ValueError, OSError):
            # If path is not in ProgramData (e.g., development), write directly
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write atomically (temp file + rename)
            temp_path = config_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            temp_path.replace(config_path)
            log_step("write_device_config", {"config_keys": list(config.keys())})
            return True
        
    except Exception as e:
        log_step("write_device_config_error", {"error": str(e)})
        return False


def get_saved_serial_port() -> Optional[str]:
    """Get saved serial port selection."""
    config = read_device_config()
    return config.get('serial_port')


def get_saved_baud_rate() -> Optional[int]:
    """Get saved baud rate selection."""
    config = read_device_config()
    return config.get('baud_rate')


def get_saved_microphone() -> Optional[int]:
    """Get saved microphone index."""
    config = read_device_config()
    return config.get('microphone_index')


def save_serial_settings(port: str, baud: int) -> bool:
    """Save serial port and baud rate selection.
    
    Args:
        port: Serial port name (e.g., "COM3", "/dev/ttyUSB0")
        baud: Baud rate (e.g., 9600, 57600)
        
    Returns:
        True if successful
    """
    config = read_device_config()
    config['serial_port'] = port
    config['baud_rate'] = baud
    return write_device_config(config)


def save_microphone_settings(index: int, name: str) -> bool:
    """Save microphone selection.
    
    Args:
        index: Microphone device index
        name: Microphone device name
        
    Returns:
        True if successful
    """
    config = read_device_config()
    config['microphone_index'] = index
    config['microphone_name'] = name
    return write_device_config(config)
