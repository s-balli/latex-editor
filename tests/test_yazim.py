# -*- coding: utf-8 -*-
"""core/yazim.py testleri — LaTeX farkındalıklı yazım denetimi çekirdeği.

Qt YOK, spylls de GEREKMİYOR: sözlük gerektiren testler sahte bir sözlük
nesnesiyle koşuyor. CI'da spylls ve tr_TR sözlüğü bulunmuyor.

Testlerin çoğu 2026-09-03'te GERÇEK ŞABLONLARDA ölçülmüş kusurları koruyor;
hangisinin neyi koruduğu tek tek yazılı.
"""

import pytest

from core.yazim import (Bulgu, Denetleyici, belgeden_dil,
                        kelimeleri_cikar)


def sozler(metin):
    return [k.kelime for k in kelimeleri_cikar(metin)]


# =====================================================================
# Komut ve argümanları
# =====================================================================


def test_usepackage_argumani_metin_degil():
    """Paket adı düz metin değil.

    Bu, aksan normalleştirmesinin klasik tuzağıyla da bağlantılı: açgözlü bir
    desen `\\usepackage`'ı `\\u` + `s` sanıp `spackage`'a çeviriyordu ve
    yanlış pozitif %9.9'dan %12.1'e ÇIKIYORDU (ölçüldü).
    """
    assert sozler("\\usepackage{amsmath}\nDenetlenecek metin.") == \
        ["Denetlenecek", "metin"]


def test_label_ve_cite_argumani_atlanir():
    ks = sozler("Bkz.~\\cite{ornek2024} ve \\ref{tab:sonuc} tablosu.")
    assert "ornek" not in ks and "tab" not in ks and "sonuc" not in ks
    assert "Bkz" in ks and "tablosu" in ks


def test_section_argumani_METINDIR():
    """Komut argümanlarının HEPSİ atılamaz: başlık gerçek metindir."""
    ks = sozler("\\section{Giris Bolumu}\\label{sec:giris}")
    assert "Giris" in ks and "Bolumu" in ks
    assert "sec" not in ks and "giris" not in ks


def test_taninmayan_komutun_argumani_metin_sayilir():
    """Bilinmeyen komut düz metin varsayılır; aksi hâlde gerçek metin kaybolur."""
    assert "Deneme" in sozler("\\ozelkomut{Deneme metni}")


# =====================================================================
# Aksan makroları
# =====================================================================


def test_suslu_aksan_kelimeyi_bolmez():
    """`M\\"{u}hendislik` -> tek kelime.

    Gerçek kusur: template25 Türkçe harfleri aksan makrosuyla yazıyor ve
    naif çıkarım "Mühendislik" yerine "hendislik" üretip yanlış işaretliyordu.
    """
    ks = sozler("Pamukkale \\\"{U}niversitesi M\\\"{u}hendislik")
    assert ks == ["Pamukkale", "Üniversitesi", "Mühendislik"]
    assert "hendislik" not in ks and "niversitesi" not in ks


def test_parantezsiz_aksan_da_calisir():
    assert sozler("B\\\"olge") == ["Bölge"]


def test_harf_adli_aksan_SUSLU_ISTER():
    """`\\c{c}` ve `\\u{g}` çalışmalı."""
    assert sozler("Ye\\c{s}ilkanat") == ["Yeşilkanat"]
    assert sozler("\\u{g}elecek") == ["ğelecek"]


def test_parantezsiz_harf_adli_aksan_KOMUT_SAYILIR():
    """`\\usepackage` ve `\\cite` aksan sanılmamalı.

    `\\u` ve `\\c` gerçek komutların da öneki. Kaba bir desen `\\usepackage`'ı
    `\\u`+`s` sanıp `spackage`'a çeviriyor ve paket adları metne sızıyordu;
    ölçüldü, yanlış pozitif %9.9'dan %12.1'e ÇIKIYORDU.

    İKİ katman koruyor ve tek tek kaldırılınca diğeri yakalıyor:
      (a) komutun TAM ADI okunup ("usepackage", h) diye aranıyor, bulunamıyor
      (b) harf adlı aksanlarda süslü parantez şart
    Kırılma denetimi bunu ortaya çıkardı: yalnız (b)'yi kaldıran mutasyonda
    test GEÇİYORDU, çünkü (a) hâlâ tutuyordu. Değiştirecek olan bunu bilsin.
    """
    ks = sozler("\\usepackage{xcolor}\\cite{anahtar} Metin")
    assert ks == ["Metin"]


def test_tek_harf_komutu_kelimeye_katilir():
    """`\\i` noktasız ı; `\\ss` Almanca eszett."""
    assert sozler("k\\i sa") == ["kısa"]


def test_aksan_konumu_KAYDIRMAZ():
    """Aksan makrosu çözülür ama konum ÖZGÜN metinde kalır.

    Metni önden normalleştirmek konumları kaydırır ve editör yanlış yeri
    gösterir. Bu yüzden tarayıcı makroyu kelimenin içinde yutuyor.
    """
    metin = "Ilk satir.\nM\\\"{u}hendislik ikinci."
    ks = kelimeleri_cikar(metin)
    m = [k for k in ks if k.kelime == "Mühendislik"][0]
    assert m.satir == 2
    assert m.sutun == 0
    assert metin[m.ofset:m.ofset + 2] == "M\\"


# =====================================================================
# Matematik, yorum, verbatim
# =====================================================================


def test_matematik_atlanir():
    ks = sozler("Deger $\\alpha + \\beta$ ve \\[ x^2 \\] sonra.")
    assert "alpha" not in ks and "beta" not in ks
    assert "Deger" in ks and "sonra" in ks


def test_yorum_atlanir():
    ks = sozler("Gorunur % gizli kalmali\nikinci")
    assert ks == ["Gorunur", "ikinci"]


def test_kacisli_yuzde_yorum_degildir():
    assert "yuzde" in sozler("Yirmi \\% yuzde isareti")


def test_verbatim_ici_atlanir():
    ks = sozler("Once\n\\begin{verbatim}\nkodicerigi\n\\end{verbatim}\nSonra")
    assert ks == ["Once", "Sonra"]


def test_denklem_ortami_atlanir():
    ks = sozler("Once\n\\begin{equation}\nxyz abc\n\\end{equation}\nSonra")
    assert "xyz" not in ks and "abc" not in ks


# =====================================================================
# Önsöz
# =====================================================================


def test_onsoz_atlanir():
    """`\\begin{document}` öncesi yapılandırmadır.

    Ölçüldü (template36-ders, dokuz bölüm): önsöz dahil 2533 bulgu, hariç
    1679 -> %34 azalma. Gürültü tcolorbox tanımlarından geliyordu:
    colback, colframe, fonttitle, breakable, blue, white.
    """
    metin = ("\\documentclass{article}\n"
             "\\newtcolorbox{kutu}{colback=blue!5,fonttitle=\\bfseries,breakable}\n"
             "\\begin{document}\nGovde metni\n\\end{document}")
    ks = sozler(metin)
    assert "colback" not in ks and "fonttitle" not in ks
    assert "breakable" not in ks and "blue" not in ks
    assert "Govde" in ks and "metni" in ks


def test_onsozdeki_baslik_ve_yazar_DENETLENIR():
    """Önsöz atlanıyor ama başlık makalenin en görünür metnidir."""
    metin = ("\\documentclass{article}\n"
             "\\title{Derin Ogrenme Yaklasimi}\n"
             "\\author{Ornek Yazar}\n"
             "\\begin{document}\\end{document}")
    ks = sozler(metin)
    assert "Derin" in ks and "Ogrenme" in ks and "Yaklasimi" in ks
    assert "Ornek" in ks and "Yazar" in ks


def test_begin_document_yoksa_HEPSI_govdedir():
    """Bölüm dosyalarının önsözü yoktur; hepsi taranmalı."""
    assert "Bolum" in sozler("\\section{Bolum} Icerik metni")


# =====================================================================
# E-posta, URL, kesme işareti
# =====================================================================


def test_eposta_parcalanmaz():
    """`eskinhasan@gmail.com` -> "eskinhasan", "gmail", "com" oluyordu."""
    ks = sozler("Iletisim: eskinhasan@gmail.com adresinden")
    assert "gmail" not in ks and "com" not in ks and "eskinhasan" not in ks
    assert "Iletisim" in ks and "adresinden" in ks


def test_url_atlanir():
    ks = sozler("Adres https://ornek.com/sayfa burada")
    assert "ornek" not in ks and "sayfa" not in ks
    assert "Adres" in ks and "burada" in ks


def test_kesme_isaretinde_KOK_denetlenir():
    """Türkçede kesme işareti özel ad + ek ayırır: Ankara'da."""
    ks = sozler("Ankara'da yapildi")
    assert "Ankara" in ks
    assert "da" not in ks


# =====================================================================
# Dil tespiti
# =====================================================================


def test_tex_spellcheck_yorumu():
    assert belgeden_dil("% !TEX spellcheck = tr_TR\n\\documentclass{article}") \
        == "tr_TR"


def test_babel_tek_dil():
    assert belgeden_dil("\\usepackage[turkish]{babel}") == "tr_TR"


def test_babel_SON_secenek_ana_dildir():
    """babel'de son seçenek ana dil: [english,turkish] -> Türkçe."""
    assert belgeden_dil("\\usepackage[english,turkish]{babel}") == "tr_TR"
    assert belgeden_dil("\\usepackage[turkish,english]{babel}") == "en_US"


def test_acik_bildirim_babeli_EZER():
    """`% !TEX spellcheck` kullanıcının açık niyeti; babel dizgi dilidir."""
    metin = "% !TEX spellcheck = en_US\n\\usepackage[turkish]{babel}"
    assert belgeden_dil(metin) == "en_US"


def test_polyglossia():
    assert belgeden_dil("\\setmainlanguage{english}") == "en_US"


def test_bildirim_yoksa_None():
    assert belgeden_dil("\\documentclass{article}") is None


# =====================================================================
# Denetleyici (sahte sözlükle — spylls gerekmiyor)
# =====================================================================


class _SahteSozluk:
    def __init__(self, dogrular):
        self.dogrular = set(dogrular)
        self.sorulan = []

    def lookup(self, k):
        self.sorulan.append(k)
        return k in self.dogrular

    def suggest(self, k):
        return iter(["oneri1", "oneri2"])


def _denetleyici(dogrular, **kw):
    d = Denetleyici(**kw)
    d._sozluk = _SahteSozluk(dogrular)
    return d


def test_yanlis_kelime_konumuyla_bildirilir():
    d = _denetleyici(["dogru"])
    b = d.denetle("dogru yanlis")
    assert b == [Bulgu("yanlis", 1, 6, 6)]


def test_buyuk_atla_ozel_adlari_gecer():
    """Ölçüldü: İngilizce şablonlarda gürültünün %4.5 puanı özel ad."""
    d = _denetleyici([])
    assert [x.kelime for x in d.denetle("Riemann teoremi", buyuk_atla=True)] \
        == ["teoremi"]
    assert len(d.denetle("Riemann teoremi", buyuk_atla=False)) == 2


def test_rakam_iceren_kelime_denetlenmez():
    d = _denetleyici([])
    assert d.denetle("sha256 degeri") == \
        [Bulgu("degeri", 1, 7, 7)]


def test_kisa_kelime_denetlenmez():
    d = _denetleyici([])
    assert [x.kelime for x in d.denetle("ab cde", en_az=3)] == ["cde"]


def test_sozluk_yokken_kimseyi_suclamaz():
    """Sözlük yüklenmeden denetim çağrılırsa sessizce boş dönmeli."""
    d = Denetleyici()
    assert d.denetle("herhangi bir metin") == []
    assert d.hazir is False


def test_onbellek_ayni_kelimeyi_IKI_KEZ_sormaz():
    d = _denetleyici(["var"])
    d.denetle("yok yok yok yok")
    assert d._sozluk.sorulan.count("yok") == 1


def test_onbellek_ORNEK_BASINA(tmp_path):
    """functools.lru_cache bir METODA konursa önbellek sınıf düzeyinde olur.

    O hâlde iki ayrı dil aynı önbelleği paylaşır ve biri diğerinin sonucunu
    görür. Kod yazılırken bu tuzağa düşülmüştü, düzeltildi.
    """
    a = _denetleyici(["kelime"])
    b = _denetleyici([])
    assert a.dogru_mu("kelime") is True
    assert b.dogru_mu("kelime") is False


def test_kullanici_sozlugu_diske_yazilir(tmp_path):
    yol = tmp_path / "alt" / "kullanici.txt"
    d = _denetleyici([], kullanici_sozlugu=str(yol))
    assert d.kullaniciya_ekle("ablasyon") is True
    assert yol.read_text(encoding="utf-8").split() == ["ablasyon"]


def test_kullanici_sozlugu_diskten_okunur(tmp_path):
    yol = tmp_path / "kullanici.txt"
    yol.write_text("evrisimsel\nhiperparametre\n", encoding="utf-8")
    d = _denetleyici([], kullanici_sozlugu=str(yol))
    assert d.denetle("evrisimsel bilinmeyen") == \
        [Bulgu("bilinmeyen", 1, 11, 11)]


def test_kullaniciya_eklemek_ONBELLEGI_temizler():
    """Eklenen kelime hemen doğru sayılmalı, önbellekten eski sonuç gelmemeli."""
    d = _denetleyici([])
    assert d.dogru_mu("ablasyon") is False
    d.kullaniciya_ekle("ablasyon")
    assert d.dogru_mu("ablasyon") is True


def test_ayni_kelime_iki_kez_eklenmez():
    d = _denetleyici([])
    assert d.kullaniciya_ekle("terim") is True
    assert d.kullaniciya_ekle("terim") is False


def test_oneriler_tavani_asmaz():
    d = _denetleyici([])
    assert d.oneriler("yanlis", tavan=1) == ["oneri1"]


def test_sozluk_yokken_oneri_bos():
    assert Denetleyici().oneriler("yanlis") == []


# =====================================================================
# Uçtan uca: gerçek belge kalıbı
# =====================================================================


def test_gercek_belge_kalibi():
    """Bir arada: önsöz, başlık, komut, matematik, e-posta, aksan."""
    metin = (
        "\\documentclass{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\title{M\\\"{u}hendislik Calismasi}\n"
        "\\begin{document}\n"
        "\\section{Giris}\\label{sec:giris}\n"
        "Yazar eskinhasan@gmail.com adresinde. Deger $\\alpha$ olsun.\n"
        "% gizli yorum\n"
        "\\end{document}\n")
    ks = sozler(metin)
    assert "Mühendislik" in ks and "Calismasi" in ks   # başlık denetlendi
    assert "Giris" in ks                                # bölüm başlığı
    assert "adresinde" in ks and "Deger" in ks          # gövde
    for sizmamali in ("fontenc", "article", "sec", "giris",
                      "gmail", "com", "alpha", "gizli", "yorum"):
        assert sizmamali not in ks, sizmamali
