"""EditorWidget atomik kayıt (save_file / _write_atomic) testleri.

Kayıt işleminin atomik olduğunu doğrular: yazma yarıda kalırsa orijinal dosya
korunur (truncate edilmez), geçici dosya geride kalmaz.
"""

import os

import pytest

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


def test_basarisiz_save_file_as_eski_kimligi_koruyor(qapp, tmp_path, monkeypatch):
    """Başarısız 'Farklı Kaydet' editörü var olmayan hedefe bağlamamalı (A3).

    save_file_as üç alanı (yol, kodlama, satır sonu) yazma DENENMEDEN
    atıyordu. Yazma başarısız olunca eski yol ve legacy kodlama geri
    alınamaz biçimde kayboluyor, Ctrl+S kalıcı olarak yazılamayan hedefe
    gitmeye devam ediyordu.
    """
    kaynak = tmp_path / "eski.tex"
    kaynak.write_bytes("Türkçe içerik\n".encode("cp1254"))

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    ed = _editor()
    assert ed.open_file(str(kaynak)) is True
    assert ed._encoding == "cp1254"

    def _patlat(path, text, enc):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(EditorWidget, "_write_atomic", staticmethod(_patlat))

    hedef = tmp_path / "yeni.tex"
    assert ed.save_file_as(str(hedef)) is False
    assert ed.file_path == str(kaynak), "editör var olmayan hedefe bağlandı"
    assert ed._encoding == "cp1254", "legacy kodlama kayboldu"
    assert ed._newline == "lf"
    assert not hedef.exists()


def test_basarili_save_file_as_yeni_kimligi_aliyor(qapp, tmp_path, monkeypatch):
    """Geri alma yolu başarılı durumu bozmamalı."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    kaynak = tmp_path / "a.tex"
    kaynak.write_text("icerik\n", encoding="utf-8")

    ed = _editor()
    assert ed.open_file(str(kaynak)) is True

    hedef = tmp_path / "b.tex"
    assert ed.save_file_as(str(hedef)) is True
    assert ed.file_path == str(hedef)
    assert ed._encoding == "utf-8"
    assert hedef.read_text(encoding="utf-8") == "icerik\n"
