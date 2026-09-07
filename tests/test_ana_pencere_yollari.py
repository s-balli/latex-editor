# -*- coding: utf-8 -*-
"""Ana pencere yolları: tek kaynak kuralı ve diyaloglara giren dış değerler.

İkisi de 2026-09-06 turunda kapatılan GİZLİ kırılganlıklar. Hiçbiri o gün
canlı hata üretmiyordu; testler, engelledikleri kırılmayı tutuyor.
"""

import os
import pathlib
import re
import types

import pytest

pytest.importorskip("PyQt6")


def _norm(yol: str) -> str:
    return os.path.normcase(os.path.normpath(yol or ""))


@pytest.fixture(scope="session")
def qapp():
    """QApplication REFERANSI TUTULMALI (bkz. test_menu_actions.py aynı ders)."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# --- Açılabilir uzantı kümesi TEK KAYNAK olmalı ---
#
# `_OPENABLE_EXT` sabitinin yorumu "sürükle-bırakla AYNI küme" diyordu ama
# `_handle_dropped_urls` sabiti kullanmıyor, kendi düz demetini taşıyordu.
# İkisi aynıydı, yani hata yoktu; kırılma bir sonraki uzantı eklendiğinde
# geliyordu. Ölçüldü (2026-09-06): sabite `.ltx` eklendiğinde "Birlikte Aç"
# açıyor, sürükle-bırak görmezden geliyordu.


@pytest.fixture
def pencere(ana_pencere, tmp_path):
    """Dosya açma/görsel ekleme çağrılarını yakalayan gerçek MainWindow."""
    from PyQt6.QtCore import QUrl

    w = ana_pencere()
    acilan, gorsel = [], []
    w._open_file_in_editor = lambda yol, *a, **k: acilan.append(yol)
    w._insert_image = lambda yol: gorsel.append(yol)

    def _dosya(ad):
        y = tmp_path / ad
        y.write_text("x\n", encoding="utf-8")
        return str(y)

    def _iki_yol(yol):
        """(Birlikte Aç açtı mı, sürükle-bırak açtı mı)"""
        acilan.clear()
        w.open_from_other_instance(yol)
        birlikte = bool(acilan)
        acilan.clear()
        w._handle_dropped_urls([QUrl.fromLocalFile(yol)])
        return birlikte, bool(acilan)

    w.dosya = _dosya
    w.iki_yol = _iki_yol
    w.gorsel = gorsel
    return w


def test_uzanti_kumesi_TEK_KAYNAK(pencere, monkeypatch):
    """Sabite eklenen uzantıyı İKİ yol da tanımalı."""
    from gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_OPENABLE_EXT",
                        MainWindow._OPENABLE_EXT + (".ltx",))
    birlikte, surukle = pencere.iki_yol(pencere.dosya("belge.ltx"))
    assert birlikte, "ön koşul: 'Birlikte Aç' yeni uzantıyı açmalı"
    assert surukle, (
        "sürükle-bırak sabiti kullanmıyor: uzantı kümesi tek kaynak değil")


def test_sabite_eklenmeyen_uzanti_IKI_YOLDA_da_reddediliyor(pencere):
    """AŞIRI DÜZELTME KAPISI: kapı 'her şeyi kabul et'e dönmemeli."""
    birlikte, surukle = pencere.iki_yol(pencere.dosya("belge.ltx"))
    assert not birlikte and not surukle
    birlikte, surukle = pencere.iki_yol(pencere.dosya("baska.txt"))
    assert not birlikte and not surukle


def test_desteklenen_uzanti_IKI_YOLDA_da_aciliyor(pencere):
    birlikte, surukle = pencere.iki_yol(pencere.dosya("normal.tex"))
    assert birlikte and surukle


def test_gorsel_surukle_birak_yolu_bozulmadi(pencere):
    """Görsel demeti ayrı ve tek kullanımlık; değişiklik ona dokunmamalı."""
    from PyQt6.QtCore import QUrl

    pencere.gorsel.clear()
    pencere._handle_dropped_urls([QUrl.fromLocalFile(pencere.dosya("r.png"))])
    assert pencere.gorsel


# --- Güncelleme diyaloğuna giren dış değerler KAÇIŞLI olmalı ---
#
# `tag`, `url` ve `notes` üçü de GitHub Releases yanıtından geliyor. Ders
# `notes` için öğrenilmiş ve gerekçesi koda yazılmıştı, ama aynı f-string'deki
# `tag` ile `url` dışarıda kalmıştı. Ölçüldü (2026-09-06): `<...>` içeren bir
# etiket yutuluyor, tek tırnak içeren bir url `href` özniteliğini erken
# kapatıp bağlantı hedefini kırpıyordu.

TEMEL = {"tag": "v1.0.21", "url": "https://example.org/r", "notes": "not"}


@pytest.fixture
def guncelleme_diyalogu(qapp, monkeypatch):
    """`_on_update_found`u koştur; (HTML, tarayıcıya giden ham url) döndür."""
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QMessageBox, QWidget
    from gui.main_window import MainWindow
    from gui.theme import THEMES

    class _Vekil(QWidget):
        def __init__(self):
            super().__init__()
            self._theme_mgr = types.SimpleNamespace(theme=THEMES["dark"])
            self._status = types.SimpleNamespace(
                showMessage=lambda *a, **k: None)

    def _calistir(info, tikla=False):
        yak = {}
        dugmeler = []
        asil_add = QMessageBox.addButton

        def _add(self, *a, **k):
            b = asil_add(self, *a, **k)
            dugmeler.append(b)
            return b

        monkeypatch.setattr(QMessageBox, "setText",
                            lambda self, h: yak.setdefault("h", h))
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        monkeypatch.setattr(QMessageBox, "addButton", _add)
        monkeypatch.setattr(
            QMessageBox, "clickedButton",
            lambda self: (dugmeler[0] if tikla and dugmeler else None))
        monkeypatch.setattr(
            QDesktopServices, "openUrl",
            staticmethod(lambda u: yak.setdefault("url", u.toString())))

        MainWindow._on_update_found(_Vekil(), info)
        assert len(yak.get("h", "")) > 100, "kapı boşa düşmesin, gövde yok"
        return yak.get("h", ""), yak.get("url")

    return _calistir


def _gorunen(html):
    """Qt'ye çizdirip kullanıcının GÖRDÜĞÜ düz metni al."""
    from PyQt6.QtWidgets import QTextBrowser

    tb = QTextBrowser()
    tb.setHtml(html)
    metin = tb.toPlainText()
    tb.deleteLater()
    return metin


@pytest.mark.parametrize("alan,deger", [
    ("tag", "v1.0.21-<rc1>"),
    ("notes", "onceki <deneme> surumu duzeltildi"),
])
def test_diyalogda_acili_parantez_yutulmuyor(guncelleme_diyalogu, alan, deger):
    html, _ = guncelleme_diyalogu(dict(TEMEL, **{alan: deger}))
    assert deger in _gorunen(html), f"{alan} alanı yutuldu"


def test_url_oznitelikte_erken_KAPATMIYOR(guncelleme_diyalogu):
    """Öznitelik tek tırnakla açılıyor; url'deki tek tırnak onu kapatırdı."""
    import html as _html

    zor = "https://example.org/r?a='b'&c=<d>"
    html, _ = guncelleme_diyalogu(dict(TEMEL, url=zor))
    m = re.search(r"<a href='([^']*)'", html)
    assert m, "bağlantı bulunamadı"
    # Doğru gösterim kaçışlı olabilir; varlıkları çözüp KARŞILAŞTIR.
    assert _html.unescape(m.group(1)) == zor, (
        "bağlantı hedefi kırpıldı: " + m.group(1))


def test_tarayiciya_giden_url_HAM_kaliyor(guncelleme_diyalogu):
    """AŞIRI DÜZELTME KAPISI: kaçış yalnız işaretlemeye giren kopyada.

    `QDesktopServices.openUrl` ham url'yi almalı; HTML varlıkları oraya
    sızarsa kullanıcı bozuk bir adrese gider.
    """
    _html_govde, ham = guncelleme_diyalogu(dict(TEMEL), tikla=True)
    assert ham == TEMEL["url"]

    zor = "https://example.org/r?a='b'&c=<d>"
    _h, ham2 = guncelleme_diyalogu(dict(TEMEL, url=zor), tikla=True)
    # QUrl kendi normalizasyonunu yapıyor (`<` -> `%3C`), bu kaçışla ilgisiz.
    assert ham2 and "&#x27;" not in ham2 and "&amp;" not in ham2
    assert "?a='b'&c=" in ham2


def test_olagan_degerler_bozulmadan_gorunuyor(guncelleme_diyalogu):
    html, _ = guncelleme_diyalogu(dict(TEMEL))
    duz = _gorunen(html)
    assert "v1.0.21" in duz and "not" in duz


# --- Uzanti kumesi BES DOSYADA degil, TEK yerde tanimli olmali ---
#
# Yukaridaki test `_OPENABLE_EXT` ile surukle-birak yolunu baglamisti; ama
# ayni dortlu ALTI yerde yaziliydi (file_tree x2, main_window x2, quick_open,
# project_search). Altisi da ayniydi, yani canli hata yoktu; kirilma bir
# sonraki uzanti eklendiginde geliyordu. Olculdu 2026-09-06: kopyalardan
# BIRINE `.ltx` eklemek uc yuzeyi ayristiriyor ("Birlikte Ac" aciyor, hizli
# ac listelemiyor, projede ara aramiyor, agac duzenlenebilir saymiyor).
# Kopyalardan biri (file_tree._EXTENSIONS) zaten OLUYDU.
#
# Asagidaki KAYNAK KAPISI asil is goreni: yeni bir kopya yazilirsa kirilir.
# Kimlik kapilari ise mevcut yuzeylerin ayni nesneden turedigini tutar.
# (Calisma aninda sabiti yeniden baglayip yayilmayi sinamak ANLAMSIZ:
# tuketiciler degeri import aninda bagliyor ve gercek degisiklik kaynagi
# duzenlemek.)

_UZANTI_DESENI = re.compile(
    r"""["']\.tex["']\s*,\s*["']\.cls["']\s*,\s*["']\.sty["']\s*,\s*["']\.bib["']""")
_UZANTI_HARIC = ("tests/", "web/", "desktop/.venv-build/", "tmp/",
                 ".temp_files/")


def _uzanti_demeti_gecisleri():
    """Demetin birinci-taraf kaynakta gectigi yerler (yorumlar haric)."""
    import subprocess
    kok = pathlib.Path(__file__).resolve().parents[1]
    r = subprocess.run(["git", "ls-files", "*.py"], cwd=kok,
                       capture_output=True, text=True, encoding="utf-8")
    out = []
    for rel in r.stdout.split():
        if rel.startswith(_UZANTI_HARIC):
            continue
        p = kok / rel
        if not p.is_file():
            continue
        for i, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if satir.lstrip().startswith("#"):
                continue           # yorumdaki anlatim kopya degil
            if _UZANTI_DESENI.search(satir):
                out.append("%s:%d" % (rel, i))
    return out


def test_uzanti_demeti_kaynakta_TEK_KEZ_yazili():
    """Kirilirsa: kume yeniden kopyalanmis demektir.

    Asil kapi bu: kimlik testleri var olan yuzeyleri tutar, bu test YENI
    bir kopyanin eklenmesini engeller.
    """
    gecisler = _uzanti_demeti_gecisleri()
    assert len(gecisler) == 1, "uzanti demeti birden fazla yerde: %s" % gecisler
    assert gecisler[0].startswith("core/fs_ops.py"), gecisler


def test_uzanti_kapisi_BOS_KOSMUYOR():
    """Desen gercekten bir sey yakaliyor mu (regex bozulursa test yesil kalir)."""
    assert _UZANTI_DESENI.search('X = (".tex", ".cls", ".sty", ".bib")')
    assert _UZANTI_DESENI.search("X = {'.tex', '.cls', '.sty', '.bib'}")
    assert not _UZANTI_DESENI.search('X = (".tex", ".bib")')


def test_her_yuzey_AYNI_nesneden_turuyor(qapp):
    """Klasor agaci, hizli ac, projede ara ve 'Birlikte Ac' tek kaynakta."""
    from core.fs_ops import KAYNAK_UZANTILARI
    import core.project_search as ps
    import gui.quick_open as qo
    import gui.file_tree as ft
    from gui.main_window import MainWindow

    assert ps.KAYNAK_UZANTILARI is KAYNAK_UZANTILARI
    assert qo._EXT_FILES is KAYNAK_UZANTILARI
    assert MainWindow._OPENABLE_EXT is KAYNAK_UZANTILARI
    assert set(ft._EDITABLE) == set(KAYNAK_UZANTILARI)
    # `iter_project_files`in varsayilan argumani da ayni nesne olmali
    assert ps.iter_project_files.__defaults__[0] is KAYNAK_UZANTILARI


def test_OLU_sabit_geri_gelmedi(qapp):
    """`file_tree._EXTENSIONS` tanimliydi ve hicbir yerden okunmuyordu."""
    import gui.file_tree as ft
    assert not hasattr(ft, "_EXTENSIONS"), "ölü sabit geri gelmiş"


def test_kume_DEGISMEDI_ve_yuzeyler_calisiyor(qapp, tmp_path):
    """Asiri duzeltme kapisi: tek kaynaga almak davranisi degistirmemeli."""
    from core.fs_ops import KAYNAK_UZANTILARI
    import core.project_search as ps
    import gui.quick_open as qo
    import gui.file_tree as ft

    assert set(KAYNAK_UZANTILARI) == {".tex", ".cls", ".sty", ".bib"}
    # `str.endswith` demet ister; kume olsaydi quick_open patlardi
    assert isinstance(KAYNAK_UZANTILARI, tuple)
    assert ".tex" in ft._EDITABLE and ".png" not in ft._EDITABLE

    for ad in ("a.tex", "b.sty", "c.png"):
        (tmp_path / ad).write_text("x\n", encoding="utf-8")
    assert sorted(qo.collect_project_files(str(tmp_path))) == ["a.tex", "b.sty"]
    bulunan = [os.path.basename(p) for p in ps.iter_project_files(str(tmp_path))]
    assert sorted(bulunan) == ["a.tex", "b.sty"]


# ==========================================================================
# Disaridan gelen yol: ILK ACILIS ile IKINCI ORNEK ayni cevabi vermeli
#
# Ayni soru iki yerde ayri yazilmisti ve ayrismisti. OLCULDU (2026-09-06),
# ayni `.png` dosyasiyla:
#
#     ilk acilis (komut satiri) -> durum cubugu "Hazir", oturumdan kalan
#                                  sekme acik, hicbir aciklama YOK
#     ikinci ornek              -> "Bu dosya turu acilamiyor: resim.png"
#
# Kullanici .png'ye "Birlikte Ac" deyip alakasiz bir belge goruyordu. Kural
# artik `MainWindow._dis_yolu_ac`ta; ikinci ornek de oradan geciyor.
# ==========================================================================

@pytest.fixture
def iki_giris(ana_pencere, tmp_path):
    """Ayni yolu IKI giristen de gecirip (mesaj, acildi_mi) doner."""
    def _dosya(ad, olustur=True):
        y = tmp_path / ad
        if olustur:
            y.write_text("x\n", encoding="utf-8")
        return str(y)

    def _ilk_acilis(yol):
        w = ana_pencere(open_file=yol)
        acildi = any((e.file_path or "") == yol
                     for e in [w._editor_tabs.widget(i)
                               for i in range(w._editor_tabs.count())])
        return w._status.currentMessage(), acildi, w

    def _ikinci_ornek(yol):
        w = ana_pencere()
        acilan = []
        w._open_file_in_editor = lambda y, *a, **k: acilan.append(y)
        w.open_from_other_instance(yol)
        return w._status.currentMessage(), bool(acilan), w

    return _dosya, _ilk_acilis, _ikinci_ornek


def test_DESTEKLENMEYEN_tur_iki_giriste_de_AYNI_mesaj(iki_giris):
    dosya, ilk, ikinci = iki_giris
    yol = dosya("resim.png")
    m1, acildi1, _w1 = ilk(yol)
    m2, acildi2, _w2 = ikinci(yol)
    assert not acildi1 and not acildi2
    assert m1 == m2 != "", (m1, m2)
    assert "resim.png" in m1, m1


def test_OLMAYAN_dosya_iki_giriste_de_AYNI_mesaj(iki_giris):
    dosya, ilk, ikinci = iki_giris
    yol = dosya("yok.tex", olustur=False)
    m1, acildi1, _w1 = ilk(yol)
    m2, acildi2, _w2 = ikinci(yol)
    assert not acildi1 and not acildi2
    assert m1 == m2 != "", (m1, m2)
    assert "yok.tex" in m1, m1


def test_ILK_ACILIS_desteklenmeyen_turde_SESSIZ_KALMIYOR(iki_giris):
    """Kusurun kendisi: eskiden burada hicbir sey soylenmiyordu."""
    dosya, ilk, _ikinci = iki_giris
    mesaj, acildi, _w = ilk(dosya("resim.png"))
    assert not acildi
    assert "resim.png" in mesaj, mesaj


def test_DESTEKLENEN_dosya_ilk_aciliste_ACILIYOR_ve_hata_YOK(iki_giris):
    """Asiri duzeltme kapisi: gecerli dosya yine acilmali, uyari cikmamali."""
    dosya, ilk, _ikinci = iki_giris
    yol = dosya("belge.tex")
    mesaj, acildi, w = ilk(yol)
    assert acildi, "gecerli .tex acilmadi"
    assert "acilamiyor" not in mesaj.lower(), mesaj
    assert _norm(w._file_tree._root) == _norm(os.path.dirname(yol))


def test_BOS_yol_hicbir_sey_soylemiyor(ana_pencere):
    """Uygulama dosyasiz da aciliyor; o normal hal, uyari uretmemeli."""
    w = ana_pencere(open_file="")
    assert "bulunamadı" not in w._status.currentMessage()
    assert "açılamıyor" not in w._status.currentMessage()


def test_IKI_giris_de_TEK_metottan_geciyor():
    """Kirilirsa kural yine iki yerde yazili demektir."""
    import inspect
    from gui.main_window import MainWindow

    for metot in (MainWindow.__init__, MainWindow.open_from_other_instance):
        assert "_dis_yolu_ac" in inspect.getsource(metot), metot.__name__


# =====================================================================
# `_goto_line` YANLIS BELGEDE imleci oynatiyordu (olculdu 2026-09-07)
#
# Imlec `_current_editor()`e konuyordu. Dosya ne acik ne diskteyse iki dal
# da atlaniyor ama alttaki blok yine kosuyor: OLCULDU, A ve B acikken
# kullanici A'da ve silinmis bir dosyanin 30. satirina gitme istegi
# `acik_a.tex`in imlecini 30. satira atliyor; hicbir sey acilmiyor, mesaj
# da yok.
#
# Ulasilabilir yol siradan: derleme hatasina ya da yazim bulgusuna tiklamak
# (`output_panel.error_clicked`), SyncTeX ters aramasi, tanima git. Dosya
# derlemeden sonra silinmis/tasinmis ya da synctex kaydindaki yol
# cozulemiyor olabilir.
# =====================================================================


class _SatirStub:
    """`_goto_line`i kosturmak icin en az iskelet."""

    def __init__(self, editorler):
        from PyQt6.QtWidgets import QTabWidget
        from gui.main_window import MainWindow
        self._goto_line = types.MethodType(MainWindow._goto_line, self)
        self._editor_tabs = QTabWidget()
        for ed in editorler:
            self._editor_tabs.addTab(ed, os.path.basename(ed.file_path))
        self.acilanlar = []
        self.mesajlar = []
        self._status = types.SimpleNamespace(
            showMessage=lambda m, t=0: self.mesajlar.append(m),
            clearMessage=lambda: None)

    def _editor_by_path(self, yol):
        for i in range(self._editor_tabs.count()):
            ed = self._editor_tabs.widget(i)
            if ed.file_path and _norm(ed.file_path) == _norm(yol):
                return ed
        return None

    def _current_editor(self):
        return self._editor_tabs.currentWidget()

    def _open_file_in_editor(self, yol, add_recent=True):
        self.acilanlar.append(yol)


def _iki_editor(tmp_path):
    from gui.editor import EditorWidget
    yollar = []
    editorler = []
    for ad in ("acik_a.tex", "acik_b.tex"):
        p = tmp_path / ad
        p.write_text("".join("%s satir %d\n" % (ad, i + 1)
                             for i in range(40)), encoding="utf-8")
        ed = EditorWidget()
        assert ed.open_file(str(p))
        yollar.append(str(p))
        editorler.append(ed)
    return editorler, yollar


def test_satira_git_HEDEF_belgede_atliyor(qapp, tmp_path):
    (eda, edb), (yol_a, yol_b) = _iki_editor(tmp_path)
    stub = _SatirStub([eda, edb])
    stub._editor_tabs.setCurrentIndex(0)          # kullanici A'da
    eda.setCursorPosition(0, 0)
    edb.setCursorPosition(0, 0)

    stub._goto_line(yol_b, 12)

    assert stub._current_editor() is edb, "hedef sekmeye gecilmedi"
    assert edb.getCursorPosition() == (11, 0)
    assert eda.getCursorPosition() == (0, 0), "yanlis belgenin imleci oynadi"


def test_satira_git_ACILAMAYAN_dosyada_imlece_DOKUNMUYOR(qapp, tmp_path):
    """Kirilirsa: silinmis bir dosyanin hatasina tiklayan kullanici, acik
    baska bir belgede imlecin atladigini goruyor."""
    (eda, edb), _yollar = _iki_editor(tmp_path)
    stub = _SatirStub([eda, edb])
    stub._editor_tabs.setCurrentIndex(0)
    eda.setCursorPosition(0, 0)

    stub._goto_line(str(tmp_path / "silinmis.tex"), 30)

    assert eda.getCursorPosition() == (0, 0), "yanlis belgede atladi"
    assert stub.acilanlar == [], "var olmayan dosya acilmaya calisildi"
    assert stub.mesajlar, "kullaniciya sebep soylenmedi"
    assert "silinmis.tex" in stub.mesajlar[-1]


def test_satira_git_ACMA_BASARISIZ_olursa_da_dokunmuyor(qapp, tmp_path):
    """Dosya DISKTE var ama acilamiyor (ikili, kodlama): acmayi denedikten
    sonra yeniden sorulmadan imlec oynatmak yine yanlis belgeye giderdi."""
    (eda, edb), _yollar = _iki_editor(tmp_path)
    ikili = tmp_path / "ikili.tex"
    ikili.write_bytes(b"metin\x00metin")
    stub = _SatirStub([eda, edb])
    stub._editor_tabs.setCurrentIndex(0)
    eda.setCursorPosition(0, 0)

    stub._goto_line(str(ikili), 30)

    assert stub.acilanlar == [str(ikili)], "acma denenmedi"
    assert eda.getCursorPosition() == (0, 0), "acma basarisizken atladi"
    assert stub.mesajlar


def test_satira_git_BOS_yolda_CARI_belgede_atliyor(qapp, tmp_path):
    """Asiri duzeltme kapisi: bos yol bilincli, "cari belgede su satira git"
    demek (Ctrl+G ve anahat gezinmesi)."""
    (eda, edb), _yollar = _iki_editor(tmp_path)
    stub = _SatirStub([eda, edb])
    stub._editor_tabs.setCurrentIndex(0)
    eda.setCursorPosition(0, 0)

    stub._goto_line("", 7)

    assert eda.getCursorPosition() == (6, 0)
    assert stub.mesajlar == [], "bos yolda uyari cikti"


def test_satira_git_SATIR_SIFIRSA_imlece_dokunmuyor(qapp, tmp_path):
    """Panel bazi bulgular icin satir 0 tasiyor (konum bilinmiyor)."""
    (eda, edb), (yol_a, _b) = _iki_editor(tmp_path)
    stub = _SatirStub([eda, edb])
    stub._editor_tabs.setCurrentIndex(0)
    eda.setCursorPosition(3, 0)

    stub._goto_line(yol_a, 0)

    assert eda.getCursorPosition() == (3, 0)


# ==========================================================================
# UCUNCU giris: surukle birak
#
# Ayni yol uc yerden geliyor: komut satiri, ikinci ornek ve surukle birak.
# Ilk ikisi bir turda `_dis_yolu_ac`ta birlestirilmisti; ucuncusu o
# birlesmeye hic girmemis ve SESSIZ kalmisti. OLCULDU (2026-09-08), ayni
# pencerede:
#
#   veri.csv   birakildi -> hicbir sey olmadi, durum cubugu "Hazir"
#   rapor.docx birakildi -> hicbir sey olmadi, durum cubugu "Hazir"
#   bir klasor birakildi -> hicbir sey olmadi, durum cubugu "Hazir"
#   ayni veri.csv KOMUT SATIRINDAN -> "Bu dosya turu acilamiyor: veri.csv"
#
# Kullanici dosyayi pencereye surukluyor, hicbir sey olmuyor ve neden
# olmadigini soyleyen bir sey yok.
# ==========================================================================


@pytest.fixture
def birakan(ana_pencere, tmp_path):
    """Pencereye yol birakip (acilanlar, gorseller, mesaj) doner."""
    from PyQt6.QtCore import QUrl

    w = ana_pencere()
    acilanlar, gorseller = [], []
    w._open_file_in_editor = lambda p, *a, **k: acilanlar.append(p)
    w._insert_image = lambda p: gorseller.append(p)

    def _birak(yol):
        acilanlar.clear()
        gorseller.clear()
        w._status.showMessage("Hazır")
        w._handle_dropped_urls([QUrl.fromLocalFile(str(yol))])
        return acilanlar[:], gorseller[:], w._status.currentMessage()

    _birak.w = w
    return _birak


def test_desteklenmeyen_tur_BIRAKILINCA_da_sebep_soyleniyor(birakan, tmp_path,
                                                            iki_giris):
    """Kırılırsa kullanıcı dosyayı pencereye sürükler, hiçbir şey olmaz ve
    neden olmadığını söyleyen hiçbir şey yoktur."""
    p = tmp_path / "veri.csv"
    p.write_text("a,b\n", encoding="utf-8")

    acilan, gorsel, mesaj = birakan(p)

    assert not acilan and not gorsel
    assert "veri.csv" in mesaj and mesaj != "Hazır", mesaj
    # Komut satırıyla AYNI cümle: kural tek yerde
    dosya, ilk, _ikinci = iki_giris
    m_komut, _a, _w = ilk(dosya("veri.csv"))
    assert mesaj == m_komut, (mesaj, m_komut)


def test_OLMAYAN_yol_birakilinca_bulunamadi_diyor(birakan, tmp_path):
    acilan, gorsel, mesaj = birakan(tmp_path / "yok.tex")

    assert not acilan and not gorsel
    assert "yok.tex" in mesaj and mesaj != "Hazır", mesaj


def test_KLASOR_birakilinca_yonlendirici_mesaj(birakan, tmp_path):
    """Klasör 'açılamayan tür' değil: uygulama klasör açabiliyor, yalnız
    bırakarak değil. Mesaj o yüzden ne yapılacağını söylemeli."""
    d = tmp_path / "projem"
    d.mkdir()

    acilan, gorsel, mesaj = birakan(d)

    assert not acilan and not gorsel
    assert "projem" in mesaj and "Ctrl+O" in mesaj, mesaj


def test_TEX_birakilinca_hala_aciliyor(birakan, tmp_path):
    """Aşırı düzeltme kapısı."""
    p = tmp_path / "belge.tex"
    p.write_text("\\documentclass{article}\n", encoding="utf-8")

    acilan, gorsel, mesaj = birakan(p)

    assert [_norm(a) for a in acilan] == [_norm(str(p))] and not gorsel
    assert "açılamıyor" not in mesaj, mesaj


def test_GORSEL_birakilinca_hala_ekleniyor(birakan, tmp_path):
    """Aşırı düzeltme kapısı: `.png` komut satırından açılamaz (doğrusu da
    o) ama bırakılınca includegraphics üretmeli, uyarı değil."""
    p = tmp_path / "sekil.png"
    p.write_bytes(b"\x89PNG\r\n")

    acilan, gorsel, mesaj = birakan(p)

    assert [_norm(g) for g in gorsel] == [_norm(str(p))] and not acilan
    assert "açılamıyor" not in mesaj, mesaj


def test_gorsel_uzanti_kumesi_TEK_KAYNAK():
    """Kırılırsa küme iki yerde yazılı demektir: `latex_refs` bir uzantı
    kazanınca sürükle bırak onu görmezden gelirdi."""
    import inspect
    from core.latex_refs import IMG_EXTS
    import gui.main_window as mw

    kaynak = inspect.getsource(mw.MainWindow._handle_dropped_urls)
    assert "IMG_EXTS" in kaynak, "sürükle bırak kendi demetini taşıyor"
    for ek in (".png", ".pdf", ".eps"):
        assert ek in IMG_EXTS
