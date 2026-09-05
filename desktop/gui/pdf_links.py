"""PDF link çözümleme — pypdfium2 ctypes çağrıları."""

import ctypes

from pypdfium2 import raw as _pdfium_raw

from gui.pdf_donusum import gorsele


def get_link_at_point(page_raw, x_pts: float, y_pdf: float):
    """Verilen PDF koordinatında link varsa FPDF_LINK döndür, yoksa None."""
    try:
        return _pdfium_raw.FPDFLink_GetLinkAtPoint(page_raw, x_pts, y_pdf)
    except Exception:
        return None


def resolve_link_action(pdf_raw, link):
    """Link'in aksiyonunu çözümle.

    Dönüş: ('uri', url_str) | ('goto', dest) | ('dest', dest) | None
    """
    try:
        action = _pdfium_raw.FPDFLink_GetAction(link)
        if action:
            action_type = _pdfium_raw.FPDFAction_GetType(action)
            if action_type == _pdfium_raw.PDFACTION_URI:
                bufsize = 4096
                buf = ctypes.create_string_buffer(bufsize)
                _pdfium_raw.FPDFAction_GetURIPath(pdf_raw, action, buf, bufsize)
                uri = buf.value.decode("utf-8", errors="ignore")
                if uri:
                    return ("uri", uri)
            if action_type == _pdfium_raw.PDFACTION_GOTO:
                dest = _pdfium_raw.FPDFAction_GetDest(pdf_raw, action)
                if dest:
                    return ("goto", dest)
        dest = _pdfium_raw.FPDFLink_GetDest(pdf_raw, link)
        if dest:
            return ("dest", dest)
    except Exception:
        pass
    return None


def resolve_dest_scroll_y(pdf_raw, dest, g, scale: float) -> int:
    """PDF destination'ın scroll Y pozisyonunu hesapla.

    ``g``: HEDEF sayfanın ``pdf_donusum.geometri()`` bilgisi. Burada eskiden
    GÖRSEL yükseklik duruyordu ve `(yükseklik - y) * ölçek` ile /Rotate 0
    formülü uygulanıyordu. Oysa destination koordinatları DÖNDÜRÜLMEMİŞ
    kullanıcı uzayında; ikisini karıştırmak döndürülmüş sayfada bağlantıyı
    bambaşka bir yere götürüyor. Kardeş yol (`_events._link_at_pos`) bu
    dönüşümü zaten yapıyor, burası atlanmıştı.

    ÖLÇÜLDÜ (2026-09-05, pdflscape ile /Rotate 90 sayfa; hedefin gerçek yeri
    render edilen piksellerden okundu): olması gereken 483 px, çıkan
    -5381 px. /Rotate 0 sayfada eski ve yeni değer aynı.

    Yatay sayfa LaTeX'te istisna değil: geniş tablo ve şekiller için
    `pdflscape` tam da bunu yapıyor, ve içindekiler ile çapraz başvuru
    bağlantıları o sayfalara gidiyor.
    """
    num_params = ctypes.c_ulong()
    params = (ctypes.c_float * 4)()
    view_mode = _pdfium_raw.FPDFDest_GetView(dest, ctypes.byref(num_params), params)
    donme = g[0]

    if view_mode == _pdfium_raw.PDFDEST_VIEW_XYZ and num_params.value >= 2:
        x, y = params[0], params[1]
        if y >= 0:
            return _sinirla(gorsele(g, x, y, scale)[1])
    elif view_mode == _pdfium_raw.PDFDEST_VIEW_FITH and num_params.value >= 1:
        y = params[0]
        if y >= 0:
            # 90/270'te dikey konumu x belirliyor (bkz. dönüşüm tablosu),
            # FitH ise x vermiyor. Yanlış yere gitmektense sayfa başı.
            if donme in (90, 270):
                return 0
            return _sinirla(gorsele(g, 0.0, y, scale)[1])
    return 0


def _sinirla(vy: float) -> int:
    """Kaydırma konumu negatife düşmesin.

    Destination koordinatı sayfanın DIŞINDA olabiliyor: ölçülen bir belgede
    hyperref+pdflscape 792 pt'lik sayfada y=4200 yazmıştı. Böyle bir değer
    döndürülmüş sayfada negatif `vy` üretiyor ve görüntü sayfanın öncesine
    kayıyor.
    """
    return max(int(vy), 0)


def get_dest_page_index(pdf_raw, dest) -> int:
    """Destination'ın hedef sayfa indeksini döndür (zero-based), geçersizse -1."""
    return _pdfium_raw.FPDFDest_GetDestPageIndex(pdf_raw, dest)
