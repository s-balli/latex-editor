"""PdfViewer event filter mixin — sunum/sayfa olay yonlendirme + link tiklama + metin secme."""

import webbrowser

from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer

from gui.pdfium_lock import pdfium_lock
from gui.pdf_donusum import geometri, kullaniciya

from gui.pdf_links import (
    get_link_at_point, resolve_link_action, resolve_dest_scroll_y, get_dest_page_index,
)


class PdfEventsMixin:

    def eventFilter(self, obj, event):
        if self._presentation_mode and obj in (self._presentation_widget, self._presentation_label):
            return self._handle_presentation_event(event)
        return self._handle_page_event(event, obj)

    def _handle_presentation_event(self, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            self._presentation_key_event(event)
            return True
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and self._current_page < self._page_count - 1:
                self._current_page += 1
                self._update_nav()
                self._presentation_render()
            elif event.button() == Qt.MouseButton.RightButton and self._current_page > 0:
                self._current_page -= 1
                self._update_nav()
                self._presentation_render()
            return True
        if event.type() == QEvent.Type.MouseMove:
            return True
        return super().eventFilter(self._presentation_widget, event)

    def _handle_page_event(self, event, obj) -> bool:
        # pos sadece fare olaylarinda gecerli
        if event.type() not in (
            QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseMove, QEvent.Type.MouseButtonDblClick,
        ):
            return super().eventFilter(obj, event)

        pos = event.position().toPoint()

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                if self._selection_right_click(pos, obj):
                    return True
                return super().eventFilter(obj, event)

            if event.button() == Qt.MouseButton.LeftButton:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._handle_reverse_click(pos, obj)
                    return True
                self._selection_press(pos, obj)
                return super().eventFilter(obj, event)

        elif event.type() == QEvent.Type.MouseMove:
            if event.buttons() & Qt.MouseButton.LeftButton and self._selection_start_label_pos is not None:
                if self._selection_move(pos, obj):
                    return True
            self._update_link_cursor(pos, obj)
            return super().eventFilter(obj, event)

        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._selection_start_label_pos is not None:
                if self._selection_release(pos, obj):
                    return True
            return super().eventFilter(obj, event)

        elif event.type() == QEvent.Type.MouseButtonDblClick:
            if event.button() == Qt.MouseButton.LeftButton:
                self._selection_dblclick(pos, obj)
                return True

        return super().eventFilter(obj, event)

    def _link_at_pos(self, pos, obj):
        if not self._pdf:
            return None
        if obj != self._pages_widget and obj not in self._page_labels:
            return None
        # Sayfa yönlendirmesi TEK yerden: kardeş etikete `mapFrom` çağırmak
        # yanlış sayfaya götürüyordu (bkz. _selection._pos_to_page).
        i, label_pos = self._pos_to_page(pos, obj)
        if i is None:
            return None
        scale = self._olcek(i)
        with pdfium_lock:
            page = self._pdf[i]
            if not page.raw:
                return None
            # `get_link_at_point` DÖNDÜRÜLMEMİŞ kullanıcı uzayı bekliyor;
            # `get_height()` GÖRSEL boyut veriyor ve /Rotate'li sayfada bu
            # karışım yanlış noktaya bakıyordu (bkz. gui/pdf_donusum.py).
            x_pts, y_pdf = kullaniciya(geometri(page), label_pos.x(),
                                       label_pos.y(), scale)
            link = get_link_at_point(page.raw, x_pts, y_pdf)
        return (i, link, page) if link else None

    def _handle_link_click(self, pos, obj):
        result = self._link_at_pos(pos, obj)
        if not result:
            return
        _, link, _page_ref = result
        # Kilit yalnız pdfium çağrısını sarar: webbrowser.open ve _goto_dest
        # dışarıda kalmalı (ikisi de uzun sürebilir, _goto_dest ayrıca render
        # işçisinin _cond'una dokunuyor — kilit sırası bozulmasın).
        with pdfium_lock:
            resolved = resolve_link_action(self._pdf.raw, link)
        if not resolved:
            return
        kind, data = resolved
        if kind == "uri":
            webbrowser.open(data)
        elif kind in ("goto", "dest"):
            self._goto_dest(data)

    def _goto_dest(self, dest):
        with pdfium_lock:
            page_idx = get_dest_page_index(self._pdf.raw, dest)
        if page_idx < 0 or page_idx >= self._page_count:
            return
        idx = page_idx
        label = self._page_labels[idx]

        if label.pixmap() is None or label.pixmap().isNull():
            self._request_render(idx)

        scale = self._olcek(idx)
        with pdfium_lock:
            # geometri(): dönme + DÖNDÜRÜLMEMİŞ boyut. Eskiden buraya
            # get_height() (GÖRSEL yükseklik) veriliyordu; /Rotate'li sayfada
            # bağlantı bambaşka bir yere gidiyordu (bkz. pdf_links).
            scroll_y = resolve_dest_scroll_y(
                self._pdf.raw, dest, geometri(self._pdf[idx]), scale)

        # Dual modda label satır widget'ının çocuğudur: pos() satıra göre olur.
        # _synctex.py'deki gibi pages_widget'e göre hesapla.
        abs_y = label.mapTo(self._pages_widget, QPoint(0, 0)).y() + scroll_y
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - 20))
        self._current_page = idx
        self._update_nav()
        QTimer.singleShot(100, self._render_visible)

    def _update_link_cursor(self, pos, obj):
        has_link = self._link_at_pos(pos, obj) is not None
        cursor = Qt.CursorShape.PointingHandCursor if has_link else Qt.CursorShape.ArrowCursor
        self._pages_widget.setCursor(cursor)
