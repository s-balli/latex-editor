# -*- coding: utf-8 -*-
"""GERCEK sozlukle uctan uca yazim denetimi.

`tests/test_yazim.py` cekirdegi SAHTE bir sozluk nesnesiyle deniyor: orada
sorulan sey "tarayici dogru kelimeleri mi cikariyor". Burada sorulan sey
baska: PAKETE GIREN sozluk gercekten calisiyor mu.

Bu test ancak sozluk depoya girdikten sonra mumkun oldu (sozlukler/*.xz,
2026-09-03). Oncesinde sozluk yerel bir dosyaydi ve CI onu hic gormuyordu;
yani "sozluk bozuk paketlendi" hatasi hicbir kapiya takilmazdi.

spylls ya da sozluk yoksa test ATLANIYOR, dusmuyor: ikisi de artik
`desktop/requirements.txt` ve depoda, ama gelistirici ham depoyu spylls'siz
kosturabilmeli.
"""

import os
import sys

import pytest

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "scripts"))

pytest.importorskip("spylls", reason="spylls kurulu degil")

import sozluk_ac                                          # noqa: E402

from core.yazim import Denetleyici                         # noqa: E402


@pytest.fixture(scope="module")
def tr():
    """Gercek tr_TR sozlugu. `.xz`den acilmasi da bu testin kapsaminda."""
    if not sozluk_ac.ac(sessiz=True):
        pytest.skip("sozlukler/tr_TR.dic yok ve .xz'den acilamadi")
    d = Denetleyici("tr_TR", os.path.join(KOK, "sozlukler"))
    d.yukle()
    return d


def test_sikistirilmis_sozluk_ACILIYOR():
    """`.xz` depoda, ham dosya degil. Acilamazsa paket sozluksuz cikar.

    Ham `.dic` 8.6 MB; deponun butun gecmisi 3.45 MB idi, ham hali depoyu
    dorde katlardi. xz ile ikisi 1.58 MB.
    """
    assert sozluk_ac.ac(sessiz=True), (
        "sozluk acilamadi. sozlukler/tr_TR.dic.xz depoda mi?")
    for ad in ("tr_TR.dic", "tr_TR.aff"):
        yol = os.path.join(KOK, "sozlukler", ad)
        assert os.path.exists(yol)
        assert os.path.getsize(yol) > 100_000, ad


def test_ek_zincirleri_COZULUYOR(tr):
    """Turkce eklemeli bir dil; sozluk morfolojiyi yapmiyorsa ise yaramaz.

    Bu kelimelerin hicbiri sozlukte DUZ HALIYLE yok, ek kurallariyla
    turetiliyorlar. Yanlis sozluk paketlenirse (ornegin LibreOffice'in
    34 MB'lik BASKA tr_TR'si) burasi duser.
    """
    for k in ("kitaplarımızdan", "değerlendirilmesi", "üniversitesinde",
              "yapabileceklerimizden", "araştırmalarında"):
        assert tr.dogru_mu(k), k


def test_uydurma_kelime_YAKALANIYOR(tr):
    """Sozluk her seye evet demiyor: denetim tarafi."""
    for k in ("zzqqww", "asdfghjkl", "kitaplarimizdan"):
        assert not tr.dogru_mu(k), k


def test_gercek_cumlede_TEK_hatayi_buluyor(tr):
    b = tr.denetle("Bu cümlede bir yannlış var.", buyuk_atla=True)
    assert [x.kelime for x in b] == ["yannlış"]


def test_kaynakca_etiketi_gercek_sozlukle_de_geciyor(tr):
    """`doi` sozlukte YOK; gomulu etiket listesi onu kurtariyor.

    Sahte sozlukle de test var ama orada "sozlukte yok" varsayimi
    kuruluydu; burada gercekten yok oldugu dogrulaniyor.
    """
    assert not tr._sozluk.lookup("doi"), "sozlukte varsa liste gereksiz"
    assert tr.dogru_mu("doi")


def test_ikinci_dil_gercek_en_US_ile(tr):
    """spylls kendi en_US sozlugunu tasiyor, ayrica indirmek gerekmiyor.

    Ikinci dil ozelligi bunun uzerine kurulu; paket buyurken bu 4.7 MB
    zaten spylls'in icinde geliyor.
    """
    en = Denetleyici("en_US")
    en.yukle()
    assert en.dogru_mu("bandwidth")
    tr.ikincil = en
    try:
        assert tr.dogru_mu("bandwidth")      # Turkce belgede Ingilizce terim
        assert not tr.dogru_mu("zzqqww")
    finally:
        tr.ikincil = None
        tr._onbellek.clear()


# =====================================================================
# Yarim kalan acma KENDINI SURDURMEMELI
#
# `ac()` hedefe DOGRUDAN yaziyordu ve "acilmis dosya sikistirilmistan
# yeniyse atla" diyordu. Yazma yarida kesilirse (Ctrl+C, dolu disk,
# oldurulen yapim) hedef VAR ve mtime'i YENI; bir daha hic acilmiyor.
#
# OLCULDU (2026-09-05): ucte birine kirpilmis sozlukle gunluk on Turkce
# kelimenin SEKIZI yanlis sayiliyor (kitap, universite, ogrenci,
# matematik...). Yazim denetimi calisiyor gorunup neredeyse her kelimeyi
# ciziyor, ve bozukluk her yapimda hayatta kaliyor.
#
# Testler GERCEK `sozlukler/` dizinine dokunmuyor: `sozluk_ac.DIZIN` gecici
# bir kopyaya cevriliyor, yoksa yukaridaki `tr` fixture'i bozulurdu.
# =====================================================================


@pytest.fixture
def gecici_sozluk(tmp_path, monkeypatch):
    """`.xz`leri gecici bir dizine kopyala ve bir kez ac."""
    import shutil

    denek = tmp_path / "sozlukler"
    denek.mkdir()
    for ad in ("tr_TR.dic.xz", "tr_TR.aff.xz"):
        kaynak = os.path.join(KOK, "sozlukler", ad)
        if not os.path.exists(kaynak):
            pytest.skip("sozlukler/%s yok" % ad)
        shutil.copy2(kaynak, denek / ad)
    monkeypatch.setattr(sozluk_ac, "DIZIN", str(denek))
    assert sozluk_ac.ac(sessiz=True), "taze acma basarisiz"
    return denek


def _kirp(yol, bolen=3):
    """Yarim kalan yazma taklidi: kirp ve mtime'i yenile."""
    tam = os.path.getsize(yol)
    with open(yol, "r+b") as f:
        f.truncate(tam // bolen)
    os.utime(yol, None)
    return tam


class TestYarimAcmaKendiniSurdurmuyor:

    def test_kirpilmis_dosya_yeniden_aciliyor(self, gecici_sozluk):
        hedef = gecici_sozluk / "tr_TR.dic"
        tam = _kirp(str(hedef))
        # önkoşul: mtime ölçütü olsaydı bu dosya "güncel" sayılırdı
        assert (os.path.getmtime(hedef)
                >= os.path.getmtime(str(hedef) + ".xz")), \
            "vaka mtime tuzağını kurmuyor, test bir şey ölçmüyor"

        sozluk_ac.ac(sessiz=True)
        assert os.path.getsize(hedef) == tam

    def test_guncel_dosya_yeniden_yazilmiyor(self, gecici_sozluk):
        """Boyut doğruysa iş yapılmamalı; yapım her seferinde 8.6 MB yazmasın."""
        hedef = gecici_sozluk / "tr_TR.dic"
        onceki = os.path.getmtime(hedef)
        sozluk_ac.ac(sessiz=True)
        assert os.path.getmtime(hedef) == onceki

    def test_olcut_mtime_DEGIL_boyut(self, gecici_sozluk):
        """mtime çok eski olsa bile boyut doğruysa yeniden açılmamalı.

        Karşı yön: ölçüt yanlışlıkla mtime'a dönerse burası kırmızı yanar.
        """
        hedef = gecici_sozluk / "tr_TR.dic"
        os.utime(hedef, (0, 0))
        sozluk_ac.ac(sessiz=True)
        assert os.path.getmtime(hedef) == 0

    def test_yarim_yazma_hedefe_ULASMIYOR(self, gecici_sozluk, monkeypatch):
        """Atomiklik: `os.replace` patlarsa hedef oluşmamalı, `.tmp` kalmamalı."""
        hedef = gecici_sozluk / "tr_TR.dic"
        os.remove(hedef)

        def patlayan(_a, _b):
            raise OSError("yazma yarıda kesildi")

        monkeypatch.setattr(sozluk_ac.os, "replace", patlayan)
        with pytest.raises(OSError):
            sozluk_ac.ac(sessiz=True)

        assert not os.path.exists(hedef), "yarım dosya hedefe ulaştı"
        kalinti = [a for a in os.listdir(gecici_sozluk) if a.endswith(".tmp")]
        assert not kalinti, "geçici dosya temizlenmedi: %s" % kalinti
