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

# Editörün açabildiği dosya türleri (sürükle-bırak/_open_file_in_editor ile
# aynı küme). TEK KAYNAK: yorumun söylediği "aynı küme" artık gerçekten aynı
# nesne; eskiden burada ayrı bir kopya duruyordu.
from core.fs_ops import KAYNAK_UZANTILARI as _EXT_FILES
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


def _aralik(q: str, p: str, bas: int) -> int | None:
    """``p[bas:]`` içinde ``q``nun yayıldığı aralık; eşleşmezse None.

    Alt dizi: sıra korunur, ardışıklık şart değil. Her karakterin ilk geçişi
    alınır (açgözlü).
    """
    qi = 0
    first, last = -1, -1
    for i in range(bas, len(p)):
        if qi < len(q) and p[i] == q[qi]:
            if first == -1:
                first = i
            last = i
            qi += 1
    if qi < len(q):
        return None
    return last - first


def fuzzy_score(query: str, path: str) -> int | None:
    """Bulanık eşleşme skoru. Küçük skor daha iyi; eşleşmezse None.

    ÖNCE DOSYA ADINDA aranıyor, sonra tüm yolda. Eskiden tarama her zaman
    yolun BAŞINDAN başlıyordu; sorgu DİZİN adında da geçtiğinde o dizindeki
    bütün dosyalar aynı puanı alıyor, dosya adı hiç rol oynamıyordu.
    Eşitlik alfabetik bozulduğu için Enter YANLIŞ DOSYAYI açıyordu, üstelik
    en yaygın yerleşimlerde. ÖLÇÜLDÜ (2026-09-05):

        bolumler/ içinde "bolum"   ->  bolumler/baslik.tex   açılıyordu
        chapters/ içinde "chapter" ->  chapters/abstract.tex açılıyordu
        sekiller/ içinde "sekil"   ->  sekiller/aciklama.tex açılıyordu

    Depodaki 59 gerçek şablonda da 3 vaka çıktı (Título-autores-resumo-
    palavras/ klasörü); orada aranan dosya 5. sıraya kadar düşüyordu.

    Tek düzeydeki projelerde (dizin yok) davranış birebir aynı: dosya adı
    zaten yolun tamamı.
    """
    if not query:
        return 0
    q = query.lower()
    p = path.lower()
    base_start = p.rfind('/') + 1
    aralik = _aralik(q, p, base_start)
    if aralik is not None:
        return aralik - 5          # eşleşme dosya adına oturmuş → bonus
    return _aralik(q, p, 0)


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
        self._edit.setPlaceholderText(_("Dosya adı yazın: Enter açar, Esc kapatır"))
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
