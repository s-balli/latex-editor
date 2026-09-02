"""Editör ayarları — dialog değer eşlemesi, editöre uygulama ve kalıcılık akışı."""

from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QDialog
    from PyQt6.Qsci import QsciScintilla
    from gui.editor import EditorWidget
    from gui.main_window import MainWindow
    from gui.settings_dialog import EditorSettingsDialog
    from gui.theme import THEMES
    from tests.stub_main import StubMain
    from syntax.latex_lexer import LatexLexer
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --- dialog: değerler gidip geliyor ---


def test_dialog_roundtrip(qapp):
    dlg = EditorSettingsDialog({"tab_width": 6, "font_size": 14, "wrap": False})
    assert dlg.values() == {"tab_width": 6, "font_size": 14, "wrap": False}
    dlg._tab.setValue(4)
    dlg._font.setValue(11)
    dlg._wrap.setChecked(True)
    assert dlg.values() == {"tab_width": 4, "font_size": 11, "wrap": True}


def test_dialog_defaults(qapp):
    dlg = EditorSettingsDialog({})
    assert dlg.values() == {"tab_width": 4, "font_size": 11, "wrap": True}


# --- EditorWidget.apply_editor_settings ---


def test_editor_applies_settings(qapp):
    ed = EditorWidget(theme=THEMES["dark"])   # font uygulanması için tema gerekli
    ed.apply_editor_settings(6, 14, False)
    assert ed.tabWidth() == 6
    assert ed.wrapMode() == QsciScintilla.WrapMode.WrapNone
    assert ed.lexer().font(LatexLexer.DEFAULT).pointSize() == 14


def test_font_size_survives_theme_change(qapp):
    ed = EditorWidget()
    ed.apply_editor_settings(4, 16, True)
    ed.apply_theme(THEMES["dark"])      # tema değişimi fontu sıfırlamamalı
    assert ed.lexer().font(LatexLexer.DEFAULT).pointSize() == 16
    assert ed.wrapMode() == QsciScintilla.WrapMode.WrapWord


# --- MainWindow._open_settings_dialog: kaydet + açık sekmelere uygula ---


class _StubMain(StubMain):
    # MainWindow'un ayar metotları (stub üstünde bağlanmış hali)
    _EDITOR_SETTING_DEFAULTS = MainWindow._EDITOR_SETTING_DEFAULTS
    # staticmethod: siniftan duz fonksiyon olarak alinip stub'a atanirsa
    # self'i ilk argüman sanip TypeError veriyor.
    _ayar_sayi = staticmethod(MainWindow._ayar_sayi)
    _read_editor_settings = MainWindow._read_editor_settings
    _apply_editor_settings = MainWindow._apply_editor_settings


def test_settings_flow_applies_and_persists(qapp):
    ed = EditorWidget()
    stub = _StubMain(editors=[ed])

    dlg = MagicMock()
    dlg.exec.return_value = QDialog.DialogCode.Accepted
    dlg.values.return_value = {"tab_width": 6, "font_size": 14, "wrap": False}
    with patch("gui.settings_dialog.EditorSettingsDialog", return_value=dlg):
        MainWindow._open_settings_dialog(stub)

    assert stub._settings.d == {"editor/tab_width": 6, "editor/font_size": 14, "editor/wrap": False}
    assert ed.tabWidth() == 6
    assert ed.wrapMode() == QsciScintilla.WrapMode.WrapNone
    assert "kaydedildi" in stub._status.msg


def test_settings_cancel_keeps_everything(qapp):
    ed = EditorWidget()
    stub = _StubMain(editors=[ed])
    before = ed.tabWidth()

    dlg = MagicMock()
    dlg.exec.return_value = QDialog.DialogCode.Rejected
    with patch("gui.settings_dialog.EditorSettingsDialog", return_value=dlg):
        MainWindow._open_settings_dialog(stub)

    assert stub._settings.d == {}
    assert ed.tabWidth() == before


def test_read_editor_settings_defaults_and_roundtrip(qapp):
    stub = _StubMain()
    # varsayılanlar
    assert MainWindow._read_editor_settings(stub) == {"tab_width": 4, "font_size": 11, "wrap": True}
    # QSettings'ten string gelen wrap ("true") de doğru çözülmeli
    stub._settings.d = {"editor/tab_width": 8, "editor/font_size": 12, "editor/wrap": "true"}
    assert MainWindow._read_editor_settings(stub) == {"tab_width": 8, "font_size": 12, "wrap": True}


# --- Bozuk ayar dosyasi acilisi engellemesin ---


def test_bozuk_ayar_varsayilana_donuyor(qapp):
    """Ayar dosyasina yarim yazma uygulamayi ACILMAZ yapiyordu.

    `int("")` ValueError atiyor ve oturumda ACIK SEKME varsa bu, __init__ ->
    _restore_state -> _apply_editor_settings zincirinde patliyordu: uygulama
    bir daha acilmiyordu ve kullanicinin duzeltmesi kolay degildi. Olculdu
    (2026-09-02, dis guvenlik raporu): bos/metin/ondalik degerlerin ucu de
    acilisi kesiyordu; sekme yokken sorun cikmiyordu.
    """
    stub = _StubMain()
    v = MainWindow._EDITOR_SETTING_DEFAULTS
    for bozuk in ("", "abc", "4.5", None, [], "0x10"):
        stub._settings.d = {"editor/tab_width": bozuk, "editor/font_size": bozuk}
        okunan = MainWindow._read_editor_settings(stub)
        assert okunan["tab_width"] == v["editor/tab_width"], bozuk
        assert okunan["font_size"] == v["editor/font_size"], bozuk


def test_absurt_ayar_kullanilabilir_araliga_cekiliyor(qapp):
    """Sifir ya da devasa deger uygulamayi acar ama kullanilamaz birakirdi."""
    stub = _StubMain()
    stub._settings.d = {"editor/tab_width": 0, "editor/font_size": 999999}
    okunan = MainWindow._read_editor_settings(stub)
    assert okunan["tab_width"] == 1
    assert okunan["font_size"] == 72

    stub._settings.d = {"editor/tab_width": 99, "editor/font_size": -20}
    okunan = MainWindow._read_editor_settings(stub)
    assert okunan["tab_width"] == 16
    assert okunan["font_size"] == 6


def test_gecerli_ayar_dokunulmadan_geciyor(qapp):
    """Sinir, gundelik degerleri degistirmemeli."""
    stub = _StubMain()
    stub._settings.d = {"editor/tab_width": 8, "editor/font_size": 14}
    assert MainWindow._read_editor_settings(stub)["tab_width"] == 8
    assert MainWindow._read_editor_settings(stub)["font_size"] == 14
