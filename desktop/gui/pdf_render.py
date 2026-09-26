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
    # Kilit BURADA da alınıyor, kardeşi `render_page_to_pixmap` gibi: çağıran
    # zaten tutuyor olsa bile (RLock) bu fonksiyon tek başına çağrılabilir
    # olmalı. Eskiden yalnız çağıranlara güveniliyordu ve statik kapı
    # (tests/test_pdfium_lock.py) `render`/`to_pil` adlarını tanımadığı için
    # buradaki iki çağrıyı hiç GÖRMÜYORDU. CI'da gerçekleşen segfault'un bir
    # tarafı tam da render işçisiydi (bkz. gui/pdfium_lock.py), yani korumanın
    # en çok gerektiği yol kapının kör noktasındaydı.
    #
    # `.copy()` ham tamponu ayrıştırıyor; kilit oraya kadar yetiyor,
    # invertPixels saf Qt.
    with pdfium_lock:
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


def tam_mantiksal_boy(kare, carpan: float, en=None, boy=None):
    """Kareyi sağdan ve alttan kırp: mantıksal boyu TAM sayı `en` x `boy`.

    pypdfium2 tuvali yukarı yuvarlıyor (`ceil`), etiketler aşağı (`int`).
    Çarpan 2'de 1895 satırlık kare 947.5 mantıksal satır ediyor ve Qt onu
    yarım fiziksel piksel kaydırıp ARA DEĞERLE çiziyordu. ÖLÇÜLDÜ
    (2026-09-26, QT_SCALE_FACTOR=2, kehanet pdfium'un fiziksel çizimi): en
    iyi tam sayı hizalamada bile fark 1.31, kenar enerjisi %94. Kırpılan
    en fazla iki fiziksel piksel, sayfanın kenarı.

    `en`/`boy` verilmezse karenin kendi mantıksal boyu aşağı yuvarlanıyor.
    QImage da QPixmap da olur (ikisinde de width/height/copy var).
    """
    if en is None:
        en = int(kare.width() / carpan)
    if boy is None:
        boy = int(kare.height() / carpan)
    w, h = round(en * carpan), round(boy * carpan)
    if kare.width() > w or kare.height() > h:
        kare = kare.copy(0, 0, min(kare.width(), w), min(kare.height(), h))
    return kare
