import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton,
)

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("OutlinePanel", s)

# Bölüm başlığının YALNIZ AÇILIŞI. Başlığın kendisi regex'le değil
# _baslik_oku ile okunur; gerekçesi orada.
#   (?:\[[^\]]*\])?   — \chapter[Giriş]{Giriş ve Kapsam} biçimindeki KISA
#                       başlık argümanı. Desende yokken bu satırlar hiç
#                       eşleşmiyordu, yani uzun başlıklı tez bölümleri
#                       anahatta HİÇ görünmüyordu (standart kullanım).
_RE_SECTION_BAS = re.compile(
    r'\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)'
    r'\*?\s*(?:\[[^\]]*\])?\s*\{'
)


def _baslik_oku(text: str, i: int) -> str | None:
    r"""Açılış `{`sinden SONRAKİ i konumundan başlığı AYRAÇ SAYARAK oku.

    Regex'in yapamadığını yapar: keyfi derinlikte iç içe küme. Önceki desen
    `((?:[^{}]|\{[^{}]*\})*)` ile tek düzeye izin veriyordu ve
    `\section{A \textbf{\emph{B}} C}` ikinci düzeyde kırpılıyordu — desene
    bir düzey daha eklemek de sınırı bir kaydırmaktan başka işe yaramazdı.

    Ters bölü kaçışları atlanır (`\{`, `\}`, `\\`); yoksa `\section{Küme
    \{a,b\}}` ilk `\}`de kapanmış sayılır, başlık yanlış kesilirdi. İki
    karakter atlamak komut adlarının ilk harfini de yutar (`\emph` → `mph`),
    zararsız: sayılan tek şey ayraçlar.

    Küme hiç kapanmazsa None döner — yarım yazılmış bölüm satırı anahata
    girmez (eski desen de eşleşmiyordu, davranış aynı).
    """
    derinlik = 1
    j = i
    n = len(text)
    while j < n:
        c = text[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            derinlik += 1
        elif c == '}':
            derinlik -= 1
            if derinlik == 0:
                return text[i:j]
        j += 1
    return None

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
        # Genişletme tercihleri yeniden kurulumda korunur: ağaç her düzenlemede
        # (500ms debounce) sıfırdan kuruluyordu; elle daraltılan/genişletilen
        # düğümler kayboluyordu. Anahtar: başlık zinciri yolu.
        if self._items:
            old_expanded, old_all = self._collect_expansion_state()
        else:
            old_expanded, old_all = None, None

        self._tree.clear()
        self._items = []

        stack = []
        # Satır numaraları artımlı sayılır: her eşleşme için metnin başından
        # yeniden saymak (text[:m.start()].count) bölüm sayısıyla çarpılan
        # kare maliyet üretiyordu; burada imleç konumundan devam edilir.
        line = 0
        line_pos = 0  # `line` numaralı satırın başlangıç offseti
        for match in _RE_SECTION_BAS.finditer(text):
            # Yorum içinde mi kontrol et
            line_start = text.rfind('\n', 0, match.start()) + 1
            line_text = text[line_start:match.start()]
            if '%' in line_text:
                continue

            ham_baslik = _baslik_oku(text, match.end())
            if ham_baslik is None:
                continue                # küme kapanmamış

            line += text.count('\n', line_pos, match.start())
            line_pos = match.start()

            cmd = match.group(1)
            title = ham_baslik.strip()
            level = _LEVEL[cmd]

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

        # Genişletme durumunu geri uygula. Eski ağaç yoksa (ilk kurulum)
        # varsayılan: en üst seviye açık. Eski ağaç varsa: bilinen düğümler
        # eski durumlarına döner, yeni düğümler varsayılanı alır.
        if old_expanded is None:
            for i in range(self._tree.topLevelItemCount()):
                self._tree.expandItem(self._tree.topLevelItem(i))
        else:
            for item in self._items:
                key = self._item_path(item)
                top = item.parent() is None
                if key in old_all:
                    item.setExpanded(key in old_expanded)
                else:
                    item.setExpanded(top)

    @staticmethod
    def _item_path(item) -> tuple:
        """Düğümün başlık-zinciri yolu ('Giriş' > 'Alt' gibi); yeniden kurulan
        ağaçta aynı düğümü eşlemek için anahtar."""
        parts = []
        cur = item
        while cur is not None:
            parts.append(cur.text(0))
            cur = cur.parent()
        return tuple(reversed(parts))

    def _collect_expansion_state(self) -> tuple[set, set]:
        """(genişletilmiş yollar, tüm yollar) — genişletme tercihleri."""
        expanded, all_keys = set(), set()

        def walk(item):
            key = self._item_path(item)
            all_keys.add(key)
            if item.isExpanded():
                expanded.add(key)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return expanded, all_keys

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
