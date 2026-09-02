"""PdfViewer UI kurulumu — araç çubuğu, scroll area, tema, kaydetme."""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QFileDialog, QLineEdit,
)

from PyQt6.QtCore import QCoreApplication
_ = lambda s: QCoreApplication.translate("PdfViewer", s)


class PdfUISetupMixin:

    def _setup_ui(self):
        _t = self._theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 4, 4, 4)

        self._btn_prev = QPushButton("<")
        self._btn_prev.setFixedWidth(30)
        self._btn_prev.clicked.connect(self.prev_page)

        self._lbl_page = QLabel(_("Sayfa 0 / 0"))
        self._lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_next = QPushButton(">")
        self._btn_next.setFixedWidth(30)
        self._btn_next.clicked.connect(self.next_page)

        self._btn_zoom_out = QPushButton("-")
        self._btn_zoom_out.setFixedWidth(30)
        self._btn_zoom_out.clicked.connect(self.zoom_out)

        self._lbl_zoom = QLabel("100%")
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_zoom.setFixedWidth(50)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setFixedWidth(30)
        self._btn_zoom_in.clicked.connect(self.zoom_in)

        from PyQt6.QtGui import QIcon, QPainter, QPen, QColor, QPixmap
        from PyQt6.QtCore import QRectF, QLineF

        # Genişliğe sığdır ←→ ikonu
        fw_px = QPixmap(16, 16)
        fw_px.fill(QColor(0, 0, 0, 0))
        fp = QPainter(fw_px)
        fp.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(_t['fg_muted'])
        fp.setPen(QPen(c, 1.5))
        fp.drawLine(QLineF(2, 8, 14, 8))
        fp.drawLine(QLineF(5, 5, 2, 8))
        fp.drawLine(QLineF(5, 11, 2, 8))
        fp.drawLine(QLineF(11, 5, 14, 8))
        fp.drawLine(QLineF(11, 11, 14, 8))
        fp.end()
        self._btn_fit_w = QPushButton(QIcon(fw_px), "")
        self._btn_fit_w.setFixedWidth(28)
        self._btn_fit_w.setToolTip(_("Genişliğe Sığdır"))
        self._btn_fit_w.clicked.connect(self.fit_width)
        self._btn_fit_w.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 2px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
        )

        # Sayfaya sığdır ↕↔ ikonu
        fp_px = QPixmap(16, 16)
        fp_px.fill(QColor(0, 0, 0, 0))
        pp = QPainter(fp_px)
        pp.setRenderHint(QPainter.RenderHint.Antialiasing)
        pp.setPen(QPen(c, 1.5))
        pp.drawLine(QLineF(2, 3, 14, 3))
        pp.drawLine(QLineF(2, 13, 14, 13))
        pp.drawLine(QLineF(2, 3, 2, 6))
        pp.drawLine(QLineF(14, 3, 14, 6))
        pp.drawLine(QLineF(2, 13, 2, 10))
        pp.drawLine(QLineF(14, 13, 14, 10))
        pp.end()
        self._btn_fit_p = QPushButton(QIcon(fp_px), "")
        self._btn_fit_p.setFixedWidth(28)
        self._btn_fit_p.setToolTip(_("Sayfaya Sığdır"))
        self._btn_fit_p.clicked.connect(self.fit_page)
        self._btn_fit_p.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 2px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
        )

        self._btn_save = QPushButton(_("💾 Farklı Kaydet"))
        self._btn_save.setFixedWidth(110)
        self._btn_save.clicked.connect(self._save_as)
        self._btn_save.setEnabled(False)

        from PyQt6.QtGui import QIcon
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, 'linux', 'invert.svg')
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'linux', 'invert.svg')
        self._btn_invert = QPushButton(QIcon(icon_path), "")
        self._btn_invert.setCheckable(True)
        self._btn_invert.setFixedWidth(60)
        self._btn_invert.setToolTip(_("PDF renklerini ters çevir"))
        self._btn_invert.toggled.connect(self._toggle_invert)

        self._btn_present = QPushButton(_("⛶ Sunum"))
        self._btn_present.setFixedWidth(80)
        self._btn_present.setToolTip(_("Sunum modu (F5)"))
        self._btn_present.clicked.connect(self.enter_presentation)

        from PyQt6.QtGui import QIcon, QPainter, QPen, QColor, QPixmap
        bm_px = QPixmap(20, 20)
        bm_px.fill(QColor(0, 0, 0, 0))
        p = QPainter(bm_px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(_t['fg_muted'])
        p.setPen(QPen(c, 1.8))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRoundedRect(QRectF(4, 2, 12, 16), 1.5, 1.5)
        p.setPen(QPen(c, 1.2))
        p.drawLine(7, 7, 13, 7)
        p.drawLine(7, 11, 13, 11)
        p.end()
        self._btn_bookmarks = QPushButton(QIcon(bm_px), "")
        self._btn_bookmarks.setCheckable(True)
        self._btn_bookmarks.setFixedWidth(30)
        self._btn_bookmarks.setEnabled(False)
        self._btn_bookmarks.setToolTip(_("Yer İmleri"))
        self._btn_bookmarks.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {_t['bg_pressed']}; }}"
            f"QPushButton:checked {{ background: {_t['bg_pressed']}; }}"
            f"QPushButton:disabled {{ opacity: 0.3; }}"
        )
        self._btn_bookmarks.toggled.connect(self._toggle_bookmarks)

        toolbar.addWidget(self._btn_prev)
        toolbar.addWidget(self._lbl_page)
        toolbar.addWidget(self._btn_next)
        toolbar.addStretch()
        toolbar.addWidget(self._btn_zoom_out)
        toolbar.addWidget(self._lbl_zoom)
        toolbar.addWidget(self._btn_zoom_in)
        toolbar.addWidget(self._btn_fit_w)
        toolbar.addWidget(self._btn_fit_p)
        toolbar.addWidget(self._btn_save)
        toolbar.addWidget(self._btn_invert)
        toolbar.addWidget(self._btn_present)
        toolbar.addWidget(self._btn_bookmarks)

        # Cift sayfa toggle
        dp_px = QPixmap(20, 16)
        dp_px.fill(QColor(0, 0, 0, 0))
        dp = QPainter(dp_px)
        dp.setRenderHint(QPainter.RenderHint.Antialiasing)
        dc = QColor(_t['fg_muted'])
        dp.setPen(QPen(dc, 1.2))
        dp.setBrush(QColor(0, 0, 0, 0))
        dp.drawRect(QRectF(1, 1, 8, 14))
        dp.drawRect(QRectF(11, 1, 8, 14))
        dp.end()
        self._btn_dual = QPushButton(QIcon(dp_px), "")
        self._btn_dual.setCheckable(True)
        self._btn_dual.setFixedWidth(30)
        self._btn_dual.setToolTip(_("Çift Sayfa"))
        self._btn_dual.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {_t['bg_pressed']}; }}"
            f"QPushButton:checked {{ background: {_t['bg_pressed']}; }}"
        )
        self._btn_dual.toggled.connect(self._toggle_dual_page)
        toolbar.addWidget(self._btn_dual)

        self._btn_search = QPushButton("🔍")
        self._btn_search.setFixedWidth(30)
        self._btn_search.setToolTip(_("PDF'te Ara (Ctrl+F)"))
        self._btn_search.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_t['fg_muted']}; border: none; border-radius: 3px; padding: 4px; }}"
            # hover'da metin de parlaklasmali: fg_muted daha acik bir zemine
            # binince karsitlik alti temada esigin altina dusuyordu.
            f"QPushButton:hover {{ background: {_t['bg_hover']}; color: {_t['fg_bright']}; }}"
            f"QPushButton:disabled {{ opacity: 0.3; }}"
        )
        self._btn_search.clicked.connect(self._toggle_search_bar)
        toolbar.addWidget(self._btn_search)

        toolbar_widget = QWidget()
        toolbar_widget.setLayout(toolbar)
        layout.addWidget(toolbar_widget)

        # Arama çubuğu (başlangıçta gizli)
        self._init_search_state()
        search_bar = QHBoxLayout()
        search_bar.setContentsMargins(4, 2, 4, 2)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(_("PDF'te ara..."))
        self._search_input.setFixedHeight(26)
        self._search_input.returnPressed.connect(self._on_search_return)
        self._search_input.setStyleSheet(
            f"QLineEdit {{ background: {_t['bg_secondary']}; color: {_t['fg_primary']}; border: 1px solid {_t['border_input']}; border-radius: 3px; padding: 2px 6px; font-size: 11px; }}"
        )

        from PyQt6.QtGui import QIcon, QPainter, QPen, QColor, QPixmap, QBrush
        from PyQt6.QtCore import QRectF, QLineF

        def _make_arrow(down=False):
            px = QPixmap(16, 16)
            px.fill(QColor(0, 0, 0, 0))
            p = QPainter(px)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QColor(_t['fg_muted'])
            p.setPen(QPen(c, 2))
            p.setBrush(QBrush(c))
            if down:
                p.drawLine(QLineF(4, 5, 8, 11))
                p.drawLine(QLineF(8, 11, 12, 5))
            else:
                p.drawLine(QLineF(4, 11, 8, 5))
                p.drawLine(QLineF(8, 5, 12, 11))
            p.end()
            return QIcon(px)

        self._search_prev_btn = QPushButton(_make_arrow(down=False), "")
        self._search_prev_btn.setFixedSize(26, 26)
        self._search_prev_btn.setToolTip(_("Önceki"))
        self._search_prev_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
        )
        self._search_prev_btn.clicked.connect(self._search_prev)

        self._search_next_btn = QPushButton(_make_arrow(down=True), "")
        self._search_next_btn.setFixedSize(26, 26)
        self._search_next_btn.setToolTip(_("Sonraki"))
        self._search_next_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; }}"
        )
        self._search_next_btn.clicked.connect(self._search_next)

        self._search_count_label = QLabel("")
        self._search_count_label.setFixedWidth(60)
        self._search_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._search_count_label.setStyleSheet(f"color: {_t['fg_muted']}; font-size: 11px;")

        close_px = QPixmap(16, 16)
        close_px.fill(QColor(0, 0, 0, 0))
        cp = QPainter(close_px)
        cp.setRenderHint(QPainter.RenderHint.Antialiasing)
        cc = QColor(_t['fg_muted'])
        cp.setPen(QPen(cc, 2))
        cp.drawLine(QLineF(4, 4, 12, 12))
        cp.drawLine(QLineF(12, 4, 4, 12))
        cp.end()
        self._search_close_btn = QPushButton(QIcon(close_px), "")
        self._search_close_btn.setFixedSize(26, 26)
        self._search_close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_t['fg_muted']}; border: none; border-radius: 3px; }}"
            f"QPushButton:hover {{ background: {_t['bg_hover']}; color: {_t['fg_primary']}; }}"
        )
        self._search_close_btn.clicked.connect(self._close_search)

        search_bar.addWidget(self._search_input)
        search_bar.addWidget(self._search_count_label)
        search_bar.addWidget(self._search_prev_btn)
        search_bar.addWidget(self._search_next_btn)
        search_bar.addWidget(self._search_close_btn)

        self._search_bar_widget = QWidget()
        self._search_bar_widget.setLayout(search_bar)
        self._search_bar_widget.hide()
        layout.addWidget(self._search_bar_widget)

        # Yer imleri paneli + PDF alanı yan yana
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._setup_bookmarks_panel()
        body.addWidget(self._bookmark_tree)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {self._theme.get('bg_pdf_scroll', '#1e1e1e')}; }}")

        self._pages_widget = QWidget()
        self._pages_layout = QVBoxLayout(self._pages_widget)
        self._pages_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pages_layout.setSpacing(10)

        self._scroll.setWidget(self._pages_widget)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._pages_widget.setMouseTracking(True)
        self._pages_widget.installEventFilter(self)
        body.addWidget(self._scroll)

        body_widget = QWidget()
        body_widget.setLayout(body)
        layout.addWidget(body_widget)

        self.setMinimumWidth(250)
        self._update_nav()

        self.apply_theme(self._theme)

    def apply_theme(self, t: dict):
        self._theme = t
        bg = "#000000" if self._invert_colors else t['bg_pdf_scroll']
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {bg}; }}")
        # Bookmark ikonunu tema rengiyle yeniden çiz
        from PyQt6.QtGui import QIcon, QPainter, QPen, QColor, QPixmap
        from PyQt6.QtCore import QRectF
        bm_px = QPixmap(20, 20)
        bm_px.fill(QColor(0, 0, 0, 0))
        p = QPainter(bm_px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(t['fg_muted'])
        p.setPen(QPen(c, 1.8))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawRoundedRect(QRectF(4, 2, 12, 16), 1.5, 1.5)
        p.setPen(QPen(c, 1.2))
        p.drawLine(7, 7, 13, 7)
        p.drawLine(7, 11, 13, 11)
        p.end()
        self._btn_bookmarks.setIcon(QIcon(bm_px))
        self._btn_bookmarks.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
            f"QPushButton:checked {{ background: {t['bg_pressed']}; }}"
            f"QPushButton:disabled {{ opacity: 0.3; }}"
        )
        self._apply_bookmark_theme(t)
        self._apply_search_theme(t)
        # Cift sayfa ikonunu yeniden ciz
        dp_px = QPixmap(20, 16)
        dp_px.fill(QColor(0, 0, 0, 0))
        dp2 = QPainter(dp_px)
        dp2.setRenderHint(QPainter.RenderHint.Antialiasing)
        dp2.setPen(QPen(c, 1.2))
        dp2.setBrush(QColor(0, 0, 0, 0))
        dp2.drawRect(QRectF(1, 1, 8, 14))
        dp2.drawRect(QRectF(11, 1, 8, 14))
        dp2.end()
        self._btn_dual.setIcon(QIcon(dp_px))
        self._btn_dual.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 4px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; }}"
            f"QPushButton:pressed {{ background: {t['bg_pressed']}; }}"
            f"QPushButton:checked {{ background: {t['bg_pressed']}; }}"
        )
        # Fit buton ikonlarini yeniden ciz
        from PyQt6.QtCore import QLineF
        fw_px = QPixmap(16, 16)
        fw_px.fill(QColor(0, 0, 0, 0))
        fp2 = QPainter(fw_px)
        fp2.setRenderHint(QPainter.RenderHint.Antialiasing)
        fp2.setPen(QPen(c, 1.5))
        fp2.drawLine(QLineF(2, 8, 14, 8))
        fp2.drawLine(QLineF(5, 5, 2, 8)); fp2.drawLine(QLineF(5, 11, 2, 8))
        fp2.drawLine(QLineF(11, 5, 14, 8)); fp2.drawLine(QLineF(11, 11, 14, 8))
        fp2.end()
        self._btn_fit_w.setIcon(QIcon(fw_px))
        self._btn_fit_w.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 2px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; }}"
        )
        fp_px = QPixmap(16, 16)
        fp_px.fill(QColor(0, 0, 0, 0))
        pp2 = QPainter(fp_px)
        pp2.setRenderHint(QPainter.RenderHint.Antialiasing)
        pp2.setPen(QPen(c, 1.5))
        pp2.drawLine(QLineF(2, 3, 14, 3)); pp2.drawLine(QLineF(2, 13, 14, 13))
        pp2.drawLine(QLineF(2, 3, 2, 6)); pp2.drawLine(QLineF(14, 3, 14, 6))
        pp2.drawLine(QLineF(2, 13, 2, 10)); pp2.drawLine(QLineF(14, 13, 14, 10))
        pp2.end()
        self._btn_fit_p.setIcon(QIcon(fp_px))
        self._btn_fit_p.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 3px; padding: 2px; }}"
            f"QPushButton:hover {{ background: {t['bg_hover']}; }}"
        )
        for label in self._page_labels:
            if label.pixmap() is None or label.pixmap().isNull():
                if self._invert_colors:
                    label.setStyleSheet("background: #000; border: 1px solid #222;")
                else:
                    label.setStyleSheet(
                        f"background: {t['bg_pdf_placeholder']}; border: 1px solid {t['border_input']};"
                    )

    def _toggle_invert(self, checked: bool):
        self._invert_colors = checked
        self._pres_cache.clear()
        bg = "#000000" if checked else self._theme['bg_pdf_scroll']
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {bg}; }}")
        for i, label in enumerate(self._page_labels):
            if i >= self._page_count:
                break
            label.setPixmap(QPixmap())
            label.setStyleSheet(
                f"background: {'#000' if checked else self._theme['bg_pdf_placeholder']}; "
                f"border: 1px solid {'#222' if checked else self._theme['border_input']};"
            )
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, self._render_visible)
        if self._presentation_mode:
            self._presentation_render()

    def _show_message(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {self._theme['fg_label']}; font-size: 14px; padding: 40px;")
        self._page_labels.append(label)
        self._pages_layout.addWidget(label)

    def _save_as(self):
        if not self._pdf_path or not os.path.exists(self._pdf_path):
            return
        name = os.path.basename(self._pdf_path)
        try:
            dest, _sel_filter = QFileDialog.getSaveFileName(self, _("PDF'i Farklı Kaydet"), name, _("PDF Dosyaları (*.pdf)"))
        except Exception as e:
            from core.log import get_logger
            get_logger("pdf_viewer").error("SaveAs dialog hatası: %s", e, exc_info=True)
            return
        if dest:
            import shutil
            try:
                shutil.copy2(self._pdf_path, dest)
            except Exception as e:
                from core.log import get_logger
                get_logger("pdf_viewer").error("PDF kopyalama hatası: %s", e, exc_info=True)
