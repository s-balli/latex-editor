# -*- coding: utf-8 -*-
"""Editorun sag tik menusu: arayuz dilinde ve dogru etkin/pasif durumlarla.

QScintilla'nin YERLESIK menusu kullaniliyordu. O menu kendi ceviri
katalogundan besleniyor; uygulama yalniz `latexeditor_<dil>.qm`i yukluyor,
QScintilla'nin katalogu yuklenmiyor ve metinler kaynak dilinde kaliyordu.
Olculdu 2026-09-06, arayuz dili Turkceyken `createStandardContextMenu()`:

    ['&Undo', '&Redo', 'Cu&t', '&Copy', '&Paste', 'Delete', 'Select All']

Qt'nin `qtbase_*.qm`ini yuklemek de cozmez: bu metinler Qt'nin degil
QScintilla'nin katalogunda. Depodaki diger menuler (dosya agaci, cikti
paneli, sekme cubugu) zaten kendi menulerini kuruyor ve `_()` kullaniyor;
editor almamisti.
"""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QContextMenuEvent
from PyQt6.QtWidgets import QApplication, QMenu

from gui.editor import EditorWidget
from gui.theme import THEMES

_INGILIZCE = {"&Undo", "&Redo", "Cu&t", "&Copy", "&Paste", "Delete",
              "Select All"}


@pytest.fixture(scope="session")
def qapp():
    """QApplication REFERANSI TUTULMALI (bkz. test_menu_actions.py ayni ders)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def menu_ac(qapp, monkeypatch):
    """Menuyu ACMADAN ogelerini oku: (metin, etkin, ayirac_mi) listesi."""
    yakalanan = []

    def _sahte(self, *a, **k):
        yakalanan.append([(x.text(), x.isEnabled(), x.isSeparator())
                          for x in self.actions()])
        return None

    monkeypatch.setattr(QMenu, "exec", _sahte)

    def _ac(ed):
        yakalanan.clear()
        ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(10, 10),
                               ed.mapToGlobal(QPoint(10, 10)))
        ed.contextMenuEvent(ev)
        return yakalanan[0] if yakalanan else []

    return _ac


def _durumlar(ogeler):
    return {m.split("\t")[0]: e for m, e, sep in ogeler if not sep}


@pytest.fixture
def editor(qapp):
    ed = EditorWidget(theme=THEMES["dark"])
    ed.setText("merhaba dunya")
    yield ed
    ed.deleteLater()
    qapp.processEvents()


def test_menu_QSCINTILLA_yerlesigini_KULLANMIYOR(editor, menu_ac):
    """Kirilirsa: yerlesik menuye donulmus, metinler cevrilmiyor demektir."""
    ogeler = [m.split("\t")[0] for m, _e, sep in menu_ac(editor) if not sep]
    assert not (_INGILIZCE & set(ogeler)), (
        "QScintilla'nin cevrilmemis metinleri geri gelmis: %s" % ogeler)
    assert len(ogeler) == 7, ogeler


def test_menu_metinleri_CEVIRIDEN_geliyor(editor, menu_ac):
    """Metinler `_()` uzerinden gelmeli; katalogda karsiliklari var."""
    from PyQt6.QtCore import QCoreApplication

    ogeler = [m.split("\t")[0] for m, _e, sep in menu_ac(editor) if not sep]
    for kaynak in ("Geri Al", "Yinele", "Kes", "Kopyala", "Yapıştır", "Sil",
                   "Tümünü Seç"):
        cevrilmis = QCoreApplication.translate("EditorWidget", kaynak)
        assert cevrilmis in ogeler, (kaynak, cevrilmis, ogeler)


def test_KISAYOLLAR_menude_gorunuyor(editor, menu_ac):
    """Yerlesik menu de kisayolu gosteriyordu; ogretici bilgi kaybolmasin."""
    ogeler = [m for m, _e, sep in menu_ac(editor) if not sep]
    for parca in ("Ctrl+Z", "Ctrl+Y", "Ctrl+X", "Ctrl+C", "Ctrl+V", "Ctrl+A"):
        assert any(parca in o for o in ogeler), (parca, ogeler)


def test_SECIM_yokken_kopyala_ve_kes_PASIF(editor, menu_ac):
    d = _durumlar(menu_ac(editor))
    assert d["Kopyala"] is False, d
    assert d["Kes"] is False, d
    assert d["Tümünü Seç"] is True, d


def test_SECIM_varken_kopyala_ve_kes_ETKIN(editor, menu_ac):
    editor.selectAll()
    d = _durumlar(menu_ac(editor))
    assert d["Kopyala"] is True, d
    assert d["Kes"] is True, d


def test_SALT_OKUNUR_editorde_yazan_islemler_pasif(qapp, menu_ac):
    """Kopyalamak serbest, degistirmek degil."""
    ed = EditorWidget(theme=THEMES["dark"])
    try:
        ed.setText("abc")
        ed.setReadOnly(True)
        ed.selectAll()
        QApplication.clipboard().setText("panoda metin")
        d = _durumlar(menu_ac(ed))
        assert d["Kes"] is False, d
        assert d["Yapıştır"] is False, d
        assert d["Sil"] is False, d
        assert d["Kopyala"] is True, d
    finally:
        ed.deleteLater()
        qapp.processEvents()


def test_BOS_belgede_tumunu_sec_pasif(qapp, menu_ac):
    """Asiri duzeltme kapisi: durumlar sabit True dondurulmemeli."""
    ed = EditorWidget(theme=THEMES["dark"])
    try:
        d = _durumlar(menu_ac(ed))
        assert d["Tümünü Seç"] is False, d
    finally:
        ed.deleteLater()
        qapp.processEvents()


def test_TEMASIZ_editorde_de_menu_aciliyor(qapp, menu_ac):
    """`EditorWidget(theme=None)` mumkun; stil dali onu atlamali, cokmemeli."""
    ed = EditorWidget()
    try:
        ogeler = [m.split("\t")[0] for m, _e, sep in menu_ac(ed) if not sep]
        assert len(ogeler) == 7, ogeler
    finally:
        ed.deleteLater()
        qapp.processEvents()


def test_menu_GRUPLAMASI_korunuyor(editor, menu_ac):
    """Iki ayirac: (geri al/yinele) | (kes..sil) | (tumunu sec)."""
    ogeler = menu_ac(editor)
    assert sum(1 for _m, _e, sep in ogeler if sep) == 2, ogeler


# =====================================================================
# Qt'nin KENDI menuleri de arayuz dilinde olmali
#
# Uygulama yalniz `latexeditor_<dil>.qm`i yukluyordu. Qt'nin kendi urettigi
# arayuz parcalari o katalogda YOK: `QLineEdit`/`QTextEdit` sag tik menusu,
# standart diyalog dugmeleri. Turkce arayuzde Ingilizce kaliyorlardi
# (kullanici bildirdi 2026-09-06: kaynakca suzme kutusunun sag tik menusu).
# `qtbase_tr.qm` PyQt6 ile birlikte GELIYOR, yuklenmiyordu.
#
# Bu, editorun kendi menusunden AYRI bir kusur: editorunki QScintilla'nin
# katalogunda, bu Qt'nin katalogunda.
# =====================================================================


@pytest.fixture(scope="module")
def _tr_yuklu(qapp):
    """Arayuz dilini Turkceye alip cevirmenleri kur, sonra GERI AL.

    Iki yan etki temizleniyor:
    - `QSettings` kalici yaziyor (Windows'ta kayit defteri). Temizlenmezse
      testi kosturan kisinin uygulamasi Turkceye donerdi.
    - `installTranslator` oturum boyu duruyor. Temizlenmezse ayni pytest
      kosusundaki sonraki dosyalar cevrili metin gorurdu.
    """
    from PyQt6.QtCore import QSettings
    import core.i18n as i18n

    ayar = QSettings("LatexEditor", "LatexEditor")
    onceki = ayar.value("language", None)
    onceki_backend, onceki_qt = i18n._backend, i18n._qt_translator

    ayar.setValue("language", "tr")
    i18n.init(qapp)
    yield i18n

    for ceviren in (i18n._qt_translator,
                    getattr(i18n._backend, "_translator", None)):
        if ceviren is not None:
            qapp.removeTranslator(ceviren)
    i18n._backend, i18n._qt_translator = onceki_backend, onceki_qt
    if onceki is None:
        ayar.remove("language")
    else:
        ayar.setValue("language", onceki)


def _qt_menu_metinleri(w):
    m = w.createStandardContextMenu()
    # Qt kisayol harfini `&` ile isaretliyor ("Ko&pyala"), kisayolu `\t` ile.
    out = [a.text().replace("&", "").split("\t")[0]
           for a in m.actions() if a.text()]
    m.deleteLater()
    return out


def test_QT_cevirmeni_kuruluyor(_tr_yuklu):
    """Referans MODUL DUZEYINDE tutulmali: installTranslator sahiplik almiyor."""
    assert _tr_yuklu._qt_translator is not None, (
        "Qt cevirmeni kurulmamis; qtbase_<dil>.qm yuklenmiyor")


def test_QLINEEDIT_sagtik_menusu_arayuz_dilinde(qapp, _tr_yuklu):
    """Kullanicinin bildirdigi yer: suzme kutusunun sag tik menusu."""
    from PyQt6.QtWidgets import QLineEdit

    le = QLineEdit()
    try:
        le.setText("kaynakca suzme")
        ogeler = _qt_menu_metinleri(le)
        assert not (_INGILIZCE & set(ogeler)), ogeler
        assert {"Geri Al", "Kopyala", "Yapıştır", "Tümünü Seç"} <= set(ogeler), \
            ogeler
    finally:
        le.deleteLater()
        qapp.processEvents()


def test_QTEXTEDIT_sagtik_menusu_de_ayni(qapp, _tr_yuklu):
    from PyQt6.QtWidgets import QTextEdit

    te = QTextEdit()
    try:
        te.setPlainText("metin")
        assert not (_INGILIZCE & set(_qt_menu_metinleri(te)))
    finally:
        te.deleteLater()
        qapp.processEvents()


def test_UYGULAMANIN_kendi_cevirisi_bozulmadi(_tr_yuklu):
    """Asiri duzeltme kapisi: Qt cevirmeni bizimkini ezmemeli."""
    from PyQt6.QtCore import QCoreApplication

    assert QCoreApplication.translate("EditorWidget", "Kopyala") == "Kopyala"
