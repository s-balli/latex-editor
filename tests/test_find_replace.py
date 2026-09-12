"""FindReplaceBar testleri — bul, say, değiştir, tümünü değiştir.

254 satırlık bu modülün HİÇ testi yoktu (2026-08-30 denetimi, D5) — üstelik
yıkıcı bir yol: "Tümünü Değiştir" tüm belgeyi tek geri-al adımında
değiştiriyor ve güvenlik sınırına ulaşınca eskiden SESSİZCE kesiyordu.
Deneyle üretilmişti: 12.000 eşleşmeli belgede 10.001 değiştirilip 1.999'u
dokunulmadan kalıyor, etiket yine sayı yazıyor, hiçbir uyarı çıkmıyordu.
"""

import os

import pytest

try:
    from PyQt6.QtWidgets import (
        QApplication, QMessageBox, QWidget, QVBoxLayout,
    )
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


# --- ARAMA SEÇENEKLERİ (harf duyarlılığı / tam kelime / düzenli ifade) ---
#
# Bu üç bayrak `findFirst(text, False, False, False, ...)` diye SABİT
# geçiliyordu: altyapı hazırdı ama hiçbir arayüzü yoktu. LaTeX'te harf durumu
# anlamlı (\Section != \section, etiket anahtarları) ve "fig" araması
# "figure" içinde de eşleşiyordu.


def _sec(bar, *, case=False, word=False, regex=False):
    """Kutuları AYARLA: sinyal yolu dahil (setChecked toggled'ı tetikler)."""
    bar._cb_case.setChecked(case)
    bar._cb_regex.setChecked(regex)
    bar._cb_word.setChecked(word)
    return bar


class TestHarfDuyarliligi:
    def test_duyarsiz_hepsini_buluyor(self, qapp):
        bar, _ed = _bar("fig FIG Fig\n", "fig")
        _sec(bar, case=False)
        bar._count_matches("fig")
        assert bar._match_count == 3

    def test_duyarli_yalniz_birebir(self, qapp):
        bar, _ed = _bar("fig FIG Fig\n", "fig")
        _sec(bar, case=True)
        bar._count_matches("fig")
        assert bar._match_count == 1

    def test_latex_komutu_ayirt_ediliyor(self, qapp):
        r"""\Section ile \section duyarlı kipte ayrı sayılmalı."""
        bar, _ed = _bar("\\section{a}\n\\Section{b}\n\\section{c}\n", "\\section")
        _sec(bar, case=True)
        bar._count_matches("\\section")
        assert bar._match_count == 2

    def test_degistirme_de_duyarli(self, qapp):
        bar, ed = _bar("fig FIG Fig\n", "fig", "X")
        _sec(bar, case=True)
        bar._replace_all()
        assert ed.text() == "X FIG Fig\n"

    def test_turkce_s_harfi(self, qapp):
        bar, _ed = _bar("Şekil şekil ŞEKİL\n", "şekil")
        _sec(bar, case=True)
        bar._count_matches("şekil")
        assert bar._match_count == 1

    def test_DUYARSIZ_kip_TURKCE_harfleri_de_katlar(self, qapp):
        """Duyarsız kip Türkçe harfler için DUYARLI davranıyordu.

        Scintilla'nın harf duyarsız araması yalnız ASCII'yi katlıyor. Belge
        UTF-8 (kod sayfası 65001 ölçüldü) ama Türkçe harfler çok baytlı, o
        yüzden hiç katlanmıyorlardı. Kutunun ipucu tam tersini söylüyor:
        "İşaretliyse 'Şekil' ile 'şekil' ayrı sayılır".

        ÖLÇÜLDÜ (2026-09-10), ASCII dışı harf içeren 83 gerçek şablon
        dosyasında 12 gerçekçi sorgu: 2286 eşleşmenin 2061'i bulunuyordu,
        225'i kaçıyordu (%9.8). En kötüsü `örnek`: 126'nın 29'u, çünkü
        Türkçe başlıklar büyük harfle başlıyor (`Örnek`).

        ÜÇ YOL da aynı eksikle çalışıyordu ve üçü de burada sınanıyor.
        En kötüsü sonuncusu: "Tümünü Değiştir" belgeyi YARIM değiştirip
        etiket "1 değişiklik" diyordu, yani sessiz bozulma.
        """
        metin = "Şekil şekil ŞEKİL\n"
        # 1) sayaç
        bar, _ed = _bar(metin, "şekil")
        _sec(bar, case=False)
        bar._count_matches("şekil")
        assert bar._match_count == 3
        # 2) gezinme: üç AYRI yere gitmeli (imleç eşleşmenin sonunda kalır)
        bar, ed = _bar(metin, "şekil")
        _sec(bar, case=False)
        yerler = []
        ed.setCursorPosition(0, 0)
        while len(yerler) < 5:
            satir, sutun = ed.getCursorPosition()
            if not bar._find_first("şekil", wrap=False, forward=True,
                                   line=satir, col=sutun):
                break
            yerler.append(ed.getSelection()[:2])
            ed.setCursorPosition(*ed.getSelection()[2:])
        assert yerler == [(0, 0), (0, 6), (0, 12)]
        # 3) tümünü değiştir: HEPSİ değişmeli
        bar, ed = _bar(metin, "şekil", "GORSEL")
        _sec(bar, case=False)
        bar._replace_all()
        assert ed.text() == "GORSEL GORSEL GORSEL\n"
        assert "3" in bar._lbl_count.text()



class TestTamKelime:
    def test_kapaliyken_ic_ice_eslesiyor(self, qapp):
        bar, _ed = _bar("fig figure figs\n", "fig")
        _sec(bar, word=False)
        bar._count_matches("fig")
        assert bar._match_count == 3

    def test_acikken_yalniz_tam_kelime(self, qapp):
        bar, _ed = _bar("fig figure figs\n", "fig")
        _sec(bar, word=True)
        bar._count_matches("fig")
        assert bar._match_count == 1

    def test_degistirme_de_tam_kelime(self, qapp):
        bar, ed = _bar("fig figure fig\n", "fig", "X")
        _sec(bar, word=True)
        bar._replace_all()
        assert ed.text() == "X figure X\n"

    def test_duyarlilikla_birlikte(self, qapp):
        bar, _ed = _bar("fig FIG figure\n", "fig")
        _sec(bar, word=True, case=True)
        bar._count_matches("fig")
        assert bar._match_count == 1


class TestDuzenliIfade:
    def test_karakter_kumesi(self, qapp):
        bar, _ed = _bar("a1 b2 c3 dd\n", "[a-z][0-9]")
        _sec(bar, regex=True)
        bar._count_matches("[a-z][0-9]")
        assert bar._match_count == 3

    def test_almasik_calisiyor(self, qapp):
        r"""`|` ALMASIK olmalı, düz karakter değil.

        Scintilla'nın ÖNTANIMLI lehçesinde `|` düz karakter ve `(` grup
        açmıyor; `\section|\subsection` sessizce sıfır sonuç veriyordu. Bu
        yüzden findFirst'e cxx11=True geçiliyor. Bayrak düşerse bu test 0
        bulur.
        """
        bar, _ed = _bar("\\section{a}\n\\subsection{b}\n\\paragraph{c}\n",
                        "section|subsection")
        _sec(bar, regex=True)
        bar._count_matches("section|subsection")
        assert bar._match_count == 2

    def test_grup_parantezi_grup(self, qapp):
        """`(...)` grup olmalı, düz parantez değil (yine cxx11 kanıtı)."""
        bar, _ed = _bar("fig1 fig2 sehir3\n", "(fig|sehir)[0-9]")
        _sec(bar, regex=True)
        bar._count_matches("(fig|sehir)[0-9]")
        assert bar._match_count == 3

    def test_geri_referans_ile_degistirme(self, qapp):
        r"""\1 yakalanan gruba karşılık gelmeli.

        `replaceSelectedText` geri referansı DÜZ METİN yazıyor; bu yüzden
        `replace` kullanılıyor. Geri dönerse belgeye harfi harfine "kare\1"
        yazılır ve bu test yakalar.
        """
        bar, ed = _bar("fig1 fig2 fig3\n", "fig([0-9])", "kare\\1")
        _sec(bar, regex=True)
        bar._replace_all()
        assert ed.text() == "kare1 kare2 kare3\n"

    def test_geri_referans_tek_tek_degistirmede_de(self, qapp):
        """Aynı kural _replace_next için de geçerli (iki ayrı çağrı yeri)."""
        bar, ed = _bar("fig1 fig2\n", "fig([0-9])", "kare\\1")
        _sec(bar, regex=True)
        ed.setCursorPosition(0, 0)
        bar._replace_next()
        assert ed.text().startswith("kare1"), ed.text()

    def test_duz_kipte_geri_referans_harfi_harfine(self, qapp):
        """Desen kipi KAPALIYKEN \\1 çözülmemeli."""
        bar, ed = _bar("aa bb\n", "aa", "X\\1Y")
        _sec(bar, regex=False)
        bar._replace_all()
        assert ed.text() == "X\\1Y bb\n"

    def test_desen_kipi_kapaliyken_ozel_karakter_duz(self, qapp):
        """Kutu işaretsizken `a.c` düz metin; 'abc' ile eşleşmemeli."""
        bar, _ed = _bar("abc a.c\n", "a.c")
        _sec(bar, regex=False)
        bar._count_matches("a.c")
        assert bar._match_count == 1

    def test_tam_kelime_kutusu_desen_kipinde_kapali(self, qapp):
        """Scintilla desen kipinde tam-kelime bayrağını yok sayıyor.

        Etkisiz kutuyu tıklanabilir bırakmak kullanıcıya yalan söylemek olur.
        """
        bar, _ed = _bar("fig figure\n", "fig")
        _sec(bar, regex=True)
        assert not bar._cb_word.isEnabled()
        _sec(bar, regex=False)
        assert bar._cb_word.isEnabled()

    def test_bozuk_desen_soyleniyor(self, qapp):
        """Bozuk desen 'Sonuç yok' değil, nedenini söylemeli."""
        bar, _ed = _bar("merhaba dunya\n", "[")
        _sec(bar, regex=True)
        bar._find_input.setText("[")
        bar._do_find()
        assert bar._gecersiz_desen
        assert "Geçersiz" in bar._lbl_count.text()

    def test_eslesen_desen_asla_gecersiz_denmiyor(self, qapp):
        """Eşleşme varsa Python'ın `re`si ne derse desin desen geçerlidir."""
        bar, _ed = _bar("fig1 fig2\n", "fig[0-9]")
        _sec(bar, regex=True)
        bar._find_input.setText("fig[0-9]")
        bar._do_find()
        assert not bar._gecersiz_desen
        assert "Geçersiz" not in bar._lbl_count.text()

    def test_duz_kipte_bozuk_desen_uyarisi_yok(self, qapp):
        """Kutu kapalıyken `[` düz metindir; 'geçersiz' demek yanlış olur."""
        bar, ed = _bar("a [ b\n", "[")
        _sec(bar, regex=False)
        bar._find_input.setText("[")
        bar._do_find()
        assert not bar._gecersiz_desen
        assert ed.hasSelectedText()

    def test_sifir_genislikli_desen_belgeyi_bozmuyor(self, qapp):
        """`x*` her konumda eşleşir; tümünü değiştir askıda kalmamalı."""
        bar, ed = _bar("abc\n", "x*", "-")
        _sec(bar, regex=True)
        bar._replace_all()
        assert ed.text() == "abc\n"


class TestSayacAramaylaAyniKurali:
    """Sayaç ile aramanın AYRIŞMAMASI.

    Sayaç eskiden `editor.text().lower().count(...)` ile ayrı bir yoldan
    geçiyordu: seçeneklerden habersizdi. Duyarlı kipte etiket "3 sonuç" derken
    ileri tuşu tek eşleşme bulurdu.
    """

    def test_duyarli_kipte_sayac_aramayla_uyusuyor(self, qapp):
        bar, ed = _bar("fig FIG Fig fig\n", "fig")
        _sec(bar, case=True)
        bar._count_matches("fig")

        ed.setCursorPosition(0, 0)
        elle = 0
        while bar._find_first("fig", wrap=False) and ed.hasSelectedText():
            elle += 1
            if elle > 20:
                break
        assert bar._match_count == elle == 2

    def test_tam_kelime_kipinde_sayac_uyusuyor(self, qapp):
        bar, ed = _bar("fig figure fig figs\n", "fig")
        _sec(bar, word=True)
        bar._count_matches("fig")
        ed.setCursorPosition(0, 0)
        elle = 0
        while bar._find_first("fig", wrap=False) and ed.hasSelectedText():
            elle += 1
            if elle > 20:
                break
        assert bar._match_count == elle == 2

    def test_sayac_imleci_oynatmiyor(self, qapp):
        """Yazarken belge yerinde durmalı: sayım seçimi/imleci bozmamalı."""
        bar, ed = _bar("bir iki bir uc bir\n", "bir")
        ed.setCursorPosition(0, 12)
        once = ed.getCursorPosition()
        bar._count_matches("bir")
        assert ed.getCursorPosition() == once
        assert not ed.hasSelectedText()

    def test_sayim_siniri_sessiz_kesmiyor(self, qapp, monkeypatch):
        monkeypatch.setattr(FindReplaceBar, "_COUNT_LIMIT", 5)
        bar, _ed = _bar("a " * 40 + "\n", "a")
        bar._count_matches("a")
        assert bar._match_count == 5
        assert bar._sayim_kesildi
        assert "+" in bar._lbl_count.text()


class TestCubukBolmeyeSigiyor:
    """Çubuğun parçaları GÖRÜNÜR alanın içinde kalmalı.

    Tek satırdayken parçalar sabit genişlikliydi (250 px kutular) ve
    daralamıyordu; fazlası bölmenin sağına taşıp görünmez oluyordu. Bölme
    genişliğine göre ölçüldü:

        1000 px -> tamam
         900 px -> "Tümünü Değiştir" kesiliyor
         600 px -> "Değiştir" kutusu da kesiliyor

    KULLANICI BİLDİRDİ (2026-09-01): "Ctrl+H'e basınca bir şey olmuyor."
    Aslında oluyordu, sadece görünmüyordu. Üç satıra ayrıldı (bul /
    değiştir / seçenekler) ve kutular esneyebilir yapıldı.
    """

    _DAR_BOLME = 700   # üç bölmeli düzende gerçekçi bir editör genişliği

    @staticmethod
    def _yerlesik_cubuk(genislik: int, kip: str):
        """Çubuğu gerçek bir kapsayıcıya koyup verilen genişliğe yerleştir.

        Yerleştirme yapılmazsa tüm geometriler 0 kalır ve aşağıdaki
        karşılaştırmalar boşa döner.
        """
        kap = QWidget()
        kap.resize(genislik, 300)
        lay = QVBoxLayout(kap)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = FindReplaceBar()
        bar.set_editor(QsciScintilla())
        lay.addWidget(bar)
        lay.addStretch()
        kap.show()
        getattr(bar, kip)()
        QApplication.processEvents()
        kap.resize(genislik, 300)
        QApplication.processEvents()
        return kap, bar

    def test_dar_bolmede_degistir_alani_gorunuyor(self, qapp):
        kap, bar = self._yerlesik_cubuk(self._DAR_BOLME, "show_replace")
        try:
            assert bar._replace_input.width() > 0, "yerleşim koşmadı, kapı boş"
            for w, ad in ((bar._replace_input, "değiştir kutusu"),
                          (bar._btn_replace, "Değiştir düğmesi"),
                          (bar._btn_replace_all, "Tümünü Değiştir")):
                assert w.geometry().right() <= self._DAR_BOLME, (
                    f"{ad} görünür alanın dışında: sağ kenar "
                    f"{w.geometry().right()} > {self._DAR_BOLME}")
        finally:
            kap.close()

    def test_dar_bolmede_bul_alani_gorunuyor(self, qapp):
        kap, bar = self._yerlesik_cubuk(self._DAR_BOLME, "show_find")
        try:
            assert bar._find_input.width() > 0, "yerleşim koşmadı, kapı boş"
            assert bar._find_input.geometry().right() <= self._DAR_BOLME
            assert bar._btn_close.geometry().right() <= self._DAR_BOLME
        finally:
            kap.close()

    def test_degistir_satiri_bul_kipinde_gizli(self, qapp):
        bar = FindReplaceBar()
        bar.show_find()
        assert bar._replace_input.isHidden()
        bar.show_replace()
        assert not bar._replace_input.isHidden()

    def test_secenekler_iki_kipte_de_gorunur(self, qapp):
        """Seçenekler üçüncü satırda: Ctrl+F'te de Ctrl+H'de de görünmeli."""
        bar = FindReplaceBar()
        for goster in (bar.show_find, bar.show_replace):
            goster()
            for cb in (bar._cb_case, bar._cb_word, bar._cb_regex):
                assert not cb.isHidden(), (goster.__name__, cb.text())


class TestSeceneklerAramayiTazeliyor:
    def test_kutu_degisince_sayac_guncelleniyor(self, qapp):
        """Kutuyu işaretleyince ekranda bir şey değişmeli."""
        bar, _ed = _bar("fig FIG Fig\n", "fig")
        bar._find_input.setText("fig")
        bar._do_find()
        bar._count_matches("fig")
        assert bar._match_count == 3

        bar._cb_case.setChecked(True)      # toggled -> _on_option_toggled
        bar._count_matches("fig")
        assert bar._match_count == 1


# =====================================================================
# Derin iç içe grup: motoru öldüren desen
# =====================================================================

def test_derin_ic_ice_grup_reddediliyor():
    """Scintilla'nın std::regex'i derin özyinelemede YIĞIN TAŞIRIYOR.

    Ölçüldü (2026-09-02): 100 kat iç içe yakalayan grup sorunsuz, 150 kat
    süreci 0xC0000005 ile öldürüyor. Python istisnası değil — try/except
    yakalayamıyor, uygulama kapanıyor ve kaydedilmemiş her şey gidiyor.
    """
    from gui.find_replace import _desen_guvenli

    assert _desen_guvenli("(" * 50 + "a" + ")" * 50)
    assert not _desen_guvenli("(" * 51 + "a" + ")" * 51)
    assert not _desen_guvenli("(a|" * 150 + "b" + ")" * 150)
    # Karakter sınıfı KAPANDIKTAN sonraki gruplar yine sayılmalı; sınıf
    # atlaması kapanışı gözden kaçırırsa tehlikeli desen güvenli sayılır.
    assert not _desen_guvenli("[abc]" + "(" * 60 + "a" + ")" * 60)


def test_gundelik_desenler_guvenli_sayiliyor():
    """Sınır gerçek aramaları engellememeli."""
    from gui.find_replace import _desen_guvenli

    for desen in (r"\\section",
                  r"\\(sub)?section\{(.*)\}",
                  r"(a|b|c)+",
                  "(" * 20 + "x" + ")" * 20,
                  # Sınırın ÜSTÜNDE sayıda parantez, ama sınıfın içinde: grup
                  # açmıyorlar. Sınıf atlaması bozulursa bu desen "güvensiz"
                  # sayılır ve test düşer.
                  "[" + "(" * 60 + "]",
                  # Aynısı kaçırılmış parantezle.
                  "\\(" * 60):
        assert _desen_guvenli(desen), desen


def test_derin_desen_arama_yolunu_tetiklemiyor(qapp, tmp_path):
    """Guard hem _find_first hem _say yolunda olmalı: ikisi de motoru çağırıyor."""
    from gui.find_replace import FindReplaceBar
    from gui.editor import EditorWidget

    ed = EditorWidget()
    ed.setText("(((a)))\n")
    bar = FindReplaceBar()
    bar.set_editor(ed)
    bar._cb_regex.setChecked(True)

    kotu = "(" * 200 + "a" + ")" * 200
    assert bar._find_first(kotu, wrap=True) is False
    assert bar._say(kotu) == (0, False)

    bar._find_input.setText(kotu)
    bar._do_find()
    assert bar._gecersiz_desen is True


# --- İç içe sınırsız nicelik: üstel geri izleme ---


@pytest.mark.parametrize("desen", [
    # Sınırsız iç nicelik
    r"(a+)+$",
    r"(a*)*b",
    r"(x+x+)+y",
    r"(a+)+b",
    r"(\w+)*x",
    r"([a-z]+)+$",
    r"(a{1,})+",
    r"(a+a+)+",
    r"(a+){2,}",
    r"((a+)*)+",
    r"(\w+\s*)+x",
    # SINIRLI iç nicelik: ilk kapı bunları kaçırıyordu, aynı üstel sınıf ve
    # daha hızlı büyüyor. Ölçüldü (2026-09-02, dış doğrulama 3. tur, Linux):
    # `(a?a?)+b` eşleşmeyen metinde 10 karakter 2.47 sn, 12 karakter 45 sn'de
    # DÖNMEDİ. Sınırsız `(a+)+$` 30 karakterde donuyordu; bu aile 12'de.
    r"(a?a?)+b",
    r"(a{1,3})+b",
    r"((a)?)+",
    r"(\w?\s?)+",
    r"(?:a+)+",
    r"(?:a?a?)+",
])
def test_ic_ice_nicelik_reddediliyor(desen):
    """`(a+)+` biçimi arayüzü KALICI dondurabiliyor.

    Ölçüldü (2026-09-02), `(a+)+$` ile eşleşmeyen metinde:

        Windows (MSVC STL)   20 kr 4.98 sn, 30 kr 2.85 sn, 40 kr 3.38 sn
        Linux  (libstdc++)   20 kr 0.25 sn, 25 kr 7.45 sn, 30 kr 90+ sn DÖNMEDİ

    Windows'ta std::regex'in karmaşıklık sınırı devreye girip vazgeçtiği için
    süre girdiyle artmıyor; Linux/AppImage'de temiz üstel artış var ve
    kullanıcı uygulamayı zorla kapatmak zorunda kalıyor. Bu fark ilk ölçümde
    kaçmıştı: yalnız Windows'a bakıp "3-4 sn, rahatsızlık" denmişti.

    std::regex'e zaman aşımı takılamıyor, bu yüzden çözüm deseni ÖNCEDEN
    elemek.
    """
    from gui.find_replace import _desen_guvenli

    assert not _desen_guvenli(desen), desen


@pytest.mark.parametrize("desen", [
    r"\\section",
    r"\\(sub)?section\{(.*)\}",
    r"(a|b|c)+",
    r"[()]{3,}",
    r"(foo)+",
    r"(\w+)\s*=\s*(\d+)",
    r"\\begin\{(figure|table)\}",
    r"(.*)",
    r"a+b+",
    r"\\cite\{([^}]+)\}",
    r"(\d{4})",
    r"\d{1,3}\.",
    # Süslü parantez LaTeX'te çok yaygın; içeriği sayı değilse nicelik değil
    r"\\begin\{figure\}(.*)\\end\{figure\}",
    # NİCELENMİŞ grubun gövdesinde KAÇIRILMAMIŞ `{...}`: içeriği sayı
    # olmadığı için nicelik sayılmamalı. Kullanıcı LaTeX ararken süslüyü
    # kaçırmayı sık unutuyor, o zaman `{x}` düz karakter oluyor.
    r"(\\section{x})+",
    r"(\\begin{itemize})+",
    r"(\\item\{ad\})+",
    # Sınıf içindeki ve kaçırılmış nicelik karakteri sayılmamalı
    r"(a[+])+b",
    r"(a\+)+b",
    # `?` ile nicelenmiş DIŞ grup patlamıyor
    r"(x|y)?z",
    # Grup türü belirteçlerindeki `?` nicelik değil
    r"(?:ab)+",
    r"(?:a|b)+",
    r"(?=foo)bar",
    r"(?P<ad>x)+",
    r"((?:ab))+",
])
def test_gercek_aramalar_kapiya_takilmiyor(desen):
    """Kapı gündelik LaTeX aramalarını engellememeli.

    Yanlış alarm burada gerçek bir bedel: kullanıcı çalışan bir deseni
    "geçersiz" görür ve neden olduğunu anlamaz.
    """
    from gui.find_replace import _desen_guvenli

    assert _desen_guvenli(desen), desen


def _sureli(fn, sinir=10.0):
    """fn'i ayrı iş parçacığında koş; sürede dönmezse testi düşür.

    Kapı kaldırılırsa arama Linux'ta 90+ saniye dönmüyor ve test ASILIYOR.
    CI'da asılma, düşmekten kötü: zaman sınırıyla düşürülüyor. Kaçan iş
    parçacığı daemon; süreç çıkışını engellemiyor.
    """
    import threading

    kutu = {}

    def kos():
        try:
            kutu["deger"] = fn()
        except Exception as e:            # pragma: no cover
            kutu["hata"] = e

    t = threading.Thread(target=kos, daemon=True)
    t.start()
    t.join(sinir)
    if t.is_alive():
        pytest.fail("arama %.0f sn içinde dönmedi (desen kapısı çalışmıyor)" % sinir)
    if "hata" in kutu:
        raise kutu["hata"]
    return kutu["deger"]


def test_kapi_arama_yollarinda_da_gecerli(qapp):
    """Koruma üç yolda birden olmalı: _find_first, _say, _do_find."""
    from gui.find_replace import FindReplaceBar
    from gui.editor import EditorWidget

    ed = EditorWidget()
    ed.setText("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa!\n")
    bar = FindReplaceBar()
    bar.set_editor(ed)
    bar._cb_regex.setChecked(True)

    kotu = r"(a+)+$"
    assert _sureli(lambda: bar._find_first(kotu, wrap=True)) is False
    assert _sureli(lambda: bar._say(kotu)) == (0, False)

    bar._find_input.setText(kotu)
    _sureli(bar._do_find)
    assert bar._gecersiz_desen is True


def test_kapi_capali_desenlerde_muhafazakar():
    r"""Gövdesi düz metinle BAŞLAYAN desenler de reddediliyor: bilinen ve kabul
    edilmiş fazla-reddetme.

    `(\ref\{[a-z]+\})+` gerçekte patlamıyor; her tekrar `\ref{` ile
    çapalandığı için bölünme tekil. Yine de reddediliyor, çünkü "çapa
    ambigüiteyi tekilleştiriyor mu" sorusunu doğru cevaplamak bu kapının işi
    değil ve yanlış cevap kullanıcıyı DONDURUR. Fazladan reddetmenin bedeli
    açık bir uyarı, eksik reddetmenin bedeli zorla kapatma.

    Test davranışı SABİTLİYOR: ileride kasıtlı olarak gevşetilirse burada
    görünsün (dış doğrulama, 2026-09-02).
    """
    from gui.find_replace import _desen_guvenli

    assert not _desen_guvenli(r"(\ref\{[a-z]+\})+")
    assert not _desen_guvenli(r"(fig\{[0-9]+\})+")


# --- ARAMA ÇAPASI: aramanın NEREDEN başladığı ---
#
# findFirst eşleşmeyi seçiyor ve imleci onun SONUNA bırakıyor. Aramayı
# imleçten başlatmak, o anda VURGULU olan eşleşmeyi atlıyordu.
#
# Bu üç kusur da o tek kök nedenden çıktı ve mevcut 52 test hiçbirini
# görmüyordu, çünkü hepsi arayüzün HİÇ girmediği bir başlangıç durumundan
# kuruluyor: `setCursorPosition(0, 0)` ile imleci elle başa alıyor ve arama
# kutusunu `setText("bir")` ile TEK SEFERDE dolduruyorlar. Kullanıcı ise
# harf harf yazıyor ve imleci elle oynatmıyor.

_SATIR = "bir iki bir uc bir"          # eşleşmeler: sütun 0, 8, 15


def _yaz(bar, s):
    """Arama kutusuna HARF HARF yaz (gerçek kullanıcı yolu)."""
    for i in range(1, len(s) + 1):
        bar._find_input.setText(s[:i])


class TestAramaCapasi:
    def test_yazarken_vurgu_belgede_yurumuyor(self, qapp):
        """Harf harf yazmak vurguyu bir sonraki eşleşmeye İTMEMELİ.

        Her tuş vuruşu `_do_find` çağırıyor; arama imleçten başlayınca
        imleç de bir önceki (daha kısa) eşleşmenin sonunda olduğu için
        vurgu belgede ileri yürüyordu: 'bir' yazınca ilk 'bir' değil
        üçüncüsü seçiliyordu (ölçüldü).
        """
        metin = ("\\section{Giris}\n"
                 "Burada bir sekil var.\n"
                 "Ikinci bir paragraf.\n"
                 "Ucuncu bir cumle.\n")
        bar, ed = _bar(metin)
        bar.show_find()
        _yaz(bar, "bir")
        assert ed.getSelection()[0] == 1, "vurgu ilk eşleşmeyi aştı"

    def test_degistir_VURGULANAN_eslesmeyi_degistiriyor(self, qapp):
        """"Değiştir" kullanıcının GÖRDÜĞÜ eşleşmeyi değiştirmeli.

        Konumdan bağımsız sınanıyor: beklenen metin, panelin o an
        vurguladığı aralıktan TÜRETİLİYOR. Sabit bir dizge beklemek
        yanıltıcı olurdu, çünkü vurgunun nerede durduğu da düzeltmenin
        parçası.
        """
        bar, ed = _bar(_SATIR + "\n", "bir", "X")
        bar.show_replace()
        sec = ed.getSelection()
        beklenen = _SATIR[:sec[1]] + "X" + _SATIR[sec[3]:]
        bar._replace_next()
        assert ed.text().strip() == beklenen

    def test_gezindikten_sonra_da_vurgulanan_degisiyor(self, qapp):
        """İleri tuşuyla gezindikten sonra da geçerli.

        Kullanıcı son eşleşmeye gidip "Değiştir"e bastığında EN BAŞTAKİ
        değişiyordu: değişiklik ekranda görünmeyen bir yerde oluyordu.
        """
        bar, ed = _bar(_SATIR + "\n", "bir", "X")
        bar.show_replace()
        bar._find_next()
        bar._find_next()
        sec = ed.getSelection()
        assert sec[1] == 15, "iki ileri SON eşleşmeye götürmeliydi"
        bar._replace_next()
        assert ed.text().strip() == "bir iki bir uc X"

    def test_geri_tusu_geriye_dolasiyor(self, qapp):
        """"<" düğmesi hiç kıpırdamıyordu.

        Geriye arama da imleçten başlıyordu; imleç eşleşmenin SONUNDA
        olduğu için geriye arama hep AYNI eşleşmeyi buluyordu. Dört
        basışta da aynı sütun ölçüldü.
        """
        bar, ed = _bar(_SATIR + "\n", "bir")
        bar.show_find()
        sutunlar = []
        for _ in range(3):
            bar._find_prev()
            sutunlar.append(ed.getSelection()[1])
        assert sutunlar == [15, 8, 0]

    def test_ileri_tusu_hala_ilerliyor(self, qapp):
        """Çapa ileri tuşunu BAĞLAMAMALI: onun işi zaten ilerlemek.

        İleri tuşu da seçimin başından arasaydı aynı eşleşmede sayardı.
        """
        bar, ed = _bar(_SATIR + "\n", "bir")
        bar.show_find()
        sutunlar = [ed.getSelection()[1]]
        for _ in range(3):
            bar._find_next()
            sutunlar.append(ed.getSelection()[1])
        assert sutunlar == [0, 8, 15, 0], "başa sarma dahil sırayla gezmeli"

    def test_secim_yokken_imlecten_ariyor(self, qapp):
        """Seçim yoksa eski yol (imleç) korunuyor."""
        bar, ed = _bar("bir iki bir\n", "bir", "X")
        ed.setCursorPosition(0, 0)
        bar._replace_next()
        assert ed.text().strip() == "X iki bir"

    def test_alakasiz_secimde_sonraki_eslesme(self, qapp):
        """Kullanıcının editördeki seçimi eşleşme değilse ondan sonrakine gider."""
        bar, ed = _bar("kirmizi bir mavi bir\n", "bir", "X")
        ed.setSelection(0, 0, 0, 7)          # 'kirmizi' seçili, eşleşme değil
        bar._replace_next()
        assert ed.text().strip() == "kirmizi X mavi bir"


# --- Güvenlik kapısının reddettiği desende "Tümünü Değiştir" ---


class TestReddedilenDesendeDegistir:
    def test_red_bilgisi_kayboluyordu(self, qapp):
        r"""Kapı deseni reddedince etiket "0 değişiklik" diyordu.

        Bul paneli aynı desen için "Geçersiz desen" diyor, "Tümünü
        Değiştir" bunu eziyordu: kullanıcı belgede eşleşme olmadığını
        sanıyor, oysa arama hiç yapılmamış.
        """
        belge = "\\ref{sek:bir} aaaa\n"
        bar, ed = _bar(belge, "", "Z")
        bar._cb_regex.setChecked(True)
        bar._find_input.setText(r"(a+)+")
        bar.show_replace()
        assert bar._lbl_count.text() == "Geçersiz desen"

        bar._replace_all()
        assert bar._lbl_count.text() == "Geçersiz desen", "red bilgisi kayboldu"
        assert ed.text() == belge, "reddedilen desende belge değişmemeli"

    def test_kapinin_muhafazakar_reddettigi_desende_de(self, qapp):
        r"""Dosyanın kendi "fazla-reddetme" örneği de sessiz kalmamalı.

        `(\ref\{[a-z]+\})+` gerçekte patlamıyor ama kapı yine reddediyor;
        bedeli AÇIK BİR UYARI olarak tarif edilmiş, bu yolda uyarı yoktu.
        """
        belge = "\\ref{sek:bir}\\ref{sek:iki}\n"
        bar, ed = _bar(belge, "", "Z")
        bar._cb_regex.setChecked(True)
        bar._find_input.setText(r"(\\ref\{[a-z]+\})+")
        bar._replace_all()
        assert bar._lbl_count.text() == "Geçersiz desen"
        assert ed.text() == belge

    def test_guvenli_desen_etkilenmedi(self, qapp):
        """Karşı durum: geçerli desende değiştirme ve sayı olduğu gibi."""
        bar, ed = _bar("sekil1 sekil2\n", "", "Z")
        bar._cb_regex.setChecked(True)
        bar._find_input.setText(r"sekil(\d)")
        bar._replace_all()
        assert ed.text() == "Z Z\n"
        assert bar._lbl_count.text() == "2 değişiklik"

    def test_duz_kipte_kapi_devrede_degil(self, qapp):
        """Düz kipte aynı metin desen değil, düz karakter dizisi."""
        bar, ed = _bar("(a+)+ var\n", "(a+)+", "Z")
        bar._replace_all()
        assert ed.text() == "Z var\n"

    def test_eslesmesiz_guvenli_desen_hala_sifir_diyor(self, qapp):
        """"0 değişiklik" mesajı GERÇEKTEN eşleşme yokken korunmalı."""
        bar, ed = _bar("abc\n", "", "Z")
        bar._cb_regex.setChecked(True)
        bar._find_input.setText(r"zzz(\d)")
        bar._replace_all()
        assert bar._lbl_count.text() == "0 değişiklik"


# =====================================================================
# Sekme değişince sayaç YENİ belgeyi sayıyor
#
# `_on_tab_changed` panele yalnız `set_editor` çağırıyordu, o da yalnız
# işaretçiyi değiştiriyordu. Sayaç önceki belgenin sayısında kalıyordu.
#
# ÖLÇÜLDÜ (2026-09-08, hem widget düzeyinde hem GERÇEK pencerede):
#
#   A.tex'te 6 eşleşme -> B.tex'e geç (0 eşleşme)  etiket: "6 sonuç"
#   A.tex'te 0 eşleşme -> B.tex'e geç (6 eşleşme)  etiket: "Sonuç yok"
#
# İkinci yön daha kötü: panel "Sonuç yok" derken kullanıcı kelimenin o
# belgede olmadığını sanıyor.
#
# Sayım imleci ve seçimi oynatmıyor (SCI_SEARCHINTARGET), o yüzden düzeltme
# sekme değiştirmeyi belge kaydıran bir eyleme çevirmiyor.
#
# Ölçüt `isVisible` DEĞİL `isHidden`: `isVisible` gizli bir üst pencerenin
# çocuklarında da False dönüyor (ölçüldü), yani panel açıkken bile sayım
# koşmazdı ve bu kapılar da vakumda geçerdi.
# =====================================================================


class TestSekmeDegisince:

    def _iki_belge(self, ilk, ikinci, aranan="figure"):
        bar, ed1 = _bar(ilk, aranan)
        bar.show()                      # kullanıcı Ctrl+F'e basmış
        bar._do_find()
        bar._count_matches(aranan)
        ed2 = QsciScintilla()
        ed2.setText(ikinci)
        return bar, ed1, ed2

    def test_SAYAC_yeni_belgeye_gore_DUSUYOR(self, qapp):
        """Kırılırsa panel eşleşme olmayan belgede "6 sonuç" diyor."""
        bar, _ed1, ed2 = self._iki_belge("figure figure figure figure "
                                         "figure figure\n", "table table\n")
        assert bar._lbl_count.text() == "6 sonuç"

        bar.set_editor(ed2)

        assert bar._lbl_count.text() == "Sonuç yok"

    def test_SAYAC_yeni_belgeye_gore_ARTIYOR(self, qapp):
        """Kırılırsa panel "Sonuç yok" derken belgede altı eşleşme var ve
        kullanıcı kelimenin orada olmadığını sanıyor."""
        bar, _ed1, ed2 = self._iki_belge(
            "table table\n", "figure figure figure figure figure figure\n")
        assert bar._lbl_count.text() == "Sonuç yok"

        bar.set_editor(ed2)

        assert bar._lbl_count.text() == "6 sonuç"

    # --- Aşırı düzeltme kapıları ---

    def test_PANEL_KAPALIYKEN_sayilmiyor(self, qapp):
        """`_on_tab_changed` panel kapalıyken de set_editor çağırıyor; orada
        sayım hem gereksiz hem de her sekme değişimine bir belge taraması
        ekler."""
        bar, _ed1, ed2 = self._iki_belge("figure figure\n", "figure\n")
        bar.hide()
        bar._lbl_count.setText("DOKUNULMADI")

        bar.set_editor(ed2)

        assert bar._lbl_count.text() == "DOKUNULMADI"

    def test_SEKME_degisimi_IMLECI_oynatmiyor(self, qapp):
        """Sekme değiştirmek belgeyi kaydıran bir eyleme dönüşmemeli:
        kullanıcı B.tex'e bakmak için geçmiş olabilir."""
        bar, _ed1, ed2 = self._iki_belge("figure figure\n", "a\nb\nfigure\n")
        ed2.setCursorPosition(0, 0)

        bar.set_editor(ed2)

        assert ed2.selectedText() == ""
        assert ed2.getCursorPosition() == (0, 0)

    def test_GECERSIZ_DESEN_mesaji_KORUNUYOR(self, qapp):
        """Desen hatası belgeye değil DESENE ait: sekme değişince sayıya
        dönüşüp "Sonuç yok" olmamalı."""
        bar, _ed1, ed2 = self._iki_belge("aaa\n", "aaa\n")
        bar._cb_regex.setChecked(True)
        bar._find_input.setText("(a+)+")
        bar._do_find()
        assert bar._lbl_count.text() == "Geçersiz desen"

        bar.set_editor(ed2)

        assert bar._lbl_count.text() == "Geçersiz desen"


def test_GERCEK_PENCEREDE_sekme_degisimi_sayaci_yeniliyor(ana_pencere,
                                                          tmp_path):
    """Zinciri bütün olarak kapatıyor: `_on_tab_changed` -> `set_editor`.

    Widget kapıları paneli doğrudan çağırıyor; bu kapı sekmeyi GERÇEKTEN
    değiştiriyor, yani bağlantı koparsa da yakalıyor.
    """
    a = tmp_path / "A.tex"
    a.write_text("figure figure figure\nfigure figure figure\n",
                 encoding="utf-8")
    b = tmp_path / "B.tex"
    b.write_text("table table\n", encoding="utf-8")

    p = ana_pencere()
    p._dis_yolu_ac(str(a), "kapi")
    p._dis_yolu_ac(str(b), "kapi")
    yollar = {}
    for i in range(p._editor_tabs.count()):
        yol = getattr(p._editor_tabs.widget(i), "file_path", "")
        if yol:
            yollar[os.path.basename(yol)] = i

    p._editor_tabs.setCurrentIndex(yollar["A.tex"])
    p._show_find()
    bar = p._find_bar
    bar._find_input.setText("figure")
    bar._do_find()
    bar._count_matches("figure")
    assert bar._lbl_count.text() == "6 sonuç"

    p._editor_tabs.setCurrentIndex(yollar["B.tex"])

    assert bar._editor is p._current_editor()
    assert bar._lbl_count.text() == "Sonuç yok"


class TestIkiAramaAyniSayiyi:
    r"""Ctrl+F ile Projede Ara AYNI metinde aynı sayıyı vermeli.

    İki ayrı motor: burada QScintilla hedef araması, orada saf Python. İkisi
    de kullanıcıya "N sonuç" diye aynı dili konuşuyor, o yüzden ölçüt
    birbirlerine EŞİTLİKLERİ. ÖLÇÜLDÜ (2026-09-09): kendisiyle örtüşen
    sorgularda ayrışıyorlardı (`\\` -> 2 / 3, iki boşluk -> 3 / 5).

    O tur bu kapıyı HARF DUYARLI kurmuş (`_cb_case.setChecked(True)`), yani
    katlama ekseni hiç karşılaştırılmamış; ayrışma orada sürüyordu ve
    2026-09-10'da bulundu. Duyarsız kip aşağıdaki kardeş testte.
    """

    ORNEKLER = [
        ("a \\\\\\\\ b\n", "\\\\"),
        ("a      b\n", "  "),
        ("aaaa\n", "aa"),
        ("abab ab\n", "ab"),
        ("bir iki bir\n", "bir"),
    ]

    def test_ayni_sayi(self, qapp, tmp_path):
        from core.project_search import search_project

        for icerik, sorgu in self.ORNEKLER:
            yol = tmp_path / "m.tex"
            yol.write_text(icerik, encoding="utf-8", newline="")
            bar, _ed = _bar(icerik, sorgu)
            bar._cb_case.setChecked(True)           # iki taraf da harf duyarlı
            bar._count_matches(sorgu)
            bulgular, kesildi = search_project(str(tmp_path), sorgu,
                                               case_sensitive=True)
            assert not kesildi
            assert bar._match_count == len(bulgular), (icerik, sorgu)

    # Türkçe belgede Ctrl+F'in gerçekten aradığı kelimeler. Beklenen sayılar
    # ELLE yazılı, iki tarafın eşitliğinden TÜRETİLMİYOR: yoksa ikisi
    # birlikte bozulsa kapı yine geçerdi. Kural: `İ` ve `I` küçültmede `i`ye
    # gidiyor, `ı` kendinde kalıyor (ı/i ayrımı korunuyor, bkz. `kucult`).
    TURKCE_METIN = ("İçindekiler ve İSTANBUL\n"
                    "Örnek örnek ÖRNEK\n"
                    "Şekil şekil ŞEKİL\n")
    TURKCE_ORNEKLER = [("içindekiler", 1), ("istanbul", 1), ("örnek", 3),
                       ("ÖRNEK", 3), ("şekil", 3), ("ŞEKİL", 3)]

    def test_ayni_sayi_HARF_DUYARSIZ_kipte_de(self, qapp, tmp_path):
        """Duyarsız kipte Ctrl+F Türkçe harfleri hiç katlamıyordu.

        Scintilla'nın duyarsız araması yalnız ASCII'yi katlıyor; belge UTF-8
        olduğu için Türkçe harfler çok baytlı ve katlanmıyorlardı. ÖLÇÜLDÜ
        (2026-09-10), ASCII dışı harf içeren 83 gerçek şablon dosyasında 12
        gerçekçi sorgu: 2286 eşleşmenin 2061'i bulunuyordu, 225'i kaçıyordu
        (%9.8). En kötüsü `örnek`: 126'nın 29'u, çünkü Türkçe başlıklar
        büyük harfle başlıyor.
        """
        from core.project_search import search_project

        yol = tmp_path / "m.tex"
        yol.write_text(self.TURKCE_METIN, encoding="utf-8", newline="")
        for sorgu, sayi in self.TURKCE_ORNEKLER:
            bar, _ed = _bar(self.TURKCE_METIN, sorgu)
            _sec(bar, case=False)
            bar._count_matches(sorgu)
            bulgular, kesildi = search_project(str(tmp_path), sorgu,
                                               case_sensitive=False)
            assert not kesildi
            assert bar._match_count == sayi, ("Ctrl+F", sorgu,
                                              bar._match_count)
            assert len(bulgular) == sayi, ("proje", sorgu, len(bulgular))


class TestDesenKipindeTurkceKatlama:
    """Düz metin kipinde kapatılan eksik DESEN kipinde duruyordu.

    Scintilla'nın harf duyarsız desen araması ASCII dışı harflerin yalnız
    bir kısmını katlıyor. ÖLÇÜLDÜ (2026-09-12; aynı belge, aynı sorgu,
    yalnız "Desen" kutusu farklı, beklenen her satırda 2):

        çift     düz kip   desen kipi
        a / A       2          2
        ğ / Ğ       2          2
        ş / Ş       2          2
        ç / Ç       2          1
        i / İ       2          1
        ö / Ö       2          1
        ü / Ü       2          1

    Yani `üçgen` sorgusu desen kipinde 3 eşleşmenin 1'ini buluyordu.
    "Tümünü Değiştir" de aynı eksik listeyle çalışıp belgeyi YARIM
    değiştiriyor, etiket ise yaptığı değişikliği doğru sayıyordu.
    """

    def test_UC_YOL_da_Turkce_harfleri_katliyor(self, qapp):
        metin = "üçgen ÜÇGEN Üçgen\n"
        # 1) sayaç
        bar, _ed = _bar(metin, "üçgen")
        _sec(bar, regex=True)
        bar._count_matches("üçgen")
        assert bar._match_count == 3
        # 2) gezinme: üç AYRI yere gitmeli
        bar, ed = _bar(metin, "üçgen")
        _sec(bar, regex=True)
        yerler = []
        ed.setCursorPosition(0, 0)
        while len(yerler) < 5:
            satir, sutun = ed.getCursorPosition()
            if not bar._find_first("üçgen", wrap=False, forward=True,
                                   line=satir, col=sutun):
                break
            yerler.append(ed.getSelection()[:2])
            ed.setCursorPosition(*ed.getSelection()[2:])
        assert yerler == [(0, 0), (0, 6), (0, 12)]
        # 3) tümünü değiştir: HEPSİ değişmeli
        bar, ed = _bar(metin, "üçgen", "X")
        _sec(bar, regex=True)
        bar._replace_all()
        assert ed.text() == "X X X\n"
        # 4) noktalı İ de: `şekil` sorgusu `ŞEKİL`i bulmalı
        bar, _ed = _bar("Şekil şekil ŞEKİL\n", "şekil")
        _sec(bar, regex=True)
        bar._count_matches("şekil")
        assert bar._match_count == 3
        # 5) KARŞI KOL: duyarlı kipte hiçbiri katlanmamalı
        bar, _ed = _bar(metin, "üçgen")
        _sec(bar, regex=True, case=True)
        bar._count_matches("üçgen")
        assert bar._match_count == 1

    def test_i_noktasiz_I_ile_KATLANMIYOR(self, qapp):
        """ı/i ayrımı korunuyor: `ısı` sorgusu `ISI`yi bulmamalı.

        `'ı'.upper()` `I` veriyor ama katlama kuralı (``kucult``) ikisini EŞ
        SAYMIYOR. Desen kipi de düz kiple aynı cevabı vermek zorunda.
        """
        bar, _ed = _bar("ısı ISI\n", "ısı")
        _sec(bar, regex=True)
        bar._count_matches("ısı")
        assert bar._match_count == 1

        bar, _ed = _bar("ısı ISI\n", "ısı")
        _sec(bar, regex=False)
        bar._count_matches("ısı")
        assert bar._match_count == 1


def test_donusum_desenin_ANLAMINI_bozmuyor():
    """Desen yeniden yazılıyor; yazdıklarımız ANLAMI değiştirmemeli."""
    from gui.find_replace import _desen_harf_katla

    # Dokunulmayanlar
    assert _desen_harf_katla("a\\d+") == "a\\d+"       # ASCII ve kaçışlar
    assert _desen_harf_katla("[çÇ]") == "[çÇ]"         # sınıf İÇİ
    assert _desen_harf_katla("\\ç") == "\\ç"           # kaçırılmış harf
    assert _desen_harf_katla("ısı") == "ısı"           # ı/i ayrımı

    # Yazılanlar
    assert set(_desen_harf_katla("ç")) == set("[çÇ]")
    assert set(_desen_harf_katla("i")) == set("[iIİ]")

    # Grup NUMARALARI değişmemeli: `\1` geri referansları buna bağlı.
    assert _desen_harf_katla("(şekil) (\\d+)").count("(") == 2

    # Nicelik harfin değil, SINIFIN üstünde kalmalı
    assert _desen_harf_katla("ş{2}").endswith("]{2}")
