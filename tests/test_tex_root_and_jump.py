"""% !TEX root magic comment + derleme sonrası otomatik SyncTeX ileri-arama.

- compile_ops: alt dosya derlenirken '% !TEX root' işaretli köke yönlendirme,
  motorda kökten algılama, açık kök/alt sekmelerinin kaydı
- compile_ops + synctex_ops: başarılı derleme sonrası imleç konumuna otomatik
  ileri-arama (quiet: durum mesajı ezilmez); başarısız derlemede atlama yok
"""

import os
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.compile_ops import CompileOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from gui.mixins.synctex_ops import SyncTexMixin
    from core.log_parser import CompileResult
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _RecCompiler:
    def __init__(self):
        self.calls = []
        self.se = []

    def is_busy(self):
        return False  # LatexCompiler dublörü: gerçek sınıfın meşgul guard API'si

    def compile(self, path, engine, shell_escape=None):
        self.calls.append((os.path.normpath(path), engine))
        self.se.append(shell_escape)
        return True


class _RecWorker:
    def __init__(self):
        self.calls = []

    def submit(self, kind, args, synctex_dir, context=None):
        self.calls.append((kind, args, synctex_dir, context))


class _StubViewer:
    def __init__(self):
        self.loaded = None
        self.scrolled = None

    def load_pdf(self, path):
        self.loaded = path
        return True

    def clear(self):
        self.loaded = None

    def scroll_to_position(self, *a):
        self.scrolled = a


class _Stub(CompileOpsMixin, TabOpsMixin, SyncTexMixin, StubMain):
    def __init__(self, editors, synctex_dir, engine="pdflatex"):
        StubMain.__init__(self, editors=editors, pdf_viewer=_StubViewer(), engine=engine)
        self._synctex_dir = synctex_dir
        self._synctex_worker = _RecWorker()
        self._compiler = _RecCompiler()
        self._compile_cursor_ctx = None

    def _refresh_error_markers(self):
        pass


def _project(tmp_path):
    """Kök + % !TEX root işaretli alt dosya projesi kur; yolları döndür."""
    root = tmp_path / "tez.tex"
    root.write_text("\\documentclass{article}\n\\usepackage{fontspec}\n"
                    "\\begin{document}\n\\input{bolum1}\n\\end{document}\n", encoding="utf-8")
    child = tmp_path / "bolum1.tex"
    child.write_text("% !TEX root = tez.tex\nbölüm metni\n", encoding="utf-8")
    return root, child


def _editor_for(path):
    ed = EditorWidget()
    ed.open_file(str(path))
    return ed


# =====================================================================
# % !TEX root: derleme hedefi köke yönlendirilir
# =====================================================================


def test_child_compiles_root_with_root_engine(qapp, tmp_path):
    """Alt dosyadan Ctrl+B → kök derlenir; motor KÖKÜN içeriğinden (fontspec →
    lualatex), combo'dan değil."""
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    assert stub._compiler.calls == [(str(root), "lualatex")]
    assert stub._compile_target == str(root)
    # imleç bağlamı ALT dosyadadır (SyncTeX girdi-dosyası bazlıdır)
    assert stub._compile_cursor_ctx[0] == str(child)


def test_standalone_file_compiles_itself(qapp, tmp_path):
    """Doğrudan derlenebilir dosya → kendisi derlenir, combo motoru geçerli kalır."""
    root, _child = _project(tmp_path)
    ed = _editor_for(root)
    stub = _Stub([ed], str(tmp_path), engine="pdflatex")

    stub._compile()
    assert stub._compiler.calls == [(str(root), "pdflatex")]


def test_child_without_root_rejected(qapp, tmp_path):
    child = tmp_path / "parca.tex"
    child.write_text("yalnızca parça, kök işareti yok\n", encoding="utf-8")
    ed = _editor_for(child)
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    assert stub._compiler.calls == []
    assert "derlenemez" in stub._status.msg


def test_compile_file_from_tree_redirects_to_root(qapp, tmp_path):
    root, child = _project(tmp_path)
    stub = _Stub([], str(tmp_path))  # alt dosya sekmede değil

    stub._compile_file(str(child))
    assert stub._compiler.calls == [(str(root), "lualatex")]
    # Sekmede açık değilse imleç bağlamı yoktur → otomatik atlama yapılmaz
    assert stub._compile_cursor_ctx is None


def test_modified_root_tab_saved_before_compile(qapp, tmp_path):
    root, child = _project(tmp_path)
    root_ed = _editor_for(root)
    root_ed.setText(root_ed.text() + "\n% değişiklik")
    root_ed.setModified(True)
    child_ed = _editor_for(child)
    stub = _Stub([child_ed, root_ed], str(tmp_path), engine="pdflatex")

    stub._compile()
    assert root_ed.isModified() is False, "açık kök sekmesi derlemeden önce kaydedilmeli"
    assert stub._compiler.calls == [(str(root), "lualatex")]


# =====================================================================
# Derleme sonrası otomatik ileri-arama
# =====================================================================


def _finished_ctx(tmp_path, success=True):
    """Başarılı derleme bitişi için gerekli dosyaları (PDF + synctex.gz) kur."""
    pdf = tmp_path / "tez.pdf"
    pdf.write_bytes(b"%PDF-1.4 content")
    gz = tmp_path / "tez.synctex.gz"
    gz.write_bytes(b"fake")
    result = CompileResult(success=success, pdf_path=str(pdf) if success else str(pdf))
    result.duration = 0.1
    return result


def test_ilk_derlemede_atlama_yok(qapp, tmp_path):
    """İlk derlemede PDF baştan açılmalı, imlece atlanmamalı.

    Atlamanın amacı yazarken BULUNDUĞUN yeri korumak; belgeyi ilk kez
    derlerken korunacak bir konum yok. Belgeyi baştan aşağı yazan kullanıcı
    imleci en altta bıraktığı için PDF son sayfada açılıyordu (kullanıcı
    bildirimi, 2026-09-02: "ilk açıp derleyince son sayfaya atıyor; sonra
    imleci değiştirince davranış doğru").
    """
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed.setCursorPosition(1, 0)
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

    assert stub._pdf_viewer.loaded == str(tmp_path / "tez.pdf")
    assert stub._synctex_worker.calls == [], "ilk derlemede atlama olmamalı"


def test_successful_compile_auto_jumps_to_cursor(qapp, tmp_path):
    """İKİNCİ derlemeden itibaren imleç konumuna ileri-arama gönderilir."""
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed.setCursorPosition(1, 0)
    stub = _Stub([ed], str(tmp_path))

    # İlk derleme: PDF ilk kez gösteriliyor, atlama yok
    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))
    assert stub._synctex_worker.calls == []

    # İkinci derleme: davranış eskisi gibi
    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

    assert stub._pdf_viewer.loaded == str(tmp_path / "tez.pdf")
    assert len(stub._synctex_worker.calls) == 1
    kind, args, synctex_dir, context = stub._synctex_worker.calls[0]
    assert kind == "forward"
    assert args[0] == str(child)          # girdi dosyası: alt dosya
    assert args[1] == 2                   # satır 1 (0-based) → 1-based 2
    assert args[3] == str(tmp_path / "tez.pdf")
    assert context[2] is True             # quiet: status ezilmez


def test_failed_compile_does_not_auto_jump(qapp, tmp_path):
    """Başarısız derleme → otomatik atlama yok (odak hatalardadır)."""
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    result = _finished_ctx(tmp_path, success=True)
    result.success = False
    result.pdf_path = ""
    stub._on_compile_finished(result)

    assert stub._synctex_worker.calls == []


def test_quiet_forward_keeps_status_message(qapp, tmp_path):
    """quiet ileri-arama sonucu PDF'i kaydırır ama 'Başarılı' mesajını ezmez."""
    stub = _Stub([], str(tmp_path))
    stub._status.msg = "Başarılı (1.2s)"
    fake = SimpleNamespace(page=5, x=100.0, y=200.0, left=0.0, width=10.0, height=8.0)
    stub._apply_forward(fake, ("/tmp/x.tex", 12, True))
    assert stub._pdf_viewer.scrolled is not None
    assert stub._status.msg == "Başarılı (1.2s)"

    # quiet değilse mesaj gösterilir (Ctrl+tık davranışı korunur)
    stub._apply_forward(fake, ("/tmp/x.tex", 12, False))
    assert "SyncTeX" in stub._status.msg
