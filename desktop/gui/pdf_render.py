"""PDF sayfa render — pypdfium2 bitmap'ten QPixmap pipeline."""

from PyQt6.QtGui import QImage, QPixmap


def render_page_to_pixmap(page, scale: float, invert: bool = False) -> QPixmap:
    """Tek bir PDF sayfasını QPixmap olarak render et.

    Saf fonksiyon — widget state yok, cache yok.
    Cache ve LRU eviction çağıranın sorumluluğunda.
    """
    bitmap = page.render(scale=scale)
    pil_img = bitmap.to_pil()
    raw = pil_img.tobytes()
    w, h = pil_img.size
    stride = w * 3
    img = QImage(raw, w, h, stride, QImage.Format.Format_RGB888)
    img = img.copy()
    if invert:
        img.invertPixels()
    return QPixmap.fromImage(img)
