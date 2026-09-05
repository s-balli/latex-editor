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

    def test_tam_sinirda_KIRPILMADI_bildirilir(self, tmp_path):
        """Sınıra DEĞMEK kırpma değil: liste eksik değilse "kırpıldı" denmemeli.

        Eskiden `>= limit` ile sınıra değildiği anda kesiliyordu ve panel tam
        listeye "ilk 5 sonuç (kırpıldı)" yazıyordu (ölçüldü 2026-09-05).
        Sessiz kırpma nasıl yanıltıyorsa, OLMAYAN kırpmayı bildirmek de
        kullanıcıyı listeyi eksik sanıp sorguyu boşuna daraltmaya itiyor.
        """
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 5)
        bulgular, kesildi = search_project(kok, "x", limit=5)
        assert kesildi is False
        assert len(bulgular) == 5

    def test_sinirin_BIR_ustunde_kirpildi(self, tmp_path):
        """Sınır üçlüsünün üçüncüsü: limit+1 eşleşme kırpmadır.

        Bu olmadan kesme koşulunu bir fazlaya kaydıran bir hata (`> limit + 1`)
        diğer testlerin hepsinden geçiyor.
        """
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 6)
        bulgular, kesildi = search_project(kok, "x", limit=5)
        assert kesildi is True
        assert len(bulgular) == 5

    def test_tam_sinir_dosya_sinirina_denk_gelirse(self, tmp_path):
        """Sınır iki dosyanın tam arasına düşse de kırpma yok."""
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 3)
        _yaz(kok, "b.tex", "x\n" * 3)
        bulgular, kesildi = search_project(kok, "x", limit=6)
        assert kesildi is False
        assert len(bulgular) == 6
        assert len({b.path for b in bulgular}) == 2

    def test_tam_sinir_satir_ortasina_denk_gelirse(self, tmp_path):
        """Tek satırda çok eşleşme varken de sınır doğru yorumlanmalı."""
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "aa aa aa\n")          # "a" -> 6 eşleşme
        bulgular, kesildi = search_project(kok, "a", limit=6)
        assert kesildi is False and len(bulgular) == 6
        bulgular, kesildi = search_project(kok, "a", limit=4)
        assert kesildi is True and len(bulgular) == 4

    def test_tek_eslesme_limit_bir(self, tmp_path):
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "hedef\n")
        bulgular, kesildi = search_project(kok, "hedef", limit=1)
        assert kesildi is False and len(bulgular) == 1

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

    def test_tam_sinirda_panel_kirpma_DEMIYOR(self, panel, tmp_path):
        """Uçtan uca: tam sınır kadar eşleşmede kullanıcı kırpma uyarısı görmez.

        Metin çeviriden geçtiği için sabit dizeye bakılmıyor; aynı listenin
        kırpılmış hâliyle ÜRETTİĞİ metin farklı olmalı.
        """
        kok = str(tmp_path)
        _yaz(kok, "a.tex", "x\n" * 5)
        bulgular, kesildi = search_project(kok, "x", limit=5)
        assert kesildi is False, "ön koşul: liste tam olmalı"

        panel.show_project_search(bulgular, kesildi, kok)
        tam = panel._psearch_status.text()
        panel.show_project_search(bulgular, True, kok)
        kirpik = panel._psearch_status.text()
        assert tam != kirpik, (
            "tam liste kırpılmış listeyle aynı metni gösteriyor: %r" % tam)

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

    def test_kisayol_TEK_yerden_kayitli(self):
        """Ctrl+Shift+F yalnız menü QAction'ında olmalı, ayrıca QShortcut YOK.

        İlk sürümde ikisi birden vardı ve Qt "Ambiguous shortcut overload"
        deyip HİÇBİRİNİ tetiklemedi — kullanıcı "tepki vermedi" diye bildirdi.
        `app_shortcut=True` şart: odak QScintilla'dayken de çalışması gerekiyor
        (asıl kullanım anı editörde yazarken).
        """
        import re
        k = self._kaynak()
        assert re.search(
            r'_add_action\(edit_menu,\s*_\("Klasörde &Ara\.\.\."\),\s*self\._project_search,\s*\n?\s*'
            r'"Ctrl\+Shift\+F",\s*app_shortcut=True\)',
            k), "menüdeki Klasörde Ara app_shortcut'lı Ctrl+Shift+F ile bağlı değil"
        assert 'QShortcut(QKeySequence("Ctrl+Shift+F")' not in k, (
            "Ctrl+Shift+F hem QAction hem QShortcut — Qt ikisini de tetiklemez"
        )

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


# --------------------------------------------------------------------------
# "bulunamadı" AÇIKLANABİLİR olmalı — kök görünür, kök dışı söylenir
# --------------------------------------------------------------------------

class TestKokGorunurlugu:
    """Kullanıcı bildirdi: big.tex'te 1800 kez geçen "paragraf" bulunamadı.

    Arama doğru çalışıyordu — kök QSettings'ten geri yüklenen ESKİ bir
    klasörde (template15, 2 dosya) kalmıştı ve açık dosya oranın dışındaydı.
    Panel yalnız "bulunamadı" diyordu; nerede aradığını söylemiyordu.
    """

    def test_kok_etiketi_klasor_adini_gosteriyor(self, panel, proje):
        panel.set_project_search_root(proje)
        assert os.path.basename(proje) in panel._psearch_kok.text()
        assert proje in panel._psearch_kok.toolTip()

    def test_kok_yokken_de_bir_sey_yaziyor(self, panel):
        panel.set_project_search_root("")
        assert panel._psearch_kok.text().strip() not in ("", "⌂")

    def test_sonuc_gosterirken_kok_da_guncelleniyor(self, panel, proje):
        panel.set_project_search_root("/eski/kok")
        panel.show_project_search([], False, proje)
        assert os.path.basename(proje) in panel._psearch_kok.text()

    def test_kok_disi_uyarisi_bulunamadiya_ekleniyor(self, panel, proje):
        panel.show_project_search([], False, proje, "açık dosya dışarıda")
        metin = panel._psearch_status.text()
        assert "açık dosya dışarıda" in metin
        # Sonuç VARKEN uyarı gösterilmez
        panel.show_project_search([Bulgu("/x/a.tex", 1, 0, "s")], False, proje, "x")
        assert "x" not in panel._psearch_status.text()


class TestKokDisiTespiti:

    def _stub(self, panel, kok, dosya_yolu):
        from gui.mixins.project_search_ops import ProjectSearchMixin

        class S(ProjectSearchMixin, _AramaStub):
            def _current_editor(s):
                return SimpleNamespace(file_path=dosya_yolu,
                                       hasSelectedText=lambda: False)

        return S(panel, kok)

    def test_dosya_kok_icindeyse_uyari_yok(self, panel, proje):
        s = self._stub(panel, proje, os.path.join(proje, "main.tex"))
        assert s._kok_disinda_mi(proje) == ""

    def test_dosya_kok_disindaysa_uyari_var(self, panel, tmp_path):
        # İki AYRI klasör: kök birinde, açık dosya diğerinde.
        kok = str(tmp_path / "kok")
        os.makedirs(kok)
        _yaz(kok, "icerideki.tex", "x\n")
        disarida = str(tmp_path / "baska" / "disarida.tex")
        os.makedirs(os.path.dirname(disarida))
        _yaz(os.path.dirname(disarida), "disarida.tex", "x\n")

        s = self._stub(panel, kok, disarida)
        uyari = s._kok_disinda_mi(kok)
        assert uyari and "disarida.tex" in uyari

    def test_dosya_yokken_uyari_yok(self, panel, proje):
        s = self._stub(panel, proje, "")
        assert s._kok_disinda_mi(proje) == ""

    def test_kullanicinin_yasadigi_durum(self, panel, tmp_path):
        """Kök template15'te, açık dosya tmp/bigpdf/big.tex — tam o vaka."""
        kok = str(tmp_path / "template15")
        os.makedirs(kok)
        _yaz(kok, "sablon.tex", "hicbir sey\n")
        acik = str(tmp_path / "tmp" / "bigpdf" / "big.tex")
        os.makedirs(os.path.dirname(acik))
        _yaz(os.path.dirname(acik), "big.tex", "Bu paragraf 1. bolumun\n")

        s = self._stub(panel, kok, acik)
        s._on_project_search_requested("paragraf", False)
        assert s.istekler == [(1, kok, "paragraf", False)]
        # İşçi 0 döndürür (o kökte gerçekten yok); panel bunu AÇIKLAMALI
        s._on_project_search_done(1, [], False)
        durum = panel._psearch_status.text()
        assert "big.tex" in durum, durum
        assert "template15" in panel._psearch_kok.text()


def test_harf_duyarlilik_etiketi_anlasilir(panel):
    """Etiket "Aa" idi; kullanıcı ne olduğunu anlamadığını bildirdi.

    VS Code'da o simge bir düğmenin üstünde ve yanında ayrıca açıklama var;
    tek başına onay kutusu etiketi olarak hiçbir şey anlatmıyor.
    """
    etiket = panel._psearch_case.text()
    assert etiket != "Aa"
    assert len(etiket) >= 5, etiket          # simge değil, sözcük
    assert panel._psearch_case.toolTip().strip(), "ipucu boş"


# --------------------------------------------------------------------------
# Klasör değişince sonuçlar bayat — atılmalı
# --------------------------------------------------------------------------

class TestKokDegisince:
    """Kullanıcı bildirdi: klasör değiştirilince arama sekmesi ESKİ sonuçları
    göstermeye devam ediyordu. Bunlar başka bir kökün dosyaları; tıklanınca
    kullanıcıyı projenin DIŞINA götürüyorlar.
    """

    def test_file_tree_kok_degisince_sinyal_veriyor(self, qapp, tmp_path):
        from gui.file_tree import FileTree
        from gui.theme import THEMES
        a = str(tmp_path / "a"); os.makedirs(a)
        b = str(tmp_path / "b"); os.makedirs(b)
        t = FileTree(theme=THEMES["dark"])
        try:
            gelen = []
            t.root_changed.connect(gelen.append)
            t.set_root(a)
            t.set_root(b)
            assert [os.path.normpath(x) for x in gelen] == \
                [os.path.normpath(a), os.path.normpath(b)]
            # AYNI kök yeniden verilince sinyal YOK (ağaç da yeniden taranmıyor)
            t.set_root(b)
            assert len(gelen) == 2
        finally:
            t.deleteLater()
            qapp.processEvents()

    def test_panel_temizleniyor_ama_SORGU_kaliyor(self, panel, proje):
        bulgular, _ = search_project(proje, "benimKomut")
        panel.show_project_search(bulgular, False, proje)
        panel._psearch_input.setText("benimKomut")
        assert panel._psearch_list.count() > 0

        panel.clear_project_search("/yeni/kok")
        assert panel._psearch_list.count() == 0
        assert panel._psearch_status.text() == ""
        assert "kok" in panel._psearch_kok.text()          # yeni kök yazıldı
        assert panel._psearch_input.text() == "benimKomut"  # sorgu KORUNDU

    def test_mixin_bayat_sonucu_engelliyor(self, panel, proje):
        """Kök değişince uçuştaki tarama da geçersiz olmalı."""
        from gui.mixins.project_search_ops import ProjectSearchMixin

        class S(ProjectSearchMixin, _AramaStub):
            pass

        s = S(panel, proje)
        s._on_project_search_requested("benimKomut", False)   # id 1
        s._on_project_root_changed("/baska/kok")              # id 2 olur
        # Eski kökün geç dönen sonucu panele DÜŞMEMELİ
        s._on_project_search_done(1, [Bulgu("/eski/a.tex", 1, 0, "bayat")], False)
        assert panel._psearch_list.count() == 0
        assert "kok" in panel._psearch_kok.text()

    def test_kok_degisince_kaynakca_da_temizleniyor(self, panel, proje):
        """Kaynakça listesi de köke bağlı: eski girdiler proje dışına götürür."""
        from gui.mixins.project_search_ops import ProjectSearchMixin

        class S(ProjectSearchMixin, _AramaStub):
            pass

        panel.show_bibliography(
            [(("k", "article", "A", "2020", "T"), "/eski/refs.bib", 1)])
        assert panel._bib_table.rowCount() == 1

        S(panel, proje)._on_project_root_changed("/baska/kok")
        assert panel._bib_table.rowCount() == 0

    def test_kablolama_main_window_da_bagli(self):
        kok = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(kok, "desktop", "gui", "main_window.py"),
                  encoding="utf-8") as f:
            k = f.read()
        assert "root_changed.connect(self._on_project_root_changed)" in k


class TestKokDisiHarfYazimi:
    """Windows'ta harf yazımı uyarıyı bozmamalı.

    Dosya sistemi harf DUYARSIZ ama `os.path.commonpath` karşılaştırması
    duyarlı. Kök `...\\TEZ`, açık dosya `...\\tez\\a.tex` iken fonksiyon
    "açık dosya bu klasörün dışında" diyordu; oysa dosya tam da o klasörün
    içinde. Bu satırın var olma sebebi tam tersiydi: yanıltıcı bir
    "bulunamadı" mesajını AÇIKLAMAK.

    POSIX'te farklı yazım FARKLI dosyadır, yani harf vakaları orada anlamsız
    ve atlanıyor. `normcase` POSIX'te kimlik işlevi olduğu için düzeltme
    orada hiçbir şeyi değiştirmiyor; aşağıdaki platformdan bağımsız testler
    bunu da sabitliyor.
    """

    _WIN = os.name == "nt"

    def _stub(self, panel, kok, dosya_yolu):
        from gui.mixins.project_search_ops import ProjectSearchMixin

        class S(ProjectSearchMixin, _AramaStub):
            def _current_editor(s):
                return SimpleNamespace(file_path=dosya_yolu,
                                       hasSelectedText=lambda: False)

        return S(panel, kok)

    @pytest.mark.skipif(os.name != "nt",
                        reason="POSIX'te farklı yazım farklı dosyadır")
    @pytest.mark.parametrize("kok_bicim,dosya_bicim", [
        (str.upper, str),          # kök BÜYÜK
        (str.lower, str),          # kök küçük
        (str, str.upper),          # dosya BÜYÜK
        (str.lower, str.upper),    # ikisi de ayrışıyor
    ])
    def test_harf_ayrisinca_da_uyari_yok(self, panel, tmp_path,
                                         kok_bicim, dosya_bicim):
        kok = str(tmp_path / "Tez")
        os.makedirs(os.path.join(kok, "bolumler"))
        _yaz(os.path.join(kok, "bolumler"), "a.tex", "x\n")
        dosya = os.path.join(kok, "bolumler", "a.tex")

        s = self._stub(panel, kok_bicim(kok), dosya_bicim(dosya))
        assert s._kok_disinda_mi(kok_bicim(kok)) == ""

    @pytest.mark.skipif(os.name != "nt",
                        reason="POSIX'te farklı yazım farklı dosyadır")
    def test_harf_ayrissa_bile_GERCEKTEN_disarisi_uyari_veriyor(self, panel,
                                                                tmp_path):
        """Karşı yön: normcase karşılaştırmayı gevşetmemeli."""
        kok = str(tmp_path / "Tez")
        os.makedirs(kok)
        disarida = str(tmp_path / "Baska" / "x.tex")
        os.makedirs(os.path.dirname(disarida))
        _yaz(os.path.dirname(disarida), "x.tex", "x\n")

        s = self._stub(panel, kok, disarida)
        uyari = s._kok_disinda_mi(kok.upper())
        assert uyari and "x.tex" in uyari

    # --- platformdan bağımsız: düzeltme bunları bozmamalı

    def test_kardes_klasor_hala_disarisi_sayiliyor(self, panel, tmp_path):
        """`kok` + ek harf: ön ek benzerliği "içinde" sanılmamalı.

        `commonpath` yol BİLEŞENİ bazlı olduğu için doğru davranıyor; test
        bunu sabitliyor, çünkü elle dize karşılaştırmasına dönülürse sessizce
        bozulur.
        """
        kok = str(tmp_path / "tez")
        os.makedirs(kok)
        kardes = str(tmp_path / "tezler" / "a.tex")
        os.makedirs(os.path.dirname(kardes))
        _yaz(os.path.dirname(kardes), "a.tex", "x\n")

        s = self._stub(panel, kok, kardes)
        assert s._kok_disinda_mi(kok)

    def test_mesajda_dosya_adi_HAM_yazimiyla(self, panel, tmp_path):
        """normcase yalnız karşılaştırma için; kullanıcı gerçek adı görmeli."""
        kok = str(tmp_path / "kok")
        os.makedirs(kok)
        disarida = str(tmp_path / "baska" / "BuyukAd.TEX")
        os.makedirs(os.path.dirname(disarida))
        _yaz(os.path.dirname(disarida), "BuyukAd.TEX", "x\n")

        s = self._stub(panel, kok, disarida)
        assert "BuyukAd.TEX" in s._kok_disinda_mi(kok)

    def test_dosya_kokun_kendi_dizinindeyse_uyari_yok(self, panel, tmp_path):
        kok = str(tmp_path / "kok")
        os.makedirs(kok)
        _yaz(kok, "a.tex", "x\n")
        s = self._stub(panel, kok, os.path.join(kok, "a.tex"))
        assert s._kok_disinda_mi(kok) == ""
