"""Tablo sihirbazı GUI + mixin testleri (dialog üretimi, ekleme, hizalama)."""

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTableWidgetItem
    from gui.editor import EditorWidget
    from gui.mixins.table_ops import TableOpsMixin
    from gui.table_wizard import TableWizardDialog
    from core.latex_tables import parse_tabular_at
    from tests.stub_main import StubMain
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# Dialog: grid → kod
# =====================================================================


def _filled_dialog(qapp):
    dlg = TableWizardDialog(existing_labels=["tab:var"])
    dlg._caption.setText("Yöntem Karşılaştırması")
    dlg._grid.setItem(0, 0, QTableWidgetItem("Yöntem"))
    dlg._grid.setItem(0, 1, QTableWidgetItem("Doğruluk %"))
    dlg._grid.setItem(0, 2, QTableWidgetItem("F1"))
    dlg._grid.setItem(1, 0, QTableWidgetItem("CNN"))
    dlg._grid.setItem(1, 1, QTableWidgetItem("91.2"))
    dlg._grid.setItem(1, 2, QTableWidgetItem("0.87"))
    return dlg


def test_dialog_builds_code(qapp):
    dlg = _filled_dialog(qapp)
    code = dlg.result_text()
    assert "\\begin{tabular}{ccc}" in code
    assert "Doğruluk \\%" in code
    assert "\\caption{Yöntem Karşılaştırması}" in code
    # caption'a göre otomatik label, mevcutla çakışmaz
    assert "\\label{tab:yontem-karsilastirmasi}" in code


def test_dialog_label_collision_suffix(qapp):
    dlg = TableWizardDialog(existing_labels=["tab:yontem-karsilastirmasi"])
    dlg._caption.setText("Yöntem Karşılaştırması")
    assert dlg._label.text() == "tab:yontem-karsilastirmasi-2"


def test_dialog_options_live_preview(qapp):
    dlg = _filled_dialog(qapp)
    dlg._cb_vlines.setChecked(True)
    dlg._align_box.itemAt(0).widget().setCurrentIndex(0)  # Sol (l)
    code = dlg.result_text()
    assert "{|l|c|c|}" in code
    assert dlg._preview.toPlainText() == code


def test_dialog_load_block_edits_existing(qapp):
    text = ("\\begin{table}\n\\begin{tabular}{lr}\n\\toprule\n"
            "Ad & Deger \\\\\n\\midrule\na & 1 \\\\\n\\bottomrule\n"
            "\\end{tabular}\n\\end{table}\n")
    block = parse_tabular_at(text, text.index("Deger"))
    dlg = TableWizardDialog()
    dlg.load_block(block)
    cells = dlg.cells()
    assert cells[0] == ["Ad", "Deger"]
    assert cells[1] == ["a", "1"]
    # spec 'lr' → ilk iki hizalama kutusu Sol/Sağ seçili
    assert dlg._align_box.itemAt(0).widget().currentIndex() == 0
    assert dlg._align_box.itemAt(1).widget().currentIndex() == 2
    assert "{lr}" in dlg.result_text()


def test_dialog_empty_preview_hint(qapp):
    dlg = TableWizardDialog()
    assert dlg.result_text() == ""


def test_csv_load_beyond_old_limits(qapp, tmp_path, monkeypatch):
    """120 satır × 18 kolon CSV: spinbox eski sınırlara (100/15) takılmamalı.

    Regression: değer spinbox'ta kırpılıp grid gerçek boyutu alınca, kullanıcı
    sonra spinbox'a dokunduğunda fazlası sessizce siliniyordu; 15+ kolonda
    hizalama kutuları da eksik kalıyordu.
    """
    import gui.table_wizard as tw

    rows = 120
    cols = 18
    lines = [";".join(f"h{j}" for j in range(cols))]
    lines += [";".join(f"{i}.{j}" for j in range(cols)) for i in range(rows - 1)]
    p = tmp_path / "buyuk.csv"
    p.write_text("\n".join(lines), encoding="utf-8")

    monkeypatch.setattr(
        tw.QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(p), "")))
    dlg = TableWizardDialog()
    dlg._load_csv()

    assert dlg._rows.value() == rows and dlg._grid.rowCount() == rows
    assert dlg._cols.value() == cols and dlg._grid.columnCount() == cols
    assert dlg._align_box.count() == cols, "hizalama kutuları kolon sayısına eksik"
    code = dlg.result_text()
    assert code.count(" \\\\\n") == rows  # tüm satırlar üretime girdi


def test_dialog_load_block_escape_roundtrip(qapp):
    """Kaçış içeren hücre grid'e AÇILARAK yüklenir; üretimde yeniden kaçar.

    Regression: ham hücre yüklenseydi \\% çift kaçışa (\\\\%) dönüşürdü.
    """
    text = ("\\begin{tabular}{l}\nDoğruluk \\% & x_1 \\\\\n\\end{tabular}\n")
    block = parse_tabular_at(text, 2)
    dlg = TableWizardDialog()
    dlg.load_block(block)

    assert dlg.cells() == [["Doğruluk %", "x_1"]]     # kaçış açıldı
    assert "Doğruluk \\% & x\\_1 \\\\" in dlg.result_text()  # yeniden kaçtı


def test_dialog_load_block_rebuilds_align_combos(qapp):
    """Dialog'dan geniş tablo yükleme: hizalama kutuları kolon sayısına büyür.

    Regression: load_block _updating kilidi yüzünden _on_cols_changed'i
    erkenden döndürüyordu; 5 kolonlu tablo 3 kutulu dialog'a 'lllcc'
    belirtimiyle üretiliyordu.
    """
    text = "\\begin{tabular}{lllll}\na & b & c & d & e \\\\\n\\end{tabular}\n"
    block = parse_tabular_at(text, 2)
    dlg = TableWizardDialog()          # varsayılan 3 kolon
    dlg.load_block(block)

    assert dlg._grid.columnCount() == 5
    assert dlg._align_box.count() == 5, "hizalama kutuları yeni kolon sayısına büyümedi"
    assert "\\begin{tabular}{lllll}" in dlg.result_text()


# =====================================================================
# Mixin: ekle / hizala (stub MainWindow)
# =====================================================================


class _Stub(TableOpsMixin, StubMain):
    def __init__(self, editors):
        StubMain.__init__(self, editors=editors)
        self._theme_mgr = type("M", (), {"theme": THEMES["dark"]})()


def test_wizard_inserts_at_cursor(qapp, monkeypatch):
    import gui.table_wizard as tw

    ed = EditorWidget()
    ed.setText("öncesi\nsonrası\n")
    ed.setCursorPosition(1, 0)
    stub = _Stub([ed])

    code = "\\begin{table}\n\\begin{tabular}{l}x\\end{tabular}\n\\end{table}"

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def apply_theme(self, t):
            pass

        def load_block(self, b):
            raise AssertionError("yeni tablo modunda load_block çağrılmamalı")

        def exec(self):
            return True

        def result_text(self):
            return code

    monkeypatch.setattr(tw, "TableWizardDialog", FakeDlg)
    stub._table_wizard()

    assert code in ed.text()
    assert "öncesi\n" in ed.text() and "sonrası" in ed.text()
    assert "Tablo eklendi" in stub._status.msg


def test_wizard_replaces_wrapped_table_whole(qapp, monkeypatch):
    """Sarmalı tabloda (\\begin{table} içinde) kılıf DAHİL değiştirilir.

    Regression: yalnız tabular aralığı değiştiriliyordu; sihirbazın ürettiği
    kılıflı kod mevcut kılıfın içine İKİNCİ bir \\begin{table} yerleştiriyordu
    (iç içe yüzen ortam = geçersiz LaTeX). Caption/label kılıftan taşınır.
    """
    import gui.table_wizard as tw

    original = ("öncesi\n\\begin{table}[htbp]\n    \\caption{Eski başlık}\n"
                "    \\label{tab:eski}\n    \\begin{tabular}{ll}\n"
                "    a & b\\\\\n    \\end{tabular}\n\\end{table}\nsonrası\n")
    ed = EditorWidget()
    ed.setText(original)
    ed.setCursorPosition(5, 5)  # tabular gövdesi içinde
    stub = _Stub([ed])

    new_code = ("\\begin{table}[htbp]\n    \\centering\n"
                "    \\caption{Eski başlık}\n    \\label{tab:eski}\n"
                "    \\begin{tabular}{ll}\n    YENİ & TABLO\\\\\n"
                "    \\end{tabular}\n\\end{table}")

    captured = {}

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def apply_theme(self, t):
            pass

        def load_block(self, b):
            captured["block"] = b

        def set_meta(self, caption, label):
            captured["meta"] = (caption, label)

        def exec(self):
            return True

        def result_text(self):
            return new_code

    monkeypatch.setattr(tw, "TableWizardDialog", FakeDlg)
    stub._table_wizard()

    t = ed.text()
    assert t.count("\\begin{table}") == 1, "iç içe table kılıfı üretildi"
    assert "YENİ & TABLO" in t and "a & b" not in t
    assert t.startswith("öncesi\n") and t.rstrip().endswith("sonrası")
    # kılıftaki caption/label dialoga taşındı
    assert captured["meta"] == ("Eski başlık", "tab:eski")


def test_wizard_replaces_existing_block(qapp, monkeypatch):
    import gui.table_wizard as tw

    original = ("öncesi\n\\begin{tabular}{ll}\na & b\\\\\n\\end{tabular}\nsonrası\n")
    ed = EditorWidget()
    ed.setText(original)
    ed.setCursorPosition(2, 0)
    stub = _Stub([ed])

    new_code = "\\begin{tabular}{ll}\nYENİ & TABLO\\\\\n\\end{tabular}"

    class FakeDlg:
        def __init__(self, *a, **k):
            pass

        def apply_theme(self, t):
            pass

        def load_block(self, b):
            self.loaded = b

        def exec(self):
            return True

        def result_text(self):
            return new_code

    monkeypatch.setattr(tw, "TableWizardDialog", FakeDlg)
    stub._table_wizard()

    t = ed.text()
    assert "YENİ & TABLO" in t
    assert "a & b" not in t
    assert t.startswith("öncesi\n") and t.rstrip().endswith("sonrası")


def test_align_table_reformats_editor(qapp):
    original = ("giriş\n\\begin{table}\n    \\begin{tabular}{lll}\n"
                "        \\toprule\n"
                "        uzunhücre & b & c \\\\\n"
                "        x & yy & zzz \\\\\n"
                "        \\bottomrule\n"
                "    \\end{tabular}\n\\end{table}\n")
    ed = EditorWidget()
    ed.setText(original)
    ed.setCursorPosition(4, 10)  # veri satırı içinde
    stub = _Stub([ed])

    stub._align_table()
    t = ed.text()
    assert "Tablo hizalandı" in stub._status.msg
    # & işaretleri hizalanmış kolonlarda
    import re as _re
    data = [ln for ln in t.split("\n") if "&" in ln]
    cols = [[m.start() for m in _re.finditer(r"(?<!\\)&", ln)] for ln in data]
    assert cols[0] == cols[1]


def test_align_table_outside(qapp):
    ed = EditorWidget()
    ed.setText("tablo yok burada\n")
    ed.setCursorPosition(0, 3)
    stub = _Stub([ed])
    stub._align_table()
    assert "tablo içinde değil" in stub._status.msg


def test_cursor_char_offset_unicode(qapp):
    ed = EditorWidget()
    ed.setText(" ascii\nğüş ti öç\nüçüncü\n")
    ed.setCursorPosition(1, 3)  # 'ğüş' → +3 char = ' ti...' başı
    stub = _Stub([ed])
    assert stub._cursor_char_offset(ed) == len(" ascii\nğüş")


# ======================================================================
# Ctrl+T: uygulama düzeyi tuş kısayolu (Scintilla tuşu yuttuğu için)
# ======================================================================


def _key_event(key, mods, text):
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    return QKeyEvent(QEvent.Type.KeyPress, key, mods, text)


def _fake_mainwindow(editor):
    """_handle_app_key_shortcut'u Qt kurulumu olmadan çalıştıran sahne."""
    from types import SimpleNamespace
    from gui.main_window import MainWindow

    calls = []
    mw = SimpleNamespace(
        _table_wizard=lambda: calls.append("wizard"),
        _toggle_comment=lambda: calls.append("comment"),
        _on_esc=lambda: calls.append("esc"),
        _pdf_viewer=SimpleNamespace(in_presentation=False),
        _current_editor=lambda: editor,
    )
    return mw, calls, MainWindow


def test_ctrl_t_consumed_by_app_key_handler(qapp):
    from PyQt6.QtCore import Qt

    ed = EditorWidget()
    mw, calls, MW = _fake_mainwindow(ed)

    ev = _key_event(Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier, "t")
    assert MW._handle_app_key_shortcut(mw, ev) is True
    assert calls == ["wizard"]

    # Ctrl+Shift+T / yalnız T tüketilmemeli
    calls.clear()
    ev = _key_event(Qt.Key.Key_T,
                    Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier, "T")
    assert MW._handle_app_key_shortcut(mw, ev) is False
    ev = _key_event(Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier, "t")
    assert MW._handle_app_key_shortcut(mw, ev) is False
    assert calls == []


def test_ctrl_t_without_editor_not_consumed(qapp):
    """Sekme yokken filtre tüketmez → menü kısayolu 'dosya açın' yoluna girer."""
    from PyQt6.QtCore import Qt

    mw, calls, MW = _fake_mainwindow(None)
    ev = _key_event(Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier, "t")
    assert MW._handle_app_key_shortcut(mw, ev) is False
    assert calls == []


def test_shortcuts_not_consumed_while_modal_dialog_open(qapp):
    """Modal dialog açıkken uygulama kısayolları tüketilmez.

    Regression: filtre QApplication'a kuruludur; dialog'a giden tuşları da
    görüyordu. Esc dialog'u kapatamıyor, Ctrl+K sürüm-adı dialogu açıkken
    ikinci bir Sürümle penceresi açıyordu.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog

    mw, calls, MW = _fake_mainwindow(EditorWidget())
    dlg = QDialog()
    dlg.setModal(True)
    dlg.show()
    try:
        assert QApplication.activeModalWidget() is dlg
        esc = _key_event(Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier, "\x1b")
        assert MW._handle_app_key_shortcut(mw, esc) is False
        k = _key_event(Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier, "k")
        assert MW._handle_app_key_shortcut(mw, k) is False
        assert calls == []
    finally:
        dlg.close()
