# -*- coding: utf-8 -*-
"""macOS'ta Finder'dan acilan uygulama TeX'i bulabiliyor mu.

MacTeX ikilileri `/Library/TeX/texbin`de duruyor ve o yol PATH'e
`/etc/paths.d/TeX` uzerinden giriyor. O dosyalari `path_helper` okuyor
ve path_helper YALNIZ GIRIS KABUKLARINDA kosuyor. Finder'dan ya da
Dock'tan acilan bir `.app` launchd ortamini devraliyor.

OLCULDU (2026-09-18, macos-15 + BasicTeX, uygulamanin kendi arama
mantigiyla `shutil.which`):

    giris kabugu             pdflatex -> /Library/TeX/texbin/pdflatex
    Finder'in asgari PATH'i  pdflatex, lualatex, biber, synctex
                             dordu de BULUNAMADI

Kullanici MacTeX'i kurmus oldugu halde "pdflatex kurulu degil" goruyor.
Kaynaktan calistirmada (Terminal) sorun degildi; `.dmg` yayinlanmaya
baslayinca gercek oldu.

Kapilar sahte bir `/etc/paths.d` agaciyla kosuyor, yani her platformda.
"""

import os
import shutil

import pytest

from core import paths


def _agac(tmp_path, girdiler, olusturulacak=()):
    """Sahte bir kok: /etc/paths + /etc/paths.d/* ve hedef dizinler."""
    etc = tmp_path / "etc"
    (etc / "paths.d").mkdir(parents=True)
    (etc / "paths").write_text("/usr/bin\n/bin\n", encoding="utf-8")
    for ad, satirlar in girdiler.items():
        (etc / "paths.d" / ad).write_text(satirlar, encoding="utf-8")
    for d in olusturulacak:
        (tmp_path / d.lstrip("/")).mkdir(parents=True, exist_ok=True)
    return str(tmp_path)


@pytest.fixture
def darwin(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")


class TestFinderPathTuzagi:

    def test_TEXBIN_ekleniyor(self, tmp_path, darwin):
        """Asil kusur: Finder'in asgari PATH'ine texbin girmiyordu."""
        kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"},
                    ["/Library/TeX/texbin"])
        ortam = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
        yeni = paths.macos_path_tamamla(ortam, kok=kok)
        assert "/Library/TeX/texbin" in yeni.split(os.pathsep), yeni
        assert ortam["PATH"] == yeni

    def test_MACTEXE_OZEL_ad_gomulu_degil(self, tmp_path, darwin):
        r"""`paths.d`ye kaydolan HER arac gelmeli.

        `/Library/TeX/texbin` elle yazilsaydi MacPorts ya da baska bir
        TeX dagitimi kullanan kullanici yine tikanirdi.
        """
        kok = _agac(tmp_path, {"MacPorts": "/opt/local/bin\n"},
                    ["/opt/local/bin"])
        yeni = paths.macos_path_tamamla({"PATH": "/usr/bin"}, kok=kok)
        assert "/opt/local/bin" in yeni.split(os.pathsep), yeni

    def test_HOMEBREW_de_ekleniyor(self, tmp_path, darwin):
        """pandoc ve biber oradan geliyor; Homebrew paths.d'ye yazmiyor."""
        kok = _agac(tmp_path, {}, ["/opt/homebrew/bin"])
        yeni = paths.macos_path_tamamla({"PATH": "/usr/bin"}, kok=kok)
        assert "/opt/homebrew/bin" in yeni.split(os.pathsep), yeni

    def test_OLMAYAN_dizin_eklenmiyor(self, tmp_path, darwin):
        """Var olmayan yol PATH'i sismekten baska bir sey yapmaz."""
        kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"})  # dizin YOK
        yeni = paths.macos_path_tamamla({"PATH": "/usr/bin"}, kok=kok)
        assert "/Library/TeX/texbin" not in yeni.split(os.pathsep), yeni

    def test_MEVCUT_girdi_TEKRARLANMIYOR(self, tmp_path, darwin):
        kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"},
                    ["/Library/TeX/texbin"])
        ilk = "/usr/bin:/Library/TeX/texbin"
        yeni = paths.macos_path_tamamla({"PATH": ilk}, kok=kok)
        assert yeni.split(os.pathsep).count("/Library/TeX/texbin") == 1, yeni

    def test_KULLANICININ_yolu_GOLGELENMIYOR(self, tmp_path, darwin):
        r"""Yollar SONA ekleniyor.

        Basa eklenseydi kullanicinin kendi kurdugu bir TeX'i sistemdeki
        gölgeler ve kullanici baska bir surumle derliyor olurdu.
        """
        kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"},
                    ["/Library/TeX/texbin"])
        yeni = paths.macos_path_tamamla({"PATH": "/kendi/tex/bin:/usr/bin"},
                                        kok=kok)
        parcalar = yeni.split(os.pathsep)
        assert parcalar[0] == "/kendi/tex/bin", parcalar
        assert parcalar.index("/Library/TeX/texbin") > parcalar.index("/usr/bin")


class TestOTEKI_PLATFORMLAR:
    """KARSI KOL: Windows ve Linux'a dokunulmuyor."""

    @pytest.mark.parametrize("platform", ["win32", "linux"])
    def test_PATH_degismiyor(self, tmp_path, monkeypatch, platform):
        monkeypatch.setattr("sys.platform", platform)
        kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"},
                    ["/Library/TeX/texbin"])
        ilk = "/usr/bin:/bin"
        ortam = {"PATH": ilk}
        yeni = paths.macos_path_tamamla(ortam, kok=kok)
        assert yeni == ilk, yeni
        assert ortam["PATH"] == ilk, ortam


def test_ACILISTA_CAGRILIYOR():
    """Islev var olup cagrilmazsa hicbir sey degismez.

    Cagrinin `MainWindow`dan ONCE olmasi sart: hem ortam denetimi
    (`shutil.which`) hem derleyici (QProcess cocugu ortami devraliyor)
    PATH'i sonra okuyor.
    """
    yol = os.path.join(os.path.dirname(__file__), "..", "desktop", "main.py")
    with open(yol, encoding="utf-8") as f:
        kaynak = f.read()
    assert "macos_path_tamamla()" in kaynak, "acilista cagrilmiyor"
    assert kaynak.index("macos_path_tamamla()") < kaynak.index("MainWindow("), \
        "cagri MainWindow'dan SONRA"


def test_SHUTIL_WHICH_tamamlanan_PATHi_goruyor(tmp_path, monkeypatch):
    """Uctan uca: ortam denetiminin kullandigi arama da bulmali.

    Kapi `shutil.which`i GERCEKTEN kosturuyor, cunku duzeltmenin degeri
    tam olarak o aramanin sonucunu degistirmesi.
    """
    monkeypatch.setattr("sys.platform", "darwin")
    kok = _agac(tmp_path, {"TeX": "/Library/TeX/texbin\n"},
                ["/Library/TeX/texbin"])
    sahte_bin = tmp_path / "Library/TeX/texbin"
    arac = sahte_bin / "pdflatex"
    arac.write_text("#!/bin/sh\n", encoding="utf-8")
    arac.chmod(0o755)

    # Sahte agacta gercek yol `kok` altinda; PATH'e onu koyacak sekilde
    # tamamlayip aramayi o PATH ile kosturuyoruz.
    ortam = {"PATH": str(tmp_path / "usr/bin")}
    yeni = paths.macos_path_tamamla(ortam, kok=kok)
    aranan = os.pathsep.join(
        kok + p if p.startswith("/") and not p.startswith(kok) else p
        for p in yeni.split(os.pathsep))
    assert shutil.which("pdflatex", path=aranan), aranan
