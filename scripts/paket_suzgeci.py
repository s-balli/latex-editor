# -*- coding: utf-8 -*-
"""Pakete girmemesi gerekenleri ele. IKI SPEC DE BURAYI CAGIRIYOR.

NEDEN VAR: PyInstaller'in Qt hook'u `QtCore -> ['qt', 'qtbase']` eslemesinden
o dizindeki BUTUN dilleri topluyor, ustune `Qsci -> ['qscintilla']` ve
`QtHelp -> ['qt_help']` geliyor. Yayinlanan v1.0.21 Windows exe'sinde
olculdu (2026-09-06): 101 katalog, acilmis 6.9 MB. Uygulama bunlardan
yalnizca ikisini yukluyor, `qtbase_tr.qm` ve `qtbase_en.qm`; gerisi hem
indirilen dosyada hem de her aciliste gecici dizine cikarilan 99 dosyada
olu agirlik.

Suzgec spec'lerde DEGIL burada: depo "uc ayri paketleme tanimi" sinifindan
bir kez yandi (bkz. tests/test_paketleme.py bas yorumu) ve iki spec ayri
dosya oldugu icin biri otekinden sessizce ayrisabiliyor.
"""
from __future__ import annotations

import os

_ONEK = "latexeditor_"
_UZANTI = ".qm"


def _hedef(girdi):
    """TOC girdisinin paket ICINDEKI yolu, ayirici normal egik cizgiyle."""
    return str(girdi[0]).replace("\\", "/")


def diller(toc):
    """Pakete giren `translations/latexeditor_<dil>.qm`lerin dil kumesi.

    Dil listesi ELLE YAZILMIYOR: `core.i18n.available_languages()` de dilleri
    ayni dosyalardan okuyor, yani yeni bir dil eklemek icin burada degisiklik
    gerekmiyor ve iki liste ayrisamiyor.
    """
    out = set()
    for girdi in toc:
        ad = os.path.basename(_hedef(girdi))
        if ad.startswith(_ONEK) and ad.endswith(_UZANTI):
            out.add(ad[len(_ONEK):-len(_UZANTI)])
    return out


def qt_cevirilerini_ele(toc):
    """Qt'nin ceviri dizininden yalniz kendi dillerimizin `qtbase`ini birak.

    Kendi katalogumuz HIC bulunamazsa suzgec DEVREYE GIRMIYOR: o durumda
    tutulacak kume bos olurdu ve butun Qt kataloglarini silerdik, yani bir
    eksigi ikiye katlardik. Boyle bir paketi zaten scripts/paket_dogrula.py
    reddediyor; burada sessizce kotulestirmemek yetiyor.
    """
    bizim = diller(toc)
    if not bizim:
        print("UYARI: kendi ceviri katalogumuz pakette yok, "
              "Qt cevirileri suzulmuyor")
        return list(toc)

    tutulacak = {"qtbase_%s%s" % (d, _UZANTI) for d in bizim}
    kalan, atilan = [], 0
    for girdi in toc:
        hedef = _hedef(girdi)
        # Qt'nin kendi dizini: onefile'da `PyQt6/Qt6/translations/...`,
        # onedir'de `_internal/` onekiyle ayni. Eski yerlesim `Qt6` yerine
        # `Qt` diyor, o yuzden olcut iki parcali.
        if "PyQt6/" in hedef and "/translations/" in hedef:
            if os.path.basename(hedef) not in tutulacak:
                atilan += 1
                continue
        kalan.append(girdi)
    print("Qt cevirileri suzuldu: %d dosya atildi, tutulan diller %s"
          % (atilan, sorted(bizim)))
    return kalan
