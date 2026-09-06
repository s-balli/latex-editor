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
