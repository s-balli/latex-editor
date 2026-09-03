# -*- coding: utf-8 -*-
"""`.spec` excludes listesi uygulamanin KULLANDIGI bir modulu atmasin.

NEDEN VAR: `0c1f25a` (2026-09-02) main_window'a `from html import escape`
ekledi. `html` iki spec'in de excludes listesindeydi. Uretilen exe HIC
ACILMIYORDU: `ModuleNotFoundError: No module named 'html'`, gui/main_window.py
satir 6, gunluge tek satir bile yazmadan.

Yayinlanan v1.0.19 saglamdi (o commit tag'den SONRA geldi) ama bir sonraki
surum tamamen bozuk cikacakti. Hicbir test bunu goremezdi: testler
paketlenmemis kaynakta kosuyor, orada `html` her zaman var.

Ayni sinif ONCE DE yasandi: `email` haric tutulmustu ve core.updater
import edilemiyordu (2026-08-30, E6). Iki kez olan ucuncu kez de olur,
o yuzden kapi.
"""

import ast
import os
import re

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECLER = [
    os.path.join(KOK, "desktop", "LaTeX Editor.spec"),
    os.path.join(KOK, "desktop", "latex-editor-linux.spec"),
]

# Pakete GIREN kaynak. tests/ ve scripts/ haric: onlar exe'ye girmiyor,
# oradaki `unittest`/`pytest` importlari excludes'u ilgilendirmiyor.
TARANAN = [
    os.path.join(KOK, "desktop", "gui"),
    os.path.join(KOK, "desktop", "syntax"),
    os.path.join(KOK, "core"),
    os.path.join(KOK, "desktop", "main.py"),
]


def _excludes(spec_yolu):
    """spec'teki `excludes=[...]` listesini oku.

    spec dosyasi calistirilamaz (PyInstaller ortami gerekiyor), o yuzden
    duz metinden cikariliyor.
    """
    s = open(spec_yolu, encoding="utf-8").read()
    m = re.search(r"excludes=\[(.*?)\]", s, re.S)
    assert m, "excludes listesi bulunamadi: " + spec_yolu
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _kok_moduller(dosya):
    """Dosyadaki TEPE modul adlari: `from html import x` -> 'html'."""
    try:
        agac = ast.parse(open(dosya, encoding="utf-8").read())
    except SyntaxError:                          # pragma: no cover
        return set()
    adlar = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            for a in d.names:
                adlar.add(a.name.split(".")[0])
        elif isinstance(d, ast.ImportFrom):
            # `from . import x` (level>0) yerel, ilgilendirmiyor
            if d.level == 0 and d.module:
                adlar.add(d.module.split(".")[0])
    return adlar


def _kullanilan_moduller():
    adlar = set()
    for hedef in TARANAN:
        if os.path.isfile(hedef):
            adlar |= _kok_moduller(hedef)
            continue
        for r, dizinler, fs in os.walk(hedef):
            dizinler[:] = [d for d in dizinler if d != "__pycache__"]
            for f in fs:
                if f.endswith(".py"):
                    adlar |= _kok_moduller(os.path.join(r, f))
    return adlar


@pytest.mark.parametrize("spec", SPECLER, ids=lambda p: os.path.basename(p))
def test_haric_tutulan_modul_KULLANILMIYOR(spec):
    """Haric tutulan bir modul uygulamada import ediliyorsa exe acilmaz."""
    catisma = _excludes(spec) & _kullanilan_moduller()
    assert not catisma, (
        "%s excludes listesinde ama uygulama bu modulleri kullaniyor: %s\n"
        "Haric tutulmus modul paketten cikar ve exe ACILMAZ. Listeden "
        "cikar ya da kullanimi kaldir." % (os.path.basename(spec),
                                           sorted(catisma)))


def test_IKI_SPEC_ayni_excludes_listesine_sahip():
    """Windows ve Linux paketleri ayni sey olmali.

    Ayrisirsa bir platformda acilan exe otekinde acilmaz ve bu yalniz
    yayindan sonra fark edilir.
    """
    a, b = (_excludes(s) for s in SPECLER)
    assert a == b, "excludes listeleri ayrismis: %s" % sorted(a ^ b)


def test_tarama_GERCEKTEN_calisiyor():
    """Testin kendisi bos degil: bilinen bir import gorulebiliyor mu.

    `_kullanilan_moduller` yanlis dizine bakarsa bos kume doner ve
    yukaridaki testler her zaman gecer.
    """
    m = _kullanilan_moduller()
    assert "html" in m, "main_window'daki `from html import escape` gorulmedi"
    assert "PyQt6" in m
    assert len(m) > 20, m