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


# =====================================================================
# Ctrl+F, arama cubugu ACIKKEN aramayi kapatiyordu (2026-09-07)
#
# `edit_ops._show_find` PDF odaktayken `_toggle_search_bar` cagiriyordu.
# OLCULDU: cubuk acik ve iki eslesme bulunmusken ayni tus cubugu KAPATIP
# sonuclari siliyor (2 eslesme -> 0, sayac "bulunamadi"), sorgu ise kutuda
# kaliyor. Editor tarafindaki ayni kisayol `find_replace.show_find`a gidiyor
# ve gosterip odakliyor, seciyor, aramayi yeniden kosuyor.
#
# Ikinci bulgu: "bulunamadi" bir SONUC. `_clear_search` onu sorgu YOKKEN de
# yaziyordu, yani cubuk yeniden acilinca kutuda "teorem" yazili, belgede iki
# gecisi var ve sayac "bulunamadi" diyordu.
# =====================================================================


def _arama_gorucusu(qapp, tmp_path, metin="merhaba teorem ve teorem"):
    from gui.pdf_viewer import PdfViewer
    from gui.theme import THEMES
    yol = _pdf_with_text([metin], str(tmp_path / "ah.pdf"))
    v = PdfViewer(theme=THEMES["dark"])
    # Pencere GOSTERILIYOR: Qt'de cocuk widget'in isVisible()'i butun ata
    # zinciri gorunur olmadikca False doner ve bu testlerin olctugu sey tam
    # olarak cubugun gorunurlugu.
    v.resize(700, 600)
    v.show()
    assert v.load_pdf(yol)
    return v


def _ara(qapp, v, sorgu="teorem"):
    v._search_input.setText(sorgu)
    v._on_search_return()
    assert _spin(qapp, lambda: bool(v._search_results)), "arama sonucu gelmedi"


def test_CTRL_F_acik_cubugu_KAPATMIYOR(qapp, tmp_path):
    """Kirilirsa: kullanici Ctrl+F'e basinca bulduklarini kaybediyor."""
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._show_search_bar()
        _ara(qapp, v)
        onceki = len(v._search_results)
        assert onceki == 2, "kapi bos kosuyor: eslesme bulunmadi"

        v._show_search_bar()               # ikinci Ctrl+F
        qapp.processEvents()

        assert v._search_bar_widget.isVisible(), "cubuk kapandi"
        assert len(v._search_results) == onceki, "sonuclar silindi"
        assert v._search_count_label.text() == "1 / 2"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_CTRL_F_kapali_cubugu_ACIYOR(qapp, tmp_path):
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        assert not v._search_bar_widget.isVisible()
        v._show_search_bar()
        assert v._search_bar_widget.isVisible()
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_CTRL_F_sorgu_varken_aramayi_YENIDEN_kosuyor(qapp, tmp_path):
    """Cubuk kapatilirken sonuclar silindi; yeniden acilinca sayac bos
    kalmasin, kullanici Enter'a basmak zorunda olmasin. Kardes
    `find_replace.show_find` de `_do_find()` cagiriyor."""
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._show_search_bar()
        _ara(qapp, v)
        v._close_search()
        assert not v._search_results, "kapatma sonuclari silmedi"

        v._show_search_bar()
        assert _spin(qapp, lambda: bool(v._search_results)), \
            "yeniden acilista arama kosmadi"
        assert v._search_count_label.text() == "1 / 2"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_DUGME_hala_acip_kapatiyor(qapp, tmp_path):
    """Asiri duzeltme kapisi: arac cubugu dugmesinin toggle olmasi DOGRU,
    kapanan sey kisayoldu."""
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._toggle_search_bar()
        assert v._search_bar_widget.isVisible()
        v._toggle_search_bar()
        assert not v._search_bar_widget.isVisible()
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_CTRL_F_PDF_odaktayken_TOGGLE_degil_GOSTERME_cagiriyor(qapp,
                                                               monkeypatch):
    """Kural kapida: ileride `_show_find` yine toggle'a baglanmasin."""
    from gui.mixins.edit_ops import EditOpsMixin

    cagrilar = []

    class _Gorucu:
        def isAncestorOf(self, w):
            return True

        def _show_search_bar(self):
            cagrilar.append("goster")

        def _toggle_search_bar(self):
            cagrilar.append("toggle")

    class _Ana:
        _show_find = EditOpsMixin._show_find
        _pdf_viewer = _Gorucu()

        def _current_editor(self):
            return None

    monkeypatch.setattr("gui.mixins.edit_ops.QApplication.focusWidget",
                        staticmethod(lambda: object()))
    _Ana()._show_find()
    assert cagrilar == ["goster"]


# --- Sayac: "bulunamadi" yalniz arama kostuysa ---


def test_sayac_arama_YAPILMADAN_bulunamadi_demiyor(qapp, tmp_path):
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._clear_search()
        assert v._search_count_label.text() == ""
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_sayac_BOS_sorguda_bulunamadi_demiyor(qapp, tmp_path):
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._do_search("")
        assert v._search_count_label.text() == ""
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_sayac_GERCEKTEN_bulunamadiysa_soyluyor(qapp, tmp_path):
    """Asiri duzeltme kapisi: mesaj biraz kalmali."""
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._do_search("boyle-bir-kelime-yok")
        assert _spin(qapp, lambda: v._search_count_label.text() not in
                     ("", "Aranıyor...")), "sayac hic guncellenmedi"
        assert "bulunamad" in v._search_count_label.text()
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


# --- Kapsam disi kalmis yollar ---


def test_ONCEKI_eslesme_dugmesi_geriye_sariyor(qapp, tmp_path):
    """`_search_prev` hic kosmuyordu.

    UC eslesme sart: ikiyle "onceki" ile "sonraki" ayni diziyi veriyor
    (0 -> 1 -> 0) ve test hicbir sey olcmuyor. Mutasyon bunu yakaladi.
    """
    v = _arama_gorucusu(qapp, tmp_path, "teorem bir teorem iki teorem")
    try:
        v._show_search_bar()
        _ara(qapp, v)
        assert v._search_count_label.text() == "1 / 3"
        v._search_prev()                   # 0'dan geriye: sona sarmali
        assert v._search_count_label.text() == "3 / 3"
        v._search_prev()
        assert v._search_count_label.text() == "2 / 3"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_ENTER_ayni_sorguda_SONRAKINE_geciyor(qapp, tmp_path):
    """`_on_search_return` hic kosmuyordu."""
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._show_search_bar()
        _ara(qapp, v)
        assert v._search_count_label.text() == "1 / 2"
        v._on_search_return()              # ayni sorgu: yeniden aramamali
        assert v._search_count_label.text() == "2 / 2"
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


def test_ENTER_bos_sorguda_hicbir_sey_yapmiyor(qapp, tmp_path):
    v = _arama_gorucusu(qapp, tmp_path)
    try:
        v._show_search_bar()
        v._search_input.setText("   ")
        v._on_search_return()
        qapp.processEvents()
        assert v._search_results == []
        assert v._search_count_label.text() == ""
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


# =====================================================================
# Arama, sayfa metnini ONARARAK arıyor (2026-09-12)
#
# OT1 belgelerde aksanlar ayrı glif basılıyor: `öğrenci` sayfa metninde
# `¨o˘grenci` olarak duruyor. Kopyalama yolu bunu 2026-09-08'den beri
# onarıyordu, arama yolu o taşınmanın DIŞINDA kalmıştı ve pdfium'un kendi
# `textpage.search()`ine ham sorguyu veriyordu.
#
# ÖLÇÜLDÜ (58 gerçek PDF + aynı adlı kaynak, kaynakta geçen 642 Türkçe
# kelime): pdfium 471'ini buluyordu, bu yol 523'ünü buluyor; kayıp 0.
# =====================================================================

from gui.pdf_metin import birlesik_metin  # noqa: E402
from gui.pdf_search_worker import _sayfada_bul  # noqa: E402


class TestOnarilmisArama:

    def test_AYRIK_aksanli_kelime_bulunuyor_ve_aralik_HAM_metne_ait(self):
        r"""Kırılırsa: Türkçe belgede arama hiçbir şey bulmaz.

        Aralık HAM metne ait olmak ZORUNDA: vurgu `get_charbox` ile ham
        karakter indisinden çiziliyor. Onarılmış metinde indis kayıyor.
        """
        ham = "Bu bir ¨o˘grenci belgesidir."
        (aralik,) = _sayfada_bul(ham, "öğrenci")
        bas, bit = aralik
        assert ham[bas:bit] == "¨o˘grenci"

    def test_TURKCE_katlama_editorunkiyle_AYNI(self):
        r"""Arama artık `project_search.eslesme_ofsetleri`den geçiyor, yani
        Ctrl+F ve Projede Ara ile aynı katlama. Kırılırsa `istanbul` sorgusu
        `İstanbul`u bulmaz; ı/i ayrımı da korunmalı."""
        assert _sayfada_bul("˙Istanbul", "istanbul")
        assert _sayfada_bul("˙Istanbul", "İSTANBUL")
        # ı ile i AYRI harf: katlama onları birbirine çevirmemeli
        assert _sayfada_bul("ışık", "IŞIK") == []
        assert _sayfada_bul("ışık", "ışık")

    def test_DUZ_metinde_gerileme_yok(self):
        r"""Aşırı düzeltme kolu: aksansız metinde davranış eskisi gibi.

        Örtüşmeyen eşleşmeler, doğru aralık, sorgu yoksa boş liste.
        """
        ham = "ab ab ab"
        assert _sayfada_bul(ham, "ab") == [(0, 2), (3, 5), (6, 8)]
        assert _sayfada_bul(ham, "zz") == []
        assert _sayfada_bul(ham, "") == []

    @pytest.mark.parametrize("ham", [
        "¨o˘grenci",
        "C¸ ALIS¸MA",
        "S¸EK˙IL",
        "resmˆı",
    ])
    def test_KOPYALAMANIN_onardigini_ARAMA_da_buluyor(self, ham):
        r"""İki yol AYNI tablodan besleniyor; ayrışırlarsa kullanıcı panoda
        doğru metni görüp aynı kelimeyi aramada bulamaz.

        Sözcük sözcük aranıyor: büyük harfler arasına giren boşluk
        (`C¸ ALIS¸MA` -> `Ç ALIŞMA`) bilinen ve belgelenmiş sınır.
        """
        for sozcuk in birlesik_metin(ham).split():
            assert _sayfada_bul(ham, sozcuk), (ham, sozcuk)
