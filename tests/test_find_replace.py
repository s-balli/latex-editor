"""FindReplaceBar testleri — bul, say, değiştir, tümünü değiştir.

254 satırlık bu modülün HİÇ testi yoktu (2026-08-30 denetimi, D5) — üstelik
yıkıcı bir yol: "Tümünü Değiştir" tüm belgeyi tek geri-al adımında
değiştiriyor ve güvenlik sınırına ulaşınca eskiden SESSİZCE kesiyordu.
Deneyle üretilmişti: 12.000 eşleşmeli belgede 10.001 değiştirilip 1.999'u
dokunulmadan kalıyor, etiket yine sayı yazıyor, hiçbir uyarı çıkmıyordu.
"""

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
