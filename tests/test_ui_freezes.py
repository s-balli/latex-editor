"""UI donması düzeltmelerinin testleri.

- file_ops: pandoc dışa aktarma arka plan thread'inde + meşgul koruması
- file_ops: Ctrl+N (_new_file) ile açılan sekmede Alt+tık tanıma-git sinyali bağlı
- file_tree: derlenebilirlik denetimi tarama sırasında değil kademeli yapılır
- main_window: arka plan pandoc kontrolü bayrak + tooltip günceller
"""

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
        self._recent_menu = SimpleNamespace(
            clear=lambda: None, addAction=lambda *a, **k: None)
        self._engine_combo = SimpleNamespace(
            currentText=lambda: "lualatex", findText=lambda t: -1,
            currentIndex=lambda: -1, setCurrentIndex=lambda i: None)
        self._file_watch_add = lambda p: None

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
