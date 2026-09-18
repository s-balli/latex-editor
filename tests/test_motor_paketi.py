# -*- coding: utf-8 -*-
r"""Motor eksikken önerilen apt paketi DOĞRU mu ve İKİ YERDE aynı mı.

Motor kurulu değilken uygulama `sudo apt-get install <paket>` diyor. Aynı
eşlem İKİ yerde duruyor:

    core/derle.sh      `MOTOR_PAKET` (derleme sırasında, Öneriler sekmesi)
    core/env_check.py  `APT_HINTS`   (Ortam Denetimi penceresi)

DOĞRULANDI (2026-09-13, Ubuntu/TeX Live; kehanet sistemin kendi paket
veritabanı): ölçüt, motor KOMUTUNU hangi paketin getirdiği.

    dpkg -S /usr/bin/pdflatex  ->  texlive-latex-base
    dpkg -S /usr/bin/lualatex  ->  texlive-latex-base
    dpkg -S /usr/bin/xelatex   ->  texlive-xetex

`lualatex` için `texlive-luatex` yazılıydı ve yanlıştı: `dpkg -L
texlive-luatex` içinde `lualatex` diye bir komut yok (checkcites,
luaotfload-tool, optex, texfindpkg) ve paket `texlive-latex-base`e bağımlı
da değil. TeX'siz bir makinede önerilen komut çalıştıktan sonra motor yine
bulunamıyordu.

Bu kapı ölçümün sonucunu sabitliyor; `dpkg` çağırmıyor, o yüzden her
platformda koşuyor.
"""

import os
import re

import pytest

from core.env_check import APT_HINTS, ENGINES

_BETIK = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")

_RE_MOTOR_PAKET = re.compile(
    r'^\s*(\w+)\)\s*MOTOR_PAKET="([^"]+)"', re.M)

# `dpkg -S` ile doğrulanmış eşleşmeler.
_DOGRU = {
    "lualatex": "texlive-latex-base",
    "pdflatex": "texlive-latex-base",
    "xelatex": "texlive-xetex",
}


def _betik_eslemi():
    with open(_BETIK, encoding="utf-8") as f:
        return dict(_RE_MOTOR_PAKET.findall(f.read()))


@pytest.mark.parametrize("motor", sorted(_DOGRU))
def test_ORTAM_DENETIMI_dogru_paketi_soyluyor(motor):
    assert APT_HINTS.get(motor) == _DOGRU[motor], APT_HINTS.get(motor)


@pytest.mark.parametrize("motor", sorted(_DOGRU))
def test_DERLEME_BETIGI_dogru_paketi_soyluyor(motor):
    esleme = _betik_eslemi()
    assert esleme.get(motor) == _DOGRU[motor], esleme.get(motor)


def test_IKI_KAYNAK_ayrismiyor():
    """Asıl değişmez: aynı soruya iki yerde aynı cevap.

    Biri düzeltilip öteki unutulursa kullanıcı hangi pencereden baktığına
    göre başka paket görür.
    """
    esleme = _betik_eslemi()

    assert set(esleme) == set(ENGINES), esleme
    for motor in ENGINES:
        assert esleme[motor] == APT_HINTS[motor], (motor, esleme[motor],
                                                   APT_HINTS[motor])


# =====================================================================
# Yardımcı araçlar: betiğin aradığı her araç Ortam Denetimi'nde de olmalı
# =====================================================================

# `dpkg -S` ile doğrulanmış eşleşmeler (2026-09-15, Ubuntu/TeX Live).
# Ölçüt motorlarınkiyle AYNI: komutu hangi paket getiriyorsa o.
_YARDIMCI = {
    "biber": "biber",
    "bibtex": "texlive-binaries",
    "makeindex": "texlive-binaries",
    "makeglossaries": "texlive-latex-extra",
}

# `command -v <ad>` ile varlığı sorulan araçlar; `$MOTOR` gibi değişkenler
# elenir.
_RE_COMMAND_V = re.compile(r"command -v ([a-z][a-z0-9-]+)\b")


def _betik_araclari():
    with open(_BETIK, encoding="utf-8") as f:
        return set(_RE_COMMAND_V.findall(f.read()))


def test_BETIGIN_ARADIGI_her_arac_ORTAM_DENETIMINDE_var():
    r"""Eksikliği SESSİZ olan araç denetimde görünmeli.

    ÖLÇÜLDÜ (2026-09-15, iki liste de kodun kendisinden okunarak):
    `bibtex`, `makeindex` ve `makeglossaries` betikte aranıyor ama
    denetimde YOKTU. Üçünün de eksikliği sessiz: derleme başarıyla biter,
    başlık basılır, altı boş kalır; Ortam Denetimi "her şey tamam" der.
    """
    from core.env_check import _ALTERNATIF, TOOLS

    kapsanan = set(TOOLS) | {a for alt in _ALTERNATIF.values() for a in alt}
    eksik = sorted(_betik_araclari() - kapsanan)
    assert not eksik, "denetimde olmayan arac: %s" % eksik


@pytest.mark.parametrize("arac", sorted(_YARDIMCI))
def test_YARDIMCI_ARAC_paketi_dogru(arac):
    assert APT_HINTS.get(arac) == _YARDIMCI[arac], APT_HINTS.get(arac)


def test_BETIK_ve_DENETIM_yardimci_araclarda_da_ayrismiyor():
    r"""Betik eksik araç için `sudo apt-get install X` diyor; Ortam
    Denetimi de aynı araç için bir paket adı veriyor. İkisi aynı olmalı.

    `bibtex` için betik `texlive-bibtex-extra` diyordu, denetim
    `texlive-binaries`. İkisi de çalışıyordu (biri ötekine bağımlı) ama
    kullanıcı hangi pencereden baktığına göre başka paket görüyordu.
    """
    with open(_BETIK, encoding="utf-8") as f:
        kaynak = f.read()
    # Başlık ve komut artık AYRI AYRI yazılmıyor: ikisini de
    # `eksik_paket_bildir` basıyor, apt paketi ikinci argümanda.
    #
    #     eksik_paket_bildir "<eksik şey>" "<apt paketi>" \
    #         "<macOS adı>" "<macOS komutu>"
    #
    # Başlık ile komutun aynı paketi söylemesi böylece YAPISAL oldu
    # (apt kolunda iki satır da `$2` kullanıyor); onu aşağıdaki ayrı
    # test sabitliyor. Burada kalan iş: betiğin önerdiği apt paketleri
    # ile Ortam Denetimi'ninkiler ayrışmasın.
    onerilen = set(re.findall(
        r'eksik_paket_bildir "[^"]*" "([a-z0-9][a-z0-9.+-]*)"', kaynak))
    assert onerilen, "betikteki kurulum onerileri okunamadi"
    for arac, paket in _YARDIMCI.items():
        if paket in onerilen or arac in onerilen:
            assert paket in onerilen, (arac, paket, sorted(onerilen))
