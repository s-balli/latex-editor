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
    parse_entries,
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
