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


# =====================================================================
# F3. Arama çubuğunun ikonları tema değişiminde tazelenmiyordu
#
# Ok ve kapat ikonları `_setup_ui` içindeki yerel bir kapanışta bir kez
# çiziliyordu; komşuları (yer imleri, çift sayfa, sığdır) apply_theme'de
# yeniden çizildiği için tazeydi, bu üçü ESKİ temanın fg_muted'ıyla
# kalıyordu.
#
# ÖLÇÜLDÜ (2026-09-08, ikonun opak pikselinden okundu):
#   yedi temanın 42 sıralı çiftinin 42'sinde de ikon bayat kalıyor
#   23 çiftte karşıtlık 3:1 eşiğinin altına düşüyor
#   en kötü: light -> nord, 1.67:1 (doğru renkle 3.34:1)
#   light -> dark: 2.31:1 (4.57:1 olmalıydı)
#
# Kapılar ikonun PİKSELİNDEN okuyor: kusur "çizim bir daha yapılmıyor"
# olduğu için stylesheet metnine bakmak hiçbir şey yakalamazdı (stiller
# zaten tazeleniyordu, ikon değil).
# =====================================================================

ARAMA_DUGMELERI = ("_search_prev_btn", "_search_next_btn", "_search_close_btn")


def _ikon_rengi(btn):
    """İkonun en opak pikselinin rengi (kenar yumuşatması hariç)."""
    img = btn.icon().pixmap(20, 20).toImage()
    en_iyi, en_alfa = None, 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > en_alfa:
                en_alfa, en_iyi = c.alpha(), c
    if en_iyi is None or en_alfa < 200:
        return None
    return en_iyi.name()


@pytest.mark.parametrize("hedef", ["dark", "nord", "monokai",
                                   "solarized_light"])
def test_arama_ikonlari_tema_degisiminde_TAZELENIYOR(qapp, hedef):
    """Kırılırsa Ctrl+F çubuğundaki ok ve kapat ikonları önceki temanın
    renginde kalıyor ve karşıtlık eşiğin altına düşüyor."""
    v = PdfViewer(theme=dict(THEMES["light"]))
    try:
        v.apply_theme(dict(THEMES[hedef]))
        bekleyen = THEMES[hedef]["fg_muted"].lower()
        for attr in ARAMA_DUGMELERI:
            assert _ikon_rengi(getattr(v, attr)) == bekleyen, attr
    finally:
        v.shutdown()
        v.deleteLater()


def test_arama_ikonlari_KURULUSTA_ciziliyor(qapp):
    """İlk çizim de tazeleme yolundan geliyor (_setup_ui sonunda
    apply_theme çağırıyor); düşerse düğmeler hiç ikonsuz kalır."""
    v = PdfViewer(theme=dict(THEMES["dark"]))
    try:
        for attr in ARAMA_DUGMELERI:
            btn = getattr(v, attr)
            assert not btn.icon().isNull(), attr
            assert _ikon_rengi(btn) == THEMES["dark"]["fg_muted"].lower(), attr
    finally:
        v.shutdown()
        v.deleteLater()


def test_UC_IKON_birbirinden_FARKLI(qapp):
    """Aşırı düzeltme kapısı: üçüne aynı ikonu vermek renk kapılarını
    geçer ama yukarı ok, aşağı ok ve kapat çarpısı ayırt edilemez olur."""
    v = PdfViewer(theme=dict(THEMES["dark"]))
    try:
        gorseller = [getattr(v, a).icon().pixmap(16, 16).toImage()
                     for a in ARAMA_DUGMELERI]
        assert gorseller[0] != gorseller[1], "önceki/sonraki okları aynı"
        assert gorseller[0] != gorseller[2], "önceki oku ile kapat aynı"
        assert gorseller[1] != gorseller[2], "sonraki oku ile kapat aynı"
    finally:
        v.shutdown()
        v.deleteLater()


class TestKaydetDugmesiGenisligi:
    r""""Farklı Kaydet" düğmesi ETİKETİNİ kırpmamalı.

    ÖLÇÜLDÜ (2026-09-09, gerçek pencere + Segoe UI; offscreen'de yazı tipi
    olmadığı için bu ölçüm ancak gerçek platformda yapılabiliyor): sabit
    110 px Türkçe etikete yetmiyor, düğme "💾 Farklı Kayd" görünüyordu.
    1280/1366/1600/1920'nin dördünde de aynı, yani pencere boyutuyla ilgisi
    yok; İngilizce "Save As" sığdığı için kusur uygulamanın KENDİ dilinde
    görünüyordu.

    Kapı yazı tipinden BAĞIMSIZ: piksel sayısına değil, "sabit genişlik
    etiketin istediğinden küçük değil" bağıntısına bakıyor. Böylece
    offscreen CI'da da anlamlı kalıyor.
    """

    def _viewer(self, qapp, tema="dark"):
        v = PdfViewer(theme=THEMES[tema])
        v.apply_theme(THEMES[tema])
        qapp.processEvents()
        return v

    def test_SABIT_genislik_etiketten_kucuk_degil(self, qapp):
        v = self._viewer(qapp)
        try:
            b = v._btn_save
            assert b.maximumWidth() >= b.sizeHint().width(), (
                "düğme %d px sabit, etiket %d px istiyor: '%s' kırpılır"
                % (b.maximumWidth(), b.sizeHint().width(), b.text()))
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_TABAN_genislik_korunuyor(self, qapp):
        """Aşırı düzeltme kapısı: kısa etikette düğme daralmamalı, çubuğun
        hizası dile göre oynamasın.

        Ölçüt KISA bir etiketle kuruluyor: yazı tipi ne olursa olsun tek
        harfin istediği genişlik tabanın altında kalır, yani kapı ortamdan
        bağımsız.
        """
        v = self._viewer(qapp)
        try:
            v._btn_save.setText("X")
            v.apply_theme(THEMES["dark"])
            qapp.processEvents()
            assert v._btn_save.minimumWidth() >= 110
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()

    def test_ETIKET_UZAYINCA_genislik_yeniden_olculuyor(self, qapp):
        """Genişlik stil uygulandıktan SONRA hesaplanıyor.

        Kurulum anındaki `sizeHint` stil (dolgu) uygulanmadan önceki değer;
        gerçek kusur da buydu. Kapı UZUN bir etiketle ölçüyor: hesaplama
        `apply_theme`ten kalkarsa sabit genişlik eski değerinde kalır ve
        etiket kırpılır. Uzun metin her yazı tipinde uzun olduğu için kapı
        offscreen'de de anlamlı.
        """
        v = self._viewer(qapp, "dark")
        try:
            b = v._btn_save
            eski = b.maximumWidth()
            b.setText("Farklı Kaydet ve epeyce uzun bir etiket daha")
            v.apply_theme(THEMES["dark"])
            qapp.processEvents()
            assert b.maximumWidth() > eski, "genişlik yeniden ölçülmemiş"
            assert b.maximumWidth() >= b.sizeHint().width()
        finally:
            v.shutdown()
            v.deleteLater()
            qapp.processEvents()
