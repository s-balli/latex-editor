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
