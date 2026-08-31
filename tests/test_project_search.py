"""Projede ara (Ctrl+Shift+F) — çekirdek arama, işçi ve panel.

Uygulamadaki diğer aramalardan farkı bu dosyanın konusu: Ctrl+F yalnız AÇIK
SEKMEDE, PDF araması derlenmiş PDF'te, Ctrl+P dosya ADLARINDA arar. Burada
aranan, sekmede açık olmayanlar dâhil tüm kaynak dosyalarının İÇERİĞİ.
"""

import os
import time
from types import SimpleNamespace

import pytest

from core.project_search import (
    Bulgu, SKIP_DIRS, coz, iter_project_files, search_project,
)


def _yaz(kok, rel, icerik, encoding="utf-8"):
    yol = os.path.join(kok, *rel.split("/"))
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding=encoding, newline="\n") as f:
        f.write(icerik)
    return yol


@pytest.fixture
def proje(tmp_path):
    """Küçük ama gerçekçi bir proje: alt dizin, atlanacak dizin, ilgisiz uzantı."""
    kok = str(tmp_path)
    _yaz(kok, "main.tex",
         "\\documentclass{article}\n"
         "\\input{bolum/giris}\n"
         "\\benimKomut{a}\n")
    _yaz(kok, "bolum/giris.tex",
         "\\section{Giriş}\n"
         "burada \\benimKomut kullanılıyor\n"
         "\\benimKomut ve yine \\benimKomut aynı satırda\n")
    _yaz(kok, "kaynaklar.bib", "@article{key1, title={benimKomut degil}}\n")
    _yaz(kok, "stil.sty", "\\ProvidesPackage{stil}\n")
    # aranmayacaklar
    _yaz(kok, "main.log", "\\benimKomut LOG icinde\n")
    _yaz(kok, "build/uretilmis.tex", "\\benimKomut build icinde\n")
    _yaz(kok, ".gizli/sakli.tex", "\\benimKomut gizli dizinde\n")
    return kok


# --------------------------------------------------------------------------
# Çekirdek: dosya yürüyüşü
# --------------------------------------------------------------------------

class TestDosyaYuruyusu:

    def test_yalniz_kaynak_uzantilari(self, proje):
        adlar = {os.path.basename(y) for y in iter_project_files(proje)}
        assert adlar == {"main.tex", "giris.tex", "kaynaklar.bib", "stil.sty"}

    def test_atlanan_ve_gizli_dizinlere_inilmiyor(self, proje):
        yollar = list(iter_project_files(proje))
        assert not [y for y in yollar if "build" in y.split(os.sep)]
        assert not [y for y in yollar if ".gizli" in y.split(os.sep)]

    def test_siralama_belirli(self, proje):
        assert list(iter_project_files(proje)) == list(iter_project_files(proje))

    def test_olmayan_kok_bos(self, tmp_path):
        assert list(iter_project_files(str(tmp_path / "yok"))) == []
        assert list(iter_project_files("")) == []

    def test_skip_dirs_tek_kaynak(self):
        """Aynı küme üç yerde kullanılıyor; kopyalanırsa sürükleniyor."""
        from gui.file_tree import _SKIP_DIRS as agac
        from gui.quick_open import _SKIP_DIRS as hizli
        assert agac is SKIP_DIRS and hizli is SKIP_DIRS


# --------------------------------------------------------------------------
# Çekirdek: eşleştirme
# --------------------------------------------------------------------------

class TestArama:

    def test_birden_fazla_dosyada_bulur(self, proje):
        bulgular, kesildi = search_project(proje, "benimKomut")
        assert not kesildi
        dosyalar = {os.path.basename(b.path) for b in bulgular}
        assert dosyalar == {"main.tex", "giris.tex", "kaynaklar.bib"}
        # .log, build/ ve .gizli/ içindekiler GELMEMELİ
        assert all("build" not in b.path and ".gizli" not in b.path
                   and not b.path.endswith(".log") for b in bulgular)

    def test_satir_numarasi_1_tabanli(self, proje):
        bulgular, _ = search_project(proje, "benimKomut")
        main = [b for b in bulgular if b.path.endswith("main.tex")]
        assert [b.line for b in main] == [3]

    def test_ayni_satirdaki_iki_eslesme_ayri_bulgu(self, proje):
        bulgular, _ = search_project(proje, "benimKomut")
        satir3 = [b for b in bulgular
                  if b.path.endswith("giris.tex") and b.line == 3]
        assert len(satir3) == 2
        assert satir3[0].col < satir3[1].col
        assert satir3[0].text == satir3[1].text     # aynı satır, farklı sütun

    def test_harf_duyarsiz_varsayilan(self, proje):
        assert search_project(proje, "benimkomut")[0]
        assert search_project(proje, "BENIMKOMUT")[0]
        assert search_project(proje, "BeNiMkOmUt")[0]

    def test_harf_duyarli_secenegi(self, proje):
        assert search_project(proje, "benimkomut", case_sensitive=True)[0] == []
        assert search_project(proje, "benimKomut", case_sensitive=True)[0]

    def test_satir_metni_kirpilmis_ve_bosluksuz(self, tmp_path):
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "        girintili hedef satır\n")
        (b,), _ = search_project(kok, "hedef")
        assert b.text == "girintili hedef satır"

    def test_bos_sorgu_bos_sonuc(self, proje):
        assert search_project(proje, "") == ([], False)

    def test_turkce_arama(self, proje):
        bulgular, _ = search_project(proje, "Giriş")
        assert len(bulgular) == 1 and bulgular[0].line == 1


class TestTurkceNoktaliI:
    """Düz `str.lower()` Türkçe belgede aramanın çoğunu KAÇIRIYOR.

    Unicode 'İ'yi 'i' + U+0307 yapıyor; metindeki 'İçindekiler' kullanıcının
    yazdığı 'içindekiler' ile eşleşmiyordu. Türkçe LaTeX belgesi bu
    başlıklarla dolu, yani kenar durumu değil.
    """

    @pytest.fixture
    def belge(self, tmp_path):
        kok = str(tmp_path)
        _yaz(kok, "a.tex",
             "\\section{İçindekiler}\n"
             "\\caption{Şekil 1: İSTANBUL haritası}\n"
             "\\label{fig:isik}\n"
             "ve ışık burada\n")
        return kok

    @pytest.mark.parametrize("sorgu", [
        "içindekiler", "İÇİNDEKİLER", "İçindekiler", "IÇINDEKILER",
        "istanbul", "İSTANBUL", "İstanbul",
        "şekil", "ŞEKİL",
    ])
    def test_noktali_I_her_iki_yonde_eslesiyor(self, belge, sorgu):
        bulgular, _ = search_project(belge, sorgu)
        assert bulgular, f"{sorgu!r} bulunamadı"

    def test_i_ve_noktasiz_i_ayrimi_KORUNUYOR(self, belge):
        """Yalnız birleşen nokta atılıyor; harf EŞLEMESİ değişmiyor.

        Yani düzeltme 'her şeyi birbirine karıştır' değil: ı ile i hâlâ
        ayrı harfler. Satır 3 etiket ('isik'), satır 4 metin ('ışık').
        """
        isikli = [b.line for b in search_project(belge, "ışık")[0]]
        etiketli = [b.line for b in search_project(belge, "isik")[0]]
        assert isikli == [4], isikli
        assert etiketli == [3], etiketli
        assert not set(isikli) & set(etiketli)

    def test_kucult_uzunlugu_koruyor(self):
        """col ofseti buna bağlı: 'İ' iki karaktere açılıp geri kapanıyor."""
        from core.project_search import kucult
        for s in ("İçindekiler", "ŞEKİL", "İİİ", "düz metin", ""):
            assert len(kucult(s)) == len(s), s

    def test_col_noktali_I_den_sonra_dogru(self, tmp_path):
        kok = str(tmp_path)
        satir = "İçindekiler ve hedef"
        _yaz(kok, "a.tex", satir + "\n")
        (b,), _ = search_project(kok, "hedef")
        assert b.col == satir.index("hedef")


class TestKodlama:
    """Eski Türkçe .tex dosyaları cp1254 olabiliyor — editör onları açabiliyor,
    arama da bulabilmeli, yoksa kullanıcı kendi dosyasında sonuç alamaz."""

    def test_cp1254_dosyada_bulunur(self, tmp_path):
        kok = str(tmp_path)
        yol = os.path.join(kok, "eski.tex")
        with open(yol, "wb") as f:
            f.write("\\section{Şekil ve Çizelge}\n".encode("cp1254"))
        bulgular, _ = search_project(kok, "Şekil")
        assert len(bulgular) == 1
        assert "Çizelge" in bulgular[0].text

    def test_coz_utf8_onceligi(self):
        assert coz("Şekil".encode("utf-8")) == "Şekil"
        assert coz("Şekil".encode("cp1254")) == "Şekil"

    def test_coz_cozulemeyeni_dusurmez(self):
        assert isinstance(coz(b"\xff\xfe\x00\x01ham"), str)


class TestSinirlarVeDayaniklilik:

    def test_sinira_takilinca_KESILDI_bildirilir(self, tmp_path):
        """Sessiz kırpma yanıltır: eksik listeyi tam sanmak yanlış sonuç verir."""
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 50)
        bulgular, kesildi = search_project(kok, "x", limit=10)
        assert kesildi is True and len(bulgular) == 10

    def test_sinir_asilmazsa_kesilmedi(self, tmp_path):
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 5)
        bulgular, kesildi = search_project(kok, "x", limit=100)
        assert kesildi is False and len(bulgular) == 5

    def test_iptal_taramayi_durdurur(self, tmp_path):
        kok = str(tmp_path)
        for i in range(20):
            _yaz(kok, f"d{i}.tex", "hedef\n")
        cagri = {"n": 0}

        def iptal():
            cagri["n"] += 1
            return cagri["n"] > 3

        bulgular, kesildi = search_project(kok, "hedef", iptal=iptal)
        assert kesildi is True
        assert len(bulgular) < 20

    def test_okunamayan_dosya_aramayi_dusurmez(self, tmp_path, monkeypatch):
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "hedef\n")
        _yaz(kok, "b.tex", "hedef\n")
        gercek_open = open

        def sahte_open(yol, *a, **k):
            if str(yol).endswith("a.tex"):
                raise PermissionError("izin yok")
            return gercek_open(yol, *a, **k)

        monkeypatch.setattr("builtins.open", sahte_open)
        bulgular, _ = search_project(kok, "hedef")
        assert len(bulgular) == 1 and bulgular[0].path.endswith("b.tex")

    def test_devasa_dosya_atlanir(self, tmp_path, monkeypatch):
        """8 MB üstü .tex kaynak değil, üretilmiş çıktıdır."""
        import core.project_search as ps
        kok = str(tmp_path)
        _yaz(kok, "buyuk.tex", "hedef\n")
        monkeypatch.setattr(ps, "_MAX_DOSYA_BAYT", 3)
        assert search_project(kok, "hedef")[0] == []


# --------------------------------------------------------------------------
# İşçi
# --------------------------------------------------------------------------

try:
    from PyQt6.QtWidgets import QApplication
    from gui.project_search_worker import ProjectSearchWorker
except ImportError:  # pragma: no cover
    ProjectSearchWorker = None


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _spin(app, kosul, timeout_ms=10000):
    t0 = time.monotonic()
    while not kosul():
        app.processEvents()
        if (time.monotonic() - t0) * 1000 > timeout_ms:
            return False
    return True


@pytest.mark.skipif(ProjectSearchWorker is None, reason="PyQt6 gerekli")
class TestIsci:
    """Tarama UI thread'inde koşmamalı: ölçüldü, WSL üzerinden 850–2250 ms."""

    def test_sonuc_damgali_gelir(self, qapp, proje):
        w = ProjectSearchWorker()
        w.start()
        gelen = []
        w.found.connect(lambda i, b, k: gelen.append((i, b, k)))
        try:
            w.search(7, proje, "benimKomut", False)
            assert _spin(qapp, lambda: bool(gelen))
            sid, bulgular, kesildi = gelen[0]
            assert sid == 7 and not kesildi
            assert all(isinstance(b, Bulgu) for b in bulgular)
        finally:
            w.stop()
            w.wait(6000)

    def test_hatali_kok_isciyi_dusurmez(self, qapp, tmp_path):
        w = ProjectSearchWorker()
        w.start()
        gelen = []
        w.found.connect(lambda i, b, k: gelen.append((i, b, k)))
        try:
            w.search(1, str(tmp_path / "yok"), "x", False)
            assert _spin(qapp, lambda: bool(gelen))
            assert gelen[0][1] == []
            # işçi ayakta: ikinci arama da sonuç vermeli
            _yaz(str(tmp_path), "a.tex", "hedef\n")
            w.search(2, str(tmp_path), "hedef", False)
            assert _spin(qapp, lambda: len(gelen) > 1)
            assert gelen[1][0] == 2 and len(gelen[1][1]) == 1
        finally:
            w.stop()
            w.wait(6000)


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------

@pytest.fixture
def panel(qapp):
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
    p = OutputPanel(theme=THEMES["dark"])
    yield p
    p.deleteLater()
    qapp.processEvents()


class TestPanel:

    def test_sonuclar_tiklanabilir_ve_konum_tasiyor(self, panel, proje):
        from PyQt6.QtCore import Qt
        bulgular, kesildi = search_project(proje, "benimKomut")
        panel.show_project_search(bulgular, kesildi, proje)
        assert panel._psearch_list.count() == len(bulgular)
        it = panel._psearch_list.item(0)
        yol, satir = it.data(Qt.ItemDataRole.UserRole)
        assert os.path.isabs(yol) and satir > 0

    def test_yol_koke_gore_gosteriliyor(self, panel, proje):
        bulgular, _ = search_project(proje, "benimKomut")
        panel.show_project_search(bulgular, False, proje)
        metinler = [panel._psearch_list.item(i).text()
                    for i in range(panel._psearch_list.count())]
        assert any(m.startswith("bolum/giris.tex:") for m in metinler), metinler
        assert not any(m.startswith(proje) for m in metinler)

    def test_tiklama_error_clicked_yayar(self, panel, proje, qapp):
        bulgular, _ = search_project(proje, "benimKomut")
        panel.show_project_search(bulgular, False, proje)
        yakalanan = []
        panel.error_clicked.connect(lambda p, ln: yakalanan.append((p, ln)))
        panel._psearch_list.itemClicked.emit(panel._psearch_list.item(0))
        qapp.processEvents()
        assert yakalanan and yakalanan[0][1] > 0

    def test_kirpma_kullaniciya_SOYLENIR(self, panel, proje):
        bulgular, _ = search_project(proje, "benimKomut", limit=2)
        panel.show_project_search(bulgular, True, proje)
        metin = panel._psearch_status.text()
        assert "2" in metin and metin != ""
        assert metin != panel._psearch_status.text().replace("2", "")

    def test_sonuc_yoksa_bulunamadi_yazar(self, panel, proje):
        panel.show_project_search([], False, proje)
        assert panel._psearch_list.count() == 0
        assert panel._psearch_status.text() != ""

    def test_enter_sinyali_sorgu_ve_bayrakla_cikiyor(self, panel):
        yakalanan = []
        panel.project_search_requested.connect(
            lambda q, cs: yakalanan.append((q, cs)))
        panel._psearch_input.setText("  hedef  ")
        panel._psearch_case.setChecked(True)     # toggled da aramayı tetikler
        panel._on_project_search_return()
        assert ("hedef", True) in yakalanan

    def test_bos_sorgu_arama_baslatmaz(self, panel):
        yakalanan = []
        panel.project_search_requested.connect(
            lambda q, cs: yakalanan.append(q))
        panel._psearch_input.setText("   ")
        panel._on_project_search_return()
        assert yakalanan == []

    def test_odak_sekmeyi_one_alir(self, panel):
        panel.focus_project_search("secili_metin")
        assert panel._tabs.currentIndex() == panel._psearch_tab_index
        assert panel._psearch_input.text() == "secili_metin"

    def test_clear_arama_sonuclarini_silmiyor(self, panel, proje):
        """Derleme çıktısı değil: yeni derleme sonuçları süpürmemeli."""
        bulgular, _ = search_project(proje, "benimKomut")
        panel.show_project_search(bulgular, False, proje)
        n = panel._psearch_list.count()
        panel.clear()
        assert panel._psearch_list.count() == n

    def test_tema_arama_sekmesini_de_boyuyor(self, panel):
        from gui.theme import THEMES
        panel.show_project_search(
            [Bulgu("/x/a.tex", 1, 0, "satır")], False, "/x")
        for ad in ("light", "dark"):
            panel.apply_theme(THEMES[ad])
            assert THEMES[ad]["bg_primary"] in panel._psearch_list.styleSheet()
            assert panel._psearch_input.styleSheet() != ""


# --------------------------------------------------------------------------
# Mixin (kök seçimi, bayat sonuç)
# --------------------------------------------------------------------------

class _AramaStub:
    def __init__(self, panel, kok):
        from tests.stub_main import StatusRecorder
        self._output_panel = panel
        self._file_tree = SimpleNamespace(_root=kok)
        self._status = StatusRecorder()
        self._psearch_id = 0
        self._psearch_root = ""
        self.istekler = []
        self._project_search_worker = SimpleNamespace(
            search=lambda *a: self.istekler.append(a))

    def _current_editor(self):
        return None


class TestMixin:

    def _stub(self, panel, kok):
        from gui.mixins.project_search_ops import ProjectSearchMixin

        class S(ProjectSearchMixin, _AramaStub):
            pass

        return S(panel, kok)

    def test_kok_dosya_agacindan_gelir(self, panel, proje):
        s = self._stub(panel, proje)
        s._on_project_search_requested("hedef", False)
        assert s.istekler == [(1, proje, "hedef", False)]

    def test_klasor_yoksa_uyarir_ve_arama_yapmaz(self, panel):
        s = self._stub(panel, "")
        s._on_project_search_requested("hedef", False)
        assert s.istekler == []
        assert s._status.currentMessage() != ""

    def test_bayat_sonuc_yenisini_ezmiyor(self, panel, proje):
        """Art arda Enter: eski taramanın geç dönen sonucu gösterilmemeli."""
        s = self._stub(panel, proje)
        s._on_project_search_requested("a", False)      # id 1
        s._on_project_search_requested("b", False)      # id 2
        s._on_project_search_done(1, [Bulgu("/x/a.tex", 9, 0, "bayat")], False)
        assert panel._psearch_list.count() == 0
        s._on_project_search_done(2, [Bulgu("/x/b.tex", 3, 0, "taze")], False)
        assert panel._psearch_list.count() == 1
        assert "taze" in panel._psearch_list.item(0).text()


# --------------------------------------------------------------------------
# Kablolama (main_window)
# --------------------------------------------------------------------------

class TestKablolama:
    """Parçalar tek tek doğru olsa da bağlanmazsa özellik yok demektir."""

    @staticmethod
    def _kaynak():
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "desktop", "gui", "main_window.py"),
                  encoding="utf-8") as f:
            return f.read()

    def test_mixin_MainWindow_a_karisimis(self):
        from gui.main_window import MainWindow
        from gui.mixins.project_search_ops import ProjectSearchMixin
        assert issubclass(MainWindow, ProjectSearchMixin)
        for ad in ("_init_project_search", "_project_search",
                   "_on_project_search_requested", "_on_project_search_done",
                   "_cleanup_project_search"):
            assert hasattr(MainWindow, ad), ad

    def test_kisayol_ve_menu_ayni_metoda_gidiyor(self):
        import re
        k = self._kaynak()
        assert re.search(
            r'QShortcut\(QKeySequence\("Ctrl\+Shift\+F"\)[^\n]*\n[^\n]*'
            r'ApplicationShortcut[^\n]*\n\s*\w+\.activated\.connect\(self\._project_search\)',
            k), "Ctrl+Shift+F kısayolu _project_search'e bağlı değil"
        assert re.search(
            r'_add_action\(edit_menu,\s*_\("&Projede Ara\.\.\."\),\s*self\._project_search',
            k), "Düzenle menüsünde Projede Ara yok (yalnız kısayolla erişilir kalır)"

    def test_panel_sinyali_bagli(self):
        k = self._kaynak()
        assert "project_search_requested.connect(" in k
        assert "_on_project_search_requested" in k

    def test_isci_aciliyor_ve_kapanista_durduruluyor(self):
        k = self._kaynak()
        assert "self._init_project_search()" in k, "işçi açılışta kurulmuyor"
        assert "self._cleanup_project_search()" in k, (
            "closeEvent işçiyi durdurmuyor — 'QThread destroyed while running'"
        )
