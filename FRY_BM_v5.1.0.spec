# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\miner_control.py'],
    pathex=[],
    binaries=[('C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\dist\\FRY_PoC_BM_v5.1.0.exe', 'embedded'), ('C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\nssm.exe', 'embedded')],
    datas=[('C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\images', 'images'), ('C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\qt.conf', '.'), ('C:\\Users\\jimbo\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\PySide6\\plugins\\imageformats\\\\qjpeg.dll', 'PySide6/plugins/imageformats'), ('C:\\Users\\jimbo\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\PySide6\\plugins\\imageformats\\\\qico.dll', 'PySide6/plugins/imageformats')],
    hiddenimports=['PySide6.QtNetwork', 'LiveData'],
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
    name='FRY_BM_v5.1.0',
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
    icon=['C:\\Users\\jimbo\\Documents\\GitHub\\DevTesting\\HardwareExe\\images\\BM.ico'],
)
