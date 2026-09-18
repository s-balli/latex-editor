# -*- coding: utf-8 -*-
"""Bir PDF'in karsilastirilabilir ozeti: surum, sayfa, Producer, metin.

NEDEN AYRI DOSYA. Ayni is once YAML'in `run:` blogu icine heredoc ile
gomulmustu; heredoc govdesi sutun 0'dan basladigi icin YAML blok skaleri
orada bitiyor ve dosya ayristirilamaz hale geliyor. Bu oturumda ayni
tuzaga birkac kez dusuldu.

Kullanim:  python3 pdf_ozet.py <dosya.pdf> [etiket]
"""
import os
import re
import sys


def ozet(yol: str, etiket: str = "") -> None:
    ham = open(yol, "rb").read()
    bas = etiket or os.path.basename(yol)
    print("=== " + bas + " ===")
    print("  boyut     :", len(ham), "bayt")
    print("  PDF surumu:", ham[:8].decode("latin-1").strip())
    # Sayfa sayisi HAM METINDEN sayilmiyor: nesneler sikistirilmis akis
    # icinde olabiliyor ve `/Type /Page` hic gorunmuyor (olculdu: lualatex
    # ciktisinda 0 cikti). Sayiyi ayristiriciya sormak gerekiyor, asagida.
    for ad in (b"Producer", b"Creator"):
        m = re.search(rb"/" + ad + rb"\s*\(([^)]*)\)", ham)
        print("  %-10s:" % ad.decode(),
              m.group(1).decode("latin-1") if m else "(yok)")
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("  sayfa     : (pypdfium2 yok)")
        print("  metin     : (pypdfium2 yok)")
        return
    belge = pdfium.PdfDocument(yol)
    print("  sayfa     :", len(belge))
    metin = "\n".join(belge[i].get_textpage().get_text_bounded()
                      for i in range(len(belge)))
    belge.close()
    duz = " ".join(metin.split())
    print("  metin     :", repr(duz[:120]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("kullanim: pdf_ozet.py <dosya.pdf> [etiket]")
        raise SystemExit(2)
    ozet(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
