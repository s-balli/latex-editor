"""Eski-PDF göstergesi testleri — başarısız derlemede bayat PDF göstermemek.

İki katman:
- core.compiler.LatexCompiler._on_finished: result.pdf_path yalnızca bu derlemenin
  ürettiği TAZE PDF (mtime >= başlangıç) için set edilir. exit != 0 olsa bile taze
  kısmi PDF iletilir; önceki derlemeden kalan eski PDF iletilmez.
- gui.mixins.compile_ops._on_compile_finished: taze PDF yoksa ve derleme başarısızsa
  viewer temizlenir (eski/tutarsız PDF ekranda kalmaz).
"""

import os
import time
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from core.compiler import LatexCompiler
    from core.log_parser import CompileResult
    from gui.mixins.compile_ops import CompileOpsMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / core / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# compiler.py — taze vs bayat PDF belirleme
# =====================================================================


def _compiler(tex_dir, tex_name, start_offset):
    """start_offset: _start_time'nın şimdiki zamana göre offseti (saniye).
    Negatif = derleme geç başladı (PDF taze); pozitif = derleme gelecekte başladı (PDF bayat)."""
    c = LatexCompiler()
    c._tex_dir = str(tex_dir)
    c._tex_name = tex_name
    c._tex_path = os.path.join(str(tex_dir), tex_name + ".tex")
    c._start_time = time.time() + start_offset
    c._output = ""
    c._finished_emitted = False
    return c


def _finish(compiler, exit_code):
    captured = []
    compiler.compilation_finished.connect(lambda r: captured.append(r))
    compiler._on_finished(exit_code, None)
    return captured[0]


def test_fresh_pdf_success(tmp_path, qapp):
    """exit 0 + taze PDF → başarılı, pdf_path set."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF-1.4 fresh")
    r = _finish(_compiler(tmp_path, "doc", start_offset=-2), 0)
    assert r.success is True
    assert r.pdf_path.endswith("doc.pdf")


def test_partial_pdf_on_error(tmp_path, qapp):
    """exit != 0 ama taze (kısmi) PDF var → başarısız AMA pdf_path set (önizleme için)."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF partial")
    r = _finish(_compiler(tmp_path, "doc", start_offset=-2), 1)
    assert r.success is False
    assert r.pdf_path.endswith("doc.pdf")


def test_stale_pdf_not_communicated(tmp_path, qapp):
    """PDF derleme başlangıcından ÖNCE yazılmış (bayat) → pdf_path set EDİLMEZ."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF old from previous compile")
    r = _finish(_compiler(tmp_path, "doc", start_offset=+2), 1)
    assert r.success is False
    assert r.pdf_path == ""  # bayat PDF sonuç olarak iletilmez


def test_no_pdf(tmp_path, qapp):
    """PDF hiç yok → pdf_path boş."""
    r = _finish(_compiler(tmp_path, "doc", start_offset=-2), 1)
    assert r.success is False
    assert r.pdf_path == ""


def test_success_requires_fresh_pdf(tmp_path, qapp):
    """exit 0 olsa bile PDF bayatsa başarısız sayılır."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF old")
    r = _finish(_compiler(tmp_path, "doc", start_offset=+2), 0)
    assert r.success is False
    assert r.pdf_path == ""


# =====================================================================
# compile_ops — temizle / yükle davranışı (stub MainWindow)
# =====================================================================


class _StubViewer:
    def __init__(self, load_ok=True):
        self.load_ok = load_ok
        self.loaded = None
        self.cleared = False

    def load_pdf(self, path):
        self.loaded = path
        self.cleared = False
        return self.load_ok

    def clear(self):
        self.cleared = True
        self.loaded = None


class _StubMain:
    """MainWindow'un _on_compile_finished'inin ihtiyaç duyduğu minimum arayüz."""
    def __init__(self, tmp_path, load_ok=True):
        self._pdf_viewer = _StubViewer(load_ok)
        self._current_pdf = "/old/onceki-derleme.pdf"  # ekrandaki eski PDF
        self._synctex_dir = str(tmp_path)
        self._progress = SimpleNamespace(hide=lambda: None)
        self._status = SimpleNamespace(showMessage=self._set_msg)
        self._output_panel = SimpleNamespace(
            show_result=lambda r: None, show_engine_hint=lambda a, b: None
        )
        self._engine_combo = SimpleNamespace(currentText=lambda: "lualatex")
        self._compile_target = ""
        self.last_msg = ""

    def _set_msg(self, msg):
        self.last_msg = msg

    def setCursor(self, *_a, **_k):
        pass

    def _current_editor(self):
        return None

    def _refresh_error_markers(self):
        pass


def test_clears_stale_pdf_on_total_failure(tmp_path, qapp):
    """Başarısız + taze PDF yok → eski PDF temizlenir."""
    stub = _StubMain(tmp_path)
    result = CompileResult(success=False, pdf_path="")  # derleme PDF üretmedi
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is True
    assert stub._current_pdf == ""
    assert "Basarisiz" in stub.last_msg


def test_loads_partial_pdf_on_failure(tmp_path, qapp):
    """Başarısız ama taze kısmi PDF var → PDF yüklenir, TEMİZLENMEZ."""
    fresh = tmp_path / "doc.pdf"
    fresh.write_bytes(b"%PDF partial content")
    stub = _StubMain(tmp_path)
    result = CompileResult(success=False, pdf_path=str(fresh))
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is False
    assert stub._pdf_viewer.loaded == str(fresh)
    assert stub._current_pdf == str(fresh)
    assert "Basarisiz" in stub.last_msg


def test_success_loads_pdf_no_clear(tmp_path, qapp):
    """Başarılı → PDF yüklenir, temizlenmez."""
    fresh = tmp_path / "doc.pdf"
    fresh.write_bytes(b"%PDF full content")
    stub = _StubMain(tmp_path)
    result = CompileResult(success=True, pdf_path=str(fresh))
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is False
    assert stub._pdf_viewer.loaded == str(fresh)
    assert "Basarili" in stub.last_msg


def test_clears_when_load_fails(tmp_path, qapp):
    """Taze PDF var ama load_pdf başarısız → temizlenir, başarısız sayılır."""
    fresh = tmp_path / "doc.pdf"
    fresh.write_bytes(b"%PDF corrupt")
    stub = _StubMain(tmp_path, load_ok=False)
    result = CompileResult(success=True, pdf_path=str(fresh))
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is True
    assert stub._current_pdf == ""
