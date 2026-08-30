"""FindReplaceBar testleri — bul, say, değiştir, tümünü değiştir.

254 satırlık bu modülün HİÇ testi yoktu (2026-08-30 denetimi, D5) — üstelik
yıkıcı bir yol: "Tümünü Değiştir" tüm belgeyi tek geri-al adımında
değiştiriyor ve güvenlik sınırına ulaşınca eskiden SESSİZCE kesiyordu.
Deneyle üretilmişti: 12.000 eşleşmeli belgede 10.001 değiştirilip 1.999'u
dokunulmadan kalıyor, etiket yine sayı yazıyor, hiçbir uyarı çıkmıyordu.
"""

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.Qsci import QsciScintilla
    from gui.find_replace import FindReplaceBar
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui.find_replace import edilemiyor", allow_module_level=True)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _bar(metin: str, bul: str = "", degistir: str = ""):
    ed = QsciScintilla()
    ed.setText(metin)
    bar = FindReplaceBar()
    bar.set_editor(ed)
    bar._find_input.setText(bul)
    bar._replace_input.setText(degistir)
    return bar, ed


# --- Sayma ---

class TestSayma:
    def test_basit_sayim(self, qapp):
        bar, _ed = _bar("bir iki bir uc bir\n", "bir")
        bar._count_matches("bir")
        assert bar._match_count == 3
        assert "3" in bar._lbl_count.text()

    def test_buyuk_kucuk_harf_duyarsiz(self, qapp):
        bar, _ed = _bar("Bir bir BIR\n", "bir")
        bar._count_matches("bir")
        assert bar._match_count == 3

    def test_eslesme_yok(self, qapp):
        bar, _ed = _bar("merhaba\n", "yok")
        bar._count_matches("yok")
        assert bar._match_count == 0
        assert "Sonuç yok" in bar._lbl_count.text()

    def test_bos_arama_temizler(self, qapp):
        bar, _ed = _bar("merhaba\n")
        bar._count_matches("")
        assert bar._match_count == 0
        assert bar._lbl_count.text() == ""


# --- Tümünü değiştir ---

class TestTumunuDegistir:
    def test_hepsi_degisiyor_ve_sayi_dogru(self, qapp):
        bar, ed = _bar("bir iki bir uc bir\n", "bir", "DORT")
        bar._replace_all()
        assert ed.text() == "DORT iki DORT uc DORT\n"
        assert "3" in bar._lbl_count.text()

    def test_tek_geri_al_hepsini_geri_aliyor(self, qapp):
        """beginUndoAction/endUndoAction: tek Ctrl+Z tüm işlemi geri almalı."""
        orijinal = "bir iki bir uc bir\n"
        bar, ed = _bar(orijinal, "bir", "DORT")
        bar._replace_all()
        assert "DORT" in ed.text()
        ed.undo()
        assert ed.text() == orijinal

    def test_buyuk_kucuk_harf_duyarsiz_degistirme(self, qapp):
        bar, ed = _bar("Bir bir BIR\n", "bir", "X")
        bar._replace_all()
        assert ed.text() == "X X X\n"

    def test_eslesme_yoksa_belge_degismiyor(self, qapp):
        bar, ed = _bar("merhaba dunya\n", "yok", "X")
        bar._replace_all()
        assert ed.text() == "merhaba dunya\n"
        assert "0" in bar._lbl_count.text()

    def test_bos_arama_hicbir_sey_yapmiyor(self, qapp):
        bar, ed = _bar("merhaba\n", "", "X")
        bar._replace_all()
        assert ed.text() == "merhaba\n"

    def test_degistirme_metni_aramayi_iceriyor(self, qapp):
        """'a' -> 'aa' sonsuz döngüye girmemeli (imleç her adımda ilerler)."""
        bar, ed = _bar("a b a\n", "a", "aa")
        bar._replace_all()
        assert ed.text() == "aa b aa\n"


# --- Güvenlik sınırı: SESSİZ KESME OLMAMALI ---

class TestDegistirmeSiniri:
    def test_sinira_ulasinca_kullanici_uyariliyor(self, qapp, monkeypatch):
        bar, ed = _bar("", "HEDEF", "YENI")
        monkeypatch.setattr(FindReplaceBar, "_REPLACE_LIMIT", 5)
        ed.setText("\n".join(f"satir{i} HEDEF" for i in range(12)))

        uyarilar = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **k: uyarilar.append(a))

        bar._replace_all()

        assert uyarilar, "sınıra ulaşıldı ama kullanıcı uyarılmadı"
        metin = " ".join(str(x) for x in uyarilar[0])
        assert "5" in metin, "uyarı kaç değişiklik yapıldığını söylemiyor"
        # Belge gerçekten yarım: sınır kadarı değişti, gerisi durutuyor
        assert ed.text().count("YENI") == 5
        assert ed.text().count("HEDEF") == 7

    def test_sinir_asilmayinca_uyari_yok(self, qapp, monkeypatch):
        bar, ed = _bar("bir HEDEF iki HEDEF\n", "HEDEF", "YENI")
        monkeypatch.setattr(FindReplaceBar, "_REPLACE_LIMIT", 5)
        uyarilar = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **k: uyarilar.append(a))
        bar._replace_all()
        assert not uyarilar, "sınır aşılmadığı hâlde uyarı çıktı"
        assert ed.text().count("YENI") == 2

    def test_sinir_tam_degerinde_kesiliyor(self, qapp, monkeypatch):
        """Sınır 'tam N' olmalı; eskiden 'count > N' ile N+1 tane işliyordu."""
        bar, ed = _bar("", "X", "Y")
        monkeypatch.setattr(FindReplaceBar, "_REPLACE_LIMIT", 3)
        ed.setText("X X X X X\n")
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
        bar._replace_all()
        assert ed.text().count("Y") == 3, ed.text()


# --- Tek tek değiştir ---

class TestDegistirNext:
    def test_ilk_eslesmeyi_degistiriyor(self, qapp):
        bar, ed = _bar("bir iki bir\n", "bir", "X")
        ed.setCursorPosition(0, 0)
        bar._replace_next()
        assert ed.text().count("X") == 1
        assert ed.text().count("bir") == 1

    def test_pesi_sira_cagri_hepsini_bitiriyor(self, qapp):
        bar, ed = _bar("bir iki bir\n", "bir", "X")
        ed.setCursorPosition(0, 0)
        bar._replace_next()
        bar._replace_next()
        assert ed.text() == "X iki X\n"
