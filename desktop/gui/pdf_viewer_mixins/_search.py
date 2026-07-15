"""PdfViewer arama mixin — PDF içinde metin arama ve vurgulama."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


class PdfSearchMixin:

    def _init_search_state(self):
        self._search_results = []
        self._search_index = 0
        self._search_highlights = []

    def _do_search(self, query: str):
        self._clear_search_highlights()
        if not query or not self._pdf:
            self._update_search_nav(0, 0)
            return

        results = []
        for i in range(self._page_count):
            try:
                page = self._pdf[i]
                textpage = page.get_textpage()
                searcher = textpage.search(query)
                while True:
                    match = searcher.get_next()
                    if match is None:
                        break
                    start, count = match
                    results.append((i, start, count, textpage))
            except Exception:
                continue

        self._search_results = results
        self._search_index = 0

        if results:
            self._show_search_result(0)
        self._update_search_nav(self._search_index + 1 if results else 0, len(results))

    def _show_search_result(self, idx):
        self._clear_search_highlights()
        if idx >= len(self._search_results):
            return

        page_idx, start, count, textpage = self._search_results[idx]
        label = self._page_labels[page_idx] if page_idx < len(self._page_labels) else None
        if not label:
            return

        # Sayfayı render et (eğer henüz render edilmediyse)
        if label.pixmap() is None or label.pixmap().isNull():
            pixmap = self._render_page(page_idx)
            if not pixmap.isNull():
                label.setPixmap(pixmap)
                label.setStyleSheet("")

        # Eşleşmenin ilk karakterinin Y pozisyonunu hesapla
        scale = 1.5 * self._zoom
        try:
            left, bottom, right, top = textpage.get_charbox(start, loose=True)
            match_y = (self._pdf[page_idx].get_height() - top) * scale
        except Exception:
            match_y = 0

        # Eşleşme konumuna scroll
        abs_y = label.pos().y() + int(match_y)
        viewport_height = self._scroll.viewport().height()
        self._scroll.verticalScrollBar().setValue(max(0, abs_y - viewport_height // 3))
        self._current_page = page_idx
        self._update_nav()

        self._draw_search_highlight(idx)

    def _draw_search_highlight(self, idx):
        self._clear_search_highlights()
        if idx >= len(self._search_results):
            return

        page_idx, start, count, textpage = self._search_results[idx]
        label = self._page_labels[page_idx] if page_idx < len(self._page_labels) else None
        if not label or label.pixmap() is None or label.pixmap().isNull():
            return

        scale = 1.5 * self._zoom
        t = self._theme

        for ci in range(start, start + count):
            try:
                left, bottom, right, top = textpage.get_charbox(ci, loose=True)
            except Exception:
                continue

            # PDF koordinatları: origin sol-alt, Qt: sol-üst
            x = left * scale
            y = (self._pdf[page_idx].get_height() - top) * scale
            w = (right - left) * scale
            h = (top - bottom) * scale

            hl = QLabel(label)
            hl.setStyleSheet(
                f"background-color: {t['pdf_hl_bg']}; "
                f"border: 1px solid {t['pdf_hl_border']}; "
                "border-radius: 1px;"
            )
            hl.setGeometry(int(x), int(y), max(int(w), 2), max(int(h), 4))
            hl.show()
            hl.raise_()
            self._search_highlights.append(hl)

    def _search_next(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index + 1) % len(self._search_results)
        self._show_search_result(self._search_index)
        self._update_search_nav(self._search_index + 1, len(self._search_results))

    def _search_prev(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index - 1) % len(self._search_results)
        self._show_search_result(self._search_index)
        self._update_search_nav(self._search_index + 1, len(self._search_results))

    def _clear_search_highlights(self):
        for hl in self._search_highlights:
            try:
                hl.deleteLater()
            except RuntimeError:
                pass
        self._search_highlights = []

    def _clear_search(self):
        self._clear_search_highlights()
        self._search_results = []
        self._search_index = 0
        self._update_search_nav(0, 0)

    def _update_search_nav(self, current, total):
        if hasattr(self, '_search_count_label'):
            self._search_count_label.setText(f"{current} / {total}" if total > 0 else _("bulunamadı"))

    def _toggle_search_bar(self):
        visible = self._search_bar_widget.isVisible()
        if visible:
            self._close_search()
        else:
            self._search_bar_widget.show()
            self._search_input.setFocus()
            self._search_input.selectAll()

    def _close_search(self):
        self._search_bar_widget.hide()
        self._clear_search()

    def _on_search_return(self):
        query = self._search_input.text().strip()
        if not query:
            return
        if query == getattr(self, '_last_search_query', None) and self._search_results:
            self._search_next()
        else:
            self._last_search_query = query
            self._do_search(query)

    def _apply_search_theme(self, t):
        if not hasattr(self, '_search_input'):
            return
        self._search_input.setStyleSheet(
            f"QLineEdit {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; border-radius: 3px; padding: 2px 6px; font-size: 11px; }}"
        )
        for btn in (self._search_prev_btn, self._search_next_btn, self._search_close_btn):
            btn.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; }}"
                f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
            )
        self._search_count_label.setStyleSheet(f"color: {t['fg_muted']}; font-size: 11px;")
        self._btn_search.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; border-radius: 3px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; }}"
            f"QPushButton:disabled {{ opacity: 0.3; }}"
        )
