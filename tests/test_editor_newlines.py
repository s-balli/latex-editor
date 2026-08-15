"""Kaydetmede satır sonu bütünlüğü — \\r\\r\\n bozulması regression'ı.

Windows'ta QScintilla CRLF metin üretebilir; Python text-mode yazımı da
\\n→\\r\\nl çevirince dosya her satırda \\r\\r\\n ile bitiyordu. TeX bunu
başıboş ^^M olarak okuyup 'Paragraph ended before \\IEEEpubid was complete'
tarzı 32 hatalık kaskatlar üretiyordu (gerçek vakayla teşhis edildi).
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_lf_file_stays_lf_after_save(qapp, tmp_path):
    f = tmp_path / "a.tex"
    f.write_bytes(b"line1\nline2\n\\begin{document}\nx\n\\end{document}\n")
    ed = EditorWidget()
    assert ed.open_file(str(f))
    ed.setText("line1\r\nline2\r\n\\begin{document}\r\ny\r\n\\end{document}\r\n")
    assert ed.save_file()
    data = f.read_bytes()
    assert b"\r" not in data, "LF dosya kayıtta CR kazanmamalı"
    assert data == b"line1\nline2\n\\begin{document}\ny\n\\end{document}\n"


def test_double_converted_buffer_not_double_spaced(qapp, tmp_path):
    """Arabellek \\r\\r\\n taşıyorsa kayıt ÇİFT SATIRA boğmamalı.

    Eski kaydetme \\r\\r\\n üretiyordu; bunu geri okuyup kaydettiğimizde
    yanlış sıralı replace dosyayı çift satırlı hale getiriyordu.
    """
    f = tmp_path / "a2.tex"
    f.write_bytes(b"line1\n\\begin{document}\nx\n\\end{document}\n")
    ed = EditorWidget()
    assert ed.open_file(str(f))
    ed.setText("line1\r\r\n\\begin{document}\r\r\ny\r\r\n\\end{document}\r\r\n")
    assert ed.save_file()
    assert f.read_bytes() == b"line1\n\\begin{document}\ny\n\\end{document}\n"


def test_crlf_file_roundtrip(qapp, tmp_path):
    f = tmp_path / "b.tex"
    f.write_bytes(b"line1\r\n\\begin{document}\r\nx\r\n\\end{document}\r\n")
    ed = EditorWidget()
    assert ed.open_file(str(f))
    assert ed._newline == "crlf"
    ed.setText("line1\r\n\\begin{document}\r\ny\r\n\\end{document}\r\n")
    assert ed.save_file()
    assert f.read_bytes() == b"line1\r\n\\begin{document}\r\ny\r\n\\end{document}\r\n"


def test_new_file_saved_as_lf(qapp, tmp_path):
    f = tmp_path / "c.tex"
    ed = EditorWidget()
    ed.setText("\\begin{document}\r\ny\r\n\\end{document}\r\n")
    assert ed.save_file_as(str(f))
    assert f.read_bytes() == b"\\begin{document}\ny\n\\end{document}\n"


def test_write_atomic_no_translation(qapp, tmp_path):
    """_write_atomic str dalı hiçbir örtük çevirim yapmamalı (rename akışları)."""
    f = tmp_path / "d.tex"
    EditorWidget._write_atomic(str(f), "a\r\nb\n")
    assert f.read_bytes() == b"a\r\nb\n"
