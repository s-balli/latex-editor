# -*- mode: python ; coding: utf-8 -*-
import os

# CI'da strip kapalı — Windows'ta strip python312.dll'i bozuyor
# ("LoadLibrary: Bellek konumuna geçersiz erişim" hatası).
# Lokalde strip+upx aktif (UPX desktop/upx/ altında kurulu).
_CI = os.environ.get("CI", "").lower() in ("true", "1")

def _collect(src, dst):
    result = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, src)
            # PyInstaller datas dest bir DIRECTORY olmalı, dosya yolu değil.
            # Önceki: (file, core/derle.sh) → directory sanınıp içine konuyordu.
            dest_dir = os.path.dirname(os.path.join(dst, rel)) or dst
            result.append((fp, dest_dir))
    return result

datas = []
for src, dst in [('..\\core', 'core'), ('gui', 'gui'), ('syntax', 'syntax'), ('linux', 'linux'), ('translations', 'translations')]:
    if os.path.isdir(src):
        datas.extend(_collect(src, dst))
    else:
        datas.append((src, dst))

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
    a.binaries,
    a.datas,
    [],
    name='LaTeX Editor',
    debug=False,
    icon='linux\\latex-editor.ico',
    bootloader_ignore_signals=False,
    strip=not _CI,
    upx=not _CI,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
