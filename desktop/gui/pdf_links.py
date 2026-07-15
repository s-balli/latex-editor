"""PDF link çözümleme — pypdfium2 ctypes çağrıları."""

import ctypes

from pypdfium2 import raw as _pdfium_raw


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


def resolve_dest_scroll_y(pdf_raw, dest, page_height: float, scale: float) -> int:
    """PDF destination'ın scroll Y pozisyonunu hesapla."""
    num_params = ctypes.c_ulong()
    params = (ctypes.c_float * 4)()
    view_mode = _pdfium_raw.FPDFDest_GetView(dest, ctypes.byref(num_params), params)

    if view_mode == _pdfium_raw.PDFDEST_VIEW_XYZ and num_params.value >= 2:
        y = params[1]
        if y >= 0:
            return int((page_height - y) * scale)
    elif view_mode == _pdfium_raw.PDFDEST_VIEW_FITH and num_params.value >= 1:
        y = params[0]
        if y >= 0:
            return int((page_height - y) * scale)
    return 0


def get_dest_page_index(pdf_raw, dest) -> int:
    """Destination'ın hedef sayfa indeksini döndür (zero-based), geçersizse -1."""
    return _pdfium_raw.FPDFDest_GetDestPageIndex(pdf_raw, dest)
