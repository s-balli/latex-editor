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
