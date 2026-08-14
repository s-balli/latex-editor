"""Editör ayarları dialogu — tab genişliği, font boyutu, satır kaydırma.

Değerleri QSettings'e yazmak/okumak MainWindow'un işi; dialog yalnızca
mevcut değerleri gösterir ve onaylanınca `values()` ile geri verir.
"""

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QCheckBox, QFormLayout, QSpinBox,
)

_ = lambda s: QCoreApplication.translate("EditorSettingsDialog", s)


class EditorSettingsDialog(QDialog):
    def __init__(self, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Editör Ayarları"))
        self.setMinimumWidth(320)

        form = QFormLayout(self)

        self._tab = QSpinBox()
        self._tab.setRange(2, 8)
        self._tab.setValue(current.get("tab_width", 4))
        form.addRow(_("Tab genişliği"), self._tab)

        self._font = QSpinBox()
        self._font.setRange(8, 24)
        self._font.setSuffix(" pt")
        self._font.setValue(current.get("font_size", 11))
        form.addRow(_("Font boyutu"), self._font)

        self._wrap = QCheckBox(_("Uzun satırları kaydır"))
        self._wrap.setChecked(current.get("wrap", True))
        form.addRow("", self._wrap)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {
            "tab_width": self._tab.value(),
            "font_size": self._font.value(),
            "wrap": self._wrap.isChecked(),
        }
