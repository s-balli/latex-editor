"""/Rotate taşıyan sayfalarda koordinat dönüşümü.

pdfium'un `get_width()`/`get_height()`i GÖRSEL (döndürülmüş) boyutu veriyor,
ama `get_charbox()`/`get_index()`/link kutuları DÖNDÜRÜLMEMİŞ kullanıcı
uzayında. İkisini karıştırmak döndürülmüş sayfada koordinatları bozuyordu.

Ölçüldü (2026-09-02, dış güvenlik raporu 5. tur), sayfa 612x792, metin
(100, 650)'de, yer gerçekliği render edilmiş pikselleri tarayarak:

    /Rotate   metnin gerçek yeri      vurgunun çizildiği yer     örtüşme
    0         (114, 142, 218, 158)    (112, 135, 220, 165)       0.51
    90        (732, 116, 748, 218)    (112, -67, 131, -37)       0.00
    180       (470, 732, 572, 748)    (112, 135, 131, 165)       0.00
    270       (140, 470, 158, 572)    (112, -67, 131, -37)       0.00

90 ve 270'te vurgu NEGATİF y'ye düşüyordu: sayfanın dışı, görünmez. Metin
seçimi de aynı ters dönüşümü kullandığı için hiçbir karakteri bulamıyordu.

Buradaki testler saf matematiği sınıyor (Qt gerekmez). Uçtan uca ölçüm
(gerçek render + piksel taraması) laboratuvarda yapıldı; dördü de düzeltmeden
sonra doğru çıktı.
"""

import pytest

from gui.pdf_donusum import (
    geometri, gorsele, gorselden_syncteze, kullaniciya, kutu_gorsele,
    synctex_kutusu, synctexten_gorsele,
)

W, H = 612.0, 792.0


class _SahteSayfa:
    """pdfium sayfası: `get_width/height` GÖRSEL boyutu verir."""

    def __init__(self, rot):
        self._rot = rot

    def get_rotation(self):
        return self._rot

    def get_width(self):
        return H if self._rot in (90, 270) else W

    def get_height(self):
        return W if self._rot in (90, 270) else H


# Ölçümden gelen beklentiler: kullanıcı uzayında (100, 650) noktası
# ekranda nereye düşmeli (ölçek 1.0).
_BEKLENEN = {
    0: (100.0, 142.0),      # x,        H - y
    90: (650.0, 100.0),     # y,        x
    180: (512.0, 650.0),    # W - x,    y
    270: (142.0, 512.0),    # H - y,    W - x
}


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_gorsele_donusumu(rot):
    s = geometri(_SahteSayfa(rot))
    assert gorsele(s, 100.0, 650.0, 1.0) == pytest.approx(_BEKLENEN[rot])


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_kullaniciya_tam_ters(rot):
    """Tıklama yönü `gorsele`nin tersi olmalı, yoksa seçim tutmaz."""
    s = geometri(_SahteSayfa(rot))
    for x, y in ((100.0, 650.0), (0.0, 0.0), (W, H), (300.0, 400.0)):
        vx, vy = gorsele(s, x, y, 1.5)
        assert kullaniciya(s, vx, vy, 1.5) == pytest.approx((x, y))


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_gorsele_sayfanin_icinde_kaliyor(rot):
    """90/270'te vurgu NEGATİF y'ye düşüyordu: sayfa dışı, görünmez."""
    s = geometri(_SahteSayfa(rot))
    _d, uw, uh = s
    gw, gh = (uh, uw) if rot in (90, 270) else (uw, uh)
    for x, y in ((0.0, 0.0), (W, 0.0), (0.0, H), (W, H), (100.0, 650.0)):
        vx, vy = gorsele(s, x, y, 1.0)
        assert -0.01 <= vx <= gw + 0.01, (rot, x, y, vx)
        assert -0.01 <= vy <= gh + 0.01, (rot, x, y, vy)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_kutu_gorsele_pozitif_boyut(rot):
    """90/270'te eksenler takas oluyor; sol/üst ekranda sol/üst kalmıyor."""
    s = geometri(_SahteSayfa(rot))
    x, y, w, h = kutu_gorsele(s, 100.0, 640.0, 204.0, 660.0, 1.0)
    assert w > 0 and h > 0
    _d, uw, uh = s
    gw, gh = (uh, uw) if rot in (90, 270) else (uw, uh)
    assert 0 <= x <= gw and 0 <= y <= gh
    assert x + w <= gw + 1 and y + h <= gh + 1
    # Kutunun uzun kenarı 90/270'te DİKEY olmalı
    if rot in (90, 270):
        assert h > w
    else:
        assert w > h


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_synctex_ters_donusum(rot):
    """SyncTeX'in düzlemi sol-ÜST kökenli ve y aşağı; PDF'inkinden farklı."""
    s = geometri(_SahteSayfa(rot))
    for sx, sy in ((100.0, 142.0), (0.0, 0.0), (W, H), (300.0, 400.0)):
        vx, vy = synctexten_gorsele(s, sx, sy, 1.25)
        assert gorselden_syncteze(s, vx, vy, 1.25) == pytest.approx((sx, sy))


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_synctex_kutusu_sayfanin_icinde(rot):
    s = geometri(_SahteSayfa(rot))
    x, y, w, h = synctex_kutusu(s, 100.0, 142.0, 104.0, 17.0, 1.0)
    _d, uw, uh = s
    gw, gh = (uh, uw) if rot in (90, 270) else (uw, uh)
    assert 0 <= x <= gw and 0 <= y <= gh
    assert x + w <= gw + 1 and y + h <= gh + 1

    # Boyut GERÇEKTEN verilen genişlik/yüksekliği taşımalı. Yalnız "> 0"
    # demek yetmiyordu: kutu sıfır yüksekliğe düşse bile alt sınır 1 onu
    # geçiriyordu (kasıtlı bozmada görüldü).
    uzun, kisa = (h, w) if rot in (90, 270) else (w, h)
    assert uzun == pytest.approx(104, abs=1)
    assert kisa == pytest.approx(17, abs=1)


def test_rotate_0_eski_davranisla_ayni():
    """Döndürülmemiş sayfada hiçbir şey değişmemeli."""
    s = geometri(_SahteSayfa(0))
    assert gorsele(s, 100.0, 650.0, 2.0) == pytest.approx((200.0, 284.0))
    assert kullaniciya(s, 200.0, 284.0, 2.0) == pytest.approx((100.0, 650.0))
    # SyncTeX rot 0'da ekranla birebir: y aynen geçer
    assert synctexten_gorsele(s, 100.0, 142.0, 1.0) == pytest.approx((100.0, 142.0))


@pytest.mark.parametrize("ham,beklenen", [
    (0, 0), (90, 90), (180, 180), (270, 270),
    (1, 90), (2, 180), (3, 270),        # pdfium çeyrek sayısı döndürebiliyor
    (360, 0), (-90, 270),
    (None, 0), ("x", 0),                # okunamayan değer sorun çıkarmamalı
])
def test_donme_okunmasi(ham, beklenen):
    class _S:
        def get_rotation(self):
            return ham

        def get_width(self):
            return W

        def get_height(self):
            return H

    assert geometri(_S())[0] == beklenen


def test_donme_istisnayi_yutuyor():
    class _S:
        def get_rotation(self):
            raise RuntimeError("bozuk sayfa")

        def get_width(self):
            return W

        def get_height(self):
            return H

    assert geometri(_S())[0] == 0


# ---------------------------------------------------------------------------
# İç bağlantı hedefi (PDF destination) de aynı dönüşümden geçmeli
#
# `resolve_dest_scroll_y` GÖRSEL yüksekliği alıp `(yükseklik - y) * ölçek`
# ile /Rotate 0 formülünü uyguluyordu. Destination koordinatları ise
# DÖNDÜRÜLMEMİŞ kullanıcı uzayında; kardeş yol `_events._link_at_pos` bu
# dönüşümü zaten yapıyordu, burası atlanmıştı.
#
# ÖLÇÜLDÜ (2026-09-05, pdflscape ile üretilen /Rotate 90 sayfa; hedefin yeri
# render edilen piksellerden okundu): olması gereken 483 px, çıkan -5381 px.
# Uçtan uca hali tests/test_pdf_baglanti_derleme.py'de (derle işi); buradaki
# testler pdfium'suz koşuyor ve tabloyu doğrudan sabitliyor.
# ---------------------------------------------------------------------------

praw = pytest.importorskip("pypdfium2.raw")
from gui.pdf_links import resolve_dest_scroll_y                     # noqa: E402


def _sahte_gorunum(mod, degerler):
    """FPDFDest_GetView yerine geçen sahte: params dizisini doldurur."""
    def f(_dest, n_ref, params):
        n_ref._obj.value = len(degerler)
        for i, v in enumerate(degerler):
            params[i] = v
        return mod
    return f


class TestDestKaydirmaKonumu:
    W, H = 612.0, 792.0
    X, Y = 150.0, 700.0          # kullanıcı uzayında hedef noktası
    OLCEK = 1.5

    # Dönüşüm tablosunun (bkz. gui/pdf_donusum.py) dikey bileşeni, ELLE
    # yazılmış hali. `gorsele`yi çağırıp karşılaştırmak dairesel olurdu.
    BEKLENEN = {
        0:   (H - Y) * OLCEK,            #  138.0
        90:  X * OLCEK,                  #  225.0
        180: Y * OLCEK,                  # 1050.0
        270: (W - X) * OLCEK,            #  693.0
    }

    @pytest.fixture
    def xyz(self, monkeypatch):
        monkeypatch.setattr(praw, "FPDFDest_GetView",
                            _sahte_gorunum(praw.PDFDEST_VIEW_XYZ,
                                           [self.X, self.Y, 0.0]))

    @pytest.mark.parametrize("donme", [0, 90, 180, 270])
    def test_xyz_hedefi_donusum_tablosuna_uyuyor(self, donme, xyz):
        g = (donme, self.W, self.H)
        assert resolve_dest_scroll_y(None, None, g, self.OLCEK) == \
            int(self.BEKLENEN[donme])

    @pytest.mark.parametrize("donme", [90, 180, 270])
    def test_eski_formul_ARTIK_kullanilmiyor(self, donme, xyz):
        """Karşı yön: eski hesabın verdiği değer artık çıkmamalı.

        Önkoşulu da doğruluyor, yoksa kapı boşalır: /Rotate 0'da eski ve yeni
        değer zaten aynı olduğu için o dönme burada sınanmıyor.
        """
        gorsel_h = self.W if donme in (90, 270) else self.H
        eski = int((gorsel_h - self.Y) * self.OLCEK)
        assert eski != int(self.BEKLENEN[donme]), \
            "vaka ayrım göstermiyor, test hiçbir şey ölçmüyor"
        g = (donme, self.W, self.H)
        assert resolve_dest_scroll_y(None, None, g, self.OLCEK) != eski

    def test_rotate_0_eski_degerle_BIREBIR_ayni(self, xyz):
        """Gündelik belgede hiçbir şey değişmemeli."""
        eski = int((self.H - self.Y) * self.OLCEK)
        assert resolve_dest_scroll_y(None, None, (0, self.W, self.H),
                                     self.OLCEK) == eski

    @pytest.mark.parametrize("donme", [0, 90, 180, 270])
    def test_sonuc_hicbir_zaman_negatif_degil(self, donme, monkeypatch):
        """Destination sayfanın DIŞINDA olabiliyor.

        Ölçülen bir belgede hyperref+pdflscape 792 pt'lik sayfaya y=4200
        yazmıştı; böyle bir değer döndürülmüş sayfada negatif üretiyor ve
        görüntü sayfanın öncesine kayıyordu.
        """
        monkeypatch.setattr(praw, "FPDFDest_GetView",
                            _sahte_gorunum(praw.PDFDEST_VIEW_XYZ,
                                           [313.8, 4200.0, 0.0]))
        assert resolve_dest_scroll_y(None, None, (donme, self.W, self.H),
                                     self.OLCEK) >= 0

    @pytest.mark.parametrize("donme,beklenen", [
        (0, int((792.0 - 700.0) * 1.5)),
        (180, int(700.0 * 1.5)),
        (90, 0),        # dikey konumu x belirliyor, FitH x vermiyor
        (270, 0),
    ])
    def test_fith_hedefi(self, donme, beklenen, monkeypatch):
        """FitH yalnız y veriyor; 90/270'te yanlış yere gitmektense sayfa başı."""
        monkeypatch.setattr(praw, "FPDFDest_GetView",
                            _sahte_gorunum(praw.PDFDEST_VIEW_FITH, [700.0]))
        assert resolve_dest_scroll_y(None, None, (donme, self.W, self.H),
                                     1.5) == beklenen

    @pytest.mark.parametrize("mod", ["FIT", "FITV", "FITR", "FITB"])
    def test_desteklenmeyen_gorunum_sayfa_basina_goturuyor(self, mod, monkeypatch):
        """Bilinmeyen görünüm kipinde tahmin yürütülmemeli."""
        sabit = getattr(praw, "PDFDEST_VIEW_" + mod, None)
        if sabit is None:
            pytest.skip("pypdfium2'de PDFDEST_VIEW_%s yok" % mod)
        monkeypatch.setattr(praw, "FPDFDest_GetView",
                            _sahte_gorunum(sabit, [1.0, 2.0, 3.0, 4.0]))
        assert resolve_dest_scroll_y(None, None, (90, self.W, self.H), 1.5) == 0

    def test_eksik_parametre_sayfa_basina_goturuyor(self, monkeypatch):
        """XYZ iki parametre istiyor; bozuk belgede tek gelebilir."""
        monkeypatch.setattr(praw, "FPDFDest_GetView",
                            _sahte_gorunum(praw.PDFDEST_VIEW_XYZ, [150.0]))
        assert resolve_dest_scroll_y(None, None, (0, self.W, self.H), 1.5) == 0
