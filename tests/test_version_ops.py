"""Sürümleme GUI testleri — Sürümle akışı, Geçmiş sekmesi, geri yükleme.

dulwich yoksa atlar; MainWindow kurulumu yerine StubMain + VersionOpsMixin.
"""

from types import SimpleNamespace
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.version_ops import VersionOpsMixin
    from gui.output_panel import OutputPanel
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

pytest.importorskip("dulwich")

from core import versioning as V  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(VersionOpsMixin, StubMain):
    def __init__(self, editors, root):
        StubMain.__init__(self, editors=editors)
        self._file_tree = SimpleNamespace(
            _root=root,
            set_root=lambda p: setattr(self._file_tree, "_root", p),
        )
        self.watch_saves = []

    def _file_watch_record_save(self, path):
        self.watch_saves.append(path)


def _project(tmp_path):
    (tmp_path / "ana.tex").write_text(
        "\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(tmp_path / "ana.tex")


def _stub_with_editor(tmp_path, monkeypatch, mesaj="deneme sürümü"):
    tex = _project(tmp_path)
    ed = EditorWidget()
    ed.open_file(tex)
    stub = _Stub([ed], str(tmp_path))

    import gui.mixins.version_ops as vo
    monkeypatch.setattr(
        vo.QInputDialog, "getText",
        staticmethod(lambda *a, **k: (mesaj, True)))
    return stub, ed, tex


def _snap(qapp, stub):
    """_snapshot çağır ve arka plan işi bitene (busy düşene) kadar dön.

    Snapshot artık arka planda koşuyor (dulwich add+commit UI'yi
    kilitlemesin diye); sonuç sinyali event loop üzerinden gelir.
    """
    stub._snapshot()
    deadline = time.monotonic() + 10
    while getattr(stub, "_snapshot_busy", False) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()


# --- Sürümle ---


def test_first_snapshot_inits_repo_and_fills_history(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)

    _snap(qapp, stub)
    assert V.is_repo(str(tmp_path))
    assert "Sürüm kaydedildi" in stub._status.msg
    assert stub._output_panel._history_list.count() == 1
    item = stub._output_panel._history_list.item(0)
    assert "deneme sürümü" in item.text()
    assert item.data(0x0100)  # UserRole: sha  (0x0100 = Qt.ItemDataRole.UserRole)


def test_open_folder_refreshes_history(qapp, tmp_path, monkeypatch):
    """Klasör değişince ÖNCEKİ klasörün geçmişi ekranda kalmamalı."""
    from gui.mixins.file_ops import FileOpsMixin

    class _FolderStub(FileOpsMixin, _Stub):
        def _close_tab_safe(self, index):
            return True  # sekmeleri kapatma; kök/geçmiş davranışını sınıyoruz

    # 1. klasörde sürüm at
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    folder_stub = _FolderStub([ed], str(tmp_path))
    _snap(qapp, folder_stub)
    assert folder_stub._output_panel._history_list.count() == 1

    # 2. başka klasör aç (boş, sürümsüz)
    other = tmp_path / "diger"
    other.mkdir()
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(other)))
    folder_stub._pdf_viewer = SimpleNamespace(clear=lambda: None)
    folder_stub._open_folder()

    assert folder_stub._file_tree._root == str(other)
    assert folder_stub._output_panel._history_list.count() == 0, \
        "eski klasörün geçmişi yeni klasörde duruyor"


def test_second_snapshot_without_changes_skipped(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)

    _snap(qapp, stub)
    assert "Değişiklik yok" in stub._status.msg
    assert stub._output_panel._history_list.count() == 1


def test_snapshot_saves_dirty_editor_first(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    ed.setText(ed.text() + "\n% yeni satır\n")
    ed.setModified(True)

    _snap(qapp, stub)
    assert ed.isModified() is False, "kirli sekme sürümden önce kaydedilmeli"
    assert "% yeni satır" in open(tex, encoding="utf-8").read()


def test_snapshot_without_folder_shows_status(qapp):
    stub = _Stub([], "")
    _snap(qapp, stub)
    assert "klasör açın" in stub._status.msg


# --- Geçmiş eylemleri: geri yükle / fark ---


def test_restore_from_version(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)
    sha = V.history(str(tmp_path))[0].sha

    # dosyayı boz
    ed.setText("\\begin{document}\nBOZUK\n\\end{document}\n")
    ed.save_file()

    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # QMessageBox.StandardButton.Yes
    stub._on_version_action("restore", sha)

    assert "BOZUK" not in open(tex, encoding="utf-8").read()
    assert "merhaba" in ed.text()
    assert "Geri yüklendi" in stub._status.msg


def test_restore_records_watch_save(qapp, tmp_path, monkeypatch):
    """Geri yükleme watcher hash'ini günceller: sahte 'diskte değişti' diyaloğu
    önlenir (yazım doğrudan diske yapılıyor, watcher görür)."""
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)
    sha = V.history(str(tmp_path))[0].sha

    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # Yes
    stub._on_version_action("restore", sha)

    assert stub.watch_saves == [tex], \
        "geri yükleme sonrası _file_watch_record_save çağrılmalı"


def test_restore_preserves_cursor(qapp, tmp_path, monkeypatch):
    """Geri yükleme sonrası imleç dosya sonuna ATILMAMALI; konum korunmalı.

    open_file (setText) imleci sona atıyordu; artık satır/sütun korunur,
    eski sürüm kısaysa geçerli aralığa kelepçelenir.
    """
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    ed.setText("\\begin{document}\nsatır1\nsatır2\nsatır3\n\\end{document}\n")
    ed.save_file()
    _snap(qapp, stub)  # uzun sürüm
    sha = V.history(str(tmp_path))[0].sha

    ed.setCursorPosition(3, 2)  # 'satır2' ortası
    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # Yes
    stub._on_version_action("restore", sha)

    assert ed.getCursorPosition() == (3, 2), "imleç konumu korunmalı"


def test_version_action_without_editor(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)
    empty = _Stub([], str(tmp_path))
    empty._on_version_action("restore", "deadbeef")
    assert "Açık dosya yok" in empty._status.msg


def test_drop_all_without_open_editor(qapp, tmp_path, monkeypatch):
    """Silme eylemleri açık dosya istemez: dosya kapalıyken de çalışmalı.

    Regression: tüm eylemler tek 'Açık dosya yok' guard'ından geçiyordu;
    drop/drop_all dosya olmadan da kullanılabilir olmalı.
    """
    _project(tmp_path)
    V.init_repo(str(tmp_path))
    V.snapshot(str(tmp_path), "kayıt")

    empty = _Stub([], str(tmp_path))
    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # Yes
    empty._on_version_action("drop_all", "x")

    assert "Açık dosya yok" not in empty._status.msg
    assert "Tüm geçmiş silindi" in empty._status.msg
    assert not V.is_repo(str(tmp_path))


def test_version_action_without_root(qapp):
    empty = _Stub([], "")
    empty._on_version_action("drop_all", "x")
    assert "klasör açın" in empty._status.msg


def test_restore_cp1254_file_not_corrupted(qapp, tmp_path, monkeypatch):
    """cp1254 Türkçe dosya geri yüklemede BİREBİR korunmalı (ham bayt)."""
    # cp1254 dosya açılırken kodlama uyarı dialogu çıkar; headless'ta bloklar
    monkeypatch.setattr("gui.editor.QMessageBox.warning",
                        staticmethod(lambda *a, **k: None))
    raw = "% Türkçe açıklama\nğüş ti\n".encode("cp1254")
    f = tmp_path / "eski.tex"
    f.write_bytes(raw)
    ed = EditorWidget()
    ed.open_file(str(f))  # editör cp1254 algılar
    assert ed._encoding == "cp1254"
    stub = _Stub([ed], str(tmp_path))
    import gui.mixins.version_ops as vo
    monkeypatch.setattr(vo.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("kayıt", True)))
    _snap(qapp, stub)
    sha = V.history(str(tmp_path))[0].sha

    f.write_bytes("% BOZUK".encode("cp1254"))
    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # Yes
    stub._on_version_action("restore", sha)

    assert f.read_bytes() == raw, "geri yükleme baytları değiştirdi"
    assert ed._encoding == "cp1254"  # yeniden açınca da doğru kodlama


def test_copy_version_content_to_clipboard(qapp, tmp_path, monkeypatch):
    """'Kopyala': sürümdeki içerik panoya gider, dosya değişmez."""
    from PyQt6.QtWidgets import QApplication

    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)
    sha = V.history(str(tmp_path))[0].sha
    before = open(tex, encoding="utf-8").read()

    ed.setText("değişti\n")
    ed.save_file()

    stub._on_version_action("copy", sha)
    assert "merhaba" in QApplication.clipboard().text()
    assert "panoya kopyalandı" in stub._status.msg
    # dosyaya dokunulmadı
    assert open(tex, encoding="utf-8").read() == "değişti\n" and before != "değişti\n"


def test_drop_version_from_history(qapp, tmp_path, monkeypatch):
    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)
    _snap(qapp, stub)
    (tmp_path / "ana.tex").write_text("yeni hâl\n", encoding="utf-8")
    _snap(qapp, stub)
    assert stub._output_panel._history_list.count() == 2

    monkeypatch.setattr(
        "gui.mixins.version_ops.QMessageBox.question",
        staticmethod(lambda *a, **k: 16384))  # Yes
    stub._on_version_action("drop", "herhangi")

    assert stub._output_panel._history_list.count() == 1
    assert "En yeni sürüm silindi" in stub._status.msg
    assert (tmp_path / "ana.tex").read_text(encoding="utf-8") == "yeni hâl\n"


# --- Fark görünümü renklendirme ---


def test_classify_diff_line():
    from gui.mixins.version_ops import classify_diff_line as cls
    assert cls("--- a/x.tex") == "hunk"
    assert cls("+++ b/x.tex") == "hunk"
    assert cls("@@ -1,2 +1,3 @@") == "hunk"
    assert cls("+eklenen") == "add"
    assert cls("-silinen") == "del"
    assert cls(" bağlam") == "ctx"


def test_build_diff_view_colors(qapp):
    from PyQt6.QtGui import QColor, QTextCursor
    from gui.theme import THEMES
    from gui.mixins.version_ops import build_diff_view

    diff = "--- a/x.tex\n+++ b/x.tex\n@@ -1 +1 @@\n-eski\n+yeni\n bağlam\n"
    view = build_diff_view(diff, THEMES["dark"])
    doc = view.document()

    def line_color(i):
        b = doc.findBlockByNumber(i)
        cur = QTextCursor(b)
        cur.movePosition(QTextCursor.MoveOperation.Right,
                         QTextCursor.MoveMode.KeepAnchor, 1)
        return cur.charFormat().foreground().color().name().lower()

    t = THEMES["dark"]
    assert line_color(0) == QColor(t["fg_muted"]).name().lower()        # --- hunk
    assert line_color(2) == QColor(t["fg_muted"]).name().lower()        # @@ hunk
    assert line_color(3) == QColor(t["sem_error"]).name().lower()       # - silinen
    assert line_color(4) == QColor(t["sem_compilable"]).name().lower()  # + eklenen
    assert line_color(5) == QColor(t["fg_primary"]).name().lower()      # bağlam
    assert doc.findBlockByNumber(3).text() == "-eski"


# --- Panel: clear() geçmişi korur ---


def test_panel_clear_keeps_history(qapp):
    from gui.theme import THEMES
    panel = OutputPanel(theme=THEMES["dark"])
    panel.show_history([V.VersionEntry(sha="a" * 40, timestamp=0,
                                       message="kayıt", nfiles=2)])
    panel.clear()
    assert panel._history_list.count() == 1


# --- Ctrl+K filtrede ---


def test_ctrl_k_handled_by_app_key_shortcut(qapp):
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtGui import QKeyEvent
    from gui.main_window import MainWindow

    calls = []
    mw = SimpleNamespace(
        _table_wizard=lambda: calls.append("t"),
        _toggle_comment=lambda: calls.append("c"),
        _on_esc=lambda: calls.append("esc"),
        _snapshot=lambda: calls.append("k"),
        _pdf_viewer=SimpleNamespace(in_presentation=False),
        _current_editor=lambda: None,
    )
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_K,
                   Qt.KeyboardModifier.ControlModifier, "k")
    assert MainWindow._handle_app_key_shortcut(mw, ev) is True
    assert calls == ["k"]


def test_snapshot_busy_iken_ikinci_cagri_reddedilir(qapp, tmp_path, monkeypatch):
    """İş sürerken ikinci Ctrl+K çift kayıt atmasın; 'bekle' mesajı versin."""
    import gui.mixins.version_ops as vo

    stub, ed, tex = _stub_with_editor(tmp_path, monkeypatch)

    gercek = vo.versioning.snapshot

    def yavas_snapshot(root, msg):
        time.sleep(0.4)
        return gercek(root, msg)

    monkeypatch.setattr(vo.versioning, "snapshot", yavas_snapshot)
    import threading
    _snap(qapp, stub)
    assert "Sürüm kaydedildi" in stub._status.msg
    assert stub._output_panel._history_list.count() == 1

    # ayni yavaslikla ikinci tur: is surerken (busy) ücüncü cagri red
    monkeypatch.setattr(vo.versioning, "snapshot", yavas_snapshot)
    ed.setText(ed.text() + "\n% baska satir\n")
    threading.Thread(target=stub._snapshot, daemon=True).start()
    deadline = time.monotonic() + 5
    while not getattr(stub, "_snapshot_busy", False) and time.monotonic() < deadline:
        qapp.processEvents(); time.sleep(0.01)
    assert stub._snapshot_busy, "arka plan isine gec girildi mi kontrol"
    stub._snapshot()
    assert "bekleyin" in stub._status.msg
    _snap(qapp, stub)   # gercek cagri zaten red edildi; busy'nin dusmesi bekle
    assert stub._output_panel._history_list.count() == 2
