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


def test_dokunulmamis_imlecle_ilk_derleme_basta_aciliyor(qapp, tmp_path):
    """Dosyayı açıp HİÇBİR ŞEY yapmadan derleyen kullanıcı başı görmeli.

    Atlamanın amacı yazarken bulunduğun yeri korumak; dosyaya hiç
    dokunulmadıysa korunacak bir konum yok ve doğal beklenti PDF'in baştan
    açılması (kullanıcı bildirimi, 2026-09-02).
    """
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed.setCursorPosition(1, 0)
    ed._ilk_imlec = ed.getCursorPosition()      # açılıştaki konum
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

    assert stub._pdf_viewer.loaded == str(tmp_path / "tez.pdf")
    assert stub._synctex_worker.calls == [], "dokunulmamış imleçte atlama olmamalı"


def test_ilk_derlemede_de_imlec_TASINDIYSA_atliyor(qapp, tmp_path):
    """İmleci bilerek bir satıra götürüp derleyen oraya gitmek istiyor.

    Ayırt edici şey "ilk derleme" DEĞİL, imlecin taşınmış olması.
    """
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed._ilk_imlec = ed.getCursorPosition()      # açılıştaki konum
    ed.setCursorPosition(1, 0)                  # kullanıcı imleci taşıdı
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

    assert len(stub._synctex_worker.calls) == 1
    kind, args, _sd, _ctx = stub._synctex_worker.calls[0]
    assert kind == "forward"
    assert args[1] == 2                         # satır 1 (0-based) → 1-based 2


def test_successful_compile_auto_jumps_to_cursor(qapp, tmp_path):
    """İkinci derlemeden itibaren imleç dokunulmamış olsa da atlanır.

    O noktada PDF zaten bir kez gösterilmiştir: korunacak bir konum vardır.
    """
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed.setCursorPosition(1, 0)
    ed._ilk_imlec = ed.getCursorPosition()
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))
    assert stub._synctex_worker.calls == []

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

    assert stub._pdf_viewer.loaded == str(tmp_path / "tez.pdf")
    assert len(stub._synctex_worker.calls) == 1


def test_baslangic_konumu_bilinmiyorsa_atliyor(qapp, tmp_path):
    """`_ilk_imlec` yoksa "dokunuldu" sayılmalı: var olan özellik korunur.

    Emin olunamayan durumda atlamayı KAPATMAK, tanıtılan bir davranışı
    sessizce kaybettirirdi.
    """
    root, child = _project(tmp_path)
    ed = _editor_for(child)
    ed.setCursorPosition(1, 0)
    assert not hasattr(ed, "_ilk_imlec")
    stub = _Stub([ed], str(tmp_path))

    stub._compile()
    stub._on_compile_finished(_finished_ctx(tmp_path, success=True))

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


# =====================================================================
# `.synctex.gz` on kosulu IKI YONDE de denetlenmeli (2026-09-06)
#
# `_on_forward_search` iki kapi tasiyordu (PDF var mi, .gz var mi);
# `_on_reverse_search` yalniz birincisini. Olculdu: .gz yokken ters arama
# isciye is GONDERIYOR, yani bir synctex/WSL sureci bosuna basliyor (bu
# modulun basligi "Windows'ta WSL soguk baslangici 1-3 sn surebilir" diyor)
# ve sonuc None donunce kullaniciya "Eslesme bulunamadi" yaziliyordu.
# Yanlis mesaj: kullanici konumu yanlis saniyor, oysa yapmasi gereken
# derlemek. Ileri arama bu dersi zaten biliyordu.
#
# Denetim `_synctex_gz_var_mi` ile TEK KAYNAGA alindi; asagidaki kapi iki
# yonu de ayni onkosula bagliyor, yani yeniden ayrisma sessiz kalmaz.
# =====================================================================


def _pdf_ve_gz(tmp_path, ad="main", gz=True):
    """PDF + (istege bagli) .synctex.gz kur; (stub, pdf_yolu) dondur."""
    sdir = tmp_path / "synctex"
    sdir.mkdir(exist_ok=True)
    pdf = tmp_path / (ad + ".pdf")
    pdf.write_bytes(b"%PDF-1.4\n")
    g = sdir / (ad + ".synctex.gz")
    if gz:
        g.write_bytes(b"x")
    elif g.exists():
        g.unlink()
    stub = _Stub([], str(sdir))
    stub._current_pdf = str(pdf)
    return stub, str(pdf)


def test_gz_YOKKEN_ters_arama_isci_calistirmiyor(qapp, tmp_path):
    """Kirilirsa: ters arama yine bosuna synctex/WSL sureci basliyor."""
    stub, pdf = _pdf_ve_gz(tmp_path, "a", gz=False)
    stub._on_reverse_search(1, 100.0, 200.0, pdf)
    assert stub._synctex_worker.calls == [], "gz yokken isciye is gonderildi"
    assert "yeniden derleyin" in stub._status.msg, stub._status.msg


def test_gz_YOKKEN_iki_yon_de_AYNI_davraniyor(qapp, tmp_path):
    """Tek kaynak kapisi: onkosul yine ayrisirsa burasi kirilir."""
    ileri, pdf1 = _pdf_ve_gz(tmp_path, "b", gz=False)
    ileri._on_forward_search(str(tmp_path / "x.tex"), 5, 1)
    ileri_mesaj = ileri._status.msg

    ters, pdf2 = _pdf_ve_gz(tmp_path, "c", gz=False)
    ters._on_reverse_search(1, 1.0, 1.0, pdf2)

    assert ileri._synctex_worker.calls == []
    assert ters._synctex_worker.calls == []
    assert ters._status.msg == ileri_mesaj, (ters._status.msg, ileri_mesaj)


def test_gz_VARKEN_iki_yon_de_CALISIYOR(qapp, tmp_path):
    """Asiri duzeltme kapisi: denetim gecerli durumu engellememeli."""
    stub, pdf = _pdf_ve_gz(tmp_path, "d", gz=True)
    stub._on_forward_search(str(tmp_path / "x.tex"), 5, 1)
    stub._on_reverse_search(2, 10.0, 20.0, pdf)
    assert [c[0] for c in stub._synctex_worker.calls] == ["forward", "reverse"]
    # Ters isin context'i sayfa numarasi (sonucun dogru etikete uygulanmasi)
    assert stub._synctex_worker.calls[1][3] == 2


def test_gercek_ESLESMESIZLIK_mesaji_yerinde_duruyor(qapp, tmp_path):
    """`.gz` varken eslesme yoksa dogru mesaj yine 'Eslesme bulunamadi'."""
    stub, pdf = _pdf_ve_gz(tmp_path, "e", gz=True)
    stub._apply_reverse(None, 3)
    assert "Eşleşme bulunamadı" in stub._status.msg, stub._status.msg


@pytest.mark.parametrize("ad", ["ana.belge.v2", "a b c"])
def test_gz_adi_NOKTALI_ve_BOSLUKLU_dosyada_da_bulunuyor(qapp, tmp_path, ad):
    """`splitext` yalniz SON uzantiyi atmali; bosluklu ad da bozmamali."""
    stub, pdf = _pdf_ve_gz(tmp_path, ad, gz=True)
    stub._on_reverse_search(1, 1.0, 1.0, pdf)
    assert len(stub._synctex_worker.calls) == 1, stub._status.msg


@pytest.mark.parametrize("yol", ["", "olmayan.pdf"])
def test_PDF_yoksa_ters_arama_sessizce_atlaniyor(qapp, tmp_path, yol):
    """Onceki kapi korunuyor: PDF yoksa mesaj bile gosterilmiyor."""
    stub, _pdf = _pdf_ve_gz(tmp_path, "f", gz=True)
    stub._status.msg = "degismedi"
    stub._on_reverse_search(1, 1.0, 1.0,
                            str(tmp_path / yol) if yol else "")
    assert stub._synctex_worker.calls == []
    assert stub._status.msg == "degismedi"
