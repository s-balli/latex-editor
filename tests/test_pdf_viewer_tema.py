"""PdfViewer tema kapıları: mesaj etiketi ve kaydırma alanı zemini.

İki gerçek kusur bu kapıların yokluğundan geçti (2026-09-05):

F1. `_show_message` etiketi `_page_labels`'a giriyor ve pixmap'i hiç olmuyor.
    `apply_theme`'in "pixmap'siz etiket = sayfa yer tutucusu" varsayımı onu
    her tema değişiminde gri bir kutuya çeviriyordu: renk, punto ve dolgu
    kayboluyordu (ölçüldü, yedi temada da).

F2. `QScrollArea {{ background: ... }}` kuralı görünür alanı boyamıyor;
    görünen alanı `_pages_widget` kaplıyor ve onun stili yoksa küresel
    `QWidget {{ background: bg_primary }}` kazanıyor. Sonuç: temanın
    `bg_pdf_scroll` rengi yedi temanın hiçbirinde görünmüyordu ve ters
    çevirme modundaki siyah çerçeve de gelmiyordu (render'dan ölçüldü).

Zemin kapısı RENDER'dan ölçüyor, stylesheet metnine bakmıyor: kusurun tamamı
"yazılan kural ekrana yansımıyor" olduğu için metin denetimi hiçbir şey
yakalamazdı.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QLabel
    from gui.pdf_viewer import PdfViewer
    from gui.stylesheet import build_stylesheet
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def kuresel_stil(qapp):
    """Küresel stylesheet'i kur ve testten sonra GERİ AL.

    Bırakılırsa aynı oturumdaki diğer testler başka bir temayla koşar.
    """
    onceki = qapp.styleSheet()
    yield lambda t: qapp.setStyleSheet(build_stylesheet(t))
    qapp.setStyleSheet(onceki)


def _baskin(w):
    """Widget'ın render'ındaki en çok görülen renk."""
    img = w.grab().toImage()
    s = {}
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y).name()
            s[c] = s.get(c, 0) + 1
    return sorted(s.items(), key=lambda x: -x[1])[0][0]


# --- F1: mesaj etiketi yer tutucudan ayrı ---

@pytest.mark.parametrize("hedef", sorted(THEMES))
def test_mesaj_etiketi_yer_tutucu_kutusuna_DONMUYOR(qapp, hedef):
    """Kırılırsa: `apply_theme`'in yer tutucu döngüsü mesaj etiketini de
    yakalıyor demektir; `_MESAJ_OZELLIGI` işaretini denetleyin."""
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v._show_message("PDF yok")
        etiket = v._page_labels[-1]
        v.apply_theme(THEMES[hedef])
        ss = etiket.styleSheet()
        assert "color: %s" % THEMES[hedef]["fg_label"] in ss, \
            "mesaj etiketi yeni temanın rengini almadı: %r" % ss
        assert "font-size" in ss and "padding" in ss, \
            "mesaj biçimi kayboldu: %r" % ss
        assert "background" not in ss, \
            "mesaj etiketi yer tutucu kutusuna döndü: %r" % ss
    finally:
        v.shutdown()
        v.deleteLater()


def test_gercek_yer_tutucu_HALA_yer_tutucu_stili_aliyor(qapp):
    """Karşı durum: işaretsiz pixmap'siz etiket yer tutucu olarak kalmalı.

    Bu olmadan F1 düzeltmesi "hiçbir etiketi boyama" hâline gelirdi ve kapı
    onu fark etmezdi.
    """
    v = PdfViewer(theme=THEMES["dark"])
    try:
        sahte = QLabel("")
        v._page_labels.append(sahte)
        v._pages_layout.addWidget(sahte)
        v.apply_theme(THEMES["light"])
        assert THEMES["light"]["bg_pdf_placeholder"] in sahte.styleSheet()
    finally:
        v.shutdown()
        v.deleteLater()


def test_ters_cevirme_mesaj_etiketini_EZMIYOR(qapp):
    """`_toggle_invert` de aynı listede geziyor; mesajı atlamalı."""
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v._show_message("PDF yok")
        etiket = v._page_labels[-1]
        v._btn_invert.setChecked(True)
        qapp.processEvents()
        assert "color: %s" % THEMES["dark"]["fg_label"] in etiket.styleSheet()
        v._btn_invert.setChecked(False)
        qapp.processEvents()
        assert "color: %s" % THEMES["dark"]["fg_label"] in etiket.styleSheet()
    finally:
        v.shutdown()
        v.deleteLater()


def test_mesaj_stili_TEK_KAYNAKTAN_geliyor(qapp):
    """`_show_message` ile `apply_theme` aynı stili üretmeli; ayrışırsa
    mesaj tema değişiminde biçim değiştirir."""
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v._show_message("PDF yok")
        kurulum = v._page_labels[-1].styleSheet()
        v.apply_theme(THEMES["dark"])
        assert v._page_labels[-1].styleSheet() == kurulum
    finally:
        v.shutdown()
        v.deleteLater()


# --- F2: kaydırma alanı zemini ekranda ---

@pytest.mark.parametrize("tema", sorted(THEMES))
def test_kaydirma_zemini_EKRANDA_temadan_geliyor(qapp, kuresel_stil, tema):
    """Kırılırsa: zemin yalnız `QScrollArea`'ya verilmiş demektir; görünen
    alanı `_pages_widget` kaplıyor, kural ona da gitmeli."""
    t = THEMES[tema]
    kuresel_stil(t)
    v = PdfViewer(theme=t)
    try:
        v.apply_theme(t)
        v.resize(300, 220)
        v.show()
        qapp.processEvents()
        assert _baskin(v._scroll) == t["bg_pdf_scroll"].lower(), \
            "ekrandaki zemin %s, istenen %s" % (_baskin(v._scroll),
                                                t["bg_pdf_scroll"])
    finally:
        v.shutdown()
        v.deleteLater()


def test_ters_cevirme_modunda_zemin_SIYAH(qapp, kuresel_stil):
    """Ters çevirme modunun yarısı buydu: sayfalar terse dönerken çevresi
    aydınlık kalıyordu."""
    t = THEMES["dark"]
    kuresel_stil(t)
    v = PdfViewer(theme=t)
    try:
        v.apply_theme(t)
        v.resize(300, 220)
        v.show()
        qapp.processEvents()
        v._btn_invert.setChecked(True)
        qapp.processEvents()
        assert _baskin(v._scroll) == "#000000"
        v._btn_invert.setChecked(False)
        qapp.processEvents()
        assert _baskin(v._scroll) == t["bg_pdf_scroll"].lower()
    finally:
        v.shutdown()
        v.deleteLater()


def test_ters_moddayken_tema_degisimi_SIYAHI_koruyor(qapp, kuresel_stil):
    kuresel_stil(THEMES["dark"])
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.apply_theme(THEMES["dark"])
        v.resize(300, 220)
        v.show()
        qapp.processEvents()
        v._btn_invert.setChecked(True)
        qapp.processEvents()
        v.apply_theme(THEMES["light"])
        qapp.processEvents()
        assert _baskin(v._scroll) == "#000000"
    finally:
        v.shutdown()
        v.deleteLater()


def test_zemin_kurali_sayfa_etiketlerine_SIZMIYOR(qapp):
    """Çıplak `background:` bildirimi çocuklara da geçerdi; kural ad ile
    sınırlı olmalı."""
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.apply_theme(THEMES["light"])
        assert "#pdfPagesWidget" in v._pages_widget.styleSheet(), \
            "zemin kuralı adla sınırlanmamış: %r" % v._pages_widget.styleSheet()
        etiket = QLabel("")
        v._page_labels.append(etiket)
        v._pages_layout.addWidget(etiket)
        v.apply_theme(THEMES["light"])
        assert THEMES["light"]["bg_pdf_placeholder"] in etiket.styleSheet()
    finally:
        v.shutdown()
        v.deleteLater()
