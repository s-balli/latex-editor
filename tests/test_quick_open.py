"""Ctrl+P hızlı dosya açma — koleksiyon, bulanık eşleşme, dialog davranışı."""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from gui.mixins.file_ops import FileOpsMixin
    from gui.quick_open import QuickOpenDialog, collect_project_files, fuzzy_score
    from tests.stub_main import StubMain
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# --- collect_project_files ---


def test_collect_filters_and_sorts(tmp_path):
    (tmp_path / "main.tex").write_text("x", encoding="utf-8")
    (tmp_path / "refs.bib").write_text("x", encoding="utf-8")
    sub = tmp_path / "bolum"
    sub.mkdir()
    (sub / "giris.tex").write_text("x", encoding="utf-8")
    (tmp_path / "sekil.png").write_bytes(b"")      # uzantı dışı → listede yok
    hid = tmp_path / ".git"
    hid.mkdir()
    (hid / "gizli.tex").write_text("x", encoding="utf-8")            # gizli dizin → yok
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "paket.sty").write_text("x", encoding="utf-8")             # skip dizini → yok (dosya ağacıyla aynı kural)
    rels = collect_project_files(str(tmp_path))
    assert rels == ["bolum/giris.tex", "main.tex", "refs.bib"]


# --- fuzzy_score ---


def test_fuzzy_empty_query_matches_all():
    assert fuzzy_score("", "her/yol.tex") == 0


def test_fuzzy_subsequence_and_basename_bonus():
    """Dosya adında eşleşen aday, adında eşleşmeyenin önünde olmalı.

    RAKİP DEĞİŞTİ. Eskiden karşılaştırma `bolum/diğer-m-t.tex` ileydi ve o
    dosyanın adı da 'mt'yi taşıyor; testin geçmesi dosya adı bonusuna değil,
    rakibin DİZİN adında 'm' bulunmasına bağlıydı. ÖLÇÜLDÜ (2026-09-05,
    düzeltmeden ÖNCEKİ kodla): rakip `sec/` ya da `kaynak/` altında olsaydı
    puanı -3 çıkıyor ve aynı iddia ESKİ kodda da düşüyordu.

    Yeni rakibin adında 'mt' hiç geçmiyor, yani karşılaştırma gerçekten
    "adında eşleşen, eşleşmeyenin önünde" diyor.
    """
    assert fuzzy_score("mt", "main.tex") < fuzzy_score("mt", "mim/tez-yok.tex")


def test_fuzzy_tight_path_match_beats_wide_basename_match():
    """Bonus küçük bir ödüldür; yayılım (spread) farkını ezemez.

    'mt' dar biçimde yol (dizin) kısmında eşleşirken (yayılım 1), geniş
    biçimde dosya adında eşleşen adaydan (yayılım ~12) ÖNDE sıralanmalı.
    Bonus büyütülürse (örn. -5 yerine -50) sıralama tersine döner; bu test
    büyüklüğü pinler (mutasyonla doğrulandı: -50 kırmızı görür).
    """
    tight_path = fuzzy_score("mt", "mt/xx.tex")             # yayılım 1, bonus yok
    wide_name = fuzzy_score("mt", "src/m___________t.tex")  # yayılım ~12, bonuslu
    assert tight_path < wide_name


def test_fuzzy_case_insensitive():
    assert fuzzy_score("MT", "main.tex") is not None


def test_fuzzy_no_match():
    assert fuzzy_score("zzz", "main.tex") is None


# --- dialog ---


def test_dialog_filters_and_selects(qapp, tmp_path):
    (tmp_path / "main.tex").write_text("x", encoding="utf-8")
    (tmp_path / "makale.tex").write_text("x", encoding="utf-8")
    dlg = QuickOpenDialog(str(tmp_path))
    assert dlg._list.count() == 2
    dlg._edit.setText("mak")
    assert dlg._list.count() == 1
    assert dlg._list.currentItem().text() == "makale.tex"
    assert dlg.selected_path().endswith("makale.tex")
    assert os.path.normpath(dlg.selected_path()) == dlg.selected_path()


def test_dialog_keyboard_navigation(qapp, tmp_path):
    (tmp_path / "a.tex").write_text("x", encoding="utf-8")
    (tmp_path / "b.tex").write_text("x", encoding="utf-8")
    (tmp_path / "c.tex").write_text("x", encoding="utf-8")
    dlg = QuickOpenDialog(str(tmp_path))
    assert dlg._list.currentRow() == 0
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    assert dlg.eventFilter(dlg._edit, ev) is True
    assert dlg._list.currentRow() == 1


# --- MainWindow._quick_open handler ---


class _StubQuick(FileOpsMixin, StubMain):
    def __init__(self, root):
        super().__init__()
        self._file_tree = SimpleNamespace(_root=root)
        self.opened = []

    def _open_file_in_editor(self, path):
        self.opened.append(path)


def test_quick_open_handler_opens_picked(qapp, tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text("x", encoding="utf-8")
    stub = _StubQuick(str(tmp_path))
    with patch("gui.quick_open.QuickOpenDialog.pick", return_value=str(tex)):
        MainWindow._quick_open(stub)
    assert stub.opened == [str(tex)]


def test_quick_open_without_folder(qapp):
    stub = _StubQuick("")
    MainWindow._quick_open(stub)
    assert stub.opened == []
    assert "klasör açın" in stub._status.msg


# =====================================================================
# Sıralama: yazdığın adın dosyası ilk sırada olmalı
#
# Ctrl+P'de Enter LİSTENİN İLK ögesini açıyor (returnPressed -> accept ->
# selected_path -> currentItem, ve _refilter ilk satırı seçiyor). Sıralama
# yanlışsa kullanıcı YANLIŞ DOSYAYI açıyor.
#
# ÖLÇÜLEN KUSUR (2026-09-05): tarama her zaman yolun BAŞINDAN başlıyor ve her
# karakterin ilk geçişini alıyordu. Sorgu DİZİN adında da geçtiğinde o
# dizindeki bütün dosyalar aynı puanı alıyor, dosya adı hiç rol oynamıyor,
# eşitlik alfabetik bozuluyordu. En yaygın yerleşimlerde:
#
#     bolumler/ içinde "bolum"   ->  bolumler/baslik.tex   açılıyordu
#     chapters/ içinde "chapter" ->  chapters/abstract.tex açılıyordu
#     sekiller/ içinde "sekil"   ->  sekiller/aciklama.tex açılıyordu
#
# Depodaki 59 gerçek şablonda da 3 vaka vardı; birinde aranan dosya 5. sıraya
# düşüyordu.
# =====================================================================


def _sirala(dosyalar, sorgu):
    """QuickOpenDialog._refilter ile AYNI sıralama."""
    p = [(fuzzy_score(sorgu, r), r) for r in dosyalar]
    p = [(s, r) for s, r in p if s is not None]
    p.sort(key=lambda t: (t[0], t[1]))
    return [r for _s, r in p]


def _adda_esliyor(sorgu, rel):
    """Sorgu, dosya ADINDA alt dizi olarak geçiyor mu."""
    q, ad = sorgu.lower(), os.path.basename(rel).lower()
    qi = 0
    for ch in ad:
        if qi < len(q) and ch == q[qi]:
            qi += 1
    return qi == len(q)


class TestSiralamaDosyaAdiniOnceliyor:

    @pytest.mark.parametrize("dosyalar,sorgu,beklenen", [
        # Türkçe tez: dizin adı dosya adını İÇERİYOR
        (["main.tex", "bolumler/bolum.tex", "bolumler/baslik.tex",
          "bolumler/ozet.tex"], "bolum", "bolumler/bolum.tex"),
        # İngilizce tez
        (["main.tex", "chapters/chapter.tex", "chapters/abstract.tex",
          "chapters/appendix.tex"], "chapter", "chapters/chapter.tex"),
        (["sekiller/sekil.tex", "sekiller/aciklama.tex", "sekiller/kaynak.tex"],
         "sekil", "sekiller/sekil.tex"),
        # uzantıyla birlikte
        (["bolumler/bolum.tex", "bolumler/baslik.tex"], "bolum.tex",
         "bolumler/bolum.tex"),
        # derin iç içe: eşleşen dizin ortada
        (["a/bolumler/b/bolum.tex", "a/bolumler/b/baslik.tex"], "bolum",
         "a/bolumler/b/bolum.tex"),
    ])
    def test_adini_yazinca_o_dosya_ilk_sirada(self, dosyalar, sorgu, beklenen):
        assert _sirala(dosyalar, sorgu)[0] == beklenen

    @pytest.mark.parametrize("dosyalar,sorgu", [
        (["bolumler/bolum.tex", "bolumler/baslik.tex"], "bolum"),
        (["chapters/chapter.tex", "chapters/abstract.tex"], "chapter"),
    ])
    def test_vakanin_ONKOSULU_sorgu_dizin_adinda_da_geciyor(self, dosyalar, sorgu):
        """Kapı boşalmasın: sorgu dizin adında geçmiyorsa vaka bir şey ölçmez.

        Kusur tam da "sorgu dizin adında da geçiyor" halinde çıkıyordu.
        """
        dizin = dosyalar[0].rsplit("/", 1)[0]
        # `_adda_esliyor` dosya ADINA bakıyor; burada DİZİN adını sınıyoruz.
        assert _adda_esliyor(sorgu, dizin), (sorgu, dizin)

    def test_adinda_eslesen_eslesmeyenin_ONUNDE(self):
        """Asıl değişmez, tek cümlede."""
        assert (fuzzy_score("bolum", "bolumler/bolum.tex")
                < fuzzy_score("bolum", "bolumler/baslik.tex"))

    def test_gercek_sablonlarda_hicbir_dosya_adina_haksizlik_yok(self):
        """Depodaki şablon ağaçlarının tamamı; ölçüt belirsizliği dışarıda bırakır.

        "InterPore" yazınca InterPore.cls mi InterPore-Sample.tex mi önce
        gelmeli sorusu (ikisinin de ADI eşleşiyor) sorulmuyor; sorulan şey,
        adında HİÇ eşleşmeyen bir dosyanın öne geçip geçmediği.
        """
        sablon = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "template")
        if not os.path.isdir(sablon):
            pytest.skip("template/ yok")

        toplam = 0
        kotu = []
        for proje_ad in sorted(os.listdir(sablon)):
            proje = os.path.join(sablon, proje_ad)
            if not os.path.isdir(proje):
                continue
            dosyalar = collect_project_files(proje)
            if len(dosyalar) < 3:
                continue
            for rel in dosyalar:
                temel = os.path.basename(rel)
                for sorgu in (temel, os.path.splitext(temel)[0]):
                    if not sorgu:
                        continue
                    toplam += 1
                    s = _sirala(dosyalar, sorgu)
                    if (s and _adda_esliyor(sorgu, rel)
                            and not _adda_esliyor(sorgu, s[0])):
                        kotu.append((proje_ad, sorgu, rel, s[0]))
        # önkoşul: kitle gerçekten sınanmış olsun
        assert toplam > 300, "şablon kitlesi beklenenden küçük: %d" % toplam
        assert not kotu, "adında eşleşmeyen dosya öne geçti: %s" % kotu[:5]


class TestSiralamaKarsiDurumlar:
    """Eskiden doğru olan davranış aynen sürmeli."""

    @pytest.mark.parametrize("sorgu,yol,beklenen", [
        ("main.tex", "main.tex", 2),          # tek düzey proje
        ("tez", "sablon/tez.tex", -3),        # alt dizindeki tam ad
    ])
    def test_puan_eski_degerinde(self, sorgu, yol, beklenen):
        assert fuzzy_score(sorgu, yol) == beklenen

    def test_sorguda_bolu_varsa_yol_uzerinden_eslesiyor(self):
        """Dosya adında '/' olamaz; böyle sorgu yola düşmeli."""
        assert fuzzy_score("bolumler/bolum", "bolumler/bolum.tex") is not None

    def test_dosya_adinda_eslesmeyen_sorgu_yola_dusuyor(self):
        assert fuzzy_score("bolumlerbolum", "bolumler/bolum.tex") is not None

    def test_hicbir_yerde_eslesmezse_None(self):
        assert fuzzy_score("zzz", "bolumler/bolum.tex") is None
