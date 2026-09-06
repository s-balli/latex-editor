# -*- coding: utf-8 -*-
"""Sekme sağ tık menüsü: "Diğer Sekmeleri Kapat" ve "Tümünü Kapat".

Bu iki dalın hiç testi yoktu (`tab_ops.py` gerçek satır kapsamı %67) ve
ikisi de kullanıcının açık belgelerini kapatan yollar, yani yanlış
davranışın bedeli doğrudan kaybedilen iş.
"""

import os
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMenu, QWidget
    from gui.editor import EditorWidget
    from gui.mixins.tab_ops import TabOpsMixin
    from gui.theme import THEMES
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(QWidget, TabOpsMixin, StubMain):
    """`QMenu(self)` gerçek bir QWidget ebeveyn istiyor."""

    def __init__(self, editors):
        QWidget.__init__(self)
        StubMain.__init__(self, editors=editors)
        self.pdf_temizlendi = []
        self._pdf_viewer = SimpleNamespace(
            clear=lambda: self.pdf_temizlendi.append(1))
        self._current_pdf = ""
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None
        self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])
        self.save_reply = "discard"
        self.watch_removed = []

    def _save_dialog(self, name):
        return self.save_reply

    def _file_watch_remove(self, path):
        self.watch_removed.append(path)


def _editor(yol=""):
    """Kaydedilmiş (yol verilirse) ya da KAYDEDİLMEMİŞ (yol boş) sekme."""
    ed = EditorWidget()
    if yol:
        # `file_path` salt okunur bir özellik; gerçek yol iç alanda tutuluyor
        # ve `open_file`/`save_file` onu normpath ile yazıyor.
        ed._file_path = os.path.normpath(yol)
    return ed


@pytest.fixture
def menu_sec(monkeypatch):
    """Menüyü AÇMADAN istenen öğeyi seçilmiş gibi çalıştır."""
    def _sec(stub, index, metin):
        def _sahte(self, *a, **k):
            for act in self.actions():
                if act.text() == metin:
                    return act
            raise AssertionError("menüde yok: %s (%s)"
                                 % (metin, [a.text() for a in self.actions()]))

        monkeypatch.setattr(QMenu, "exec", _sahte)
        nokta = stub._editor_tabs.tabBar().tabRect(index).center()
        stub._tab_context_menu(nokta)
    return _sec


def _yollar(stub):
    return [stub._editor_tabs.widget(i).file_path or "(kaydedilmemiş)"
            for i in range(stub._editor_tabs.count())]


# =====================================================================
# "Diğer Sekmeleri Kapat" hedefi DOSYA YOLUYLA ayırt ediyordu
#
# Kaydedilmemiş sekmelerin `file_path`i "" olduğu için hepsi aynı hedef
# sayılıyordu: kullanıcı kaydedilmemiş bir sekmede "Diğerlerini Kapat"
# dediğinde ÖTEKİ kaydedilmemiş sekmeler de açık kalıyordu.
# =====================================================================

def test_KAYDEDILMEMIS_hedefte_oteki_kaydedilmemisler_de_kapaniyor(
        qapp, menu_sec, tmp_path):
    stub = _Stub([_editor(), _editor(), _editor(str(tmp_path / "c.tex"))])
    try:
        menu_sec(stub, 0, "Diğer Sekmeleri Kapat")
        assert stub._editor_tabs.count() == 1, _yollar(stub)
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_KAYDEDILMEMIS_hedef_sekmesi_KENDISI_kaliyor(qapp, menu_sec, tmp_path):
    """Aşırı düzeltme kapısı: sağ tıklanan sekme kapanmamalı."""
    hedef = _editor()
    stub = _Stub([hedef, _editor(), _editor(str(tmp_path / "c.tex"))])
    try:
        menu_sec(stub, 0, "Diğer Sekmeleri Kapat")
        assert stub._editor_tabs.count() == 1
        assert stub._editor_tabs.widget(0) is hedef
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_KAYITLI_hedefte_de_yalniz_o_kaliyor(qapp, menu_sec, tmp_path):
    hedef = _editor(str(tmp_path / "a.tex"))
    stub = _Stub([hedef, _editor(), _editor(str(tmp_path / "c.tex"))])
    try:
        menu_sec(stub, 0, "Diğer Sekmeleri Kapat")
        assert stub._editor_tabs.count() == 1
        assert stub._editor_tabs.widget(0) is hedef
    finally:
        stub.deleteLater()
        qapp.processEvents()


# =====================================================================
# "Tümünü Kapat" İPTAL edilse bile PDF'i temizliyordu
#
# Döngü `_close_tab_safe` False dönünce kırılıyor (kullanıcı vazgeçti,
# sekmeler açık kaldı) ama hemen ardından `_pdf_viewer.clear()` koşulsuz
# çalışıyordu: kullanıcı vazgeçtiği hâlde önizlemesini kaybediyordu.
# =====================================================================

def test_TUMUNU_KAPAT_iptal_edilince_PDF_duruyor(qapp, menu_sec, tmp_path):
    ed = _editor(str(tmp_path / "a.tex"))
    ed.insert("x")                      # kirli: soru sorulacak
    stub = _Stub([ed, _editor(str(tmp_path / "b.tex"))])
    stub.save_reply = "cancel"          # kullanıcı VAZGEÇİYOR
    stub._current_pdf = str(tmp_path / "a.pdf")
    try:
        menu_sec(stub, 0, "Tümünü Kapat")
        assert stub._editor_tabs.count() > 0, "ön koşul: sekme kalmalı"
        assert stub._current_pdf, "vazgeçildi ama PDF yolu silindi"
        assert not stub.pdf_temizlendi, "vazgeçildi ama önizleme temizlendi"
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_TUMUNU_KAPAT_gercekten_kapaninca_PDF_temizleniyor(qapp, menu_sec,
                                                           tmp_path):
    """Aşırı düzeltme kapısı: hepsi kapandıysa önizleme gitmeli."""
    stub = _Stub([_editor(str(tmp_path / "a.tex")),
                  _editor(str(tmp_path / "b.tex"))])
    stub._current_pdf = str(tmp_path / "a.pdf")
    try:
        menu_sec(stub, 0, "Tümünü Kapat")
        assert stub._editor_tabs.count() == 0
        assert stub._current_pdf == ""
        assert stub.pdf_temizlendi
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_YOLU_KOPYALA_panoya_yaziyor(qapp, menu_sec, tmp_path):
    yol = str(tmp_path / "a.tex")
    stub = _Stub([_editor(yol)])
    try:
        QApplication.clipboard().setText("")
        menu_sec(stub, 0, "Dosya Yolunu Kopyala")
        assert QApplication.clipboard().text() == yol
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_KAPAT_yalniz_o_sekmeyi_kapatiyor(qapp, menu_sec, tmp_path):
    kalan = _editor(str(tmp_path / "b.tex"))
    stub = _Stub([_editor(str(tmp_path / "a.tex")), kalan])
    try:
        menu_sec(stub, 0, "Kapat")
        assert stub._editor_tabs.count() == 1
        assert stub._editor_tabs.widget(0) is kalan
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_TUMUNU_KAPAT_ILGISIZ_pdf_i_de_temizliyor(qapp, menu_sec, tmp_path):
    """Temizliği YALNIZ bu dal yapabilir; kapı onu ölçmeli.

    `_close_tab_safe` kapanan sekmenin ürettiği PDF'i zaten temizliyor, yani
    `a.tex` + `a.pdf` kurulumunda bu dalın temizliği ölçülemiyor: mutasyon
    testi düşürmeden kaçtı (2026-09-06). Çok dosyalı projede gerçek hâl bu:
    kök `ana.tex` derlenmiş, açık sekmeler `bolum1/2.tex`, kök açık değil.
    """
    stub = _Stub([_editor(str(tmp_path / "bolum1.tex")),
                  _editor(str(tmp_path / "bolum2.tex"))])
    stub._current_pdf = str(tmp_path / "ana.pdf")
    try:
        menu_sec(stub, 0, "Tümünü Kapat")
        assert stub._editor_tabs.count() == 0
        assert stub._current_pdf == "", "kapanan sekmelerle ilgisiz PDF kaldı"
        assert stub.pdf_temizlendi
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_TUMUNU_KAPAT_iptalde_KALAN_sekmelere_dokunmuyor(qapp, menu_sec,
                                                         tmp_path):
    """Vazgeçilince döngü DURMALI, sıradakine geçmemeli.

    Döngü son sekmeden başa doğru gidiyor. Kirli sekme SONDA olmalı ki
    "vazgeç" ilk adımda gelsin ve öndeki temiz sekmeye hiç sıra gelmesin;
    kirli sekme başta olsaydı temiz sekme zaten önce kapanır, `break`in
    olup olmaması sonucu değiştirmezdi (mutasyon oradan kaçtı).
    """
    temiz = _editor(str(tmp_path / "temiz.tex"))
    kirli = _editor(str(tmp_path / "kirli.tex"))
    kirli.insert("x")
    stub = _Stub([temiz, kirli])
    stub.save_reply = "cancel"
    try:
        menu_sec(stub, 0, "Tümünü Kapat")
        assert stub._editor_tabs.count() == 2, (
            "vazgeçildi ama döngü sonraki sekmeyi de kapattı: %s"
            % _yollar(stub))
    finally:
        stub.deleteLater()
        qapp.processEvents()


def test_DIGERLERINI_KAPAT_iptalde_de_duruyor(qapp, menu_sec, tmp_path):
    """Aynı kural öteki dalda da geçerli."""
    hedef = _editor(str(tmp_path / "hedef.tex"))
    temiz = _editor(str(tmp_path / "temiz.tex"))
    kirli = _editor(str(tmp_path / "kirli.tex"))
    kirli.insert("x")
    stub = _Stub([hedef, temiz, kirli])
    stub.save_reply = "cancel"
    try:
        menu_sec(stub, 0, "Diğer Sekmeleri Kapat")
        assert stub._editor_tabs.count() == 3, _yollar(stub)
    finally:
        stub.deleteLater()
        qapp.processEvents()
