"""PdfViewer SyncTeX mixin — ileri/geri arama koordinat dönüşümü."""

from PyQt6.QtCore import QPoint, QTimer
from gui.pdf_donusum import geometri, gorselden_syncteze, synctex_kutusu
from gui.pdfium_lock import pdfium_lock


class PdfSyncTexMixin:

    def _handle_reverse_click(self, pos, obj):
        if not self._pdf or not self._pdf_path:
            return
        if obj != self._pages_widget and obj not in self._page_labels:
            return
        # Sayfa yönlendirmesi TEK yerden (bkz. _selection._pos_to_page).
        i, label_pos = self._pos_to_page(pos, obj)
        if i is None:
            return
        scale = self._olcek(i)
        # SyncTeX'in düzlemi /Rotate 0'da ekranla örtüşüyor ama döndürülmüş
        # sayfada örtüşmüyor (bkz. gui/pdf_donusum.py).
        with pdfium_lock:
            g = geometri(self._pdf[i])
        x_pts, y_pts = gorselden_syncteze(
            g, label_pos.x(), label_pos.y(), scale)
        self.reverse_search_requested.emit(i + 1, x_pts, y_pts, self._pdf_path)

    def scroll_to_position(self, page_num: int, x: float, y: float,
                           left: float = 0.0, width: float = 0.0, height: float = 0.0):
        # Belge denetimi ŞART, sınır denetimi tek başına YETMİYOR.
        # `_page_labels` yalnız sayfa etiketi tutmuyor: PDF açılamayınca
        # `_show_message` oraya bir mesaj etiketi koyuyor (bkz. _ui_setup)
        # ve tam o anda `_pdf` None oluyor. `len(_page_labels)` 1 olduğu için
        # aşağıdaki sınır denetimi 0'ı KABUL EDİYOR ve `self._pdf[idx]`
        # patlıyordu: TypeError, 'NoneType' object is not subscriptable
        # (ölçüldü 2026-09-06). Çağıran `synctex_ops._apply_forward` işçi
        # sonucu slot'u ve korumasız; PyQt6'da slot'tan çıkan istisna süreci
        # sonlandırıyor. Ulaşılabilir yol: başarılı bir derlemeden sonra
        # sonraki derleme bozuk PDF üretir, dosya ve eski .synctex.gz diskte
        # durduğu için ileri aramanın iki kapısı da geçer.
        # Kardeş `_handle_reverse_click` (yukarıda) bu dersi zaten biliyor.
        if not self._pdf:
            return
        idx = page_num - 1
        if idx < 0 or idx >= len(self._page_labels):
            return
        label = self._page_labels[idx]
        scale = self._olcek(idx)
        with pdfium_lock:
            g = geometri(self._pdf[idx])
        x_pixel, y_pixel, w_pixel, h_kutu = synctex_kutusu(
            g, left, y, width, height, scale)

        if label.pixmap() is None or label.pixmap().isNull():
            # Label yüklemede doğru boyutla kurulmuş; pixmap arka planda
            # gelir, vurgu/konum hesabı onu beklemez
            self._request_render(idx)

        h_pixel = h_kutu if height else 20
        self._show_highlight(label, int(x_pixel), int(y_pixel), h_pixel, w_pixel)

        abs_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y() + int(y_pixel)
        viewport_height = self._scroll.viewport().height()
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - viewport_height // 2))
        self._current_page = idx
        self._update_nav()
        QTimer.singleShot(100, self._render_visible)
