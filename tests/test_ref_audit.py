"""Referans denetimi — edit_ops handler ve OutputPanel tıklanabilir bulgu testleri.

İki katman:
- gui.mixins.edit_ops: _audit_references bulguları (metin, dosya, satır) üretir
- gui.output_panel: show_audit listeleri doldurur, tıklama error_clicked üretir
"""

import os

import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.mixins.edit_ops import EditOpsMixin
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _StubMain(EditOpsMixin, StubMain):
    """MainWindow yerine: _audit_references'in ihtiyaç duyduğu arayüz.

    EditOpsMixin'den miras alır — handler self._collect_audit_items çağırır.
    """

    def __init__(self, editor):
        super().__init__(editors=[editor])


# --- handler: bulgular (metin, dosya, satır) üretir ---


def test_handler_undefined_ref_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\ref{fig:yok}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._suggest_list.count() == 0
    assert panel._warn_list.count() == 1
    item = panel._warn_list.item(0)
    assert "Tanımsız \\ref" in item.text() and "fig:yok" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 tanımsız ref" in stub._status.msg


def test_handler_unused_bib_clickable(qapp, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{kullanilmayan,}\n", encoding="utf-8")
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n\\bibliography{refs}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan .bib girdisi" in item.text() and "kullanilmayan" in item.text()
    assert "refs.bib:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(bib), 1)


def test_handler_unused_label_clickable(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{bos}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 1
    item = panel._suggest_list.item(0)
    assert "Kullanılmayan label" in item.text() and "bos" in item.text()
    assert "m.tex:1" in item.text()
    assert item.data(Qt.ItemDataRole.UserRole) == (str(main), 1)
    assert "1 kullanılmayan label" in stub._status.msg


def test_handler_clean_doc(qapp, tmp_path):
    main = tmp_path / "m.tex"
    main.write_text("\\label{a}\n\\ref{a}\n", encoding="utf-8")
    ed = EditorWidget()
    ed._file_path = str(main)
    ed.setText(main.read_text(encoding="utf-8"))

    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    # temiz belgede tek 'Sorun bulunamadı' mesajı Öneriler'de
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert "sorun yok" in stub._status.msg


def test_handler_needs_saved_file(qapp):
    ed = EditorWidget()  # dosya yolu yok
    stub = _StubMain(ed)
    MainWindow._audit_references(stub)
    panel = stub._output_panel
    assert panel._warn_list.count() == 0
    assert panel._suggest_list.count() == 0   # temiz-belge mesajı da yok
    assert ".tex dosyası açın" in stub._status.msg


# --- OutputPanel: show_audit + tıklama ---


def _panel(qapp):
    return OutputPanel(theme=THEMES["dark"])


def test_panel_show_audit_lists_and_tabs(qapp):
    panel = _panel(qapp)
    panel.show_audit(
        [("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)],
        [("refs.bib:1 — Kullanılmayan .bib girdisi: a", "/tmp/refs.bib", 1)],
    )
    assert panel._warn_list.count() == 1
    assert panel._suggest_list.count() == 1
    assert panel._tabs.currentIndex() == panel._warn_tab_index


def test_panel_audit_click_emits_jump(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("m.tex:3 — Tanımsız \\ref: fig:yok", "/tmp/m.tex", 3)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == [("/tmp/m.tex", 3)]


def test_panel_audit_click_without_location_no_emit(qapp):
    panel = _panel(qapp)
    jumps = []
    panel.error_clicked.connect(lambda p, l: jumps.append((p, l)))
    panel.show_audit([("Tanımsız \\ref: fig:yok", "", 0)], [])
    panel._on_result_click(panel._warn_list.item(0))
    assert jumps == []


def test_panel_audit_clean_shows_message(qapp):
    panel = _panel(qapp)
    panel.show_audit([], [])
    assert panel._suggest_list.count() == 1
    assert "Sorun bulunamadı" in panel._suggest_list.item(0).text()
    assert panel._tabs.currentIndex() == panel._suggest_tab_index


# --- Denetim maliyeti bulgu sayısıyla BÜYÜMEMELİ ---
#
# _collect_audit_items eskiden her bulgu için ayrı konum araması yapıyordu ve
# her arama \input zincirini diskten baştan okuyordu. 30 bölümlü, 200 girdilik
# .bib'li bir tezde ölçüldü: 495 arama = 1.74 sn, hepsi UI thread'inde
# (derleme sonrası denetim açıksa HER derlemeden sonra). 2026-08-31, G6.
#
# Süre ölçmek CI'da kırılgan olur; ölçülen şey DİSK OKUMASI: zincir okuma
# sayısı bulgu sayısından bağımsız, küçük bir sabit olmalı.

def _tez_projesi(tmp_path, n_bolum, n_etiket):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "k.bib").write_text(
        "".join("@article{a%d, title={T}}\n" % i for i in range(20)), encoding="utf-8")
    ana = ["\\documentclass{book}", "\\bibliography{k}", "\\begin{document}"]
    for b in range(n_bolum):
        satir = []
        for j in range(n_etiket):
            satir.append("\\section{S%d}" % j)
            satir.append("\\label{sec:b%d-%d}" % (b, j))   # hiç \ref edilmiyor
        (tmp_path / ("b%d.tex" % b)).write_text("\n".join(satir), encoding="utf-8")
        ana.append("\\input{b%d}" % b)
    ana.append("\\end{document}")
    icerik = "\n".join(ana)
    yol = tmp_path / "main.tex"
    yol.write_text(icerik, encoding="utf-8")
    return icerik, str(yol)


def _dosya_okuma_sayisi(monkeypatch, icerik, ana):
    """Denetim sırasında açılan .tex/.bib sayısı + denetim sonucu.

    Sayılan şey gerçek disk erişimi; hangi fonksiyonun yaptığı önemsiz.
    (İlk hâli ``_chain_texts`` çağrısını sayıyordu ve kapı düzeltmeden ÖNCEKİ
    kodda da yeşil kalıyordu: eski yol zinciri ``_flatten_input_paths``
    üzerinden okuyordu, sayaç onu hiç görmüyordu.)
    """
    import builtins

    from core import latex_refs
    latex_refs._label_file_cache.clear()
    latex_refs._bib_cache.clear()

    sayac = {"n": 0}
    gercek_open = builtins.open

    def sayan_open(dosya, *a, **kw):
        if isinstance(dosya, (str, os.PathLike)) and str(dosya).endswith((".tex", ".bib")):
            sayac["n"] += 1
        return gercek_open(dosya, *a, **kw)

    monkeypatch.setattr(builtins, "open", sayan_open)
    try:
        bulgular = EditOpsMixin._collect_audit_items(icerik, ana)
    finally:
        monkeypatch.undo()
    return sayac["n"], bulgular


def test_denetim_maliyeti_bulgu_sayisiyla_buyumuyor(tmp_path, monkeypatch):
    """Aynı DOSYA sayısı, 20 kat BULGU → disk okuması değişmemeli.

    İki proje de 4 bölüm dosyası + 1 .bib içerir; tek fark kullanılmayan
    label sayısıdır (4'e karşı 80). Eski kod her bulgu için zinciri baştan
    okuduğundan okuma sayısı bulguyla birlikte artıyordu.
    """
    kucuk = _tez_projesi(tmp_path / "az", 4, 1)      # 4 kullanılmayan label
    buyuk = _tez_projesi(tmp_path / "cok", 4, 20)    # 80 kullanılmayan label

    az_okuma, (_w1, _o1, az_c) = _dosya_okuma_sayisi(monkeypatch, *kucuk)
    cok_okuma, (_w2, _o2, cok_c) = _dosya_okuma_sayisi(monkeypatch, *buyuk)

    assert (az_c["l"], cok_c["l"]) == (4, 80), "test projesi beklendiği gibi değil"
    assert az_okuma == cok_okuma, (
        f"disk okuması bulgu sayısıyla büyüyor: {az_okuma} → {cok_okuma} "
        f"({az_c['l']} → {cok_c['l']} bulgu)")


def test_kullanilmayan_label_konumu_dogru_kaliyor(tmp_path):
    """Hız düzeltmesi 'dosya:satır' bağlantısını bozmamalı."""
    icerik, ana = _tez_projesi(tmp_path, 2, 1)
    _w, oneriler, _c = EditOpsMixin._collect_audit_items(icerik, ana)
    kayit = {t: (d, s) for t, d, s in oneriler}
    hedef = next(t for t in kayit if "sec:b1-0" in t)
    dosya, satir = kayit[hedef]
    assert dosya.endswith("b1.tex")
    assert satir == 2                      # \section{S0} 1, \label 2
    assert "b1.tex:2" in hedef
