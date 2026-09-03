# -*- coding: utf-8 -*-
"""Yazim denetimi sozlugunu sikistirilmis halden ac.

NEDEN SIKISTIRILMIS DURUYOR: `tr_TR.dic` 8.6 MB, `.aff` 0.2 MB. Deponun
BUTUN gecmisi 3.45 MB; ham hali depoyu dorde katlar ve git gecmisinden bir
daha cikmaz. xz ile ikisi birden 1.58 MB, depo ~5 MB'a cikiyor.

NEDEN INDIRILMIYOR: Ubuntu paketi (`hunspell-tr` 1:24.2.1-1) `.deb` icinde
`data.tar.zst` tasiyor; Python'un `tarfile`'i zstd'yi 3.14'ten once
okuyamiyor, biz 3.10 ve 3.12 hedefliyoruz. Cozmek icin `zstandard` diye
fazladan bir yapim bagimliligi gerekirdi. Ayrica yapim aga bagimli olurdu:
arsiv adresi surumle degisiyor, paket guncellenince yapim ya kirilir ya da
SESSIZCE BASKA bir sozlukle cikar.

NEDEN LibreOffice DEPOSUNDAN DEGIL: oradaki `tr_TR.dic` 34.5 MB, tamamen
baska bir sozluk. Yanlis pozitif olcumlerimiz (%2-5) Ubuntu'nun 371.169
kayitli surumuyle yapildi; kaynak degisirse hepsi bastan olculmeli.

Bu betik ILK yazarken (--paketle) sikistirmayi, sonra her yapimda acmayi
yapiyor. `.spec` dosyalari yapim basinda bunu cagiriyor, yani ayrica bir
adim eklemek gerekmiyor.

Kullanim:
    python scripts/sozluk_ac.py              # ac (yapimda otomatik)
    python scripts/sozluk_ac.py --paketle    # ham dosyalardan .xz uret
"""
from __future__ import annotations

import lzma
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIZIN = os.path.join(KOK, "sozlukler")
DOSYALAR = ("tr_TR.dic", "tr_TR.aff")


def ac(sessiz: bool = False) -> bool:
    """`.xz` dosyalarini ac. Guncel olanlari atla.

    True doner: sozluk kullanilabilir durumda.
    """
    if not os.path.isdir(DIZIN):
        if not sessiz:
            print("sozlukler/ yok, yazim denetimi sozluksuz paketlenecek")
        return False

    tamam = True
    for ad in DOSYALAR:
        hedef = os.path.join(DIZIN, ad)
        kaynak = hedef + ".xz"
        if not os.path.exists(kaynak):
            if os.path.exists(hedef):
                continue                     # ham dosya elde, sikistirilmisi yok
            tamam = False
            continue
        # Acilmis dosya sikistirilmistan yeniyse tekrar acma
        if (os.path.exists(hedef)
                and os.path.getmtime(hedef) >= os.path.getmtime(kaynak)):
            continue
        with lzma.open(kaynak, "rb") as f:
            veri = f.read()
        with open(hedef, "wb") as f:
            f.write(veri)
        if not sessiz:
            print("  acildi: sozlukler/%s (%.1f MB)" % (ad, len(veri) / 1048576))

    for ad in DOSYALAR:
        if not os.path.exists(os.path.join(DIZIN, ad)):
            tamam = False
    return tamam


def paketle() -> None:
    """Ham `.dic`/`.aff` dosyalarindan `.xz` uret (bir kereye mahsus)."""
    for ad in DOSYALAR:
        kaynak = os.path.join(DIZIN, ad)
        if not os.path.exists(kaynak):
            raise SystemExit("bulunamadi: sozlukler/%s" % ad)
        ham = open(kaynak, "rb").read()
        sik = lzma.compress(ham, preset=9)
        with open(kaynak + ".xz", "wb") as f:
            f.write(sik)
        print("  %s: %.2f MB -> %.2f MB"
              % (ad, len(ham) / 1048576, len(sik) / 1048576))


if __name__ == "__main__":
    if "--paketle" in sys.argv:
        paketle()
    else:
        sys.exit(0 if ac() else 1)
