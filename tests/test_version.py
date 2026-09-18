"""Sürüm tutarlılığı: pyproject.toml, core/version.py ile senkron kalmalı.

Çalışma zamanı sürüm kaynağı core/version.py'dir (pyproject pip paketi değil);
bu test, release sırasında ikisinden birinin güncellenmemesini yakalar.

Sürüm DÖRT yerde yaşıyor; ikisi burada eşitleniyordu, kalan ikisi (iki
README'nin Sürüm Geçmişi bölümü) elle yazılıyor ve kapısı yoktu. Sonuç:
v1.0.27 ve v1.0.28 yayınlandı, ikisi de hiçbir README'ye girmedi ve liste
v1.0.26'da durdu (2026-09-18'de fark edildi, iki yayın sonra). Kullanıcının
"bu sürümde ne değişti" diye baktığı yer, yayınlanmış iki sürümü hiç
bilmiyordu. Aşağıdaki kapı bunu tutuyor.
"""

import os
import re

import pytest

from core.version import VERSION

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pyproject_version_matches_core():
    with open(os.path.join(_ROOT, "pyproject.toml"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml'da version alanı bulunamadı"
    assert m.group(1) == VERSION


@pytest.mark.parametrize("ad", ["README.md", "README.tr.md"])
def test_SURUM_GECMISINDE_bu_surumun_girdisi_var(ad):
    """Yayınlanan her sürümün iki README'de de bir başlığı olmalı.

    Kapının ölçütü sürümün KENDİSİ: `core/version.py` ne diyorsa o başlık
    aranıyor, yani listeye elle bir şey eklemeye gerek yok. Sürüm
    yükseltilip geçmiş yazılmazsa bu test düşer; geliştirme sırasında
    sürüm son yayınlanan değerde durduğu için yeşil kalır.
    """
    with open(os.path.join(_ROOT, ad), encoding="utf-8") as f:
        metin = f.read()
    baslik = "### v%s:" % VERSION
    assert baslik in metin, (
        "%s: sürüm geçmişinde '%s' başlığı yok. Sürüm yükseltilirken "
        "iki README'ye de girdi eklenmeli." % (ad, baslik))
