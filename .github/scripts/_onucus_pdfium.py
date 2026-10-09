# -*- coding: utf-8 -*-
"""GECICI on ucus yardimcisi, BIRLESTIRILMEYECEK.

Pakete giren pypdfium2: iki version.json (pypdfium2 ve pypdfium2_raw) ve
pdfium kutuphanesi pakette mi, surum yapim ortamindakiyle ayni mi. Tek
dosya exe verilirse PyInstaller arsivinin icindekiler okunuyor; dizin
verilirse (acilmis AppImage, .app) dosyalar araniyor.
    python .github/scripts/_onucus_pdfium.py <exe | dizin>
"""
import json
import os
import sys
from importlib.metadata import version

KUTUPHANE = ("pdfium.dll", "libpdfium.so", "libpdfium.dylib")


def arsivden(yol):
    from PyInstaller.archive.readers import CArchiveReader
    arsiv = CArchiveReader(yol)
    for ad in arsiv.toc:
        yield ad.replace("\\", "/"), (lambda a=ad: arsiv.extract(a))


def dizinden(yol):
    for kok, _d, dosyalar in os.walk(yol):
        for ad in dosyalar:
            tam = os.path.join(kok, ad)
            goreli = os.path.relpath(tam, yol).replace(os.sep, "/")
            yield goreli, (lambda t=tam: open(t, "rb").read())


yol = sys.argv[1]
girdiler = dict(arsivden(yol) if os.path.isfile(yol) else dizinden(yol))
surumler = {}
for ad, oku in girdiler.items():
    for paket in ("pypdfium2", "pypdfium2_raw"):
        hedef = paket + "/version.json"
        if ad == hedef or ad.endswith("/" + hedef):
            surumler[paket] = json.loads(oku())
kutuphane = sorted(ad for ad in girdiler if ad.rsplit("/", 1)[-1] in KUTUPHANE)

p = surumler.get("pypdfium2")
r = surumler.get("pypdfium2_raw")
paketteki = "%d.%d.%d" % (p["major"], p["minor"], p["patch"]) if p else None
pdfium = "%d.%d.%d.%d" % (r["major"], r["minor"], r["build"], r["patch"]) if r else None
beklenen = version("pypdfium2")
print("yapim ortaminda pypdfium2:", beklenen)
print("paketteki pypdfium2:", paketteki, "| PDFium:", pdfium)
print("paketteki kutuphane:", ", ".join(kutuphane) or "YOK")
sys.exit(0 if paketteki == beklenen and pdfium and kutuphane else 1)
