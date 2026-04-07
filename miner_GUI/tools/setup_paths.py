"""
Global path setup for the modular miner GUI application.
This module ensures correct Python paths for all imports.
"""

import sys
from pathlib import Path

def setup_paths():
    """Setup Python paths for modular imports."""
    # Get the workspace directory
    if __file__:
        workspace_dir = Path(__file__).parent
    else:
        workspace_dir = Path.cwd()
    
    # Paths to add
    paths_to_add = [
        str(workspace_dir),
        str(workspace_dir / "miner_GUI"),
    ]
    
    # Add paths if not already present
    for path in paths_to_add:
        if path not in sys.path:
            sys.path.insert(0, path)

# Auto-setup when imported
setup_paths()

# For type checkers, provide module location hints
if hasattr(sys, '_getframe'):
    # This helps IDEs understand the module structure
    _current_dir = Path(__file__).parent if __file__ else Path.cwd()
    _gui_dir = _current_dir / "miner_GUI"
    
    
    # Help the type checker find modules
    if _gui_dir.exists():
        for module_dir in ['core', 'utils', 'ui', 'services']:
            module_path = _gui_dir / module_dir
            if module_path.exists():
                if str(module_path) not in sys.path:
                    sys.path.append(str(module_path))