# PyInstaller spec for counterX POS (run on Windows: pyinstaller installer/counterx.spec)
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['..\\src\\main.py'],
    pathex=['..\\src'],
    binaries=[],
    datas=[
        ('..\\assets', 'assets'),
    ],
    hiddenimports=[
        'sqlalchemy',
        'sqlalchemy.sql.default_comparator',
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtPrintSupport',
        'win32print', 'win32api', 'pywintypes',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='counterX POS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed app: no console window
    icon='..\\assets\\counterx.ico',
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='counterX POS',
)
