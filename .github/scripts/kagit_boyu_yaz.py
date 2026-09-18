# -*- coding: utf-8 -*-
"""Bir PDF'in ilk sayfasinin kagit boyunu ve karsiligini yazar.

`kagit_boyu_haritasi.sh` her platformda bunu cagiriyor, boylece ciktilar
satir satir karsilastirilabiliyor.

Ayri dosya olmasinin sebebi ayni: kabuk betiginin icine gomulen Python,
YAML `run:` blogunun icinde oldugunda blok skalerini bozuyor.
"""
import sys

# Genislik x yukseklik, NOKTA (1/72 inc)
KAGITLAR = {
    "A4": (595.276, 841.890),
    "A5": (419.528, 595.276),
    "US Letter": (612.0, 792.0),
    "US Legal": (612.0, 1008.0),
    "B5": (498.898, 708.661),
}
TOLERANS = 2.0


def ad_bul(g, y):
    for ad, (kg, ky) in KAGITLAR.items():
        if abs(g - kg) <= TOLERANS and abs(y - ky) <= TOLERANS:
            return ad
    return "(bilinen kagit degil)"


def main(yol, etiket):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("  %s: (pypdfium2 yok, olculemedi)" % etiket)
        return
    belge = pdfium.PdfDocument(yol)
    g, y = belge[0].get_size()
    belge.close()
    print("  %-4s %7.2f x %7.2f nokta  = %6.1f x %6.1f mm  -> %s"
          % (etiket, g, y, g * 25.4 / 72, y * 25.4 / 72, ad_bul(g, y)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
