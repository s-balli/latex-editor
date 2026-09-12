# -*- coding: utf-8 -*-
"""gui/synctex.py: SyncTeX köprüsünün sözleşmesi.

Bu modülün BİRİM testi yoktu; tek kapsamı `test_synctex_live.py` idi ve o
gerçek TeX Live istediği için Windows'ta ve matris işlerinde hep atlanıyor.
Yani köprünün dört sarmalayıcısı pratikte yalnız `derle` işinde koşuyordu.

ANA SORU: "synctex ÇALIŞTIRILAMADI" ile "koştu, eşleşme yok" ayrı mı.
Üçü de `None` dönüyordu ve kullanıcı üçünde de "SyncTeX: Eşleşme
bulunamadı" görüyordu. ÖLÇÜLDÜ (2026-09-06, gerçek süreçlerle):

    synctex kurulu değil (native)   FileNotFoundError
    WSL var, TeX Live yok           çıkış 127, stderr "command not found"
    koştu, o noktada eşleşme yok    çıkış 255, stdout'ta sürüm başlığı

İlk ikisinde kullanıcı konumu yanlış sanıp aynı yeri tekrar deniyordu;
yapması gereken TeX Live kurmaktı. Aynı ders `.synctex.gz` denetiminde bir
kez alınmıştı (bkz. `synctex_ops._on_reverse_search` yorumu).
"""

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401
    import gui.synctex as st
    from gui.synctex import ARAC_YOK, _parse_forward, _parse_reverse
    from gui.mixins.synctex_ops import SyncTexMixin
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 / gui modülleri gerekli", allow_module_level=True)


TAM_ILERI = ("SyncTeX result begin\nOutput:a.pdf\nPage:2\nx:100.0\ny:200.0\n"
             "h:50.0\nW:300.0\nH:9.0\nSyncTeX result end\n")
TAM_TERS = ("SyncTeX result begin\nInput:/p/a.tex\nLine:42\nColumn:-1\n"
            "SyncTeX result end\n")


@pytest.fixture
def kos(monkeypatch):
    """Köprüyü sahte bir `subprocess.run` ile çalıştır."""
    def _kos(platform, tur, kod=None, cikti="", istisna=None):
        monkeypatch.setattr(st, "_PLATFORM", platform)
        if istisna is not None:
            yama = patch("gui.synctex.subprocess.run", side_effect=istisna)
        else:
            yama = patch("gui.synctex.subprocess.run",
                         return_value=SimpleNamespace(returncode=kod,
                                                      stdout=cikti, stderr=""))
        with yama:
            if tur == "forward":
                return st.forward_search("/a.tex", 1, 0, "/a.pdf")
            return st.reverse_search(1, 10, 10, "/a.pdf")
    return _kos


_PLATFORMLAR = ["linux", "win32"]
_TURLER = ["forward", "reverse"]


# --- "çalıştırılamadı" ile "eşleşme yok" ayrımı ---

@pytest.mark.parametrize("platform", _PLATFORMLAR)
@pytest.mark.parametrize("tur", _TURLER)
def test_ARAC_KURULU_DEGILSE_arac_yok_donuyor(kos, platform, tur):
    """`synctex` yoksa süreç hiç başlamıyor: FileNotFoundError."""
    assert kos(platform, tur, istisna=FileNotFoundError("yok")) is ARAC_YOK


@pytest.mark.parametrize("platform", _PLATFORMLAR)
@pytest.mark.parametrize("tur", _TURLER)
def test_CIKIS_127_arac_yok_sayiliyor(kos, platform, tur):
    """`wsl -e synctex` komutu bulamazsa kabuk 127 döndürüyor (ölçüldü)."""
    assert kos(platform, tur, kod=127) is ARAC_YOK


@pytest.mark.parametrize("platform", _PLATFORMLAR)
@pytest.mark.parametrize("tur", _TURLER)
def test_CIKIS_255_eslesme_yok_demek(kos, platform, tur):
    """AŞIRI DÜZELTME KAPISI: synctex'in kendi 'eşleşme yok'u araç yok değil."""
    sonuc = kos(platform, tur, kod=255, cikti="This is SyncTeX...\n")
    assert sonuc is None, sonuc


@pytest.mark.parametrize("platform", _PLATFORMLAR)
@pytest.mark.parametrize("tur", _TURLER)
def test_ZAMAN_ASIMI_arac_yok_DEGIL(kos, platform, tur):
    """Zaman aşımı 'koştu ama asıldı' demek; kurulum sorunu değil.

    PLATFORM PARAMETRESİ ŞART. Yalnız `linux` ile yazılmıştı, yani yalnız
    `_*_native` dalını sınıyordu; WSL dalında aynı ayrımı bozan mutasyon
    kapıdan KAÇTI (ölçüldü 2026-09-06). Dört sarmalayıcı da ayrı kod.
    """
    sonuc = kos(platform, tur,
                istisna=subprocess.TimeoutExpired("synctex", 1))
    assert sonuc is None, sonuc


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_BASARILI_sonuc_bozulmadi_ileri(kos, platform):
    r = kos(platform, "forward", kod=0, cikti=TAM_ILERI)
    assert r is not None and r is not ARAC_YOK
    assert (r.page, r.x, r.y) == (2, 100.0, 200.0)
    assert (r.left, r.width, r.height) == (50.0, 300.0, 9.0)


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_BASARILI_sonuc_bozulmadi_ters(kos, platform):
    r = kos(platform, "reverse", kod=0, cikti=TAM_TERS)
    assert r is not None and r is not ARAC_YOK
    assert r.line == 42 and r.col == 0
    assert r.file_path.endswith("a.tex"), r.file_path


def test_ARAC_YOK_yanlislikla_SONUC_sanilmiyor():
    """`if result:` yazan bir çağıran sessizce 'eşleşme var' sanmamalı."""
    assert not ARAC_YOK
    assert ARAC_YOK is not None


# --- ayrıştırıcılar ---

def test_ILERI_ayristirici_ILK_kaydi_aliyor():
    """synctex birden çok eşleşme basıyor; en yakını ilkidir."""
    cikti = (TAM_ILERI.replace("SyncTeX result end\n", "")
             + "Page:9\nx:1.0\ny:2.0\nSyncTeX result end\n")
    r = _parse_forward(cikti)
    assert r.page == 2 and r.x == 100.0


def test_ILERI_ayristirici_EKSIK_alanda_None():
    assert _parse_forward("SyncTeX result begin\nPage:1\nSyncTeX result end\n") is None


def test_TERS_ayristirici_iki_noktali_yolu_bolmuyor():
    """Windows yolu `C:\\...` ilk iki noktadan sonra geliyor."""
    r = _parse_reverse("Input:C:\\Users\\a\\b.tex\nLine:7\nColumn:3\n")
    assert r.file_path == "C:\\Users\\a\\b.tex"
    assert (r.line, r.col) == (7, 3)


def test_TERS_ayristirici_kolon_eksi_bir_sifira_donuyor():
    assert _parse_reverse("Input:/a.tex\nLine:1\nColumn:-1\n").col == 0


def test_TERS_ayristirici_satir_yoksa_None():
    assert _parse_reverse("Input:/a.tex\nColumn:0\n") is None


# --- kullanıcıya giden mesaj ---

class _SahteAna(SyncTexMixin):
    """`_apply_*`in dokunduğu asgari yüzey."""

    def __init__(self):
        self.mesaj = ""
        self._status = SimpleNamespace(
            showMessage=lambda m: setattr(self, "mesaj", m))
        self._pdf_viewer = SimpleNamespace(scroll_to_position=lambda *a: None)

    def _goto_line(self, yol, satir):
        pass


_UYGULAMALAR = [("_apply_forward", ("/a.tex", 1, False)),
                ("_apply_reverse", 3)]


@pytest.mark.parametrize("uygula,baglam", _UYGULAMALAR)
def test_ARAC_YOKTA_dogru_sebep_soyleniyor(uygula, baglam):
    s = _SahteAna()
    getattr(s, uygula)(ARAC_YOK, baglam)
    assert s.mesaj, "araç yokken kullanıcıya hiçbir şey söylenmedi"
    assert "Eşleşme" not in s.mesaj, s.mesaj


@pytest.mark.parametrize("uygula,baglam", _UYGULAMALAR)
def test_ESLESME_YOKTA_eski_mesaj_duruyor(uygula, baglam):
    """AŞIRI DÜZELTME KAPISI: gerçek 'eşleşme yok' hâlâ öyle denmeli."""
    s = _SahteAna()
    getattr(s, uygula)(None, baglam)
    assert "Eşleşme" in s.mesaj, s.mesaj


@pytest.mark.parametrize("uygula,baglam", _UYGULAMALAR)
def test_IKI_SEBEP_ayri_mesaj(uygula, baglam):
    a, b = _SahteAna(), _SahteAna()
    getattr(a, uygula)(ARAC_YOK, baglam)
    getattr(b, uygula)(None, baglam)
    assert a.mesaj != b.mesaj


def test_MESAJ_TEK_KAYNAKTAN():
    """İleri ve ters arama aynı sebebe iki ayrı cevap vermesin."""
    import inspect
    for ad in ("_apply_forward", "_apply_reverse"):
        kaynak = inspect.getsource(getattr(SyncTexMixin, ad))
        assert "_synctex_araci_yok()" in kaynak, ad


# --- Ters ayrıştırıcı da İLK kaydı almalı (2026-09-12) ---

# GERÇEK `synctex edit` çıktısı (template21/egpaper_final.pdf, sayfa 1).
# İki kayıt da AYNI dosyayı gösteriyor; ikincisinin satırı uydurma, dosya
# 458 satır.
_IKI_KAYITLI_TERS = """This is SyncTeX command line utility, version 1.5
SyncTeX result begin
Output:egpaper_final.pdf
Input:/tmp/egpaper_final.tex
Line:99
Column:-1
Offset:0
Context:
Output:egpaper_final.pdf
Input:/tmp/baska.tex
Line:19213
Column:5
Offset:0
Context:
SyncTeX result end
"""


def test_TERS_ayristirici_ILK_kaydi_aliyor():
    r"""İleri ayrıştırıcı ilkini alıyor; ters olan SONUNCUYU alıyordu.

    ÖLÇÜLDÜ (30 gerçek `.synctex.gz`, 143 nokta): synctex 18 noktada birden
    çok kayıt döndürüyor ve 18'inde de ilk ile son farklı. Son kaydı almak
    istenen satırdan ortalama 245 satır sapıyordu (en büyük 19114) ve iki
    noktada dosyada OLMAYAN bir satıra gönderiyordu; ilk kayıtla ortalama
    6.6 satır ve dosya dışına çıkan yok.
    """
    r = _parse_reverse(_IKI_KAYITLI_TERS)
    assert r.line == 99, "son kayıt alınmış"
    assert r.file_path == "/tmp/egpaper_final.tex"
    # Sütun da İLK kaydın sütunu olmalı (-1 -> 0), ikincinin 5'i değil
    assert r.col == 0


def test_TERS_ayristirici_TEK_kayitta_degismedi():
    """Aşırı düzeltme kolu: tek kayıtlı çıktı eskisi gibi okunuyor."""
    r = _parse_reverse("Input:/a.tex\nLine:42\nColumn:7\n")
    assert (r.file_path, r.line, r.col) == ("/a.tex", 42, 7)


# --- Ters arama: koordinat KESİRLİ, yol WSL-UNC'ye geri dönüyor (2026-09-12) ---

def _komutu_yakala(monkeypatch, platform, x, y, pdf, cikti):
    """Ters aramayı koş, synctex'e giden komutu ve sonucu döndür."""
    from unittest.mock import patch
    from types import SimpleNamespace

    yakalanan = {}

    def sahte_run(cmd, **k):
        yakalanan["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=cikti, stderr="")

    monkeypatch.setattr(st, "_PLATFORM", platform)
    with patch("gui.synctex.subprocess.run", side_effect=sahte_run):
        sonuc = st.reverse_search(1, x, y, pdf)
    return yakalanan["cmd"], sonuc


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_arama_koordinati_KIRPMIYOR(monkeypatch, platform):
    """Kırılırsa: kullanıcının tıkladığı nokta bir puntoya kadar kayıyor.

    ÖLÇÜLDÜ (142 nokta): kırpmak 11 noktada FARKLI satır döndürüyor; tam
    isabet 76'ya karşı 80. Satır yüksekliği ~9 pt, yani 1 pt satır
    sınırında cevabı değiştirebiliyor.
    """
    cmd, _s = _komutu_yakala(monkeypatch, platform, 10.75, 20.25,
                             "/a.pdf", TAM_TERS)
    spec = [a for a in cmd if ":" in str(a) and "pdf" in str(a)][-1]
    assert "10.75" in spec and "20.25" in spec, spec


def test_WSL_UNC_yolu_WINDOWSA_geri_cevriliyor(monkeypatch):
    r"""Proje WSL'in KENDİ dosya sisteminde durabiliyor.

    İleri çevrim `\\wsl.localhost\Ubuntu\home\x`i biliyor, geri çevrim
    bilmiyordu: synctex `/home/x/main.tex` döndürüyor ve `_goto_line` o
    yolu Windows'ta açamayıp sessizce vazgeçiyordu. ÜRETİLDİ: WSL'in kendi
    dosya sisteminde derlenmiş gerçek bir belgede ileri arama çalışıyor,
    ters arama açılamayan bir yol veriyordu.
    """
    cikti = ("SyncTeX result begin\nInput:/home/secho/tez/main.tex\n"
             "Line:7\nColumn:-1\nSyncTeX result end\n")
    _cmd, s = _komutu_yakala(
        monkeypatch, "win32", 10.0, 20.0,
        "\\\\wsl.localhost\\Ubuntu\\home\\secho\\tez\\main.pdf", cikti)
    assert s.file_path == \
        "\\\\wsl.localhost\\Ubuntu\\home\\secho\\tez\\main.tex"
    assert s.line == 7


def test_SURUCU_yolunda_eski_davranis_SURUYOR(monkeypatch):
    """Aşırı düzeltme kolu: `/mnt/` biçimi örnekten etkilenmemeli."""
    cikti = ("SyncTeX result begin\nInput:/mnt/c/Users/a/main.tex\n"
             "Line:3\nColumn:-1\nSyncTeX result end\n")
    _cmd, s = _komutu_yakala(monkeypatch, "win32", 1.0, 2.0,
                             "\\\\wsl.localhost\\Ubuntu\\home\\a\\main.pdf",
                             cikti)
    assert s.file_path == "C:\\Users\\a\\main.tex"


# --- BAYAT `.synctex.gz` (2026-09-12) ---
#
# Eskiden yalnız dosyanın VARLIĞINA bakılıyordu. `derle.sh` GEÇİCİ dizinde
# derleyip PDF'i `mv`, `.gz`yi `cp ... || true` ile kaynak klasöre taşıyor;
# belge (ya da sınıfı) `\synctex=0` yazıyorsa motor `.gz` ÜRETMİYOR,
# kopyalama sessizce atlanıyor ve ESKİ `.gz` yerinde kalıyor.
#
# ÜRETİLDİ: belge 7 satırdan 13 satıra çıktı, PDF yenilendi, `.gz` eski
# kaldı; satır 13 sorulduğunda eski yerleşimin koordinatı dönüyordu ve
# kullanıcıya hiçbir uyarı çıkmıyordu.


class TestBayatSynctex:

    def _kur(self, tmp_path, gz_yasi=None):
        """(stub, pdf yolu). `gz_yasi` saniye: `.gz`yi o kadar ESKİ yap."""
        import os
        import time

        from gui.mixins.synctex_ops import SyncTexMixin

        pdf = tmp_path / "main.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        gz = tmp_path / "main.synctex.gz"
        gz.write_bytes(b"gz")
        simdi = time.time()
        os.utime(str(pdf), (simdi, simdi))
        if gz_yasi is not None:
            os.utime(str(gz), (simdi - gz_yasi, simdi - gz_yasi))

        class Stub(SyncTexMixin):
            def __init__(self, dizin):
                self._synctex_dir = dizin

        return Stub(str(tmp_path)), str(pdf), gz

    def test_gz_PDF_ten_eskiyse_BAYAT(self, tmp_path):
        """Kırılırsa: kullanıcı eski yerleşime göre yanlış yere atlar."""
        stub, pdf, _gz = self._kur(tmp_path, gz_yasi=60)
        assert stub._synctex_gz_durumu(pdf) == "bayat"

    def test_SAGLAM_cift_tamam(self, tmp_path):
        """Aşırı düzeltme kolu: `.gz` PDF'ten YENİ olduğunda çalışmalı.

        ÖLÇÜLDÜ (30 gerçek çift): `gz - pdf` farkı 0.0 ile +1.4 sn arasında
        ve hiçbirinde negatif değil; hepsi "tamam" diyor.
        """
        stub, pdf, _gz = self._kur(tmp_path, gz_yasi=-1.0)
        assert stub._synctex_gz_durumu(pdf) == "tamam"

    def test_KUCUK_fark_bayat_SAYILMIYOR(self, tmp_path):
        """Dosya sistemi çözünürlüğü payı: FAT 2 sn'ye yuvarlıyor."""
        stub, pdf, _gz = self._kur(tmp_path, gz_yasi=1.0)
        assert stub._synctex_gz_durumu(pdf) == "tamam"

    def test_gz_YOKSA_yok(self, tmp_path):
        stub, pdf, gz = self._kur(tmp_path)
        gz.unlink()
        assert stub._synctex_gz_durumu(pdf) == "yok"

    def test_IKI_SEBEP_AYRI_mesaj(self):
        """"yok" ile "bayat" aynı cümleyi vermemeli: yapılacak iş farklı."""
        from gui.mixins.synctex_ops import _GZ_MESAJI

        mesajlar = {k: f() for k, f in _GZ_MESAJI.items()}
        assert set(mesajlar) == {"yok", "bayat"}
        assert mesajlar["yok"] != mesajlar["bayat"]
        assert all(m.strip() for m in mesajlar.values())

    def test_ILERI_ve_TERS_ayni_on_kosula_bagli(self):
        """TEK KAYNAK: iki yol da `_synctex_gz_durumu`ya sormalı."""
        import inspect

        for ad in ("_on_forward_search", "_on_reverse_search"):
            kaynak = inspect.getsource(getattr(SyncTexMixin, ad))
            assert "_synctex_gz_durumu(" in kaynak, ad
            assert "_GZ_MESAJI[" in kaynak, ad
