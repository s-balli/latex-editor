# -*- mode: python ; coding: utf-8 -*-
# macOS .app build icin PyInstaller spec
#
# Govde `latex-editor-linux.spec` ile AYNI olmak zorunda: ayni uygulama
# paketleniyor. Ayrisirsa bir platformda acilan paket otekinde acilmiyor
# ve bu ancak yayindan sonra fark ediliyor; bu depoda `html` haric tutma
# hatasiyla bir kez odendi. tests/test_spec_excludes.py uc spec'in
# excludes listesini, tests/test_macos_paketleme.py da bu spec'in
# Linux'unkinden ayrismadigini sabitliyor.
#
# macOS'a OZGU olan yalnizca sondaki BUNDLE: .app kabugu, ikon ve
# Info.plist.

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

# Yazim denetimi sozlugu depoda SIKISTIRILMIS duruyor (sozlukler/*.xz).
# Burada aciliyor: ayrica bir CI adimi eklemek gerekmesin ve yerelde de
# yapim tek komutla issin. Sozluk yoksa yapim DURMUYOR, yalnizca ozellik
# pakete girmiyor (spylls yoksa menu ogesi zaten eklenmiyor).
import sys as _sys
_sys.path.insert(0, os.path.join('..', 'scripts'))
try:
    import sozluk_ac as _sozluk
    _sozluk.ac()
except Exception as _e:
    print('sozluk acilamadi, yazim denetimi sozluksuz paketlenecek: %s' % _e)

datas = []
for src, dst in [('../core', 'core'), ('gui', 'gui'), ('syntax', 'syntax'), ('linux', 'linux'), ('translations', 'translations')]:
    if os.path.isdir(src):
        datas.extend(_collect(src, dst))

# Ceviri KAYNAK dosyalari pakete girmesin: uygulama yalniz derlenmis `.qm`i
# okuyor, iki `.ts` ~300 KB olu agirlik. Sozluklerdeki `.xz` dersinin ayni
# sinifi. scripts/paket_dogrula.py bunu yapim adiminda denetliyor.
datas = [(s, d) for s, d in datas if not s.endswith('.ts')]

# Sozluk _collect ile TOPLANMIYOR: o dizinde `.xz` dosyalari da var ve
# `_collect` hepsini alirdi, pakete 1.6 MB olu agirlik girerdi. Yalniz
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
    # `html` HARIC TUTULAMAZ: main_window `from html import escape`
    # kullaniyor (surum notlari diyalogu). Haric tutulunca paket HIC
    # ACILMIYOR: ModuleNotFoundError, gui/main_window.py satir 6.
    # `email` de ayni sebeple listede degil, bkz. yukaridaki not.
    # tests/test_spec_excludes.py bu sinifi topluca koruyor.
    excludes=['tkinter', 'unittest', 'test', 'xmlrpc', 'pydoc', 'curses', 'lib2to3', 'idlelib', 'pip', 'setuptools'],
    noarchive=False,
    optimize=0,
)

# Qt'nin ceviri dizininden kullanilmayan dilleri ele. Suzgec
# scripts/paket_suzgeci.py'de: spec dosyalari ayri ve biri otekinden
# sessizce ayrisabilir, o sinifin bedeli bu depoda bir kez odendi.
import paket_suzgeci as _suzgec
a.datas = _suzgec.qt_cevirilerini_ele(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='latex-editor',
    debug=False,
    bootloader_ignore_signals=False,
    # strip=True BILEREK YOK. Gerekce ONLEM: arm64 macOS'ta her ikilinin
    # en az ad-hoc imzali olmasi sart ve imzalanmis bir ikiliyi `strip`
    # etmek imzayi gecersiz kilar. PyInstaller'in imzalama ile strip
    # sirasini OLCMEDIM; riski almak yerine strip kapali birakildi.
    # Bedeli birkac MB. Linux spec'inde strip acik kalabiliyor, orada
    # imza kavrami yok. Paketin imzasi yapim adiminda `codesign --verify`
    # ile denetleniyor.
    strip=False,
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
    strip=False,
    upx_exclude=[],
    name='latex-editor',
)

# ---- macOS'a OZGU kisim ----
#
# Surum TEK KAYNAKTAN (`core/version.py`) okunuyor; Info.plist'e elle
# yazilsa depodaki surumle ayrisirdi ve "Hakkinda" penceresi baska,
# Finder'in bilgi kutusu baska sey soylerdi.
_sys.path.insert(0, '..')
from core.version import VERSION as _SURUM

# Ikon depoda ikili olarak DURMUYOR, `macos_ikon_uret.sh` kaynak PNG'den
# uretiyor (gerekce betigin basinda). Uretilmemisse yapim durmuyor,
# paket ikonsuz cikiyor: ikon yoklugu uygulamayi calismaz kilmiyor.
_ikon = os.path.join('linux', 'latex-editor.icns')
if not os.path.exists(_ikon):
    print('UYARI: %s yok, paket ikonsuz uretiliyor '
          '(bash macos_ikon_uret.sh ile uretilir)' % _ikon)
    _ikon = None

app = BUNDLE(
    coll,
    name='LaTeX Editor.app',
    icon=_ikon,
    bundle_identifier='com.sballi.latexeditor',
    version=_SURUM,
    info_plist={
        'CFBundleName': 'LaTeX Editor',
        'CFBundleDisplayName': 'LaTeX Editor',
        'CFBundleShortVersionString': _SURUM,
        'CFBundleVersion': _SURUM,
        # Retina'da bulanik cikmasin. Varsayilan FALSE: bayraksiz paket
        # 1x olceklenip buyutuluyor ve metin bulanik goruniyor.
        'NSHighResolutionCapable': True,
        # macos-15 kosucusunda olculdu; daha eskisi denenmedi.
        'LSMinimumSystemVersion': '11.0',
        # `.tex` ile iliskilendirme. Windows'ta bu is kayit defterinden
        # yapiliyor (desktop/main.py `_register_file_association`), macOS'ta
        # dogru yer Info.plist. Rol `Editor`: uygulama dosyayi acmakla
        # kalmiyor, duzenliyor.
        'CFBundleDocumentTypes': [{
            'CFBundleTypeName': 'LaTeX Document',
            'CFBundleTypeRole': 'Editor',
            'LSHandlerRank': 'Alternate',
            'CFBundleTypeExtensions': ['tex'],
        }],
    },
)
