"""Yüksek DPI ekranda PDF netliği.

Kare MANTIKSAL ölçekte çiziliyordu; çarpanı 2 olan ekranda (Retina, %200
Windows) Qt onu iki katına büyütüyor ve metin bulanıklaşıyordu. ÖLÇÜLDÜ
(2026-09-26, gerçek Windows penceresi, QT_SCALE_FACTOR ile; kehanet aynı
sayfanın pdfium'la FİZİKSEL çözünürlükte çizimi, ölçüt kenar enerjisi):

    çarpan   görünüm önce/sonra   sunum önce/sonra
    1.25     %77 / %100           %71 / %100
    1.5      %65 / %91            %59 / %91
    2        %52 / %100           %37 / %100

1.5'te kalan fark Qt'nin kesirli ölçeklemesinden: etiketin mantıksal boyu
çarpı 1.5 tam sayı etmiyor. Pencere çarpanı farklı bir ekrana taşınınca da
kareler eski çarpanda kalıyordu.

Test AYRI SÜREÇTE: Qt'nin ekransız platformu iki sanal ekranla kuruluyor
(A 96 dpi, B 192 dpi, yani çarpan 1 ve 2) ve platform süreç başına bir kez
seçiliyor.
"""

import os
import subprocess
import sys

import pytest

try:
    import PyQt6.QtWidgets  # noqa: F401
    _VAR = True
except ImportError:  # pragma: no cover
    _VAR = False

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_COCUK = r'''
import os, sys
os.chdir(sys.argv[1])
# Yol GÖRELİ: "C:"deki iki nokta Qt'nin platform argümanlarını bölüyor.
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=ekranlar.json"
sys.path[:0] = [sys.argv[2], os.path.join(sys.argv[2], "desktop")]
import core.log as _gunluk
_gunluk.LOG_DIR = sys.argv[1]
_gunluk.LOG_FILE = os.path.join(_gunluk.LOG_DIR, "latex-editor.log")
import time
from PIL import Image, ImageChops, ImageStat
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
app = QApplication([])
if [round(s.devicePixelRatio()) for s in app.screens()] != [1, 2]:
    print("EKRANLAR_KURULAMADI", [s.devicePixelRatio() for s in app.screens()])
    sys.exit(0)
from gui.pdf_viewer import PdfViewer
from gui.pdfium_lock import pdfium_lock
from gui.theme import THEMES


def bekle(kosul, sn=5.0):
    son = time.monotonic() + sn
    while not kosul() and time.monotonic() < son:
        app.processEvents()
        time.sleep(0.01)
    return kosul()


def pil(qimg):
    qimg = qimg.convertToFormat(QImage.Format.Format_RGB888)
    p = qimg.bits()
    p.setsize(qimg.sizeInBytes())
    return Image.frombuffer("RGB", (qimg.width(), qimg.height()), bytes(p),
                            "raw", "RGB", qimg.bytesPerLine(), 1)


def fark(etiket, olcek):
    """Ekrana çizilen (grab, fiziksel piksel) ile pdfium'un fiziksel çizimi."""
    ekran = pil(etiket.grab().toImage())
    with pdfium_lock:
        keh = v._pdf[0].render(scale=olcek).to_pil().convert("RGB")
    w, h = min(ekran.width, keh.width), min(ekran.height, keh.height)
    a, b = ekran.crop((0, 0, w, h)), keh.crop((0, 0, w, h))
    return ImageStat.Stat(ImageChops.difference(a, b).convert("L")).mean[0]


def kare(etiket):
    pm = etiket.pixmap()
    return None if pm is None or pm.isNull() else pm


kap = QWidget()
v = PdfViewer(theme=THEMES["dark"])
QVBoxLayout(kap).addWidget(v)
b = app.screens()[1].geometry()
kap.setGeometry(b.x() + 20, b.y() + 20, 700, 500)
kap.show()
assert v.load_pdf(sys.argv[3])
lb = v._page_labels[0]
assert bekle(lambda: kare(lb) is not None), "sayfa çizilmedi"
# Pencere önce birincil ekranda belirmiş olabilir: çarpan 2'yi bekle
bekle(lambda: kare(lb) is not None and kare(lb).devicePixelRatio() == 2.0, 3.0)
print("GORUNUM", v.screen().name(), kare(lb).devicePixelRatio(),
      "%.2f" % fark(lb, v._olcek(0) * 2), flush=True)

v.enter_presentation()
app.processEvents()
plb = v._presentation_label
with pdfium_lock:
    pw = v._pdf[0].get_width()
# Eski kodda `_sunum_olcek` yok; orada etiket karenin kendisi (çarpan 1)
olcek = getattr(v, "_sunum_olcek", None) or plb.width() / pw
print("SUNUM", v._presentation_widget.screen().name(), kare(plb).devicePixelRatio(),
      "%.2f" % fark(plb, olcek * 2), flush=True)
v.exit_presentation()
app.processEvents()

a = app.screens()[0].geometry()
kap.move(a.x() + 20, a.y() + 20)
bekle(lambda: kare(lb) is not None and kare(lb).devicePixelRatio() == 1.0, 3.0)
print("TASINDI", v.screen().name(),
      kare(lb).devicePixelRatio() if kare(lb) is not None else None, flush=True)
v.shutdown()
'''


@pytest.mark.skipif(not _VAR, reason="PyQt6 gerekli")
def test_CARPANI_2_olan_ekranda_PDF_keskin_ve_tasininca_yeniden_ciziliyor(
        tmp_path):
    """Kırılırsa: kare yine mantıksal çözünürlükte (bulanık) ya da pencere
    başka çarpanlı ekrana geçince eski çarpanda kalıyor demektir."""
    (tmp_path / "ekranlar.json").write_text(
        '{"screens": ['
        '{"name": "A", "x": 0, "y": 0, "width": 1920, "height": 1080,'
        ' "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},'
        '{"name": "B", "x": 1920, "y": 0, "width": 1920, "height": 1080,'
        ' "logicalDpi": 192, "logicalBaseDpi": 96, "dpr": 1}]}\n',
        encoding="utf-8")
    cocuk = tmp_path / "cocuk.py"
    cocuk.write_text(_COCUK, encoding="utf-8")
    pdf = os.path.join(_KOK, "tests", "veri", "arama_ornegi.pdf")
    r = subprocess.run([sys.executable, str(cocuk), str(tmp_path), _KOK, pdf],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180)
    # Çocuğun günlüğü hapiste yazıldı mı: yazılmadıysa gerçek dosyaya gitmiştir
    assert (tmp_path / "latex-editor.log").exists(), r.stderr[-400:]
    if "EKRANLAR_KURULAMADI" in r.stdout:
        pytest.skip("bu Qt sürümü ekransız platformda çok ekranı kurmuyor")
    satirlar = {s.split()[0]: s.split()[1:] for s in r.stdout.splitlines()
                if s.split() and s.split()[0] in ("GORUNUM", "SUNUM", "TASINDI")}
    assert set(satirlar) == {"GORUNUM", "SUNUM", "TASINDI"}, (
        r.stdout[-600:], r.stderr[-600:])

    ekran, carpan, sapma = satirlar["GORUNUM"]
    assert ekran == "B", "kapı boş koşuyor: pencere çarpanı 2 olan ekranda değil"
    assert float(carpan) == 2.0, "görünümün karesi çarpan %s" % carpan
    assert float(sapma) < 0.5, "görünüm pdfium'un keskin çiziminden %s sapıyor" % sapma

    ekran, carpan, sapma = satirlar["SUNUM"]
    assert float(carpan) == 2.0, "sunumun karesi çarpan %s" % carpan
    assert float(sapma) < 0.5, "sunum pdfium'un keskin çiziminden %s sapıyor" % sapma

    ekran, carpan = satirlar["TASINDI"]
    assert ekran == "A", "kapı boş koşuyor: pencere taşınmadı"
    assert carpan == "1.0", "taşınınca kareler eski çarpanda kaldı: %s" % carpan
