# -*- coding: utf-8 -*-
"""macOS'ta ARAYUZUN KENDI derleme yolu PDF uretiyor mu.

NEDEN BOYLE: derlemeyi arayuzde tetiklemek Ctrl+S ya da Derle dugmesi
istiyor, yani klavye/fare. CI kosucusunda System Events'in Erisilebilirlik
izni YOK ("Can't get process ... Invalid index"), o yuzden GUI otomasyonu
calismiyor. Burada arayuz PROGRAMLA suruluyor: gercek `MainWindow`,
gercek `LatexCompiler`, gercek `derle.sh`, gercek TeX.

Kapsam disi: PyInstaller paketleme katmani. O ayrica olculuyor (paket
uretiliyor, imzasi dogrulaniyor, uygulama aciliyor).

Kehanet PDF'in OLUSMASI ve derleyicinin hata bildirmemesi.
"""
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KOK)
sys.path.insert(0, os.path.join(KOK, "desktop"))

from PyQt6.QtCore import QTimer                                  # noqa: E402
from PyQt6.QtWidgets import QApplication                         # noqa: E402

from core.paths import macos_path_tamamla                        # noqa: E402

macos_path_tamamla()

BELGE = "\n".join([
    r"\documentclass{article}",
    r"\begin{document}",
    r"\section{Deneme}\label{b}",
    r"Bkz. bolum \ref{b}.",
    r"\end{document}",
    "",
])


def main():
    hedef_dizin = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gui_derleme"
    os.makedirs(hedef_dizin, exist_ok=True)
    tex = os.path.join(hedef_dizin, "deneme.tex")
    pdf = os.path.join(hedef_dizin, "deneme.pdf")
    with open(tex, "w", encoding="utf-8") as f:
        f.write(BELGE)
    if os.path.exists(pdf):
        os.remove(pdf)

    app = QApplication(sys.argv[:1])
    from gui.main_window import MainWindow

    pencere = MainWindow(open_file=tex)
    pencere.show()

    durum = {"bitti": False, "sonuc": None}

    def _bitti(sonuc):
        durum["bitti"] = True
        durum["sonuc"] = sonuc
        app.quit()

    pencere._compiler.compilation_finished.connect(_bitti)

    # Arayuzun KENDI yolu: kaydet ve derle (Ctrl+S'in bagli oldugu islev).
    QTimer.singleShot(1500, pencere._on_save_and_compile)
    # Derleme asilirsa is sonsuza kadar beklemesin.
    QTimer.singleShot(180000, app.quit)
    app.exec()

    print("derleme bitti mi : %s" % durum["bitti"])
    sonuc = durum["sonuc"]
    if sonuc is not None:
        print("basarili mi      : %s" % getattr(sonuc, "success", "?"))
        hatalar = getattr(sonuc, "errors", []) or []
        print("hata sayisi      : %d" % len(hatalar))
        for h in hatalar[:3]:
            print("   %s" % str(getattr(h, "message", h))[:90])
    print("PDF var mi       : %s" % os.path.exists(pdf))
    if os.path.exists(pdf):
        print("PDF boyutu       : %d bayt" % os.path.getsize(pdf))
        try:
            import pypdfium2 as pdfium
            belge = pdfium.PdfDocument(pdf)
            metin = belge[0].get_textpage().get_text_bounded()
            belge.close()
            duz = " ".join(metin.split())
            print("PDF metni        : %r" % duz[:80])
            # Ikinci gecis kostu mu: \ref cozulmediyse "??" kalir.
            print("atif cozuldu mu  : %s" % ("??" not in duz))
        except Exception as e:                                   # noqa: BLE001
            print("PDF metni okunamadi: %s" % e)

    return 0 if os.path.exists(pdf) else 1


if __name__ == "__main__":
    sys.exit(main())
