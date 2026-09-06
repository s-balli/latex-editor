"""Arka plan PDF araması — işçi ve viewer uçtan uca testleri.

Arama eskiden tüm dokümanı UI thread'inde senkron tarıyordu; işçi (latest-wins
tek slot, sayfa sayfa iptal) sonuçları yalnız koordinat olarak döndürür,
textpage'ler UI tarafında ihtiyaç anında yaratılır.
"""

import time

import pytest

pytest.importorskip("PyQt6")
pytest.importorskip("pypdfium2")

from PyQt6.QtWidgets import QApplication

from gui.pdf_search_worker import PdfSearchWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _pdf_with_text(pages_text: list[str], path: str) -> str:
    """Ham PDF yaz (TeX/pandoc gerektirmez, CI güvenli): sayfa başına bir
    metin satırı; pdfium'un arama/yazıtipi zinciri bunu okur."""
    objs = {}
    objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    n = len(pages_text)
    kids = " ".join(f"{4 + 2*i} 0 R" for i in range(n))
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()
    objs[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for i, txt in enumerate(pages_text):
        safe = txt.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        content = f"BT /F1 12 Tf 20 150 Td ({safe}) Tj ET".encode()
        objs[4 + 2*i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
                         f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2*i} 0 R >>").encode()
        objs[5 + 2*i] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + objs[num] + b"\nendobj\n"
    xref_pos = len(out)
    total = max(objs) + 1
    out += b"xref\n0 %d\n" % total + b"0000000000 65535 f \n"
    for num in range(1, total):
        out += b"%010d 00000 n \n" % offsets.get(num, 0)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (total, xref_pos)
    with open(path, "wb") as f:
        f.write(bytes(out))
    return path


def _spin(qapp, cond, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not cond() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    return cond()


# --- İşçi ---


def test_worker_search_eslesmeleri_bulur(qapp, tmp_path):
    path = _pdf_with_text(
        ["merhaba testalfa dunya", "baska sayfa", "tekrar testalfa gecti"],
        str(tmp_path / "s.pdf"))
    w = PdfSearchWorker()
    got = []
    w.found.connect(lambda sid, res: got.append((sid, res)))
    w.start()
    try:
        w.open_document(path, 3)
        w.search(3, "testalfa")
        assert _spin(qapp, lambda: bool(got)), "arama sonucu gelmedi"
        sid, res = got[0]
        assert sid == 3
        # (sayfa, baslangic, sayi) koordinat; textpage YOK
        assert [r[0] for r in res] == [0, 2]
        assert all(len(r) == 3 for r in res)
    finally:
        w.stop()
        w.wait(6000)


def test_worker_son_sorgu_kazanir(qapp, tmp_path):
    path = _pdf_with_text(["testalfa sayfada"], str(tmp_path / "s.pdf"))
    w = PdfSearchWorker()
    got = {}
    w.found.connect(lambda sid, res: got.update({sid: res}))
    w.start()
    try:
        w.open_document(path, 1)
        w.search(1, "olmayan-kelime")
        w.search(2, "testalfa")
        assert _spin(qapp, lambda: 2 in got), "son sorgunun sonucu gelmedi"
        assert got[2], "son sorgu eslesme bulmali"
    finally:
        w.stop()
        w.wait(6000)


# --- Viewer uçtan uca ---


def test_viewer_async_arama_ve_gecis(qapp, tmp_path):
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES

    path = _pdf_with_text(
        ["merhaba testalfa dunya", "baska sayfa", "tekrar testalfa gecti"],
        str(tmp_path / "v.pdf"))
    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert v.load_pdf(path)

        v._do_search("testalfa")
        assert _spin(qapp, lambda: bool(v._search_results)), "arama sonucu gelmedi"
        assert len(v._search_results) == 2
        assert v._search_count_label.text() == "1 / 2"

        v._search_next()
        assert v._search_count_label.text() == "2 / 2"

        # Yeni sorgu: bayat damga düşer, sonuç sıfırlanır
        v._do_search("olmayan-kelime")
        assert _spin(qapp, lambda: not v._search_results), "bos sonuc islenmedi"
        assert v._search_count_label.text() != "1 / 2"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


# =====================================================================
# Isci dururken pdfium belgesini KAPATMALI (2026-09-06)
#
# `_run_loop` stop gorunce donuyor ve dokumani kapatan TEK yer
# `_swap_document`; o da artik hic calismayacagi icin handle ACIK
# KALIYORDU. Kapatmayi pypdfium2'nin weakref finalizer'i devraliyor,
# GC'nin denk geldigi thread'de ve `pdfium_lock` TUTULMADAN. pdfium thread
# guvenli degil (bkz. gui/pdfium_lock.py), yani baska bir thread pdfium
# icindeyken bu segfault sinifi.
#
# pdf_render_worker bu duzeltmeyi 2026-09-05'te aldi; pdf_search_worker
# almamisti, oysa kendi basliginda "pdf_render_worker'in IKIZI (ayni yasam
# dongusu korumasi)" diyor. Olculdu 2026-09-06: ikizin _doc'u stop() sonrasi
# None, arama iscisininki hala acik ve finalizer MainThread'de kosuyor.
#
# Kapi IKI ISCIYI de ayni parametrik testten geciriyor: ilerideki ayrisma
# hangi yonde olursa olsun burasi kirilir.
# =====================================================================

import threading as _threading


def _iki_isci():
    from gui.pdf_render_worker import PdfRenderWorker
    from gui.pdf_search_worker import PdfSearchWorker
    return [PdfRenderWorker, PdfSearchWorker]


def _isci_kur(sinif, yol, gen=1):
    w = sinif()
    w.open_document(yol, gen)
    w.start()
    for _ in range(400):
        if w._doc is not None:
            break
        time.sleep(0.01)
    return w


@pytest.mark.parametrize("sinif", _iki_isci(),
                         ids=lambda c: c.__name__)
def test_isci_dururken_belgeyi_KAPATIYOR(qapp, tmp_path, sinif):
    """Kirilirsa: kapatma GC finalizer'ina kaliyor, kilitsiz ve keyfi thread'de."""
    yol = _pdf_with_text(["testalfa"], str(tmp_path / "s.pdf"))
    w = _isci_kur(sinif, yol)
    # Kapi bos kosmasin: belge gercekten acilmis olmali
    assert w._doc is not None, "belge hic acilmadi, test bir sey kanitlamaz"
    w.stop()
    assert w.wait(6000), "isci durmadi"
    assert w._doc is None, "stop() sonrasi pdfium handle acik kaldi"


@pytest.mark.parametrize("sinif", _iki_isci(), ids=lambda c: c.__name__)
def test_belge_kapatmasi_ISCI_THREADINDE_oluyor(qapp, tmp_path, sinif,
                                                monkeypatch):
    """Kapatma ana thread'e kacmamali: `_doc`a yalniz run() dokunmali.

    `pdfium_lock` yalniz uygulama kodunda aliniyor; kapatma baska bir
    thread'e kacarsa kilit disinda pdfium cagrisi olur.
    """
    kapatan = []
    asil = sinif._swap_document

    def _izleyen(self, wanted):
        if self._doc is not None:
            kapatan.append(_threading.current_thread().name)
        return asil(self, wanted)

    monkeypatch.setattr(sinif, "_swap_document", _izleyen)

    yol = _pdf_with_text(["testalfa"], str(tmp_path / "s.pdf"))
    w = _isci_kur(sinif, yol)
    assert w._doc is not None
    w.stop()
    assert w.wait(6000)

    assert kapatan, "belge hic kapatilmadi"
    ana = _threading.main_thread().name
    assert all(t != ana for t in kapatan), (
        "belge ana thread'de kapatildi: %s" % kapatan)


@pytest.mark.parametrize("sinif", _iki_isci(), ids=lambda c: c.__name__)
def test_belge_ACILMAMIS_iscide_stop_sorunsuz(qapp, sinif):
    """Sinir: hic dokuman verilmemis isci de temiz durmali."""
    w = sinif()
    w.start()
    time.sleep(0.05)
    w.stop()
    assert w.wait(6000)
    assert w._doc is None


@pytest.mark.parametrize("sinif", _iki_isci(), ids=lambda c: c.__name__)
def test_UST_USTE_stop_sorunsuz(qapp, tmp_path, sinif):
    yol = _pdf_with_text(["testalfa"], str(tmp_path / "s.pdf"))
    w = _isci_kur(sinif, yol)
    w.stop()
    w.stop()
    assert w.wait(6000)
    assert w._doc is None


def test_ARAMA_hala_calisiyor_ve_belge_arama_boyunca_ACIK(qapp, tmp_path):
    """Asiri duzeltme kapisi: erken kapatma aramayi oldurmemeli."""
    yol = _pdf_with_text(["merhaba testalfa", "bos", "yine testalfa"],
                         str(tmp_path / "s.pdf"))
    w = _isci_kur(PdfSearchWorker, yol, gen=5)
    got = []
    w.found.connect(lambda sid, res: got.append((sid, res)))
    try:
        w.search(11, "testalfa")
        assert _spin(qapp, lambda: bool(got)), "arama sonucu gelmedi"
        assert got[0][0] == 11
        assert [r[0] for r in got[0][1]] == [0, 2]
        assert w._doc is not None, "arama sirasinda belge kapanmis"
    finally:
        w.stop()
        w.wait(6000)
    assert w._doc is None
