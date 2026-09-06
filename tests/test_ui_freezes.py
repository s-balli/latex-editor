"""UI donması düzeltmelerinin testleri.

- file_ops: pandoc dışa aktarma arka plan thread'inde + meşgul koruması
- file_ops: Ctrl+N (_new_file) ile açılan sekmede Alt+tık tanıma-git sinyali bağlı
- file_tree: derlenebilirlik denetimi tarama sırasında değil kademeli yapılır
- main_window: arka plan pandoc kontrolü bayrak + tooltip günceller
"""

import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QAction
    from gui.mixins.file_ops import FileOpsMixin
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

from tests.stub_main import StubMain
from gui.theme import THEMES


def _spin(app, cond, timeout_ms=5000):
    """Koşul sağlanana dek event loop'u işlet (sinyal/zamanlayıcı teslimatı)."""
    t0 = time.monotonic()
    while not cond():
        app.processEvents()
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            return False
    return True


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _FileOpsStub(FileOpsMixin, StubMain):
    """FileOpsMixin'i StubMain arayüzüyle çalıştır (ağır MainWindow kurulumu yok)."""

    def __init__(self, editors):
        StubMain.__init__(self, editors=editors)
        self._pandoc_available = True
        self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])
        # addAction GERÇEK Qt'de QAction döndürür; sahte de döndürmeli.
        # `None` döndüren eski sahte, menüyü yenilerken `act.setData(yol)`
        # eklendiğinde patladı: sızıntı düzeltmesi yolu artık öğenin
        # verisinde taşıyor (bkz. file_ops._refresh_recent_menu).
        self._recent_menu = SimpleNamespace(
            clear=lambda: None,
            addAction=lambda *a, **k: SimpleNamespace(
                setData=lambda v: None, setEnabled=lambda v: None))
        self._engine_combo = SimpleNamespace(
            currentText=lambda: "lualatex", findText=lambda t: -1,
            currentIndex=lambda: -1, setCurrentIndex=lambda i: None)
        self._file_watch_add = lambda p: None

    def _editor_by_path(self, path):
        for ed in self._editors:
            if ed.file_path and os.path.normpath(ed.file_path) == os.path.normpath(path):
                return ed
        return None

    def _save_if_open(self, path):
        """CompileOpsMixin'deki eşleniğin sadeleştirilmiş kopyası.

        Gerçek MainWindow her iki mixin'i de taşıyor; stub yalnız FileOps
        aldığı için burada yeniden tanımlanıyor.
        """
        editor = self._editor_by_path(path)
        if editor is None:
            return True
        if editor.isModified():
            return editor.save_file()
        return True

    def _apply_editor_settings(self, editor):
        pass

    def _add_tab_close_button(self, index):
        pass

    def _on_goto_definition(self, key, kind):
        pass

    # _new_file'in bağladığı TabOps handler'ları (stub'da no-op)
    def _update_cursor_pos(self):
        pass

    def _update_wordcount(self, editor):
        pass

    def _update_outline_debounced(self, editor):
        pass

    def _paste_image(self):
        pass

    def _on_forward_search(self, *a):
        pass

    def _on_rename_label(self, key):
        pass

    def _on_rename_cite(self, key):
        pass

    def _on_rename_bibitem(self, key):
        pass


# =====================================================================
# Dışa aktarma: arka plan thread + meşgul koruması
# =====================================================================


def test_export_runs_in_background_and_reports(qapp, tmp_path, monkeypatch):
    """_export_file hemen döner; pandoc zinciri arka planda çalışıp sonucu bildirir."""
    import gui.mixins.file_ops as fo

    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass{article}\n\\begin{document}\nhi\n\\end{document}", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(tex)
    stub = _FileOpsStub([ed])

    calls = []

    def fake_export(src, dst):
        calls.append((src, dst))
        return True, ""

    monkeypatch.setattr(fo, "_export", fake_export)
    monkeypatch.setattr(
        fo.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(tmp_path / "out.docx"), ""))

    stub._export_file("DOCX", ".docx")
    # Çağrı bloklamadı: denetim arka planda; sonuç sinyalle gelecek
    assert stub._export_busy is True
    assert "Dışa aktarılıyor" in stub._status.msg

    ok = _spin(qapp, lambda: calls and not stub._export_busy)
    assert ok, "arka plan export tamamlanmadı"
    assert calls == [(str(tex), str(tmp_path / "out.docx"))]
    assert "Dışa aktarıldı" in stub._status.msg


def test_export_kirli_arabellegi_once_kaydeder(qapp, tmp_path, monkeypatch):
    """Dışa aktarma diskteki bayat içeriği değil, kaydedilmiş arabelleği işler.

    exporter.export() .tex'i diskten okuyor; kaydetmeden dışa aktarınca
    kullanıcı son değişiklikleri içermeyen bir DOCX alıp durum çubuğunda
    'Dışa aktarıldı' görüyordu.
    """
    import gui.mixins.file_ops as fo

    tex = tmp_path / "doc.tex"
    tex.write_text("eski icerik\n", encoding="utf-8")
    ed = EditorWidget()
    ed.open_file(str(tex))
    ed.setText("yeni icerik\n")          # arabellek kirli, disk hâlâ eski
    assert ed.isModified()

    goruldu = []

    def fake_export(src, dst):
        goruldu.append(open(src, encoding="utf-8").read())
        return True, ""

    monkeypatch.setattr(fo, "_export", fake_export)
    monkeypatch.setattr(
        fo.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(tmp_path / "out.docx"), ""))

    stub = _FileOpsStub([ed])
    stub._export_file("DOCX", ".docx")
    assert _spin(qapp, lambda: goruldu and not stub._export_busy), "export bitmedi"

    assert goruldu == ["yeni icerik\n"], "pandoc'a bayat disk içeriği gitti"
    assert not ed.isModified()


def test_export_busy_guard(qapp, tmp_path, monkeypatch):
    """Export sürerken ikinci istek yeni pandoc süreci başlatmaz."""
    import gui.mixins.file_ops as fo

    tex = tmp_path / "doc.tex"
    tex.write_text("\\begin{document}x\\end{document}", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(tex)
    stub = _FileOpsStub([ed])

    started = []

    def slow_export(src, dst):
        started.append(dst)
        time.sleep(0.2)
        return True, ""

    monkeypatch.setattr(fo, "_export", slow_export)
    monkeypatch.setattr(
        fo.QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(tmp_path / "out.md"), ""))

    stub._export_file("Markdown", ".md")
    stub._export_file("Markdown", ".md")  # ikinci istek meşgulken reddedilmeli
    assert "zaten sürüyor" in stub._status.msg

    ok = _spin(qapp, lambda: started and not stub._export_busy)
    assert ok
    assert len(started) == 1, "meşgulken ikinci export başladı"


# =====================================================================
# Kapanış: diske yazan daemon thread'ler kesilmeden beklenmeli
# =====================================================================


def test_export_runner_wait_isi_bekler(qapp, tmp_path, monkeypatch):
    """wait() iş bitene kadar bloklar; kapanışta yarım dosya kalmasın."""
    import gui.mixins.file_ops as fo

    bitti = []

    def slow_export(src, dst):
        time.sleep(0.3)
        bitti.append(dst)
        return True, ""

    monkeypatch.setattr(fo, "_export", slow_export)
    runner = fo._ExportRunner()
    runner.start("a.tex", "a.docx")

    assert runner.wait(5000) is True
    assert bitti == ["a.docx"], "wait() iş bitmeden döndü"


def test_runner_wait_bos_ve_zaman_asimi():
    """Hiç başlatılmamışsa anında True; süre yetmezse False (kapanış askıda kalmasın)."""
    import gui.mixins.file_ops as fo

    runner = fo._ExportRunner()
    assert runner.wait(1000) is True          # _thread None

    monkeypatch_free = threading.Event()
    runner._thread = threading.Thread(
        target=monkeypatch_free.wait, daemon=True)
    runner._thread.start()
    try:
        assert runner.wait(50) is False, "bitmeyen iş için False dönmeli"
    finally:
        monkeypatch_free.set()


def test_snapshot_runner_wait(qapp, tmp_path, monkeypatch):
    """Sürümleme thread'i: add+commit ortasında kesilmek depoyu bozabilir."""
    import gui.mixins.version_ops as vo

    monkeypatch.setattr(vo.versioning, "init_repo", lambda root: None)

    def slow_snapshot(root, msg):
        time.sleep(0.3)
        return None

    monkeypatch.setattr(vo.versioning, "snapshot", slow_snapshot)
    runner = vo._SnapshotRunner()
    runner.start(str(tmp_path), "mesaj", first=True)

    assert runner.wait(5000) is True
    assert not runner._thread.is_alive()


def test_wait_background_writers_hepsini_bekler(qapp):
    """MainWindow.closeEvent kancası: tanımlı her yazıcıyı bekler, yoksa atlar."""
    from gui.main_window import MainWindow

    beklenen = []

    class _Runner:
        def __init__(self, ad, sonuc):
            self.ad, self.sonuc = ad, sonuc

        def wait(self, timeout_ms):
            beklenen.append((self.ad, timeout_ms))
            return self.sonuc

    stub = SimpleNamespace(
        _BG_WRITERS=MainWindow._BG_WRITERS,        # gerçek liste/süreler sınansın
        _snapshot_runner=_Runner("snapshot", True),
        _export_runner=_Runner("export", False),   # zaman aşımı: sadece uyarı
    )
    MainWindow._wait_background_writers(stub)

    assert [ad for ad, _ in beklenen] == ["snapshot", "export"]
    sureler = dict(beklenen)
    assert sureler["snapshot"] >= sureler["export"], \
        "git commit dışa aktarmadan daha uzun tutulmalı"

    # Yazıcı hiç oluşmamışsa (sürümleme/dışa aktarma kullanılmadı) sessiz geçer
    MainWindow._wait_background_writers(
        SimpleNamespace(_BG_WRITERS=MainWindow._BG_WRITERS))


# =====================================================================
# _new_file: goto_definition sinyali bağlanmalı (Alt+tık)
# =====================================================================


def test_new_file_connects_goto_definition(qapp, tmp_path, monkeypatch):
    got = []

    class _S(_FileOpsStub):
        def _on_goto_definition(self, key, kind):
            got.append((key, kind))

    stub = _S(editors=[])
    import gui.mixins.file_ops as fo
    path = str(tmp_path / "yeni.tex")
    monkeypatch.setattr(fo.QFileDialog, "getSaveFileName", lambda *a, **k: (path, ""))

    stub._new_file()
    new_ed = stub._editor_tabs.widget(stub._editor_tabs.count() - 1)
    assert new_ed is not None and new_ed.file_path == path

    # Alt+tık sinyali bağlı mı? Emit → handler çalışmalı
    new_ed.goto_definition_requested.emit("key1", "cite")
    assert got == [("key1", "cite")], (
        "_new_file sekmesinde goto_definition_requested bağlı değil (Alt+tık ölü)")


# ======================================================================
# file_tree: derlenebilirlik denetimi kademeli
# ======================================================================


def _tree_items(tree):
    """Kök öğeleri (metin → QTreeWidgetItem) topla."""
    out = {}
    top = tree._tree.invisibleRootItem()
    for i in range(top.childCount()):
        item = top.child(i)
        out[item.text(0)] = item
    return out


def test_tree_compile_check_is_deferred_and_correct(qapp, tmp_path):
    from PyQt6.QtGui import QColor
    from gui.file_tree import FileTree

    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nx\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "child.tex").write_text("yalnızca parça; ana belge işareti yok\n", encoding="utf-8")

    theme = THEMES["dark"]
    tree = FileTree(theme=theme)
    tree.set_root(str(tmp_path))

    # Tarama bitti ama denetim HENÜZ yapılmadı: kuyrukta iki .tex olmalı
    # (senkron olsaydı set_root dönüşünde kuyruk boş ve renkler dolmuş olurdu)
    assert len(tree._pending_checks) == 2, "denetim tarama sırasında değil kademeli olmalı"

    assert _spin(qapp, lambda: not tree._pending_checks and not tree._check_timer.isActive())

    items = _tree_items(tree)
    assert items["📄 main.tex"].foreground(0).color().name() == QColor(theme["sem_compilable"]).name()
    assert items["📄 child.tex"].foreground(0).color().name() == QColor(theme["fg_muted"]).name()


def test_tree_refresh_keeps_queue_consistent(qapp, tmp_path):
    """refresh() bekleyen denetimleri düşürür; kuyruk her zaman geçerli öğe taşır."""
    from gui.file_tree import FileTree

    (tmp_path / "a.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
    tree = FileTree(theme=THEMES["dark"])
    tree.set_root(str(tmp_path))
    assert tree._pending_checks  # kuyruk dolu

    tree.refresh()  # bekleyen denetimler düşürüldü, yenisi planlandı
    assert len(tree._pending_checks) == 1
    assert _spin(qapp, lambda: not tree._pending_checks)


# ======================================================================
# main_window: pandoc kontrolü bayrak + tooltip günceller
# ======================================================================


def test_on_pandoc_checked_updates_flag_and_tooltips(qapp):
    from gui.main_window import MainWindow

    acts = [QAction("DOCX (.docx)"), QAction("HTML (.html)")]
    mw = SimpleNamespace(_export_actions=acts, _pandoc_available=True)

    MainWindow._on_pandoc_checked(mw, False)
    assert mw._pandoc_available is False
    assert all("pandoc" in a.toolTip() for a in acts), "pandoc yokken tooltip dolu olmalı"

    # QAction'ta boş tooltip metne düşer — anlamlı olan 'pandoc' ipucunun gitmesi
    MainWindow._on_pandoc_checked(mw, True)
    assert mw._pandoc_available is True
    assert all("pandoc" not in a.toolTip() for a in acts)


def test_ayni_kok_yeniden_taranmiyor(qapp, tmp_path):
    """set_root aynı kökle tekrar çağrılırsa ağacı baştan taramamalı.

    Açılışta iki kez çağrılıyordu: `_restore_state()` kayıtlı kökü kuruyor,
    ardından komut satırından/"Birlikte Aç"tan dosya geldiyse `main_window`
    onun dizinini kök yapıyor — genellikle AYNI dizin. İkinci çağrı ağacı
    boşaltıp baştan tarıyor ve her .tex için `_can_compile` denetim kuyruğunu
    ikinci kez dolduruyordu (2026-08-31, F4).
    """
    from gui.file_tree import FileTree

    for ad in ("a.tex", "b.tex", "c.tex"):
        (tmp_path / ad).write_text("\\begin{document}\\end{document}", encoding="utf-8")

    tree = FileTree(theme=THEMES["dark"])
    tarama = []
    gercek = tree._scan_dir
    tree._scan_dir = lambda *a, **kw: (tarama.append(1), gercek(*a, **kw))[1]

    tree.set_root(str(tmp_path))
    assert len(tarama) == 1, "ilk set_root taramalı"
    kuyruk = len(tree._pending_checks)
    assert kuyruk == 3

    tree.set_root(str(tmp_path))                       # aynı kök
    tree.set_root(str(tmp_path) + os.sep)              # normpath sonrası aynı
    assert len(tarama) == 1, "aynı kök yeniden taranmamalı"
    assert len(tree._pending_checks) == kuyruk, "denetim kuyruğu ikizlenmemeli"

    # Kök GERÇEKTEN değişince yine taranmalı
    alt = tmp_path / "alt"
    alt.mkdir()
    (alt / "d.tex").write_text("\\begin{document}\\end{document}", encoding="utf-8")
    tree.set_root(str(alt))
    assert len(tarama) == 2, "yeni kök taranmalı"
    assert _spin(qapp, lambda: not tree._pending_checks)


def test_render_edilen_pixmap_yalniz_label_da_tutuluyor(qapp, tmp_path):
    """PdfViewer okunmayan bir ikinci pixmap referansı TUTMAMALI.

    `self._cache` yazılıyor ve sıfırlanıyordu ama hiçbir yerden okunmuyordu.
    Ölçüldü (2026-08-31, F2): zoom sonrasında label'ın bıraktığı pixmap'leri
    tek başına ayakta tutuyordu — küçük bir belgede 19.3 MB, tavanı 256 MB.
    Geri gelirse burası kırılır.
    """
    pytest.importorskip("pypdfium2")
    from gui.pdf_viewer import PdfViewer

    v = PdfViewer(theme=THEMES["dark"])
    try:
        assert not hasattr(v, "_cache"), "okunmayan sayfa önbelleği geri gelmiş"
        assert not hasattr(v, "_cache_bytes")
        assert not hasattr(v, "_cache_put")
        # Sunum modu önbelleği AYRI ve gerçekten okunuyor — kalmalı
        assert hasattr(v, "_pres_cache")
    finally:
        v.shutdown()
        v.deleteLater()
        qapp.processEvents()


# =====================================================================
# Fare hareketi UI thread'ini pdfium kilidinde bekletiyordu (2026-09-06)
#
# `_events._handle_page_event` HER MouseMove olayinda `_update_link_cursor`
# cagiriyor; o da `_link_at_pos` icinde `pdfium_lock`u BEKLEYEREK aliyordu.
# Kilit render iscisindeyse UI thread o sayfanin render'i bitene kadar
# bloke oluyordu. Olculdu: isci kilidi 500 ms tutarken TEK fare hareketi
# UI'i 500.5 ms bekletiyor (kilit bosken ayni hareket 0.075 ms). Render
# iscisinin kendi yorumu "uc zoomda tek sayfa render'i ~3 sn surebilir"
# diyor.
#
# `pdfium_lock.py`nin kurali: "Blokta tutulan sure kisa olmali, yoksa UI
# uzun bir render partisi boyunca donardi." Isci tarafi kurali tutuyordu
# (kilidi sayfa basina aliyor), bekleyen taraf UI'di.
#
# Duzeltme: imlec yolu kilidi BEKLEMEDEN aliyor, mesgulse imlec oldugu gibi
# kaliyor. TIKLAMA yolu bilerek bekliyor: tiklama atlanamaz.
#
# KAPILAR ZAMANA DEGIL DAVRANISA bakiyor (CI'da zamanlama kirilgan olur):
# kilit mesgulken imlec yolu pdfium'a HIC sormamali, tiklama yolu ise
# beklenip SORMALI.
# =====================================================================


@pytest.fixture
def _pdf_gorucu(qapp, tmp_path):
    """Uc sayfalik gercek PDF yuklu gorucu + pdfium cagri sayaci."""
    pypdfium2 = pytest.importorskip("pypdfium2")
    from gui.pdf_viewer import PdfViewer
    import gui.pdf_viewer_mixins._events as ev

    yol = str(tmp_path / "a.pdf")
    d = pypdfium2.PdfDocument.new()
    for _ in range(3):
        d.new_page(400, 600)
    d.save(yol)
    d.close()

    sayac = []
    asil = ev.get_link_at_point

    def _sayan(*a, **k):
        sayac.append(1)
        return asil(*a, **k)

    ev.get_link_at_point = _sayan
    v = PdfViewer(theme=THEMES["dark"])
    v.resize(900, 700)
    assert v.load_pdf(yol)
    qapp.processEvents()
    try:
        yield v, v._page_labels[0], sayac
    finally:
        ev.get_link_at_point = asil
        v.shutdown()
        v.close()
        qapp.processEvents()


def _fare_hareketi(x, y):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y),
                       Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


class _KilitTutan:
    """pdfium_lock'u baska bir thread'de tut (render iscisini taklit eder)."""

    def __init__(self):
        from gui.pdfium_lock import pdfium_lock
        self._lock = pdfium_lock
        self._alindi = threading.Event()
        self._birak = threading.Event()
        self._t = None

    def __enter__(self):
        def _calis():
            with self._lock:
                self._alindi.set()
                self._birak.wait(10)

        self._t = threading.Thread(target=_calis, daemon=True)
        self._t.start()
        assert self._alindi.wait(5), "yardimci thread kilidi alamadi"
        return self

    def __exit__(self, *a):
        self._birak.set()
        self._t.join(5)
        return False


def test_fare_hareketi_MESGUL_kilidi_beklemiyor(_pdf_gorucu):
    """Kirilirsa: imlec yolu kilidi yine BEKLEYEREK aliyor demektir.

    Zamanlama degil DAVRANIS siniyor: kilit mesgulken pdfium'a hic
    sorulmamali. Sorulsaydi cagri kilidin serbest kalmasini beklerdi.
    """
    v, label, sayac = _pdf_gorucu
    sayac.clear()
    with _KilitTutan():
        v.eventFilter(label, _fare_hareketi(30, 50))
    assert sayac == [], "kilit mesgulken pdfium'a soruldu (yol bloke olur)"


def test_fare_hareketi_kilit_BOSKEN_calisiyor(_pdf_gorucu):
    """Karsi durum: duzeltme imleci tumuyle olduren bir sey olmamali."""
    v, label, sayac = _pdf_gorucu
    sayac.clear()
    v.eventFilter(label, _fare_hareketi(30, 50))
    assert len(sayac) == 1, "kilit bosken imlec yolu pdfium'a sormadi"


def test_MESGUL_kilitte_cok_sayida_hareket_hizli(_pdf_gorucu):
    """Kilit mesgulken bir suru hareket birikse de hicbiri beklememeli."""
    v, label, sayac = _pdf_gorucu
    sayac.clear()
    with _KilitTutan():
        t0 = time.monotonic()
        for i in range(50):
            v.eventFilter(label, _fare_hareketi(20 + i, 40))
        gecen = time.monotonic() - t0
    assert sayac == []
    # Genis pay: 50 atlanan hareket milisaniyeler surer; BEKLESEYDI
    # yardimci thread'in 10 sn'lik tutusuna takilirdi.
    assert gecen < 2.0, "hareketler bekledi: %.2f sn" % gecen


def test_TIKLAMA_yolu_kilidi_BEKLIYOR(_pdf_gorucu):
    """Asiri duzeltme kapisi: tiklama atlanamaz, o yol beklemeli.

    Kirilirsa: bloklamayan alim tiklama yoluna da sizmis demektir ve
    render sirasinda baglanti tiklamalari sessizce dusverirdi.
    """
    v, label, sayac = _pdf_gorucu
    sayac.clear()
    tutan = _KilitTutan()
    tutan.__enter__()
    # Kisa sure sonra birak; tiklama yolu beklemeli ve SONRA sormali.
    threading.Timer(0.15, tutan._birak.set).start()
    try:
        v._handle_link_click(_fare_hareketi(30, 50).position().toPoint(), label)
    finally:
        tutan._birak.set()
        tutan._t.join(5)
    assert sayac, "tiklama yolu pdfium'a hic sormadi (atlamis)"


def test_atlanan_hareket_KILIDI_SIZDIRMIYOR(_pdf_gorucu):
    """`acquire(blocking=False)` basarisiz olunca release edilmemeli."""
    from gui.pdfium_lock import pdfium_lock

    v, label, _sayac = _pdf_gorucu
    with _KilitTutan():
        v.eventFilter(label, _fare_hareketi(30, 50))
    # Kilit serbest kalmis olmali
    assert pdfium_lock.acquire(blocking=False), "kilit sizdi"
    pdfium_lock.release()
    # Ve yol yeniden calisiyor olmali
    v.eventFilter(label, _fare_hareketi(31, 51))


def test_BELGE_YOKKEN_fare_hareketi_sorunsuz(qapp):
    """Sinir: PDF yuklenmemis gorucude hareket patlamamali."""
    pytest.importorskip("pypdfium2")
    from gui.pdf_viewer import PdfViewer

    v = PdfViewer(theme=THEMES["dark"])
    try:
        v.eventFilter(v, _fare_hareketi(5, 5))
    finally:
        v.shutdown()
        v.close()
        qapp.processEvents()


# =====================================================================
# pandoc kontrolu: arka plan is parcacigi Qt'ye DOKUNMAMALI (2026-09-06)
#
# Eskiden her pencere kendi `_PandocCheckSignal` koprusunu kurup arka plan
# thread'inden emit ediyordu. Pencere kapandiginda o thread'i durduran,
# bekleyen ya da baglantiyi kesen hicbir sey yoktu; kontrol pencerenin
# omrunden uzun surunce emit OLU nesneye gidiyordu. Ayni yarisin iki yuzu:
# nesne tam olmusse PyQt "does not have a signal with the signature
# ready(bool)" atip thread'i sessizce olduruyor, yok etme emit'in ortasina
# denk gelirse serbest bellege yaziliyor ve SUREC 0xC0000005 ile oluyor.
#
# OLCULDU 2026-09-06, emit gecikmesi denetlenerek (5'er kosu):
#      30 ms -> cokme 0/5      60 ms -> cokme 4/5     150 ms -> cokme 5/5
#     400 ms -> cokme 2/5    5000 ms -> cokme 0/5
# Gercek sure WSL'e bagli: ilk cagri 2770 ms (soguk), sonrakiler ~110 ms,
# yani tam cokme bandinda. Belirti: tests/test_ana_pencere_yollari.py arka
# arkaya kosturulunca 3. kosudan itibaren surec oluyordu; kod degismeden,
# yalniz WSL isindiginda.
#
# Cozum cross-thread Qt erisimini TUMUYLE kaldiriyor: is parcacigi yalniz bir
# Python degiskeni yaziyor, sonucu UI'ya tasiyan zamanlayici PENCERENIN
# COCUGU (pencere olunce Qt onu da olduruyor). Sonuc surec genelinde
# onbellekli, ikinci pencere WSL'e hic sormuyor.
# =====================================================================

_WIN = sys.platform == "win32"
sadece_win = pytest.mark.skipif(not _WIN,
                                reason="pandoc kontrolu yalniz Windows'ta "
                                       "arka planda kosuyor")


def test_pandoc_arka_plan_yolu_QT_NESNESINE_dokunmuyor():
    """Kirilirsa: kontrol yine cross-thread Qt erisimi yapiyor demektir.

    Bu kapi her platformda kosar: sinanan sey KAYNAGIN sekli.
    """
    import inspect
    import gui.main_window as mw

    kaynak = inspect.getsource(mw._pandoc_kontrolu_basla)
    for yasak in ("emit", "QObject", "pyqtSignal", "self."):
        assert yasak not in kaynak, (
            "arka plan yolunda Qt erisimi geri gelmis: %r" % yasak)
    assert not hasattr(mw, "_PandocCheckSignal"), (
        "olu sinyal koprusu sinifi geri gelmis")


@pytest.fixture
def _pandoc_taze():
    """Surec genelindeki pandoc onbellegini test basina sifirla.

    TEARDOWN ONBELLEGI YERLESIK BIRAKIR, None DEGIL. Onbellek SUREC genelinde:
    None birakilirsa suitedeki SONRAKI her MainWindow gercek WSL kontrolunu
    yeniden baslatir. Olculdu 2026-09-06: monkeypatch ile None'a geri
    donuldugunde tam takim Windows'ta butun testler gectikten SONRA, cikista
    0xC0000409 ile oluyordu (CI test-windows kirmizi). Bu yuzden geri yukleme
    elle yapiliyor ve onbellek gercek bir degerle kapatiliyor.
    """
    import gui.main_window as mw
    eski = mw._pandoc_sonuc
    mw._pandoc_sonuc = None
    mw._pandoc_thread = None
    try:
        yield mw
    finally:
        # `_pandoc_kontrolu_basla` sonuc None DEGILSE hic thread baslatmiyor.
        mw._pandoc_sonuc = True if eski is None else eski


# PENCERE KURAN KAPI HENUZ EKLENEMIYOR.
# Kusurun en dogrudan kapisi 'pencere kontrol bitmeden yok edilince is
# parcaciginda istisna cikmiyor' olurdu; yazildi ve calisiyor (tek basina
# yesil). Ama takima EKLENEMEDI: bu depoda tam takim Windows'ta bir ek
# MainWindow'u daha kaldiramiyor, butun testler gectikten SONRA cikista
# 0xC0000409 ile dusuyor. Olculdu 2026-09-06 ve bu duzeltmeden BAGIMSIZ:
# uretim degisikligi tumuyle geri alinmisken, pandoc mantigi OLMAYAN iki
# pencerelik atilabilir bir test de ayni cokmeyi uretiyor; pencere kuran
# testim cikarilinca takim temiz (2440 gecti, rc=0).
# DURUM (2026-09-06 sonu): o cokme icin `ana_pencere` teardown'una
# DeferredDelete bosaltmasi eklendi (bkz. tests/conftest.py ve
# tests/test_pencere_yasam_dongusu.py). Olculen etki 6'sar kosuyla
# yuklu-duzeltmesiz 2/6, yuklu-duzeltmeli 0/6. Ama MEKANIZMA hala
# kanitlanmadi, yani elimizde bir HAFIFLETME var, kok neden yok. Bu yuzden
# asagidaki kapi HALA eklenmedi: ekleneceginde oran yeniden olculmeli.
#   pandoc_available bloklanir, pencere kurulur, KAPATILIP yok edilir,
#   sonra kontrol serbest birakilir; threading.excepthook istisna
#   GORMEMELI ve _pandoc_sonuc yine de dolmali.

@sadece_win
def test_pandoc_kontrolu_SUREC_te_bir_kez_kosuyor(_pandoc_taze, monkeypatch):
    """Sonuc bilindikten sonra yeni is parcacigi baslamamali.

    WSL'e pencere basina sormak gereksiz: `pandoc_available()` ilk cagrida
    2770 ms suruyor (WSL soguk). Onbellek olmasa her pencere bu bedeli oderdi.

    PENCERE KURMUYOR. Bu depoda tek testte IKI MainWindow kurmak tam takimi
    Windows'ta cikista 0xC0000409 ile dusuruyor (olculdu 2026-09-06, bu
    duzeltmeden BAGIMSIZ, ayri bir kusur). Onbellek sozlesmesi modul
    duzeyinde sinanabiliyor, pencereye gerek yok.
    """
    import core.exporter as ex
    cagri = []
    monkeypatch.setattr(ex, "pandoc_available",
                        lambda: (cagri.append(1), False)[-1])

    _pandoc_taze._pandoc_kontrolu_basla()
    for _ in range(500):
        if _pandoc_taze._pandoc_sonuc is not None:
            break
        time.sleep(0.01)
    assert _pandoc_taze._pandoc_sonuc is False, _pandoc_taze._pandoc_sonuc
    assert len(cagri) == 1, cagri

    _pandoc_taze._pandoc_kontrolu_basla()      # ikinci kez: hicbir sey olmamali
    time.sleep(0.05)
    assert len(cagri) == 1, "sonuc bilinirken yeniden soruldu: %s" % cagri




class _YoklamaKuklasi:
    """`_pandoc_yokla` icin en kucuk alici: pencere kurmadan sinamak icin.

    NEDEN PENCERE YOK: bu depoda bir testte IKI MainWindow kurmak (ve toplamda
    birkac ek pencere) tam takimi Windows'ta butun testler gectikten SONRA,
    cikista 0xC0000409 ile dusuruyor. Olculdu 2026-09-06 ve bu duzeltmeden
    BAGIMSIZ: uretim degisikligi tumuyle geri alinmisken, pandoc mantigi
    OLMAYAN iki pencerelik atilabilir bir test de ayni cokmeyi uretiyor. Ayri
    bir kusur; asagidaki tek pencereli test o butceyi harciyor.
    """

    def __init__(self):
        self.durduruldu = False
        self.alinan = []
        kukla = self

        class _Zaman:
            def stop(self):
                kukla.durduruldu = True

        self._pandoc_bekleyici = _Zaman()

    def _on_pandoc_checked(self, deger):
        self.alinan.append(deger)


def test_pandoc_yokla_SONUC_GELINCE_zamanlayiciyi_durdurup_uyguluyor(
        _pandoc_taze):
    """Yoklama: sonuc yokken hicbir sey yapmamali, gelince bir kez uygulamali."""
    import gui.main_window as mw

    k = _YoklamaKuklasi()
    mw.MainWindow._pandoc_yokla(k)
    assert k.alinan == [], "sonuc yokken uygulandi"
    assert not k.durduruldu, "sonuc yokken zamanlayici durduruldu"

    _pandoc_taze._pandoc_sonuc = False
    mw.MainWindow._pandoc_yokla(k)
    assert k.alinan == [False], k.alinan
    assert k.durduruldu, "sonuc gelince zamanlayici durmadi"


def test_pandoc_pencere_yolu_ONBELLEGI_OKUYOR_ve_zamanlayici_EBEVEYNLI():
    """Pencere tarafinin iki degismezi, KAYNAK SEKLI uzerinden.

    Bu iki kapi normalde DAVRANISLA tutulurdu (pencere kurup zamanlayicinin
    ebeveynini ve ikinci pencerenin WSL'e sormadigini olcerek) ama takim bir
    ek MainWindow'u daha kaldiramiyor (bkz. yukaridaki not, ayri kusur).
    Kaynak sekli davranistan ZAYIF bir olcut; M2 duzelince davranis kapilari
    buraya gelmeli. Yine de mutasyonla dogrulandi: iki degismezden biri
    bozulunca burasi kirmizi yaniyor.
    """
    import inspect
    import gui.main_window as mw

    kaynak = inspect.getsource(mw.MainWindow._setup_menus)
    assert "QTimer(self)" in kaynak, (
        "pandoc zamanlayicisi PENCERENIN cocugu degil; pencere olunce Qt onu "
        "oldurmez ve olu nesneye cagri kalir")
    assert "if _pandoc_sonuc is not None:" in kaynak, (
        "pencere surec genelindeki onbellegi okumuyor; her pencere WSL'e "
        "yeniden sorar (ilk cagri 2770 ms)")
