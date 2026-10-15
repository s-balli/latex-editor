# -*- coding: utf-8 -*-
"""scripts/winget_notu.py: winget manifestine giden not yalnız etiket notu.

komac notu GitHub yayın sayfasının tamamından alıyordu; 1.2.5'te nota iki
dilin kurulum bölümleriyle 86 satır girdi (microsoft/winget-pkgs#453477).
Aşağıdaki manifest o PR'daki locale dosyasının kısaltılmış biçimi.
"""
import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

import winget_notu  # noqa: E402

_MANIFEST = """\
# Created with WinGet Releaser using komac v2.17.1
# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.12.0.schema.json

PackageIdentifier: s-balli.LaTeXEditor
PackageVersion: 1.2.5
PackageLocale: en-US
Publisher: Serkan BALLI
PackageName: LaTeX Editor
Tags:
- latex
- pdf
ReleaseNotes: |-
  What's Changed
  While the Dictionary Loads

  - Closing the app while the dictionary was loading no
    longer crashes it on exit.
  Installation
  Windows
  3. Download LaTeX_Editor_v1.2.5_Windows.exe and run.
  Download LaTeX_Editor_v1.2.5_Linux_x86_64.AppImage, chmod +x and run.
ReleaseNotesUrl: https://github.com/s-balli/latex-editor/releases/tag/v1.2.5
InstallationNotes: 'The editor only. To compile you also need WSL: run `wsl --install`.'
Documentations:
- DocumentLabel: Homepage
  DocumentUrl: https://s-balli.github.io/latex-editor/
ManifestType: defaultLocale
ManifestVersion: 1.12.0
"""

_NOT = """\
While the Dictionary Loads

A small release after 1.2.4.

- Closing the app while the spell-check dictionary was still loading no
  longer crashes it on exit.

4671 tests, up from 4668.
"""


def _blok_disi(metin):
    """ReleaseNotes bloğu dışındaki satırlar (sırasıyla)."""
    disari, blokta = [], False
    for s in metin.split("\n"):
        if s.startswith("ReleaseNotes:"):
            blokta = True
            continue
        if blokta and (s.startswith(" ") or not s.strip()):
            continue
        blokta = False
        disari.append(s)
    return disari


def test_not_YALNIZ_etiket_notu_oluyor():
    yeni = winget_notu.notu_degistir(_MANIFEST, _NOT)
    # `InstallationNotes:` alanı kalıyor; giden, notun kendi kurulum satırı.
    assert "chmod +x" not in yeni and "\n  Installation\n" not in yeni, yeni
    assert "  4671 tests, up from 4668." in yeni
    # Devam satırının ek girintisi korunuyor, boş satır girintisiz kalıyor.
    assert "    longer crashes it on exit." in yeni
    assert "\n\n  A small release after 1.2.4.\n" in yeni


def test_ust_bilgi_ve_OBUR_alanlar_degismiyor():
    yeni = winget_notu.notu_degistir(_MANIFEST, _NOT)
    assert _blok_disi(yeni) == _blok_disi(_MANIFEST)
    assert yeni.count("ReleaseNotes:") == 1


def test_YAML_olarak_okununca_not_ve_alanlar_dogru():
    yaml = pytest.importorskip("yaml")
    eski = yaml.safe_load(_MANIFEST)
    yeni = yaml.safe_load(winget_notu.notu_degistir(_MANIFEST, _NOT))
    assert yeni["ReleaseNotes"] == _NOT.strip("\n")
    eski.pop("ReleaseNotes")
    yeni.pop("ReleaseNotes")
    assert yeni == eski


def test_alan_YOKSA_ReleaseNotesUrl_den_once_ekleniyor():
    """komac yayında not bulamazsa alanı hiç yazmıyor."""
    alansiz = (_MANIFEST[:_MANIFEST.index("ReleaseNotes: |-")]
               + _MANIFEST[_MANIFEST.index("ReleaseNotesUrl:"):])
    satirlar = winget_notu.notu_degistir(alansiz, _NOT).split("\n")
    i = satirlar.index("ReleaseNotes: |-")
    assert satirlar[i + 1] == "  While the Dictionary Loads"
    assert satirlar[i - 1] == "- pdf"
    assert satirlar[i + 9].startswith("ReleaseNotesUrl:"), satirlar[i:i + 10]


def test_main_klasordeki_locale_dosyasini_degistiriyor(tmp_path):
    hedef = tmp_path / "s" / "s-balli" / "LaTeXEditor" / "1.2.5"
    hedef.mkdir(parents=True)
    locale = hedef / "s-balli.LaTeXEditor.locale.en-US.yaml"
    locale.write_text(_MANIFEST, encoding="utf-8")
    kurulum = hedef / "s-balli.LaTeXEditor.installer.yaml"
    kurulum.write_text("PackageIdentifier: s-balli.LaTeXEditor\n", encoding="utf-8")
    not_dosyasi = tmp_path / "not.txt"
    not_dosyasi.write_text(_NOT, encoding="utf-8")
    assert winget_notu.main(["", str(tmp_path), str(not_dosyasi)]) == 0
    assert "chmod +x" not in locale.read_text(encoding="utf-8")
    assert kurulum.read_text(encoding="utf-8") == "PackageIdentifier: s-balli.LaTeXEditor\n"


@pytest.mark.parametrize("durum", ["locale_yok", "not_bos"])
def test_main_eksikte_DUSUYOR(tmp_path, durum):
    """Sessizce eski notla gondermesin: iş akışı bu çıkışla duruyor."""
    if durum == "not_bos":
        (tmp_path / "a.locale.en-US.yaml").write_text(_MANIFEST, encoding="utf-8")
    not_dosyasi = tmp_path / "not.txt"
    not_dosyasi.write_text("" if durum == "not_bos" else _NOT, encoding="utf-8")
    assert winget_notu.main(["", str(tmp_path), str(not_dosyasi)]) == 1
