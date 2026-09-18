# -*- coding: utf-8 -*-
"""macOS paketleme: spec, ikon ve yayin isi.

macOS spec'i Linux'unkinin KOPYASI: ayni uygulama paketleniyor, yalniz
sonuna `.app` kabugu (BUNDLE) ekleniyor. Kopya olmasi kacinilmaz ama
AYRISMASI degil; bu depoda iki spec'in ayrismasinin bedeli bir kez
odendi (`html` haric tutulunca uretilen exe hic acilmiyordu).

Buradaki kapilar o ayrismayi tutuyor ve macOS'a ozgu kismin gercekten
orada oldugunu sabitliyor.

DOGRULANDI (2026-09-18, macos-15 arm64, gercek yapi):
    .icns uretildi   236K, "Mac OS X icon"
    .app uretildi    107M, codesign --verify: valid on disk
    Info.plist       com.sballi.latexeditor, 1.0.26, tex, retina true
    .dmg uretildi    46M, hdiutil verify: checksum VALID
"""

import os
import re

import pytest

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAC = os.path.join(_KOK, "desktop", "latex-editor-macos.spec")
_LINUX = os.path.join(_KOK, "desktop", "latex-editor-linux.spec")
_IKON_BETIK = os.path.join(_KOK, "desktop", "macos_ikon_uret.sh")
_RELEASE = os.path.join(_KOK, ".github", "workflows", "release.yml")


def _oku(yol):
    with open(yol, encoding="utf-8") as f:
        return f.read()


def _govde(kaynak):
    """Spec'in PAYLASILAN kismi: BUNDLE'dan oncesi.

    Yorumlar ve bos satirlar atiliyor; iki dosyanin aciklama metinleri
    ayri yazilmis olabilir, sozlesme KODDA.
    """
    kaynak = kaynak.split("# ---- macOS'a OZGU kisim ----")[0]
    satirlar = []
    for s in kaynak.splitlines():
        kirpik = s.strip()
        if not kirpik or kirpik.startswith("#"):
            continue
        satirlar.append(kirpik)
    return satirlar


# Linux'ta acik, macOS'ta BILEREK kapali olan ayarlar. Gerekce spec'te
# yazili: arm64'te imzalanmis ikiliyi `strip` etmek imzayi gecersiz
# kilabiliyor ve imzasi bozuk ikili calistirilamiyor.
_BEKLENEN_FARKLAR = {"strip=True,", "strip_binaries=True,",
                     "strip=False,"}


def test_SPEC_GOVDESI_linux_ile_ayrismiyor():
    r"""Paylasilan kisim birebir ayni olmali.

    Ayrisirsa iki platform ayni uygulamayi paketlemiyor demektir:
    sozluk, spylls verisi, gizli importlar, Qt ceviri suzgeci hepsi
    burada yasiyor ve birinden dusen sessizce kayboluyor.
    """
    mac, linux = _govde(_oku(_MAC)), _govde(_oku(_LINUX))
    fark = set(mac) ^ set(linux)
    kalan = fark - _BEKLENEN_FARKLAR
    assert not kalan, (
        "macOS ve Linux spec govdeleri ayrismis: %s" % sorted(kalan))


def test_MACOSA_OZGU_kisim_yerinde():
    """BUNDLE olmadan `.app` degil, cikplak bir dizin uretilir."""
    kaynak = _oku(_MAC)
    assert "app = BUNDLE(" in kaynak
    assert "name='LaTeX Editor.app'" in kaynak
    assert "bundle_identifier='com.sballi.latexeditor'" in kaynak


def test_SURUM_TEK_KAYNAKTAN_okunuyor():
    """Info.plist'e surum ELLE yazilmamali.

    Yazilsaydi `core/version.py` ile ayrisirdi: "Hakkinda" penceresi
    baska, Finder'in bilgi kutusu baska surum soylerdi.
    """
    kaynak = _oku(_MAC)
    assert "from core.version import VERSION" in kaynak
    # Sabit bir surum dizesi (1.2.3 bicimi) gecmemeli.
    sabitler = re.findall(r"['\"]\d+\.\d+\.\d+['\"]", kaynak)
    assert not sabitler, "spec'te sabit surum: %s" % sabitler


@pytest.mark.parametrize("anahtar", [
    "CFBundleShortVersionString", "NSHighResolutionCapable",
    "CFBundleDocumentTypes", "LSMinimumSystemVersion",
])
def test_INFO_PLIST_anahtarlari(anahtar):
    assert anahtar in _oku(_MAC), anahtar


def test_TEX_DOSYA_ILISKILENDIRMESI_var():
    r"""Windows'ta bu is kayit defterinden yapiliyor (main.py
    `_register_file_association`), macOS'ta dogru yer Info.plist.
    Ikisinden biri dusunce `.tex` dosyalari uygulamayla acilmiyor."""
    kaynak = _oku(_MAC)
    assert "'CFBundleTypeExtensions': ['tex']" in kaynak


def test_IKON_IKILI_OLARAK_DEPODA_DURMUYOR():
    r"""`.icns` kaynak PNG'den uretiliyor, depoda ikili olarak yok.

    Ikili olsaydi `latex-editor.png` degisince onunla birlikte
    degismesi hicbir seyin guvencesinde olmazdi; bu depoda tam olarak
    o sinif (ayni bilgi iki yerde, sessizce ayrisiyor) tekrar tekrar
    cikti.
    """
    icns = [os.path.join(k, f)
            for k, _d, fs in os.walk(os.path.join(_KOK, "desktop"))
            for f in fs if f.endswith(".icns") and ".venv" not in k]
    assert not icns, "depoya .icns islenmis: %s" % icns
    assert os.path.exists(_IKON_BETIK), "ikon uretici betik yok"


def test_IKON_BETIGI_KAYNAK_PNGyi_kullaniyor():
    """Ikonun tek kaynagi uygulamanin kendi PNG'si olmali."""
    betik = _oku(_IKON_BETIK)
    assert "linux/latex-editor.png" in betik
    assert "iconutil" in betik


class TestYayinIsi:
    """release.yml'de macOS isi ve urettigi dosya."""

    def _release(self):
        return _oku(_RELEASE)

    def test_build_macos_isi_var(self):
        assert "build-macos:" in self._release()

    def test_ARM64_kosucusu(self):
        r"""macos-13 Intel'dir. Yanlis kosucu, Apple Silicon
        kullanicisina Intel yapisi gonderirdi."""
        m = re.search(r"build-macos:.*?runs-on: (\S+)", self._release(), re.S)
        assert m and m.group(1) == "macos-15", m and m.group(1)

    def test_DMG_yayina_yukleniyor(self):
        """Uretilip yuklenmezse is bosuna kosar."""
        kaynak = self._release()
        assert "_macOS_arm64.dmg" in kaynak
        m = re.search(r"build-macos:.*?fail_on_unmatched_files: true",
                      kaynak, re.S)
        assert m, "dmg yuklemesi eksik dosyada sessizce gecer"

    def test_IMZA_dogrulaniyor(self):
        r"""arm64'te imzasi gecersiz ikili CALISTIRILAMIYOR. Yapim
        sirasinda denetlenmezse kullanici paketi hic acamaz."""
        assert "codesign --verify" in self._release()

    def test_PAKET_ICERIGI_dogrulaniyor(self):
        """Windows ve Linux islerindeki ayni kapi."""
        m = re.search(r"build-macos:.*?paket_dogrula\.py", self._release(),
                      re.S)
        assert m, "build-macos paket_dogrula.py cagirmiyor"
