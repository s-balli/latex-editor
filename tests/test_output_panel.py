"""OutputPanel — bağlamsal Ortam Denetimi satırı testleri.

Kurulum komutu taşıyan öneriler (eksik paket, motor, WSL, Pygments) Öneriler
sekmesinde doktor satırı getirmeli; motor değiştirme önerisi getirmemeli.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from gui.output_panel import OutputPanel
    from gui.theme import THEMES
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)

from core.log_parser import CompileResult, LatexError, LatexSuggestion


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _panel():
    return OutputPanel(theme=THEMES["dark"])


def _suggest_texts(panel) -> list[str]:
    return [panel._suggest_list.item(i).text()
            for i in range(panel._suggest_list.count())]


def test_kurulum_onerisi_doktor_satiri_getirir(qapp):
    panel = _panel()
    result = CompileResult(success=False)
    result.errors = [LatexError(message="! LaTeX Error: File `minted.sty' not found.")]
    result.suggestions = [LatexSuggestion(
        message="Eksik paket: texlive-latex-extra (minted.sty)",
        install_command="sudo apt-get install texlive-latex-extra")]

    fired = []
    panel.env_check_requested.connect(lambda: fired.append(1))
    panel.show_result(result)

    texts = _suggest_texts(panel)
    assert any("Ortam Denetimi" in t for t in texts)
    # Tıklamayı simüle et: son satır doktor satırı, sinyal fimşe vermeli
    last = panel._suggest_list.item(panel._suggest_list.count() - 1)
    assert "Ortam Denetimi" in last.text()
    panel._on_result_click(last)
    assert fired == [1]


def test_motor_degistirme_onerisi_doktor_satiri_getirmez(qapp):
    """'Bu belge xelatex gerektiriyor' bir ortam sorunu değil."""
    panel = _panel()
    result = CompileResult(success=False)
    result.errors = [LatexError(message="requires XeLaTeX")]
    result.suggestions = [LatexSuggestion(
        message="Bu belge xelatex gerektiriyor. Derleme motorunu değiştirin.")]

    panel.show_result(result)
    assert not any("Ortam Denetimi" in t for t in _suggest_texts(panel))


def test_onerisiz_sonuc_doktor_satiri_getirmez(qapp):
    panel = _panel()
    result = CompileResult(success=True)
    panel.show_result(result)
    assert _suggest_texts(panel) == []


# =====================================================================
# Sağ tık menüleri
#
# Üçü de HİÇ koşmuyordu (kapsam ölçümü: `_on_history_menu` 25,
# `_on_list_context_menu` 11, `_on_yazim_context_menu` 10 satır). Menüler
# panelin tek yazma/silme yüzeyi: yanlış sha ile "geri yükle" kullanıcının
# belgesini başka bir sürümün üzerine yazar.
#
# `QMenu.exec` bloklar, o yüzden testlerde metne göre eylem seçen bir
# yardımcıyla değiştiriliyor. Hem TETİKLER hem DÖNDÜRÜR: menülerin biri
# lambda bağlıyor (`_on_yazim_context_menu`), ikisi dönüş değerini
# karşılaştırıyor.
# =====================================================================

from PyQt6.QtWidgets import QApplication, QMenu, QListWidgetItem
from PyQt6.QtCore import Qt

from core.versioning import VersionEntry


class _MenuSecici:
    """`with _MenuSecici("Kopyala"):` -> menüde o eylem seçilmiş sayılır.

    `metin=None` iptali (Esc) taklit eder: hiçbir eylem seçilmez.
    """

    def __init__(self, metin):
        self.metin = metin
        self.gorulen = []

    def __enter__(self):
        self._asil = QMenu.exec
        secici = self

        def _exec(menu, *a, **k):
            secici.gorulen = [x.text() for x in menu.actions() if x.text()]
            if secici.metin is None:
                return None
            for act in menu.actions():
                if act.text() == secici.metin:
                    act.trigger()
                    return act
            raise AssertionError(
                "menüde %r yok, olanlar: %r" % (secici.metin, secici.gorulen))

        QMenu.exec = _exec
        return self

    def __exit__(self, *a):
        QMenu.exec = self._asil
        return False


def _sag_tik_noktasi(liste, satir):
    return liste.visualItemRect(liste.item(satir)).center()


def _gecmis_paneli(n=3):
    p = _panel()
    p.show_history([VersionEntry("sha%d" % i + "0" * 36, 1700000000 + i,
                                 "kayit %d" % i, i + 1)
                    for i in range(n)])
    return p


# --- Sürüm geçmişi menüsü ---------------------------------------------


def test_gecmis_menusu_TIKLANAN_satirin_shasini_yayiyor(qapp):
    """Kırılırsa "geri yükle" başka bir sürümü belgenin üzerine yazar.

    Seçili satır ile SAĞ TIKLANAN satır farklı olabilir; ölçülen davranış
    tıklananın kazanması.
    """
    p = _gecmis_paneli()
    p._history_list.setCurrentRow(0)          # seçili: en yeni
    yayilan = []
    p.version_action.connect(lambda a, s: yayilan.append((a, s)))

    with _MenuSecici("Açık dosyayı bu sürümden geri yükle"):
        p._on_history_menu(_sag_tik_noktasi(p._history_list, 2))

    assert yayilan == [("restore", "sha2" + "0" * 36)], "%r" % (yayilan,)


def test_gecmis_menusu_uc_eylemi_de_yayiyor(qapp):
    p = _gecmis_paneli()
    for etiket, aksiyon in (
            ("Açık dosyanın farklarını göster", "diff"),
            ("Açık dosyanın bu sürümdeki hâlini kopyala", "copy"),
            ("Tüm geçmişi sil", "drop_all")):
        yayilan = []
        baglanti = p.version_action.connect(
            lambda a, s: yayilan.append((a, s)))
        with _MenuSecici(etiket):
            p._on_history_menu(_sag_tik_noktasi(p._history_list, 1))
        p.version_action.disconnect(baglanti)
        assert yayilan and yayilan[0][0] == aksiyon, "%s -> %r" % (etiket,
                                                                   yayilan)


def test_SURUM_SIL_yalniz_en_yeni_satirda_var(qapp):
    """`versioning.drop_last` HER hâlde HEAD'i düşürüyor, tıklanan sürümü
    değil. Öğe başka satırda da çıksa kullanıcı seçtiğinden farklı bir
    sürümü silmiş olurdu.
    """
    p = _gecmis_paneli()

    with _MenuSecici(None) as m0:
        p._on_history_menu(_sag_tik_noktasi(p._history_list, 0))
    assert "Bu sürümü sil (en yeni)" in m0.gorulen

    with _MenuSecici(None) as m1:
        p._on_history_menu(_sag_tik_noktasi(p._history_list, 1))
    assert "Bu sürümü sil (en yeni)" not in m1.gorulen


def test_gecmis_menusu_IPTAL_edilirse_sinyal_cikmiyor(qapp):
    """Esc'e basmak bir sürümü geri yüklememeli."""
    p = _gecmis_paneli()
    yayilan = []
    p.version_action.connect(lambda a, s: yayilan.append((a, s)))

    with _MenuSecici(None):
        p._on_history_menu(_sag_tik_noktasi(p._history_list, 0))

    assert yayilan == []


def test_gecmis_menusu_BOS_alanda_acilmiyor(qapp):
    p = _gecmis_paneli(0)
    yayilan = []
    p.version_action.connect(lambda a, s: yayilan.append((a, s)))
    with _MenuSecici("Tüm geçmişi sil"):
        p._on_history_menu(p._history_list.rect().center())
    assert yayilan == []


# --- Liste menüsü (Kopyala) -------------------------------------------


def test_kopyala_SAG_TIKLANAN_ogeyi_kopyaliyor(qapp):
    """Seçili öğe başkası olabilir; panoya giden, sağ tıklanan olmalı.

    SİNYALDEN geçmek zorunlu: handler listeyi `sender()` ile buluyor,
    doğrudan çağrıldığında hiçbir şey yapmadan çıkıyor (yani doğrudan çağıran
    bir test hiçbir şey ölçmez).
    """
    p = _panel()
    for metin in ("birinci satir", "ikinci satir"):
        p._error_list.addItem(QListWidgetItem(metin))
    p._error_list.setCurrentRow(0)
    QApplication.clipboard().setText("onceki")

    with _MenuSecici("Kopyala"):
        p._error_list.customContextMenuRequested.emit(
            _sag_tik_noktasi(p._error_list, 1))

    assert QApplication.clipboard().text() == "ikinci satir"


def test_kopyala_LISTE_DISINDAN_gelirse_cokmuyor(qapp):
    """`sender()` QListWidget değilse (doğrudan çağrı, başka gönderen)
    sessizce çıkmalı."""
    p = _panel()
    p._on_list_context_menu(p._error_list.rect().center())   # patlamamalı


# --- Ham log -----------------------------------------------------------


def test_append_output_BIRIKTIRIYOR_ve_etiketi_ceviriyor(qapp):
    """Derleme çıktısı akış hâlinde geliyor (`compiler.output_line`); her
    parça öncekinin üstüne yazmamalı."""
    p = _panel()
    p.append_output("[derleniyor] ana.tex\n")
    p.append_output("[basarili] 2 sayfa\n")

    metin = p._log_text.toPlainText()
    assert metin.count("\n") == 2
    assert metin.endswith("2 sayfa\n")
    assert "ana.tex" in metin
    # Türkçe arayüzde etiketler kaynak diliyle aynı; çeviri tablosu kimlik
    # eşlemesini atlıyor, yani etiket bozulmadan geçmeli.
    assert "derleniyor" in metin and "basarili" in metin


# --- Hata satırına tıklama --------------------------------------------


def test_hata_tiklamasi_SATIRSIZ_bulguda_atlamiyor(qapp):
    """Satır numarası olmayan hatada imleç oynamamalı: nereye gideceği
    bilinmiyor ve cari belgede rastgele bir satıra atlamak yanlış."""
    p = _panel()
    it = QListWidgetItem("dosyasiz hata")
    it.setData(Qt.ItemDataRole.UserRole, ("", 0))
    p._error_list.addItem(it)
    yayilan = []
    p.error_clicked.connect(lambda f, l: yayilan.append((f, l)))

    p._on_error_click(it)

    assert yayilan == []


def test_hata_tiklamasi_SATIR_varsa_yayiyor(qapp):
    """Aşırı düzeltme kapısı."""
    p = _panel()
    it = QListWidgetItem("hata")
    it.setData(Qt.ItemDataRole.UserRole, ("C:/x/a.tex", 12))
    p._error_list.addItem(it)
    yayilan = []
    p.error_clicked.connect(lambda f, l: yayilan.append((f, l)))

    p._on_error_click(it)

    assert yayilan == [("C:/x/a.tex", 12)]
