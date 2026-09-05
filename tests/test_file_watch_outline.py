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
# İlki standart bir kullanım (uzun başlığın içindekiler/üstbilgi karşılığı),
# yani uzun başlıklı tezlerde anahat sessizce eksikti.

@pytest.mark.parametrize("kaynak,baslik", [
    ("\\section{Giris}", "Giris"),
    ("\\chapter[Kisa]{Uzun Bolum Basligi}", "Ch: Uzun Bolum Basligi"),
    ("\\subsection[K]{Uzun}", "Uzun"),
    ("\\section{Yontem ve \\emph{Materyal}}", "Yontem ve \\emph{Materyal}"),
    ("\\subsection{A \\texttt{kod} B}", "A \\texttt{kod} B"),
    ("\\section*{Yildizli}", "Yildizli"),
    ("\\chapter{$E=mc^2$ uzerine}", "Ch: $E=mc^2$ uzerine"),
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
    from gui.outline import _sozel_araliklar

    kok = pathlib.Path(__file__).resolve().parents[1] / "template"
    if not kok.is_dir():
        pytest.skip("template dizini yok")

    re_bas = re.compile(
        r'\\(part|chapter|section|subsection|subsubsection'
        r'|paragraph|subparagraph)\*?\s*(?:\[[^\]]*\])?\s*\{')
    icerideki = 0
    for yol in kok.rglob("*.tex"):
        metin = yol.read_text(encoding="utf-8", errors="replace")
        araliklar = _sozel_araliklar(metin)
        if not araliklar:
            continue
        icerideki += sum(1 for m in re_bas.finditer(metin)
                         if any(a <= m.start() < b for a, b in araliklar))

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
    ("\\section{Kar \\%20} \\subsection{Detay}\n", ["Kar \\%20", "Detay"]),
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
