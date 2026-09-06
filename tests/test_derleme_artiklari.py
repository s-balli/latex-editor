# -*- coding: utf-8 -*-
'''"Bu bir derleme artığı mı" sorusunun TEK KAYNAĞI.

Soru iki yerde soruluyor ve iki liste ayrışmıştı:

    desktop/gui/file_tree.py  ->  dosya ağacında gizlensin mi
    core/versioning.py        ->  .gitignore şablonuna girsin mi

ÖLÇÜLDÜ (2026-09-06), dört uzantı ayrı cevap alıyordu:

    .run.xml   sürümleme yoksayıyor, ağaç KAYNAK sanıp gösteriyor
    .dvi       aynı şekilde
    .xdv       aynı şekilde
    .gz        ağaç gizliyor, sürümleme geçmişe alıyor

`.run.xml` ağacın KENDİ listesinde zaten vardı ama ÖLÜ girdiydi: ağaç
`os.path.splitext` ile bakıyordu ve o iki noktalı adı göremiyor
(`ana.run.xml` -> `.xml`). Yani liste doğruyu söylüyor, eşleştirme
tutmuyordu. Biber bu dosyayı her biblatex projesinde üretiyor.
'''

import os
import re

import pytest

from core import fs_ops
from core.versioning import IGNORE_TEMPLATE

try:
    from gui.file_tree import _dosya_gizli_mi
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


_DIZIN, _KOK = os.path.join("/p", "alt"), "/p"


def _agacta_gizli(ad, dizin=_DIZIN, tex_adlari=()):
    return _dosya_gizli_mi(ad, dizin, _KOK, set(tex_adlari))


def _surumde_yoksayiliyor(ad):
    for satir in IGNORE_TEMPLATE.splitlines():
        if not satir.startswith("*."):
            continue
        if re.fullmatch(re.escape(satir).replace(r"\*", ".*"), ad):
            return True
    return False


# --- ölü girdi olmamalı ---

@pytest.mark.parametrize("sonek", fs_ops.DERLEME_ARTIKLARI)
def test_HER_SONEK_gercekten_eslesiyor(sonek):
    """Kırılırsa listede yazan ama hiç tutmayan bir girdi var demektir.

    `.run.xml` tam olarak böyleydi: listede vardı, eşleşmiyordu.
    """
    assert fs_ops.derleme_artigi_mi("ana" + sonek), sonek


@pytest.mark.parametrize("sonek", fs_ops.DERLEME_ARTIKLARI)
def test_HER_SONEK_agacta_da_gizleniyor(sonek):
    assert _agacta_gizli("ana" + sonek), sonek


@pytest.mark.parametrize("sonek", fs_ops.DERLEME_ARTIKLARI)
def test_HER_SONEK_surumlemede_de_yoksayiliyor(sonek):
    assert _surumde_yoksayiliyor("ana" + sonek), sonek


# --- iki yüzey AYNI cevabı vermeli ---

_ORNEKLER = ["ana" + s for s in fs_ops.DERLEME_ARTIKLARI] + [
    "ana.tex", "kaynaklar.bib", "sekil.png", "veri.csv.gz", "notlar.md",
    "yapilandirma.xml", "arsiv.gz",
]


@pytest.mark.parametrize("ad", _ORNEKLER)
def test_IKI_YUZEY_ayni_cevabi_veriyor(ad):
    """`.pdf` hariç: o bilerek iki anlamlı (çıktı mı, vektörel şekil mi)."""
    assert _agacta_gizli(ad) == _surumde_yoksayiliyor(ad), ad


def test_YENI_SONEK_iki_yuzeye_de_ulasiyor(monkeypatch):
    """Sonraki uzantı eklendiğinde ayrışma geri gelmesin.

    Depo bu dersi `KAYNAK_UZANTILARI`nda bir kez almıştı; artık kopyalardan
    BİRİNE ekleme yapmak mümkün değil, ikisi de aynı demetten türüyor.
    """
    import importlib
    import core.versioning as vs

    monkeypatch.setattr(fs_ops, "DERLEME_ARTIKLARI",
                        fs_ops.DERLEME_ARTIKLARI + (".deneme123",))
    importlib.reload(vs)
    try:
        assert "*.deneme123" in vs.IGNORE_TEMPLATE
        assert _agacta_gizli("ana.deneme123")
    finally:
        monkeypatch.undo()
        importlib.reload(vs)


# --- aşırı gizleme kapıları ---

@pytest.mark.parametrize("ad", ["ana.tex", "kaynaklar.bib", "stil.cls",
                                "paket.sty", "sekil.png", "sekil.jpg",
                                "notlar.md", "veri.csv"])
def test_KAYNAK_dosyalari_gizlenmiyor(ad):
    assert not _agacta_gizli(ad), ad


def test_SIKISTIRILMIS_veri_dosyasi_gizlenmiyor():
    """Bare `.gz` artık gizlenmiyor: tek gerçek örneği `.synctex.gz`.

    `veri.csv.gz` kullanıcının koyduğu bir kaynak; ağaçta görünmeliydi.
    Sürümleme onu zaten geçmişe alıyordu, iki yüzey burada ayrışıyordu.
    """
    assert not _agacta_gizli("veri.csv.gz")
    assert not _surumde_yoksayiliyor("veri.csv.gz")


def test_SYNCTEX_hala_gizli():
    """Aşırı düzeltme kapısı: `.gz`i bırakmak `.synctex.gz`i açmamalı."""
    assert _agacta_gizli("ana.synctex.gz")
    assert _surumde_yoksayiliyor("ana.synctex.gz")


def test_BUYUK_HARFLI_ad_da_taniniyor():
    """Windows'ta `ANA.LOG` aynı dosya."""
    assert _agacta_gizli("ANA.LOG")
    assert _agacta_gizli("Ana.Run.XML")


# --- `.pdf` bilerek iki anlamlı, o kural bozulmamalı ---

def test_PDF_kokte_cikti_sayiliyor():
    assert _agacta_gizli("ana.pdf", dizin=_KOK)


def test_PDF_alt_klasorde_sekil_sayiliyor():
    assert not _agacta_gizli("Sample.pdf", dizin=os.path.join(_KOK, "Figures"))


def test_PDF_ayni_adli_tex_yanindaysa_cikti():
    assert _agacta_gizli("bolum1.pdf", tex_adlari={"bolum1"})


# =====================================================================
# GERÇEK bir derlemenin ürettikleri
#
# Yukarıdaki testler listenin KENDİSİ üzerinden parametreli, yani listeden
# bir girdi SİLİNİRSE o test hiç koşmuyor ve silme görünmüyor: mutasyon
# sınamasında ".dvi ve .xdv listeden düşüyor" mutantı tam bu yüzden KAÇTI
# (2026-09-06). Buradaki liste kaynaktan türemiyor, ÖLÇÜLDÜ.
#
# WSL / TeX Live 2023, tek belgede pdflatex + biber + makeindex zinciri
# (biblatex + makeidx + tableofcontents/listoffigures/listoftables), sonra
# `xelatex -no-pdf` ve `latex`. Üretilen dosyaların tamamı:
# =====================================================================

_OLCULEN_CIKTILAR = [
    "ana.aux", "ana.bbl", "ana.bcf", "ana.blg", "ana.idx", "ana.ilg",
    "ana.ind", "ana.lof", "ana.log", "ana.lot", "ana.run.xml",
    "ana.synctex.gz", "ana.toc",
    "ana.xdv",          # xelatex -no-pdf
    "ana.dvi",          # latex
]


@pytest.mark.parametrize("ad", _OLCULEN_CIKTILAR)
def test_OLCULEN_ciktilarin_hepsi_taniniyor(ad):
    """Kırılırsa listeden gerçekten üretilen bir çıktı düşmüş demektir."""
    assert fs_ops.derleme_artigi_mi(ad), ad
    assert _agacta_gizli(ad), ad
    assert _surumde_yoksayiliyor(ad), ad


def test_OLCULEN_listede_pdf_YOK():
    """`.pdf` de üretiliyor ama iki anlamlı; bu listeye bilerek alınmadı."""
    assert not any(a.endswith(".pdf") for a in _OLCULEN_CIKTILAR)
    assert not fs_ops.derleme_artigi_mi("ana.pdf")
