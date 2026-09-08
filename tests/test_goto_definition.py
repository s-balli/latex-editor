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


# =====================================================================
# JESTİN KENDİSİ: Ctrl+tık ve Alt+tık dağıtımı
#
# Anahtar çözme (`_ref_cite_key_at`, `_bib_key_at`, `_bibitem_key_at`) ve
# hedefe zıplama (`_on_goto_definition`) yukarıda test ediliyor; ARADAKİ
# katman, yani `mousePressEvent`in tıklanan noktayı satır/sütuna çevirip
# doğru sinyali yayması, HİÇ koşmuyordu (kapsam ölçümü: 40 satır). Bir
# yeniden düzenleme Ctrl+tık'ı sessizce kırsa hiçbir test yanmazdı.
#
# Offscreen platformda nokta<->konum dönüşümü çalışıyor (ölçüldü: konum 56
# -> (252, 28) -> 56), o yüzden jest GERÇEK QMouseEvent ile sınanıyor.
# =====================================================================

import os  # noqa: E402

from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402


@pytest.fixture
def tiklanabilir(qapp, tmp_path):
    """Açık bir editör ve "şu metne şu değiştiriciyle tıkla" yardımcısı."""
    acilanlar = []

    def _kur(icerik, ad="ana.tex"):
        yol = tmp_path / ad
        yol.write_text(icerik, encoding="utf-8")
        ed = EditorWidget()
        assert ed.open_file(str(yol))
        ed.resize(900, 400)
        ed.show()
        qapp.processEvents()
        acilanlar.append(ed)

        ileri, tanim = [], []
        ed.forward_search_requested.connect(lambda *a: ileri.append(a))
        ed.goto_definition_requested.connect(lambda *a: tanim.append(a))

        def _tikla(satir, parca, mods=Qt.KeyboardModifier.NoModifier,
                   kaydir=1):
            """`parca`nin `kaydir`. karakterine tikla."""
            metin = ed.text(satir)
            sutun = metin.index(parca) + kaydir
            pos = ed.positionFromLineIndex(satir, sutun)
            x = ed.SendScintilla(ed.SCI_POINTXFROMPOSITION, 0, pos)
            y = ed.SendScintilla(ed.SCI_POINTYFROMPOSITION, 0, pos)
            assert ed.SendScintilla(ed.SCI_POSITIONFROMPOINT, int(x),
                                    int(y)) == pos, \
                "nokta<->konum donusumu tutmadi, test bir sey olcmuyor"
            ileri.clear()
            tanim.clear()
            ed.mousePressEvent(QMouseEvent(
                QMouseEvent.Type.MouseButtonPress, QPointF(x, y),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))
            return ileri, tanim

        return ed, _tikla, str(yol)

    yield _kur

    for ed in acilanlar:
        ed.deleteLater()
    from PyQt6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


_BELGE = ("\\documentclass{article}\n"
          "\\begin{document}\n"
          "Sekil \\ref{fig:bir} ve \\cite{kaynak2020}\n"
          "\\end{document}\n")


def test_CTRL_tik_ileri_arama_yayiyor(tiklanabilir):
    """Kırılırsa Ctrl+tık ile PDF'e gitme sessizce ölür."""
    _ed, tikla, yol = tiklanabilir(_BELGE)

    ileri, tanim = tikla(2, "fig:bir", Qt.KeyboardModifier.ControlModifier)

    assert len(ileri) == 1, ileri
    gelen_yol, satir, sutun = ileri[0]
    assert os.path.normpath(gelen_yol) == os.path.normpath(yol)
    # SyncTeX 1 TABANLI: satır/sütun bir artırılmış gelmeli
    assert satir == 3, satir
    assert sutun == _BELGE.splitlines()[2].index("fig:bir") + 2
    assert tanim == []


def test_ALT_tik_ref_uzerinde_tanima_gidiyor(tiklanabilir):
    _ed, tikla, _yol = tiklanabilir(_BELGE)

    _ileri, tanim = tikla(2, "fig:bir", Qt.KeyboardModifier.AltModifier)

    assert tanim == [("fig:bir", "label")], tanim


def test_ALT_tik_cite_uzerinde_tanima_gidiyor(tiklanabilir):
    _ed, tikla, _yol = tiklanabilir(_BELGE)

    _ileri, tanim = tikla(2, "kaynak2020", Qt.KeyboardModifier.AltModifier)

    assert tanim == [("kaynak2020", "cite")], tanim


def test_ALT_tik_BIB_dosyasinda_TERS_yon(tiklanabilir):
    """`.bib` içinde Alt+tık, girdinin makalede `\\cite` edildiği yere gider."""
    _ed, tikla, _yol = tiklanabilir(
        "@article{karaca2024,\n  title = {Bir},\n}\n", ad="kaynaklar.bib")

    _ileri, tanim = tikla(0, "karaca2024", Qt.KeyboardModifier.AltModifier)

    assert tanim == [("karaca2024", "cite-usage")], tanim


def test_DUZ_tik_hicbir_sinyal_yaymiyor(tiklanabilir):
    """Aşırı düzeltme kapısı: değiştiricisiz tıklama sıradan imleç
    hareketidir, jest değil."""
    _ed, tikla, _yol = tiklanabilir(_BELGE)

    ileri, tanim = tikla(2, "fig:bir")

    assert ileri == [] and tanim == []


def test_ALT_tik_ANAHTAR_DISINDA_sinyal_yaymiyor(tiklanabilir):
    """Aşırı düzeltme kapısı: sıradan metne Alt+tık bir şey yapmamalı."""
    _ed, tikla, _yol = tiklanabilir(_BELGE)

    _ileri, tanim = tikla(2, "Sekil", Qt.KeyboardModifier.AltModifier)

    assert tanim == []


def test_YOLSUZ_tamponda_jest_calismiyor(qapp):
    """Kaydedilmemiş tamponun SyncTeX'te karşılığı yok; jest sessiz kalmalı
    (`self._file_path` denetimi)."""
    ed = EditorWidget()
    try:
        ed.setText("Sekil \\ref{fig:bir}\n")
        ed.resize(900, 200)
        ed.show()
        qapp.processEvents()
        ileri, tanim = [], []
        ed.forward_search_requested.connect(lambda *a: ileri.append(a))
        ed.goto_definition_requested.connect(lambda *a: tanim.append(a))
        pos = ed.positionFromLineIndex(0, 13)
        x = ed.SendScintilla(ed.SCI_POINTXFROMPOSITION, 0, pos)
        y = ed.SendScintilla(ed.SCI_POINTYFROMPOSITION, 0, pos)

        for mods in (Qt.KeyboardModifier.ControlModifier,
                     Qt.KeyboardModifier.AltModifier):
            ed.mousePressEvent(QMouseEvent(
                QMouseEvent.Type.MouseButtonPress, QPointF(x, y),
                Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))

        assert ileri == [] and tanim == []
    finally:
        ed.deleteLater()
        qapp.processEvents()
