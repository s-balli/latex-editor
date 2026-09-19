# -*- coding: utf-8 -*-
"""Açık sayfa geçişleri geri alınıyordu.

ORTAK KÖK. `_render_visible` çağrıldığı her yerde `_current_page`i KAYDIRMA
KONUMUNDAN yeniden hesaplıyordu. Oysa o hesap yalnız kullanıcı kaydırdığında
doğru: sayfa düğmesi, yer imi, SyncTeX ileri araması ve PDF içi bağlantı
`_current_page`i kendileri atıyor ve ardından yalnız çizim için 100 ms'lik
bir zamanlayıcı kuruyor. O zamanlayıcı geçişi geri alıyordu.

İki ayrı belirti, tek kök (ÖLÇÜLDÜ 2026-09-19, altı sayfalık belge):

  1. Uzaklaştırılmış belgede ">" düğmesi ÖLÜ. `ensureWidgetVisible` hedef
     zaten görünürken hiçbir şey yapmıyor (Qt: `visibleRect.contains(
     focusRect)` -> return), görüntü kımıldamıyor ve sayaç 100 ms sonra eski
     sayfaya dönüyordu. Üç basışta da "Sayfa 2 / 6" olup "Sayfa 1 / 6"ya
     döndü; yer imi 3. sayfayı istedi, sayaç 1. sayfada kaldı.
  2. Olağan %100 ölçekte SyncTeX 4. sayfanın üst yarısına atlıyor, vurgu
     doğru sayfada çiziliyor, sayaç "Sayfa 3 / 6"ya dönüyordu.
     `_hedefe_kaydir` pay bıraktığı için kaydırma konumu hedef sayfanın
     ÜSTÜNDE, yani önceki sayfanın içinde kalıyor.

`_current_page` yalnız sayaç değil: "Genişliğe Sığdır" ölçüyü ondan alıyor
ve sunum modu (F5) oradan başlıyor.

SON KAPI kontrol: elle kaydırma geçerli sayfayı HÂLÂ belirlemeli. Düzeltme
fazla genişse (hesap tümden kalkarsa) orası kırılır.
"""

import os
import time

import pytest

try:
    import pypdfium2
    from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QTimer
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.pdfium_lock import pdfium_lock
    from gui.theme import THEMES
    _VAR = True
except ImportError:                                   # pragma: no cover
    _VAR = False

gui = pytest.mark.skipif(not _VAR, reason="PyQt6 / gui modülleri gerekli")

_KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Depoda duran gerçek belge (3 sayfa, A4). Ham PDF yazan bir yardımcı
# KOPYALANMIYOR; var olan fixture iki kez içe aktarılıp altı sayfaya
# çıkarılıyor. Altı ŞART: üç sayfada, %20 ölçekte kaydırma çubuğu 2. sayfanın
# üstüne zaten varamıyor, yani kapı düz yolu değil sınır durumunu ölçerdi
# (ölçüldü: çubuk en çok 228 px, 2. sayfanın üstü 271 px).
_FIXTURE = os.path.join(_KOK, "tests", "veri", "arama_ornegi.pdf")
SAYFA = 6


@pytest.fixture(scope="module")
def qapp():
    if not _VAR:
        yield None
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def belge(tmp_path_factory):
    if not _VAR:
        yield ""
        return
    yol = str(tmp_path_factory.mktemp("gecis") / "alti_sayfa.pdf")
    with pdfium_lock:
        kaynak = pypdfium2.PdfDocument(_FIXTURE)
        d = pypdfium2.PdfDocument.new()
        d.import_pages(kaynak)
        d.import_pages(kaynak)
        d.save(yol)
        d.close()
        kaynak.close()
    yield yol


def _dongu(ms=5):
    """Gerçek olay döngüsü; `processEvents` yerleşim için yetmiyor."""
    d = QEventLoop()
    QTimer.singleShot(ms, d.quit)
    d.exec()


def _bekle(kosul, saniye=3.0):
    bitis = time.monotonic() + saniye
    while not kosul() and time.monotonic() < bitis:
        _dongu(5)
    return kosul()


def _zamanlayici_kossun():
    """Geçişlerin kurduğu 100 ms'lik `_render_visible` çağrısı gelsin.

    Kusur TAM BURADA görünüyordu: geçişin hemen ardından sayaç doğru, 100 ms
    sonra yanlıştı. Zamanlayıcı beklenmezse kapı boş koşar.
    """
    bitis = time.monotonic() + 0.5
    while time.monotonic() < bitis:
        _dongu(20)


def _yerlesti(v):
    """Ölçek değişikliği yerleşsin: iki turda aynı geometri."""
    onceki = None
    bitis = time.monotonic() + 3.0
    while time.monotonic() < bitis:
        simdi = (v._page_labels[0].height(),
                 v._scroll.verticalScrollBar().maximum())
        if simdi == onceki:
            return True
        onceki = simdi
        _dongu(10)
    return False


def _ust(v, i):
    return v._page_labels[i].mapTo(v._pages_widget, QPoint(0, 0)).y()


@pytest.fixture
def gorucu(qapp, belge):
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(700, 600)
    v.show()
    assert v.load_pdf(belge), "belge açılmadı: %s" % belge
    assert _bekle(lambda: len(v._page_labels) == SAYFA
                  and v._scroll.verticalScrollBar().maximum() > 0), \
        "belge yerleşmedi"
    yield v
    v.shutdown()
    v.close()
    QApplication.instance().sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _uzaklastir(v):
    """Birden fazla sayfa aynı anda görünsün ve görüntü 1. sayfanın içinde
    dursun. Kusurun koşulu bu; kurulmadıysa kapı bir şey kanıtlamaz."""
    v._zoom_uygula(0.2)
    assert _yerlesti(v)
    assert v._page_labels[0].height() < v._scroll.viewport().height(), \
        "koşul kurulmadı: sayfa hâlâ görüntüden büyük"
    v._scroll.verticalScrollBar().setValue(_ust(v, 0) + 20)
    _dongu(20)
    assert v._current_page == 0


@gui
class TestAcikGecisGeriAlinmiyor:

    def test_SONRAKI_sayfa_dugmesi_uzaklastirilmis_belgede_ilerliyor(
            self, gorucu):
        """Kusurun kendisi: hedef zaten görünürken düğme hiçbir şey yapmıyordu."""
        _uzaklastir(gorucu)
        gorucu.next_page()
        _zamanlayici_kossun()
        assert gorucu._current_page == 1, gorucu._lbl_page.text()
        assert "2 / %d" % SAYFA in gorucu._lbl_page.text()
        # Görüntü de gerçekten oynamalı: sayaç tek başına yeterli değil,
        # "sayacı doğru yaz ama yerinde kal" da aynı kusur olurdu.
        assert gorucu._scroll.verticalScrollBar().value() == _ust(gorucu, 1)

    def test_YER_IMI_tiklamasi_gittigi_sayfayi_soyluyor(self, gorucu):
        """Yer imi yolu (`_bookmarks._on_bookmark_clicked`) sayfa
        düğmelerinden farklı olarak `_update_nav` çağırmıyor."""
        _uzaklastir(gorucu)
        gorucu._scroll_to_page(2)
        _zamanlayici_kossun()
        assert gorucu._current_page == 2, gorucu._lbl_page.text()
        assert "3 / %d" % SAYFA in gorucu._lbl_page.text()

    def test_SON_sayfaya_gidis_cubuk_VARAMASA_da_dogru(self, gorucu):
        """Sınır: belgenin sonu görüntüden kısa, çubuk hedefe varamıyor.

        Kayıt `setValue`den SONRA konuyor, yoksa kırpılan kaydırmanın
        tetiklediği hesap sayfayı geri alırdı.

        SAYAÇ da burada sınanıyor: kaydırma hedefe varan yollarda etiketi
        `_on_scroll`un hesabı zaten tazeliyor, varamayan bu yolda ise
        tazeleyen tek şey `_scroll_to_page`in kendi `_update_nav` çağrısı.
        Mutasyonla görüldü (2026-09-19): o çağrı kaldırıldığında yalnız
        BURASI kırılıyor.
        """
        _uzaklastir(gorucu)
        dikey = gorucu._scroll.verticalScrollBar()
        son = SAYFA - 1
        assert _ust(gorucu, son) > dikey.maximum(), \
            "koşul kurulmadı: çubuk son sayfanın üstüne varabiliyor"
        gorucu._scroll_to_page(son)
        _zamanlayici_kossun()
        assert gorucu._current_page == son, gorucu._lbl_page.text()
        assert "%d / %d" % (son + 1, SAYFA) in gorucu._lbl_page.text()
        # Sayfa gerçekten görüntüde olmalı: doğru sayıyı yazıp yanlış yere
        # bakmak da kusur olurdu.
        y = _ust(gorucu, son)
        vp = gorucu._scroll.viewport().height()
        assert y < dikey.value() + vp
        assert y + gorucu._page_labels[son].height() > dikey.value()

    def test_SYNCTEX_ileri_aramasi_sayaci_geri_almiyor(self, gorucu):
        """Olağan ölçekte, hedef sayfanın ÜST YARISINDA.

        `_hedefe_kaydir` görüntünün yarısı kadar pay bıraktığı için kaydırma
        konumu hedef sayfanın üstünde, önceki sayfanın içinde kalıyor.
        """
        gorucu._zoom_uygula(1.0)
        assert _yerlesti(gorucu)
        assert gorucu._page_labels[0].height() > \
            gorucu._scroll.viewport().height(), "koşul kurulmadı"
        hedef = SAYFA - 1
        gorucu.scroll_to_position(hedef + 1, 100.0, 120.0,
                                  left=100.0, width=60.0, height=12.0)
        _zamanlayici_kossun()
        assert gorucu._scroll.verticalScrollBar().value() < _ust(gorucu, hedef), \
            "koşul kurulmadı: kaydırma hedef sayfanın üstünde kalmadı"
        assert gorucu._current_page == hedef, gorucu._lbl_page.text()
        # Atlamanın kendisi değişmedi: vurgu hedef sayfanın etiketinde
        vurgu = gorucu._highlight_label
        assert vurgu is not None
        assert gorucu._page_labels.index(vurgu.parent()) == hedef


@gui
class TestKaydirmaSayfayiBelirlemeye_devam_ediyor:
    """KONTROL. Düzeltme hesabı tümden kaldırırsa burası kırılır."""

    def test_ELLE_kaydirma_gecerli_sayfayi_belirliyor(self, gorucu):
        gorucu._zoom_uygula(1.0)
        assert _yerlesti(gorucu)
        for hedef in (1, 2, 0):
            gorucu._scroll.verticalScrollBar().setValue(_ust(gorucu, hedef) + 30)
            _dongu(30)
            assert gorucu._current_page == hedef, (
                "%d. sayfaya kaydırıldı, sayaç %r"
                % (hedef + 1, gorucu._lbl_page.text()))
