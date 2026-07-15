"""PdfViewer bookmark mixin — PDF yer imlerini gösterme ve navigasyon."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QSizePolicy

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


class PdfBookmarksMixin:

    def _setup_bookmarks_panel(self):
        self._bookmark_tree = QTreeWidget()
        self._bookmark_tree.setHeaderHidden(True)
        self._bookmark_tree.setIndentation(12)
        self._bookmark_tree.setMaximumWidth(200)
        self._bookmark_tree.setMinimumWidth(0)
        self._bookmark_tree.setRootIsDecorated(True)
        self._bookmark_tree.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Expanding)
        self._bookmark_tree.itemClicked.connect(self._on_bookmark_clicked)
        self._bookmark_tree.hide()

        t = self._theme
        self._bookmark_tree.setStyleSheet(
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; border-right: 1px solid {t['border_subtle']}; font-size: 11px; }}"
            f"QTreeWidget::item {{ padding: 2px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )

    def update_bookmarks(self):
        self._bookmark_tree.clear()
        if not self._pdf:
            self._bookmark_tree.hide()
            return

        try:
            bookmarks = list(self._pdf.get_toc())
        except Exception:
            bookmarks = []

        if not bookmarks:
            self._bookmark_tree.hide()
            return

        stack = []
        for bm in bookmarks:
            title = bm.get_title() or ""
            level = bm.level
            dest = bm.get_dest()
            page_idx = dest.get_index() if dest else None

            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, page_idx)

            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self._bookmark_tree.addTopLevelItem(item)
            stack.append((level, item))

        self._bookmark_tree.expandAll()
        if self._btn_bookmarks.isChecked():
            self._bookmark_tree.show()

    def _on_bookmark_clicked(self, item, _col):
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        if page_idx is not None and 0 <= page_idx < self._page_count:
            self._scroll_to_page(page_idx)

    def _apply_bookmark_theme(self, t):
        self._bookmark_tree.setStyleSheet(
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; border-right: 1px solid {t['border_subtle']}; font-size: 11px; }}"
            f"QTreeWidget::item {{ padding: 2px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )

    def _toggle_bookmarks(self, checked: bool):
        if checked and self._bookmark_tree.topLevelItemCount() == 0:
            self._btn_bookmarks.setChecked(False)
            return
        self._bookmark_tree.setVisible(checked)
