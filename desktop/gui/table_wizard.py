"""Tablo sihirbazı dialogu — grid düzenleme + seçenekler + canlı kod önizleme.

Üretim çekirdeği core/latex_tables.py'dedir (saf fonksiyonlar); bu dialog
yalnızca değerleri toplar ve önizler. Mevcut bir tabular bloğu düzenleniyorsa
`load_block` ile hücreler/spec doldurulur.
"""

import csv
import re

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from core.latex_tables import (
    TableOptions, build_tabular, csv_to_rows, extract_caption_label,
    parse_first_tabular, suggest_label, unescape_cell,
)

_ = lambda s: QCoreApplication.translate("TableWizardDialog", s)

# Hizalama seçenekleri: (etiket, token)
_ALIGNS = [
    (_("Sol (l)"), "l"),
    (_("Orta (c)"), "c"),
    (_("Sağ (r)"), "r"),
    (_("Paragraf (p{3cm})"), "p"),
]

_ENVS = ("tabular", "tabularx", "longtable")


class TableWizardDialog(QDialog):
    """Hücrelere yazarak/CSV yükleyerek LaTeX tablosu üret."""

    def __init__(self, parent=None, *, existing_labels: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(_("Tablo Sihirbazı"))
        self.setMinimumSize(640, 520)
        self._existing = list(existing_labels or [])
        self._label_manual = False
        self._updating = False
        self._setup_ui()
        self._update_preview()

    # --- kurulum ---

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # Üst bar: boyut + ortam
        top = QHBoxLayout()
        top.addWidget(QLabel(_("Satır")))
        self._rows = QSpinBox()
        # Sınırlar geniş: CSV yüklemesi spinbox üst sınırına takılırsa değer
        # kırpılır ama grid gerçek boyutu alır; kullanıcı sonra spinbox'a
        # dokununca satırlar sessizce KAYBEDİLİRDİ (100 satır sınırı bunu
        # yapıyordu). 1000 satır / 30 kolon pratik üst sınırdır.
        self._rows.setRange(1, 1000)
        self._rows.setValue(3)
        top.addWidget(self._rows)
        top.addWidget(QLabel(_("Sütun")))
        self._cols = QSpinBox()
        self._cols.setRange(1, 30)
        self._cols.setValue(3)
        top.addWidget(self._cols)
        top.addSpacing(12)
        top.addWidget(QLabel(_("Ortam")))
        self._env = QComboBox()
        self._env.addItems(list(_ENVS))
        top.addWidget(self._env)
        top.addStretch()
        self._btn_csv = QPushButton(_("CSV Yükle..."))
        top.addWidget(self._btn_csv)
        self._btn_code = QPushButton(_("Koddan Yükle..."))
        top.addWidget(self._btn_code)
        root.addLayout(top)

        # Hücre grid'i
        self._grid = QTableWidget(self._rows.value(), self._cols.value())
        root.addWidget(self._grid, 2)

        # Kolon hizalamaları
        align_row = QHBoxLayout()
        align_row.addWidget(QLabel(_("Hizalama:")))
        self._align_box = QHBoxLayout()
        align_row.addLayout(self._align_box)
        align_row.addStretch()
        root.addLayout(align_row)

        # Seçenekler
        opts = QGridLayout()
        self._cb_booktabs = QCheckBox(_("booktabs kuralları (toprule/midrule)"))
        self._cb_booktabs.setChecked(True)
        self._cb_header = QCheckBox(_("İlk satır başlık"))
        self._cb_header.setChecked(True)
        self._cb_vlines = QCheckBox(_("Dikey çizgiler (|)"))
        self._cb_wrap = QCheckBox(_("table kılıfı (caption + label)"))
        self._cb_wrap.setChecked(True)
        opts.addWidget(self._cb_booktabs, 0, 0)
        opts.addWidget(self._cb_header, 0, 1)
        opts.addWidget(self._cb_vlines, 1, 0)
        opts.addWidget(self._cb_wrap, 1, 1)
        root.addLayout(opts)

        # Caption + label
        meta = QFormLayout()
        self._caption = QLineEdit()
        self._caption.setPlaceholderText(_("Tablo başlığı (caption)"))
        self._label = QLineEdit()
        self._label.setPlaceholderText("tab:...")
        meta.addRow(_("Başlık"), self._caption)
        meta.addRow(_("Etiket"), self._label)
        root.addLayout(meta)

        # Önizleme
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(160)
        root.addWidget(self._preview, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(_("Ekle"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # Sinyaller
        self._rows.valueChanged.connect(self._resize_grid)
        self._cols.valueChanged.connect(self._on_cols_changed)
        self._env.currentTextChanged.connect(self._on_env_changed)
        self._btn_csv.clicked.connect(self._load_csv)
        self._btn_code.clicked.connect(self._load_from_code)
        self._caption.textChanged.connect(self._on_caption_changed)
        self._label.textEdited.connect(lambda _t: setattr(self, "_label_manual", True))
        self._grid.itemChanged.connect(self._on_grid_changed)
        for cb in (self._cb_booktabs, self._cb_header, self._cb_vlines, self._cb_wrap):
            cb.toggled.connect(self._update_preview)
        self._on_cols_changed()

    def apply_theme(self, t: dict):
        """Koyu temayla uyumlu basit stil (ana pencereden çağrılır)."""
        self.setStyleSheet(
            f"QDialog {{ background: {t['bg_secondary']}; }}"
            f"QLabel {{ color: {t['fg_primary']}; }}"
            f"QLineEdit, QSpinBox, QComboBox {{ background: {t['bg_button']};"
            f" color: {t['fg_primary']}; border: 1px solid {t['border_input']}; padding: 3px 6px; }}"
            f"QTableWidget {{ background: {t['bg_primary']}; color: {t['fg_editor']};"
            f" gridline-color: {t['border_separator']}; }}"
            f"QPlainTextEdit {{ background: {t['bg_primary']}; color: {t['fg_editor']};"
            f" border: 1px solid {t['border_separator']};"
            f" font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 11px; }}"
        )

    # --- boyut/hizalama senkronu ---

    def _sinirlari_genislet(self, nsatir: int, nkolon: int):
        """Spinbox üst sınırlarını yüklenen veriye göre büyüt.

        SPINBOX ile GRID AYRIŞMAMALI. Eskiden `setValue` sınıra kırpılıyor
        ama grid gerçek boyutu alıyordu; hangisi sonra çalışırsa o kazanıyor
        ve fazlalık SESSİZCE gidiyordu. Ölçüldü:

          1200 satırlık CSV: grid 1200 alıyor, spinbox 1000'de kalıyor.
            Kullanıcı spinbox'a dokununca `_resize_grid` 1000'e indiriyor,
            200 satır uyarısız kayboluyor.
          35 kolonlu CSV: `_on_cols_changed` yüklemeden HEMEN SONRA gridi
            30'a indiriyor, 5 kolon anında gidiyor.

        Sınırı büyütmek YENİ MALİYET getirmiyor: grid zaten bugün de gerçek
        satır sayısıyla kuruluyor, sınırlı olan yalnızca spinbox'tı.
        """
        if nsatir > self._rows.maximum():
            self._rows.setMaximum(nsatir)
        if nkolon > self._cols.maximum():
            self._cols.setMaximum(nkolon)

    def _resize_grid(self):
        self._grid.setRowCount(self._rows.value())

    def _on_cols_changed(self):
        if self._updating:
            return
        self._updating = True
        try:
            self._grid.setColumnCount(self._cols.value())
            # hizalama kutularını yeniden kur (mevcut seçimleri koru)
            old = []
            for i in range(self._align_box.count()):
                w = self._align_box.itemAt(i).widget()
                if w is not None:
                    old.append(_ALIGNS[w.currentIndex()][1])
            while self._align_box.count():
                w = self._align_box.takeAt(0).widget()
                if w:
                    w.deleteLater()
            for col in range(self._cols.value()):
                combo = QComboBox()
                for label, _token in _ALIGNS:
                    combo.addItem(label)
                combo.setCurrentIndex({"l": 0, "c": 1, "r": 2, "p": 3}.get(
                    old[col] if col < len(old) else "c", 1))
                self._align_box.addWidget(combo)
                combo.currentIndexChanged.connect(self._update_preview)
        finally:
            self._updating = False
        self._update_preview()

    def _on_env_changed(self, _t):
        # longtable yüzen kılıf içinde olamaz
        if self._env.currentText() == "longtable":
            self._cb_wrap.setChecked(False)
            self._cb_wrap.setEnabled(False)
        else:
            self._cb_wrap.setEnabled(True)
        self._update_preview()

    # --- veri akışı ---

    def _on_grid_changed(self, _item):
        self._update_preview()

    def _on_caption_changed(self, _t):
        if not self._label_manual:
            self._label.setText(suggest_label(self._existing, self._caption.text()))
        self._update_preview()

    def _load_csv(self):
        path, _f = QFileDialog.getOpenFileName(
            self, _("CSV Yükle"), "", _("CSV dosyaları (*.csv *.txt);;Tüm Dosyalar (*)"))
        if not path:
            return
        try:
            rows = csv_to_rows(path)
        except (OSError, UnicodeError, csv.Error, ValueError):
            # Yalnız OSError yakalanıyordu; UnicodeDecodeError buradan kaçıp
            # slot'tan dışarı çıkıyor ve düğme sessizce hiçbir şey yapmamış
            # gibi oluyordu. Okuma artık kodlamayı kendi çözüyor, bu geniş
            # yakalama ikinci hat.
            self._preview.setPlainText(_("CSV okunamadı"))
            return
        if not rows:
            self._preview.setPlainText(_("CSV boş görünüyor"))
            return
        self._updating = True
        try:
            ncols = max(len(r) for r in rows)
            self._sinirlari_genislet(len(rows), ncols)
            self._rows.setValue(len(rows))
            self._grid.setRowCount(len(rows))
            self._cols.setValue(ncols)
            self._grid.setColumnCount(ncols)
            self._grid.clearContents()
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    self._grid.setItem(i, j, QTableWidgetItem(cell))
        finally:
            self._updating = False
        self._on_cols_changed()
        self._update_preview()

    def _load_from_code(self):
        """Yapıştırılan LaTeX tablo kodunu çözümle ve grid'e yükle.

        Daha önce üretilen/başka yerden kopyalanan tabloyu sihirbazla yeniden
        düzenlemeyi sağlar. İlk tabular ortamı alınır; table kılıfındaki
        caption/label varsa alanlara doldurulur.
        """
        from PyQt6.QtWidgets import QMessageBox

        dlg = QDialog(self)
        dlg.setWindowTitle(_("Koddan Yükle"))
        dlg.setMinimumSize(560, 380)
        v = QVBoxLayout(dlg)
        edit = QPlainTextEdit()
        edit.setPlaceholderText(
            _("LaTeX tablo kodunu yapıştırın (\\begin{tabular} ... \\end{tabular})"))
        v.addWidget(edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(_("Yükle"))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        code = edit.toPlainText()
        block = parse_first_tabular(code)
        if block is None:
            QMessageBox.warning(
                self, _("Koddan Yükle"),
                _("Yapıştırdığınız kodda tabular ortamı bulunamadı"))
            return
        self.load_block(block)
        caption, label = extract_caption_label(code)
        if caption:
            self._caption.setText(caption)
        if label:
            self._label.setText(label)
            self._label_manual = True
        self._update_preview()

    def set_meta(self, caption: str, label: str):
        """Düzenlenen kılıfın caption/label'ını alanlara taşı (table_ops için)."""
        if caption:
            self._caption.setText(caption)
        if label:
            self._label.setText(label)
            self._label_manual = True

    def cells(self) -> list[list[str]]:
        """Grid'den hücre satırlarını oku (tamamen boş satırlar atılır)."""
        rows = []
        for i in range(self._grid.rowCount()):
            row = []
            for j in range(self._grid.columnCount()):
                item = self._grid.item(i, j)
                row.append(item.text() if item else "")
            if any(c.strip() for c in row):
                rows.append(row)
        return rows

    def _aligns(self) -> list[str]:
        tokens = []
        for i in range(self._align_box.count()):
            w = self._align_box.itemAt(i).widget()
            tokens.append(_ALIGNS[w.currentIndex()][1] if w else "c")
        return tokens

    def options(self) -> TableOptions:
        return TableOptions(
            environment=self._env.currentText(),
            booktabs=self._cb_booktabs.isChecked(),
            header_row=self._cb_header.isChecked(),
            vertical_lines=self._cb_vlines.isChecked(),
            wrap_table=self._cb_wrap.isChecked(),
            caption=self._caption.text(),
            label=self._label.text().strip(),
        )

    def result_text(self) -> str:
        return build_tabular(self.cells(), self._aligns(), self.options())

    def _update_preview(self):
        if self._updating:
            return
        code = self.result_text()
        self._preview.setPlainText(code if code else _("Hücrelere veri yazın veya CSV yükleyin"))

    # --- mevcut tabloyu düzenleme ---

    def load_block(self, block: dict):
        """parse_tabular_at çıktısını grid/seçeneklere yükle (düzenleme modu)."""
        self._updating = True
        try:
            rows = block["rows"]
            nrows = max(1, len(rows))
            ncols = max(1, max((len(r) for r in rows), default=1))
            # Yapıştırılan tablo da sınırları aşabilir; bkz. _sinirlari_genislet
            self._sinirlari_genislet(nrows, ncols)
            self._rows.setValue(nrows)
            self._grid.setRowCount(nrows)
            self._cols.setValue(ncols)
            self._grid.setColumnCount(ncols)
            self._grid.clearContents()
            # Kaçışlar AÇILARAK yüklenir: \% → %. Üretimde escape_cell yeniden
            # kaçırır; ham hücreyi koysaydık çift kaçış (\\%) oluşurdu.
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    self._grid.setItem(i, j, QTableWidgetItem(unescape_cell(cell)))
        finally:
            self._updating = False
        # Kolon sayısı değiştiyse hizalama kutularını YENİDEN KUR. Yukarıdaki
        # _updating kilidi _on_cols_changed'i erkenden döndürdü (valueChanged
        # sinyali kilit içindeyken geldi); kurulum yapılmazsa kutu sayısı eski
        # kalır ve 3 kolonlu dialog'a yüklenen 5 kolonlu tablo 'lllcc' üretirdi.
        self._on_cols_changed()
        # kolon spec → hizalama kutuları (p{2cm} ve X gibi belirteçler 'p'ye iner)
        spec = (block.get("col_spec") or "").lower()
        aligns = []
        for m in re.finditer(r"p\{[^{}]*\}|[lcrx]", spec):
            token = m.group(0)
            aligns.append("p" if token.startswith(("p", "x")) else token)
        self._aligns_from_spec(aligns)
        if block.get("env") in _ENVS:
            self._env.setCurrentText(block["env"])
        self._update_preview()

    def _aligns_from_spec(self, aligns: list[str]):
        self._updating = True
        try:
            for i in range(self._align_box.count()):
                w = self._align_box.itemAt(i).widget()
                if w is None:
                    continue
                token = aligns[i] if i < len(aligns) else "c"
                w.setCurrentIndex({"l": 0, "c": 1, "r": 2, "p": 3}.get(token, 1))
        finally:
            self._updating = False

