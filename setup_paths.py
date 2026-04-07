"""
Compatibility shim for setup_paths. The canonical implementation lives at
`miner_GUI/tools/setup_paths.py`. Historically some build scripts and imports
expect `setup_paths` to be a top-level module. Providing this shim keeps both
source and PyInstaller builds working.
"""

try:
    # Prefer the packaged location
    from miner_GUI.tools import setup_paths  # type: ignore
except Exception:
    # Last-resort: attempt to load the file by path relative to repo root
    import importlib.util
    import sys
    from pathlib import Path

    cand = Path(__file__).parent / 'miner_GUI' / 'tools' / 'setup_paths.py'
    if cand.exists():
        spec = importlib.util.spec_from_file_location('setup_paths', str(cand))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
            sys.modules['setup_paths'] = module
    # If even that fails, let normal import errors surface when the caller imports
    # setup_paths; don't raise here to keep import-time behavior consistent.
