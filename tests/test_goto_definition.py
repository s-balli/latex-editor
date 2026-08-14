"""Alt+tık ile \\ref/\\cite tanıma gitme testleri.

İki katman:
- gui.editor.EditorWidget._ref_cite_key_at: tıklanan konumdaki anahtarı çöz
- gui.main_window.MainWindow._on_goto_definition: anahtarın tanımına (file, line) zıpla
"""


import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# EditorWidget — tıklanan konumdaki \ref/\cite anahtarını çözme
# =====================================================================


def test_ref_key_hit(qapp):
    ed = EditorWidget()
    assert ed._ref_cite_key_at("Bak \\ref{fig:x} burada", 10) == ("fig:x", "label")


def test_ref_family_commands(qapp):
    ed = EditorWidget()
    for cmd in ("\\eqref{e}", "\\pageref{p}", "\\autoref{a}"):
        col = cmd.index('{') + 1   # argümanın içi
        assert ed._ref_cite_key_at(cmd, col)[1] == "label"


def test_cite_single_key(qapp):
    ed = EditorWidget()
    assert ed._ref_cite_key_at("\\cite{karaca2024}", 8) == ("karaca2024", "cite")


def test_cite_multi_key_picks_nearest(qapp):
    ed = EditorWidget()
    # \cite{a, b, c} — imleç 'b' segmentinde
    assert ed._ref_cite_key_at("\\cite{a, bb, c}", 9) == ("bb", "cite")


def test_cite_with_optional_args(qapp):
    ed = EditorWidget()
    # \citep[see][p. 5]{key1} — opsiyonel [...] argümanlar atlanmalı
    assert ed._ref_cite_key_at("\\citep[see][]{key1}", 16) == ("key1", "cite")


def test_no_key_outside_arg(qapp):
    ed = EditorWidget()
    assert ed._ref_cite_key_at("normal metin \\ref{x}", 5) is None


def test_bib_key_at(qapp):
    ed = EditorWidget()
    line = "@inproceedings{kazemi2025synthetic,"
    assert ed._bib_key_at(line, line.index("kazemi") + 3) == "kazemi2025synthetic"


def test_bib_key_outside(qapp):
    ed = EditorWidget()
    assert ed._bib_key_at("@article{k,}\n author={K},", 0) is None  # @ üzerinde, key değil


def test_bibitem_key_at(qapp):
    ed = EditorWidget()
    line = r"\bibitem{karaca2024} Karaca, 2024."
    assert ed._bibitem_key_at(line, line.index("karaca") + 2) == "karaca2024"


def test_bibitem_key_at_with_label(qapp):
    ed = EditorWidget()
    line = r"\bibitem[Hasan(2026)]{hasan2026} Hasan."
    assert ed._bibitem_key_at(line, line.index("hasan2026") + 2) == "hasan2026"


def test_nearest_key_segments(qapp):
    assert EditorWidget._nearest_key("a, b, c", 0) == "a"
    assert EditorWidget._nearest_key("a, b, c", 4) == "b"
    assert EditorWidget._nearest_key("a, b, c", 99) == "c"   # son segment


# =====================================================================
# MainWindow._on_goto_definition — tanıma zıplama (stub MainWindow)
# =====================================================================


from tests.stub_main import StubMain


class _StubMain(StubMain):
    """Paylaşımlı StubMain; sender() None döner → handler _current_editor()'e düşer."""

    def __init__(self, editor):
        super().__init__(editors=[editor])


def test_handler_jumps_to_label(tmp_path, qapp):
    main = tmp_path / "m.tex"
    main.write_text("\\section{X}\n\\label{fig:one}\n", encoding="utf-8")
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "fig:one", "label")
    assert stub.goto_calls == [(str(main), 2)]
    assert "Tanım" in stub._status.msg


def test_handler_label_in_input_child(tmp_path, qapp):
    child = tmp_path / "ch.tex"
    child.write_text("icerik\n\\label{eq:c}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\input{ch}\n", encoding="utf-8")
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "eq:c", "label")
    assert stub.goto_calls == [(str(child), 2)]


def test_handler_jumps_to_cite(tmp_path, qapp):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k2024,\n author={A},\n}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\bibliography{refs}\n\\cite{k2024}\n", encoding="utf-8")
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "k2024", "cite")
    assert stub.goto_calls == [(str(bib), 1)]


def test_handler_cite_fallback_to_bibitem(tmp_path, qapp):
    # .bib yok; el ile thebibliography + \bibitem var → \bibitem satırına atlar
    main = tmp_path / "m.tex"
    main.write_text(
        "Metin \\cite{k}.\n"
        "\\begin{thebibliography}{}\n"
        "\\bibitem{k} Yazar, Baslik.\n"
        "\\end{thebibliography}\n",
        encoding="utf-8",
    )
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "k", "cite")
    assert stub.goto_calls == [(str(main), 3)]


def test_handler_cite_prefers_bib_over_bibitem(tmp_path, qapp):
    # Hem .bib hem \bibitem varsa → .bib öncelikli (fallback devreye girmez)
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,\n}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text(
        "\\bibliography{refs}\n\\cite{k}\n\\bibitem{k} yazar\n",
        encoding="utf-8",
    )
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "k", "cite")
    assert stub.goto_calls == [(str(bib), 1)]


def test_handler_bibitem_to_cite(tmp_path, qapp):
    # .bib'in thebibliography'deki \bibitem'inden makaledeki \cite yerine (ters yön)
    main = tmp_path / "m.tex"
    main.write_text(
        "Giris \\cite{k}.\n"
        "\\begin{thebibliography}{}\n"
        "\\bibitem{k} Yazar.\n"
        "\\end{thebibliography}\n",
        encoding="utf-8",
    )
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "k", "cite-usage")
    assert stub.goto_calls == [(str(main), 1)]


def test_handler_not_found_shows_message(tmp_path, qapp):
    main = tmp_path / "m.tex"
    main.write_text("boss\n", encoding="utf-8")
    ed = EditorWidget()
    ed.setText(main.read_text(encoding="utf-8"))
    ed._file_path = str(main)

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "yok", "label")
    assert stub.goto_calls == []
    assert "bulunamadı" in stub._status.msg


def test_handler_cite_usage_bib_to_tex(tmp_path, qapp):
    # .bib editöründeyken cite-usage: girdiden makaledeki \cite yerine
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{k,\n author={A},\n}\n", encoding="utf-8")
    tex = tmp_path / "m.tex"
    tex.write_text("baslik\nGor bak \\citep{k}.\n", encoding="utf-8")
    ed = EditorWidget()
    ed.setText(bib.read_text(encoding="utf-8"))
    ed._file_path = str(bib)   # editör .bib'de

    stub = _StubMain(ed)
    MainWindow._on_goto_definition(stub, "k", "cite-usage")
    assert stub.goto_calls == [(str(tex), 2)]
