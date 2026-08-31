"""Eski-PDF göstergesi testleri — başarısız derlemede bayat PDF göstermemek.

İki katman:
- core.compiler.LatexCompiler._on_finished: result.pdf_path yalnızca bu derlemenin
  ürettiği TAZE PDF için set edilir. exit != 0 olsa bile taze kısmi PDF iletilir;
  önceki derlemeden kalan eski PDF iletilmez. Tazelik ölçütü DUVAR SAATİ DEĞİL:
  dosyanın derleme öncesi/sonrası damgası (mtime_ns, boyut) karşılaştırılır,
  exit 0 ise derle.sh'nin sözleşmesine güvenilir. Eski ölçüt (mtime >= başlangıç)
  Windows'un saatiyle WSL'in saatini karşılaştırıyordu ve saat farkında taze
  PDF'i bayat sayıyordu (bkz. test_compiler.TestPdfTazelik).
- gui.mixins.compile_ops._on_compile_finished: taze PDF yoksa ve derleme başarısızsa
  viewer temizlenir (eski/tutarsız PDF ekranda kalmaz).
"""

import os
import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from core.compiler import LatexCompiler
    from core.log_parser import CompileResult
    from gui.mixins.compile_ops import CompileOpsMixin
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / core / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# compiler.py — taze vs bayat PDF belirleme
# =====================================================================


def _compiler(tex_dir, tex_name, *, onceki_pdf_vardi=False):
    """Derlemeye BAŞLAMIŞ bir compiler kur.

    ``onceki_pdf_vardi``: derleme başlarken o adda bir PDF diskte miydi?
    Tazelik kararı artık duvar saatiyle değil, dosyanın derleme ÖNCESİ
    damgasıyla (mtime_ns, boyut) karşılaştırılarak veriliyor — compile()
    bu damgayı alır, burada onu taklit ediyoruz.
    """
    c = LatexCompiler()
    c._tex_dir = str(tex_dir)
    c._tex_name = tex_name
    c._tex_path = os.path.join(str(tex_dir), tex_name + ".tex")
    c._start_time = time.time()
    pdf = os.path.join(str(tex_dir), tex_name + ".pdf")
    c._pdf_damgasi_once = c._pdf_damgasi(pdf) if onceki_pdf_vardi else None
    c._output = ""
    c._finished_emitted = False
    return c


def _pdf_yaz(tmp_path, ad, icerik):
    """PDF'i yaz ve damgasının kesin değişmesini garantile (boyut farklı)."""
    (tmp_path / (ad + ".pdf")).write_bytes(icerik)


def _finish(compiler, exit_code):
    captured = []
    compiler.compilation_finished.connect(lambda r: captured.append(r))
    compiler._on_finished(exit_code, None)
    return captured[0]


def test_fresh_pdf_success(tmp_path, qapp):
    """exit 0 + derlemenin ürettiği PDF → başarılı, pdf_path set."""
    c = _compiler(tmp_path, "doc")                 # başlarken PDF yoktu
    _pdf_yaz(tmp_path, "doc", b"%PDF-1.4 fresh")   # derleme üretti
    r = _finish(c, 0)
    assert r.success is True
    assert r.pdf_path.endswith("doc.pdf")


def test_partial_pdf_on_error(tmp_path, qapp):
    """exit != 0 ama derleme PDF'i DEĞİŞTİRDİ → başarısız AMA pdf_path set."""
    (tmp_path / "doc.pdf").write_bytes(b"%PDF onceki")
    c = _compiler(tmp_path, "doc", onceki_pdf_vardi=True)
    _pdf_yaz(tmp_path, "doc", b"%PDF partial, farkli boyut")   # kısmi çıktı
    r = _finish(c, 1)
    assert r.success is False
    assert r.pdf_path.endswith("doc.pdf")


def test_stale_pdf_not_communicated(tmp_path, qapp):
    """Başarısız derleme PDF'e DOKUNMADI → önceki derlemeden kalmadır, iletilmez.

    Ölçüt eskiden "mtime derleme başlangıcından sonra mı" idi; artık dosyanın
    derleme öncesi/sonrası damgası karşılaştırılıyor. Değişmemiş dosya bayattır.
    """
    (tmp_path / "doc.pdf").write_bytes(b"%PDF old from previous compile")
    c = _compiler(tmp_path, "doc", onceki_pdf_vardi=True)
    r = _finish(c, 1)                              # dosyaya dokunulmadı
    assert r.success is False
    assert r.pdf_path == ""


def test_no_pdf(tmp_path, qapp):
    """PDF hiç yok → pdf_path boş."""
    r = _finish(_compiler(tmp_path, "doc"), 1)
    assert r.success is False
    assert r.pdf_path == ""


def test_exit_sifir_derle_sh_sozlesmesiyle_kabul_edilir(tmp_path, qapp):
    """exit 0 → PDF taze sayılır, damga değişmemiş görünse bile.

    Bu, eski "exit 0 olsa bile PDF bayatsa başarısız" kuralının yerini aldı.
    Gerekçe derle.sh'nin sözleşmesi: sıfır YALNIZCA `$TMPDIR/$ISIM.pdf`
    bulunup `$KLASOR/$CIKTI_ISIM.pdf`e taşındıktan sonra dönüyor (PDF
    üretilmediyse "PDF olusmadi" + return 1) ve CIKTI_ISIM her zaman ISIM,
    yani compiler.py'nin baktığı yolun ta kendisi. Sıfır görüyorsak dosya bu
    koşunun ürünüdür.

    Eski kural pratikte ZARARLIYDI: tazeliği duvar saatiyle ölçtüğü için
    WSL/Windows saat farkında taze PDF'i bayat sayıp kullanıcıya "başarısız —
    0 hata" gösteriyordu (2026-08-31, gerçek hata raporu).
    """
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")
    c = _compiler(tmp_path, "doc", onceki_pdf_vardi=True)
    r = _finish(c, 0)
    assert r.success is True
    assert r.pdf_path.endswith("doc.pdf")


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


class _StubMain(StubMain):
    """MainWindow'un _on_compile_finished'inin ihtiyaç duyduğu minimum arayüz."""

    def __init__(self, tmp_path, load_ok=True):
        super().__init__(pdf_viewer=_StubViewer(load_ok))
        self._current_pdf = "/old/onceki-derleme.pdf"  # ekrandaki eski PDF
        self._synctex_dir = str(tmp_path)

    def _refresh_error_markers(self):
        pass


def test_clears_stale_pdf_on_total_failure(tmp_path, qapp):
    """Başarısız + taze PDF yok → eski PDF temizlenir."""
    stub = _StubMain(tmp_path)
    result = CompileResult(success=False, pdf_path="")  # derleme PDF üretmedi
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is True
    assert stub._current_pdf == ""
    assert "Basarisiz" in stub._status.msg


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
    assert "Basarisiz" in stub._status.msg


def test_success_loads_pdf_no_clear(tmp_path, qapp):
    """Başarılı → PDF yüklenir, temizlenmez."""
    fresh = tmp_path / "doc.pdf"
    fresh.write_bytes(b"%PDF full content")
    stub = _StubMain(tmp_path)
    result = CompileResult(success=True, pdf_path=str(fresh))
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is False
    assert stub._pdf_viewer.loaded == str(fresh)
    assert "Basarili" in stub._status.msg


def test_clears_when_load_fails(tmp_path, qapp):
    """Taze PDF var ama load_pdf başarısız → temizlenir, başarısız sayılır."""
    fresh = tmp_path / "doc.pdf"
    fresh.write_bytes(b"%PDF corrupt")
    stub = _StubMain(tmp_path, load_ok=False)
    result = CompileResult(success=True, pdf_path=str(fresh))
    CompileOpsMixin._on_compile_finished(stub, result)
    assert stub._pdf_viewer.cleared is True
    assert stub._current_pdf == ""
