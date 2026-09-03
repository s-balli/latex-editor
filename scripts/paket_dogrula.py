# -*- coding: utf-8 -*-
"""Uretilen paketin ICINDE ne var, denetle.

NEDEN VAR: yazim denetiminin pakete girmesi UC ayri seyin bir arada
olmasina bagli ve ucu de ayri sekilde sessizce kaybolabiliyor:

  1. `spylls` modulu (PYZ icinde, saf Python)
  2. bizim `sozlukler/tr_TR.dic` + `.aff` (spec `.xz`den aciyor)
  3. spylls'in KENDI `en_US` sozlugu (ikinci dil ozelligi buna dayaniyor)

Ucuncusu ilk denemede GERCEKTEN EKSIK CIKTI: PyInstaller modul analizi
yalniz `.py` dosyalarini goruyor, paketin veri dosyalarini gormuyor. Exe
sorunsuz uretiliyordu ve ikinci dil calismiyordu. Testler bunu goremez,
cunku testler paketlenmemis kaynakta kosuyor.

Ayrica `.xz` dosyalarinin pakete OLU AGIRLIK olarak girmedigi de
denetleniyor (1.6 MB).

Kullanim:
    python scripts/paket_dogrula.py "desktop/dist/LaTeX Editor.exe"
    python scripts/paket_dogrula.py desktop/dist/LaTeXEditor      # onedir
"""
from __future__ import annotations

import os
import sys


def _tek_dosya_icerigi(yol):
    """Onefile exe: PyInstaller CArchive TOC'u."""
    from PyInstaller.archive.readers import CArchiveReader
    return list(CArchiveReader(yol).toc)


def _dizin_icerigi(kok):
    """Onedir: dizin agacindaki goreli yollar."""
    adlar = []
    for r, _d, fs in os.walk(kok):
        for f in fs:
            adlar.append(os.path.relpath(os.path.join(r, f), kok))
    return adlar


def dogrula(yol: str) -> int:
    if os.path.isdir(yol):
        adlar = _dizin_icerigi(yol)
    else:
        adlar = _tek_dosya_icerigi(yol)
    duz = [a.replace("\\", "/") for a in adlar]

    hata = []

    def var_mi(parca):
        return [a for a in duz if parca in a]

    tr = var_mi("sozlukler/tr_TR.dic")
    if not tr:
        hata.append("tr_TR.dic pakete GIRMEMIS (spec sozlugu acamamis olabilir)")
    if not var_mi("sozlukler/tr_TR.aff"):
        hata.append("tr_TR.aff pakete GIRMEMIS")

    # Ikinci dil: spylls'in kendi en_US'u. ILK DENEMEDE EKSIKTI.
    if not var_mi("spylls/hunspell/data/en/en_US.dic"):
        hata.append("spylls en_US.dic pakete GIRMEMIS: ikinci dil calismaz")
    if not var_mi("spylls/hunspell/data/en/en_US.aff"):
        hata.append("spylls en_US.aff pakete GIRMEMIS: ikinci dil calismaz")

    # Olu agirlik denetimi
    xz = var_mi(".xz")
    if xz:
        hata.append("sikistirilmis sozluk de paketlenmis (olu agirlik): %s"
                    % xz[:3])
    for istenmeyen in ("data/ru/", "data/sv/"):
        if var_mi(istenmeyen):
            hata.append("spylls'in kullanilmayan sozlugu paketlenmis: %s"
                        % istenmeyen)

    print("paket icerigi: %d girdi" % len(adlar))
    for a in sorted(var_mi("sozlukler/") + var_mi("spylls/hunspell/data/")):
        print("  bulundu: %s" % a)

    if hata:
        print()
        for h in hata:
            print("HATA: %s" % h)
        return 1
    print("paket tam: tr_TR sozlugu ve spylls en_US icinde, olu agirlik yok")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("kullanim: paket_dogrula.py <exe ya da dist dizini>")
    sys.exit(dogrula(sys.argv[1]))
