# -*- coding: utf-8 -*-
"""GECICI on ucus yardimcisi, BIRLESTIRILMEYECEK.

Paketteki gui.pdf_render yeni mi (rev_byteorder var, to_pil yok) ve PYZ'de
PIL modulu var mi. Arsiv tek dosyada (exe, ELF) ya da .app icinde olabilir;
.app verilirse PYZ tasiyan dosya aranir.
    python .github/scripts/_onucus_cizim.py <exe | elf | .app>
"""
import os
import sys

from PyInstaller.archive.readers import CArchiveReader


def adaylar(yol):
    if os.path.isfile(yol):
        yield yol
        return
    birinci = os.path.join(yol, "Contents", "MacOS", "latex-editor")
    if os.path.isfile(birinci):
        yield birinci
    for kok, _d, dosyalar in os.walk(yol):
        for ad in dosyalar:
            tam = os.path.join(kok, ad)
            if tam != birinci and os.path.getsize(tam) > 1_000_000:
                yield tam


for aday in adaylar(sys.argv[1]):
    try:
        arsiv = CArchiveReader(aday)
        pyz_adi = [k for k, v in arsiv.toc.items() if v[-1] == "z"]
        if not pyz_adi:
            continue
        pyz = arsiv.open_embedded_archive(pyz_adi[0])
    except Exception:                          # noqa: BLE001
        continue
    ham = pyz.extract("gui.pdf_render", raw=True)
    yeni = b"rev_byteorder" in ham
    eski = b"to_pil" in ham
    pil = sorted(k for k in pyz.toc if k == "PIL" or k.startswith("PIL."))
    print("arsiv:", aday)
    print("gui.pdf_render: rev_byteorder %s | to_pil %s" % (yeni, eski))
    print("PYZ'de PIL modulu: %d" % len(pil))
    sys.exit(0 if yeni and not eski and not pil else 1)
print("PYZ tasiyan arsiv bulunamadi")
sys.exit(2)
