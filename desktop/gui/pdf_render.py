"""PDF sayfa render — pypdfium2 bitmap'ten QImage/QPixmap pipeline."""

from PyQt6.QtGui import QImage, QPixmap


from gui.pdfium_lock import pdfium_lock


def render_page_to_qimage(page, scale: float, invert: bool = False) -> QImage:
    """Tek bir PDF sayfasını QImage olarak render et.

    Saf fonksiyon — widget state yok, cache yok. QImage (QPixmap değil)
    döner: QPixmap oluşturmak GUI thread'inde yapılmalıdır; arka plan
    işçisi (pdf_render_worker) bu fonksiyonu kullanır, UI tarafı sonucu
    QPixmap'e sarar. .copy() buffer'ı ayrıştırır; QImage iş parçacıkları
    arası sinyalle taşınabilir.
    """
    bitmap = page.render(scale=scale)
    pil_img = bitmap.to_pil()
    raw = pil_img.tobytes()
    w, h = pil_img.size
    img = QImage(raw, w, h, w * 3, QImage.Format.Format_RGB888).copy()
    if invert:
        img.invertPixels()
    return img


def render_page_to_pixmap(page, scale: float, invert: bool = False) -> QPixmap:
    """Eşzamanlı gereken tek kullanımlık yerler için (sunum modu).

    Normal görüntüleme yolu arka plan işçisindedir (pdf_render_worker);
    cache/eviction çağıranın sorumluluğunda.
    """
    # Kilit burada da: çağıran zaten tutuyor olsa bile (RLock) bu
    # fonksiyon tek başına da çağrılabilir olmalı.
    with pdfium_lock:
        return QPixmap.fromImage(render_page_to_qimage(page, scale, invert))
