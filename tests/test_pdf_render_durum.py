"""PdfViewer render mixin: başarısız yükleme durumu ve yer tutucu stili.

İki gerçek kusur bu kapıların yokluğundan geçti (2026-09-05):

F1. `load_pdf` hata yolu yalnız `_clear_pages()` çağırıyordu; o da sadece
    etiketleri ve yerleşimi atıyor. ÖNCEKİ belgenin durumu kalıyordu:
    sayfa sayacı "Sayfa 1 / 3" demeye devam ediyor ve "Farklı Kaydet" etkin
    kalıp ÖNCEKİ PDF'i kaydediyordu (ölçüldü: 799 baytlık önceki belge
    kopyalanıyordu). Tam temizliği yapan `clear()` metodu vardı ama
    çağrılmıyordu.

F2. Yer tutucu stili beş yerde yazılı ve iki farklı tema anahtarı
    kullanıyordu: `_render.py` `border_separator`, `_ui_setup.apply_theme`
    `border_input`. Kenarlık, tema yeniden uygulanır uygulanmaz renk
    değiştiriyordu (yedi temanın altısında).
"""

import pathlib
import re

import pytest

try:
    import pypdfium2
    from PyQt6.QtWidgets import QApplication
    from gui.pdf_viewer import PdfViewer
    from gui.pdfium_lock import pdfium_lock
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / pypdfium2 / gui gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def pdfler(tmp_path):
    """(geçerli 3 sayfalık PDF, bozuk dosya) yolları."""
    iyi = tmp_path / "onceki.pdf"
    with pdfium_lock:
        doc = pypdfium2.PdfDocument.new()
        for _ in range(3):
            doc.new_page(200, 300)
        doc.save(str(iyi))
        doc.close()
    bozuk = tmp_path / "bozuk.pdf"
    bozuk.write_bytes(b"bu bir PDF degil")
    return str(iyi), str(bozuk)


def _durum(v):
    """Belge durumunu taşıyan alanlar."""
    return {
        "pdf_var": v._pdf is not None,
        "page_count": v._page_count,
        "pdf_path": v._pdf_path,
        "kaydet_etkin": v._btn_save.isEnabled(),
        "current_page": v._current_page,
    }


def test_durum_kapisi_GERCEKTEN_olcuyor(qapp, pdfler):
    """`_durum` gerçekten durum okumalı.

    Boş sözlük dönseydi aşağıdaki tüm karşılaştırmalar bedava geçerdi;
    mutasyonla ölçüldü.
    """
    iyi, _bozuk = pdfler
    taze = PdfViewer(theme=THEMES["dark"])
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(iyi)
        assert _durum(v) != _durum(taze), "_durum iki durumu ayırt etmiyor"
        assert _durum(v)["page_count"] == 3
        assert _durum(taze)["page_count"] == 0
    finally:
        v.shutdown()
        taze.shutdown()


# --- F1: başarısız yükleme durumu ---

def test_bozuk_yukleme_ONCEKI_belgeyi_birakmiyor(qapp, pdfler):
    """Kırılırsa: hata yolu tam temizlik yapmıyor demektir; `clear()`
    çağrıldığından emin olun.

    Ölçüt TAZE VIEWER: başarısız yüklemeden sonraki durum, hiç PDF
    yüklenmemiş bir viewer'ınkiyle aynı olmalı.
    """
    iyi, bozuk = pdfler
    taze = PdfViewer(theme=THEMES["dark"])
    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert v.load_pdf(iyi) is True
        assert v._page_count == 3
        assert v.load_pdf(bozuk) is False
        assert _durum(v) == _durum(taze), (
            "başarısız yüklemeden sonra durum temiz değil:\n"
            "  bozuk sonrası: %s\n  taze viewer   : %s"
            % (_durum(v), _durum(taze)))
    finally:
        v.shutdown()
        taze.shutdown()


def test_bozuk_yukleme_sonrasi_KAYDET_devre_disi(qapp, pdfler):
    """En somut sonuç: düğme etkin kalırsa ÖNCEKİ PDF kaydedilirdi."""
    iyi, bozuk = pdfler
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(iyi)
        assert v._btn_save.isEnabled()
        v.load_pdf(bozuk)
        assert not v._btn_save.isEnabled()
        assert v._pdf_path == "", \
            "_pdf_path önceki dosyayı gösteriyor: %r" % v._pdf_path
    finally:
        v.shutdown()


def test_olmayan_dosya_mevcut_belgeyi_BOZMUYOR(qapp, pdfler, tmp_path):
    """Karşı durum: erken dönüş yolu temizlik yapmamalı.

    Bu olmadan F1 düzeltmesi "her başarısızlıkta her şeyi sil" hâline
    gelebilir ve açık belge boşuna kapanırdı.
    """
    iyi, _bozuk = pdfler
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(iyi)
        onceki = _durum(v)
        assert v.load_pdf(str(tmp_path / "yok.pdf")) is False
        assert _durum(v) == onceki
    finally:
        v.shutdown()


def test_bozuk_sonrasi_gecerli_PDF_yeniden_yuklenebiliyor(qapp, pdfler):
    iyi, bozuk = pdfler
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(bozuk)
        assert v.load_pdf(iyi) is True
        assert v._page_count == 3
        assert v._btn_save.isEnabled()
        assert v._pdf_path == iyi
    finally:
        v.shutdown()


def test_ust_uste_bozuk_yukleme_mesaj_YIGMIYOR(qapp, pdfler):
    iyi, bozuk = pdfler
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(iyi)
        v.load_pdf(bozuk)
        v.load_pdf(bozuk)
        assert len(v._page_labels) == 1, \
            "mesaj etiketi yığıldı: %d" % len(v._page_labels)
    finally:
        v.shutdown()


# --- F2: yer tutucu stili kurulum ile apply_theme'de aynı ---

@pytest.mark.parametrize("tema", sorted(THEMES))
def test_yer_tutucu_stili_kurulum_ve_apply_theme_de_AYNI(qapp, pdfler, tema):
    """Kırılırsa: iki yol farklı tema anahtarı kullanıyor demektir."""
    iyi, _bozuk = pdfler
    v = PdfViewer(theme=THEMES[tema])
    try:
        v.load_pdf(iyi)
        kurulum = v._page_labels[0].styleSheet()
        v.apply_theme(THEMES[tema])
        assert v._page_labels[0].styleSheet() == kurulum, (
            "yer tutucu stili tema yeniden uygulanınca değişti:\n"
            "  kurulum: %s\n  sonra  : %s"
            % (kurulum, v._page_labels[0].styleSheet()))
    finally:
        v.shutdown()


def test_cift_sayfa_ve_zoom_yollari_da_ayni_stili_uretiyor(qapp, pdfler):
    """Aynı stil üç yerde yazılı; üçü birden aynı kalmalı."""
    iyi, _bozuk = pdfler
    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.load_pdf(iyi)
        tek = v._page_labels[0].styleSheet()
        v._toggle_dual_page(True)
        assert v._page_labels[0].styleSheet() == tek, "çift sayfa yolu ayrışmış"
        v._toggle_dual_page(False)
        v._update_page_sizes()
        assert v._page_labels[0].styleSheet() == tek, "zoom yolu ayrışmış"
    finally:
        v.shutdown()


_KENARLIK_KALIP = re.compile(
    r"bg_pdf_placeholder'\]\}; border: 1px solid \{[^\[]*\['(\w+)'\]")


def _kenarlik_anahtarlari(metin: str) -> set:
    """Metindeki yer tutucu stillerinin kullandığı kenarlık anahtarları."""
    return {m.group(1) for m in _KENARLIK_KALIP.finditer(metin)}


def test_yer_tutucu_kenarlik_anahtari_IKI_DOSYADA_ayni():
    """Statik kapı: `_render.py` ile `_ui_setup.py` aynı anahtarı kullanmalı.

    Widget kurmadan da ayrışmayı yakalar; yeni bir yazım yeri eklenirse
    (şu an beş tane) burada görünür.
    """
    kok = pathlib.Path(__file__).resolve().parents[1] / "desktop" / "gui"
    anahtarlar = {}
    for ad in ("pdf_viewer_mixins/_render.py", "pdf_viewer_mixins/_ui_setup.py"):
        metin = (kok / ad).read_text(encoding="utf-8")
        for k in _kenarlik_anahtarlari(metin):
            anahtarlar.setdefault(k, []).append(ad)

    assert anahtarlar, "yer tutucu stili hiç bulunamadı, tarama bozuk olabilir"
    assert len(anahtarlar) == 1, \
        "yer tutucu kenarlığı farklı anahtarlarla yazılıyor: %s" % anahtarlar


def test_kenarlik_kapisi_GERCEKTEN_yakaliyor():
    """Kapının boş koşmadığının kanıtı: F2'nin birebir kendisi.

    Kapının KENDİ tarayıcısı kullanılıyor; ayrı bir kopya olsaydı tarayıcı
    körelince bu test yine geçerdi (mutasyonla ölçüldü).
    """
    ornek = (
        "background: {self._theme['bg_pdf_placeholder']}; "
        "border: 1px solid {self._theme['border_separator']}; "
        "background: {t['bg_pdf_placeholder']}; "
        "border: 1px solid {t['border_input']};")
    assert _kenarlik_anahtarlari(ornek) == {"border_separator", "border_input"}
    assert _kenarlik_anahtarlari("alakasiz metin") == set()
