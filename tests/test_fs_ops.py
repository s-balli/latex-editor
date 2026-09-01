"""core/fs_ops: ad denetimi ve dosya/klasör işlemleri (Qt'süz).

Dosya ağacında yalnız "aç / sil" vardı; yeniden adlandırma, yeni dosya ve
yeni klasör yoktu. Adlandırma kuralları burada, GUI'siz sınanıyor.

Kurallar HER PLATFORMDA Windows'a göre: proje Windows'ta yazılıp WSL'de
derleniyor ve git ile paylaşılıyor. Linux'ta serbest olan `rapor<1>.tex`
Windows'ta açılamıyor; hata dosyayı yaratan makinede değil karşı tarafta
patlıyor.
"""

import os

import pytest

from core import fs_ops


# --- Ad denetimi ---

class TestAdHatasi:
    def test_normal_adlar_gecerli(self):
        for ad in ("bolum1.tex", "ana.tex", "Şekil-2.png", "kaynaklar.bib",
                   "a", "çok uzun ad boşluklu.tex", "bolum.1.tex", ".gitignore"):
            assert fs_ops.ad_hatasi(ad) == "", ad

    def test_bos_ad(self):
        assert fs_ops.ad_hatasi("") == fs_ops.BOS
        assert fs_ops.ad_hatasi("   ") == fs_ops.BOS

    def test_nokta_adlari(self):
        assert fs_ops.ad_hatasi(".") == fs_ops.NOKTA_ADI
        assert fs_ops.ad_hatasi("..") == fs_ops.NOKTA_ADI

    @pytest.mark.parametrize("ad", [
        "a<b.tex", "a>b.tex", "a:b.tex", 'a"b.tex',
        "a/b.tex", "a\\b.tex", "a|b.tex", "a?b.tex", "a*b.tex",
    ])
    def test_yasak_karakterler(self, ad):
        assert fs_ops.ad_hatasi(ad) == fs_ops.YASAK_KARAKTER, ad

    def test_ayrac_ad_icinde_yasak(self):
        """Bu katman TEK klasörde iş yapıyor; ad yol taşıyamaz.

        Yoksa "Yeni Dosya" kutusuna `../../ana.tex` yazmak proje dışına
        dosya yaratırdı.
        """
        assert fs_ops.ad_hatasi("../ana.tex") == fs_ops.YASAK_KARAKTER
        assert fs_ops.ad_hatasi("alt/ana.tex") == fs_ops.YASAK_KARAKTER

    def test_kontrol_karakteri(self):
        assert fs_ops.ad_hatasi("a\nb.tex") == fs_ops.YASAK_KARAKTER
        assert fs_ops.ad_hatasi("a\x00b.tex") == fs_ops.YASAK_KARAKTER

    def test_sonu_nokta_veya_bosluk(self):
        assert fs_ops.ad_hatasi("rapor.") == fs_ops.SONU_NOKTA_BOSLUK
        assert fs_ops.ad_hatasi("rapor.tex ") == fs_ops.SONU_NOKTA_BOSLUK

    @pytest.mark.parametrize("ad", ["CON", "con", "PRN", "AUX", "NUL",
                                    "COM1", "com9", "LPT1", "lpt9"])
    def test_aygit_adlari(self, ad):
        assert fs_ops.ad_hatasi(ad) == fs_ops.AYGIT_ADI, ad

    def test_aygit_adi_uzantiyla_da_yasak(self):
        """Windows'ta "CON.tex" de açılamıyor; uzantı korumuyor."""
        assert fs_ops.ad_hatasi("CON.tex") == fs_ops.AYGIT_ADI
        assert fs_ops.ad_hatasi("con.TEX") == fs_ops.AYGIT_ADI

    def test_aygit_adina_benzeyenler_serbest(self):
        """Kural fazla geniş olmamalı: CONTROL, CONS, LPT10 meşru adlar."""
        for ad in ("CONTROL.tex", "console.tex", "CONS", "LPT10.tex",
                   "COM10.tex", "MYCON.tex", "con2.tex"):
            assert fs_ops.ad_hatasi(ad) == "", ad

    def test_cok_uzun(self):
        assert fs_ops.ad_hatasi("a" * 256) == fs_ops.COK_UZUN
        assert fs_ops.ad_hatasi("a" * 255) == ""


# --- Çarpışma denetimi ---

class TestHedefDolu:
    def test_yoksa_bos(self, tmp_path):
        assert not fs_ops.hedef_dolu_mu(str(tmp_path / "yok.tex"))

    def test_varsa_dolu(self, tmp_path):
        p = tmp_path / "var.tex"
        p.write_text("x", encoding="utf-8")
        assert fs_ops.hedef_dolu_mu(str(p))

    def test_kendi_uzerine_carpisma_sayilmaz(self, tmp_path):
        """`rapor.tex` → `Rapor.tex` MEŞRU bir yeniden adlandırma.

        Windows'ta dosya sistemi harf duyarsız olduğu için düz bir
        `os.path.exists` denetimi bunu haksız yere engellerdi.
        """
        p = tmp_path / "rapor.tex"
        p.write_text("x", encoding="utf-8")
        assert not fs_ops.hedef_dolu_mu(str(p), eski=str(p))

    def test_baska_dosya_carpisma(self, tmp_path):
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("x", encoding="utf-8")
        b.write_text("y", encoding="utf-8")
        assert fs_ops.hedef_dolu_mu(str(b), eski=str(a))


# --- Oluşturma ---

class TestYeniOge:
    def test_dosya_yaratiliyor_ve_bos(self, tmp_path):
        yol = fs_ops.yeni_dosya(str(tmp_path), "yeni.tex")
        assert os.path.isfile(yol)
        assert open(yol, encoding="utf-8").read() == ""

    def test_klasor_yaratiliyor(self, tmp_path):
        yol = fs_ops.yeni_klasor(str(tmp_path), "bolumler")
        assert os.path.isdir(yol)

    def test_var_olan_dosyanin_uzerine_YAZMIYOR(self, tmp_path):
        """`open(..., "x")`: denetimle yaratma arasında dosya belirirse
        (başka pencere, git checkout) içerik sessizce silinmemeli."""
        p = tmp_path / "dolu.tex"
        p.write_text("degerli icerik", encoding="utf-8")
        with pytest.raises(FileExistsError):
            fs_ops.yeni_dosya(str(tmp_path), "dolu.tex")
        assert p.read_text(encoding="utf-8") == "degerli icerik"

    def test_var_olan_klasor_hata(self, tmp_path):
        (tmp_path / "var").mkdir()
        with pytest.raises(FileExistsError):
            fs_ops.yeni_klasor(str(tmp_path), "var")


# --- Yeniden adlandırma ---

class TestYenidenAdlandir:
    def test_dosya_tasiniyor_icerik_korunuyor(self, tmp_path):
        p = tmp_path / "eski.tex"
        p.write_text("icerik", encoding="utf-8")
        yeni = fs_ops.yeniden_adlandir(str(p), "yeni.tex")
        assert not p.exists()
        assert open(yeni, encoding="utf-8").read() == "icerik"
        assert os.path.basename(yeni) == "yeni.tex"

    def test_klasor_de_adlandirilabiliyor(self, tmp_path):
        d = tmp_path / "eski"
        d.mkdir()
        (d / "ic.tex").write_text("x", encoding="utf-8")
        yeni = fs_ops.yeniden_adlandir(str(d), "yeni")
        assert os.path.isfile(os.path.join(yeni, "ic.tex"))

    def test_var_olanin_UZERINE_YAZMIYOR(self, tmp_path):
        """`os.rename` POSIX'te hedefin üstüne SESSİZCE yazıyor.

        Kullanıcı `taslak.tex`i `ana.tex` yapmak isteyip var olan `ana.tex`i
        yok edebilirdi. Bu testi düşürmek veri kaybı demek.
        """
        a = tmp_path / "taslak.tex"
        b = tmp_path / "ana.tex"
        a.write_text("taslak", encoding="utf-8")
        b.write_text("DEGERLI", encoding="utf-8")
        with pytest.raises(FileExistsError):
            fs_ops.yeniden_adlandir(str(a), "ana.tex")
        assert b.read_text(encoding="utf-8") == "DEGERLI"
        assert a.exists()

    def test_ayni_klasorde_kaliyor(self, tmp_path):
        alt = tmp_path / "alt"
        alt.mkdir()
        p = alt / "a.tex"
        p.write_text("x", encoding="utf-8")
        yeni = fs_ops.yeniden_adlandir(str(p), "b.tex")
        assert os.path.dirname(yeni) == os.path.abspath(str(alt))

    def test_yalniz_harf_degisimi(self, tmp_path):
        """Windows'ta harf duyarsız dosya sistemi bunu engellememelidir."""
        p = tmp_path / "rapor.tex"
        p.write_text("x", encoding="utf-8")
        yeni = fs_ops.yeniden_adlandir(str(p), "Rapor.tex")
        assert os.path.basename(yeni) == "Rapor.tex"
        assert os.path.isfile(yeni)
