# -*- coding: utf-8 -*-
"""Kullaniciya gorunen metinlerde em/en dash olmasin.

NEDEN VAR: duz yazi kurali. Bu kural bir kez elle uygulandi (2026-09-04,
57 dizge ve iki ceviri katalogu) ama kural elle korunamaz: yeni bir mesaj
yazan kisi farkinda olmaz ve tire sessizce geri gelir.

CEVIRI KATALOGU DA DENETLENIYOR: `<source>` Python'daki dizgenin AYNISI
olmali. Ayrisirsa `lupdate` eskisini "vanished" isaretleyip yenisini
"unfinished" ekliyor; CI'daki ceviri kapisi o zaman duser ve neden
oldugunu bulmak zor olur.

TEK ISTISNA `core/bibtex.py`: oradaki tire METIN DEGIL VERI. Crossref
sayfa araligini U+2013 ile veriyor, kod onu `--` ye ceviriyor; plain.bst
araligi boyle taniyor (gercek derlemeyle olculdu). Silinirse kaynakcada
"page 770-778" tekil yaziyor.
"""

import ast
import io
import os

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EM, EN = "—", "–"

# Pakete GIREN kaynak. tests/ ve scripts/ disarida: onlar kullaniciya
# gorunmuyor.
TARANAN = [
    os.path.join(KOK, "desktop", "gui"),
    os.path.join(KOK, "desktop", "syntax"),
    os.path.join(KOK, "core"),
    os.path.join(KOK, "desktop", "main.py"),
]

ISTISNA = {os.path.join(KOK, "core", "bibtex.py")}

TS_DOSYALARI = [
    os.path.join(KOK, "desktop", "translations", "latexeditor_tr.ts"),
    os.path.join(KOK, "desktop", "translations", "latexeditor_en.ts"),
]


def _py_dosyalari():
    for hedef in TARANAN:
        if os.path.isfile(hedef):
            yield hedef
            continue
        for r, dizinler, fs in os.walk(hedef):
            dizinler[:] = [d for d in dizinler if d != "__pycache__"]
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(r, f)


def _dizgeler(dosya):
    """Dosyadaki dizge sabitleri, DOCSTRING'LER HARIC.

    Docstring'ler kullaniciya gorunmuyor; onlari da kapsamak testi
    gurultulu yapar ve asil derdi (arayuz metni) golgeler.
    """
    agac = ast.parse(io.open(dosya, encoding="utf-8").read())
    docs = set()
    for n in ast.walk(agac):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)):
            ds = ast.get_docstring(n, clean=False)
            if ds:
                docs.add(ds)
    for n in ast.walk(agac):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and n.value not in docs):
            yield n.lineno, n.value


def test_arayuz_ve_gunluk_metinlerinde_dash_YOK():
    """Dizge sabitlerinde em/en dash olmamali."""
    kotu = []
    for d in _py_dosyalari():
        if d in ISTISNA:
            continue
        for satir, metin in _dizgeler(d):
            if EM in metin or EN in metin:
                kotu.append("%s:%d  %r"
                            % (os.path.relpath(d, KOK), satir, metin[:60]))
    assert not kotu, (
        "Kullaniciya gorunen metinde em/en dash var. Duz yazi kurali: "
        "virgul, iki nokta ya da parantez kullanin.\n  " + "\n  ".join(kotu))


def test_ISTISNA_hala_gecerli():
    """`core/bibtex.py` istisnasi bos kalmamali.

    Istisna, o dosyada tirenin VERI olarak kullanildigi icin var. Kullanim
    kalkarsa istisna da kalkmali, yoksa gercek bir kusuru saklamaya baslar.

    DIZGE icinde araniyor, dosyanin herhangi bir yerinde degil: once oyle
    yaziliydi ve yorumdaki bir tire istisnayi ayakta tutuyordu. `.replace`
    cagrisi silindiginde denetim gecmeye devam etti (mutasyonla goruldu).
    """
    for yol in ISTISNA:
        dizgeler = [m for _, m in _dizgeler(yol) if EN in m or EM in m]
        assert dizgeler, (
            "%s artik DIZGE icinde tire kullanmiyor, ISTISNA listesinden "
            "cikarilmali" % os.path.relpath(yol, KOK))


@pytest.mark.parametrize("ts", TS_DOSYALARI, ids=os.path.basename)
def test_ceviri_katalogunda_dash_YOK(ts):
    if not os.path.exists(ts):
        pytest.skip("katalog yok: " + ts)
    s = io.open(ts, encoding="utf-8").read()
    assert EM not in s and EN not in s, (
        "%s icinde em/en dash var. Kaynak dizgeyi degistirdiyseniz "
        "<source> alanini da AYNI sekilde degistirin, sonra "
        "scripts/update_translations.sh calistirin." % os.path.basename(ts))
