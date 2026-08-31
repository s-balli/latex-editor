# -*- mode: python ; coding: utf-8 -*-
import os

# BU DOSYA PAKETLEMENİN TEK KAYNAĞIDIR. Neyin exe'ye gireceği (datas,
# excludes, hiddenimports, ikon, ad) yalnız burada tanımlı; "Exe Olustur.bat"
# ve "Sikistirilmis Exe Olustur.bat" argümanları TEKRARLAMAZ, bu spec'i
# çağırır. Eskiden üç ayrı tanım vardı ve üçü de farklı exe üretiyordu —
# yayınlanan sürümle yerelde denenen sürüm aynı şey değildi.
#
# strip/upx: CI'da KAPALI — Windows'ta strip python312.dll'i bozuyor
# ("LoadLibrary: Bellek konumuna geçersiz erişim" hatası). Yerelde varsayılan
# AÇIK (UPX desktop/upx/ altında kurulu); LE_HIZLI=1 ile kapatılabilir —
# "Exe Olustur.bat" onu kullanır, böylece yayınlanan exe'nin birebir aynısını
# yerelde üretir.
_CI = os.environ.get("CI", "").lower() in ("true", "1")
_HIZLI = os.environ.get("LE_HIZLI", "").lower() in ("true", "1")
_sikistir = not (_CI or _HIZLI)

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
    # email HARİÇ TUTULAMAZ: urllib.request -> http.client -> email zinciriyle
    # 15 email alt modülü yükleniyor. Hariç tutulunca core.updater import
    # edilemiyor, main_window'daki try/except onu "ağ hatası" sanıp bildiriyor
    # ve kullanıcı güncellemelerden sonsuza dek habersiz kalıyordu
    # (2026-08-30, E6). Bu not eskiden .bat'ta duruyordu — listenin yanında.
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
    strip=_sikistir,
    upx=_sikistir,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
