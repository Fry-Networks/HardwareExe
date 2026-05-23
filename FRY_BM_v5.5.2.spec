# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('images', 'images'), ('qt.conf', '.'), ('C:\\Users\\saf70\\AppData\\Roaming\\Python\\Python314\\site-packages\\PySide6\\plugins\\imageformats\\qjpeg.dll', 'PySide6/plugins/imageformats'), ('C:\\Users\\saf70\\AppData\\Roaming\\Python\\Python314\\site-packages\\PySide6\\plugins\\imageformats\\qico.dll', 'PySide6/plugins/imageformats'), ('C:\\Users\\saf70\\AppData\\Roaming\\Python\\Python314\\site-packages\\PySide6\\plugins\\imageformats\\qsvg.dll', 'PySide6/plugins/imageformats')]
datas += collect_data_files('matplotlib')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PySide6.QtNetwork', 'miner_GUI.ui.widgets.charts', 'matplotlib.backends.backend_qtagg', 'matplotlib.backends.backend_qt5agg', 'miner_GUI.LiveData', 'miner_GUI.LiveData', 'miner_GUI.LiveData'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pymongo', 'sounddevice', 'serial'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FRY_BM_v5.5.2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='D:\\Fry Networks\\testing\\work\\HardwareExe-git\\_tmp_version_gui_BM.txt',
    icon=['D:\\Fry Networks\\testing\\work\\HardwareExe-git\\images\\BM.ico'],
)
