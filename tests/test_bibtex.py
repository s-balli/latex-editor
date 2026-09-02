"""core/bibtex: BibTeX ayrıştırma ve .bib iç tutarlılık denetimi (Qt'süz).

`collect_cite_keys` .bib'ten yalnız anahtarları çıkarıyordu ve bunu KÜME olarak
topluyordu; mükerrer anahtar orada sessizce tekilleşiyordu. Mükerrer anahtar
sinsi bir hata: BibTeX uyarmıyor, ilk tanımı alıyor, belgede YANLIŞ kaynak
basılıyor.

Ayrıştırma regex değil ayraç sayımı: alan değerlerinde iç içe süslü parantez
kural (şablon corpusunda 71 yerde geçiyor), regex ilk `}` ile durup değeri
yarıda kesiyor.
"""

import pytest

from core.bibtex import (
    BibGirdi, denetle, dosyayi_denetle, eksik_alanlar, mukerrer_anahtarlar,
    ozet, parse_entries,
)


# --- Ayrıştırma ---

class TestAyristirma:
    def test_basit_girdi(self):
        g = parse_entries("@article{key1, author={A}, year={2020}}")
        assert len(g) == 1
        assert g[0].tur == "article"
        assert g[0].anahtar == "key1"
        assert g[0].alanlar == {"author": "A", "year": "2020"}

    def test_tur_ve_alan_adlari_kucuk_harfe_iniyor(self):
        """BibTeX tür ve alan adlarında harf duyarsız; @InBook = @inbook."""
        g = parse_entries("@InBook{k, AUTHOR={A}, Title={T}}")[0]
        assert g.tur == "inbook"
        assert set(g.alanlar) == {"author", "title"}

    def test_ic_ice_suslu_parantez(self):
        """`title={The {BERT} Model}` regex ile ilk `}`de kesilirdi."""
        g = parse_entries("@article{k, title={The {BERT} Model}, year={2020}}")[0]
        assert g.alanlar["title"] == "The {BERT} Model"
        assert g.alanlar["year"] == "2020"

    def test_deger_icinde_virgul(self):
        """Yazar listesi virgül taşıyor; alan sınırı olarak alınmamalı."""
        g = parse_entries("@article{k, author={Kaya, Aydın and Can, Ahmet}, year={2020}}")[0]
        assert g.alanlar["author"] == "Kaya, Aydın and Can, Ahmet"
        assert g.alanlar["year"] == "2020"

    def test_tirnakli_deger(self):
        g = parse_entries('@article{k, title = "Bir Başlık", year = 2020}')[0]
        assert g.alanlar["title"] == "Bir Başlık"
        assert g.alanlar["year"] == "2020"

    def test_sarmalsiz_deger_makro_olarak_kaliyor(self):
        """`month=jun` bir makro; süslü parantez uydurmak yanlış olur."""
        g = parse_entries("@article{k, month=jun}")[0]
        assert g.alanlar["month"] == "jun"

    def test_parantezli_girdi_bicimi(self):
        g = parse_entries("@article(key2, title={T})")
        assert len(g) == 1 and g[0].anahtar == "key2"

    def test_string_comment_preamble_girdi_degil(self):
        metin = ('@string{jname = "Nature"}\n'
                 '@comment{bu bir not}\n'
                 '@preamble{"\\newcommand{\\x}{y}"}\n'
                 '@article{gercek, title={T}}\n')
        g = parse_entries(metin)
        assert [x.anahtar for x in g] == ["gercek"]

    def test_deger_icindeki_at_isareti_girdi_sanilmiyor(self):
        g = parse_entries("@article{k, note={yazar@ornek.com}, title={T}}")
        assert len(g) == 1
        assert g[0].alanlar["note"] == "yazar@ornek.com"

    def test_satir_numarasi(self):
        metin = "\n\n@article{a, title={T}}\n\n@book{b, title={T}}\n"
        g = parse_entries(metin)
        assert [(x.anahtar, x.satir) for x in g] == [("a", 3), ("b", 5)]

    def test_girdiler_dosya_sirasinda_ve_mukerrerler_duruyor(self):
        """`collect_cite_keys` küme döndürüyor; burada sıra ve tekrar korunmalı."""
        g = parse_entries("@article{b,}\n@article{a,}\n@article{b,}\n")
        assert [x.anahtar for x in g] == ["b", "a", "b"]

    def test_dengelenmemis_ayrac_kismi_sonuc(self):
        """Bozuk dosyada bulunanlar dönmeli; sessiz yanlış sonuç yerine."""
        g = parse_entries("@article{iyi, title={T}}\n@article{bozuk, title={T}\n")
        assert [x.anahtar for x in g] == ["iyi"]

    def test_bos_ve_bozuk_girdi_cokmuyor(self):
        for metin in ("", "@", "@@@", "hicbir sey", "@article", "@article{",
                      "@article{,}", "@{k, t={x}}"):
            parse_entries(metin)  # istisna atmamalı

    def test_cift_suslu_parantez_ic_kalıyor(self):
        """`{{Başlık}}` büyük harf koruması; yalnız DIŞ sarmal atılmalı."""
        g = parse_entries("@article{k, title={{BERT}}}")[0]
        assert g.alanlar["title"] == "{BERT}"


# --- Mükerrer anahtar ---

class TestMukerrer:
    def test_bulunuyor_ve_satirlar_veriliyor(self):
        metin = "@article{a,}\n@book{b,}\n@article{a,}\n"
        assert mukerrer_anahtarlar(parse_entries(metin)) == [("a", [1, 3])]

    def test_temiz_dosyada_bos(self):
        assert mukerrer_anahtarlar(parse_entries("@article{a,}\n@book{b,}\n")) == []

    def test_uc_kez_tanimli(self):
        metin = "@article{x,}\n@article{x,}\n@article{x,}\n"
        assert mukerrer_anahtarlar(parse_entries(metin)) == [("x", [1, 2, 3])]

    def test_harf_farki_mukerrer_DEGIL(self):
        """BibTeX anahtarları harf DUYARLI: Kaya2020 ile kaya2020 ayrı."""
        metin = "@article{Kaya2020,}\n@article{kaya2020,}\n"
        assert mukerrer_anahtarlar(parse_entries(metin)) == []


# --- Eksik zorunlu alan ---

class TestEksikAlan:
    def test_tam_article_temiz(self):
        g = parse_entries(
            "@article{k, author={A}, title={T}, journal={J}, year={2020}}")[0]
        assert eksik_alanlar(g) == []

    def test_eksik_alanlar_listeleniyor(self):
        g = parse_entries("@article{k, title={T}}")[0]
        assert eksik_alanlar(g) == ["author", "journal", "year"]

    def test_secenekli_alan_biri_yeterli(self):
        """@book için author ya da editor; ikisi de yoksa tek bulgu."""
        yazarli = parse_entries(
            "@book{k, author={A}, title={T}, publisher={P}, year={2020}}")[0]
        assert eksik_alanlar(yazarli) == []
        editorlu = parse_entries(
            "@book{k, editor={E}, title={T}, publisher={P}, year={2020}}")[0]
        assert eksik_alanlar(editorlu) == []
        yok = parse_entries("@book{k, title={T}, publisher={P}, year={2020}}")[0]
        assert eksik_alanlar(yok) == ["author/editor"]

    def test_bos_deger_yok_sayiliyor(self):
        g = parse_entries("@article{k, author={}, title={T}, journal={J}, year={2020}}")[0]
        assert eksik_alanlar(g) == ["author"]

    def test_misc_denetlenmiyor(self):
        """@misc'in zorunlu alanı yok; uydurma zorunluluk üretilmemeli."""
        assert eksik_alanlar(parse_entries("@misc{k,}")[0]) == []

    def test_taninmayan_tur_denetlenmiyor(self):
        """biblatex'e özgü türler (@online, @dataset) klasik listede yok."""
        assert eksik_alanlar(parse_entries("@online{k,}")[0]) == []
        assert eksik_alanlar(BibGirdi("uydurmatip", "k", 1, {})) == []

    def test_inproceedings_booktitle_istiyor(self):
        g = parse_entries("@inproceedings{k, author={A}, title={T}, year={2020}}")[0]
        assert eksik_alanlar(g) == ["booktitle"]


# --- Bütün denetim ---

class TestDenetle:
    def test_iki_sorunu_birden_buluyor(self):
        metin = ("@article{a, author={A}, title={T}, journal={J}, year={2020}}\n"
                 "@article{a, title={T}}\n")
        d = denetle(metin)
        assert d.mukerrer == [("a", [1, 2])]
        assert d.eksik == [("a", 2, ["author", "journal", "year"])]

    def test_temiz_dosya(self):
        d = denetle("@article{a, author={A}, title={T}, journal={J}, year={2020}}")
        assert d.mukerrer == [] and d.eksik == []


class TestDosyaOkuma:
    def test_utf8_dosya(self, tmp_path):
        p = tmp_path / "refs.bib"
        p.write_text("@article{k, title={Şekil ve Ölçüm}}\n", encoding="utf-8")
        d = dosyayi_denetle(str(p))
        assert d.eksik and d.eksik[0][0] == "k"

    def test_cp1254_dosya_okunabiliyor(self, tmp_path):
        """Türkçe .bib dosyaları cp1254 ile kaydedilmiş olabilir."""
        p = tmp_path / "refs.bib"
        p.write_bytes("@article{k, title={Şekil}}\n".encode("cp1254"))
        d = dosyayi_denetle(str(p))
        assert d.eksik and d.eksik[0][0] == "k"

    def test_olmayan_dosya_bos_denetim(self, tmp_path):
        d = dosyayi_denetle(str(tmp_path / "yok.bib"))
        assert d.mukerrer == [] and d.eksik == []

    def test_bos_yol_bos_denetim(self):
        d = dosyayi_denetle("")
        assert d.mukerrer == [] and d.eksik == []

    def test_onbellek_degisikligi_kaciriyor_mu(self, tmp_path):
        """mtime değişince yeniden okumalı; bayat sonuç göstermemeli."""
        import os
        import time
        p = tmp_path / "refs.bib"
        p.write_text("@article{a, author={A}, title={T}, journal={J}, year={2020}}\n",
                     encoding="utf-8")
        assert dosyayi_denetle(str(p)).eksik == []

        p.write_text("@article{a, title={T}}\n", encoding="utf-8")
        # Kaba dosya sistemlerinde aynı saniyeye düşmesin
        os.utime(str(p), (time.time() + 2, time.time() + 2))
        assert dosyayi_denetle(str(p)).eksik != []


@pytest.mark.parametrize("metin,beklenen", [
    # Alansız girdi GEÇERLİ BibTeX: sondaki virgül de zorunlu değil.
    ("@article{k}", 1),
    ("@article{k,}", 1),
    ("@ARTICLE{k, title={T}}", 1),
    ("  @article{k, title={T}}", 1),
    ("@article {k, title={T}}", 1),      # tür ile ayraç arasında boşluk
    ("@article{k, title={T},}", 1),      # sonda fazladan virgül
])
def test_bicim_varyantlari(metin, beklenen):
    assert len(parse_entries(metin)) == beklenen


# --- Listeleme özeti ---
#
# Bu üçü ısırma denemesinde AÇIK çıktı: kod doğruydu ama hiçbir test
# değişikliği yakalamıyordu.

class TestOzet:
    def test_tek_yazar(self):
        g = parse_entries("@article{k, author={Kaya, Aydın}}")[0]
        assert ozet(g)[2] == "Kaya"

    def test_cok_yazar_vd(self):
        g = parse_entries("@article{k, author={Kaya, A and Can, B and Öz, C}}")[0]
        assert ozet(g)[2] == "Kaya vd."

    def test_ad_soyad_bicimi(self):
        """BibTeX "Aydın Kaya" biçimini de kabul ediyor: soyadı SON kelime."""
        g = parse_entries("@article{k, author={Aydın Kaya}}")[0]
        assert ozet(g)[2] == "Kaya"

    def test_kurum_adi_BOLUNMUYOR(self):
        """`{Dünya Sağlık Örgütü}` kurum demek; içindeki boşluk ad ayracı değil."""
        g = parse_entries("@article{k, author={{Dünya Sağlık Örgütü}}}")[0]
        assert ozet(g)[2] == "Dünya Sağlık Örgütü"

    def test_yazar_yoksa_editor(self):
        g = parse_entries("@book{k, editor={Öz, Ali}}")[0]
        assert ozet(g)[2] == "Öz"

    def test_yazar_da_editor_de_yoksa_bos(self):
        assert ozet(parse_entries("@misc{k, title={T}}")[0])[2] == ""

    def test_baslik_koruma_parantezleri_ATILIYOR(self):
        """`{BERT}` dizgi motoru için; listede okunacak metin var."""
        g = parse_entries("@article{k, title={The {BERT} Model}}")[0]
        assert ozet(g)[4] == "The BERT Model"

    def test_baslik_satir_sonlari_tek_bosluga_iniyor(self):
        g = parse_entries("@article{k, title={Uzun\n   bir\n   başlık}}")[0]
        assert ozet(g)[4] == "Uzun bir başlık"

    def test_ozet_sirasi(self):
        g = parse_entries(
            "@inproceedings{He2016, author={He, K}, title={T}, year={2016}}")[0]
        assert ozet(g) == ("He2016", "inproceedings", "He", "2016", "T")


# --- DOI ile kaynak ekleme ---
#
# Getirilen BibTeX HAM HÂLİYLE kullanılamıyor. Üç kusur da GERÇEK DERLEMEYLE
# ölçüldü (pdflatex + bibtex, TeX Live 2023):
#
#   month=June  -> "Warning--string name 'june' is undefined", ay SESSİZCE
#                  düşüyor. Standart makrolar üç harfli (jan..dec).
#   pages={770<U+2013>778} (orta tire) -> plain.bst aralığı `--` ile tanıyor;
#                  çıktıya "page 770<U+2013>778" yazıyor, TEKİL. `--` ile
#                  "pages 770--778" oluyor.
#   anahtar olarak URL -> doi.org yolu `@misc{https://doi.org/10.48550/...}`
#                  döndürebiliyor, bu geçerli bir BibTeX anahtarı değil.
#
# Düzeltmelerden sonra dört gerçek DOI sıfır uyarıyla derlendi.

import urllib.error  # noqa: E402

from core.bibtex import (  # noqa: E402
    DoiHatasi, benzersiz_anahtar, bibe_ekle, doi_getir, doi_temizle,
    normallestir,
)


IEEE_HAM = (
    "@inproceedings{He_2016, title={Deep Residual Learning for Image "
    "Recognition}, DOI={10.1109/cvpr.2016.90}, booktitle={CVPR}, "
    "publisher={IEEE}, author={He, Kaiming and Zhang, Xiangyu}, year={2016}, "
    "month=June, pages={770–778} }"
)


class TestDoiTemizle:
    def test_ciplak_doi(self):
        assert doi_temizle("10.1038/nature14539") == "10.1038/nature14539"

    def test_tam_url(self):
        assert doi_temizle("https://doi.org/10.1038/nature14539") == "10.1038/nature14539"

    def test_dx_ve_doi_oneki(self):
        assert doi_temizle("http://dx.doi.org/10.1/x") == "10.1/x"
        assert doi_temizle("doi:10.1/x") == "10.1/x"
        assert doi_temizle("DOI:10.1/x") == "10.1/x"

    def test_bosluk_kirpiliyor(self):
        assert doi_temizle("  10.1/x  ") == "10.1/x"


class TestNormallestir:
    def test_ay_uc_harfe_iniyor(self):
        """`month=June` bibtex'te TANIMSIZ makro; ay sessizce düşüyordu."""
        metin, _a = normallestir(IEEE_HAM)
        assert "month = jun," in metin
        assert "June" not in metin

    def test_ay_suslu_parantez_ICINE_ALINMIYOR(self):
        """`month = {jun}` metin olur ve bibtex 'jun' diye basar, 'June' değil."""
        metin, _a = normallestir(IEEE_HAM)
        assert "month = {" not in metin

    def test_sayfa_araligi_cift_tire(self):
        """plain.bst aralığı `--` ile tanıyor; orta tirede 'page' (tekil) yazıyor."""
        metin, _a = normallestir(IEEE_HAM)
        assert "pages = {770--778}" in metin

    def test_tanınmayan_ay_atiliyor(self):
        ham = "@article{k, title={T}, month=Sonbahar, year={2020}}"
        metin, _a = normallestir(ham)
        assert "month" not in metin

    def test_kisa_ay_korunuyor(self):
        metin, _a = normallestir("@article{k, title={T}, month=Apr}")
        assert "month = apr," in metin

    def test_gecersiz_anahtar_yeniden_uretiliyor(self):
        """doi.org yolu anahtar olarak URL döndürebiliyor."""
        ham = ("@misc{https://doi.org/10.48550/arxiv.1706.03762, "
               "author={Vaswani, Ashish}, title={Attention}, year={2017}}")
        _m, anahtar = normallestir(ham)
        assert anahtar == "Vaswani2017"

    def test_gecerli_anahtar_KORUNUYOR(self):
        _m, anahtar = normallestir(IEEE_HAM)
        assert anahtar == "He_2016"

    def test_anahtar_cakismasi_cozuluyor(self):
        _m, anahtar = normallestir(IEEE_HAM, mevcut_anahtarlar=["He_2016"])
        assert anahtar == "He_2016a"

    def test_cok_satirli_uretiliyor(self):
        """Gelen girdi TEK satır; .bib'e öyle eklemek dosyayı okunmaz yapar."""
        metin, _a = normallestir(IEEE_HAM)
        assert len(metin.splitlines()) > 5
        assert metin.startswith("@inproceedings{He_2016,")
        assert metin.rstrip().endswith("}")

    def test_kacissiz_ampersan_kaciriliyor(self):
        """LaTeX'te çıplak `&` derlemeyi bozar."""
        metin, _a = normallestir("@article{k, title={Ar & Ge}, year={2020}}")
        assert "Ar \\& Ge" in metin

    def test_kacisli_ampersan_iki_kez_kacmiyor(self):
        metin, _a = normallestir("@article{k, title={Ar \\& Ge}, year={2020}}")
        assert "\\\\&" not in metin

    def test_bos_girdi_hata(self):
        with pytest.raises(DoiHatasi):
            normallestir("hicbir sey")

    def test_turkce_karakter_korunuyor(self):
        ham = "@article{k, title={Akciğer nodülü}, author={Kaya, Aydın}, year={2018}}"
        metin, _a = normallestir(ham)
        assert "Akciğer nodülü" in metin
        assert "Kaya, Aydın" in metin


class TestBenzersizAnahtar:
    def test_bostaysa_aynen(self):
        assert benzersiz_anahtar("a2020", []) == "a2020"

    def test_doluysa_harf_ekleniyor(self):
        assert benzersiz_anahtar("a2020", ["a2020"]) == "a2020a"
        assert benzersiz_anahtar("a2020", ["a2020", "a2020a"]) == "a2020b"

    def test_harfler_bitince_sayi(self):
        dolu = ["a"] + ["a" + chr(c) for c in range(ord("a"), ord("z") + 1)]
        assert benzersiz_anahtar("a", dolu) == "a2"


class TestDoiGetir:
    """Ağ SAHTE: gerçek DOI'ler ayrıca elle ölçüldü (dördü de derlendi)."""

    def test_crossref_basarili(self):
        cagrilar = []

        def sahte(url, kabul):
            cagrilar.append(url)
            return IEEE_HAM

        assert doi_getir("10.1109/CVPR.2016.90", ac=sahte) == IEEE_HAM
        assert "api.crossref.org" in cagrilar[0]
        assert len(cagrilar) == 1, "ilk uç yettiği hâlde ikincisi de denendi"

    def test_crossref_404_ise_doi_org_deneniyor(self):
        """Crossref DataCite kayıtlarını (arXiv, Zenodo) tanımıyor."""
        cagrilar = []

        def sahte(url, kabul):
            cagrilar.append(url)
            if "crossref" in url:
                raise urllib.error.HTTPError(url, 404, "yok", None, None)
            return IEEE_HAM

        assert doi_getir("10.1/x", ac=sahte) == IEEE_HAM
        assert len(cagrilar) == 2 and "doi.org" in cagrilar[1]

    def test_ikisi_de_bulamazsa_hata(self):
        def sahte(url, kabul):
            raise urllib.error.HTTPError(url, 404, "yok", None, None)

        with pytest.raises(DoiHatasi) as e:
            doi_getir("10.1/x", ac=sahte)
        assert "bulunamadi" in str(e.value)

    def test_ag_hatasi_ayirt_ediliyor(self):
        """"Bulunamadı" ile "bağlanamadım" kullanıcı için ayrı şeyler."""
        def sahte(url, kabul):
            raise OSError("baglanti yok")

        with pytest.raises(DoiHatasi) as e:
            doi_getir("10.1/x", ac=sahte)
        assert "ag" in str(e.value)

    def test_doi_gibi_gorunmeyen_ag_a_HIC_gitmiyor(self):
        cagrilar = []

        def sahte(url, kabul):
            cagrilar.append(url)
            return IEEE_HAM

        for kotu in ("", "   ", "merhaba", "https://ornek.com/makale"):
            with pytest.raises(DoiHatasi):
                doi_getir(kotu, ac=sahte)
        assert cagrilar == [], cagrilar

    def test_bibtex_olmayan_cevap_reddediliyor(self):
        def sahte(url, kabul):
            return "<html>404 sayfasi</html>"

        with pytest.raises(DoiHatasi):
            doi_getir("10.1/x", ac=sahte)


class TestBibeEkle:
    def test_sona_ekleniyor_mevcut_KORUNUYOR(self, tmp_path):
        """Dosya yeniden yazılmıyor: yorumlar, @string ve sıra duruyor."""
        p = tmp_path / "refs.bib"
        onceki = ("% elle yazilmis yorum\n"
                  "@string{jn = \"Nature\"}\n"
                  "@article{eski, title={T}, year={2019}}\n")
        p.write_text(onceki, encoding="utf-8")
        bibe_ekle(str(p), "@article{yeni,\n  title = {Y},\n}")
        sonra = p.read_text(encoding="utf-8")
        assert sonra.startswith(onceki)
        assert "@article{yeni," in sonra

    def test_olmayan_dosya_yaratiliyor(self, tmp_path):
        p = tmp_path / "yeni.bib"
        bibe_ekle(str(p), "@article{a,\n}")
        assert "@article{a," in p.read_text(encoding="utf-8")

    def test_eklenen_girdi_geri_ayristirilabiliyor(self, tmp_path):
        p = tmp_path / "refs.bib"
        p.write_text("@article{eski, title={T}}\n", encoding="utf-8")
        metin, anahtar = normallestir(IEEE_HAM)
        bibe_ekle(str(p), metin)
        girdiler = parse_entries(p.read_text(encoding="utf-8"))
        assert [g.anahtar for g in girdiler] == ["eski", anahtar]
        assert girdiler[1].alanlar["pages"] == "770--778"

    def test_cp1254_dosyaya_eklenince_bozulmuyor(self, tmp_path):
        """Türkçe .bib'ler cp1254 olabiliyor; okuma çözücüden geçiyor."""
        p = tmp_path / "refs.bib"
        p.write_bytes("@article{eski, title={Şekil}}\n".encode("cp1254"))
        bibe_ekle(str(p), "@article{yeni,\n  title = {Ölçüm},\n}")
        ham = p.read_bytes()
        assert b"@article{yeni," in ham
