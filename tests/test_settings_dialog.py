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
    dlg = EditorSettingsDialog({"tab_width": 6, "font_size": 14, "wrap": False,
                                "autosave": False, "autosave_dk": 9,
                                "guncelleme": False})
    assert dlg.values() == {"tab_width": 6, "font_size": 14, "wrap": False,
                            "autosave": False, "autosave_dk": 9,
                            "guncelleme": False}
    dlg._tab.setValue(4)
    dlg._font.setValue(11)
    dlg._wrap.setChecked(True)
    dlg._autosave.setChecked(True)
    dlg._autosave_dk.setValue(5)
    dlg._guncelleme.setChecked(True)
    assert dlg.values() == {"tab_width": 4, "font_size": 11, "wrap": True,
                            "autosave": True, "autosave_dk": 5,
                            "guncelleme": True}


def test_dialog_defaults(qapp):
    dlg = EditorSettingsDialog({})
    assert dlg.values() == {"tab_width": 4, "font_size": 11, "wrap": True,
                            "autosave": True, "autosave_dk": 3,
                            "guncelleme": True}


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


def test_okumanin_kabul_ettigi_deger_diyalogda_KIRPILMIYOR(qapp):
    """Diyalog 2-8 / 8-24, okuma 1-16 / 6-72 idi. ÖLÇÜLDÜ (2026-09-24,
    gerçek pencere): kayıtlı yazı 28 ve sekme 12, hiçbir alana dokunulmadan
    Tamam'la 24 ve 8 oldu, açık sekme de küçüldü."""
    dlg = EditorSettingsDialog({"tab_width": 12, "font_size": 28, "wrap": True,
                                "autosave": True, "autosave_dk": 3})
    assert dlg.values()["tab_width"] == 12
    assert dlg.values()["font_size"] == 28


def test_yazi_buyuyunce_satir_numarasi_kenari_da_BUYUYOR(qapp):
    """Kenar genişliği ölçüldüğü anki yazıyla hesaplanıyor ve yalnız satır
    sayısı değişince tazeleniyordu. ÖLÇÜLDÜ (2026-09-24): yazı 11'den 24'e
    çıkınca kenar 32 pikselde kaldı, dört hane 72 piksel istiyordu (Windows'un
    gerçek platformu; offscreen'de sayılar başka, oran aynı). Kehanet
    Scintilla'nın kendi ölçüsü: SCI_TEXTWIDTH."""
    ed = EditorWidget(theme=THEMES["dark"])
    ed.setText("\n".join("satir %d" % i for i in range(1, 1201)))
    ed.apply_editor_settings(4, 11, True)
    ed.apply_editor_settings(4, 24, True)

    kenar = ed.SendScintilla(QsciScintilla.SCI_GETMARGINWIDTHN, 1)
    gerek = ed.SendScintilla(QsciScintilla.SCI_TEXTWIDTH,
                             QsciScintilla.STYLE_LINENUMBER,
                             b"0" * len(str(ed.lines())))
    assert kenar >= gerek, (kenar, gerek)


# --- MainWindow._open_settings_dialog: kaydet + açık sekmelere uygula ---


class _StubMain(StubMain):
    # MainWindow'un ayar metotları (stub üstünde bağlanmış hali)
    _EDITOR_SETTING_DEFAULTS = MainWindow._EDITOR_SETTING_DEFAULTS
    # staticmethod: siniftan duz fonksiyon olarak alinip stub'a atanirsa
    # self'i ilk argüman sanip TypeError veriyor.
    _ayar_sayi = staticmethod(MainWindow._ayar_sayi)
    _read_editor_settings = MainWindow._read_editor_settings
    _apply_editor_settings = MainWindow._apply_editor_settings

    def _autosave_uygula(self):
        # Gerçeği zamanlayıcıyı tazeliyor; burada yalnız çağrıldığı kayda
        # geçiyor, çünkü "ayar hemen uygulanıyor" kapısı bunu sayıyor.
        self.autosave_tazelendi = getattr(
            self, "autosave_tazelendi", 0) + 1


def test_settings_flow_applies_and_persists(qapp):
    ed = EditorWidget()
    stub = _StubMain(editors=[ed])

    dlg = MagicMock()
    dlg.exec.return_value = QDialog.DialogCode.Accepted
    dlg.values.return_value = {"tab_width": 6, "font_size": 14,
                               "wrap": False, "autosave": False,
                               "autosave_dk": 9, "guncelleme": False}
    with patch("gui.settings_dialog.EditorSettingsDialog", return_value=dlg):
        MainWindow._open_settings_dialog(stub)

    assert stub._settings.d == {"editor/tab_width": 6, "editor/font_size": 14,
                                "editor/wrap": False,
                                "editor/autosave": False,
                                "editor/autosave_dk": 9,
                                "update/acilista_denetle": False}
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
    assert MainWindow._read_editor_settings(stub) == {
        "tab_width": 4, "font_size": 11, "wrap": True,
        "autosave": True, "autosave_dk": 3, "guncelleme": True}
    # QSettings'ten string gelen wrap ("true") de doğru çözülmeli
    stub._settings.d = {"editor/tab_width": 8, "editor/font_size": 12,
                        "editor/wrap": "true", "editor/autosave": "false",
                        "editor/autosave_dk": "12",
                        "update/acilista_denetle": "false"}
    assert MainWindow._read_editor_settings(stub) == {
        "tab_width": 8, "font_size": 12, "wrap": True,
        "autosave": False, "autosave_dk": 12, "guncelleme": False}


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


def test_ayar_kutusu_otomatik_kaydetmeyi_TAZELIYOR(qapp):
    """Kutuyu kapatan kullanici yeni ayarin hemen gecerli olmasini
    bekliyor; tazelenmezse kapattigi otomatik kaydetme uygulamayi
    yeniden baslatana kadar yasamaya devam ederdi."""
    stub = _StubMain(editors=[EditorWidget()])
    dlg = MagicMock()
    dlg.exec.return_value = QDialog.DialogCode.Accepted
    dlg.values.return_value = {"tab_width": 4, "font_size": 11,
                               "wrap": True, "autosave": False,
                               "autosave_dk": 3, "guncelleme": True}
    with patch("gui.settings_dialog.EditorSettingsDialog",
               return_value=dlg):
        MainWindow._open_settings_dialog(stub)

    assert getattr(stub, "autosave_tazelendi", 0) == 1


# --- exec dönüşü sonrası diyalog siliniyor (2026-11-17, ikinci tur durum
# --- makinesi taraması bulgu 5): parent'lı yerel diyalog birikiyordu


def test_ayar_diyalogu_kapaninca_SILINIYOR_ve_degerler_once_okunuyor(
        qapp, monkeypatch):
    """`dlg = EditorSettingsDialog(..., self)` yerel değişkenle açılıyordu:
    Python referansı düşse de C++ nesnesi ebeveynin çocuğu olarak yaşıyor,
    her ayar açılışı bir diyalog biriktiriyordu (aynı sınıf 2f10a63'te
    Ctrl+P/yardım/Ortam Denetimi için ölçülmüştü). `values()` exec dönüşünde
    okunduğu için WA_DeleteOnClose riskli; deleteLater değerlerden SONRA."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QTabWidget, QWidget
    from tests.stub_main import FakeSettings, StatusRecorder

    class _Pencere(QWidget):
        _EDITOR_SETTING_DEFAULTS = MainWindow._EDITOR_SETTING_DEFAULTS
        _ayar_sayi = staticmethod(MainWindow._ayar_sayi)
        _read_editor_settings = MainWindow._read_editor_settings
        _apply_editor_settings = MainWindow._apply_editor_settings

        def _autosave_uygula(self):
            pass

    w = _Pencere()
    w._settings = FakeSettings()
    w._status = StatusRecorder()
    w._editor_tabs = QTabWidget()
    w._editor_tabs.addTab(EditorWidget(), "t")

    def _exec(self):
        self._tab.setValue(6)             # kullanıcı alanları değiştirdi
        self._font.setValue(14)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(EditorSettingsDialog, "exec", _exec)

    MainWindow._open_settings_dialog(w)

    # Değerler SİLME gerçekleşmeden okunmuş olmalı
    assert w._settings.d["editor/tab_width"] == 6
    assert w._settings.d["editor/font_size"] == 14
    assert "kaydedildi" in w._status.msg

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    kalan = w.findChildren(EditorSettingsDialog)
    assert kalan == [], "ayar diyaloğu ebeveynin çocuğu olarak birikiyor"
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_ayar_diyalogu_IPTALDE_de_SILINIYOR(qapp, monkeypatch):
    """Silme yalnız Tamam yolundaydı; İptal (en sık yol) erken dönüyor ve
    diyalog yine ebeveynde birikiyordu (2026-11-17, Claude denetimi)."""
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QTabWidget, QWidget
    from tests.stub_main import FakeSettings, StatusRecorder

    class _Pencere(QWidget):
        _EDITOR_SETTING_DEFAULTS = MainWindow._EDITOR_SETTING_DEFAULTS
        _ayar_sayi = staticmethod(MainWindow._ayar_sayi)
        _read_editor_settings = MainWindow._read_editor_settings
        _apply_editor_settings = MainWindow._apply_editor_settings

        def _autosave_uygula(self):
            pass

    w = _Pencere()
    w._settings = FakeSettings()
    w._status = StatusRecorder()
    w._editor_tabs = QTabWidget()
    w._editor_tabs.addTab(EditorWidget(), "t")
    monkeypatch.setattr(EditorSettingsDialog, "exec",
                        lambda self: QDialog.DialogCode.Rejected)

    MainWindow._open_settings_dialog(w)

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    assert w.findChildren(EditorSettingsDialog) == [], \
        "iptal edilen ayar diyaloğu ebeveynin çocuğu olarak birikiyor"
    assert "editor/tab_width" not in w._settings.d, "iptal ayar yazdı"
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
