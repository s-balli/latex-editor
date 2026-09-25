"""PdfViewer bookmark mixin — PDF yer imlerini gösterme ve navigasyon."""

from PyQt6.QtCore import Qt

from gui.pdfium_lock import pdfium_lock
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QSizePolicy

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


def _bm_title(bm) -> str:
    """Yer imi başlığı. pypdfium2 sürümleri arası: get_title() (eski PdfBookmark)
    veya .title (yeni PdfOutlineItem)."""
    fn = getattr(bm, "get_title", None)
    if callable(fn):
        return fn() or ""
    return getattr(bm, "title", "") or ""


def _bm_level(bm) -> int:
    """Yer imi seviyesi (her iki API'de de attribute)."""
    return getattr(bm, "level", 0) or 0


def _bm_page_index(bm):
    """Sayfa indeksi. .page_index (yeni PdfOutlineItem) yoksa
    get_dest().get_index() (eski PdfBookmark) dener."""
    pi = getattr(bm, "page_index", None)
    if pi is not None:
        return pi
    get_dest = getattr(bm, "get_dest", None)
    dest = get_dest() if callable(get_dest) else getattr(bm, "dest", None)
    if dest:
        get_index = getattr(dest, "get_index", None)
        if callable(get_index):
            try:
                return get_index()
            except Exception:
                return None
    return None


def _bm_gorunum(bm):
    """Hedef görünümü (mod, parametreler) ya da None. `.view_mode`/`.view_pos`
    (PdfOutlineItem, pypdfium2 4.x) yoksa get_dest().get_view() (5.x)."""
    mod = getattr(bm, "view_mode", None)
    if mod is not None:
        return mod, list(getattr(bm, "view_pos", None) or [])
    get_dest = getattr(bm, "get_dest", None)
    dest = get_dest() if callable(get_dest) else None
    get_view = getattr(dest, "get_view", None) if dest else None
    if callable(get_view):
        try:
            mod, konum = get_view()
            return mod, list(konum)
        except Exception:
            return None
    return None


# Öğede sayfa indeksinin (UserRole) yanında hedefin görünümü.
_GORUNUM_ROLU = Qt.ItemDataRole.UserRole + 1


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

    def _yer_imi_yollari(self):
        """(öğe, kökten başlık yolu) çiftleri; anahat panelindeki anahtar."""
        yigin = [(self._bookmark_tree.topLevelItem(i), ())
                 for i in range(self._bookmark_tree.topLevelItemCount())]
        while yigin:
            item, ust = yigin.pop()
            yol = ust + (item.text(0),)
            yield item, yol
            yigin.extend((item.child(j), yol) for j in range(item.childCount()))

    def update_bookmarks(self):
        # Kullanıcının KAPATTIĞI düğümler yeniden yüklemede korunuyor, anahat
        # panelinin yaptığı gibi. ÖLÇÜLDÜ (2026-09-25): kapatılan bölüm her
        # derlemede (otomatik derlemede her Ctrl+S) yeniden açılıyordu,
        # anahat paneli aynı durumda kapalı tutuyordu.
        kapali = {yol for item, yol in self._yer_imi_yollari()
                  if item.childCount() and not item.isExpanded()}
        self._bookmark_tree.clear()
        if not self._pdf:
            self._bookmark_tree.hide()
            return

        # Kilit YALNIZ get_toc'u sarmalıyordu; başlık ve sayfa indeksi
        # okumaları döngüde, kilidin DIŞINDA kalıyordu. `_bm_title` ve
        # `_bm_page_index` pdfium'a giriyor (get_title, get_dest().get_index)
        # ve pdfium küresel durum tuttuğu için render işçisiyle aynı anda
        # çağrılmaları segfault sınıfı (bkz. gui/pdfium_lock.py). Çıkarma
        # artık kilit altında; ağaç kurulumu dışarıda, çünkü Qt tarafı
        # pdfium'a dokunmuyor ve kilit kısa tutulmalı.
        try:
            with pdfium_lock:
                girdiler = [(_bm_title(bm), _bm_level(bm), _bm_page_index(bm),
                             _bm_gorunum(bm))
                            for bm in self._pdf.get_toc()]
        except Exception:
            girdiler = []

        if not girdiler:
            self._bookmark_tree.hide()
            return

        stack = []
        for title, level, page_idx, gorunum in girdiler:
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, page_idx)
            item.setData(0, _GORUNUM_ROLU, gorunum)

            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].addChild(item)
            else:
                self._bookmark_tree.addTopLevelItem(item)
            stack.append((level, item))

        self._bookmark_tree.expandAll()
        for item, yol in self._yer_imi_yollari():
            if yol in kapali:
                item.setExpanded(False)
        if self._btn_bookmarks.isChecked():
            self._bookmark_tree.show()

    def _on_bookmark_clicked(self, item, _col):
        # Hedefin KONUMUNA, iç bağlantının gittiği yere; yalnız sayfa başına
        # değil. ÖLÇÜLDÜ (2026-09-25, gerçek hyperref PDF'i): sayfanın alt
        # yarısındaki bir alt bölümün yer imi sayfa başını gösteriyordu ve
        # başlık görüntünün dışında kalıyordu; aynı hedefe giden içindekiler
        # bağlantısı başlığa iniyordu.
        page_idx = item.data(0, Qt.ItemDataRole.UserRole)
        if page_idx is None or not (0 <= page_idx < self._page_count):
            return
        gorunum = item.data(0, _GORUNUM_ROLU)
        if gorunum:
            self._gorunume_git(page_idx, *gorunum)
        else:
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
