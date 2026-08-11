"""EditorWidget atomik kayıt (save_file / _write_atomic) testleri.

Kayıt işleminin atomik olduğunu doğrular: yazma yarıda kalırsa orijinal dosya
korunur (truncate edilmez), geçici dosya geride kalmaz.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

_DESKTOP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "desktop"))
if _DESKTOP not in sys.path:
    sys.path.insert(0, _DESKTOP)

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor():
    return EditorWidget()


def _raise_oserror(*args, **kwargs):
    raise OSError("simulated failure")


# --- Başarı yolu ---


def test_save_writes_content(qapp, tmp_path):
    target = tmp_path / "doc.tex"
    target.write_text("ESKI", encoding="utf-8")
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("YENI ICERIK")
    assert ed.save_file() is True
    assert target.read_text(encoding="utf-8") == "YENI ICERIK"


def test_save_creates_new_file(qapp, tmp_path):
    target = tmp_path / "yeni.tex"
    assert not target.exists()
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("ilk icerik")
    assert ed.save_file() is True
    assert target.read_text(encoding="utf-8") == "ilk icerik"


def test_save_preserves_utf8_turkish(qapp, tmp_path):
    target = tmp_path / "tr.tex"
    ed = _editor()
    ed._file_path = str(target)
    metin = "Çığ Öğü Şoför İı, Türkçe karakterler"
    ed.setText(metin)
    ed.save_file()
    assert target.read_text(encoding="utf-8") == metin


def test_save_clears_modified_flag(qapp, tmp_path):
    target = tmp_path / "m.tex"
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("x")
    ed.setModified(True)
    ed.save_file()
    assert ed.isModified() is False


def test_no_tmp_left_after_success(qapp, tmp_path):
    target = tmp_path / "clean.tex"
    ed = _editor()
    ed._file_path = str(target)
    ed.setText("icerik")
    ed.save_file()
    assert not (tmp_path / "clean.tex.tmp").exists()


def test_save_as_sets_path_and_saves(qapp, tmp_path):
    target = tmp_path / "as.tex"
    ed = _editor()
    ed.setText("veri")
    ed.save_file_as(str(target))
    assert target.read_text(encoding="utf-8") == "veri"
    assert ed._file_path == os.path.normpath(str(target))


# --- Atomiklik: yazma/replace hatasında orijinal korunur ---


def test_write_atomic_preserves_original_on_replace_error(qapp, tmp_path, monkeypatch):
    """os.replace patlarsa orijinal dosya dokunulmamış kalmalı, .tmp temizlenmeli."""
    target = tmp_path / "doc.tex"
    target.write_text("ORIGINAL", encoding="utf-8")
    monkeypatch.setattr(os, "replace", _raise_oserror)

    ed = _editor()
    with pytest.raises(OSError):
        ed._write_atomic(str(target), "NEW")
    # Orijinal bozulmamış (truncate-on-open olmadığı için)
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
    # Geçici dosya temizlendi
    assert not (tmp_path / "doc.tex.tmp").exists()


def test_save_returns_false_and_keeps_original_on_error(qapp, tmp_path, monkeypatch):
    """save_file hatada False dönmeli, orijinali koruyarak (modal kutu açmadan)."""
    target = tmp_path / "doc.tex"
    target.write_text("ORIGINAL", encoding="utf-8")
    # Modal QMessageBox.critical'in testte bloklanmasını önle
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(os, "replace", _raise_oserror)

    ed = _editor()
    ed._file_path = str(target)
    ed.setText("NEW")
    assert ed.save_file() is False
    assert target.read_text(encoding="utf-8") == "ORIGINAL"
