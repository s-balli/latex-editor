# -*- coding: utf-8 -*-
"""OLCUM: sayfa belgenin bekledigi kagittan kisayken metin KAYBOLUYOR mu.

NEDEN. `\\documentclass[a4paper]` yazan ama `geometry` YUKLEMEYEN bir belge
macOS'ta US Letter sayfa aliyor (olculdu 2026-09-19). Sinif secenegi metin
blogunu A4'e gore kuruyor: TeX sayfayi `\\textheight` kadar dolduruyor ve o
yukseklik 297 mm'lik bir sayfaya gore hesaplanmis. Cikti sayfasi ise
279.4 mm. Aradaki 17.6 mm'de ne oluyor, iki ihtimal var:

  A) TeX satirlari bir sonraki sayfaya ITIYOR  -> hicbir sey kaybolmaz,
     yalniz sayfa sayisi artar
  B) Satirlar sayfanin DISINA ciziliyor        -> metin KAYBOLUYOR

Ayirt edici olcut: kaynaktaki her satir ciktidan CIKARILABILIYOR mu.
Satirlar numarali, yani eksik olan tek tek adlandirilabiliyor.

Kullanim: python kagit_tasma_olcumu.py <calisma_dizini> [--pdflatex]
"""
import os
import re
import subprocess
import sys

SATIR = 200


def belge_yaz(yol):
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\\documentclass[a4paper,11pt]{article}\n")
        f.write("\\begin{document}\n")
        for i in range(1, SATIR + 1):
            f.write("\\noindent SATIR%03d bu satir olcum icindir.\\par\n" % i)
        f.write("\\end{document}\n")


def main(calisma, motor):
    kok = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    os.makedirs(calisma, exist_ok=True)
    tex = os.path.join(calisma, "tasma.tex")
    pdf = os.path.join(calisma, "tasma.pdf")
    belge_yaz(tex)

    cmd = ["bash", os.path.join(kok, "core", "derle.sh"), tex]
    if motor:
        cmd.append(motor)
    subprocess.run(cmd, capture_output=True, timeout=300)
    if not os.path.exists(pdf):
        print("PDF URETILMEDI, olcum yapilamadi")
        return 1

    import pypdfium2 as pdfium
    belge = pdfium.PdfDocument(pdf)
    gen, yuk = belge[0].get_size()
    metin = "\n".join(belge[i].get_textpage().get_text_bounded()
                      for i in range(len(belge)))
    sayfa_sayisi = len(belge)
    belge.close()

    bulunan = set(int(x) for x in re.findall(r"SATIR(\d{3})", metin))
    eksik = [i for i in range(1, SATIR + 1) if i not in bulunan]

    print("platform   :", sys.platform)
    print("motor      :", motor or "(varsayilan)")
    print("sayfa boyu : %.2f x %.2f nokta (%.1f x %.1f mm)"
          % (gen, yuk, gen * 25.4 / 72, yuk * 25.4 / 72))
    print("sayfa      :", sayfa_sayisi)
    print("kaynak satiri:", SATIR, "| ciktida CIKARILABILEN:", len(bulunan))
    print("cikarilamayan:", len(eksik))

    # ASIL OLCUT BU. Metnin cikarilabilir olmasi sayfada GORUNDUGU anlamina
    # gelmiyor: sayfa kutusunun disina cizilen metin de icerik akisinda
    # duruyor ve `get_text_bounded` onu yine veriyor. Ilk surumde olcut
    # "cikarilabiliyor mu" idi ve gormesi gereken kusuru goremezdi.
    # Burada karakter kutulari sayfa kutusuyla karsilastiriliyor.
    belge = pdfium.PdfDocument(pdf)
    tasan = 0
    for i in range(sayfa_sayisi):
        sayfa = belge[i]
        _g, y = sayfa.get_size()
        tp = sayfa.get_textpage()
        kutular = [tp.get_charbox(k) for k in range(tp.count_chars())]
        kutular = [k for k in kutular if k]
        if not kutular:
            continue
        alt = min(k[1] for k in kutular)
        ust = max(k[3] for k in kutular)
        disarida = alt < 0 or ust > y
        if disarida:
            tasan += 1
        print("  sayfa %d: metin %.1f .. %.1f | sayfa 0 .. %.1f%s"
              % (i + 1, alt, ust, y, "   <-- SAYFA DISINDA" if disarida else ""))
    belge.close()
    print("SAYFA DISINA TASAN SAYFA:", tasan)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1],
                          sys.argv[2] if len(sys.argv) > 2 else ""))
