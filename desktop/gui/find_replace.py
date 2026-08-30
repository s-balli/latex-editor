"""VS Code tarzı bul/değiştir inline paneli."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox,
)
from PyQt6.Qsci import QsciScintilla

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("FindReplaceBar", s)


class FindReplaceBar(QWidget):
    # "Tümünü Değiştir" için üst sınır. Döngü normalde kendiliğinden biter
    # (arama wrap'siz ileri gider, imleç her değiştirmede ilerler); bu yalnız
    # patolojik bir durumda takılmamak için konmuş bir emniyet kemeri.
    # Sınıra ULAŞILDIĞINDA kullanıcı UYARILMAK zorunda: eskiden sessizce
    # kesiliyor, etiket yine sayıyı yazıyordu ve kullanıcı belgenin yarım
    # değiştiğini ancak derleme hatasından anlıyordu (2026-08-30 denetimi, D5).
    _REPLACE_LIMIT = 10000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editor: QsciScintilla | None = None
        self._match_count = 0
        self._count_timer = QTimer(self)
        self._count_timer.setSingleShot(True)
        self._count_timer.setInterval(300)
        self._count_timer.timeout.connect(self._do_count_matches)
        self._count_text = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText(_("Bul"))
        self._find_input.setFixedWidth(250)
        self._find_input.textChanged.connect(self._on_find_text_changed)
        self._find_input.returnPressed.connect(self._find_next)
        layout.addWidget(self._find_input)

        self._btn_prev = QPushButton("<")
        self._btn_prev.setFixedWidth(28)
        self._btn_prev.clicked.connect(self._find_prev)
        layout.addWidget(self._btn_prev)

        self._btn_next = QPushButton(">")
        self._btn_next.setFixedWidth(28)
        self._btn_next.clicked.connect(self._find_next)
        layout.addWidget(self._btn_next)

        self._lbl_count = QLabel("")
        self._lbl_count.setFixedWidth(80)
        layout.addWidget(self._lbl_count)

        # Değiştir alanı
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText(_("Değiştir"))
        self._replace_input.setFixedWidth(250)
        self._replace_input.returnPressed.connect(self._replace_next)
        layout.addWidget(self._replace_input)

        self._btn_replace = QPushButton(_("Değiştir"))
        self._btn_replace.clicked.connect(self._replace_next)
        layout.addWidget(self._btn_replace)

        self._btn_replace_all = QPushButton(_("Tümünü Değiştir"))
        self._btn_replace_all.clicked.connect(self._replace_all)
        layout.addWidget(self._btn_replace_all)

        layout.addStretch()

        self._btn_close = QPushButton("X")
        self._btn_close.setFixedWidth(24)
        self._btn_close.clicked.connect(self.hide)
        layout.addWidget(self._btn_close)

        self._replace_input.hide()
        self._btn_replace.hide()
        self._btn_replace_all.hide()

        self.setStyleSheet("")

    def apply_theme(self, t: dict):
        self.setStyleSheet(
            f"QWidget {{ background: {t['bg_secondary']}; }}"
            f"QLineEdit {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"padding: 4px 8px; border-radius: 4px; }}"
            f"QLineEdit:focus {{ border: 1px solid {t['accent']}; }}"
            f"QPushButton {{ background: {t['bg_button']}; color: {t['fg_primary']}; border: 1px solid {t['border_input']}; "
            f"padding: 3px 10px; border-radius: 4px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; border: 1px solid {t['accent']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
            f"QLabel {{ color: {t['fg_label']}; background: transparent; }}"
        )

    def set_editor(self, editor: QsciScintilla):
        self._editor = editor

    def show_find(self):
        self._replace_input.hide()
        self._btn_replace.hide()
        self._btn_replace_all.hide()
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()
        self._do_find()

    def show_replace(self):
        self._replace_input.show()
        self._btn_replace.show()
        self._btn_replace_all.show()
        self.show()
        self._find_input.setFocus()
        self._find_input.selectAll()
        self._do_find()

    def hide(self):
        super().hide()
        if self._editor:
            self._editor.setFocus()
            # Seçimi temizle ama indicator'ları bırak

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def _on_find_text_changed(self):
        self._do_find()

    def _do_find(self):
        if not self._editor:
            return
        text = self._find_input.text()
        if not text:
            self._lbl_count.setText("")
            self._match_count = 0
            return

        # İlk eşleşmeyi bul
        self._find_next_in_text(text, forward=True, wrap=True)
        # Sayıyı debounce et — her tuş vuruşunda metin kopyalamasın
        self._count_text = text
        self._count_timer.start()

    def _find_next_in_text(self, text, forward=True, wrap=True):
        if not self._editor or not text:
            return
        line, col = self._editor.getCursorPosition()

        # QScintilla findFirst: (expr, re, cs, wo, wrap, forward, line, col)
        found = self._editor.findFirst(
            text, False, False, False, wrap, forward, line, col
        )
        if not found:
            self._lbl_count.setText("0/0")

    def _find_next(self):
        text = self._find_input.text()
        if not text:
            return
        self._find_next_in_text(text, forward=True, wrap=True)
        self._update_current_match()

    def _find_prev(self):
        text = self._find_input.text()
        if not text:
            return
        self._find_next_in_text(text, forward=False, wrap=True)
        self._update_current_match()

    def _do_count_matches(self):
        if not self._editor or not self._count_text:
            return
        self._count_matches(self._count_text)

    def _count_matches(self, text):
        if not self._editor or not text:
            self._match_count = 0
            self._lbl_count.setText("")
            return

        content = self._editor.text().lower()
        self._match_count = content.count(text.lower())
        self._update_current_match()

    def _update_current_match(self):
        if self._match_count == 0:
            self._lbl_count.setText(_("Sonuç yok"))
        else:
            self._lbl_count.setText(_("{n} sonuç").format(n=self._match_count))

    def _replace_next(self):
        if not self._editor:
            return
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if not find_text:
            return

        self._editor.setFocus()
        self._editor.beginUndoAction()

        # İleriye doğru ara (wrap=False)
        line, col = self._editor.getCursorPosition()
        found = self._editor.findFirst(
            find_text, False, False, False, False, True, line, col
        )

        # Bulunamazsa başa dönüp tekrar ara
        if not found or not self._editor.hasSelectedText():
            found = self._editor.findFirst(
                find_text, False, False, False, False, True, 0, 0
            )

        if found and self._editor.hasSelectedText():
            self._editor.replaceSelectedText(replace_text)

            # Sonrakini bul ve göster
            line, col = self._editor.getCursorPosition()
            self._editor.findFirst(
                find_text, False, False, False, True, True, line, col
            )

        self._editor.endUndoAction()
        self._count_matches(find_text)

    def _replace_all(self):
        if not self._editor:
            return
        find_text = self._find_input.text()
        replace_text = self._replace_input.text()
        if not find_text:
            return

        self._editor.setFocus()
        self._editor.beginUndoAction()

        # Başa dönüp tek tek bul ve değiştir
        self._editor.setCursorPosition(0, 0)
        count = 0
        found = self._editor.findFirst(
            find_text, False, False, False, False, True, 0, 0
        )
        sinira_ulasildi = False
        while found and self._editor.hasSelectedText():
            if count >= self._REPLACE_LIMIT:
                sinira_ulasildi = True
                break
            self._editor.replaceSelectedText(replace_text)
            count += 1
            line, col = self._editor.getCursorPosition()
            found = self._editor.findFirst(
                find_text, False, False, False, False, True, line, col
            )

        self._editor.endUndoAction()
        self._match_count = 0
        self._lbl_count.setText(_("{n} değişiklik").format(n=count))

        if sinira_ulasildi:
            # Sessiz kesme yok: belge YARIM değişti, kullanıcı bilmeli.
            # Arama ileri yönlü ve wrap'siz olduğu için komutu tekrarlamak
            # kaldığı yerden devam eder — eyleme dönük tavsiye bu.
            QMessageBox.warning(
                self, _("Tümünü Değiştir"),
                _("{n} değişiklik yapıldı ve güvenlik sınırına ulaşıldı.\n\n"
                  "Belgede değiştirilmemiş eşleşmeler kalmış olabilir; "
                  "işlemi tekrarlayarak kaldığı yerden sürdürebilirsiniz.").format(n=count),
            )
