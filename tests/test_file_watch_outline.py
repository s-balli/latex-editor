"""file_watch prompt-guard ve anahat genişletme korunumu testleri."""

from types import SimpleNamespace

import pytest

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox, QTabWidget, QWidget
    from gui.editor import EditorWidget
    from gui.mixins.file_watch import FileWatchMixin
    from gui.mixins.tab_ops import TabOpsMixin
    from gui.outline import OutlinePanel
    from gui.theme import THEMES
    from syntax.latex_lexer import VERB_ENVS
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# =====================================================================
# file_watch: modal prompt açıkken kuyruk birikmez
# =====================================================================


class _WatchStub(FileWatchMixin, TabOpsMixin, QWidget):
    """file_watch, QWidget olmayan StubMain ile kurulamaz (QTimer/watcher
    parent ister); gereken arayüz küçük tutuldu."""

    def __init__(self, editors=()):
        super().__init__()
        self._editor_tabs = QTabWidget()
        for ed in editors:
            self._editor_tabs.addTab(ed, ed.display_name)
        self._wordcount_editor = None
        self._outline_editor = None
        self._find_bar = None
        self._current_pdf = ""
        self._pdf_viewer = SimpleNamespace(clear=lambda: None)
        self._file_watch_init()

    def _detect_engine(self, path):
        pass


def _tex(tmp_path, name):
    p = tmp_path / name
    p.write_text("\\begin{document}\nx\n\\end{document}\n", encoding="utf-8")
    return str(p)


def test_prompt_acikken_kuyruk_defer_edilir(qapp, tmp_path, monkeypatch):
    """Dialog açıkken process_queue yeniden tur koşarsa promptlar üst üste
    binerdi; kuyruk beklemeli, timer yeniden planlanmalı."""
    ed = EditorWidget()
    ed.open_file(_tex(tmp_path, "a.tex"))
    stub = _WatchStub([ed])
    cagrilar = []
    monkeypatch.setattr(stub, "_process_single", lambda p: cagrilar.append(p))

    stub._pending_reloads = {"/a.tex", "/b.tex"}
    stub._reload_prompt_active = True
    stub._file_watch_process_queue()

    assert cagrilar == []                       # hiç işlenmedi
    assert stub._pending_reloads == {"/a.tex", "/b.tex"}  # kuyruk duruyor
    assert stub._debounce_timer.isActive()      # dialog kapanınca tekrar denenecek

    # dialog kapandı: kuyruk işlenir
    stub._reload_prompt_active = False
    stub._debounce_timer.stop()
    stub._file_watch_process_queue()
    assert sorted(cagrilar) == ["/a.tex", "/b.tex"]
    assert stub._pending_reloads == set()


def test_prompt_flag_acilis_kapanis_yasam_dongusu(qapp, tmp_path, monkeypatch):
    """_prompt_reload flag'i dialog bitince kesin düşürür (istisnada bile)."""
    ed = EditorWidget()
    ed.open_file(_tex(tmp_path, "a.tex"))

    def fake_exec(self):
        return None  # dialog aninda kapandi

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    stub = _WatchStub([ed])
    stub._prompt_reload(ed, ed.file_path, "yeni-hash")
    assert stub._reload_prompt_active is False


# =====================================================================
# outline: genişletme tercihleri yeniden kurulumda korunur
# =====================================================================


BELGE = (
    "\\section{Bir}\n\\subsection{Alt Bir}\n\\subsection{Alt Iki}\n"
    "\\section{Iki}\n\\subsection{Alt Uc}\n"
)


def _bul(panel, yol):
    """Başlık-zincirine göre düğüm bul ('Iki' > 'Alt Uc' gibi)."""
    parcalar = yol.split(" > ")

    def ara(item, kalan):
        if item.text(0) == kalan[0]:
            if len(kalan) == 1:
                return item
            for i in range(item.childCount()):
                r = ara(item.child(i), kalan[1:])
                if r is not None:
                    return r
        return None

    for i in range(panel._tree.topLevelItemCount()):
        r = ara(panel._tree.topLevelItem(i), parcalar)
        if r is not None:
            return r
    return None


def test_genisletme_durumu_yeniden_kurulumda_korunur(qapp):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(BELGE)

    alt = _bul(p, "Bir > Alt Bir")
    ust_iki = _bul(p, "Iki")
    assert alt is not None and ust_iki is not None

    # kullanici tercihleri: alt düğümü aç, üst 'Iki'yi kapat
    p._tree.expandItem(alt)
    p._tree.collapseItem(ust_iki)

    # ayni içerik + yeni bölüm ile yeniden kur
    p.update_outline(BELGE + "\\section{Uc}\n")
    assert _bul(p, "Bir > Alt Bir").isExpanded(), "açılan alt düğüm açık kalmalı"
    assert not _bul(p, "Iki").isExpanded(), "kapatılan üst düğüm kapalı kalmalı"
    # yeni düğüm varsayılanı alır (üst seviye → açık)
    assert _bul(p, "Uc").isExpanded()


def test_ilk_kurulum_varsayilan_ust_seviye_acik(qapp):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(BELGE)
    assert _bul(p, "Bir").isExpanded()
    assert not _bul(p, "Bir > Alt Bir").isExpanded()  # alt seviye kapalı


# --- outline: bölüm başlığı deseni ---
#
# İki biçim eskiden yanlış işleniyordu (2026-08-31, G3):
#   \chapter[Giriş]{Giriş ve Kapsam}  → hiç eşleşmiyordu, bölüm anahatta YOKTU
#   \section{A \emph{B} C}            → başlık ilk iç kümede kırpılıyordu
#
# GÖSTERİM 2026-09-09'da değişti: panelde ham LaTeX görünüyordu
# (`\centerline{KISALTMALAR}`, `\LaTeX-Specific Advice`, `\break
# Footnotes`). 39 şablonun 133 dosyasında 12 dosyada 37 ayrı başlıkta
# kalıntı ölçüldü. Beklentiler ona göre; kapıların AMACI aynı.
# İlki standart bir kullanım (uzun başlığın içindekiler/üstbilgi karşılığı),
# yani uzun başlıklı tezlerde anahat sessizce eksikti.

@pytest.mark.parametrize("kaynak,baslik", [
    ("\\section{Giris}", "Giris"),
    ("\\chapter[Kisa]{Uzun Bolum Basligi}", "Ch: Uzun Bolum Basligi"),
    ("\\subsection[K]{Uzun}", "Uzun"),
    # Sarmalayıcı komut argümanına indiriliyor: görünen metin o
    ("\\section{Yontem ve \\emph{Materyal}}", "Yontem ve Materyal"),
    ("\\subsection{A \\texttt{kod} B}", "A kod B"),
    ("\\section*{Yildizli}", "Yildizli"),
    # Matematik ayracı etikette bilgi taşımıyor, içeriği kalıyor
    ("\\chapter{$E=mc^2$ uzerine}", "Ch: E=mc^2 uzerine"),
    ("\\section {Bosluklu}", "Bosluklu"),
])
def test_bolum_basligi_deseni(qapp, kaynak, baslik):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(kaynak + "\n")
    assert len(p._items) == 1, f"bölüm anahatta görünmedi: {kaynak}"
    assert p._items[0].text(0) == baslik


def test_kisa_baslikli_bolum_hiyerarsiye_giriyor(qapp):
    """Opsiyonel argüman seviye/satır bilgisini bozmamalı."""
    belge = ("\\chapter[K]{Birinci Bolum}\n"
             "metin\n"
             "\\section[A]{Alt Baslik}\n")
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(belge)
    assert [i.text(0) for i in p._items] == ["Ch: Birinci Bolum", "Alt Baslik"]
    # alt başlık chapter'ın ÇOCUĞU olmalı, kardeşi değil
    assert p._items[1].parent() is p._items[0]
    # satır numarası (0-bazlı) korunuyor: goto_line bunu kullanıyor
    assert p._items[0].data(0, Qt.ItemDataRole.UserRole) == 0
    assert p._items[1].data(0, Qt.ItemDataRole.UserRole) == 2


def test_yorumdaki_bolum_kisa_baslikliyken_de_atlaniyor(qapp):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("% \\chapter[K]{Yorumda}\n\\section{Gercek}\n")
    assert [i.text(0) for i in p._items] == ["Gercek"]


# =====================================================================
# Anahat taraması: sözel ortamlar ve kaçışlı yüzde (2026-09-05)
#
# F1. Tarama yalnız `%` yorumunu atlıyordu; verbatim/lstlisting/minted
#     içindeki ÖRNEK bölüm komutları gerçek bölüm sanılıyordu. Ölçüldü:
#     paketlenmiş şablonların ikisi (mnras_guide, pasj02_usage) bölüm
#     komutunu `\begin{verbatim}` içinde ANLATIYOR ve anahatta 11 sahte
#     başlık çıkıyordu; tıklanınca kullanıcı kod örneğine gidiyordu.
#
# F2. Yorum denetimi ham `'%' in line_text` idi. LaTeX'te `\%` yorum
#     başlatmaz. Aynı satırda bölümden önce bir `\%` geçerse bölüm anahattan
#     düşüyordu. Aynı dosyadaki `_baslik_oku` kaçışları zaten doğru ele
#     alıyordu; yorum denetimi o dersi almamıştı.
# =====================================================================

_SOZEL_VAKALAR = [
    ("verbatim", "verbatim"),
    ("Verbatim", "Verbatim"),
    ("lstlisting", "lstlisting"),
    ("minted}{python", "minted"),
    ("alltt", "alltt"),
]


@pytest.mark.parametrize("acilis,kapanis", _SOZEL_VAKALAR)
def test_sozel_ortamdaki_bolum_anahatta_CIKMIYOR(qapp, acilis, kapanis):
    """Kırılırsa: `_sozel_araliklar` o ortamı tanımıyor demektir."""
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("\\section{Gercek}\n"
                     "\\begin{%s}\n\\subsection{Ornek}\n\\end{%s}\n"
                     "\\section{Ikinci}\n" % (acilis, kapanis))
    assert [i.text(0) for i in p._items] == ["Gercek", "Ikinci"]


def test_sozel_ortam_YILDIZLI_ve_ardisik_bloklar(qapp):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(
        "\\section{A}\n\\begin{verbatim*}\n\\section{X}\n\\end{verbatim*}\n"
        "\\section{B}\n\\begin{lstlisting}\n\\section{Y}\n\\end{lstlisting}\n"
        "\\section{C}\n")
    assert [i.text(0) for i in p._items] == ["A", "B", "C"]


def test_kapanmamis_sozel_ortam_sonrasini_YUTUYOR(qapp):
    """LaTeX de yutuyor; yarım bloktan sahte başlık üretmek daha kötü."""
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("\\section{A}\n\\begin{verbatim}\n\\section{X}\n")
    assert [i.text(0) for i in p._items] == ["A"]


def test_sozel_ortam_DISINDAKI_bolum_korunuyor(qapp):
    """Karşı durum: aşırı düzeltme (her şeyi atla) burada kırılır."""
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(
        "\\begin{verbatim}\nkod\n\\end{verbatim}\n\\section{A}\n"
        "\\subsection{B}\n")
    assert [i.text(0) for i in p._items] == ["A", "B"]
    p.update_outline("verbatim kelimesi metinde\n\\section{A}\n")
    assert [i.text(0) for i in p._items] == ["A"]


def test_sozel_tarama_SABLONLARDA_gercekten_is_goruyor(qapp):
    """Kapı boş koşmasın: korpusta gerçekten sözel içi bölüm olmalı.

    Şablonlar değişip bu vakalar kaybolursa yukarıdaki sentetik testler
    yeşil kalır ama korpus artık hiçbir şey kanıtlamaz; burası onu söyler.
    """
    import pathlib
    import re

    from core.latex_utils import sozel_soy

    kok = pathlib.Path(__file__).resolve().parents[1] / "template"
    if not kok.is_dir():
        pytest.skip("template dizini yok")

    re_bas = re.compile(
        r'\\(part|chapter|section|subsection|subsubsection'
        r'|paragraph|subparagraph)\*?\s*(?:\[[^\]]*\])?\s*\{')
    # Soyma uzunluğu KORUDUĞU için "soyulmuş metinde artık eşleşmiyor" ile
    # "sözel içindeydi" aynı şey; ayrı bir aralık listesine gerek yok.
    icerideki = 0
    for yol in kok.rglob("*.tex"):
        metin = yol.read_text(encoding="utf-8", errors="replace")
        soyulmus = sozel_soy(metin)
        if soyulmus == metin:
            continue
        icerideki += sum(1 for m in re_bas.finditer(metin)
                         if not re_bas.match(soyulmus, m.start()))

    assert icerideki >= 10, \
        "korpusta sözel içi bölüm kalmamış (%d), kapı boş koşuyor" % icerideki


@pytest.mark.parametrize("parca,beklenen", [
    ("", False),
    ("abc", False),
    ("%", True),
    ("\\%", False),          # kaçışlı yüzde YORUM DEĞİL
    ("\\\\%", True),         # `\\` satır sonu, ardından yorum
    ("a \\% b % c", True),
    ("\\%\\%", False),
    ("\\", False),
])
def test_yorum_var_mi_kacisi_biliyor(parca, beklenen):
    from gui.outline import _yorum_var_mi
    assert _yorum_var_mi(parca) is beklenen


@pytest.mark.parametrize("kaynak,beklenen", [
    ("\\%20 indirim \\section{Giris}\n", ["Giris"]),
    # Yüzde işareti KORUNUYOR ama kaçışı GÖSTERİLMİYOR: LaTeX de "Kar %20"
    # basıyor. Kaçış korunmasa `%` başlıktan düşerdi (gösterim temizliği
    # 2026-09-09'da eklenirken bir kez düşmüştü, bu kapı yakaladı).
    ("\\section{Kar \\%20} \\subsection{Detay}\n", ["Kar %20", "Detay"]),
    ("\\textbackslash\\%5 \\section{A}\n", ["A"]),
    # KONTROL: gerçek yorumlar hâlâ atlanmalı
    ("% \\section{Y}\n", []),
    ("metin % \\section{Y}\n", []),
    ("a \\\\% \\section{Y}\n", []),
    ("% yorum\n\\section{A}\n", ["A"]),
])
def test_kacisli_yuzde_bolumu_DUSURMUYOR(qapp, kaynak, beklenen):
    """Kırılırsa: yorum denetimi kaçışı yeniden unutmuş demektir."""
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline(kaynak)
    assert [i.text(0) for i in p._items] == beklenen


# =====================================================================
# Sözel ortam listesi TEK KAYNAK (2026-09-06)
#
# Liste iki yerde ayrı ayrı yazılıydı ve AYRIŞMIŞTI: lexer 9 taban ortamı
# sözel sayıyor, anahat 5'ini. Ölçüldü: `comment`, `BVerbatim`, `LVerbatim`
# ve `listing` içine alınmış bir bölüm komutu editörde sözel renklenirken
# ANAHATTA listeleniyordu. `comment` paketi büyük blokları geçici kapatmanın
# standart yolu, yani senaryo sıradan.
#
# Bu, yukarıdaki F1'in ta kendisi; o düzeltme beş elemanlı AYRI bir liste
# kullanmış, lexer'ınkini değil. Aşağıdaki kapı listeyi lexer'dan TÜRETİYOR:
# yeni bir sözel ortam eklendiğinde kendiliğinden onu da sınar.
# =====================================================================

_LEXER_SOZEL = sorted({e.rstrip("*") for e in VERB_ENVS})


def test_sozel_ortam_listesi_TEK_KAYNAKTAN():
    """Kırılırsa: anahat yine kendi ayrı listesini tutuyor demektir.

    2026-09-09'da soyma işi `core.latex_utils.sozel_soy`a taşındı (aynı
    listeyi referans denetimi de kullanıyor ve orada satır içi `\\verb` de
    kapsanıyor). Kapı artık iki şeye bakıyor: anahat kendi liste/desen
    tutmuyor, ve soymayı o tek kaynaktan alıyor.
    """
    import io
    import os

    import gui.outline as anahat

    assert anahat.sozel_soy is not None
    kaynak = io.open(os.path.abspath(anahat.__file__), encoding="utf-8",
                     newline="").read()
    for desen in ("_SOZEL_ORTAMLAR", "_RE_SOZEL", "VERB_ENVS"):
        assert desen not in kaynak, (
            "anahat yine kendi sözel listesini tutuyor: %r" % desen)


def test_lexer_listesi_BOS_DEGIL():
    """Kapı boş koşmasın: liste boşalırsa aşağısı hiçbir şey kanıtlamaz."""
    assert len(_LEXER_SOZEL) >= 5


def test_AYRISMADA_EKSIK_KALAN_dortlu_listede_duruyor():
    """Listeden düşerlerse yukarıdaki parametrik kapılar sessizce boşalırdı.

    Bu dördü 2026-09-06'da anahatta eksikti ve BAŞKA hiçbir testleri yok
    (`verbatim`, `Verbatim`, `lstlisting`, `minted`, `alltt` beşlisini
    yukarıdaki `_SOZEL_VAKALAR` ayrıca tutuyor). Alt küme denetimi: yeni
    ortam eklemek burayı kırmaz, çıkarmak kırar.
    """
    assert {"comment", "BVerbatim", "LVerbatim", "listing"} <= set(_LEXER_SOZEL)


@pytest.mark.parametrize("ortam", _LEXER_SOZEL)
def test_lexerin_HER_sozel_ortami_anahatta_da_SOZEL(qapp, ortam):
    """Lexer bir ortamı sözel sayıyorsa anahat da saymalı."""
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("\\section{Gercek}\n"
                     "\\begin{%s}\n\\subsection{GIZLI}\n\\end{%s}\n"
                     "\\section{Ikinci}\n" % (ortam, ortam))
    assert [i.text(0) for i in p._items] == ["Gercek", "Ikinci"]


@pytest.mark.parametrize("ortam", _LEXER_SOZEL)
def test_sozel_ortamin_YILDIZLI_bicimi_de_sozel(qapp, ortam):
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("\\section{A}\n"
                     "\\begin{%s*}\n\\section{GIZLI}\n\\end{%s*}\n"
                     "\\section{B}\n" % (ortam, ortam))
    assert [i.text(0) for i in p._items] == ["A", "B"]


def test_BENZER_ADLI_ortam_sozel_SAYILMIYOR(qapp):
    """Aşırı düzeltme kapısı: `verbatimx` sözel değil, içindeki bölüm görünmeli.

    Desen `re.escape` ile ve tam ad eşleyerek kuruluyor; önek eşlemesine
    kayarsa burası kırılır.
    """
    p = OutlinePanel(theme=THEMES["dark"])
    p.update_outline("\\begin{verbatimx}\n\\section{GORUNSUN}\n"
                     "\\end{verbatimx}\n")
    assert [i.text(0) for i in p._items] == ["GORUNSUN"]


# =====================================================================
# Anahat GÖSTERİMİ: ham LaTeX değil, okunur başlık
#
# 39 şablonun 133 .tex dosyası dört ölçütle tarandı (2026-09-09). Ölçütler
# ground truth gerektirmiyor: başlıkta LaTeX kalıntısı, BOŞ başlık, yanlış
# satır numarası, aynı satırda tekrar.
#
#   başlıkta LaTeX kalıntısı : 37 tekil / 12 dosya -> 0
#   BOŞ başlık               : 20 -> 0
#   aynı satırda tekrar      :  3 -> 0
#   yanlış satır numarası    :  0 -> 0   (zaten doğruydu)
#
# Üç kök, hepsi gerçek satırlardan:
#   \section*{\centerline{KISALTMALAR}}          template11/Etuthesis
#   \subsection{\LaTeX-Specific Advice}          template19/access
#   \section{\break Footnotes}                   template20/access (5 kez)
#   \section{The \code{main.tex} File Explained} template29-tez/Chapter1
#   \section[\appendixname~\thesection]{}        template27 (3 kez, BOŞ)
#   \verb|\section{}| anlatan satır              template29-tez/Chapter1:308
#                                                (iki BOŞ başlık + tekrar)
# =====================================================================


from gui.outline import _baslik_goster


class TestAnahatBaslikGosterimi:

    @pytest.mark.parametrize("ham,beklenen", [
        # Sarmalayıcı: görünen kısım ARGÜMAN
        (r"\centerline{KISALTMALAR}", "KISALTMALAR"),
        (r"The \code{main.tex} File Explained", "The main.tex File Explained"),
        (r"\textbf{Kalin} ve \emph{egik}", "Kalin ve egik"),
        (r"Ic ice \textbf{\emph{iki kat}} baslik", "Ic ice iki kat baslik"),
        # Argümansız komut: ADI kalıyor, `\LaTeX` doğru sonucu veriyor
        (r"Using \LaTeX", "Using LaTeX"),
        (r"\LaTeX-Specific Advice", "LaTeX-Specific Advice"),
        (r"Learning \LaTeX{}", "Learning LaTeX"),
        (r"\LaTeX{} on a Mac", "LaTeX on a Mac"),
        # Yerleşim/sembol komutları: tümden atılıyor
        (r"\break Footnotes", "Footnotes"),
        (r"ScholarOne\textregistered\ Manuscripts", "ScholarOne Manuscripts"),
        # Font bildirimi metin üretmiyor
        (r"\texttt{\bfseries kod}", "kod"),
        # Matematik ayracı etikette bilgi taşımıyor, içeriği kalıyor
        (r"$E=mc^2$ uzerine", "E=mc^2 uzerine"),
        # Bağlayıcı boşluk bir BOŞLUK
        (r"\appendixname~\thesection", "appendixname thesection"),
        # Düz başlık dokunulmadan geçiyor
        ("Duz baslik", "Duz baslik"),
    ])
    def test_BASLIK_okunur_hale_geliyor(self, ham, beklenen):
        """Kırılırsa panelde ham LaTeX görünüyor."""
        assert _baslik_goster(ham) == beklenen

    @pytest.mark.parametrize("ham,beklenen", [
        (r"Kar \%20", "Kar %20"),
        (r"Fiyat \$5", "Fiyat $5"),
        (r"A \& B", "A & B"),
        (r"Küme \{x\}", "Küme {x}"),
        (r"alt\_cizgi", "alt_cizgi"),
    ])
    def test_KACISLI_noktalama_GORUNUR_kaliyor(self, ham, beklenen):
        """Aşırı düzeltme kapısı: `\\%` basılı bir karakter. Sembol kuralı
        onu bir kez yutmuştu ve deponun kaçışlı yüzde kapısı yakaladı."""
        assert _baslik_goster(ham) == beklenen

    def test_SATIR_ICI_VERB_anahatta_bolum_URETMIYOR(self, qapp):
        r"""`\verb|\section{}|` anlatan bir satır iki BOŞ başlık üretiyordu
        (ölçüldü, template29-tez/Chapter1.tex:308)."""
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline(
                "\\section{Gercek}\n"
                "LaTeX \\verb|\\section{}| ve \\verb|\\subsection{}| yazimi.\n")

            assert [i.text(0) for i in p._items] == ["Gercek"]
        finally:
            p.deleteLater()
            qapp.processEvents()

    def test_ZORUNLU_baslik_BOSSA_kisa_baslik_gosteriliyor(self, qapp):
        r"""`\section[\appendixname~\thesection]{}`: görünen metin KISA
        başlıktır, anahatta boş satır çıkıyordu."""
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline("\\section[Ek A]{}\n")

            assert [i.text(0) for i in p._items] == ["Ek A"]
        finally:
            p.deleteLater()
            qapp.processEvents()

    def test_GERCEKTEN_basliksiz_bolum_ETIKETLENIYOR(self, qapp):
        r"""`\section{}` şablonlarda yazarın dolduracağı yer. Boş satır
        tıklanabilir ama GÖRÜNMEZ."""
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline("\\section{}\\label{}\n")

            assert [i.text(0) for i in p._items] == ["(başlıksız)"]
        finally:
            p.deleteLater()
            qapp.processEvents()

    # --- Aşırı düzeltme kapıları ---

    def test_TEMIZLIK_baslik_DUSURMUYOR(self, qapp):
        """Kalıntı temizliği bir bölümü anahattan atmamalı: temizlenen
        başlık boşalsa bile satır listede kalıyor."""
        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline(
                "\\section{\\centerline{A}}\n"
                "\\section{\\break}\n"
                "\\section{Normal}\n")

            assert len(p._items) == 3
            assert [i.text(0) for i in p._items] == ["A", "(başlıksız)",
                                                     "Normal"]
        finally:
            p.deleteLater()
            qapp.processEvents()

    def test_SATIR_NUMARALARI_temizlikten_ETKILENMIYOR(self, qapp):
        """Soyma ve temizlik uzunluğu korumalı; korumazsa tıklayan kullanıcı
        yanlış satıra gider."""
        from PyQt6.QtCore import Qt

        p = OutlinePanel(theme=THEMES["dark"])
        try:
            p.update_outline(
                "onsoz\n"
                "\\verb|\\section{sahte}| yazimi\n"
                "\\section{\\code{gercek}}\n")

            veriler = [(i.text(0), i.data(0, Qt.ItemDataRole.UserRole))
                       for i in p._items]
            assert veriler == [("gercek", 2)], veriler
        finally:
            p.deleteLater()
            qapp.processEvents()
