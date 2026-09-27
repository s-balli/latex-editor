"""PDF araç çubuğu: dar bölmede araçlar üst üste binmemeli.

ÖLÇÜLDÜ (2026-09-27, gerçek pencere ve Segoe UI, iki dilde): çubuğun asgari
genişliği 745 px (İngilizce) ile 749 px (Türkçe), ilk açılışta PDF bölmesi
pencerenin yarısı. Varsayılan 1400 px'lik pencerede "Farklı Kaydet" ters
çevirme düğmesinin 21-23 px üstündeydi, 800 px'de on bir çakışma vardı ve
sayfa etiketi kırpılıyordu. Sığmayan araçlar artık "»" menüsüne gidiyor.

Kapılar yazı tipinden BAĞIMSIZ: piksel sayısına değil, Qt'nin yerleştirdiği
geometrinin bağıntılarına bakıyorlar (komşu dikdörtgenler kesişmiyor, çubuk
tam sığınca hiçbir şey gizlenmiyor, gizlenen her araç menüde). Offscreen'de
glifler kutu olarak çiziliyor ve metin daha GENİŞ ölçülüyor; kusur orada
daha geniş bir aralıkta görülüyor, kapılar yine anlamlı.
"""

import pytest

try:
    import pypdfium2
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication, QPushButton
    from gui.pdf_viewer import PdfViewer
    from gui.pdfium_lock import pdfium_lock
    from gui.stylesheet import build_stylesheet
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / pypdfium2 / gui modülleri gerekli",
                allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cubuklu(qapp, tmp_path):
    """Belge yüklü, verilen genişlikte GÖSTERİLMİŞ görüntüleyici üreten fabrika.

    Yerleşim ancak gösterilen pencerede koşuyor; gösterilmezse geometriler
    varsayılan boyda kalır ve karşılaştırmalar boşa döner. Uygulamanın küresel
    stil sayfası da kuruluyor: düğmelerin boyu (dolgu) onunla geliyor ve
    üretimdeki yerleşim ancak onunla ölçülüyor.
    """
    onceki_stil = qapp.styleSheet()
    qapp.setStyleSheet(build_stylesheet(THEMES["dark"]))
    yol = str(tmp_path / "tez.pdf")
    with pdfium_lock:
        belge = pypdfium2.PdfDocument.new()
        for _ in range(120):            # "Sayfa 1 / 120": gerçekçi etiket
            belge.new_page(400, 300)
        belge.save(yol)
        belge.close()
    kurulanlar = []

    def _kur(genislik):
        v = PdfViewer(theme=THEMES["dark"])
        kurulanlar.append(v)
        assert v.load_pdf(yol)
        v.resize(genislik, 400)
        v.show()
        qapp.processEvents()
        return v

    yield _kur
    for v in kurulanlar:
        v.shutdown()
        v.close()
        v.deleteLater()
    # Silme kuyruğu AÇIKÇA boşaltılıyor (bkz. conftest._sahipsiz_qsci_temizle):
    # kapatılmış ama silinmemiş görüntüleyici sonraki testin stil sayfası
    # değişimini alıyor ve süreç erişim hatasıyla (0xC0000005) ölüyordu.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    qapp.setStyleSheet(onceki_stil)


# Yardımcılar çubuğa gezinme düğmesinden ulaşıyor: kapılar düzeltmeden ÖNCEKİ
# kodda da kusurun kendisinde düşsün, eksik bir öznitelikte değil.
def _cubuk(v):
    return v._btn_prev.parentWidget()


def _ogeler(v):
    lay = _cubuk(v).layout()
    return [lay.itemAt(i).widget() for i in range(lay.count())
            if lay.itemAt(i).widget() is not None]


def _araclar(v):
    """Menüye gidebilen komut düğmeleri: gezinme ve "»" dışındakiler."""
    return [w for w in _ogeler(v) if isinstance(w, QPushButton)
            and w not in (v._btn_prev, v._btn_next,
                          getattr(v, "_btn_tasma", None))]


def _cakisma_yok(v):
    gorunur = [w for w in _ogeler(v) if w.isVisible()]
    for a, b in zip(gorunur, gorunur[1:]):
        assert a.geometry().right() < b.geometry().left(), (
            "üst üste biniyor: %r ile %r, %d px" % (
                a.toolTip() or a.text(), b.toolTip() or b.text(),
                a.geometry().right() - b.geometry().left() + 1))
    assert gorunur[-1].geometry().right() < _cubuk(v).width(), "çubuk taşıyor"


@pytest.mark.parametrize("genislik", [250, 300, 400, 500, 600, 700])
def test_DAR_bolmede_araclar_ust_uste_binmiyor(cubuklu, genislik):
    v = cubuklu(genislik)
    assert v._btn_prev.isVisible() and v._btn_next.isVisible(), \
        "gezinme gizlenmiş"
    _cakisma_yok(v)
    gizli = [w for w in _araclar(v) if w.isHidden()]
    assert v._btn_tasma.isVisible() == bool(gizli), \
        '"»" düğmesi gizli araçlarla uyuşmuyor'
    # Sayfa etiketi ancak son çare olarak kırpılabilir
    if v._lbl_page.width() < v._lbl_page.minimumSizeHint().width():
        assert len(gizli) == len(_araclar(v)), \
            "araçlar dururken sayfa etiketi kırpılmış"


def test_TAM_sigan_cubukta_hicbir_arac_gizlenmiyor(cubuklu, qapp):
    """Aşırı düzeltme kapısı: çubuk tam sığınca menü yok, sığmayınca var.

    Sınır ölçüyle kuruluyor: geniş bölmede Qt'nin çubuk için istediği asgari
    genişlik okunuyor, bölme tam o genişliğe ve bir piksel altına getiriliyor.
    Yazı tipi ne olursa olsun sınır aynı yerde.
    """
    v = cubuklu(3000)
    assert not any(w.isHidden() for w in _araclar(v)), "geniş bölmede araç gizli"
    tam = _cubuk(v).layout().minimumSize().width()
    v.resize(tam, 400)
    qapp.processEvents()
    assert _cubuk(v).width() == tam, "çubuk bölmenin genişliğinde değil"
    assert not any(w.isHidden() for w in _araclar(v)), \
        "tam sığan çubukta araç gizlendi"
    v.resize(tam - 1, 400)
    qapp.processEvents()
    assert any(w.isHidden() for w in _araclar(v)), \
        "sığmayan çubukta araç gizlenmedi"
    _cakisma_yok(v)
    # Bölme yeniden genişleyince araçlar geri geliyor, "»" kalkıyor
    v.resize(tam, 400)
    qapp.processEvents()
    assert not any(w.isHidden() for w in _araclar(v)), "araçlar geri gelmedi"
    assert v._btn_tasma.isHidden()


def test_GIZLENEN_araclar_menude_ve_calisiyor(cubuklu, qapp):
    """Gizlenen araç kaybolmamalı: menüde, çubuktaki sırasıyla ve durumuyla;
    girdisi düğmesine basılmış gibi çalışıyor."""
    v = cubuklu(250)
    gizli = [w for w in _araclar(v) if w.isHidden()]
    assert v._btn_invert in gizli and v._btn_zoom_in in gizli, \
        "250 px'de araçlar gizlenmemiş, kapı boş"
    v._btn_invert.setChecked(True)
    v._btn_tasma.click()
    try:
        eylemler = v._tasma_menusu.actions()
        assert [e.text() for e in eylemler] == \
            [w.toolTip() or w.text() for w in gizli]
        for e, w in zip(eylemler, gizli):
            assert e.isEnabled() == w.isEnabled(), e.text()
            assert e.isChecked() == w.isChecked(), e.text()

        eylemler[gizli.index(v._btn_invert)].trigger()
        assert not v._btn_invert.isChecked() and not v._invert_colors
        eski = v._zoom
        eylemler[gizli.index(v._btn_zoom_in)].trigger()
        assert v._zoom > eski, "yakınlaştır girdisi yakınlaştırmadı"
    finally:
        v._tasma_menusu.close()


def test_ETIKET_UZAYINCA_cubuk_yeniden_sigdiriliyor(cubuklu, qapp):
    """Sayfa numarası uzayınca (1 / 120 -> 120 / 120) etiket genişliyor.

    Bölmenin boyu değişmiyor, yani tek tetik `_update_nav`. Ölçüt yine
    sınırdan: bölme, kısa etiketle tam sığan genişlikte.
    """
    v = cubuklu(3000)
    tam = _cubuk(v).layout().minimumSize().width()
    v.resize(tam, 400)
    qapp.processEvents()
    assert not any(w.isHidden() for w in _araclar(v)), \
        "tam sığan çubukta araç gizli"
    eski = v._lbl_page.minimumSizeHint().width()
    v._current_page = v._page_count - 1
    v._update_nav()
    qapp.processEvents()
    assert v._lbl_page.minimumSizeHint().width() > eski, "etiket uzamadı, kapı boş"
    assert v._lbl_page.width() >= v._lbl_page.minimumSizeHint().width(), \
        "sayfa etiketi kırpıldı"
    _cakisma_yok(v)

    # En dar bölmede büyük belgenin etiketi: gezinme bile tam sığmıyor. Qt
    # açığı en büyük ögeden, etiketten alıyor; etiket kırpılabilir ama
    # düğmeler üst üste binmemeli (etikete sabit genişlik verilirse biner).
    v._lbl_page.setText("Sayfa 1000 / 1000  (123456 KB)")
    v.resize(v.minimumWidth(), 400)
    qapp.processEvents()
    _cakisma_yok(v)
    assert v._lbl_page.width() < v._lbl_page.minimumSizeHint().width(), \
        "etiket sığdı, en dar durum oluşmadı, kapı boş"
