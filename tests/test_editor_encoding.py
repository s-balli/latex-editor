"""EditorWidget dosya kodlama testleri (A.3).

open_file eskiden errors='replace' ile okuyordu; bu, UTF-8 olmayan (ör. eski
Türkçe cp1254/iso-8859-9) dosyalardaki baytları sessizce U+FFFD ile değiştiriyor,
içeriği bozup kaydediyordu. Şimdi _decode_bytes önce UTF-8 (katı), sonra Türkçe
kodlamaları dener; her bayt tanımlı bir karaktere eşlenir, dosya açıldığı
kodlamayla kaydedilir (round-trip güvenli) ve kullanıcı uyarılır.
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
    from gui.editor import EditorWidget, _decode_bytes
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.editor import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _editor():
    return EditorWidget()


def _write_raw(path, raw: bytes):
    with open(path, "wb") as f:
        f.write(raw)


# --- _decode_bytes birim testleri ---


def test_decode_utf8():
    text = "Türkçe metin İğı"
    decoded, enc = _decode_bytes(text.encode("utf-8"))
    assert decoded == text
    assert enc == "utf-8"


def test_decode_cp1254_turkish():
    text = "Çığ ötüyor şoför İsmail"
    decoded, enc = _decode_bytes(text.encode("cp1254"))
    assert decoded == text
    assert enc == "cp1254"


def test_decode_no_silent_corruption():
    """cp1254 Türkçe dosya -> Türkçe harfler doğru (replacement char değil)."""
    text = "ĞİŞ çğıöşü"
    decoded, _ = _decode_bytes(text.encode("cp1254"))
    assert decoded == text            # bayt bozulması yok
    assert "�" not in decoded    # U+FFFD (sessiz değiştirme) yok


def test_decode_iso88599_text_correct():
    """iso-8859-9 dosya -> Türkçe harfler doğru (cp1254 ile aynı sonucu verir)."""
    text = "Öğretmen İşçi"
    decoded, _ = _decode_bytes(text.encode("iso-8859-9"))
    assert decoded == text


def test_decode_roundtrip_preserves_bytes():
    """decode -> dönen encoding ile re-encode baytları birebir korur."""
    text = "Mağaza İşi ğüş"
    for src_enc in ("cp1254", "iso-8859-9"):
        raw = text.encode(src_enc)
        decoded, enc = _decode_bytes(raw)
        assert decoded.encode(enc) == raw


# --- open_file entegrasyon ---


def test_open_utf8_sets_encoding(qapp, tmp_path):
    p = tmp_path / "a.tex"
    _write_raw(p, "Türkçe".encode("utf-8"))
    ed = _editor()
    assert ed.open_file(str(p)) is True
    assert ed._encoding == "utf-8"
    assert ed.text() == "Türkçe"


def test_open_cp1254_preserves_turkish(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = tmp_path / "legacy.tex"
    metin = "Çığ şoför İsmail"
    _write_raw(p, metin.encode("cp1254"))
    ed = _editor()
    assert ed.open_file(str(p)) is True
    assert ed.text() == metin          # Türkçe doğru (bozulma yok)
    assert ed._encoding == "cp1254"


def test_open_cp1254_warns_user(qapp, tmp_path, monkeypatch):
    """UTF-8 olmayan dosya açılınca kullanıcı uyarılmalı."""
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(True))
    p = tmp_path / "legacy.tex"
    _write_raw(p, "şoför".encode("cp1254"))
    ed = _editor()
    ed.open_file(str(p))
    assert warned == [True]


def test_open_utf8_no_warning(qapp, tmp_path, monkeypatch):
    """UTF-8 dosyada kodlama uyarısı olmamalı."""
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(True))
    p = tmp_path / "utf.tex"
    _write_raw(p, "şoför".encode("utf-8"))
    ed = _editor()
    ed.open_file(str(p))
    assert warned == []


def test_open_binary_rejected(qapp, tmp_path, monkeypatch):
    """Null bayt içeren (binary) dosya metin olarak açılmamalı."""
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    p = tmp_path / "bin.tex"
    _write_raw(p, b"\x00\x01\x02 binary \x00")
    ed = _editor()
    assert ed.open_file(str(p)) is False


# --- round-trip: aç -> kaydet -> baytlar korunur ---


def test_save_roundtrips_cp1254(qapp, tmp_path, monkeypatch):
    """cp1254 aç + kaydet -> diskteki baytlar aynı kalır."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = tmp_path / "rt.tex"
    metin = "Mağaza İşi ğüş"
    _write_raw(p, metin.encode("cp1254"))
    ed = _editor()
    ed.open_file(str(p))
    ed.save_file()
    with open(p, "rb") as f:
        assert f.read() == metin.encode("cp1254")


def test_save_file_as_resets_to_utf8(qapp, tmp_path, monkeypatch):
    """Farklı kaydet yeni dosyayı UTF-8 yapar."""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    p = tmp_path / "legacy.tex"
    _write_raw(p, "İş".encode("cp1254"))
    ed = _editor()
    ed.open_file(str(p))
    assert ed._encoding == "cp1254"

    newp = tmp_path / "new.tex"
    ed.save_file_as(str(newp))
    with open(newp, "rb") as f:
        assert f.read() == "İş".encode("utf-8")
    assert ed._encoding == "utf-8"
