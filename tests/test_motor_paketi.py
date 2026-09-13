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
