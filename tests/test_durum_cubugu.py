# -*- coding: utf-8 -*-
"""Durum çubuğu: son sekme kapanınca imleç konumu ve kelime sayacı.

Bu iki etiketin hiç kapısı yoktu. Kusur: son sekme kapatıldığında ikisi de
KAPANMIŞ belgenin değerlerini göstermeye devam ediyordu.

ÖLÇÜLDÜ (2026-09-08, gerçek pencerede):

  1) açılış, hiç sekme yok   ('Satır 1, Sütun 1', '')
  2) A.tex açık, imleç (2,7) ('Satır 3, Sütun 8', '  40 kelime, 349 karakter  ')
  3) son sekme KAPANDI       ('Satır 3, Sütun 8', '  40 kelime, 349 karakter  ')

Doğru boş durumu uygulamanın kendisi tanımlıyor: 1. satır. Kullanıcı "her
şeyi kapattım" ile "yeni başlattım" arasında fark görmemeli.

Kapılar GERÇEK pencere kuruyor: iki etiket yalnız orada var, vekil bir
nesnede bu kusur hiç görünmezdi.
"""


def _durum(p):
    return (p._status_pos.text(), p._status_wordcount.text())


def _belge(tmp_path, ad="A.tex", kelime=40):
    yol = tmp_path / ad
    yol.write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        + " ".join("kelime%d" % i for i in range(kelime))
        + "\n\\end{document}\n", encoding="utf-8")
    return str(yol)


def _say_hemen(p, editor):
    """Debounce'i bekleme: sayımı şimdi koştur."""
    p._update_wordcount(editor)
    p._wordcount_timer.stop()
    p._do_wordcount()


def test_ACILISTA_bos_durum_boyle_gorunuyor(ana_pencere):
    """Öteki kapıların ölçütü bu: "her şeyi kapattım" hâli açılıştaki hâl."""
    p = ana_pencere()
    assert p._editor_tabs.count() == 0
    assert _durum(p) == ("Satır 1, Sütun 1", "")


def test_SON_SEKME_kapaninca_ACILISTAKI_hale_donuyor(ana_pencere, tmp_path):
    """Kırılırsa durum çubuğu artık açık olmayan belgenin konumunu ve kelime
    sayısını göstermeye devam ediyor."""
    p = ana_pencere()
    p._dis_yolu_ac(_belge(tmp_path), "kapi")
    ed = p._current_editor()
    ed.setCursorPosition(2, 7)
    p._update_cursor_pos()
    _say_hemen(p, ed)
    assert _durum(p) == ("Satır 3, Sütun 8",
                         "  40 kelime, 349 karakter  ")

    p._close_tab(p._editor_tabs.indexOf(ed))

    assert p._editor_tabs.count() == 0
    assert _durum(p) == ("Satır 1, Sütun 1", "")


def test_BEKLEYEN_debounce_bayat_sayiyi_GERI_GETIRMIYOR(ana_pencere, tmp_path):
    """Sekme kapandıktan sonra bekleyen sayım turu ateşlenirse etiket bir
    daha eski değeri yazamamalı."""
    p = ana_pencere()
    p._dis_yolu_ac(_belge(tmp_path), "kapi")
    ed = p._current_editor()
    _say_hemen(p, ed)
    p._update_wordcount(ed)          # debounce yeniden bekliyor

    p._close_tab(p._editor_tabs.indexOf(ed))
    assert p._wordcount_timer.isActive() is False

    p._do_wordcount()                # zamanlayıcı yine de ateşlense
    assert p._status_wordcount.text() == ""


# --- Aşırı düzeltme kapıları ---

def test_SEKME_KALIYORSA_kalanin_degerleri_yaziliyor(ana_pencere, tmp_path):
    """Temizlik YALNIZ hiç sekme kalmayınca: iki sekmeden biri kapanınca
    durum çubuğu kalan belgeyi göstermeli, boşalmamalı."""
    p = ana_pencere()
    p._dis_yolu_ac(_belge(tmp_path, "A.tex", 40), "kapi")
    p._dis_yolu_ac(_belge(tmp_path, "B.tex", 7), "kapi")
    a = p._editor_by_path(str(tmp_path / "A.tex"))
    b = p._editor_by_path(str(tmp_path / "B.tex"))
    assert a is not None and b is not None

    p._close_tab(p._editor_tabs.indexOf(a))

    assert p._editor_tabs.count() == 1
    assert p._current_editor() is b
    # Temizlik dalına GİRİLMEMELİ: sayım kalan belge için debounce'a alınmış
    # olmalı. Etiketi burada okumak yanıltıcı olurdu, çünkü ürün sayımı
    # zamanlayıcıya bırakıyor ve o an etiket hâlâ eski değeri taşıyor.
    assert p._wordcount_timer.isActive() is True
    assert p._wordcount_editor is b

    p._wordcount_timer.stop()
    p._do_wordcount()
    assert "7 kelime" in p._status_wordcount.text()


def test_ACIK_BELGEDE_konum_hala_guncelleniyor(ana_pencere, tmp_path):
    """Aşırı düzeltme kapısı: boş dal her çağrıda konumu sıfırlamamalı."""
    p = ana_pencere()
    p._dis_yolu_ac(_belge(tmp_path), "kapi")
    ed = p._current_editor()

    ed.setCursorPosition(1, 3)
    p._update_cursor_pos()

    assert p._status_pos.text() == "Satır 2, Sütun 4"


def test_SON_SEKME_kapaninca_input_agaci_ve_anahat_da_BOSALIYOR(ana_pencere,
                                                                 tmp_path):
    r"""Sayaçtaki kusurun ikizi. ÖLÇÜLDÜ (2026-09-24, gerçek pencere): son
    sekme ya da "Tümünü Kapat" sonrası `\input` ağacında kapanan belgenin
    bağlantısı, anahatta başlığı kaldı; başlığa tıklamak hiçbir şey
    yapmıyordu. Ölçüt açılıştaki hâl: ağaç gizli, anahat boş."""
    (tmp_path / "bolum.tex").write_text("x\n", encoding="utf-8")
    yol = tmp_path / "A.tex"
    yol.write_text("\\documentclass{article}\n\\begin{document}\n"
                   "\\section{Kapanan}\n\\input{bolum}\n\\end{document}\n",
                   encoding="utf-8")
    p = ana_pencere()
    p._dis_yolu_ac(str(yol), "kapi")
    p._on_tab_changed(p._editor_tabs.currentIndex())
    assert p._file_tree._input_tree.topLevelItemCount() and p._outline._items

    p._close_tab(p._editor_tabs.currentIndex())

    assert p._editor_tabs.count() == 0
    assert p._file_tree._input_tree.isHidden()
    assert p._file_tree._input_tree.topLevelItemCount() == 0
    assert p._outline._items == []
