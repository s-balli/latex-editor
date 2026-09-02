"""FileOpsMixin — klasör açma/yeni dosya/dışa aktarma/recent davranışları.

Regression odağı: _open_folder iptalinde yarım durum, kayıt başarısızlığında
sahte yollu sekme, meşgul kontrolünün dialog'dan sonra gelmesi, oturum geri
yüklemede Son Açılanlar'ın ezilmesi.
"""

import os
from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.editor import EditorWidget
    from gui.mixins.file_ops import FileOpsMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from gui.theme import THEMES
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Stub(FileOpsMixin, TabOpsMixin, StubMain):
    def __init__(self, editors):
        StubMain.__init__(self, editors=editors)
        self._theme_mgr = SimpleNamespace(theme=THEMES["dark"])
        self._pdf_viewer = SimpleNamespace(clear=lambda: None)
        roots = []
        self._file_tree = SimpleNamespace(
            _root="", set_root=lambda p: roots.append(p))
        self._file_tree.roots = roots
        self.recent_calls = []
        self.watch_added = []
        self.watch_removed = []
        self.save_reply = "cancel"
        # TabOpsMixin._close_tab_safe'in dokunduğu durumlar
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None

    def _add_tab_close_button(self, index):
        pass  # QWidget değiliz; kapat düğmesi bu testlerin konusu değil

    # --- test no-op/recorder katmanı ---
    def _save_dialog(self, name):
        return self.save_reply

    def _add_recent(self, path):
        self.recent_calls.append(path)

    def _file_watch_add(self, path):
        self.watch_added.append(path)

    def _file_watch_remove(self, path):
        self.watch_removed.append(path)

    def _refresh_recent_menu(self):
        pass

    def _detect_engine(self, path):
        pass

    def _apply_editor_settings(self, editor):
        pass

    def _refresh_history(self):
        pass

    def _on_forward_search(self, *a):
        pass

    def _paste_image(self):
        pass

    def _on_rename_label(self, key):
        pass

    def _on_rename_cite(self, key):
        pass

    def _on_rename_bibitem(self, key):
        pass

    def _on_goto_definition(self, key, kind):
        pass


def _tex(tmp_path, name="ana.tex"):
    p = tmp_path / name
    p.write_text("\\begin{document}\nmerhaba\n\\end{document}\n", encoding="utf-8")
    return str(p)


def _editor(tex):
    ed = EditorWidget()
    assert ed.open_file(tex)
    return ed


# --- _open_folder: kayıt kararları kapanmadan önce ---


def test_open_folder_iptal_hicbir_sekme_kapanmaz(qapp, tmp_path, monkeypatch):
    """İptal: yarım kapanmış sekme + değişmemiş klasör durumu kalmasın."""
    ed1 = _editor(_tex(tmp_path, "a.tex"))
    ed2 = _editor(_tex(tmp_path, "b.tex"))
    ed1.insert("x")                      # dirty
    stub = _Stub([ed1, ed2])
    stub.save_reply = "cancel"
    other = tmp_path / "diger"
    other.mkdir()
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(other)))

    stub._open_folder()

    assert stub._editor_tabs.count() == 2        # hiçbir sekme kapanmadı
    assert stub._file_tree.roots == []           # klasör değişmedi


def test_open_folder_kayit_basarisisiz_durur(qapp, tmp_path, monkeypatch):
    ed = _editor(_tex(tmp_path))
    ed.insert("x")
    stub = _Stub([ed])
    stub.save_reply = "save"
    monkeypatch.setattr(EditorWidget, "save_file", lambda self: False)
    other = tmp_path / "diger"
    other.mkdir()
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(other)))

    stub._open_folder()

    assert stub._editor_tabs.count() == 1
    assert stub._file_tree.roots == []


def test_open_folder_discard_sekmeler_kapanir_kok_degisir(qapp, tmp_path, monkeypatch):
    ed = _editor(_tex(tmp_path))
    ed.insert("x")
    stub = _Stub([ed])
    stub.save_reply = "discard"
    other = tmp_path / "diger"
    other.mkdir()
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(other)))

    stub._open_folder()

    assert stub._editor_tabs.count() == 0
    assert stub._file_tree.roots == [str(other)]


# --- _new_file: kayıt başarısızsa sekme açılmasın ---


def test_new_file_kayit_basarisiz_tab_eklenmez(qapp, tmp_path, monkeypatch):
    stub = _Stub([])
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "yeni.tex"), "")))
    monkeypatch.setattr(EditorWidget, "save_file_as", lambda self, p: False)

    stub._new_file()

    assert stub._editor_tabs.count() == 0
    assert stub.recent_calls == [] and stub.watch_added == []


# --- _export_file: meşgul kontrolü hedef dialogundan önce ---


def test_export_busy_dialog_oncesi_reddedilir(qapp, tmp_path, monkeypatch):
    ed = _editor(_tex(tmp_path))
    stub = _Stub([ed])
    stub._export_busy = True
    dialogs = []
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: dialogs.append(a) or ("", "")))

    stub._export_file("HTML", ".html")

    assert dialogs == []                          # dialog hiç açılmadı
    assert "sürüyor" in stub._status.msg


# --- _open_file_in_editor: oturum geri yükleme recent'e dokunmasın ---


def test_open_file_add_recent_false(qapp, tmp_path):
    stub = _Stub([])
    tex = _tex(tmp_path, "r1.tex")

    stub._open_file_in_editor(tex, add_recent=False)
    assert stub._editor_tabs.count() == 1
    assert stub.recent_calls == []                 # oturum restore yolu

    tex2 = _tex(tmp_path, "r2.tex")
    stub._open_file_in_editor(tex2)               # normal açış varsayılanı
    assert stub.recent_calls == [tex2]


# --- _on_file_renamed: dosya ağacındaki yeniden adlandırmayı sekme takip etsin


def test_yeniden_adlandirilan_dosya_sekmede_takip_ediliyor(qapp, tmp_path):
    """Sekme eski yola bağlı kalırsa Ctrl+S SİLİNMİŞ adı yeniden yaratır.

    Kullanıcı aynı içerikten iki dosyayla kalır ve hangisinin derlendiğini
    bilemez. Ayrıca izleme eski yolda asılı kalıp bir daha hiçbir dış
    değişikliği bildirmez.
    """
    eski = _tex(tmp_path, "eski.tex")
    ed = _editor(eski)
    stub = _Stub([ed])
    yeni = str(tmp_path / "yeni.tex")
    os.rename(eski, yeni)

    stub._on_file_renamed(eski, yeni)

    assert ed.file_path == os.path.normpath(yeni)
    assert stub._editor_tabs.tabText(0) == "yeni.tex"
    assert stub.watch_added == [yeni], stub.watch_added


def test_kirli_sekme_kirli_kaliyor_diske_yazilmiyor(qapp, tmp_path):
    """Yeniden adlandırma KAYDETME değildir.

    `save_file_as` çağırmak kirli sekmeyi zorla kaydeder, kodlamayı utf-8'e
    çevirir ve satır sonu stilini kaybederdi.
    """
    eski = _tex(tmp_path, "eski.tex")
    ed = _editor(eski)
    ed.insert("KAYDEDILMEMIS")
    assert ed.isModified()
    yeni = str(tmp_path / "yeni.tex")
    os.rename(eski, yeni)

    stub = _Stub([ed])
    stub._on_file_renamed(eski, yeni)

    assert ed.isModified(), "kirlilik yutuldu"
    assert "KAYDEDILMEMIS" not in open(yeni, encoding="utf-8").read()
    assert stub._editor_tabs.tabText(0) == "* yeni.tex"


def test_acik_olmayan_dosya_sekmelere_dokunmuyor(qapp, tmp_path):
    ed = _editor(_tex(tmp_path, "acik.tex"))
    stub = _Stub([ed])
    stub._on_file_renamed(str(tmp_path / "baska.tex"), str(tmp_path / "x.tex"))
    assert ed.file_path == os.path.normpath(str(tmp_path / "acik.tex"))


def test_son_acilanlar_guncelleniyor(qapp, tmp_path):
    """Eski yol Son Açılanlar'da ölü bağlantı olarak kalmasın."""
    eski = _tex(tmp_path, "eski.tex")
    baska = _tex(tmp_path, "baska.tex")
    ed = _editor(eski)
    stub = _Stub([ed])
    stub._settings.setValue("recent_files", [eski, baska])
    yeni = str(tmp_path / "yeni.tex")
    os.rename(eski, yeni)

    stub._on_file_renamed(eski, yeni)

    assert stub._settings.value("recent_files") == [yeni, baska]


# --- Bellek sızıntısı: tekrar kurulan menü ---
#
# `addAction(metin, lambda)` her çağrıda bir KAPANIŞ sızdırıyor: QMenu.clear()
# QAction'ı siliyor ama PyQt Python çağrılabilirini bırakmıyor. Ölçüldü
# (2026-09-02, gerçek MainWindow):
#
#     clear + 5 addAction(lambda)     +5,00 nesne/çağrı
#     clear + 5 addAction(lambda YOK) +0,00 nesne/çağrı
#
# Son Açılanlar menüsü HER dosya açılışında yenileniyor, yani sızıntı oturum
# boyunca birikiyordu: 60 turda nesne sayısı hiç doymadan büyüyordu. Yol artık
# öğenin verisinde taşınıyor ve menü TEK bir `triggered` sinyaline bağlı.


class _RecentStub(_Stub):
    """_Stub `_refresh_recent_menu`i no-op'a çeviriyor; burada GERÇEĞİ lazım."""

    _refresh_recent_menu = FileOpsMixin._refresh_recent_menu
    _on_recent_triggered = FileOpsMixin._on_recent_triggered


def _menu_stub(qapp, tmp_path):
    from PyQt6.QtWidgets import QMenu
    dosya = tmp_path / "a.tex"
    dosya.write_text("x", encoding="utf-8")
    ed = EditorWidget()
    stub = _RecentStub([ed])
    stub._recent_menu = QMenu()
    stub._settings.setValue("recent_files", [str(dosya)])
    return stub, str(dosya)


def test_recent_menu_yenilemesi_sizdirmiyor(qapp, tmp_path):
    """Menüyü N kez yenile: Python nesne sayısı BÜYÜMEMELİ."""
    import gc

    stub, _yol = _menu_stub(qapp, tmp_path)
    for _ in range(20):                      # ısınma
        stub._refresh_recent_menu()
    gc.collect()
    once = len(gc.get_objects())

    N = 100
    for _ in range(N):
        stub._refresh_recent_menu()
    gc.collect()
    artis = (len(gc.get_objects()) - once) / N

    # Lambda'lı hâlde bu sayı girdi başına 1,00 idi. Eşik gevşek tutuldu:
    # test kendi çöpünü de üretiyor, ölçülen şey DOĞRUSAL büyüme.
    assert artis < 0.5, f"menü yenilemesi nesne sızdırıyor: {artis:.2f}/çağrı"


def test_recent_menu_yolu_ogenin_verisinde(qapp, tmp_path):
    """Yol lambda'da değil `QAction.data()` içinde taşınmalı."""
    stub, yol = _menu_stub(qapp, tmp_path)
    stub._refresh_recent_menu()
    eylemler = [a for a in stub._recent_menu.actions() if a.isEnabled()]
    assert eylemler, "menüde öğe yok"
    assert eylemler[0].data() == yol


def test_recent_menu_tiklama_dosyayi_aciyor(qapp, tmp_path):
    """Veri taşımak işe yaramalı: tetiklenince dosya açılmalı."""
    stub, yol = _menu_stub(qapp, tmp_path)
    stub._refresh_recent_menu()
    eylem = [a for a in stub._recent_menu.actions() if a.isEnabled()][0]
    stub._on_recent_triggered(eylem)
    acilan = [stub._editor_tabs.widget(i).file_path
              for i in range(stub._editor_tabs.count())]
    assert os.path.normpath(yol) in [os.path.normpath(x) for x in acilan if x]


def test_recent_menu_bos_veride_cokmuyor(qapp, tmp_path):
    """'(boş)' öğesinin verisi yok; tıklama sessizce geçmeli."""
    from PyQt6.QtGui import QAction
    stub, _yol = _menu_stub(qapp, tmp_path)
    stub._on_recent_triggered(QAction("x"))          # data() None
    assert stub._editor_tabs.count() == 1            # yeni sekme açılmadı


def test_menu_tek_sinyale_bagli():
    """Bağlantı KURULUM'da bir kez yapılmalı, öğe başına değil."""
    kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(kok, "desktop", "gui", "main_window.py"),
              encoding="utf-8") as f:
        mw = f.read()
    assert "self._recent_menu.triggered.connect(self._on_recent_triggered)" in mw
    with open(os.path.join(kok, "desktop", "gui", "mixins", "file_ops.py"),
              encoding="utf-8") as f:
        fo = f.read()
    # Yenilenen menüde lambda kalmamalı
    bolum = fo[fo.index("def _refresh_recent_menu"):fo.index("def _on_recent_triggered")]
    # Yorumda geçen kelimeye değil GERÇEK çağrıya bak: kapanış yeniden
    # eklenirse addAction ikinci bir argüman alır.
    kod = [l for l in bolum.splitlines() if not l.strip().startswith("#")]
    assert not [l for l in kod if "lambda" in l], "menü yenilemesinde lambda geri gelmiş"
