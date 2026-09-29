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

import os
import shutil
import subprocess
import sys
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


def _toplu_mu(cmd) -> bool:
    """Windows'ta ters arama noktaları TEK `wsl -e sh` sürecinde soruluyor."""
    return list(cmd[:4]) == ["wsl", "-e", "sh", "-c"]


def _noktalar(cmd) -> list:
    """Komutun sorduğu `sayfa:x:y:pdf` belirteçleri (tek ya da toplu)."""
    if _toplu_mu(cmd):
        args = list(cmd[6:])
        return args[1:] if cmd[4].startswith('d="$1"') else args
    return [cmd[cmd.index("-o") + 1]]


def _yanit(cmd, kod, cikti):
    """Tek sorguda synctex'in kendi çıktısı; toplu sorguda her nokta için
    çıktı ve ardından betiğin yazdığı işaret + çıkış kodu."""
    if _toplu_mu(cmd):
        return SimpleNamespace(returncode=0, stderr="", stdout="".join(
            cikti + "%s %d\n" % (st._TOPLU_AYRAC, kod) for _ in _noktalar(cmd)))
    return SimpleNamespace(returncode=kod, stdout=cikti, stderr="")


@pytest.fixture
def kos(monkeypatch):
    """Köprüyü sahte bir `subprocess.run` ile çalıştır."""
    def _kos(platform, tur, kod=None, cikti="", istisna=None):
        monkeypatch.setattr(st, "_PLATFORM", platform)
        if istisna is not None:
            yama = patch("gui.synctex.subprocess.run", side_effect=istisna)
        else:
            yama = patch("gui.synctex.subprocess.run",
                         side_effect=lambda cmd, **k: _yanit(cmd, kod, cikti))
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
    """Ters aramayı koş; tıklamanın KENDİ sorgusunu (ilk komut) ve sonucu
    döndür. Sonraki komutlar köşe ve komşu sorguları (bkz. reverse_search)."""
    from unittest.mock import patch

    yakalanan = {}

    def sahte_run(cmd, **k):
        yakalanan.setdefault("cmd", cmd)
        return _yanit(cmd, 0, cikti)

    monkeypatch.setattr(st, "_PLATFORM", platform)
    with patch("gui.synctex.subprocess.run", side_effect=sahte_run):
        sonuc = st.reverse_search(1, x, y, pdf)
    return yakalanan["cmd"], sonuc


# --- Ters arama: sayfanın gönderilme konumu ve komşu noktalar (2026-09-27) ---

_GONDERILME = ("/mnt/c/p/yontem.tex", 3)     # köşe sorgusunun cevabı
_DOGRU = ("/mnt/c/p/giris.tex", 6)


def _ters_senaryo(monkeypatch, platform, harita, varsayilan=None):
    """Noktaya göre cevap veren sahte synctex ile ters aramayı koş.

    `harita`: {x: (dosya, satır) ya da None}; köşe sorgusu x=1.0.
    Döner: ((dosya adı, satır) ya da None, sorulan x'ler sırasıyla).
    """
    from types import SimpleNamespace
    from unittest.mock import patch

    sorulan = []
    surec = []

    def _nokta(spec):
        x = round(float(spec.split(":")[1]), 1)
        sorulan.append(x)
        kayit = harita.get(x, varsayilan)
        if kayit is None:                          # synctex "eşleşme yok"
            return 255, ""
        return 0, ("SyncTeX result begin\nInput:%s\nLine:%d\nColumn:-1\n"
                   "SyncTeX result end\n" % kayit)

    def sahte_run(cmd, **k):
        surec.append(cmd)
        cevaplar = [_nokta(s) for s in _noktalar(cmd)]
        if not _toplu_mu(cmd):
            kod, cikti = cevaplar[0]
            return SimpleNamespace(returncode=kod, stdout=cikti, stderr="")
        return SimpleNamespace(returncode=0, stderr="", stdout="".join(
            c + "%s %d\n" % (st._TOPLU_AYRAC, k) for k, c in cevaplar))

    monkeypatch.setattr(st, "_PLATFORM", platform)
    pdf = r"C:\p\main.pdf" if platform == "win32" else "/mnt/c/p/main.pdf"
    with patch("gui.synctex.subprocess.run", side_effect=sahte_run):
        s = st.reverse_search(1, 100.0, 200.0, pdf)
    _ters_senaryo.surec = len(surec)
    _ters_senaryo.yol = s.file_path if s else None
    if not s:
        return None, sorulan
    return (s.file_path.replace("\\", "/").rsplit("/", 1)[-1], s.line), sorulan


# Windows'ta komşular TEK süreçte, hep birlikte soruluyor (bkz.
# `_reverse_search_wsl`); yerli kolda sırayla ve ilk uygun komşuda duruluyor.
_TUM_KOMSULAR = [92.0, 108.0, 84.0, 116.0, 68.0, 36.0]


def _sorulmasi_gereken(platform, sirali):
    if platform == "win32" and len(sirali) > 2:
        return [100.0, 1.0] + _TUM_KOMSULAR
    return sirali


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_GONDERILME_konumu_komsudan_duzeltiliyor(monkeypatch, platform):
    """LuaTeX, sayfa gönderilirken oluşan düğümlere o anki giriş konumunu
    yazıyor; o noktaya tıklamak sonraki bölümün dosyasına atlıyordu
    (ölçüm `reverse_search` docstring'inde). Tıklanan nokta sayfanın
    gönderilme konumunu verirse komşu noktanın cevabı alınıyor."""
    sonuc, sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: _GONDERILME, 92.0: _GONDERILME,
        108.0: _DOGRU})
    assert sonuc == ("giris.tex", 6), "gönderilme konumu dönüyor"
    assert sorulan == _sorulmasi_gereken(platform, [100.0, 1.0, 92.0, 108.0])


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_metin_GERCEKTEN_o_satirdaysa_sonuc_degismiyor(monkeypatch,
                                                           platform):
    """Aşırı düzeltme kolu: sayfa tam o satırın metninde bölündüyse komşular
    da aynı konumu veriyor ve sonuç değişmiyor."""
    sonuc, sorulan = _ters_senaryo(monkeypatch, platform, {},
                                   varsayilan=_GONDERILME)
    assert sonuc == ("yontem.tex", 3)
    # Sola büyüyen adımlar sayfanın soluna taşınca (100-128 < 0) sorulmuyor.
    assert sorulan == [100.0, 1.0, 92.0, 108.0, 84.0, 116.0, 68.0, 36.0]


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_SATIR_SONU_boslugu_soldaki_metinden_duzeltiliyor(monkeypatch,
                                                              platform):
    """LuaTeX'te satır sonundaki boşluğun tamamı gönderilme konumunu
    verebiliyor; ±16 pt komşular da boşlukta kalıyordu (ölçüm
    `reverse_search` docstring'inde). O satırın metni solda."""
    harita = {x: _GONDERILME for x in (1.0, 100.0, 92.0, 108.0, 84.0, 116.0)}
    harita[68.0] = _DOGRU
    sonuc, sorulan = _ters_senaryo(monkeypatch, platform, harita)
    assert sonuc == ("giris.tex", 6), "boşluk tıkı gönderilme konumuna gidiyor"
    assert sorulan == _sorulmasi_gereken(
        platform, [100.0, 1.0, 92.0, 108.0, 84.0, 116.0, 68.0])


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_GONDERILME_dosyasinda_SONRAKI_satir_supheli(monkeypatch,
                                                         platform):
    """Üç motorda da: bölüm dosyasının son paragrafını sonraki dosyanın
    `\\newpage`i kapatınca satır kutuları SONRAKİ dosyanın adını, kendi satır
    numaralarını taşıyor (`yontem.tex:9` yerine `sonuc.tex:9`). Sayfadaki her
    şey gönderilme konumundan önce okunduğu için o dosyada sonraki satır o
    sayfada olamaz."""
    sonuc, _sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: ("/mnt/c/p/yontem.tex", 9),
        92.0: ("/mnt/c/p/giris.tex", 9)})
    assert sonuc == ("giris.tex", 9), "sonraki dosyanın adı dönüyor"


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_GONDERILME_dosyasinda_ONCEKI_satir_supheli_DEGIL(monkeypatch,
                                                              platform):
    """Maliyet ve aşırı düzeltme kapısı: tek dosyalı belgede her tık
    gönderilme konumunun dosyasında ve ondan ÖNCEKİ bir satırda. Köşe
    sorgusundan başka sorgu yapılmıyor, sonuç değişmiyor."""
    sonuc, sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: ("/mnt/c/p/yontem.tex", 2)})
    assert sonuc == ("yontem.tex", 2)
    assert sorulan == [100.0, 1.0]


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_PROJE_DISI_dosya_supheli(monkeypatch, platform):
    """LuaTeX'te gönderilme bölgelerinin arasında `article.cls:0` gibi tek
    noktalık kayıtlar var; komşu taraması onlara düşünce editörde TeX
    dağıtımının sınıf dosyası açılıyordu (ölçüldü 2026-09-29)."""
    sinif = ("/usr/share/texlive/texmf-dist/tex/latex/base/article.cls", 2)
    sonuc, _sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: _GONDERILME, 92.0: sinif, 108.0: _DOGRU})
    assert sonuc == ("giris.tex", 6), "sınıf dosyası dönüyor"


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_BAGLI_projede_sonuc_KULLANICININ_yolunda(monkeypatch, platform):
    """Proje sembolik bağ ya da dizin bağlantısı altında (macOS'ta `/var` ve
    `/tmp` de öyle): TeX dosya adlarını GERÇEK yolla kaydediyor, sonuç bağsız
    biçimde geliyordu. Proje kökü kullanıcının yolundan hesaplandığı için her
    sonuç proje dışı sayılıyor, sonraki dosyaya atlama kuralı işlemiyordu
    (ölçüldü 2026-09-29, macos-15, bkz. `_kullanici_yoluna`). Burada bağı
    `_gercek_yol` taklit ediyor: kullanıcının `p` klasörü gerçekte
    `gercek/p`; synctex yalnız gerçek yolu biliyor."""
    if (platform == "win32") != (sys.platform == "win32"):
        pytest.skip("yol biçimi yalnız kendi platformunda kurulabiliyor")
    if platform == "win32":
        kullanici, gercek = "C:\\p", "C:\\gercek\\p"
    else:
        kullanici, gercek = "/mnt/c/p", "/mnt/c/gercek/p"
    monkeypatch.setattr(st, "_gercek_yol",
                        lambda y: y.replace(kullanici, gercek, 1))
    sonuc, _sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: ("/mnt/c/gercek/p/yontem.tex", 3),
        100.0: ("/mnt/c/gercek/p/yontem.tex", 9),
        92.0: ("/mnt/c/gercek/p/giris.tex", 9)})
    assert sonuc == ("giris.tex", 9), "sonraki dosyaya atlama kuralı işlemedi"
    assert _ters_senaryo.yol == os.path.join(kullanici, "giris.tex")


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_BOS_sonuc_komsudan_kurtariliyor(monkeypatch, platform):
    """LuaTeX'te bazı noktalar hiç kayıt vermiyordu (ölçümde 3/464)."""
    sonuc, _sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: None, 92.0: None, 108.0: _DOGRU})
    assert sonuc == ("giris.tex", 6)


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_dogru_sonucta_TEK_ek_sorgu(monkeypatch, platform):
    """Maliyet kapısı: pdflatex ve xelatex'te tıklama gönderilme konumunu
    vermiyor (ölçümde hiç); köşe sorgusundan başka sorgu yapılmıyor."""
    sonuc, sorulan = _ters_senaryo(monkeypatch, platform, {
        1.0: _GONDERILME, 100.0: _DOGRU})
    assert sonuc == ("giris.tex", 6)
    assert sorulan == [100.0, 1.0]


def test_TERS_ilk_sorgu_YAVASSA_ek_sorgu_yok(monkeypatch):
    """Soğuk WSL ya da asılı süreç: ilk sorgu bütçeden uzun sürdüyse ek
    sorgu yapılmıyor, yoksa tek tıklama altı kez zaman aşımı bekliyordu."""
    monkeypatch.setattr(st, "_EK_SORGU_BUTCESI", -1.0)
    sonuc, sorulan = _ters_senaryo(monkeypatch, "linux", {
        1.0: _GONDERILME, 100.0: _GONDERILME, 92.0: _DOGRU})
    assert sonuc == ("yontem.tex", 3)
    assert sorulan == [100.0]


# --- Windows: sorgular TOPLU (2026-09-29) ---
#
# Her sorgu ayrı bir `wsl -e` süreciydi (~85 ms, maliyetin tamamı süreç
# açılışı); şüpheli sonuçta tık başına on bire kadar süreç. ÖLÇÜLDÜ
# (2026-09-29, gerçek WSL, üç motor, 272-312 nokta, .gz yanında ve `-d`
# ile): sonuçlar ESKİSİYLE nokta nokta aynı (0 fark); ortanca 205-267 ms'den
# 104-134 ms'ye, en uzun tık 1.1-1.4 sn'den 0.25-0.47 sn'ye indi.


@pytest.mark.parametrize("harita, surec", [
    ({1.0: _GONDERILME, 100.0: _DOGRU}, 1),                     # olağan tık
    ({1.0: _GONDERILME, 100.0: _GONDERILME, 108.0: _DOGRU}, 2),  # şüpheli
    ({}, 2),                                                    # hiç eşleşme yok
])
def test_TERS_WSL_tik_basina_EN_FAZLA_iki_surec(monkeypatch, harita, surec):
    _ters_senaryo(monkeypatch, "win32", harita)
    assert _ters_senaryo.surec == surec


def test_TERS_WSL_ilk_toplu_sorgu_DUSERSE_komsulara_gidilmiyor(monkeypatch):
    """Zaman aşımı 15 sn: ikinci süreç ikinci bir 15 sn demekti."""
    cagri = []

    def sahte_run(cmd, **k):
        cagri.append(cmd)
        raise subprocess.TimeoutExpired("wsl", 15)

    monkeypatch.setattr(st, "_PLATFORM", "win32")
    with patch("gui.synctex.subprocess.run", side_effect=sahte_run):
        assert st.reverse_search(1, 100.0, 200.0, r"C:\p\main.pdf") is None
    assert len(cagri) == 1


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("sh"),
                    reason="betik POSIX sh'de koşuyor")
@pytest.mark.parametrize("synctex_dir", ["", r"C:\p\gz dizini"])
def test_TERS_WSL_toplu_BETIGI_gercek_kabukta(tmp_path, monkeypatch, synctex_dir):
    """Betiğin kendisi: yukarıdaki sahte `run` betiği hiç çalıştırmıyor. Burada
    `wsl -e`den sonrası gerçek `sh`de, PATH'teki sahte `synctex` ile koşuyor;
    her çağrı doğru noktayı ve `-d` dizinini almalı."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    sahte = bin_ / "synctex"
    sahte.write_text('#!/bin/sh\necho "$*" >> "$(dirname "$0")/cagri.txt"\n'
                     'printf "Input:/mnt/c/p/a.tex\\nLine:7\\nColumn:-1\\n"\n',
                     encoding="utf-8")
    sahte.chmod(0o755)
    yol = str(bin_) + os.pathsep + os.environ.get("PATH", "")
    gercek_run = subprocess.run            # aşağıda gui.synctex'inki yamalı

    def gercek_kabuk(cmd, **k):
        assert list(cmd[:2]) == ["wsl", "-e"]
        r = gercek_run(cmd[2:], capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env=dict(os.environ, PATH=yol))
        return SimpleNamespace(returncode=r.returncode, stdout=r.stdout,
                               stderr=r.stderr)

    monkeypatch.setattr(st, "_PLATFORM", "win32")
    with patch("gui.synctex.subprocess.run", side_effect=gercek_kabuk):
        sonuc = st._reverse_wsl_toplu(1, [(10.0, 20.0), (1.0, 1.0)],
                                      r"C:\p\main.pdf", synctex_dir)
    d = " -d /mnt/c/p/gz dizini" if synctex_dir else ""
    assert (bin_ / "cagri.txt").read_text(encoding="utf-8").splitlines() == [
        "edit -o 1:10.000000:20.000000:/mnt/c/p/main.pdf" + d,
        "edit -o 1:1.000000:1.000000:/mnt/c/p/main.pdf" + d]
    assert [s.line for s in sonuc] == [7, 7]


@pytest.mark.parametrize("synctex_dir", ["", r"C:\p\gz dizini"])
def test_TERS_WSL_yollar_BETIGE_gomulmuyor(monkeypatch, synctex_dir):
    r"""Boşluklu ve Türkçe yol tek sorgudaki gibi TEK argüman olarak gidiyor;
    betik sabit, `"$@"` ile okuyor. `-d` dizini ilk argüman."""
    pdf = r"C:\Users\Şerif Ö\tez klasörü\main.pdf"
    yakalanan = []

    def sahte_run(c, **k):
        yakalanan.append(c)
        return _yanit(c, 0, TAM_TERS)

    monkeypatch.setattr(st, "_PLATFORM", "win32")
    with patch("gui.synctex.subprocess.run", side_effect=sahte_run):
        st.reverse_search(1, 100.0, 200.0, pdf, synctex_dir)
    cmd = yakalanan[0]
    assert "Şerif" not in cmd[4] and "main.pdf" not in cmd[4], cmd[4]
    ozel = cmd[6:]
    if synctex_dir:
        assert ozel[0] == "/mnt/c/p/gz dizini"
        ozel = ozel[1:]
    assert ozel == ["1:100.000000:200.000000:/mnt/c/Users/Şerif Ö/tez klasörü/main.pdf",
                    "1:1.000000:1.000000:/mnt/c/Users/Şerif Ö/tez klasörü/main.pdf"]


@pytest.mark.parametrize("platform", _PLATFORMLAR)
def test_TERS_arama_koordinati_KIRPMIYOR(monkeypatch, platform):
    """Kırılırsa: kullanıcının tıkladığı nokta bir puntoya kadar kayıyor.

    ÖLÇÜLDÜ (142 nokta): kırpmak 11 noktada FARKLI satır döndürüyor; tam
    isabet 76'ya karşı 80. Satır yüksekliği ~9 pt, yani 1 pt satır
    sınırında cevabı değiştirebiliyor.
    """
    cmd, _s = _komutu_yakala(monkeypatch, platform, 10.75, 20.25,
                             "/a.pdf", TAM_TERS)
    spec = _noktalar(cmd)[0]           # ilk nokta tıklamanın kendisi
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
