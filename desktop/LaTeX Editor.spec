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

# Yazim denetimi sozlugu depoda SIKISTIRILMIS duruyor (sozlukler/*.xz).
# Burada aciliyor: ayrica bir CI adimi eklemek gerekmesin ve yerelde de
# yapim tek komutla issin. Sozluk yoksa yapim DURMUYOR, yalnizca ozellik
# exe'ye girmiyor (spylls yoksa menu ogesi zaten eklenmiyor).
import sys as _sys
_sys.path.insert(0, os.path.join('..', 'scripts'))
try:
    import sozluk_ac as _sozluk
    _sozluk.ac()
except Exception as _e:
    print('sozluk acilamadi, yazim denetimi sozluksuz paketlenecek: %s' % _e)

datas = []
for src, dst in [('..\\core', 'core'), ('gui', 'gui'), ('syntax', 'syntax'), ('linux', 'linux'), ('translations', 'translations')]:
    if os.path.isdir(src):
        datas.extend(_collect(src, dst))
    else:
        datas.append((src, dst))

# Ceviri KAYNAK dosyalari pakete girmesin: uygulama yalniz derlenmis `.qm`i
# okuyor, iki `.ts` ~300 KB olu agirlik. Sozluklerdeki `.xz` dersinin ayni
# sinifi. scripts/paket_dogrula.py bunu yapim adiminda denetliyor.
datas = [(s, d) for s, d in datas if not s.endswith('.ts')]

# Sozluk _collect ile TOPLANMIYOR: o dizinde `.xz` dosyalari da var ve
# `_collect` hepsini alirdi, exe'ye 1.6 MB olu agirlik girerdi. Yalniz
# spylls'in okudugu iki dosya aliniyor.
for _ad in ('tr_TR.dic', 'tr_TR.aff'):
    _yol = os.path.join('..', 'sozlukler', _ad)
    if os.path.exists(_yol):
        datas.append((_yol, 'sozlukler'))

# spylls KENDI en_US sozlugunu tasiyor ve ikinci dil ozelligi ona dayaniyor
# (`Dictionary.from_files("en_US")` paketin icindeki data/en/ dizinine
# bakiyor). PyInstaller bunu KENDILIGINDEN ALMIYOR: modul analizi yalniz
# .py dosyalarini goruyor, veri dosyalarini gormuyor. Elle eklenmezse paket
# sessizce ikinci dilsiz cikiyordu (olculdu: exe'de en_US girdisi yoktu).
#
# ru ve sv BILEREK ALINMIYOR: 4.1 MB ve hicbir yerde kullanilmiyor.
try:
    import spylls.hunspell.dictionary as _spd
    _sp_en = os.path.join(os.path.dirname(os.path.realpath(_spd.__file__)),
                          'data', 'en')
    for _f in ('en_US.dic', 'en_US.aff'):
        _p = os.path.join(_sp_en, _f)
        if os.path.exists(_p):
            datas.append((_p, os.path.join('spylls', 'hunspell', 'data', 'en')))
        else:
            print('UYARI: spylls en_US bulunamadi: %s' % _p)
except ImportError:
    print('spylls kurulu degil, yazim denetimi pakete girmeyecek')

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
    # `html` HARIC TUTULAMAZ: main_window `from html import escape`
    # kullaniyor (surum notlari diyalogu). Haric tutulunca exe HIC
    # ACILMIYOR: ModuleNotFoundError, gui/main_window.py satir 6.
    # `email` de ayni sebeple listede degil, bkz. yukaridaki not.
    # tests/test_spec_excludes.py bu sinifi topluca koruyor.
    excludes=['tkinter', 'unittest', 'test', 'xmlrpc', 'pydoc', 'curses', 'lib2to3', 'idlelib', 'pip', 'setuptools'],
    noarchive=False,
    optimize=0,
)

# Qt'nin ceviri dizininden kullanilmayan dilleri ele. Suzgec
# scripts/paket_suzgeci.py'de: iki spec ayri dosya ve biri otekinden
# sessizce ayrisabilir, o sinifin bedeli bu depoda bir kez odendi.
import paket_suzgeci as _suzgec
a.datas = _suzgec.qt_cevirilerini_ele(a.datas)

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
