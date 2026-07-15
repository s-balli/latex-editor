# -*- mode: python ; coding: utf-8 -*-
# Linux AppImage build için PyInstaller spec

import os

def _collect(src, dst):
    result = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, src)
            dest_dir = os.path.dirname(os.path.join(dst, rel)) or dst
            result.append((fp, dest_dir))
    return result

datas = []
for src, dst in [('../core', 'core'), ('gui', 'gui'), ('syntax', 'syntax'), ('linux', 'linux'), ('translations', 'translations')]:
    if os.path.isdir(src):
        datas.extend(_collect(src, dst))

a = Analysis(
    ['main.py'],
    pathex=['..'],
    binaries=[],
    datas=datas,
    hiddenimports=['logging.handlers', 'core.i18n', 'core.version', 'core.paths'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'html', 'xmlrpc', 'pydoc', 'curses', 'lib2to3', 'idlelib', 'pip', 'setuptools'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='latex-editor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip_binaries=True,
    upx_exclude=[],
    name='latex-editor',
)
