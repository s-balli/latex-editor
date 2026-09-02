"""UI donması düzeltmelerinin testleri.

- file_ops: pandoc dışa aktarma arka plan thread'inde + meşgul koruması
- file_ops: Ctrl+N (_new_file) ile açılan sekmede Alt+tık tanıma-git sinyali bağlı
- file_tree: derlenebilirlik denetimi tarama sırasında değil kademeli yapılır
- main_window: arka plan pandoc kontrolü bayrak + tooltip günceller
"""

import os
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
