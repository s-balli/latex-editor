# -*- coding: utf-8 -*-
"""derle.sh'nin "eksik paket" önerileri DOĞRU paketi söylüyor mu.

Derleme bir `.sty`/`.cls`/`.bst` bulamadığında ya da babel bilinmeyen bir
dil gördüğünde uygulama kullanıcıya `sudo apt-get install <paket>` diyor.
Yanlış ad, kullanıcının komutu çalıştırıp yine aynı hatayı alması demek;
apt'de HİÇ OLMAYAN bir ad ise komutun "Unable to locate package" ile
düşmesi demek.

DOĞRULANDI (2026-09-13, Ubuntu/TeX Live). Dosyalar `kpsewhich` ile bulunup
sahipleri `dpkg -S` ile soruldu, paket adlarının varlığı `apt-cache policy`
ile denetlendi:

    dosya haritası   32 denetlenebilir girdinin 5'i YANLIŞ pakete
                     gönderiyordu (5 girdi yüklü olmadığı için
                     denetlenemedi)
    babel haritası   5 girdi apt'de HİÇ OLMAYAN paket adı veriyordu

Bu kapı ölçümün sonucunu sabitliyor; `dpkg` çağırmıyor, o yüzden her
platformda koşuyor.
"""

import os
import re

import pytest

_BETIK = os.path.join(os.path.dirname(__file__), "..", "core", "derle.sh")

# Tablolar `declare -A` İDİ; macOS'un /bin/bash'i (3.2.57) birleşik dizi
# tanımadığı için `case`e çevrildi. Sözleşme değişmedi: hangi dosya hangi
# pakete gidiyor. Ayrıştırıcı da `case` kollarını okuyor; bir kol birden
# çok anahtar taşıyabiliyor (`a.sty|b.sty)`).
_RE_TABLO = re.compile(r'\n(\w+)\(\) \{\n    case "\$1" in\n(.*?)\n    esac',
                       re.S)
_RE_KOL = re.compile(r'^        (\S+)\)\n +echo "([^"]+)" ;;', re.M)

# `declare -A` adları testin sözlüğünde yaşamaya devam ediyor; işlev
# adlarıyla eşlemesi burada.
_ADLAR = {"paket_ara": "PAKET_HARITASI", "babel_ara": "BABEL_HARITASI"}


def _tablolar():
    with open(_BETIK, encoding="utf-8") as f:
        kaynak = f.read()
    tablolar = {}
    for islev, govde in _RE_TABLO.findall(kaynak):
        if islev not in _ADLAR:
            continue
        tablo = {}
        for desen, paket in _RE_KOL.findall(govde):
            for anahtar in desen.split("|"):
                tablo[anahtar] = paket
        tablolar[_ADLAR[islev]] = tablo
    return tablolar


# `dpkg -S` ile DOĞRULANMIŞ eşleşmeler. İlk beşi düzeltilenler, kalanı
# zaten doğru olanlardan örneklem (karşı kol: düzeltme fazla iş yapıp
# doğruları bozmasın).
_DOSYA = {
    "cancel.sty": "texlive-latex-extra",
    "nicefrac.sty": "texlive-latex-extra",
    "units.sty": "texlive-latex-extra",
    "emulateapj.cls": "texlive-latex-extra",
    "pifont.sty": "texlive-latex-base",
    "siunitx.sty": "texlive-science",
    "IEEEtran.cls": "texlive-publishers",
    "pstricks.sty": "texlive-pstricks",
    "plainurl.bst": "texlive-bibtex-extra",
    "phonrule.sty": "texlive-humanities",
    "fontawesome5.sty": "texlive-fonts-extra",
}

_BABEL = {
    "danish": "texlive-lang-european",
    "dutch": "texlive-lang-european",
    "finnish": "texlive-lang-european",
    "norwegian": "texlive-lang-european",
    "swedish": "texlive-lang-european",
    "greek": "texlive-lang-greek",
    "french": "texlive-lang-french",
    "russian": "texlive-lang-cyrillic",
}

# apt'de OLMAYAN adlar. Debian bu dilleri `texlive-lang-european`da
# topluyor; ayrı paketleri hiç yok.
_OLMAYAN = frozenset({
    "texlive-lang-danish", "texlive-lang-dutch", "texlive-lang-finnish",
    "texlive-lang-norwegian", "texlive-lang-swedish",
})


@pytest.mark.parametrize("dosya,paket", sorted(_DOSYA.items()))
def test_dosya_haritasi_DOGRU_paketi_soyluyor(dosya, paket):
    tablo = _tablolar()["PAKET_HARITASI"]
    assert tablo.get(dosya) == paket, (dosya, tablo.get(dosya), paket)


@pytest.mark.parametrize("dil,paket", sorted(_BABEL.items()))
def test_babel_haritasi_DOGRU_paketi_soyluyor(dil, paket):
    tablo = _tablolar()["BABEL_HARITASI"]
    assert tablo.get(dil) == paket, (dil, tablo.get(dil), paket)


def test_OLMAYAN_paket_adi_onerilmiyor():
    """Komutun "Unable to locate package" ile düşmesi en kötü hâli.

    Kullanıcı hatayı okuyup verilen komutu çalıştırıyor ve hiçbir şey
    kurulmuyor; üstelik sorunun kendisinde değil, bizim yazdığımız adda.
    """
    tablolar = _tablolar()
    onerilen = set()
    for tablo in tablolar.values():
        for deger in tablo.values():
            onerilen.update(p for p in deger.replace("+", " ").split()
                            if p.startswith("texlive"))
    kesisim = onerilen & _OLMAYAN
    assert not kesisim, kesisim
