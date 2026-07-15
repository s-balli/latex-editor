import re

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton,
)

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("OutlinePanel", s)

_RE_SECTION = re.compile(
    r'\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)'
    r'\*?\{([^}]*)\}'
)

_LEVEL = {
    'part': 0,
    'chapter': 1,
    'section': 2,
    'subsection': 3,
    'subsubsection': 4,
    'paragraph': 5,
    'subparagraph': 6,
}

_PREFIX = {
    'part': 'Part',
    'chapter': 'Ch',
}


class OutlinePanel(QWidget):
    goto_line_requested = pyqtSignal(int)

    def __init__(self, parent=None, *, theme: dict = None):
        super().__init__(parent)
        self._items = []
        self._theme = theme or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        t = self._theme

        header = QHBoxLayout()
        header.setContentsMargins(8, 6, 4, 4)
        title = QLabel(_("ANAHAT"))
        self._title_label = title
        title.setStyleSheet(f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        collapse_btn = QPushButton("")
        collapse_btn.setFixedSize(20, 20)
        collapse_btn.setToolTip(_("Tümünü Daralt"))
        self._collapse_btn = collapse_btn
        collapse_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
        )
        collapse_btn.setText("⊟")
        collapse_btn.clicked.connect(self._collapse_all)
        header.addWidget(collapse_btn)

        expand_btn = QPushButton("")
        expand_btn.setFixedSize(20, 20)
        expand_btn.setToolTip(_("Tümünü Genişlet"))
        self._expand_btn = expand_btn
        expand_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
        )
        expand_btn.setText("⊞")
        expand_btn.clicked.connect(self._expand_all)
        header.addWidget(expand_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        layout.addWidget(header_widget)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(16)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; font-size: 12px; }}"
            f"QTreeWidget::item {{ padding: 2px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        self.setMinimumWidth(120)
        self.setMaximumWidth(350)

    def update_outline(self, text: str):
        self._tree.clear()
        self._items = []

        stack = []
        for match in _RE_SECTION.finditer(text):
            # Yorum içinde mi kontrol et
            line_start = text.rfind('\n', 0, match.start()) + 1
            line_text = text[line_start:match.start()]
            if '%' in line_text:
                continue

            cmd = match.group(1)
            title = match.group(2).strip()
            level = _LEVEL[cmd]
            line = text[:match.start()].count('\n')

            prefix = _PREFIX.get(cmd, '')
            label = f"{prefix}: {title}" if prefix else title

            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, line)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, level)

            t = self._theme
            colors = {
                0: t["outline_part"],
                1: t["outline_chapter"],
                2: t["outline_section"],
                3: t["outline_subsection"],
                4: t["outline_subsubsection"],
                5: t["outline_paragraph"],
                6: t["outline_subparagraph"],
            }
            item.setForeground(0, QColor(colors.get(level, t["fg_primary"])))

            # Hiyerarşi: stack'ten bu seviyeden yüksek olanları çıkar
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)

            stack.append((level, item))
            self._items.append(item)

        # İlk seviyeyi genişlet
        for i in range(self._tree.topLevelItemCount()):
            self._tree.expandItem(self._tree.topLevelItem(i))

    def _on_item_clicked(self, item, _column):
        line = item.data(0, Qt.ItemDataRole.UserRole)
        if line is not None:
            self.goto_line_requested.emit(line)

    def _collapse_all(self):
        self._tree.collapseAll()

    def _expand_all(self):
        self._tree.expandAll()

    def apply_theme(self, t: dict):
        self._theme = t
        self._title_label.setStyleSheet(f"color: {t['fg_muted']}; font-size: 11px; font-weight: bold;")
        self._collapse_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
        )
        self._expand_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t['fg_muted']}; border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {t['fg_primary']}; }}"
        )
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {t['bg_secondary']}; color: {t['fg_primary']}; border: none; font-size: 12px; }}"
            f"QTreeWidget::item {{ padding: 2px 4px; }}"
            f"QTreeWidget::item:hover {{ background: {t['bg_hover']}; }}"
            f"QTreeWidget::item:selected {{ background: {t['bg_pressed']}; }}"
        )
        # Mevcut öğelerin renklerini güncelle
        colors = {
            0: t["outline_part"], 1: t["outline_chapter"], 2: t["outline_section"],
            3: t["outline_subsection"], 4: t["outline_subsubsection"],
            5: t["outline_paragraph"], 6: t["outline_subparagraph"],
        }
        for item in self._items:
            level = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if level is not None:
                item.setForeground(0, QColor(colors.get(level, t["fg_primary"])))
