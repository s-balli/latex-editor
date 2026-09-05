"""Arka plan PDF render — pipeline, işçi ve viewer uçtan uca testleri.

Senkron render hızlı scroll'da UI'yi kilitliyordu; işçi kendi
pypdfium2 handle'ını açar (pdfium handle'ları iş parçacıkları arasında
paylaşılamaz), sonuçlar gen/scale/invert ile damgalanır, bayat olanlar
UI tarafında düşürülür.
"""

import time

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pypdfium2")

from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
import pypdfium2

from gui.pdf_render import render_page_to_qimage
from gui.pdf_render_worker import PdfRenderWorker
from gui.pdfium_lock import pdfium_lock


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _tiny_pdf(tmp_path, name="mini.pdf") -> str:
    doc = pypdfium2.PdfDocument.new()
    doc.new_page(200, 300)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return str(p)


def _spin(qapp, cond, timeout=10.0):
    """Koşul sağlanana kadar event loop'u döndür (async sinyaller işlesin)."""
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    return cond()


# --- Pipeline ---


def test_render_qimage_boyut_ve_format(tmp_path):
    with pdfium_lock:
        doc = pypdfium2.PdfDocument(_tiny_pdf(tmp_path))
        img = render_page_to_qimage(doc[0], 1.0)
        doc.close()
    assert isinstance(img, QImage) and not img.isNull()
    assert (img.width(), img.height()) == (200, 300)


def test_render_qimage_invert_pikseli_degistirir(tmp_path):
    with pdfium_lock:
        doc = pypdfium2.PdfDocument(_tiny_pdf(tmp_path))
        normal = render_page_to_qimage(doc[0], 1.0, invert=False)
        ters = render_page_to_qimage(doc[0], 1.0, invert=True)
        doc.close()
    assert normal.pixel(100, 150) != ters.pixel(100, 150)


# --- İşçi ---


def test_worker_arka_planda_render_eder(qapp, tmp_path):
    path = _tiny_pdf(tmp_path)
    w = PdfRenderWorker()
    results = []
    w.rendered.connect(lambda *a: results.append(a))
    w.start()
    try:
        w.open_document(path, 7)             # gen=7: rastgele, damga testi
        w.submit(7, 0, 1.0, False)
        assert _spin(qapp, lambda: bool(results)), "render sonucu gelmedi"
        gen, idx, scale, invert, img = results[0]
        assert (gen, idx, scale, invert) == (7, 0, 1.0, False)
        assert not img.isNull() and (img.width(), img.height()) == (200, 300)
    finally:
        w.stop()
        w.wait(4000)


def test_worker_dedup_ayni_sayfanin_son_istegi_kazanir(qapp, tmp_path):
    """Hızlı scroll'da ara ölçekler boşa render edilmesin: aynı sayfaya
    ardışık submit'lerden yalnız son ölçek koşar."""
    path = _tiny_pdf(tmp_path)
    w = PdfRenderWorker()
    scales = []
    w.rendered.connect(lambda gen, idx, scale, inv, img: scales.append(scale))
    w.start()
    try:
        w.open_document(path, 1)
        w.submit(1, 0, 1.0, False)
        w.submit(1, 0, 2.0, False)           # ilki render'a başlamadan ezildi
        assert _spin(qapp, lambda: bool(scales)), "render sonucu gelmedi"
        assert scales == [2.0] or scales == [1.0, 2.0]  # dedup: 1.0 en fazla bir kez
        assert scales[-1] == 2.0
    finally:
        w.stop()
        w.wait(4000)


def test_worker_open_document_bekleyenleri_temizler(qapp, tmp_path):
    path = _tiny_pdf(tmp_path)
    w = PdfRenderWorker()
    got = []
    w.rendered.connect(lambda *a: got.append(a))
    w.start()
    try:
        w.open_document(path, 1)
        w.submit(1, 0, 1.0, False)
        # hemen yeni doküman: eski gen'in işi düşmeli
        w.open_document(path, 2)
        w.submit(2, 0, 1.0, False)
        assert _spin(qapp, lambda: len(got) >= 1)
        assert all(r[0] == 2 for r in got), f"bayat gen sızdı: {[r[0] for r in got]}"
    finally:
        w.stop()
        w.wait(4000)


# --- Viewer uçtan uca ---


def test_viewer_async_render_ve_bayat_zoom_dusurme(qapp, tmp_path):
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES

    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert v.load_pdf(_tiny_pdf(tmp_path))
        gen = v._render_gen
        assert gen == 1

        def _has_pixmap():
            pm = v._page_labels[0].pixmap()
            return pm is not None and not pm.isNull()

        assert _spin(qapp, _has_pixmap), "ilk render gelmedi"
        # Eskiden burada `v._cache_bytes > 0` vardı; o sayaç yalnız hiç
        # okunmayan bir sözlüğü besliyordu (2026-08-31, F2 ile kaldırıldı).
        # "Render gerçekten oldu" iddiasını label'ın kendisi taşıyor.
        assert v._page_labels[0].pixmap().width() > 0

        # Zoom: label temizlenir; eski ölçekli in-flight sonuç düşürülmeli,
        # yenisi gelmeli
        v.zoom_in()
        v._page_labels[0].setPixmap(type(v._page_labels[0].pixmap())())
        assert _spin(qapp, _has_pixmap), "zoom sonrası render gelmedi"
        assert v._render_gen == gen   # zoom gen değiştirmez; scale damgası düşürür
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


# --- Açılışı kaçıran işçi nesil boyunca ölü kalmasın ---


def _tek_sayfalik_pdf(tmp_path, ad="a.pdf"):
    icerik = b"BT /F1 12 Tf 50 50 Td (x) Tj ET"
    nesneler = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(icerik)).encode() + b">>stream\n" + icerik +
        b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    yerler = []
    for i, n in enumerate(nesneler, start=1):
        yerler.append(len(out))
        out += b"%d 0 obj" % i + n + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(nesneler) + 1)
    for y in yerler:
        out += b"%010d 00000 n \n" % y
    out += (b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(nesneler) + 1, xref))
    yol = tmp_path / ad
    yol.write_bytes(bytes(out))
    return str(yol)


def test_acilisi_kaciran_isci_yeniden_deniyor(tmp_path, monkeypatch):
    """Windows'ta derleme PDF'i YERİNDE yeniden yazıyor.

    O ana denk gelen açılış başarısız oluyor ve `_doc_key` zaten atandığı
    için BİR DAHA denenmiyordu: işçi o nesil boyunca ölü kalıyor, kullanıcı
    bir sonraki derlemeye kadar boş sayfa görüyordu (dış güvenlik raporu,
    kod okuması maddesi).

    `_doc_key`i boş bırakmak çözüm DEĞİL: bekleme koşulu
    `_wanted == _doc_key` olduğu için işçi %100 CPU ile döner.
    """
    from gui.pdf_render_worker import PdfRenderWorker

    yol = _tek_sayfalik_pdf(tmp_path)
    w = PdfRenderWorker()

    gercek_open = open
    kalan = {"hata": 1}

    def sahte_open(dosya, *a, **kw):
        if str(dosya) == yol and kalan["hata"] > 0:
            kalan["hata"] -= 1
            raise OSError("yazma sirasinda yakalandi")
        return gercek_open(dosya, *a, **kw)

    monkeypatch.setattr("builtins.open", sahte_open)

    w._wanted = (yol, 1)
    w._swap_document((yol, 1))
    assert w._doc is None                   # ilk deneme kacti
    assert w._doc_key == (yol, 1)           # anahtar yine atandi (spin olmasin)
    assert w._acilis_denemesi == 1

    # İş geldiğinde yeniden denenmeli
    w._swap_document((yol, 1))
    assert w._doc is not None, "isci nesil boyunca olu kaldi"
    assert w._acilis_denemesi == 0          # basarida sayac sifirlanir

    with pdfium_lock:
        w._doc.close()


def test_yeniden_deneme_sinirli(tmp_path, monkeypatch):
    """Kalıcı olarak bozuk dosyada sonsuza dek denenmemeli."""
    from gui.pdf_render_worker import PdfRenderWorker, _MAX_ACILIS_DENEMESI

    yol = _tek_sayfalik_pdf(tmp_path)
    w = PdfRenderWorker()

    def hep_hata(dosya, *a, **kw):
        raise OSError("hep bozuk")

    monkeypatch.setattr("builtins.open", hep_hata)
    for _ in range(_MAX_ACILIS_DENEMESI + 3):
        w._swap_document((yol, 1))
    assert w._acilis_denemesi >= _MAX_ACILIS_DENEMESI


def test_yeni_nesilde_sayac_sifirlaniyor(tmp_path, monkeypatch):
    """Bir nesilde tükenen deneme hakkı sonrakini kilitlememeli."""
    from gui.pdf_render_worker import PdfRenderWorker

    yol = _tek_sayfalik_pdf(tmp_path)
    w = PdfRenderWorker()

    monkeypatch.setattr("builtins.open",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("x")))
    for _ in range(5):
        w._swap_document((yol, 1))
    assert w._acilis_denemesi > 0

    tukenen = w._acilis_denemesi

    # Yeni nesil de HATA versin: basari yolu sayaci zaten sifirladigi icin
    # basarili acilisla olcmek bos olurdu (kasitli bozmada goruldu).
    w._swap_document((yol, 2))
    assert w._acilis_denemesi == 1, (
        "yeni nesilde sayac sifirlanmadi: %d (onceki nesilde %d)"
        % (w._acilis_denemesi, tukenen))

    monkeypatch.undo()
    w._swap_document((yol, 3))
    assert w._doc is not None
    assert w._acilis_denemesi == 0
    with pdfium_lock:
        w._doc.close()


# --- İşçi dururken kendi doküman handle'ını kapatmalı ---
#
# `_run_loop` `_stop` görünce dönüyordu ve dokümanı kapatan TEK yer
# `_swap_document`; o da artık hiç çalışmayacağı için handle AÇIK kalıyordu.
# Kapatmayı pypdfium2'nin weakref finalizer'ı devralıyor: KEYFİ bir thread'de
# ve `pdfium_lock` TUTULMADAN. Ölçüldü (2026-09-05): stres altında 12
# kapanışın 12'si kilitsiz ve hepsi başka bir thread pdfium içindeyken.
# Kural `gui/pdfium_lock.py`de yazılı: belge açma/kapama da kilit ister;
# kilitsiz pdfium çağrısı bu depoda zaten CI'da heap bozulmasına yol açmıştı.


class _SahteBelge:
    """close() çağrıldığında kilidin TUTULUYOR olduğunu kaydeden sahte doküman.

    Gerçek `PdfDocument` yerine bu kullanılıyor: pypdfium2'nin kapatma iç
    yapısı sürümden sürüme değişiyor (4.x'te ham `FPDF_CloseDocument`, 5.x'te
    `_close_impl`), oysa sınanmak istenen şey BİZİM kod yolumuz.
    """

    def __init__(self):
        self.kapandi = False
        self.kilit_vardi = None

    def close(self):
        self.kapandi = True
        self.kilit_vardi = pdfium_lock._is_owned()


def test_stop_sonrasi_isci_dokumani_kapaniyor(qapp, tmp_path):
    """Durdurulan işçi handle'ı finalizer'a bırakmamalı."""
    w = PdfRenderWorker()
    sonuc = []
    w.rendered.connect(lambda *a: sonuc.append(a))
    w.start()
    try:
        w.open_document(_tiny_pdf(tmp_path), 1)
        w.submit(1, 0, 1.0, False)
        assert _spin(qapp, lambda: bool(sonuc)), "render sonucu gelmedi"
        assert w._doc is not None, "ön koşul: işçi render ederken doküman açık"
    finally:
        w.stop()
        assert w.wait(6000), "işçi durmadı"
    assert w._doc is None, "durdurulan işçi dokümanı açık bıraktı"


def test_kapatma_pdfium_kilidi_altinda(tmp_path):
    """Kapatma `pdfium_lock` TUTULARAK yapılmalı (kuralın kendisi)."""
    # Kapının kör kalmaması için: bu sınama `_is_owned`a dayanıyor, yoksa
    # sessizce hep None okuyup her mutantı hayatta bırakırdı.
    assert hasattr(pdfium_lock, "_is_owned"), "RLock._is_owned kayboldu"
    assert not pdfium_lock._is_owned(), "ön koşul: kilit çağıranda olmamalı"

    w = PdfRenderWorker()
    sahte = _SahteBelge()
    w._doc = sahte
    w._doc_key = ("x.pdf", 1)
    w._run_loop = lambda: None      # run()'ın finally'si sınanıyor
    w.run()                         # start() değil: saf Python yolu

    assert sahte.kapandi, "run() bittiğinde doküman kapatılmadı"
    assert sahte.kilit_vardi is True, "doküman pdfium_lock TUTULMADAN kapatıldı"
    assert w._doc is None


def test_run_loop_istisnayla_biterse_de_kapaniyor():
    """Beklenmedik istisna handle'ı arkada bırakmamalı."""
    w = PdfRenderWorker()
    sahte = _SahteBelge()
    w._doc = sahte
    w._doc_key = ("x.pdf", 1)

    def patlayan():
        raise RuntimeError("kasitli patlama")

    w._run_loop = patlayan
    with pytest.raises(RuntimeError):
        w.run()
    assert sahte.kapandi, "istisna yolunda doküman kapatılmadı"
    assert sahte.kilit_vardi is True
    assert w._doc is None


def test_hic_dokuman_acmayan_isci_temiz_duruyor(qapp):
    """Kapatılacak bir şey yokken durma yolu istisna atmamalı."""
    w = PdfRenderWorker()
    w.start()
    assert _spin(qapp, lambda: w.isRunning())
    w.stop()
    assert w.wait(6000), "işçi durmadı"
    assert w._doc is None


def test_acilisi_basarisiz_isci_temiz_duruyor(qapp, tmp_path):
    """`_doc` None kalmışken durma yolu yine sorunsuz olmalı."""
    w = PdfRenderWorker()
    w.start()
    try:
        w.open_document(str(tmp_path / "yok-boyle-dosya.pdf"), 1)
        w.submit(1, 0, 1.0, False)
        assert _spin(qapp, lambda: w._doc_key is not None)
    finally:
        w.stop()
        assert w.wait(6000), "işçi durmadı"
    assert w._doc is None


def test_calisan_isci_dokumani_erken_kapatmiyor(qapp, tmp_path):
    """AŞIRI DÜZELTME KAPISI: kapatma yalnız DURMA yolunda olmalı.

    "Her ihtimale karşı" döngü içinde kapatan bir düzeltme burada kırılır:
    ikinci render hiç gelmez.
    """
    w = PdfRenderWorker()
    sonuc = []
    w.rendered.connect(lambda *a: sonuc.append(a))
    w.start()
    try:
        w.open_document(_tiny_pdf(tmp_path), 1)
        w.submit(1, 0, 1.0, False)
        assert _spin(qapp, lambda: bool(sonuc)), "ilk render gelmedi"
        assert w._doc is not None, "işçi çalışırken doküman kapatılmış"
        w.submit(1, 0, 2.0, False)
        assert _spin(qapp, lambda: len(sonuc) >= 2), "ikinci render gelmedi"
        assert w._doc is not None
    finally:
        w.stop()
        w.wait(6000)


def test_viewer_shutdown_isci_dokumanini_kapatiyor(qapp, tmp_path):
    """Uçtan uca: uygulama kapanış yolu handle bırakmamalı."""
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES

    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert v.load_pdf(_tiny_pdf(tmp_path))
        assert _spin(qapp, lambda: v._render_worker._doc is not None), \
            "ön koşul: yükleme sonrası işçi dokümanı açık"
        rw = v._render_worker
        v.shutdown()
        assert not rw.isRunning()
        assert rw._doc is None, "shutdown sonrası işçi dokümanı açık kaldı"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()
