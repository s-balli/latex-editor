"""Ctrl+P hızlı dosya açma — koleksiyon, bulanık eşleşme, dialog davranışı."""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from gui.mixins.file_ops import FileOpsMixin
    from gui.quick_open import QuickOpenDialog, collect_project_files, fuzzy_score
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --- collect_project_files ---


def test_collect_filters_and_sorts(tmp_path):
    (tmp_path / "main.tex").write_text("x")
    (tmp_path / "refs.bib").write_text("x")
    sub = tmp_path / "bolum"
    sub.mkdir()
    (sub / "giris.tex").write_text("x")
    (tmp_path / "sekil.png").write_bytes(b"")      # uzantı dışı → listede yok
    hid = tmp_path / ".git"
    hid.mkdir()
    (hid / "gizli.tex").write_text("x")            # gizli dizin → yok
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "paket.sty").write_text("x")             # skip dizini → yok (dosya ağacıyla aynı kural)
    rels = collect_project_files(str(tmp_path))
    assert rels == ["bolum/giris.tex", "main.tex", "refs.bib"]


# --- fuzzy_score ---


def test_fuzzy_empty_query_matches_all():
    assert fuzzy_score("", "her/yol.tex") == 0


def test_fuzzy_subsequence_and_basename_bonus():
    # 'mt' main.tex'in dosya adında başlıyor → bonus (daha küçük skor)
    assert fuzzy_score("mt", "main.tex") < fuzzy_score("mt", "bolum/diğer-m-t.tex")


def test_fuzzy_tight_path_match_beats_wide_basename_match():
    """Bonus küçük bir ödüldür; yayılım (spread) farkını ezemez.

    'mt' dar biçimde yol (dizin) kısmında eşleşirken (yayılım 1), geniş
    biçimde dosya adında eşleşen adaydan (yayılım ~12) ÖNDE sıralanmalı.
    Bonus büyütülürse (örn. -5 yerine -50) sıralama tersine döner; bu test
    büyüklüğü pinler (mutasyonla doğrulandı: -50 kırmızı görür).
    """
    tight_path = fuzzy_score("mt", "mt/xx.tex")             # yayılım 1, bonus yok
    wide_name = fuzzy_score("mt", "src/m___________t.tex")  # yayılım ~12, bonuslu
    assert tight_path < wide_name


def test_fuzzy_case_insensitive():
    assert fuzzy_score("MT", "main.tex") is not None


def test_fuzzy_no_match():
    assert fuzzy_score("zzz", "main.tex") is None


# --- dialog ---


def test_dialog_filters_and_selects(qapp, tmp_path):
    (tmp_path / "main.tex").write_text("x")
    (tmp_path / "makale.tex").write_text("x")
    dlg = QuickOpenDialog(str(tmp_path))
    assert dlg._list.count() == 2
    dlg._edit.setText("mak")
    assert dlg._list.count() == 1
    assert dlg._list.currentItem().text() == "makale.tex"
    assert dlg.selected_path().endswith("makale.tex")
    assert os.path.normpath(dlg.selected_path()) == dlg.selected_path()


def test_dialog_keyboard_navigation(qapp, tmp_path):
    (tmp_path / "a.tex").write_text("x")
    (tmp_path / "b.tex").write_text("x")
    (tmp_path / "c.tex").write_text("x")
    dlg = QuickOpenDialog(str(tmp_path))
    assert dlg._list.currentRow() == 0
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert dlg.eventFilter(dlg._edit, ev) is True
    assert dlg._list.currentRow() == 1


# --- MainWindow._quick_open handler ---


class _StubQuick(FileOpsMixin, StubMain):
    def __init__(self, root):
        super().__init__()
        self._file_tree = SimpleNamespace(_root=root)
        self.opened = []

    def _open_file_in_editor(self, path):
        self.opened.append(path)


def test_quick_open_handler_opens_picked(qapp, tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text("x")
    stub = _StubQuick(str(tmp_path))
    with patch("gui.quick_open.QuickOpenDialog.pick", return_value=str(tex)):
        MainWindow._quick_open(stub)
    assert stub.opened == [str(tex)]


def test_quick_open_without_folder(qapp):
    stub = _StubQuick("")
    MainWindow._quick_open(stub)
    assert stub.opened == []
    assert "klasör açın" in stub._status.msg
