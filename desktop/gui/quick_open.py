"""Ctrl+P hızlı dosya açma — bulanık filtre + proje dosyaları listesi.

VS Code tarzı: yaz → anında filtrele → Enter ile aç. Dosya kaynağı, dosya
ağacının köküdür (klasör açılmadan çalışmaz).
"""

import os

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from core.project_search import SKIP_DIRS as _SKIP_DIRS

_ = lambda s: QCoreApplication.translate("QuickOpenDialog", s)

# Editörün açabildiği dosya türleri (sürükle-bırak/_open_file_in_editor ile aynı küme)
_EXT_FILES = (".tex", ".cls", ".sty", ".bib")
_MAX_LISTED = 200


def collect_project_files(root: str) -> list[str]:
    """Kök altındaki düzenlenebilir dosyalar; köke göre göreli yol, sıralı.

    Gizli dizinlere inilmez; resim dizinleri (media/ vb.) uzantı filtresiyle
    doğal olarak elenir. Yol ayracı her platformda '/'tir.
    """
    rels = []
    for dirpath, dirs, files in os.walk(root):
        # Dosya ağacıyla aynı atlama kuralları: node_modules/venv gibi büyük
        # ilgisiz dizinlere inilmesin (WSL'de yürüyüş maliyeti yüksek).
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in _SKIP_DIRS]
        for fn in files:
            if fn.lower().endswith(_EXT_FILES):
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                rels.append(rel.replace(os.sep, '/'))
    return sorted(rels)


def fuzzy_score(query: str, path: str) -> int | None:
    """Alt dizi (sıra korunur, ardışıklık şart değil) bulanık eşleşme skoru.

    Küçük skor daha iyi: eşleşmenin yayıldığı aralık kısa olan ve dosya adı
    içinde eşleşen önde gelir. Eşleşmezse None.
    """
    if not query:
        return 0
    q = query.lower()
    p = path.lower()
    base_start = p.rfind('/') + 1
    qi = 0
    first, last = -1, -1
    for i, ch in enumerate(p):
        if qi < len(q) and ch == q[qi]:
            if first == -1:
                first = i
            last = i
            qi += 1
    if qi < len(q):
        return None
    score = last - first
    if first >= base_start:
        score -= 5          # eşleşme dosya adına oturmuş → bonus
    return score


class QuickOpenDialog(QDialog):
    """Yazarak filtrelenen, Enter ile açılan hızlı dosya seçme dialogu."""

    def __init__(self, root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Hızlı Dosya Aç"))
        self.setModal(True)
        self.resize(560, 380)
        self._root = root
        self._files = collect_project_files(root)

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(_("Dosya adı yazın — Enter açar, Esc kapatır"))
        self._edit.textChanged.connect(self._refilter)
        self._edit.returnPressed.connect(self.accept)
        self._edit.installEventFilter(self)
        self._edit.setFocus()

        self._list = QListWidget()
        self._list.itemActivated.connect(lambda _item: self.accept())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._edit)
        layout.addWidget(self._list)

        self._refilter()

    def eventFilter(self, obj, event):
        """Yazma alanında Yukarı/Aşağı → listede gezinme (fare bırakmadan)."""
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down,
                       Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
                QApplication.sendEvent(self._list, event)
                return True
        return super().eventFilter(obj, event)

    def _refilter(self):
        query = self._edit.text().strip()
        scored = []
        for rel in self._files:
            s = fuzzy_score(query, rel)
            if s is not None:
                scored.append((s, rel))
        scored.sort(key=lambda t: (t[0], t[1]))
        self._list.clear()
        for _s, rel in scored[:_MAX_LISTED]:
            self._list.addItem(QListWidgetItem(rel))
        if self._list.count():
            self._list.setCurrentRow(0)

    def selected_path(self) -> str:
        item = self._list.currentItem()
        if item is None:
            return ""
        return os.path.normpath(os.path.join(self._root, item.text()))

    @staticmethod
    def pick(root: str, parent=None) -> str:
        """Dialogu aç; seçilen mutlak yolu (iptal edilirse boş) döndür."""
        dlg = QuickOpenDialog(root, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_path()
        return ""
