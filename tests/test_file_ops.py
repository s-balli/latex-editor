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
        # Sekme BASINA farkli cevap: `_open_folder` her kirli sekmeye
        # ayri soruyor ve iptalin ONCEKI cevaplari uygulamamis olmasi
        # sinaniyor. Bosken `save_reply` gecerli (eski testler).
        self.save_replies = []
        # TabOpsMixin._close_tab_safe'in dokunduğu durumlar
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None

    def _add_tab_close_button(self, index):
        pass  # QWidget değiliz; kapat düğmesi bu testlerin konusu değil

    # --- test no-op/recorder katmanı ---
    def _save_dialog(self, name):
        if self.save_replies:
            return self.save_replies.pop(0)
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


def test_new_file_imleci_govdeye_koyuyor(qapp, tmp_path, monkeypatch):
    r"""İmleç `\end{document}` satırında değil, boş gövde satırında olmalı.

    Satır 3 kapanış etiketi. İmleç oraya konunca ilk tuş vuruşu etiketin
    SOLUNA, aynı satıra düşüyor ve gövde ile `\end{document}` tek satırda
    birleşiyordu. Ayrıca derleme sonrası SyncTeX ileri araması belgenin
    SONUNA gidiyordu, çünkü imleç kapanış etiketindeydi.
    """
    stub = _Stub([])
    yol = str(tmp_path / "yeni.tex")
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (yol, "")))

    stub._new_file()

    ed = stub._editor_tabs.widget(0)
    satir, sutun = ed.getCursorPosition()
    assert (satir, sutun) == (2, 0)
    assert ed.text(satir).strip() == "", "imleç boş gövde satırında olmalı"
    assert ed.text(satir + 1).startswith("\\end{document}")


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


# --- Büyük dosya açmadan önce sorulmalı ---


from PyQt6.QtWidgets import QMessageBox as _GercekQMB


def _buyuk(tmp_path, mb, ad="dev.log"):
    y = tmp_path / ad
    y.write_bytes(b"x" * (mb * 1024 * 1024 + 1))
    return str(y)


def test_buyuk_dosya_soruluyor_ve_hayirda_acilmiyor(qapp, tmp_path, monkeypatch):
    """Açılış SENKRON: ~0.53 sn/MB, yani 40 MB'lık dosyada pencere 21 saniye
    yanıt vermiyor (ölçüldü 2026-09-02).

    Dosya seçicide "Tüm Dosyalar (*)" olduğu için yanlışlıkla büyük bir .log
    seçmek kolay; çökme yok ama kullanıcı ne olduğunu anlamıyor.
    """
    stub = _Stub([])
    yol = _buyuk(tmp_path, 11)
    sorulan = []

    class _SahteQMB:
        StandardButton = _GercekQMB.StandardButton

        @staticmethod
        def question(parent, baslik, metin, *a, **k):
            sorulan.append(metin)
            return _SahteQMB.StandardButton.No

    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", _SahteQMB)

    stub._open_file_in_editor(yol)

    assert len(sorulan) == 1
    assert "11 MB" in sorulan[0] or "MB" in sorulan[0]
    assert stub._editor_tabs.count() == 0, "hayır denince açılmamalı"


def test_kucuk_dosya_sorulmuyor(qapp, tmp_path, monkeypatch):
    stub = _Stub([])
    yol = _tex(tmp_path)
    sorulan = []

    class _SahteQMB:
        StandardButton = _GercekQMB.StandardButton

        @staticmethod
        def question(parent, baslik, metin, *a, **k):
            sorulan.append(metin)
            return _SahteQMB.StandardButton.No

    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", _SahteQMB)

    stub._open_file_in_editor(yol)

    assert sorulan == []
    assert stub._editor_tabs.count() == 1


def test_oturum_geri_yuklemede_sorulmuyor(qapp, tmp_path, monkeypatch):
    """Geçen oturumda açık olan dosya için açılışta dialog çıkmamalı."""
    stub = _Stub([])
    yol = _buyuk(tmp_path, 11, "buyuk.tex")
    sorulan = []

    class _SahteQMB:
        StandardButton = _GercekQMB.StandardButton

        @staticmethod
        def question(parent, baslik, metin, *a, **k):
            sorulan.append(metin)
            return _SahteQMB.StandardButton.No

    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox", _SahteQMB)

    stub._open_file_in_editor(yol, add_recent=False)

    assert sorulan == [], "oturum geri yüklemede sorulmamalı"
    assert stub._editor_tabs.count() == 1


def test_motor_algilama_BUYUK_HARFLI_uzantida_da_kosuyor(qapp, tmp_path,
                                                         monkeypatch):
    """`.TEX` acilinca motor algilama HIC kosmuyordu.

    Guard `path.endswith(".tex")` idi, yani harf duyarli. Gercek sablonda
    var: `template34-tez` kok dosyasi `iufenbil_tez_sablonu.TEX`. O belge
    acilinca bir onceki belgenin motoru kaliyor, yanlis motorla derleniyordu.

    2026-09-04'te MiKTeX olcumu sirasinda bulundu.
    """
    from gui.mixins import file_ops as fo

    cagrilan = []
    monkeypatch.setattr(fo, "_detect_engine_auto",
                        lambda p: cagrilan.append(p) or "lualatex")

    stub = _Stub([])
    # Guard'i gectikten sonra motor kutusuna dokunuyor; testin derdi o degil,
    # yalniz algilamanin CAGRILIP cagrilmadigi. En kucuk sahte yeterli.
    stub._engine_combo = SimpleNamespace(findText=lambda s: -1,
                                         currentIndex=lambda: 0)

    for ad in ("kucuk.tex", "BUYUK.TEX"):
        yol = tmp_path / ad
        yol.write_text("\\documentclass{article}\n", encoding="utf-8")
        fo.FileOpsMixin._detect_engine(stub, str(yol))

    assert len(cagrilan) == 2, (
        "buyuk harfli uzantida algilama atlandi: %s" % cagrilan)


# =====================================================================
# Dosya diyalogları AÇIK PROJEDEN başlamalı
#
# Dördü de `QFileDialog`a boş yol veriyordu; Qt boş yolda süreç çalışma
# dizinini kullanıyor (ölçüldü 2026-09-07) ve o dizinin kullanıcının
# projesiyle ilgisi yok. Proje kökü zaten elde duruyordu, yalnız
# `_quick_open` kullanıyordu.
#
# LaTeX'te bedeli gezinmekten fazlası: proje kökünün dışına kaydedilen bir
# dosya `\input` ile bulunmuyor ve dosya ağacında görünmüyor.
# =====================================================================


class _DialogKaydedici:
    """Statik QFileDialog fonksiyonlarının yerine geçer; argümanı saklar."""

    def __init__(self):
        self.cagrilar = []

    def getSaveFileName(self, parent, baslik, dizin="", suzgec="", *a, **k):
        self.cagrilar.append((baslik, dizin))
        return "", ""

    def getOpenFileNames(self, parent, baslik, dizin="", suzgec="", *a, **k):
        self.cagrilar.append((baslik, dizin))
        return [], ""


@pytest.fixture
def dialog_kaydi(monkeypatch):
    from gui.mixins import file_ops as fo
    k = _DialogKaydedici()
    monkeypatch.setattr(fo, "QFileDialog", k)
    return k


def _proje_stub(tmp_path, ad="bolum3.tex"):
    """Kökü açık, alt klasörde bir belge açık pencere."""
    proje = tmp_path / "proje"
    (proje / "bolumler").mkdir(parents=True)
    belge = proje / "bolumler" / ad
    belge.write_text("\\documentclass{article}\n", encoding="utf-8")
    ed = EditorWidget()
    assert ed.open_file(str(belge))
    stub = _Stub([ed])
    stub._file_tree._root = str(proje)
    return stub, str(proje), str(belge)


def test_YENI_DOSYA_proje_kokunden_basliyor(qapp, tmp_path, dialog_kaydi):
    r"""Kırılırsa: yeni dosya projenin dışına düşüyor ve `\input` bulmuyor."""
    stub, proje, _belge = _proje_stub(tmp_path)
    stub._new_file()
    assert dialog_kaydi.cagrilar, "dialog hiç açılmadı"
    assert dialog_kaydi.cagrilar[0][1] == proje


def test_DOSYA_AC_proje_kokunden_basliyor(qapp, tmp_path, dialog_kaydi):
    stub, proje, _belge = _proje_stub(tmp_path)
    stub._open_file()
    assert dialog_kaydi.cagrilar[0][1] == proje


def test_FARKLI_KAYDET_belgenin_kendi_yolunu_oneriyor(qapp, tmp_path,
                                                      dialog_kaydi):
    """"Aynı yere, başka adla" en sık istenen şey; ad da hazır gelmeli."""
    stub, _proje, belge = _proje_stub(tmp_path)
    stub._save_file_as()
    assert dialog_kaydi.cagrilar[0][1] == os.path.normpath(belge)


def test_DISA_AKTAR_belgenin_YANINA_oneriyor(qapp, tmp_path, dialog_kaydi):
    """Çıplak ad süreç çalışma dizinine göre çözülüyordu."""
    stub, _proje, belge = _proje_stub(tmp_path)
    stub._pandoc_available = True
    stub._save_if_open = lambda p: True
    stub._export_file("HTML", ".html")
    assert dialog_kaydi.cagrilar[0][1] == os.path.join(
        os.path.dirname(os.path.normpath(belge)), "bolum3.html")


def test_KLASOR_YOKKEN_belgenin_yanindan_basliyor(qapp, tmp_path,
                                                  dialog_kaydi):
    """Proje açık değilse açık belgenin klasörü kullanılmalı."""
    stub, _proje, belge = _proje_stub(tmp_path)
    stub._file_tree._root = ""
    stub._new_file()
    assert dialog_kaydi.cagrilar[0][1] == os.path.dirname(
        os.path.normpath(belge))


def test_HICBIR_SEY_yokken_bos_yol_donuyor(qapp, tmp_path, dialog_kaydi):
    """Aşırı düzeltme kapısı: uydurma bir dizine gitmemeli."""
    stub = _Stub([])
    stub._file_tree._root = ""
    assert stub._dialog_dizini() == ""


def test_kok_SILINMISSE_uydurulmuyor(qapp, tmp_path):
    """Ayar dosyasında kalmış eski bir kök gerçek olmayabilir."""
    stub = _Stub([])
    stub._file_tree._root = str(tmp_path / "yok_boyle_bir_yer")
    assert stub._dialog_dizini() == ""


# =====================================================================
# Son Açılanlar: girdilerin hepsi silinmişse menü BOMBOŞ açılıyordu
#
# "(boş)" kararı HAM listeye bakıyordu: beş girdinin beşi de silinmişse
# koşul False, döngü de hiçbir şey eklemiyor. Ölçüldü (2026-09-07):
# kayıtlı 5 girdi, menüde 0 öğe, yer tutucu da yok.
# =====================================================================


def test_recent_menu_TUM_girdiler_silinmisse_bos_yer_tutucu_koyuyor(
        qapp, tmp_path):
    from PyQt6.QtWidgets import QMenu
    stub = _RecentStub([EditorWidget()])
    stub._recent_menu = QMenu()
    olu = [str(tmp_path / ("olu%d.tex" % i)) for i in range(5)]
    stub._settings.setValue("recent_files", olu)

    stub._refresh_recent_menu()

    eylemler = stub._recent_menu.actions()
    assert len(eylemler) == 1, "menü boş açıldı ya da ölü girdi gösterdi"
    assert not eylemler[0].isEnabled()
    assert eylemler[0].data() is None


def test_recent_menu_var_olan_girdiler_HALA_gosteriliyor(qapp, tmp_path):
    """Aşırı düzeltme kapısı: yaşayan girdiler yer tutucuya kurban gitmesin."""
    from PyQt6.QtWidgets import QMenu
    canli = tmp_path / "canli.tex"
    canli.write_text("x", encoding="utf-8")
    stub = _RecentStub([EditorWidget()])
    stub._recent_menu = QMenu()
    stub._settings.setValue(
        "recent_files", [str(tmp_path / "olu.tex"), str(canli)])

    stub._refresh_recent_menu()

    veriler = [a.data() for a in stub._recent_menu.actions()]
    assert veriler == [str(canli)]


def test_recent_menu_olu_girdiyi_LISTEDEN_silmiyor(qapp, tmp_path):
    """Kopmuş bir ağ sürücüsündeki dosya unutulmamalı, yalnız o an
    gösterilmemeli."""
    from PyQt6.QtWidgets import QMenu
    stub = _RecentStub([EditorWidget()])
    stub._recent_menu = QMenu()
    olu = [str(tmp_path / "olu.tex")]
    stub._settings.setValue("recent_files", olu)

    stub._refresh_recent_menu()

    assert stub._settings.value("recent_files") == olu


# =====================================================================
# "Klasör Aç" iptali, ÖNCEKİ cevapları da uygulamamış olmalı
#
# `_open_folder` her kirli sekmeye ayrı soruyor. Cevap alınır alınmaz
# uygulanıyordu ve "Kaydetme" HEMEN `setModified(False)` çağırıyordu.
# ÖLÇÜLDÜ (2026-09-08), iki kirli sekmeyle: 1. sekmeye "Kaydetme",
# 2. sekmeye "İptal" -> klasör değişmedi, hiçbir sekme kapanmadı (doğru), ama
# 1. sekmenin kirli işareti düşmüştü. Kaydedilmemiş metin editörde duruyor,
# uygulama onu kaydedilmiş sanıyor: o sekme kapatılırken artık soru ÇIKMIYOR
# ve emek uyarısız gidiyor.
#
# "Kaydetme" cevabı "kapatırken kaydetme" demek; hiçbir şey kapanmadıysa
# hükmü de yok. Dosyanın kendi yorumu bu dersi kapanma tarafında zaten
# yazmıştı ("yarım durum kalıyordu"), kirli işaret tarafında almamıştı.
# =====================================================================


def _iki_kirli(tmp_path):
    ed1 = _editor(_tex(tmp_path, "a.tex"))
    ed2 = _editor(_tex(tmp_path, "b.tex"))
    ed1.insert("BIRINCIDE KAYDEDILMEMIS EMEK")
    ed2.insert("IKINCIDE KAYDEDILMEMIS EMEK")
    assert ed1.isModified() and ed2.isModified()
    return ed1, ed2


def _hedef(tmp_path, monkeypatch):
    other = tmp_path / "diger"
    other.mkdir()
    monkeypatch.setattr(
        "gui.mixins.file_ops.QFileDialog.getExistingDirectory",
        staticmethod(lambda *a, **k: str(other)))
    return other


def test_iptal_ONCEKI_kaydetme_cevabini_uygulamiyor(qapp, tmp_path,
                                                    monkeypatch):
    """Kırılırsa: iptal edilen bir işlem, bir belgeyi sessizce 'kaydedilmiş'
    gösterir ve o sekme kapanırken soru çıkmaz."""
    ed1, ed2 = _iki_kirli(tmp_path)
    stub = _Stub([ed1, ed2])
    stub.save_replies = ["discard", "cancel"]
    _hedef(tmp_path, monkeypatch)

    stub._open_folder()

    assert stub._file_tree.roots == []           # klasör değişmedi
    assert stub._editor_tabs.count() == 2        # hiçbir sekme kapanmadı
    assert ed1.isModified(), "iptal edildi ama kirli işaret düşürüldü"
    assert ed2.isModified()


def test_iptal_ONCEKI_kaydet_cevabini_da_uygulamiyor(qapp, tmp_path,
                                                     monkeypatch):
    """Kayıt da bir yan etki: sorular bitmeden diske yazılmamalı."""
    ed1, ed2 = _iki_kirli(tmp_path)
    stub = _Stub([ed1, ed2])
    stub.save_replies = ["save", "cancel"]
    _hedef(tmp_path, monkeypatch)
    yazilan = []
    # Sahte kayit GERCEGI taklit etmeli: `save_file` basarili olunca
    # kirli isareti dusuruyor. Dusurmeyen bir sahte, `_close_tab_safe`i
    # ikinci kez sordurup testi yaniltiyordu (birebir yasandi).
    monkeypatch.setattr(
        EditorWidget, "save_file",
        lambda self: (yazilan.append(self.file_path),
                      self.setModified(False), True)[2])

    stub._open_folder()

    assert yazilan == [], "iptalden önce diske yazıldı: %r" % (yazilan,)
    assert stub._file_tree.roots == []


def test_HEPSI_cevaplaninca_kararlar_uygulaniyor(qapp, tmp_path, monkeypatch):
    """Aşırı düzeltme kapısı: olağan yol bozulmamalı."""
    ed1, ed2 = _iki_kirli(tmp_path)
    stub = _Stub([ed1, ed2])
    stub.save_replies = ["save", "discard"]
    _hedef(tmp_path, monkeypatch)
    yazilan = []
    # Sahte kayit GERCEGI taklit etmeli: `save_file` basarili olunca
    # kirli isareti dusuruyor. Dusurmeyen bir sahte, `_close_tab_safe`i
    # ikinci kez sordurup testi yaniltiyordu (birebir yasandi).
    monkeypatch.setattr(
        EditorWidget, "save_file",
        lambda self: (yazilan.append(self.file_path),
                      self.setModified(False), True)[2])

    stub._open_folder()

    assert len(yazilan) == 1, yazilan
    assert not ed2.isModified(), "discard uygulanmadı"
    assert stub._editor_tabs.count() == 0        # hepsi kapandı
    assert len(stub._file_tree.roots) == 1       # klasör değişti


def test_KAYIT_DUSERSE_kirli_isaretler_dusurulmuyor(qapp, tmp_path,
                                                    monkeypatch):
    """Kayıt hatası da yarım durum bırakmamalı: 'Kaydetme' denen sekme,
    başka bir sekmenin kaydı düştüğü için hâlâ açık kalıyor."""
    ed1, ed2 = _iki_kirli(tmp_path)
    stub = _Stub([ed1, ed2])
    # 1. sekme "Kaydetme", 2. sekme "Kaydet" ve kayıt DÜŞÜYOR
    stub.save_replies = ["discard", "save"]
    _hedef(tmp_path, monkeypatch)
    monkeypatch.setattr(EditorWidget, "save_file", lambda self: False)

    stub._open_folder()

    assert stub._file_tree.roots == []
    assert stub._editor_tabs.count() == 2
    assert ed1.isModified(), "kayıt düştü ama başka sekmenin işareti düşürüldü"


def test_ACMA_DIYALOGU_kaynak_uzantilariyla_AYNI_kumeyi_gosteriyor(
        qapp, monkeypatch):
    """"Dosya Aç" süzgeci `KAYNAK_UZANTILARI` ile aynı kümeyi göstermeli.

    O sabitin kendi yorumu "TEK KAYNAK: klasör ağacı, hızlı aç, projede ara,
    Birlikte Aç ve sürükle bırak hepsi buradan alır" diyor ve altı kopyanın
    nasıl ayrıştığı orada ölçülmüş. Ama uygulamanın EN ÇOK kullanılan giriş
    kapısı, "Dosya Aç" diyaloğu, kümeyi kendi metninde elle taşıyor ve o
    listede yok. Bugün ikisi aynı; bu kapı aynı kalmalarını sağlıyor,
    çünkü sabite eklenen bir uzantı diyalogda görünmezse kullanıcı kendi
    dosyasını listede bulamaz.
    """
    import re as _re

    from core.fs_ops import KAYNAK_UZANTILARI
    from gui.mixins import file_ops as fo

    yakalanan = {}

    def sahte(parent, baslik, dizin, filtre):
        yakalanan["filtre"] = filtre
        return [], ""

    monkeypatch.setattr(fo.QFileDialog, "getOpenFileNames",
                        staticmethod(sahte))
    _Stub([])._open_file()

    ilk_grup = yakalanan["filtre"].split(";;")[0]
    ekler = set(_re.findall(r"\*(\.\w+)", ilk_grup))
    assert ekler == set(KAYNAK_UZANTILARI), (ekler, KAYNAK_UZANTILARI)
