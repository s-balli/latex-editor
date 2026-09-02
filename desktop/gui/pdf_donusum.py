"""PDF kullanıcı uzayı ile ekran (etiket) uzayı arasında dönüşüm.

NEDEN AYRI BİR MODÜL: pdfium'un `get_width()`/`get_height()`i sayfanın
GÖRSEL (döndürülmüş) boyutunu veriyor, ama `get_charbox()` ve `get_index()`
DÖNDÜRÜLMEMİŞ kullanıcı uzayında çalışıyor. İkisini karıştırmak `/Rotate`
taşıyan sayfalarda koordinatları bozuyordu.

Ölçüldü (2026-09-02, dış güvenlik raporu 5. tur; sayfa 612x792, metin
(100, 650)'de, yer gerçekliği render edilmiş pikselleri tarayarak bulundu):

    /Rotate   metnin gerçek yeri        vurgunun çizildiği yer      örtüşme
    0         (114, 142, 218, 158)      (112, 135, 220, 165)        0.51
    90        (732, 116, 748, 218)      (112, -67, 131, -37)        0.00
    180       (470, 732, 572, 748)      (112, 135, 131, 165)        0.00
    270       (140, 470, 158, 572)      (112, -67, 131, -37)        0.00

90 ve 270'te vurgu NEGATİF y'ye, yani sayfanın dışına düşüyordu: görünmez.
Aynı ters dönüşüm kullanıldığı için metin seçimi de hiçbir şey bulamıyordu.

Dönüşüm tablosu (`x`, `y` kullanıcı uzayı, y YUKARI; `vx`, `vy` ekran, y AŞAĞI;
`W`, `H` DÖNDÜRÜLMEMİŞ sayfa boyutu). Dördü de yukarıdaki ölçümle doğrulandı:

    /Rotate 0     vx = x        vy = H - y
    /Rotate 90    vx = y        vy = x
    /Rotate 180   vx = W - x    vy = y
    /Rotate 270   vx = H - y    vy = W - x

KULLANIM: önce `geometri(sayfa)` ile sayfanın bilgisi BİR KEZ alınır, sonraki
dönüşümler saf aritmetiktir. Bunun iki sebebi var:

  - `_draw_selection_highlights` karakter başına dönüşüm yapıyor; her
    çağrıda pdfium'a üç soru sormak (rotasyon + iki boyut) gereksiz maliyet.
  - pdfium küresel durum tutuyor ve çağrıları kilit altında olmalı
    (bkz. gui/pdfium_lock.py). Tek giriş noktası olunca kilit de tek yerde.
"""

from gui.pdfium_lock import pdfium_lock


def geometri(page) -> tuple[int, float, float]:
    """Sayfanın (donme, DÖNDÜRÜLMEMİŞ genişlik, yükseklik) bilgisi.

    pdfium'a sorulan tek yer burası; kilit içeride alınıyor (RLock, çağıran
    zaten tutuyorsa sorun değil).
    """
    with pdfium_lock:
        try:
            ham = page.get_rotation()
        except Exception:
            ham = 0
        gw, gh = page.get_width(), page.get_height()

    try:
        d = int(ham)
    except (TypeError, ValueError):
        d = 0
    # pdfium bazı sürümlerde 0-3 çeyrek sayısı döndürüyor
    if d in (0, 1, 2, 3):
        d *= 90
    d %= 360
    # get_width/get_height GÖRSEL boyut: 90/270'te takas edilmiş geliyor
    return (d, gh, gw) if d in (90, 270) else (d, gw, gh)


def gorsele(g, x: float, y: float, olcek: float) -> tuple[float, float]:
    """Kullanıcı uzayındaki (x, y) noktasının ekran (etiket) koordinatı."""
    d, w, h = g
    if d == 90:
        vx, vy = y, x
    elif d == 180:
        vx, vy = w - x, y
    elif d == 270:
        vx, vy = h - y, w - x
    else:
        vx, vy = x, h - y
    return vx * olcek, vy * olcek


def kullaniciya(g, vx: float, vy: float, olcek: float) -> tuple[float, float]:
    """Ekran koordinatının kullanıcı uzayındaki karşılığı; `gorsele`nin tersi."""
    d, w, h = g
    ex, ey = vx / olcek, vy / olcek
    if d == 90:
        return ey, ex
    if d == 180:
        return w - ex, ey
    if d == 270:
        return w - ey, h - ex
    return ex, h - ey


def kutu_gorsele(g, sol: float, alt: float, sag: float, ust: float,
                 olcek: float) -> tuple[int, int, int, int]:
    """Kullanıcı uzayındaki kutunun ekran dikdörtgeni: (x, y, genişlik, yükseklik).

    İki köşe ayrı ayrı dönüştürülüp normalleştiriliyor: 90/270'te eksenler
    takas olduğu için "sol/üst" ekranda sol/üst kalmıyor.
    """
    x1, y1 = gorsele(g, sol, ust, olcek)
    x2, y2 = gorsele(g, sag, alt, olcek)
    x0, x3 = (x1, x2) if x1 <= x2 else (x2, x1)
    y0, y3 = (y1, y2) if y1 <= y2 else (y2, y1)
    return int(x0), int(y0), max(int(x3 - x0), 2), max(int(y3 - y0), 2)


# --- SyncTeX ---
#
# SyncTeX koordinatları PDF'inkinden FARKLI: origin sol-ÜST ve y AŞAĞI
# (TeX'in kendi düzlemi), üstelik DÖNDÜRÜLMEMİŞ sayfaya göre. /Rotate 0'da
# ekranla birebir örtüştüğü için eski kod dönüşümsüz çalışıyordu; döndürülmüş
# sayfada örtüşmüyor.


def synctexten_gorsele(g, sx: float, sy: float, olcek: float):
    """SyncTeX noktasının ekran (etiket) koordinatı."""
    _d, _w, h = g
    return gorsele(g, sx, h - sy, olcek)


def gorselden_syncteze(g, vx: float, vy: float, olcek: float):
    """Ekran noktasının SyncTeX koordinatı (geri arama bu yönü kullanıyor)."""
    _d, _w, h = g
    ux, uy = kullaniciya(g, vx, vy, olcek)
    return ux, h - uy


def synctex_kutusu(g, sol: float, sy: float, genislik: float,
                   yukseklik: float, olcek: float):
    """SyncTeX kutusunun ekran dikdörtgeni: (x, y, genişlik, yükseklik).

    Kutu SyncTeX'te (sol, sy) noktasının ÜSTÜNDE `yukseklik` kadar uzanıyor.
    90/270'te eksenler takas olduğu için iki köşe ayrı dönüştürülüp
    normalleştiriliyor.
    """
    x1, y1 = synctexten_gorsele(g, sol, sy - yukseklik, olcek)
    x2, y2 = synctexten_gorsele(g, sol + (genislik or 0.0), sy, olcek)
    x0, x3 = (x1, x2) if x1 <= x2 else (x2, x1)
    y0, y3 = (y1, y2) if y1 <= y2 else (y2, y1)
    return int(x0), int(y0), max(int(x3 - x0), 1), max(int(y3 - y0), 1)
